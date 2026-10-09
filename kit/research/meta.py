"""Forschungsrunde 2 (F-05): KI-Meta-Filter auf den Signalen der F-04-Basisvarianten (Vorregistrierung docs/bot/prereg/F05_ENTWURF.md).

Nur Standardbibliothek. Das Training (scikit-learn) liegt außerhalb von kit/ in forschung/meta_training.py und wird als Funktion
übergeben (`trainer`); Ablauf und Prüfungen bleiben hier, damit sie auch ohne scikit-learn getestet werden.

Ablauf (python -m forschung.runde2 …, Versuchsprotokoll forschung/versuchsprotokoll.jsonl, Lauf F-05):
  0. kit forschung vorab --lauf F-05 – Vorregistrierung der Familien F05-META und F05-DATEN (Code-Liste protokoll.CODE_F05).
  1. daten        – Datensicht F05-DATEN: Kerzen gebunden an die Abzugs-Hashes der F-04-Datensicht (Zeitbasis W1); je Basisvariante
                    alle Signale mit Merkmalen und Label (Dreifach-Barriere über kit.backtest.ausstieg.simulieren, Hauptprofil, 1 Lot)
                    → work/f05/<Basis>.jsonl (nie veröffentlicht), im Protokoll nur Hashes und Anzahlen.
  2. entwicklung  – je Variante TRIAL „Beginn“; Training je Walk-Forward-Fenster mit Purge, Embargo und innerer Validierung (Schwelle);
                    eingefrorene Modelle forschung/modelle/F05/<Variante>.json; je Variante drei Läufe des Takts (Hauptprofil,
                    Kosten × 1,5, Kommission 3,25) mit dem MetaFilter; Bewertung wie F-04 (alle Kriterien des 85-%-Tors inkl.
                    Technik, Zufallsbasis über die gefilterten Einstiege); DSR der Familie; Auswahl; Bericht
                    berichte/forschung/<datum>_runde2.md/.json (nur %, R, Anzahl, Trades/Monat); je Variante TRIAL „Ergebnis“.
Der Holdout wird nie gezogen oder gelesen (Datenleser bricht ab 01.07.2021 ab); das Holdout-Modell wird nur eingefroren.

Purge: jede Trainings- und Validierungsmenge enthält nur Signale, deren Label-Ausstieg spätestens am Ende der Menge liegt (Prereg:
„Label-Ausstieg nach dem Anpassungsende → fällt weg“). Embargo: die ersten 5 Handelstage (Mo–Fr ohne 1. Januar und 25. Dezember) jedes
Testfensters ohne Trades. Jedes Modell trägt seine Trainingsgrenzen; die Hülle verweigert ein Modell, dessen Trainings- oder
Validierungsdaten ins Testfenster reichen (fail-closed). Der Fensterschnitt des Datensatzes ist derselbe wie in der Signal-Parität
(kit.backtest.paritaet.signal_fenster); die Takt-Signale des Hauptprofils müssen genau den Datensatz-Entscheidungen entsprechen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt, simulieren
from kit.backtest.kosten import Kostenprofil
from kit.domain.types import Bar, Side
from kit.gates import ROOT, tore
from kit.gates import trade_test as tt
from kit.research import entwicklung, protokoll, stats, trials
from kit.risk import guards
from kit.strategy import meta_filter as mf
from kit.strategy import varianten as var

D = Decimal
UTC = dt.UTC
LAUF = "F-05"
FAMILIE = "F05-META"
FAMILIE_DATEN = "F05-DATEN"
GITTER = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)
MIN_VALIDIERUNG = 20
EMBARGO_HANDELSTAGE = 5
VALIDIERUNG_JAHRE = 1
HOLDOUT_START = "2021-07-01"
PROFILE = entwicklung.PROFILE
DATENSAETZE = ROOT / "work" / "f05"                          # gitignored: abgeleitete Kursdaten, nie veröffentlicht
MODELLE = ROOT / "forschung" / "modelle" / "F05"
BERICHTE = entwicklung.BERICHTE
MAX_MODELLDATEI = 1_800_000                                  # Bytes (Commit-Grenze 2 MB je Datei)
HYPERPARAMETER = {
    "LOGREG": {"modell": "Pipeline(StandardScaler, LogisticRegression)", "C": 1.0, "regularisierung": "L2 (l1_ratio 0)",
               "solver": "lbfgs", "max_iter": 1000, "standardisierung": "auf der jeweiligen Trainingsmenge"},
    "HGB": {"modell": "HistGradientBoostingClassifier", "max_depth": 3, "learning_rate": 0.05, "max_iter": 200, "min_samples_leaf": 50,
            "l2_regularization": 0.0, "early_stopping": False, "random_state": 0},
}


@dataclass(frozen=True)
class MetaVariante:
    id: str
    basis_id: str
    art: str          # REV01 / REV02 (Merkmalssatz)
    modell: str       # LOGREG / HGB


BASIS_REV01 = "S-REV-01-k2.0-z0.75-r3"
BASIS_REV02 = "S-REV-02-L40-z0.5"
VARIANTEN = (
    MetaVariante("F05-REV01-LOGREG", BASIS_REV01, "REV01", "LOGREG"),
    MetaVariante("F05-REV01-HGB", BASIS_REV01, "REV01", "HGB"),
    MetaVariante("F05-REV02-LOGREG", BASIS_REV02, "REV02", "LOGREG"),
    MetaVariante("F05-REV02-HGB", BASIS_REV02, "REV02", "HGB"),
)
BASEN = (BASIS_REV01, BASIS_REV02)
Trainer = Callable[[list[dict], MetaVariante, list[dict]], dict]


def variante(vid: str) -> MetaVariante:
    return next(v for v in VARIANTEN if v.id == vid)


def basis_strategie(basis_id: str):
    """Basisstrategie mit den unveränderten F-04-Parametern (kit/strategy/varianten.py)."""
    return var.strategie(next(v for v in var.varianten() if v.id == basis_id))


def art_der_basis(basis_id: str) -> str:
    return "REV02" if basis_id.startswith("S-REV-02-") else "REV01"


# ---------------------------------------------------------------------------------------------------- Kerzen wie im Takt
def takt_kerzen(h1: Mapping[str, Sequence[Bar]], tfk: Mapping[str, Sequence[Bar]] | None, tf: str, profil: Kostenprofil) -> dict[str, list[Bar]]:
    """Kerzen des Strategie-Zeitrahmens genau so, wie der Takt sie der Strategie gibt (BacktestTerminal): H1 mit dem Spread des
    Kostenprofils; H4 mit dem Spread der H1-Kerze mit demselben Schluss (sonst dem eigenen), jeweils mit dem Kostenprofil."""
    aus: dict[str, list[Bar]] = {}
    if tf == "H1":
        for s, kerzen in h1.items():
            aus[s] = [b if profil.spread_points(b.spread_points) == b.spread_points else replace(b, spread_points=profil.spread_points(b.spread_points))
                      for b in kerzen]
        return aus
    dauer = mf.TF_S[tf]
    for s, kerzen in (tfk or {}).items():
        h1_nach_beginn = {b.time: b for b in h1.get(s, ())}
        liste = []
        for b in kerzen:
            h = h1_nach_beginn.get(b.time + dauer - mf.TF_S["H1"])
            sp = profil.spread_points(h.spread_points if h is not None else b.spread_points)
            liste.append(b if sp == b.spread_points else replace(b, spread_points=sp))
        aus[s] = liste
    return aus


# ---------------------------------------------------------------------------------------------------- Datensatz
def datensatz(basis, art: str, kerzen_tf: Mapping[str, Sequence[Bar]], markt: Markt, konf=None) -> tuple[list[dict], dict]:
    """Alle Signale der Basis mit genau der Fensterregel der MetaFilter-Hülle im Takt (paritaet.signal_fenster mit rueckblick =
    max(Basis, FENSTER); Basis-Signal aus den letzten Basis-Kerzen); je Signal Merkmale und Label (Dreifach-Barriere, 1 Lot, Einstieg
    Ask/Bid des Schritts). Unabhängig von Konto, Band und Positionsbelegung (Prereg: alle Signale). Zusätzlich nur zur Auskunft:
    takt_moeglich = im Handelsfenster und Stop ≤ 3 × Ziel (zustandsunabhängige Ablehnungen des Takts).
    Rückgabe: Zeilen und Zählung (ohne Merkmale, offen am Datenende, nie handelbar)."""
    konf = konf or runner.bot_konfiguration()
    stop_ziel = D(str(tore()["limits"]["stop_zu_ziel_max"]))
    rb = max(int(basis.rueckblick), mf.FENSTER)
    spanne_l = getattr(basis, "L", None) if art == "REV02" else None
    zeilen: list[dict] = []
    zaehlung = Counter()
    for sym in basis.symbole:
        kerzen = list(kerzen_tf.get(sym, ()))
        for i, jetzt, fenster in paritaet.signal_fenster(basis.zeitrahmen, rb, kerzen, markt.schritte):
            b = kerzen[i]
            sig = basis.signal(sym, fenster[-int(basis.rueckblick):])
            if sig is None:
                continue
            zaehlung["basissignale"] += 1
            x = mf.merkmale(fenster, sig.side, art, spanne_l=spanne_l)
            if x is None:
                zaehlung["ohne_merkmale"] += 1
                continue
            q = markt.kurs(sym, jetzt)
            if q is None:
                zaehlung["ohne_kurs"] += 1
                continue
            preis = q[1] if sig.side is Side.BUY else q[0]
            a = simulieren(markt, sym, sig.side, preis, sig.sl, sig.tp, D(1), jetzt, basis.max_halte_s)
            offen = a.grund == "OFFEN"
            zaehlung["offen"] += int(offen)
            im_fenster = guards.im_fenster(float(jetzt), konf)
            stop_ok = abs(preis - sig.sl) <= stop_ziel * abs(sig.tp - preis)
            zaehlung["ausserhalb_fenster"] += int(not im_fenster)
            zaehlung["stop_zu_ziel"] += int(not stop_ok)
            zeilen.append({"symbol": sym, "t_kerze": b.time, "t_ent": jetzt, "side": str(sig.side), "sl": str(sig.sl), "tp": str(sig.tp),
                           "preis_auf": str(preis), "x": x, "label": None if offen else int(a.ergebnis > 0),
                           "t_exit": None if offen else a.t, "grund": a.grund, "ergebnis": str(a.ergebnis),
                           "takt_moeglich": bool(im_fenster and stop_ok)})
    zeilen.sort(key=lambda z: (z["t_ent"], z["symbol"]))
    zaehlung["zeilen"] = len(zeilen)
    return zeilen, dict(sorted(zaehlung.items()))


def datensatz_text(zeilen: Sequence[Mapping]) -> str:
    return "".join(json.dumps(z, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for z in zeilen)


def datensatz_lesen(pfad: Path, soll_sha: str) -> list[dict]:
    roh = Path(pfad).read_bytes()
    if hashlib.sha256(roh).hexdigest() != soll_sha:
        raise protokoll.ProtokollFehler(f"Datensatz {Path(pfad).name} passt nicht zum Hash der Datensicht")
    return [json.loads(z) for z in roh.decode("utf-8").splitlines() if z.strip()]


# ---------------------------------------------------------------------------------------------------- Plan, Purge, Embargo
def _tag(t: int) -> dt.date:
    return dt.datetime.fromtimestamp(t, UTC).date()


def _mitternacht(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def _minus_jahre(t: int, jahre: int) -> int:
    d = _tag(t)
    try:
        z = d.replace(year=d.year - jahre)
    except ValueError:                                           # 29.02. → 28.02.
        z = d.replace(year=d.year - jahre, day=28)
    return _mitternacht(z)


FREIE_TAGE = ((1, 1), (12, 25))                               # Neujahr, 1. Weihnachtstag: Devisenmarkt ohne Handel


def handelstag(d: dt.date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in FREIE_TAGE


def embargo_ende(t: int, tage: int = EMBARGO_HANDELSTAGE) -> int:
    """Beginn (00:00 UTC) des (tage+1)-ten Handelstags (Mo–Fr ohne 1. Januar und 25. Dezember) ab dem Tag von t: die ersten `tage`
    Handelstage ab dem Anpassungsende sind gesperrt."""
    d = _tag(t)
    gezaehlt = 0
    while True:
        if handelstag(d):
            if gezaehlt == tage:
                return _mitternacht(d)
            gezaehlt += 1
        d += dt.timedelta(days=1)


def plan(*, test_fenster: Sequence[tuple[int, int]] | None = None, holdout_von: int | None = None, anpassung_jahre: int | None = None,
         validierung_jahre: int = VALIDIERUNG_JAHRE) -> list[dict]:
    """Walk-Forward-Plan wie F-04 (Testfenster aus config/trade_test.toml) plus das eingefrorene Holdout-Modell (nur gespeichert):
    je Fenster Anpassung [fit_von, test_von), innere Validierung [val_von, test_von), Embargo bis embargo_bis."""
    wf = tt.konfig()["walk_forward"]
    jahre = int(wf["anpassung_jahre"]) if anpassung_jahre is None else anpassung_jahre
    fenster = list(entwicklung.fenster() if test_fenster is None else test_fenster)
    if holdout_von is None:
        holdout_von = _mitternacht(dt.date.fromisoformat(HOLDOUT_START))
    aus = []
    for von, bis in [*fenster, (holdout_von, None)]:
        aus.append({"test_von": von, "test_bis": bis, "embargo_bis": embargo_ende(von), "fit_von": _minus_jahre(von, jahre),
                    "val_von": _minus_jahre(von, validierung_jahre), "holdout": bis is None})
    return aus


def menge(zeilen: Sequence[Mapping], von: int, bis: int) -> list[Mapping]:
    """Trainier- bzw. Validierungsmenge: Entscheidung in [von, bis), Label vorhanden und Label-Ausstieg ≤ bis (Purge)."""
    return [z for z in zeilen if von <= z["t_ent"] < bis and z["label"] is not None and z["t_exit"] is not None and z["t_exit"] <= bis]


def gepurgt(zeilen: Sequence[Mapping], von: int, bis: int) -> int:
    """Anzahl Signale mit Entscheidung in [von, bis), die der Purge entfernt (Label-Ausstieg nach bis oder offen)."""
    return sum(1 for z in zeilen if von <= z["t_ent"] < bis and (z["label"] is None or z["t_exit"] is None or z["t_exit"] > bis))


def schwelle_waehlen(p: Sequence[float], y: Sequence[int], gitter: Sequence[float] = GITTER, min_n: int = MIN_VALIDIERUNG) -> dict:
    """Prereg: kleinste Schwelle aus dem Gitter mit der höchsten Wilson-95-%-Untergrenze der Validierungs-Trefferquote (Signale mit
    p > Schwelle), mindestens min_n Signale über der Schwelle. Keine solche Schwelle → schwelle None (Testjahr ohne Trades)."""
    if len(p) != len(y):
        raise ValueError("p und y verschieden lang")
    kandidaten = []
    for s in gitter:
        sel = [yy for pp, yy in zip(p, y, strict=True) if pp > s]
        n, k = len(sel), sum(sel)
        unten = stats.wilson(k, n)[0] if n >= min_n else None
        kandidaten.append({"schwelle": s, "n": n, "treffer": k, "quote": k / n if n else None, "wilson_unten": unten})
    zulaessig = [c for c in kandidaten if c["wilson_unten"] is not None]
    if not zulaessig:
        return {"schwelle": None, "kandidaten": kandidaten}
    beste = max(zulaessig, key=lambda c: (c["wilson_unten"], -c["schwelle"]))
    return {"schwelle": beste["schwelle"], "n": beste["n"], "treffer": beste["treffer"], "quote": beste["quote"],
            "wilson_unten": beste["wilson_unten"], "kandidaten": kandidaten}


PLAN_SCHLUESSEL = ("test_von", "test_bis", "embargo_bis", "fit_von", "val_von")


def purge_pruefen(modell_datei: Mapping, zeilen: Sequence[Mapping], plan_werte: Sequence[Mapping] | None = None) -> list[str]:
    """Gegenprobe zu dem, was der Trainer angibt (fail-closed, fehlende Angaben sind Befunde): je Fenster die gemeldeten Grenzen der
    inneren, der Validierungs- und der finalen Menge (spätester Label-Ausstieg, späteste Entscheidung) gegen Testbeginn bzw.
    Validierungsbeginn, die gemeldeten Anzahlen gegen die Purge-Regel nachgerechnet, Embargo = 5 Handelstage und – mit plan_werte –
    die Fenster genau wie registriert."""
    befunde = []
    fenster = [*modell_datei["fenster"], modell_datei["holdout"]]
    if plan_werte is not None:
        soll = [tuple(p[k] for k in PLAN_SCHLUESSEL) for p in plan_werte]
        ist = [tuple(f.get(k) for k in PLAN_SCHLUESSEL) for f in fenster]
        if ist != soll:
            befunde.append("plan:Fenster der Modelldatei weichen vom registrierten Plan ab")
    for f in fenster:
        tv = f["test_von"]
        if f.get("embargo_bis") != embargo_ende(tv):
            befunde.append(f"embargo:{tv}")
        mengen = {"innen": (f["fit_von"], f["val_von"]), "validierung": (f["val_von"], tv), "final": (f["fit_von"], tv)}
        for name, (von, bis) in mengen.items():
            g = (f.get("grenzen") or {}).get(name)
            if not isinstance(g, Mapping):
                befunde.append(f"grenzen_fehlen:{name}:{tv}")
                continue
            if g.get("n") != len(menge(zeilen, von, bis)):
                befunde.append(f"anzahl:{name}:{tv}")
            if g.get("n"):
                if not (g.get("max_t_exit") is not None and g["max_t_exit"] <= bis and g.get("max_t_ent") is not None
                        and von <= g.get("min_t_ent", von) and g["max_t_ent"] < bis):
                    befunde.append(f"grenze:{name}:{tv}")
        m = f.get("modell")
        if m is not None:
            tr = m.get("training") or {}
            if not (tr.get("max_t_exit") is not None and tr["max_t_exit"] <= tv and tr.get("val_max_t_exit") is not None
                    and tr["val_max_t_exit"] <= tv and tr.get("fit_bis") == tv):
                befunde.append(f"modellgrenze:{tv}")
    return befunde


# ---------------------------------------------------------------------------------------------------- Filterwirkung (direkt)
def datensatz_paritaet(zeilen: Sequence[Mapping], meta: mf.MetaFilter, takt_signale: Sequence[Sequence]) -> dict:
    """Takt-Signale des Hauptprofils (Symbol, Kerze, Richtung) gegen die Entscheidungen der Hülle aus den Datensatz-Merkmalen: gleich
    nur, wenn Training und Laufzeit dieselben Merkmale sehen (Fensterschnitt, Spread, Zeit). Soll 100 %."""
    direkt = []
    for z in zeilen:
        f = meta.fenster_fuer(z["t_ent"])
        if f is None or z["t_ent"] < f.embargo_bis or f.schwelle is None or f.modell is None:
            continue
        if mf.wahrscheinlichkeit(f.modell, z["x"]) > f.schwelle:
            direkt.append((z["symbol"], int(z["t_kerze"]), z["side"]))
    return paritaet.vergleich([(s, int(k), str(r)) for s, k, r in takt_signale], direkt)


def filterwirkung(zeilen: Sequence[Mapping], meta: mf.MetaFilter, fenster: Sequence[tuple[int, int]]) -> dict:
    """Entscheidung der Hülle je Basissignal im Testzeitraum (aus den Datensatz-Merkmalen, ohne Takt): Anzahl je Entscheidung und
    Gewinnquote (Label) aller Basissignale bzw. der durchgelassenen – Signalqualität unabhängig von Konto und Band."""
    zaehl: Counter[str] = Counter()
    alle: list[int] = []
    durch: list[int] = []
    nie = 0
    for z in zeilen:
        if not any(a <= z["t_ent"] < b for a, b in fenster):
            continue
        f = meta.fenster_fuer(z["t_ent"])
        if f is None:
            e = "KEIN_FENSTER"
        elif z["t_ent"] < f.embargo_bis:
            e = "EMBARGO"
        elif f.schwelle is None or f.modell is None:
            e = "KEINE_SCHWELLE"
        else:
            e = "HANDELN" if mf.wahrscheinlichkeit(f.modell, z["x"]) > f.schwelle else "UNTER_SCHWELLE"
        zaehl[e] += 1
        nie += int(e == "HANDELN" and not z.get("takt_moeglich", True))
        if z["label"] is not None:
            alle.append(z["label"])
            if e == "HANDELN":
                durch.append(z["label"])
    return {"entscheidungen": dict(sorted(zaehl.items())), "basissignale": sum(zaehl.values()),
            "gewinnquote_basis": sum(alle) / len(alle) if alle else None, "gewinnquote_durchgelassen": sum(durch) / len(durch) if durch else None,
            "durchgelassen_mit_label": len(durch), "durchgelassen_nie_handelbar": nie}


# ---------------------------------------------------------------------------------------------------- Takt-Lauf (Arbeitsprozess)
def aufgabe(vid: str, profil_name: str, db: str, sw: dict, soll: dict[str, str], modell_pfad: str) -> dict:
    """Ein Lauf des Takts mit dem MetaFilter über die ganze Entwicklungsperiode und seine Bewertung (nur Kennzahlen)."""
    d = entwicklung._daten(db, soll)
    h1, h4 = d["kerzen"]["H1"], d["kerzen"]["H4"]
    v = variante(vid)
    strat = mf.laden(modell_pfad, basis_strategie(v.basis_id))
    profil = entwicklung.kostenprofil(profil_name, sw)
    konf = tt.konfig()
    k = konf["konto"]
    einst = runner.Einstellungen(profil, start_equity=D(k["start_equity"]), hebel=int(k["hebel"]), versatz_s=int(k["versatz_s"]))
    tf_kerzen = h4 if strat.zeitrahmen == "H4" else None
    with tempfile.TemporaryDirectory(prefix="kit_f05_") as ablage:
        erg = runner.laufen(strat, h1, Path(ablage), einst, tf_kerzen=tf_kerzen)
    kerzen_takt = takt_kerzen(h1, h4, strat.zeitrahmen, profil)
    e = entwicklung.bewerten_lauf(erg, strat, profil, h1, kerzen_takt, vid, profil_name, konf, spread_abgebildet=True)
    e["takt_signale"] = [[s["symbol"], int(s["kerze"]), s["side"]] for s in erg.signale]
    return e


# ---------------------------------------------------------------------------------------------------- Schritt 1: Datensicht
def _f04_sicht(log: Sequence[Mapping]) -> Mapping:
    sicht = [e for e in log if e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == entwicklung.FAMILIE_DATEN]
    if not sicht:
        raise protokoll.ProtokollFehler("F-04-Datensicht fehlt – Runde 2 nutzt genau deren Abzüge")
    return sicht[-1]


def _soll(sicht: Mapping, zeitrahmen: Sequence[str] = ("H1", "H4")) -> dict[str, str]:
    return {f"{a['symbol']}/{a['zeitrahmen']}": a["sha256"] for a in sicht["body"]["daten"]["abzuege"] if a["zeitrahmen"] in zeitrahmen}


def daten_eintragen(*, datum: str, db: Path | None = None, protokoll_pfad: Path = protokoll.PFAD, ordner: Path = DATENSAETZE,
                    vorpruefen: bool = True, kerzen: Mapping | None = None) -> dict:
    """Schritt 1 – Datensicht der Runde 2: Vorprüfung (Code = Vorregistrierung F-05), Kerzen der F-04-Abzüge (Hash-gebunden), Datensätze
    je Basis nach `ordner`, DATA_VIEW F05-DATEN mit Abzugs- und Datensatz-Hashes (keine Kurse, keine Merkmale)."""
    log = protokoll.lesen(protokoll_pfad)
    if vorpruefen:
        protokoll.vorpruefung(pfad=protokoll_pfad, lauf=LAUF)
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung F-05 fehlt (kit forschung vorab --lauf F-05)")
    if any(e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Datensicht F-05 schon eingetragen – die Datensätze gelten einmal je Lauf")
    vorhanden = [b for b in BASEN if (Path(ordner) / f"{b}.jsonl").exists()]
    if vorhanden:
        raise protokoll.ProtokollFehler(f"Datensätze ohne Datensicht vorhanden ({', '.join(vorhanden)}) – Abbruch eines früheren Laufs "
                                        "klären und im HANDOFF vermerken, dann die Dateien entfernen")
    sicht04 = _f04_sicht(log)
    soll = _soll(sicht04)
    if kerzen is None:
        kerzen = entwicklung.daten_laden(Path(db or entwicklung.db_pfad()), ("H1", "H4"), soll)["kerzen"]
    h1, h4 = kerzen["H1"], kerzen["H4"]
    profil = entwicklung.kostenprofil("HAUPT", entwicklung.startwerte())
    markt = Markt(h1, profil, versatz_s=entwicklung.serverversatz_daten())
    datensaetze, texte = {}, {}
    for basis_id in BASEN:                            # erst alles im Speicher rechnen, dann protokollieren, dann schreiben
        basis = basis_strategie(basis_id)
        zeilen, zaehlung = datensatz(basis, art_der_basis(basis_id), takt_kerzen(h1, h4, basis.zeitrahmen, profil), markt)
        texte[basis_id] = datensatz_text(zeilen)
        datensaetze[basis_id] = {"datei": f"{basis_id}.jsonl", "sha256": hashlib.sha256(texte[basis_id].encode("utf-8")).hexdigest(),
                                 "zaehlung": zaehlung, "merkmale": list(mf.merkmal_namen(art_der_basis(basis_id)))}
    abzuege = [a for a in sicht04["body"]["daten"]["abzuege"] if a["zeitrahmen"] in ("H1", "H4")]
    eintrag = protokoll.datensicht(FAMILIE_DATEN, "DATENSATZ", "DEVELOPMENT", datum, {"abzuege": abzuege, "f04_datensicht_seq": sicht04["seq"]},
                                   pfad=protokoll_pfad, datensaetze=datensaetze, kostenprofil="HAUPT", label_lots="1",
                                   startwerte_sha=protokoll.sha256_datei(entwicklung.STARTWERTE),
                                   zeitbasis="Serverzeit − versatz_s (F-04 W1)", versatz_s=entwicklung.serverversatz_daten())
    Path(ordner).mkdir(parents=True, exist_ok=True)
    for basis_id, text in texte.items():
        (Path(ordner) / f"{basis_id}.jsonl").write_text(text, encoding="utf-8", newline="\n")
    return {"seq": eintrag["seq"], "datensaetze": {b: {"zeilen": d["zaehlung"]["zeilen"], "sha256": d["sha256"][:16]} for b, d in datensaetze.items()}}


# ---------------------------------------------------------------------------------------------------- Schritt 2: Entwicklung
def _sicht_f05(log: Sequence[Mapping]) -> Mapping:
    sicht = [e for e in log if e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN]
    if not sicht:
        raise protokoll.ProtokollFehler("Datensicht F-05 fehlt (python -m forschung.runde2 daten)")
    return sicht[-1]


def modell_schreiben(daten: Mapping, ordner: Path) -> Path:
    """Eingefrorenes Modell als JSON (kompakt, floats exakt) – nie überschreiben; Größe begrenzt (Commit-Grenze)."""
    Path(ordner).mkdir(parents=True, exist_ok=True)
    pfad = Path(ordner) / f"{daten['variante']}.json"
    if pfad.exists():
        raise FileExistsError(f"Modelldatei {pfad.name} existiert schon – nie überschreiben")
    text = json.dumps(daten, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if len(text.encode("utf-8")) > MAX_MODELLDATEI:
        raise ValueError(f"Modelldatei {pfad.name} zu groß ({len(text)} Bytes)")
    pfad.write_text(text, encoding="utf-8", newline="\n")
    return pfad


def _json(x: object) -> object:
    return entwicklung._json(x)


def ausfuehren(*, datum: str, trainer: Trainer, prozesse: int | None = None, db: Path | None = None,
               sw_pfad: Path = entwicklung.STARTWERTE, protokoll_pfad: Path = protokoll.PFAD, datensatz_ordner: Path = DATENSAETZE,
               modell_ordner: Path = MODELLE, bericht_ordner: Path = BERICHTE, melden=print, vorpruefen: bool = True,
               nur: Sequence[str] | None = None, plan_werte: Sequence[dict] | None = None,
               test_fenster: Sequence[tuple[int, int]] | None = None) -> dict:
    """Schritt 2 – genau einmal je Familie. Fail-closed vorher: Vorprüfung (Code und mechanik_hash = Vorregistrierung F-05,
    Arbeitsbaum committet), Datensicht F-05 vorhanden, Datensätze = Hashes der Datensicht, noch kein ERGEBNIS der Familie, kein
    Bericht und keine Modelldatei dieses Laufs. plan_werte/test_fenster/nur/vorpruefen=False nur für Tests auf synthetischen Daten."""
    log = protokoll.lesen(protokoll_pfad)
    if vorpruefen:
        stand = protokoll.vorpruefung(pfad=protokoll_pfad, lauf=LAUF)
    else:
        stand = {"commit": None, "mechanik_hash": entwicklung.mechanik_hash(), "code": {}, "prereg_sha": protokoll.PREREG_F05_SHA}
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == FAMILIE for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung F-05 fehlt (kit forschung vorab --lauf F-05)")
    sicht = _sicht_f05(log)
    if any(e["body"].get("kind") == "TRIAL" and e["body"].get("phase") == "ERGEBNIS" and e["body"].get("family") == FAMILIE for e in log):
        raise protokoll.ProtokollFehler("Die Familie F05-META ist schon ausgewertet – eine Neuauswertung braucht eine neue Vorregistrierung")
    for endung in ("json", "md"):
        if (Path(bericht_ordner) / f"{datum}_runde2.{endung}").exists():
            raise protokoll.ProtokollFehler(f"Bericht {datum}_runde2 existiert schon – nie überschreiben")
    liste = [v for v in VARIANTEN if nur is None or v.id in nur]
    for v in liste:
        if (Path(modell_ordner) / f"{v.id}.json").exists():
            raise protokoll.ProtokollFehler(f"Modelldatei {v.id}.json existiert schon – nie überschreiben")
    ds = sicht["body"]["datensaetze"]
    zeilen = {b: datensatz_lesen(Path(datensatz_ordner) / ds[b]["datei"], ds[b]["sha256"]) for b in BASEN if b in {v.basis_id for v in liste}}
    soll = _soll(sicht)                               # genau die Abzüge, die die Datensicht F-05 protokolliert hat
    db = Path(db or entwicklung.db_pfad())
    sw = entwicklung.startwerte(sw_pfad)
    plaene = list(plan(test_fenster=test_fenster) if plan_werte is None else plan_werte)
    test_fenster = [(f["test_von"], f["test_bis"]) for f in plaene if not f["holdout"]]
    gemeinsam = {"commit": stand["commit"], "prereg_sha": stand["prereg_sha"], "mechanik_hash": stand["mechanik_hash"],
                 "code": stand["code"], "startwerte_sha": protokoll.sha256_datei(sw_pfad), "datensicht_seq": sicht["seq"]}
    for v in liste:
        protokoll.versuch(FAMILIE, v.id, datum, pfad=protokoll_pfad, phase="BEGINN", basis=v.basis_id, modell=v.modell,
                          hyperparameter=HYPERPARAMETER[v.modell], merkmale=list(mf.merkmal_namen(v.art)), merkmal_fenster=mf.FENSTER,
                          gitter=list(GITTER), min_validierung=MIN_VALIDIERUNG, embargo_handelstage=EMBARGO_HANDELSTAGE,
                          purge="Label-Ausstieg ≤ Ende der Trainings-/Validierungsmenge", schwelle="p > Schwelle",
                          datensatz_sha=ds[v.basis_id]["sha256"], plan=[{k: f[k] for k in ("test_von", "test_bis", "embargo_bis", "fit_von",
                                                                                           "val_von")} for f in plaene],
                          kostenprofile=list(PROFILE), **gemeinsam)
    modelle: dict[str, Path] = {}
    modell_info: dict[str, dict] = {}
    trainiert: dict[str, dict] = {}
    for v in liste:                                  # erst alle Modelle anpassen und prüfen, dann schreiben (kein halber Stand)
        melden(f"Training {v.id} …")
        daten = trainer(zeilen[v.basis_id], v, plaene)
        if daten.get("variante") != v.id or daten.get("datensatz_sha") != ds[v.basis_id]["sha256"]:
            raise protokoll.ProtokollFehler(f"Modell {v.id}: Variante oder Datensatz passt nicht")
        befunde = purge_pruefen(daten, zeilen[v.basis_id], plaene)
        if befunde:
            raise protokoll.ProtokollFehler(f"Purge/Embargo/Plan verletzt ({v.id}): {befunde[:3]}")
        if not float(daten["paritaet_max"]) <= 1e-9:                                  # NaN fällt durch → Abbruch
            raise protokoll.ProtokollFehler(f"Modell {v.id}: Laufzeit-Parität {daten['paritaet_max']} > 1e-9")
        mf.MetaFilter(basis_strategie(v.basis_id), mf.fenster_aus_json(daten), art=daten["art"], name=v.id)   # Modellbindung
        mf.MetaFilter(basis_strategie(v.basis_id), mf.fenster_aus_json({"fenster": [daten["holdout"]]}), art=daten["art"], name=v.id)
        trainiert[v.id] = daten
    for v in liste:
        daten = trainiert[v.id]
        modelle[v.id] = modell_schreiben(daten, modell_ordner)
        meta = mf.laden(modelle[v.id], basis_strategie(v.basis_id))
        modell_info[v.id] = {"sha256": mf.datei_sha(modelle[v.id]), "paritaet_max": daten["paritaet_max"],
                             "fenster": [{k: f.get(k) for k in ("test_von", "test_bis", "schwelle", "n_innen", "n_validierung", "n_final",
                                                                "gepurgt_innen", "gepurgt_validierung", "gepurgt_final", "validierung")}
                                         for f in daten["fenster"]],
                             "holdout": {k: daten["holdout"].get(k) for k in ("schwelle", "n_innen", "n_validierung", "n_final")},
                             "filter": filterwirkung(zeilen[v.basis_id], meta, test_fenster)}
    aufgaben = [(v.id, p) for v in liste for p in PROFILE]
    n_proz = max(1, min(prozesse or max(1, (os.cpu_count() or 2) - 4), len(aufgaben)))
    melden(f"{len(aufgaben)} Läufe in {n_proz} Prozessen …")
    ergebnisse: dict[tuple[str, str], dict] = {}
    with ProcessPoolExecutor(max_workers=n_proz) as pool:
        zukunft = {pool.submit(aufgabe, vid, p, str(db), sw, soll, str(modelle[vid])): (vid, p) for vid, p in aufgaben}
        for f in zukunft:
            vid, p = zukunft[f]
            ergebnisse[(vid, p)] = f.result()
            melden(f"  fertig: {vid} {p}")
    for v in liste:
        meta_v = mf.laden(modelle[v.id], basis_strategie(v.basis_id))
        for p in PROFILE:
            e = ergebnisse[(v.id, p)]
            signale = e.pop("takt_signale")
            if p == "KOSTEN_X1_5":
                continue                                    # dort sieht das Merkmal Spread/ATR den verschärften Spread
            dp = datensatz_paritaet(zeilen[v.basis_id], meta_v, signale)
            if p == "HAUPT":
                modell_info[v.id]["datensatz_paritaet"] = {k: dp[k] for k in ("takt", "direkt", "gleich", "quote")}
            tk = e["bewertung"]["kriterien"]["technik"]
            tk["wert"]["datensatz_paritaet"] = dp["quote"]
            if dp["quote"] != 1.0:
                tk["ok"] = None
                e["bewertung"]["bestanden"] = False
    log = protokoll.lesen(protokoll_pfad)
    haupt = {vid: e for (vid, p), e in ergebnisse.items() if p == "HAUPT"}
    dsr = dsr_familie(haupt, log, [v.id for v in liste])
    auswahl = tt.auswahl({v.id: haupt[v.id]["bewertung"] for v in liste})
    bericht = bericht_daten(ergebnisse, modell_info, dsr, auswahl, sicht, datum, liste, test_fenster)
    md, js = bericht_schreiben(bericht, Path(bericht_ordner), datum)
    sha = hashlib.sha256(js.read_bytes()).hexdigest()
    for v in liste:
        e = haupt[v.id]
        k = e["bewertung"]["kennzahlen"]
        kurz = {"bestanden": e["bewertung"]["bestanden"], "trades": k["n"], "quote": k["quote"], "e_r": k["e_r"],
                "e_r_untergrenze": k["e_r_untergrenze"], "pf_eur": k["pf_eur"], "max_dd_prozent": k["max_dd_prozent"],
                "trades_pro_monat": k["trades_pro_monat"], "technik": e["bewertung"]["kriterien"]["technik"]["ok"],
                "bestanden_3_25": ergebnisse[(v.id, "GEGENPROBE_3_25")]["bewertung"]["bestanden"]}
        protokoll.versuch(FAMILIE, v.id, datum, pfad=protokoll_pfad, phase="ERGEBNIS", ergebnis=_json(kurz), bericht=js.name, bericht_sha=sha,
                          auswahl=auswahl, modell_datei=modelle[v.id].name, modell_sha=modell_info[v.id]["sha256"], **gemeinsam)
    return {"bericht_md": str(md), "bericht_json": str(js), "auswahl": auswahl, "modelle": {k: str(p) for k, p in modelle.items()}}


def dsr_familie(haupt: Mapping[str, dict], log: list[dict], ids: Sequence[str]) -> dict[str, dict | None]:
    """DSR je Variante mit N und N_eff der Familie F05-META aus dem Protokoll (eine Versuchszahl, stats.dsr)."""
    reihen = [haupt[i]["monatsrenditen"] for i in ids]
    n = len(reihen[0]) if reihen else 0
    if n < 3 or any(len(r) != n for r in reihen):
        return {i: None for i in ids}
    corr = [[entwicklung._korrelation(a, b) for b in reihen] for a in reihen]
    try:
        anzahl = trials.dsr_trials(log, corr, family=FAMILIE)
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


# ---------------------------------------------------------------------------------------------------- Bericht
def _datum_nach_monaten(datum: str, monate: float) -> str:
    return (dt.date.fromisoformat(datum) + dt.timedelta(days=round(monate * 365.25 / 12))).isoformat()


def bericht_daten(ergebnisse: Mapping, modell_info: Mapping, dsr: Mapping, auswahl: str | None, sicht: Mapping, datum: str,
                  liste: Sequence[MetaVariante], test_fenster: Sequence[tuple[int, int]]) -> dict:
    varianten = []
    for v in liste:
        h, x15, g = (ergebnisse[(v.id, p)] for p in PROFILE)
        zus = tt.zusatz(tt.konfig(), teilperioden_werte=[D(1) if p else D(-1) for p in h["teilperioden"]["positiv"]],
                        gewinnfaktor_kosten=entwicklung._pf_dez(x15["bewertung"]["kennzahlen"]["pf_eur"]), dsr=(dsr.get(v.id) or {}).get("dsr"))
        tr = modell_info[v.id]
        handelbar_s = sum(max(0, f["test_bis"] - embargo_ende(f["test_von"])) for f in tr["fenster"] if f["schwelle"] is not None)
        n = h["bewertung"]["kennzahlen"]["n"]
        ohne = sum(1 for f in tr["fenster"] if f["schwelle"] is None)
        varianten.append({"id": v.id, "basis": v.basis_id, "modell": v.modell, "haupt": h, "kosten_x1_5": entwicklung._kurz(x15),
                          "gegenprobe_3_25": entwicklung._kurz(g), "zusatz": _json(zus), "dsr": dsr.get(v.id),
                          "teilperioden_r": h["teilperioden"]["r_summe"], "training": tr,
                          "handelbare_monate": handelbar_s / entwicklung.MONAT_S,
                          "trades_pro_handelbarem_monat": (n / (handelbar_s / entwicklung.MONAT_S)) if handelbar_s > 0 else None,
                          "fenster_ohne_schwelle": ohne,
                          "nicht_bewertbar": bool(n < int(tore()["tor_85"]["min_trades_oos"]) and ohne > 0)})
    kandidat = None
    if auswahl is not None:
        k = next(x for x in varianten if x["id"] == auswahl)["haupt"]["bewertung"]["kennzahlen"]
        tpm = k["trades_pro_monat"] or 0.0
        kandidat = {"variante": auswahl, "trades_pro_monat": tpm,
                    "trades_pro_handelbarem_monat": next(x for x in varianten if x["id"] == auswahl)["trades_pro_handelbarem_monat"],
                    "datum_100_trades_handelbar": (_datum_nach_monaten(datum, 100 / x) if (x := next(
                        v for v in varianten if v["id"] == auswahl)["trades_pro_handelbarem_monat"]) else None),
                    "monate_fuer_100": (100 / tpm) if tpm > 0 else None,
                    "datum_100_trades_ab_heute": _datum_nach_monaten(datum, 100 / tpm) if tpm > 0 else None}
    return {"schema": "f05_runde2/1", "datum": datum, "lauf": LAUF, "prereg_sha": protokoll.PREREG_F05_SHA,
            "einordnung": "Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.",
            "daten": {"f04_datensicht_seq": sicht["body"]["daten"]["f04_datensicht_seq"], "datensicht_seq": sicht["seq"],
                      "datensaetze": {b: {"sha256": d["sha256"][:16], "zaehlung": d["zaehlung"]} for b, d in sicht["body"]["datensaetze"].items()},
                      "holdout": "nicht gezogen"},
            "verfahren": {"gitter": list(GITTER), "min_validierung": MIN_VALIDIERUNG, "embargo_handelstage": EMBARGO_HANDELSTAGE,
                          "merkmal_fenster": mf.FENSTER, "hyperparameter": HYPERPARAMETER,
                          "testfenster": [[a, b] for a, b in test_fenster]},
            "varianten": varianten, "auswahl": auswahl, "kandidat": kandidat,
            "kostenprofile": {p: entwicklung._ohne_swap(entwicklung.kostenprofil(p, entwicklung.startwerte())) for p in PROFILE}}


def bericht_schreiben(b: Mapping, ordner: Path, datum: str) -> tuple[Path, Path]:
    """Bericht als JSON und Markdown – nie überschreiben (fail-closed)."""
    ordner.mkdir(parents=True, exist_ok=True)
    js, md = ordner / f"{datum}_runde2.json", ordner / f"{datum}_runde2.md"
    if js.exists() or md.exists():
        raise FileExistsError(f"{datum}_runde2 existiert schon")
    js.write_text(json.dumps(b, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    md.write_text(markdown(b), encoding="utf-8", newline="\n")
    return md, js


def _jahr(t: int) -> str:
    d = dt.datetime.fromtimestamp(t, UTC)
    return f"{d.year}" if d.month == 1 else f"{d.year}-{d.month:02d}"


def markdown(b: Mapping) -> str:
    p, z, ok = entwicklung._p, entwicklung._z, entwicklung._ok
    zeilen: list[str] = []
    a = zeilen.append
    vs = b["varianten"]
    bestanden = [v["id"] for v in vs if v["haupt"]["bewertung"]["bestanden"]]
    a(f"# Bericht Runde 2 (F-05, {b['datum']}) – KI-Meta-Filter auf den Signalen von S-REV-01 und S-REV-02")
    a("")
    a("Nur Prozent, R, Anzahlen und Trades je Monat. Vorregistrierung `docs/bot/prereg/F05_ENTWURF.md` "
      f"(SHA-256 `{b['prereg_sha'][:16]}…`), Versuchsprotokoll `forschung/versuchsprotokoll.jsonl` (Familie F05-META, 4 gezählte "
      "Versuche). Der Holdout (ab 01.07.2021) wurde nicht gezogen.")
    a("")
    a("## Ergebnis in einem Satz")
    a("")
    if bestanden:
        a(f"{len(bestanden)} von {len(vs)} Varianten erfüllen alle Entwicklungskriterien des 85-%-Tors (Hauptprofil, technisch gültig); "
          f"Holdout-Kandidat nach der Auswahlregel: **{b['auswahl']}**.")
        k = b["kandidat"]
        a("")
        a(f"Erwartete Trades je Monat (Entwicklung, Hauptprofil): {z(k['trades_pro_monat'], 1)}; 100 Demo-Trades nach etwa "
          f"{z(k['monate_fuer_100'], 1)} Monaten (ab {b['datum']}: um den {k['datum_100_trades_ab_heute']}). Bezogen nur auf die Zeit mit "
          f"Modell und Schwelle: {z(k['trades_pro_handelbarem_monat'], 1)} je Monat, 100 Trades um den {k['datum_100_trades_handelbar']}. "
          "Im Betrieb gilt die Schwelle des Holdout-Modells; die Rate kann davon abweichen.")
    else:
        a(f"**Keine der {len(vs)} Varianten erfüllt alle Entwicklungskriterien des 85-%-Tors. Es gibt keinen Holdout-Kandidaten.** "
          "Das ist ein gültiges, vorab als wahrscheinlich benanntes Ergebnis (Prereg §5).")
    ungueltig = [v["id"] for v in vs if v["haupt"]["bewertung"]["kriterien"]["technik"]["ok"] is not True]
    a("")
    a("Technisch gültig (keine Sperre, kein Vorfall, Signal- und Trade-Parität 100 %, Modell-Parität ≤ 1e-9): " + (
        "alle Läufe." if not ungueltig else f"**nicht** bei {', '.join(ungueltig)} – diese gelten als nicht bewertbar = nicht bestanden."))
    a("")
    a("## Kriterien je Variante (Hauptprofil, Testfenster 2013 bis 2021-H1)")
    a("")
    a("| Variante | Trades | T/Monat | Quote | Wilson-UG | E[R] | E[R]-UG 95 % | GF | ØV/ØG | Zufall Mittel / P95 | Max-DD | "
      "50-%-Folge / Schatten | Band/Budget | bestanden |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in vs:
        k = v["haupt"]["bewertung"]["kennzahlen"]
        kr = v["haupt"]["bewertung"]["kriterien"]
        schatten = ", ".join(f"{art} {n}" for art, n in sorted((k.get("schatten") or {}).items())) or "0"
        a(f"| {v['id']} | {k['n']} | {z(k['trades_pro_monat'], 1)} | {p(k['quote'])} | "
          f"{p(k['wilson_95'][0]) if k['wilson_95'] else '–'} | {z(k['e_r'], 3)} | {z(k['e_r_untergrenze'], 3)} | {z(k['pf_eur'])} | "
          f"{z(k['verlust_zu_gewinn_eur'])} | {p(k['zufall']['mittel'])} / {p(k['zufall']['p95'])} | {z(k['max_dd_prozent'], 1)} % | "
          f"{len(k.get('stop50_ereignisse') or [])} / {schatten} | {ok(kr['band_budget']['ok'])} | **{ok(v['haupt']['bewertung']['bestanden'])}** |")
    a("")
    a("„50-%-Folge“: Ereignisse der 50-%-Regel in der OOS-Tradefolge; „Schatten“: Schattenereignisse LOSS_LOCK und STOP50 im OOS-Zeitraum "
      "(jedes neue Eintreten zählt; im Betrieb hätte schon das erste den Handel gesperrt). Das Kriterium verlangt beides 0.")
    a("")
    namen = list(vs[0]["haupt"]["bewertung"]["kriterien"]) if vs else []
    a(f"Erfüllt je Kriterium (Anzahl Varianten von {len(vs)}):")
    a("")
    a("| " + " | ".join(namen) + " |")
    a("|" + "---|" * len(namen))
    a("| " + " | ".join(str(sum(1 for v in vs if v["haupt"]["bewertung"]["kriterien"][n]["ok"] is True)) for n in namen) + " |")
    a("")
    nb = [v["id"] for v in vs if v["nicht_bewertbar"]]
    if nb:
        a(f"Nicht bewertbar (Prereg: < 200 Trades und Testfenster ohne zulässige Schwelle): {', '.join(nb)} – zählt als nicht bestanden.")
        a("")
    a("Trades je Monat bezogen auf die Testzeit mit Modell und Schwelle (ohne Embargo und Fenster ohne Schwelle): " +
      "; ".join(f"{v['id']} {z(v['trades_pro_handelbarem_monat'], 1)} ({z(v['handelbare_monate'], 1)} Monate)" for v in vs) + ".")
    a("")
    a("Schwellen wie F-04 (config/tore.toml [tor_85]): ≥ 200 Trades, Quote ≥ 85 %, E[R]-Untergrenze > 0, Gewinnfaktor ≥ 1,2, Ø Verlust ≤ "
      "3 × Ø Gewinn, Quote > 95. Perzentil der Zufallsbasis (zufällige Richtung zu denselben, gefilterten Einstiegszeiten, komplette "
      "Ausstiegslogik, 1.000 Wiederholungen), Max-Drawdown < 25 %, kein 50-%-Ereignis, Band/Budget/Stop ≤ 3 × Ziel, Lauf technisch gültig. "
      "„n. b.“ = nicht bewertbar = nicht bestanden.")
    a("")
    a("## Filterwirkung (Basissignale im Testzeitraum, ohne Konto und Band)")
    a("")
    a("Entscheidung der Hülle je Basissignal aus den Datensatz-Merkmalen; Gewinnquote = Anteil Label „Ergebnis > 0“ (1 Lot, Hauptprofil, "
      "Dreifach-Barriere) – die reine Auswahlleistung des Filters, bevor Band, Budget, Handelsfenster und Positionsgrenze wirken.")
    a("")
    a("| Variante | Basissignale | Embargo | ohne Schwelle | unter Schwelle | durchgelassen | davon nie handelbar | Gewinnquote Basis | "
      "Gewinnquote durchgelassen |")
    a("|---|---|---|---|---|---|---|---|---|")
    for v in vs:
        f = v["training"]["filter"]
        e = f["entscheidungen"]
        a(f"| {v['id']} | {f['basissignale']} | {e.get('EMBARGO', 0)} | {e.get('KEINE_SCHWELLE', 0)} | {e.get('UNTER_SCHWELLE', 0)} | "
          f"{e.get('HANDELN', 0)} | {f['durchgelassen_nie_handelbar']} | {p(f['gewinnquote_basis'])} | {p(f['gewinnquote_durchgelassen'])} |")
    a("")
    a("„Nie handelbar“ (Untergrenze): außerhalb des Handelsfensters oder Stop > 3 × Ziel am Signal – der Takt lehnt solche Signale "
      "unabhängig vom Konto ab; er prüft Stop/Ziel zusätzlich mit gerundeten Kursen, deshalb können im Takt einige mehr abgelehnt werden. Sie "
      "zählen laut Vorregistrierung („alle Signale“) im Training und in der Schwellenwahl mit.")
    a("")
    a("## Schwellen je Testfenster (innere Validierung)")
    a("")
    a("Schwelle p* = kleinste Schwelle aus {0,50; 0,55; …; 0,90} mit der höchsten Wilson-95-%-Untergrenze der Validierungs-Trefferquote "
      "(mindestens 20 Validierungssignale über der Schwelle); „–“ = keine zulässige Schwelle → im Testfenster keine Trades.")
    a("")
    jahre = [_jahr(f["test_von"]) for f in vs[0]["training"]["fenster"]] if vs else []
    a("| Variante | " + " | ".join(jahre) + " | Holdout-Modell |")
    a("|---|" + "---|" * (len(jahre) + 1))
    for v in vs:
        tr = v["training"]
        zellen = []
        for f in tr["fenster"]:
            val = f.get("validierung") or {}
            zellen.append("–" if f["schwelle"] is None else f"{z(f['schwelle'])} ({p(val.get('quote'), 0)}, n {val.get('n')})")
        h = tr["holdout"]
        a(f"| {v['id']} | " + " | ".join(zellen) + f" | {'–' if h['schwelle'] is None else z(h['schwelle'])} |")
    a("")
    a("In Klammern: Validierungs-Trefferquote und Anzahl über der Schwelle. Modell-Parität (Standardbibliothek gegen scikit-learn, "
      "größte Abweichung der Wahrscheinlichkeit über alle Datensatzzeilen und Fenster): " +
      ", ".join(f"{v['id']} {v['training']['paritaet_max']:.1e}" for v in vs) + ".")
    a("")
    a("## Band-Wirkung und Quote Signal → Trade (Takt)")
    a("")
    a("| Variante | Signale (gefiltert) | Trades | Signal→Trade | Hebel min/Ø/max | Ablehnungen (häufigste) |")
    a("|---|---|---|---|---|---|")
    for v in vs:
        s = v["haupt"]["bewertung"]["kennzahlen"]["signale"]
        h = v["haupt"]["bewertung"]["kennzahlen"]["hebel"]
        abl = sorted(s["abgelehnt"].items(), key=lambda kv: -kv[1])[:5]
        a(f"| {v['id']} | {s['gesamt']} | {s['erledigt']} | {p(s['quote_signal_trade'])} | {z(h['min'])}/{z(h['mittel'])}/{z(h['max'])} | "
          + ", ".join(f"{g} {n}" for g, n in abl) + " |")
    a("")
    a("## Kosten-Gegenproben")
    a("")
    a("Die Modelle sind auf dem Hauptprofil trainiert und bleiben in allen Profilen gleich; das Merkmal Spread/ATR sieht im Profil "
      "„Kosten × 1,5“ den verschärften Spread.")
    a("")
    a("| Variante | Quote (Haupt) | Quote (Kosten × 1,5) | GF (Kosten × 1,5) | Quote (Kommission 3,25) | E[R] (Kommission 3,25) | GF (3,25) | "
      "bestanden (3,25) |")
    a("|---|---|---|---|---|---|---|---|")
    for v in vs:
        k = v["haupt"]["bewertung"]["kennzahlen"]
        x, g = v["kosten_x1_5"], v["gegenprobe_3_25"]
        a(f"| {v['id']} | {p(k['quote'])} | {p(x['quote'])} | {z(x['pf_eur'])} | {p(g['quote'])} | {z(g['e_r'], 3)} | {z(g['pf_eur'])} | "
          f"{ok(g['bestanden'])} |")
    a("")
    a("## Zusatzkriterien (nur berichtet, ZUSATZKRITERIEN-OK = nein)")
    a("")
    a("Teilperioden: vier gleich lange Abschnitte der Testzeit; „positiv“ nach dem Nettoergebnis in EUR, in Klammern die R-Summen.")
    a("")
    a("| Variante | DSR (N, N_eff) | Teilperioden positiv (R-Summen) | GF bei Kosten × 1,5 > 1,0 |")
    a("|---|---|---|---|")
    for v in vs:
        d = v["dsr"] or {}
        zt = v["zusatz"]
        dsr_txt = f"{z(d.get('dsr'), 3)} ({d.get('N', '–')}, {z(d.get('N_eff'), 1)})" if "dsr" in d else (d.get("fehler") or "–")
        a(f"| {v['id']} | {dsr_txt} | {zt['teilperioden']['positiv']}/4 ({', '.join(z(x, 1) for x in v['teilperioden_r'])}) | "
          f"{ok(zt['gewinnfaktor_kosten']['ok'])} |")
    a("")
    a("## Technik, Parität, Schatten")
    a("")
    a("| Variante | Technik gültig | Signal-Parität (gleich; Takt/direkt) | Trade-Parität (geprüft, Zwang) | Schattenereignisse | offen am Ende |")
    a("|---|---|---|---|---|---|")
    for v in vs:
        e = v["haupt"]
        pt, ps = e["paritaet"]["trades"], e["paritaet"]["signale"]
        a(f"| {v['id']} | {ok(e['bewertung']['kriterien']['technik']['ok'])} | {p(ps['quote'], 2)} ({ps['gleich']}; {ps['takt']}/{ps['direkt']}) | "
          f"{p(pt['quote'], 2)} ({pt['geprueft']}, {pt['zwangsausstiege']}) | {e['schatten_gesamt'] or '–'} | {e['offen_am_ende']} |")
    a("")
    a("## Daten und Verfahren")
    a("")
    a(f"Kerzen: genau die Abzüge der F-04-Datensicht (seq {b['daten']['f04_datensicht_seq']}, Hash je Symbol/Zeitrahmen, Zeitbasis W1). "
      f"Datensätze (Datensicht F-05, seq {b['daten']['datensicht_seq']}): " +
      "; ".join(f"{bid}: {d['zaehlung'].get('zeilen')} Signale mit Merkmalen, davon außerhalb des Handelsfensters "
                f"{d['zaehlung'].get('ausserhalb_fenster', 0)}, Stop > 3 × Ziel {d['zaehlung'].get('stop_zu_ziel', 0)}"
                for bid, d in b["daten"]["datensaetze"].items()) +
      ". Label je Signal (alle Signale, unabhängig von Konto, Band und Positionsbelegung) über die direkte Ausstiegsrechnung des Takts.")
    a("")
    a(f"Walk-Forward wie F-04: Anpassung 3 Jahre, Test 1 Jahr. Purge: Trainings- und Validierungssignale nur mit Label-Ausstieg bis zum "
      f"Ende ihrer Menge. Embargo: {EMBARGO_HANDELSTAGE} Handelstage (Mo–Fr ohne 1.1. und 25.12.) zu Beginn jedes Testfensters ohne "
      "Trades. Jedes Modell trägt seine Trainingsgrenzen; die Hülle verweigert Modelle, deren Daten ins Testfenster reichen. Merkmalsfenster "
      f"{mf.FENSTER} Kerzen. Vor 2013 hat die Hülle kein Modell und handelt nicht; das Konto startet damit 2013 mit dem Startkapital.")
    a("")
    a("## Grenzen dieser Auswertung")
    a("")
    for g in GRENZEN:
        a(f"- {g}")
    a("")
    a("Einordnung: " + b["einordnung"])
    a("")
    return "\n".join(zeilen)


GRENZEN = (
    *entwicklung.GRENZEN[:5],
    "Die Modelle lernen aus 3 Jahren Signalen je Fenster (S-REV-02: H4, deutlich weniger Signale); die Schwelle wählt die innere "
    "Validierung aus einem einzigen Jahr – das Ergebnis schwankt entsprechend.",
    "Die Basisvarianten wurden nach den F-04-Ergebnissen auf denselben Testjahren gewählt (12 Versuche); die DSR zählt nur die 4 Versuche "
    "der Familie F05-META und ist damit eher zu günstig.",
    "Training und Schwellenwahl enthalten laut Vorregistrierung alle Signale, auch solche, die der Takt nie handelt (Spalte „nie handelbar“).",
    "Im Profil „Kosten × 1,5“ sieht das Merkmal Spread/ATR den verschärften Spread: der Filter wählt dort andere Signale (keine reine "
    "Kostenverschärfung derselben Trades).",
    "Stunde und Wochentag stehen auf der Zeitbasis W1 (im US-Winter 1 h gegen Berlin verschoben), der H4-Spread folgt der Backtest-Regel; "
    "im Demo-Betrieb weichen beide leicht ab – vor einem Einsatz im Betrieb anzugleichen.",
    "Feiertage außer 1.1. und 25.12. zählen im Embargo als Handelstage.",
    "Das Holdout-Modell ist nur eingefroren (Anpassung 01.07.2018–30.06.2021, Schwelle aus der Validierung 07/2020–06/2021); es wird "
    "nur mit einem Kandidaten und nach eigener Vorregistrierung im Holdout geprüft.",
)
