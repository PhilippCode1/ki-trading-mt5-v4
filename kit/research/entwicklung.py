"""Entwicklungsauswertung F-04 (Vorregistrierung docs/bot/prereg/F04_ENTWURF.md, Plan F-1 §5 Tor 85) – nur Entwicklungsperiode.

Ablauf (kit forschung …, Versuchsprotokoll forschung/versuchsprotokoll.jsonl):
  1. vorab        – Code-Hashes, Commit, Schwellen- und PREREG-SHA vor jeder Datensicht (protokoll.vorab).
  2. kostenprofil – erste Datensicht: Abzüge laden (Hash- und Holdout-Prüfung), Spreadprofil je Symbol aus den H1-Kerzen
                    (DATA_VIEW, Familie F04-DATEN). Kommission laut erstem Demo-Trade (0) mit Gegenprobe Startwert 3,25 je Lot und
                    Seite, Swappunkte aus config/kostenprofil/f04_startwerte.json (privat).
  3. entwicklung  – je Variante ein TRIAL „Beginn“, dann je Variante drei Läufe des Takts über die ganze Entwicklungsperiode
                    (Hauptprofil, Kosten × 1,5, Kommission 3,25), Bewertung der OOS-Trades (Walk-Forward: Anpassung 3 Jahre, Test 1 Jahr),
                    Zufallsbasis mit kompletter Ausstiegslogik, Parität, DSR mit allen Versuchen der Familie; Bericht berichte/forschung/
                    <datum>_entwicklung.md/.json (nur %, R, Anzahl, Trades/Monat); je Variante ein TRIAL „Ergebnis“.
Der Holdout wird nie gezogen oder gelesen (Datenleser bricht bei Kerzen ab 01.07.2021 ab).
S-BL-01 (Referenz) läuft nicht über den Takt (kein Server-TP), nur als Signal-/Trade-Rechnung nach BL-TFD1; zählt nie für das Tor.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import statistics
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from pathlib import Path

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt, zufallspaar
from kit.backtest.kosten import Kostenprofil
from kit.backtest.terminal import punkt
from kit.config import Konfiguration
from kit.domain.types import Bar
from kit.gates import ROOT, tore
from kit.gates import trade_test as tt
from kit.gates.tor_t import mechanik_hash
from kit.research import daten, protokoll, stats, trials
from kit.strategy import donchian_ref
from kit.strategy import varianten as var
from kit.strategy.base import strategie_hash

UTC = dt.UTC
D = Decimal
SYMBOLE = ("EURUSD", "USDJPY", "GBPUSD", "CHFJPY", "CADJPY", "AUDUSD", "NZDUSD")
STARTWERTE = ROOT / "config" / "kostenprofil" / "f04_startwerte.json"
SPREADPROFIL = ROOT / "config" / "kostenprofil" / "f04_spreadprofil.json"      # aus der Datensicht, privat (nicht im Spiegel)
BERICHTE = ROOT / "berichte" / "forschung"
PROFILE = ("HAUPT", "KOSTEN_X1_5", "GEGENPROBE_3_25")
MONAT_S = 365.25 / 12 * 86400
FAMILIE_DATEN = "F04-DATEN"
_DATEN: dict | None = None          # je Arbeitsprozess einmal geladen


# ---------------------------------------------------------------------------------------------------- Eingaben
def db_pfad() -> Path:
    from kit import paths
    return paths.kit_home() / "marktdaten" / "entwicklung.sqlite"


def bot_konf() -> Konfiguration:
    return runner.bot_konfiguration()


def startwerte(pfad: Path = STARTWERTE) -> dict:
    return json.loads(Path(pfad).read_text(encoding="utf-8"))


def kostenprofil(name: str, sw: Mapping) -> Kostenprofil:
    """HAUPT: Kommission laut erstem Demo-Trade; KOSTEN_X1_5: HAUPT × Kostenfaktor; GEGENPROBE_3_25: Startwert cost_truth."""
    konf = tt.konfig()["kosten"]
    swap = {s: (D(str(a)), D(str(b))) for s, (a, b) in sw["swap_punkte"].items()}
    haupt = Kostenprofil("HAUPT", D(konf["provision_gemessen"]), swap, int(konf["dreifachtag"]), fx_gebuehr=D(str(sw.get("fx_gebuehr", "0"))))
    if name == "HAUPT":
        return haupt
    if name == "KOSTEN_X1_5":
        return haupt.mal(konf["kostenfaktor"], name="KOSTEN_X1_5")
    if name == "GEGENPROBE_3_25":
        return Kostenprofil("GEGENPROBE_3_25", D(konf["provision_gegenprobe"]), swap, int(konf["dreifachtag"]), fx_gebuehr=haupt.fx_gebuehr)
    raise ValueError(f"unbekanntes Kostenprofil {name}")


def zeitraum() -> tuple[str, str, str]:
    wf = tt.konfig()["walk_forward"]
    return wf["entwicklung_start"], wf["entwicklung_ende"], bot_konf().holdout[0]


def daten_laden(db: Path, zeitrahmen: Sequence[str] = ("H1", "H4", "D1"), soll: Mapping[str, str] | None = None) -> dict:
    """{"kerzen": {tf: {symbol: [Bar]}}, "abzuege": [Kennzahlen]} – nur lesend, mit Hash- und Holdout-Prüfung je Abzug.
    soll = {"SYMBOL/TF": sha256} bindet an die Abzüge der Datensicht (sonst der jüngste OK-Abzug)."""
    start, ende, holdout = zeitraum()
    versatz = serverversatz_daten()
    cache: dict = {}
    kerzen: dict[str, dict[str, list[Bar]]] = {tf: {} for tf in zeitrahmen}
    abzuege = []
    for tf in zeitrahmen:
        for sym in SYMBOLE:
            soll_sha = None
            if soll is not None:
                soll_sha = soll.get(f"{sym}/{tf}")
                if not soll_sha:
                    raise daten.DatenFehler(f"{sym}/{tf}: kein Abzug in der Datensicht")
            bars, info = daten.lesen(db, sym, tf, start=start, ende=ende, holdout_ab=holdout, zwischenspeicher=cache, soll_sha=soll_sha,
                                     versatz_s=versatz)
            kerzen[tf][sym] = bars
            abzuege.append(info)
    return {"kerzen": kerzen, "abzuege": abzuege}


def serverversatz_daten() -> int:
    """Die Abzüge stehen in Serverzeit (F-04-Befund); umgerechnet wird mit dem festen Versatz aus config/trade_test.toml [konto]
    (+3 h). Der Server folgt der New-Yorker Sommerzeit: im US-Sommer exakt, im Winter (UTC+2) liegt die Backtest-Uhr 1 h hinter der
    echten UTC – Servermitternacht und Rollover bleiben richtig, das Handelsfenster (Berlin) liegt dann 1 h später (Bericht: Grenzen)."""
    return int(tt.konfig()["konto"]["versatz_s"])


def spreadprofil(h1: Mapping[str, Sequence[Bar]]) -> dict:
    """Spread je Symbol aus den H1-Kerzen (Points): Median, 10./90. Perzentil, Mittel, Anteil Kerzen mit Spread 0."""
    aus = {}
    for sym, bars in h1.items():
        sp = sorted(b.spread_points for b in bars)
        n = len(sp)
        aus[sym] = {"median": statistics.median(sp), "p10": sp[int(0.1 * (n - 1))], "p90": sp[int(0.9 * (n - 1))],
                    "mittel": round(sum(sp) / n, 2), "anteil_null": round(sum(1 for x in sp if x == 0) / n, 4), "kerzen": n}
    return aus


# ---------------------------------------------------------------------------------------------------- ein Lauf (Arbeitsprozess)
def _daten(db: str, soll: Mapping[str, str]) -> dict:
    global _DATEN
    if _DATEN is None:
        _DATEN = daten_laden(Path(db), ("H1", "H4"), soll)
    return _DATEN


def fenster() -> list[tuple[int, int]]:
    wf = tt.konfig()["walk_forward"]
    return tt.walk_forward(wf["entwicklung_start"], wf["entwicklung_ende"], int(wf["anpassung_jahre"]), int(wf["test_jahre"]))


def _json(x: object) -> object:
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {str(k): _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return "unendlich" if x > 0 else None
    return x


def aufgabe(variante_id: str, profil_name: str, db: str, sw: dict, soll: dict[str, str]) -> dict:
    """Ein Lauf des Takts über die ganze Entwicklungsperiode und seine Bewertung (nur Kennzahlen, keine Kurse). soll bindet die
    Kerzen an die Abzüge der Datensicht (Hash je Symbol/Zeitrahmen)."""
    d = _daten(db, soll)
    h1, h4 = d["kerzen"]["H1"], d["kerzen"]["H4"]
    v = next(x for x in var.varianten() if x.id == variante_id)
    strat = var.strategie(v)
    profil = kostenprofil(profil_name, sw)
    konf = tt.konfig()
    k = konf["konto"]
    einst = runner.Einstellungen(profil, start_equity=D(k["start_equity"]), hebel=int(k["hebel"]), versatz_s=int(k["versatz_s"]))
    tf_kerzen = h4 if strat.zeitrahmen == "H4" else None
    with tempfile.TemporaryDirectory(prefix="kit_f04_") as ablage:
        erg = runner.laufen(strat, h1, Path(ablage), einst, tf_kerzen=tf_kerzen)
    return bewerten_lauf(erg, strat, profil, h1, h4 if tf_kerzen else h1, variante_id, profil_name, konf)


def bewerten_lauf(erg: runner.Ergebnis, strat, profil: Kostenprofil, h1: Mapping, kerzen_tf: Mapping, variante_id: str,
                  profil_name: str, konf: dict, *, spread_abgebildet: bool = False) -> dict:
    """Bewertung eines Laufs. kerzen_tf = Kerzen des Strategie-Zeitrahmens für die Signal-Parität; spread_abgebildet = True, wenn sie
    schon so aussehen wie im Takt (Spread des Kostenprofils, H4 mit dem Spread der H1-Kerze desselben Schlusses – F-05 MetaFilter)."""
    t = tore()
    fe = fenster()
    von, bis = fe[0][0], fe[-1][1]
    paare = [(tr, de) for tr, de in zip(erg.trades, erg.details, strict=True) if any(a <= tr.t_auf < b for a, b in fe)]
    trades_oos = [tr for tr, _ in paare]
    kurve_oos = [(z, e) for z, e in erg.kurve if von <= z < bis]
    m = Markt(h1, profil, versatz_s=int(konf["konto"]["versatz_s"]))
    zufall = [zufallspaar(m, de.symbol, de.t_auf, abs(de.preis_auf - de.sl), abs(de.tp - de.preis_auf), de.lots, strat.max_halte_s)
              for _, de in paare]
    signale_oos = [s for s in erg.signale if von <= s["t"] < bis]
    monate = (bis - von) / MONAT_S
    bew = tt.bewerten(trades_oos, kurve_oos, signale_oos, erg.schatten, zufall, t, konf, monate=monate, zeitraum=(von, bis))
    tp = paritaet.trade_paritaet(erg.details, m, strat.max_halte_s)
    sp = paritaet.signal_paritaet(erg.signale, strat, kerzen_tf, m.schritte, spread_points=None if spread_abgebildet else profil.spread_points)
    z = konf["zusatz"]
    teil_eur = tt.teilperioden(trades_oos, int(z["teilperioden"]), von, bis)
    teil_r = [0.0] * int(z["teilperioden"])
    for tr in trades_oos:
        teil_r[min(len(teil_r) - 1, max(0, (tr.t_zu - von) * len(teil_r) // (bis - von)))] += tr.r
    unvollstaendig = sum(1 for v in erg.vorfaelle if v.get("art") == "TRADE_UNVOLLSTAENDIG")
    technik_ok = erg.technik_ok and not erg.sperren and not unvollstaendig and tp["quote"] == 1.0 and sp["quote"] == 1.0
    bew["kriterien"]["technik"] = {
        "wert": {"technik_ok": erg.technik_ok, "sperren": erg.sperren, "unvollstaendig": unvollstaendig, "trade_paritaet": tp["quote"],
                 "signal_paritaet": sp["quote"]},
        "schwelle": "technik_ok, keine Sperren, Parität 100 %", "ok": True if technik_ok else None,
        "text": "Lauf technisch gültig (keine Sperre/kein Vorfall, alle Trades vollständig, Signal- und Trade-Parität 100 %); "
                "sonst nicht bewertbar = nicht bestanden"}
    bew["bestanden"] = bool(bew["bestanden"] and technik_ok)
    alle = erg.trades
    return _json({
        "variante": variante_id, "profil": profil_name, "strategie_hash": erg.strategie_hash, "mechanik_hash": erg.mechanik_hash,
        "technik_ok": erg.technik_ok, "sperren": erg.sperren, "vorfaelle": dict(Counter(str(v.get("art")) for v in erg.vorfaelle)),
        "schritte": erg.schritte, "offen_am_ende": erg.offen_am_ende, "tagesstopps": erg.tagesstopps,
        "schatten_gesamt": dict(Counter(s["art"] for s in erg.schatten)),
        "bewertung": bew,
        "paritaet": {"trades": {k2: tp[k2] for k2 in ("trades", "zwangsausstiege", "geprueft", "gleich", "quote")},
                     "signale": {k2: sp[k2] for k2 in ("takt", "direkt", "gleich", "quote")}},
        "monatsrenditen": tt.monatsrenditen(kurve_oos, von, bis),
        "teilperioden": {"positiv": [w > 0 for w in teil_eur], "r_summe": [round(x, 3) for x in teil_r]},
        "einstieg_nachteil_ticks": _nachteil(erg.einstieg_nachteil_ticks),
        "gesamt": {"trades": len(alle), "quote": (sum(1 for x in alle if x.gewinn) / len(alle)) if alle else None,
                   "max_dd_prozent": tt.max_drawdown_prozent(erg.kurve)},
        "oos": {"von": von, "bis": bis, "monate": round(monate, 2)},
    })


def _nachteil(ticks: Sequence[int]) -> dict:
    """Fill gegen den erwarteten Einstieg e der Strategie (Ticks, positiv = schlechter). Soll 0: die H4-Kerze trägt im Backtest den
    Spread der H1-Kerze mit demselben Schluss; Abweichungen nur, wenn diese H1-Kerze fehlt."""
    if not ticks:
        return {"n": 0, "mittel": None, "max": None, "anteil_ungleich_null": None}
    return {"n": len(ticks), "mittel": round(sum(ticks) / len(ticks), 2), "max": max(ticks), "min": min(ticks),
            "anteil_ungleich_null": round(sum(1 for t in ticks if t) / len(ticks), 4)}


# ---------------------------------------------------------------------------------------------------- S-BL-01 (Referenz)
def bl01(d1: Mapping[str, Sequence[Bar]], spreads: Mapping[str, dict], fe: Sequence[tuple[int, int]]) -> dict:
    """BL-TFD1 je Symbol (D1, halber Median-Spread je Seite, Kommission 0 wie im Hauptprofil); R = Ergebnis / Anfangsstopp-Abstand."""
    v = next(x for x in var.varianten() if x.id == "S-BL-01")
    p = var.strategie(v)
    rs: list[float] = []
    je_symbol = {}
    for sym, bars in d1.items():
        kerzen = [donchian_ref.Kerze(float(b.high), float(b.low), float(b.close), float(b.open)) for b in bars]
        hs = float(punkt(sym)) * spreads[sym]["median"] / 2
        lauf = donchian_ref.run(kerzen, hs, p)
        r_sym = [(tr.exit_price - tr.entry_price) * tr.direction / tr.stop_distance for tr in lauf.trades
                 if tr.exit_price is not None and any(a <= bars[tr.entry_bar].time < b for a, b in fe)]
        je_symbol[sym] = len(r_sym)
        rs += r_sym
    n = len(rs)
    gew = sum(x for x in rs if x > 0)
    verl = -sum(x for x in rs if x <= 0)
    monate = (fe[-1][1] - fe[0][0]) / MONAT_S
    treffer = sum(1 for x in rs if x > 0)
    return {"variante": "S-BL-01", "zaehlt": False, "trades": n, "trades_je_symbol": je_symbol, "quote": treffer / n if n else None,
            "wilson_95": list(stats.wilson(treffer, n)) if n else None, "e_r": sum(rs) / n if n else None,
            "pf_r": gew / verl if verl > 0 else None, "trades_pro_monat": n / monate, "strategie_hash": _params_hash(p)}


def _params_hash(p) -> str:
    import inspect
    roh = json.dumps({"params": vars(p) if hasattr(p, "__dict__") else str(p), "quelle": inspect.getsource(donchian_ref)}, sort_keys=True,
                     default=str)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------------- DSR, Auswahl, Bericht
def dsr_familie(ergebnisse: Mapping[str, dict], log: list[dict]) -> dict[str, dict | None]:
    """DSR je gezählter Variante mit N und N_eff der Familie F04-ZIEL-STOP aus dem Protokoll (eine Versuchszahl, stats.dsr)."""
    ids = [v.id for v in var.varianten() if v.zaehlt and v.id in ergebnisse]
    reihen = [ergebnisse[i]["monatsrenditen"] for i in ids]
    n = len(reihen[0]) if reihen else 0
    if n < 3 or any(len(r) != n for r in reihen):
        return {i: None for i in ids}
    corr = []
    for a in reihen:
        zeile = []
        for b in reihen:
            zeile.append(_korrelation(a, b))
        corr.append(zeile)
    try:
        anzahl = trials.dsr_trials(log, corr, family=var.FAMILIE_ZIEL_STOP)
    except ValueError as exc:
        return {i: {"fehler": str(exc)} for i in ids}
    srs = []
    for r in reihen:
        try:
            srs.append(stats.sharpe(r))
        except ValueError:
            srs.append(0.0)
    aus: dict[str, dict | None] = {}
    for i, r in zip(ids, reihen, strict=True):
        try:
            d = stats.dsr(r, anzahl, srs)
            aus[i] = {"dsr": d["dsr"], "sr_monat": d["sr"], "sr0": d["sr0"], "N": d["N"], "N_eff": d["N_eff"]}
        except ValueError as exc:
            aus[i] = {"fehler": str(exc)}
    return aus


def _korrelation(a: Sequence[float], b: Sequence[float]) -> float:
    if a is b:
        return 1.0
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    c = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / math.sqrt(va * vb)
    return max(-1.0, min(1.0, c))


def ausfuehren(*, datum: str, prozesse: int | None = None, db: Path | None = None, sw_pfad: Path = STARTWERTE,
               spread_pfad: Path = SPREADPROFIL, protokoll_pfad: Path = protokoll.PFAD, bericht_ordner: Path = BERICHTE, melden=print,
               nur: Sequence[str] | None = None, vorpruefen: bool = True) -> dict:
    """Schritt 3: alle Varianten × Profile, Bewertung, Bericht, Protokoll – genau einmal je Familie.

    Fail-closed vorher: protokoll.vorpruefung (Protokoll ohne Befund, Code und mechanik_hash = Vorregistrierung, Arbeitsbaum committet),
    Datensicht vorhanden, Spreadprofil = Hash der Datensicht, noch kein ERGEBNIS der Familie, kein Bericht dieses Datums. Die Kerzen
    werden an die Abzüge der Datensicht gebunden (Hash je Symbol/Zeitrahmen). nur/vorpruefen=False nur für Tests auf synthetischen Daten."""
    log = protokoll.lesen(protokoll_pfad)
    stand = protokoll.vorpruefung(pfad=protokoll_pfad) if vorpruefen else {"commit": None, "mechanik_hash": mechanik_hash(),
                                                                            "code": protokoll.code_hashes(), "prereg_sha": protokoll.PREREG_SHA}
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == var.FAMILIE_ZIEL_STOP for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung fehlt (kit forschung vorab)")
    sicht = [e for e in log if e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN]
    if not sicht:
        raise protokoll.ProtokollFehler("Kostenprofil/Datensicht fehlt (kit forschung kostenprofil)")
    if any(e["body"].get("kind") == "TRIAL" and e["body"].get("phase") == "ERGEBNIS" and e["body"].get("family") == var.FAMILIE_ZIEL_STOP
           for e in log):
        raise protokoll.ProtokollFehler("Die Familie ist schon ausgewertet – eine Neuauswertung braucht eine neue Vorregistrierung")
    if (Path(bericht_ordner) / f"{datum}_entwicklung.json").exists() or (Path(bericht_ordner) / f"{datum}_entwicklung.md").exists():
        raise protokoll.ProtokollFehler(f"Bericht {datum}_entwicklung existiert schon – nie überschreiben")
    if protokoll.sha256_datei(spread_pfad) != sicht[-1]["body"].get("spreadprofil_sha"):
        raise protokoll.ProtokollFehler("Spreadprofil passt nicht zum Hash der Datensicht")
    spreads = json.loads(Path(spread_pfad).read_text(encoding="utf-8"))["symbole"]
    db = Path(db or db_pfad())
    sw = startwerte(sw_pfad)
    soll = {f"{a['symbol']}/{a['zeitrahmen']}": a["sha256"] for a in sicht[-1]["body"]["daten"]["abzuege"]}
    liste = [v for v in var.varianten() if nur is None or v.id in nur]
    gemeinsam = {"commit": stand["commit"], "prereg_sha": stand["prereg_sha"], "mechanik_hash": stand["mechanik_hash"],
                 "code": stand["code"], "startwerte_sha": protokoll.sha256_datei(sw_pfad),
                 "spreadprofil_sha": sicht[-1]["body"].get("spreadprofil_sha"), "datensicht_seq": sicht[-1]["seq"]}
    for v in liste:
        s = var.strategie(v)
        protokoll.versuch(v.familie, v.id, datum, pfad=protokoll_pfad, phase="BEGINN", parameter=v.parameter, zaehlt=v.zaehlt,
                          strategie_hash=strategie_hash(s) if v.zaehlt else _params_hash(s), **gemeinsam,
                          daten={k: h for k, h in soll.items() if k.endswith("/H1") or (v.id.startswith("S-REV-02") and k.endswith("/H4"))
                                 or (v.id == "S-BL-01" and k.endswith("/D1"))},
                          kostenprofile=list(PROFILE) if v.zaehlt else ["HAUPT"])
    aufgaben = [(v.id, p) for v in liste if v.zaehlt for p in PROFILE]
    n_proz = max(1, min(prozesse or max(1, (os.cpu_count() or 2) - 4), len(aufgaben)))
    melden(f"{len(aufgaben)} Läufe in {n_proz} Prozessen …")
    ergebnisse: dict[tuple[str, str], dict] = {}
    with ProcessPoolExecutor(max_workers=n_proz) as pool:
        zukunft = {pool.submit(aufgabe, vid, p, str(db), sw, soll): (vid, p) for vid, p in aufgaben}
        for f in zukunft:
            vid, p = zukunft[f]
            ergebnisse[(vid, p)] = f.result()
            melden(f"  fertig: {vid} {p}")
    d1 = daten_laden(db, ("D1",), soll)["kerzen"]["D1"]
    referenz = bl01(d1, spreads, fenster())
    log = protokoll.lesen(protokoll_pfad)
    haupt = {vid: e for (vid, p), e in ergebnisse.items() if p == "HAUPT"}
    dsr = dsr_familie(haupt, log)
    auswahl = tt.auswahl({vid: e["bewertung"] for vid, e in haupt.items()})
    bericht = _bericht_daten(ergebnisse, referenz, dsr, auswahl, sicht[-1], datum, liste)
    md, js = bericht_schreiben(bericht, bericht_ordner, datum)
    sha = hashlib.sha256(js.read_bytes()).hexdigest()
    for v in liste:
        if v.zaehlt:
            e = haupt[v.id]
            k = e["bewertung"]["kennzahlen"]
            kurz = {"bestanden": e["bewertung"]["bestanden"], "trades": k["n"], "quote": k["quote"], "e_r": k["e_r"],
                    "e_r_untergrenze": k["e_r_untergrenze"], "pf_eur": k["pf_eur"], "max_dd_prozent": k["max_dd_prozent"],
                    "trades_pro_monat": k["trades_pro_monat"], "technik": e["bewertung"]["kriterien"]["technik"]["ok"],
                    "bestanden_3_25": ergebnisse[(v.id, "GEGENPROBE_3_25")]["bewertung"]["bestanden"]}
        else:
            kurz = {"trades": referenz["trades"], "quote": referenz["quote"], "e_r": referenz["e_r"], "zaehlt": False}
        protokoll.versuch(v.familie, v.id, datum, pfad=protokoll_pfad, phase="ERGEBNIS", ergebnis=_json(kurz), bericht=js.name,
                          bericht_sha=sha, auswahl=auswahl, **gemeinsam)
    return {"bericht_md": str(md), "bericht_json": str(js), "auswahl": auswahl}


def _bericht_daten(ergebnisse: dict, referenz: dict, dsr: dict, auswahl: str | None, sicht: dict, datum: str, liste: Sequence) -> dict:
    varianten = []
    for v in liste:
        if not v.zaehlt:
            continue
        h, x15, g = (ergebnisse[(v.id, p)] for p in PROFILE)
        zus = tt.zusatz(tt.konfig(), teilperioden_werte=[D(1) if p else D(-1) for p in h["teilperioden"]["positiv"]],
                        gewinnfaktor_kosten=_pf_dez(x15["bewertung"]["kennzahlen"]["pf_eur"]),
                        dsr=(dsr.get(v.id) or {}).get("dsr"))
        varianten.append({"id": v.id, "parameter": v.parameter, "haupt": h, "kosten_x1_5": _kurz(x15), "gegenprobe_3_25": _kurz(g),
                          "zusatz": _json(zus), "dsr": dsr.get(v.id), "teilperioden_r": h["teilperioden"]["r_summe"]})
    return {"schema": "f04_entwicklung/1", "datum": datum, "lauf": "F-04", "prereg_sha": protokoll.PREREG_SHA,
            "einordnung": "Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.",
            "daten": {"abzuege": [{k: a.get(k) for k in ("symbol", "zeitrahmen", "anzahl", "erster", "letzter", "verworfen_holdout")}
                                  | {"sha256": a["sha256"][:16]}
                                  for a in sicht["body"]["daten"]["abzuege"]], "holdout": "nicht gezogen",
                      "spreadprofil": f"privat (SHA-256 {str(sicht['body'].get('spreadprofil_sha'))[:16]}…)"},
            "varianten": varianten, "referenz_s_bl_01": referenz, "auswahl": auswahl,
            "kostenprofile": {p: _ohne_swap(kostenprofil(p, startwerte())) for p in PROFILE}}


def _ohne_swap(profil: Kostenprofil) -> dict:
    """Beschreibung ohne die Swappunkte des Startprofils (privat; im Protokoll steht der SHA der Startwerte-Datei)."""
    return {k: v for k, v in profil.beschreibung().items() if k != "swap_punkte"} | {"swap_punkte": "privat (Startwerte-Datei)"}


def _pf_dez(x) -> Decimal | None:
    if x is None:
        return None
    if x == "unendlich":
        return D("Infinity")
    return D(str(x))


def _kurz(e: dict) -> dict:
    k = e["bewertung"]["kennzahlen"]
    return {"bestanden": e["bewertung"]["bestanden"], "trades": k["n"], "quote": k["quote"], "e_r": k["e_r"],
            "e_r_untergrenze": k["e_r_untergrenze"], "pf_eur": k["pf_eur"], "verlust_zu_gewinn_eur": k["verlust_zu_gewinn_eur"],
            "max_dd_prozent": k["max_dd_prozent"], "technik_ok": e["technik_ok"],
            "kriterien": {n: c["ok"] for n, c in e["bewertung"]["kriterien"].items()}}


# ---------------------------------------------------------------------------------------------------- Bericht (Markdown)
def _p(x, stellen: int = 1) -> str:
    return "–" if x is None else f"{100 * x:.{stellen}f} %".replace(".", ",")


def _z(x, stellen: int = 2) -> str:
    if x is None:
        return "–"
    if x == "unendlich":
        return "∞"
    return f"{x:.{stellen}f}".replace(".", ",")


def _ok(x) -> str:
    return {True: "ja", False: "nein", None: "n. b."}[x]


def bericht_schreiben(b: dict, ordner: Path, datum: str) -> tuple[Path, Path]:
    """Bericht als JSON und Markdown – nie überschreiben (fail-closed)."""
    ordner.mkdir(parents=True, exist_ok=True)
    js = ordner / f"{datum}_entwicklung.json"
    if js.exists() or (ordner / f"{datum}_entwicklung.md").exists():
        raise FileExistsError(f"{datum}_entwicklung existiert schon")
    js.write_text(json.dumps(b, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    md = ordner / f"{datum}_entwicklung.md"
    md.write_text(markdown(b), encoding="utf-8", newline="\n")
    return md, js


def markdown(b: dict) -> str:
    z: list[str] = []
    a = z.append
    vs = b["varianten"]
    bestanden = [v["id"] for v in vs if v["haupt"]["bewertung"]["bestanden"]]
    a(f"# Entwicklungsbericht F-04 ({b['datum']}) – Ziel/Stop-Strategien auf der Entwicklungsperiode")
    a("")
    a("Nur Prozent, R, Anzahlen und Trades je Monat. Vorregistrierung `docs/bot/prereg/F04_ENTWURF.md` "
      f"(SHA-256 `{b['prereg_sha'][:16]}…`), Versuchsprotokoll `forschung/versuchsprotokoll.jsonl`. Der Holdout (ab 01.07.2021) "
      "wurde nicht gezogen.")
    a("")
    a("## Ergebnis in einem Satz")
    a("")
    if bestanden:
        a(f"{len(bestanden)} von {len(vs)} gezählten Varianten erfüllen alle Entwicklungskriterien des 85-%-Tors (Hauptprofil, technisch "
          f"gültig); Holdout-Kandidat nach der Auswahlregel: **{b['auswahl']}**.")
    else:
        a(f"**Keine der {len(vs)} gezählten Varianten erfüllt alle Entwicklungskriterien des 85-%-Tors. Es gibt keinen Holdout-Kandidaten.** "
          "Das ist ein gültiges, vorab als wahrscheinlich benanntes Ergebnis (Prereg §1).")
    ungueltig = [v["id"] for v in vs if v["haupt"]["bewertung"]["kriterien"]["technik"]["ok"] is not True]
    a("")
    a("Technisch gültig (keine Sperre, kein Vorfall, Parität 100 %): " + ("alle Läufe." if not ungueltig else
      f"**nicht** bei {', '.join(ungueltig)} – diese gelten als nicht bewertbar = nicht bestanden."))
    a("")
    a("## Kriterien je Variante (Hauptprofil, Entwicklung außerhalb der Anpassung)")
    a("")
    a("| Variante | Trades | T/Monat | Quote | Wilson-UG | E[R] | E[R]-UG 95 % | GF | ØV/ØG | Zufall P95 | Max-DD | 50-%-Ereign. | "
      "Band/Budget | bestanden |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in vs:
        k = v["haupt"]["bewertung"]["kennzahlen"]
        kr = v["haupt"]["bewertung"]["kriterien"]
        a(f"| {v['id']} | {k['n']} | {_z(k['trades_pro_monat'], 1)} | {_p(k['quote'])} | "
          f"{_p(k['wilson_95'][0]) if k['wilson_95'] else '–'} | {_z(k['e_r'], 3)} | {_z(k['e_r_untergrenze'], 3)} | {_z(k['pf_eur'])} | "
          f"{_z(k['verlust_zu_gewinn_eur'])} | {_p(k['zufall']['p95'])} | {_z(k['max_dd_prozent'], 1)} % | "
          f"{kr['stop50']['wert']} | {_ok(kr['band_budget']['ok'])} | **{_ok(v['haupt']['bewertung']['bestanden'])}** |")
    a("")
    a(f"Erfüllt je Kriterium (Anzahl Varianten von {len(vs)}):")
    a("")
    namen = list(vs[0]["haupt"]["bewertung"]["kriterien"]) if vs else []
    a("| " + " | ".join(namen) + " |")
    a("|" + "---|" * len(namen))
    a("| " + " | ".join(str(sum(1 for v in vs if v["haupt"]["bewertung"]["kriterien"][n]["ok"] is True)) for n in namen) + " |")
    a("")
    a("Schwellen (config/tore.toml [tor_85]): ≥ 200 Trades (das Tor zählt Entwicklung + Holdout gemeinsam; hier die Entwicklung allein), "
      "Quote ≥ 85 %, E[R]-Untergrenze > 0, Gewinnfaktor ≥ 1,2, Ø Verlust ≤ 3 × Ø Gewinn, Quote > 95. Perzentil der Zufallsbasis, "
      "Max-Drawdown < 25 %, kein 50-%-Ereignis (Folge oder Schatten-Sperre), Band, Budget und Stop ≤ 3 × Ziel beim Einstieg eingehalten, "
      "Lauf technisch gültig. „n. b.“ = nicht bewertbar = nicht bestanden. Gewinnfaktor und Ø Verlust/Ø Gewinn in EUR (Ø Verlust nur "
      "über Ergebnisse < 0), E[R] je Trade = Ergebnis / geplanter Verlust bis SL zu den Kosten des Laufs.")
    a("")
    a("## Band-Wirkung und Quote Signal → Trade")
    a("")
    a("| Variante | Signale | Trades | Signal→Trade | Hebel min/Ø/max | Fill − e (Ticks Ø/max) | Ablehnungen (häufigste) |")
    a("|---|---|---|---|---|---|---|")
    for v in vs:
        s = v["haupt"]["bewertung"]["kennzahlen"]["signale"]
        h = v["haupt"]["bewertung"]["kennzahlen"]["hebel"]
        abl = sorted(s["abgelehnt"].items(), key=lambda kv: -kv[1])[:5]
        en = v["haupt"]["einstieg_nachteil_ticks"]
        a(f"| {v['id']} | {s['gesamt']} | {s['erledigt']} | {_p(s['quote_signal_trade'])} | {_z(h['min'])}/{_z(h['mittel'])}/{_z(h['max'])} | "
          f"{_z(en['mittel'], 1)}/{en['max'] if en['max'] is not None else '–'} | " + ", ".join(f"{g} {n}" for g, n in abl) + " |")
    a("")
    a("## Kosten-Gegenproben")
    a("")
    a("Hauptprofil = Kommission 0 (erster Demo-Trade). „Kosten × 1,5“ verschärft Spread und Swap-Belastungen des Hauptprofils; seine "
      "Kommission bleibt 0 (0 × 1,5). Die Kommission prüft die eigene Gegenprobe mit 3,25 je Lot und Seite (Startwert cost_truth).")
    a("")
    a("| Variante | Quote (Haupt) | Quote (Kosten × 1,5) | GF (Kosten × 1,5) | Quote (Kommission 3,25) | E[R] (Kommission 3,25) | "
      "GF (Kommission 3,25) | bestanden (3,25) |")
    a("|---|---|---|---|---|---|---|---|")
    for v in vs:
        k = v["haupt"]["bewertung"]["kennzahlen"]
        x, g = v["kosten_x1_5"], v["gegenprobe_3_25"]
        a(f"| {v['id']} | {_p(k['quote'])} | {_p(x['quote'])} | {_z(x['pf_eur'])} | {_p(g['quote'])} | {_z(g['e_r'], 3)} | {_z(g['pf_eur'])} | "
          f"{_ok(g['bestanden'])} |")
    a("")
    a("## Zusatzkriterien (nur berichtet, V2: ZUSATZKRITERIEN-OK = nein)")
    a("")
    a("Teilperioden: vier gleich lange Abschnitte der Testzeit; „positiv“ nach dem Nettoergebnis in EUR, in Klammern die R-Summen.")
    a("")
    a("| Variante | DSR (N, N_eff) | Teilperioden positiv (R-Summen) | GF bei Kosten × 1,5 > 1,0 |")
    a("|---|---|---|---|")
    for v in vs:
        d = v["dsr"] or {}
        zt = v["zusatz"]
        dsr_txt = f"{_z(d.get('dsr'), 3)} ({d.get('N', '–')}, {_z(d.get('N_eff'), 1)})" if "dsr" in d else (d.get("fehler") or "–")
        a(f"| {v['id']} | {dsr_txt} | {zt['teilperioden']['positiv']}/4 ({', '.join(_z(x, 1) for x in v['teilperioden_r'])}) | "
          f"{_ok(zt['gewinnfaktor_kosten']['ok'])} |")
    a("")
    r = b["referenz_s_bl_01"]
    a("## Referenz S-BL-01 (BL-TFD1, zählt nie für das Tor, kein Server-TP)")
    a("")
    a(f"Trades {r['trades']}, Trades je Monat {_z(r['trades_pro_monat'], 1)}, Quote {_p(r['quote'])}, E[R] {_z(r['e_r'], 3)}, "
      f"Gewinnfaktor in R {_z(r['pf_r'])}. Plausibilitätsanker: ein Trendfolger trifft selten und lebt von wenigen großen Gewinnen.")
    a("")
    a("## Technik, Parität, Schatten")
    a("")
    a("Signal-Parität = gleiche Signale / max(Takt, direkt); Trade-Parität über alle Trades ohne Zwangsausstieg (Band/K3). "
      "Schattenereignisse über den ganzen Lauf inkl. Anlaufjahre.")
    a("")
    a("| Variante | Profil | Technik gültig | Signal-Parität (gleich; Takt/direkt) | Trade-Parität (geprüft, Zwang) | Schattenereignisse "
      "| offen am Ende |")
    a("|---|---|---|---|---|---|---|")
    for v in vs:
        for name, e in (("Haupt", v["haupt"]),):
            pt, ps = e["paritaet"]["trades"], e["paritaet"]["signale"]
            a(f"| {v['id']} | {name} | {_ok(e['bewertung']['kriterien']['technik']['ok'])} | {_p(ps['quote'], 2)} ({ps['gleich']}; "
              f"{ps['takt']}/{ps['direkt']}) | {_p(pt['quote'], 2)} ({pt['geprueft']}, {pt['zwangsausstiege']}) | "
              f"{e['schatten_gesamt'] or '–'} | {e['offen_am_ende']} |")
    a("")
    a("## Daten und Kostenprofil")
    a("")
    verworfen = sum(int(x.get("verworfen_holdout") or 0) for x in b["daten"]["abzuege"])
    a(f"{len(b['daten']['abzuege'])} Abzüge (7 Symbole × H1/H4/D1), je Abzug Hash geprüft; {verworfen} Kerzen, die über den Holdout-Beginn "
      "hinausreichen, verworfen (nie verwendet). Spread je Kerze aus den Daten; das Spreadprofil der Datensicht ist privat "
      f"({b['daten']['spreadprofil']}).")
    a("Kommission: Hauptprofil 0 je Lot und Seite (erster Demo-Trade), Gegenprobe 3,25 (Startwert cost_truth). Swap: Swappunkte des "
      "Startprofils (Stand 2026, privat), Dreifachtag Mittwoch. Die Größe rechnet der Takt wie im Betrieb mit 3,25 je Lot und Seite "
      "(config/kit_demo.toml).")
    a("")
    a("## Grenzen dieser Auswertung")
    a("")
    for g in GRENZEN:
        a(f"- {g}")
    a("")
    a("Einordnung: " + b["einordnung"])
    a("")
    return "\n".join(z)


GRENZEN = (
    "Ausführung auf H1-Kerzen: innerhalb einer Kerze gilt SL vor TP (vorsichtig), Lücken füllen zum Eröffnungskurs; kein Schlupf darüber hinaus.",
    "Spread je Kerze aus dem MT5-Kerzenfeld; das Feld kann den kleinsten Spread der Stunde zeigen. Die Gegenprobe Kosten × 1,5 deckt das nur teilweise.",
    "Swapsätze von 2026 für 2010–2021 (damalige Zinsdifferenzen waren anders); Haltedauer höchstens 24 h, also wenige Nächte je Trade.",
    "Zeitbasis: Der Datenabzug (F-02) hat die Kerzen in Serverzeit gespeichert; der Backtest rechnet sie mit dem festen Versatz +3 h "
    "nach UTC um. Der Server folgt der New-Yorker Sommerzeit (Datenprüfung: Wochenöffnung immer Mo 00:00 Serverzeit); im Winter (UTC+2) "
    "liegt das Handelsfenster deshalb 1 h später (09–23 Uhr Berlin, freitags bis 21 Uhr), Servermitternacht und Rollover bleiben richtig.",
    "Das Demokonto berechnet keine Kommission; ein Echtgeldkonto mit Rohspread kostet mehr (siehe Gegenprobe 3,25).",
    "Der Band-Prüfpunkt 21:30 Berlin läuft im Stundentakt beim ersten Schritt danach (22:00).",
    "S-REV-02 (H4): Im Backtest trägt die H4-Kerze den Spread der H1-Kerze mit demselben Schluss, damit der erwartete Einstieg e gleich "
    "dem Fill ist (Spalte „Fill − e“ = 0). Im Betrieb sieht die Strategie das MT5-Spreadfeld der H4-Kerze; dort kann der Fill um die "
    "Spreaddifferenz von e abweichen.",
    "Zeitbarriere = 24 h Wanduhr (Prereg: „24 Kerzen (24 h)“): Über Wochenende und Feiertage sind das weniger Kerzen; eine Position "
    "vom Freitag schließt beim ersten Schritt nach der Pause.",
    "Eine am Datenende (30.06.2021) noch offene Position zählt nicht (Spalte „offen am Ende“, höchstens 1).",
    "S-BL-01 (nur Referenz) nimmt den halben Median-Spread der ganzen Entwicklungsperiode als festen Kostensatz.",
    "Holdout-Grenze in UTC: D1/H4-Kerzen, die vor dem 01.07.2021 00:00 UTC beginnen, aber danach enden, werden verworfen (Spalte im JSON).",
    "Walk-Forward ohne angepasste Parameter: Die Varianten sind fest vorregistriert; die ersten 3 Jahre zählen nicht (nur Anlauf).",
)


# ---------------------------------------------------------------------------------------------------- Kostenprofil (Datensicht)
def kostenprofil_eintragen(*, datum: str, db: Path | None = None, protokoll_pfad: Path = protokoll.PFAD, spread_pfad: Path = SPREADPROFIL,
                           vorpruefen: bool = True) -> dict:
    """Schritt 2 – erste Datensicht: Vorprüfung (Code = Vorregistrierung), alle Abzüge laden (Hash/Holdout), Spreadprofil aus den
    H1-Kerzen in die private Datei config/kostenprofil/f04_spreadprofil.json, DATA_VIEW mit Abzugs-Hashes und Profil-Hash."""
    log = protokoll.lesen(protokoll_pfad)
    if vorpruefen:
        protokoll.vorpruefung(pfad=protokoll_pfad)
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung fehlt (kit forschung vorab)")
    if any(e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Datensicht schon eingetragen – das Kostenprofil gilt einmal je Lauf")
    db = Path(db or db_pfad())
    d = daten_laden(db)
    spreads = spreadprofil(d["kerzen"]["H1"])
    Path(spread_pfad).parent.mkdir(parents=True, exist_ok=True)
    Path(spread_pfad).write_text(json.dumps({"schema": "spreadprofil/1", "lauf": "F-04", "einheit": "Points je H1-Kerze",
                                             "symbole": spreads}, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                 encoding="utf-8", newline="\n")
    sw = startwerte()
    eintrag = protokoll.datensicht(FAMILIE_DATEN, "KOSTENPROFIL", "DEVELOPMENT", datum,
                                   {"abzuege": d["abzuege"], "datenbank": db.name}, pfad=protokoll_pfad,
                                   spreadprofil_sha=protokoll.sha256_datei(spread_pfad),
                                   kostenprofile={p: _ohne_swap(kostenprofil(p, sw)) for p in PROFILE},
                                   startwerte_sha=protokoll.sha256_datei(STARTWERTE))
    return {"abzuege": len(d["abzuege"]), "verworfen_holdout": sum(a["verworfen_holdout"] for a in d["abzuege"]),
            "spreadprofil": "privat: config/kostenprofil/f04_spreadprofil.json", "seq": eintrag["seq"]}
