"""Forschungsrunde 3 (F-05b): Richtungsmodell auf den handelbaren Entscheidungspunkten der F-04-Basisvarianten (Vorregistrierung
docs/bot/prereg/F05B_ENTWURF.md). Nur Standardbibliothek; das Training (scikit-learn) liegt in forschung/richtung_training.py und wird als
Funktion übergeben. Bausteine aus Runde 2 (kit.research.meta): Plan, Embargo, Schwellenregel, Kerzen wie im Takt, Datensatz-Format.

Ablauf (python -m forschung.runde3 …, Lauf F-05b):
  0. kit forschung vorab --lauf F-05b – Vorregistrierung F05B-RICHTUNG und F05B-DATEN (Code-Liste protokoll.CODE_F05B).
  1. daten        – Datensicht F05B-DATEN: je Basis die handelbaren Entscheidungspunkte mit Merkmalen und zwei Labels (Kauf, Verkauf zu
                    denselben Abständen) → work/f05b/<Basis>.jsonl; im Protokoll nur Hashes und Anzahlen.
  2. entwicklung  – je Variante TRIAL „Beginn“; je Fenster Kauf- und Verkaufsmodell, Schwelle d* für den Vorsprung (innere Validierung,
                    mindestens 50 Signale); eingefrorene Modelle forschung/modelle/F05B/<Variante>.json; drei Takt-Läufe je Variante;
                    Bewertung wie F-04/F-05; Bericht berichte/forschung/<datum>_runde3.md/.json; TRIAL „Ergebnis“.
Purge: Trainings- und Validierungszeilen nur, wenn beide Label-Ausstiege bis zum Ende ihrer Menge liegen. Embargo wie F-05.
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
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt, simulieren
from kit.domain.types import Side
from kit.gates import ROOT, tore
from kit.gates import trade_test as tt
from kit.research import entwicklung, meta, protokoll, stats, trials
from kit.strategy import meta_filter as mf
from kit.strategy import richtung as rf

D = Decimal
LAUF = "F-05b"
FAMILIE = "F05B-RICHTUNG"
FAMILIE_DATEN = "F05B-DATEN"
GITTER = (0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
MIN_VALIDIERUNG = 50
PROFILE = entwicklung.PROFILE
DATENSAETZE = ROOT / "work" / "f05b"                         # gitignored: abgeleitete Kursdaten, nie veröffentlicht
MODELLE = ROOT / "forschung" / "modelle" / "F05B"
BERICHTE = entwicklung.BERICHTE
HYPERPARAMETER = meta.HYPERPARAMETER
PLAN_SCHLUESSEL = meta.PLAN_SCHLUESSEL


@dataclass(frozen=True)
class RichtungsVariante:
    id: str
    basis_id: str
    art: str
    modell: str


VARIANTEN = (
    RichtungsVariante("F05B-REV01-LOGREG", meta.BASIS_REV01, "REV01", "LOGREG"),
    RichtungsVariante("F05B-REV01-HGB", meta.BASIS_REV01, "REV01", "HGB"),
    RichtungsVariante("F05B-REV02-LOGREG", meta.BASIS_REV02, "REV02", "LOGREG"),
    RichtungsVariante("F05B-REV02-HGB", meta.BASIS_REV02, "REV02", "HGB"),
)
BASEN = meta.BASEN
Trainer = Callable[[list[dict], RichtungsVariante, list[dict]], dict]


def variante(vid: str) -> RichtungsVariante:
    return next(v for v in VARIANTEN if v.id == vid)


def stop_ziel_max() -> Decimal:
    return D(str(tore()["limits"]["stop_zu_ziel_max"]))


def huelle_laden(pfad: Path | str, v: RichtungsVariante, *, holdout: bool = False) -> rf.Richtungsfilter:
    return rf.laden(pfad, meta.basis_strategie(v.basis_id), konf=runner.bot_konfiguration(), stop_ziel_max=stop_ziel_max(), holdout=holdout)


# ---------------------------------------------------------------------------------------------------- Datensatz
def datensatz(basis, art: str, kerzen_tf: Mapping[str, Sequence], markt: Markt, konf=None) -> tuple[list[dict], dict]:
    """Handelbare Entscheidungspunkte der Basis mit genau der Fensterregel der Hülle im Takt (paritaet.signal_fenster, rueckblick =
    max(Basis, FENSTER)); je Punkt Merkmale und zwei Labels (Kauf, Verkauf) zu denselben Abständen (direkte Ausstiegsrechnung, 1 Lot,
    Einstieg Ask/Bid des Schritts). Unabhängig von Konto, Band und Positionsbelegung."""
    konf = konf or runner.bot_konfiguration()
    szm = stop_ziel_max()
    rb = max(int(basis.rueckblick), mf.FENSTER)
    spanne_l = getattr(basis, "L", None) if art == "REV02" else None
    zeilen: list[dict] = []
    zaehlung: Counter[str] = Counter()
    for sym in basis.symbole:
        kerzen = list(kerzen_tf.get(sym, ()))
        for i, jetzt, fenster in paritaet.signal_fenster(basis.zeitrahmen, rb, kerzen, markt.schritte):
            sig = basis.signal(sym, fenster[-int(basis.rueckblick):])
            if sig is None:
                continue
            zaehlung["basissignale"] += 1
            k = kerzen[i]
            kauf, verkauf = rf.spiegeln(sig, k, Side.BUY), rf.spiegeln(sig, k, Side.SELL)
            if not rf.handelbar(jetzt, kauf, verkauf, k, konf, szm):
                zaehlung["nicht_handelbar"] += 1
                continue
            x = mf.merkmale(fenster, sig.side, art, spanne_l=spanne_l)
            if x is None:
                zaehlung["ohne_merkmale"] += 1
                continue
            q = markt.kurs(sym, jetzt)
            if q is None:
                zaehlung["ohne_kurs"] += 1
                continue
            zaehlung["kurs_abweichung"] += int(q[0] != k.close)        # H4 ohne H1-Kerze desselben Schlusses (Datenlücke)
            ak = simulieren(markt, sym, Side.BUY, q[1], kauf.sl, kauf.tp, D(1), jetzt, basis.max_halte_s)
            av = simulieren(markt, sym, Side.SELL, q[0], verkauf.sl, verkauf.tp, D(1), jetzt, basis.max_halte_s)
            offen = "OFFEN" in (ak.grund, av.grund)
            zaehlung["offen"] += int(offen)
            ziel, stop = rf.abstaende(sig, k)
            zeilen.append({"symbol": sym, "t_kerze": k.time, "t_ent": jetzt, "basis_side": str(sig.side), "x": x,
                           "sl_k": str(kauf.sl), "tp_k": str(kauf.tp), "sl_v": str(verkauf.sl), "tp_v": str(verkauf.tp),
                           "label_k": None if offen else int(ak.ergebnis > 0), "label_v": None if offen else int(av.ergebnis > 0),
                           "t_exit_k": None if offen else ak.t, "t_exit_v": None if offen else av.t,
                           "t_exit": None if offen else max(ak.t, av.t), "geometrie": float(stop / (stop + ziel))})
    zeilen.sort(key=lambda z: (z["t_ent"], z["symbol"]))
    zaehlung["zeilen"] = len(zeilen)
    return zeilen, dict(sorted(zaehlung.items()))


def menge(zeilen: Sequence[Mapping], von: int, bis: int) -> list[Mapping]:
    """Trainier- bzw. Validierungsmenge: Entscheidung in [von, bis), beide Labels vorhanden, beide Ausstiege ≤ bis (Purge)."""
    return [z for z in zeilen if von <= z["t_ent"] < bis and z["label_k"] is not None and z["label_v"] is not None
            and z["t_exit"] is not None and z["t_exit"] <= bis]


def gepurgt(zeilen: Sequence[Mapping], von: int, bis: int) -> int:
    return sum(1 for z in zeilen if von <= z["t_ent"] < bis) - len(menge(zeilen, von, bis))


def entscheidung(f: rf.Fenster, z: Mapping) -> tuple[str, str | None, float | None]:
    """(Entscheidung, gewählte Richtung, Vorsprung) für eine Datensatzzeile – dieselbe Rechnung wie Richtungsfilter.bewerten."""
    if z["t_ent"] < f.embargo_bis:
        return "EMBARGO", None, None
    if f.schwelle is None or f.modell_kauf is None:
        return "KEINE_SCHWELLE", None, None
    pk, pv = mf.wahrscheinlichkeit(f.modell_kauf, z["x"]), mf.wahrscheinlichkeit(f.modell_verkauf, z["x"])
    side = "BUY" if pk >= pv else "SELL"
    return ("HANDELN" if abs(pk - pv) > f.schwelle else "UNTER_SCHWELLE"), side, abs(pk - pv)


def purge_pruefen(modell_datei: Mapping, zeilen: Sequence[Mapping], plan_werte: Sequence[Mapping] | None = None) -> list[str]:
    """Gegenprobe zu den Angaben des Trainers wie in Runde 2 (Grenzen und Anzahlen der drei Mengen, Embargo, Plan, Modellgrenzen beider
    Modelle) – fail-closed, fehlende Angaben sind Befunde."""
    befunde = []
    fenster = [*modell_datei["fenster"], modell_datei["holdout"]]
    if plan_werte is not None and [tuple(f.get(k) for k in PLAN_SCHLUESSEL) for f in fenster] != \
            [tuple(p[k] for k in PLAN_SCHLUESSEL) for p in plan_werte]:
        befunde.append("plan:Fenster der Modelldatei weichen vom registrierten Plan ab")
    for f in fenster:
        tv = f["test_von"]
        if f.get("embargo_bis") != meta.embargo_ende(tv):
            befunde.append(f"embargo:{tv}")
        for name, (von, bis) in {"innen": (f["fit_von"], f["val_von"]), "validierung": (f["val_von"], tv),
                                 "final": (f["fit_von"], tv)}.items():
            g = (f.get("grenzen") or {}).get(name)
            if not isinstance(g, Mapping):
                befunde.append(f"grenzen_fehlen:{name}:{tv}")
                continue
            if g.get("n") != len(menge(zeilen, von, bis)):
                befunde.append(f"anzahl:{name}:{tv}")
            if g.get("n") and not (g.get("max_t_exit") is not None and g["max_t_exit"] <= bis and g.get("max_t_ent") is not None
                                   and g["max_t_ent"] < bis and von <= g.get("min_t_ent", von)):
                befunde.append(f"grenze:{name}:{tv}")
        trainings = []
        for schluessel in ("modell_kauf", "modell_verkauf"):
            m = f.get(schluessel)
            if m is not None:
                tr = m.get("training") or {}
                trainings.append(tr)
                final = (f.get("grenzen") or {}).get("final") or {}
                if not (tr.get("max_t_exit") is not None and tr["max_t_exit"] <= tv and tr.get("val_max_t_exit") is not None
                        and tr["val_max_t_exit"] <= tv and tr.get("fit_bis") == tv and tr.get("fit_von") == f["fit_von"]
                        and tr.get("n") == final.get("n") == len(menge(zeilen, f["fit_von"], tv))):
                    befunde.append(f"modellgrenze:{schluessel}:{tv}")
        if len(trainings) == 2 and trainings[0] != trainings[1]:
            befunde.append(f"modellgrenze:kauf_verkauf_ungleich:{tv}")
    return befunde


# ---------------------------------------------------------------------------------------------------- Wirkung (direkt, ohne Takt)
def wirkung(zeilen: Sequence[Mapping], huelle: rf.Richtungsfilter, fenster: Sequence[tuple[int, int]]) -> dict:
    """Entscheidungen je Datensatzzeile im Testzeitraum und der Richtungsvorsprung ohne Konto und Band: Trefferquote der gewählten
    Richtung gegen das Mittel beider Richtungen (= zufällige Richtung) an denselben Zeitpunkten, dazu Geometriewert und Anteil Kauf."""
    zaehl: Counter[str] = Counter()
    gewaehlt, beide, geometrie, kauf, mit_basis = [], [], [], 0, 0
    for z in zeilen:
        if not any(a <= z["t_ent"] < b for a, b in fenster):
            continue
        f = huelle.fenster_fuer(z["t_ent"])
        e, side, _ = ("KEIN_FENSTER", None, None) if f is None else entscheidung(f, z)
        zaehl[e] += 1
        if e == "HANDELN" and z["label_k"] is not None:
            gewaehlt.append(z["label_k"] if side == "BUY" else z["label_v"])
            beide.append((z["label_k"] + z["label_v"]) / 2)
            geometrie.append(z["geometrie"])
            kauf += int(side == "BUY")
            mit_basis += int(side == z["basis_side"])
    n = len(gewaehlt)
    return {"entscheidungen": dict(sorted(zaehl.items())), "zeilen": sum(zaehl.values()), "durchgelassen_mit_label": n,
            "quote_gewaehlt": sum(gewaehlt) / n if n else None, "quote_zufall": sum(beide) / n if n else None,
            "vorsprung_punkte": 100 * (sum(gewaehlt) - sum(beide)) / n if n else None,
            "geometrie_mittel": sum(geometrie) / n if n else None, "anteil_kauf": kauf / n if n else None,
            "anteil_wie_basis": mit_basis / n if n else None}


def datensatz_paritaet(zeilen: Sequence[Mapping], huelle: rf.Richtungsfilter, takt_signale: Sequence[Sequence]) -> dict:
    """Takt-Signale (Symbol, Kerze, Richtung) gegen die Entscheidungen der Hülle aus den Datensatz-Merkmalen. Soll 100 %."""
    direkt = []
    for z in zeilen:
        f = huelle.fenster_fuer(z["t_ent"])
        if f is None:
            continue
        e, side, _ = entscheidung(f, z)
        if e == "HANDELN":
            direkt.append((z["symbol"], int(z["t_kerze"]), side))
    return paritaet.vergleich([(s, int(k), str(r)) for s, k, r in takt_signale], direkt)


# ---------------------------------------------------------------------------------------------------- Takt-Lauf (Arbeitsprozess)
def aufgabe(vid: str, profil_name: str, db: str, sw: dict, soll: dict[str, str], modell_pfad: str) -> dict:
    d = entwicklung._daten(db, soll)
    h1, h4 = d["kerzen"]["H1"], d["kerzen"]["H4"]
    v = variante(vid)
    strat = huelle_laden(modell_pfad, v)
    profil = entwicklung.kostenprofil(profil_name, sw)
    konf = tt.konfig()
    k = konf["konto"]
    einst = runner.Einstellungen(profil, start_equity=D(k["start_equity"]), hebel=int(k["hebel"]), versatz_s=int(k["versatz_s"]))
    tf_kerzen = h4 if strat.zeitrahmen == "H4" else None
    with tempfile.TemporaryDirectory(prefix="kit_f05b_") as ablage:
        erg = runner.laufen(strat, h1, Path(ablage), einst, tf_kerzen=tf_kerzen)
    kerzen_takt = meta.takt_kerzen(h1, h4, strat.zeitrahmen, profil)
    e = entwicklung.bewerten_lauf(erg, strat, profil, h1, kerzen_takt, vid, profil_name, konf, spread_abgebildet=True)
    e["takt_signale"] = [[s["symbol"], int(s["kerze"]), s["side"]] for s in erg.signale]
    return e


# ---------------------------------------------------------------------------------------------------- Schritt 1: Datensicht
def daten_eintragen(*, datum: str, db: Path | None = None, protokoll_pfad: Path = protokoll.PFAD, ordner: Path = DATENSAETZE,
                    vorpruefen: bool = True, kerzen: Mapping | None = None) -> dict:
    """Datensicht F05B-DATEN (atomar wie Runde 2): Vorprüfung, Kerzen der F-04-Abzüge, Datensätze im Speicher, Protokolleintrag, erst
    dann die Dateien. Reste eines abgebrochenen Laufs (Dateien ohne Datensicht) brechen ab."""
    log = protokoll.lesen(protokoll_pfad)
    if vorpruefen:
        protokoll.vorpruefung(pfad=protokoll_pfad, lauf=LAUF)
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung F-05b fehlt (kit forschung vorab --lauf F-05b)")
    if any(e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN for e in log):
        raise protokoll.ProtokollFehler("Datensicht F-05b schon eingetragen – die Datensätze gelten einmal je Lauf")
    vorhanden = [b for b in BASEN if (Path(ordner) / f"{b}.jsonl").exists()]
    if vorhanden:
        raise protokoll.ProtokollFehler(f"Datensätze ohne Datensicht vorhanden ({', '.join(vorhanden)}) – Abbruch eines früheren Laufs "
                                        "klären und im HANDOFF vermerken, dann die Dateien entfernen")
    sicht04 = meta._f04_sicht(log)
    soll = meta._soll(sicht04)
    if kerzen is None:
        kerzen = entwicklung.daten_laden(Path(db or entwicklung.db_pfad()), ("H1", "H4"), soll)["kerzen"]
    h1, h4 = kerzen["H1"], kerzen["H4"]
    profil = entwicklung.kostenprofil("HAUPT", entwicklung.startwerte())
    markt = Markt(h1, profil, versatz_s=entwicklung.serverversatz_daten())
    datensaetze, texte = {}, {}
    for basis_id in BASEN:
        basis = meta.basis_strategie(basis_id)
        art = meta.art_der_basis(basis_id)
        zeilen, zaehlung = datensatz(basis, art, meta.takt_kerzen(h1, h4, basis.zeitrahmen, profil), markt)
        texte[basis_id] = meta.datensatz_text(zeilen)
        datensaetze[basis_id] = {"datei": f"{basis_id}.jsonl", "sha256": hashlib.sha256(texte[basis_id].encode("utf-8")).hexdigest(),
                                 "zaehlung": zaehlung, "merkmale": list(mf.merkmal_namen(art))}
    abzuege = [a for a in sicht04["body"]["daten"]["abzuege"] if a["zeitrahmen"] in ("H1", "H4")]
    eintrag = protokoll.datensicht(FAMILIE_DATEN, "DATENSATZ", "DEVELOPMENT", datum, {"abzuege": abzuege, "f04_datensicht_seq": sicht04["seq"]},
                                   pfad=protokoll_pfad, datensaetze=datensaetze, kostenprofil="HAUPT", label_lots="1",
                                   labels="Kauf und Verkauf zu denselben Abständen", startwerte_sha=protokoll.sha256_datei(entwicklung.STARTWERTE),
                                   zeitbasis="Serverzeit − versatz_s (F-04 W1)", versatz_s=entwicklung.serverversatz_daten())
    Path(ordner).mkdir(parents=True, exist_ok=True)
    for basis_id, text in texte.items():
        (Path(ordner) / f"{basis_id}.jsonl").write_text(text, encoding="utf-8", newline="\n")
    return {"seq": eintrag["seq"], "datensaetze": {b: {"zeilen": d["zaehlung"]["zeilen"], "sha256": d["sha256"][:16]} for b, d in datensaetze.items()}}


# ---------------------------------------------------------------------------------------------------- Schritt 2: Entwicklung
def _sicht(log: Sequence[Mapping]) -> Mapping:
    sicht = [e for e in log if e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == FAMILIE_DATEN]
    if not sicht:
        raise protokoll.ProtokollFehler("Datensicht F-05b fehlt (python -m forschung.runde3 daten)")
    return sicht[-1]


def ausfuehren(*, datum: str, trainer: Trainer, prozesse: int | None = None, db: Path | None = None,
               sw_pfad: Path = entwicklung.STARTWERTE, protokoll_pfad: Path = protokoll.PFAD, datensatz_ordner: Path = DATENSAETZE,
               modell_ordner: Path = MODELLE, bericht_ordner: Path = BERICHTE, melden=print, vorpruefen: bool = True,
               nur: Sequence[str] | None = None, plan_werte: Sequence[dict] | None = None) -> dict:
    """Schritt 2 – genau einmal je Familie, fail-closed wie Runde 2 (Vorprüfung, Datensicht, Datensatz-Hash, kein zweites Ergebnis, keine
    vorhandene Berichts- oder Modelldatei; erst alle Modelle anpassen und prüfen, dann schreiben)."""
    log = protokoll.lesen(protokoll_pfad)
    if vorpruefen:
        stand = protokoll.vorpruefung(pfad=protokoll_pfad, lauf=LAUF)
    else:
        stand = {"commit": None, "mechanik_hash": entwicklung.mechanik_hash(), "code": {}, "prereg_sha": protokoll.runde(LAUF)["prereg_sha"]}
    if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == FAMILIE for e in log):
        raise protokoll.ProtokollFehler("Vorregistrierung F-05b fehlt (kit forschung vorab --lauf F-05b)")
    sicht = _sicht(log)
    if any(e["body"].get("kind") == "TRIAL" and e["body"].get("phase") == "ERGEBNIS" and e["body"].get("family") == FAMILIE for e in log):
        raise protokoll.ProtokollFehler("Die Familie F05B-RICHTUNG ist schon ausgewertet – eine Neuauswertung braucht eine neue Vorregistrierung")
    for endung in ("json", "md"):
        if (Path(bericht_ordner) / f"{datum}_runde3.{endung}").exists():
            raise protokoll.ProtokollFehler(f"Bericht {datum}_runde3 existiert schon – nie überschreiben")
    liste = [v for v in VARIANTEN if nur is None or v.id in nur]
    for v in liste:
        if (Path(modell_ordner) / f"{v.id}.json").exists():
            raise protokoll.ProtokollFehler(f"Modelldatei {v.id}.json existiert schon – nie überschreiben")
    ds = sicht["body"]["datensaetze"]
    zeilen = {b: meta.datensatz_lesen(Path(datensatz_ordner) / ds[b]["datei"], ds[b]["sha256"]) for b in {v.basis_id for v in liste}}
    soll = meta._soll(sicht)
    db = Path(db or entwicklung.db_pfad())
    sw = entwicklung.startwerte(sw_pfad)
    plaene = list(meta.plan() if plan_werte is None else plan_werte)
    test_fenster = [(f["test_von"], f["test_bis"]) for f in plaene if not f["holdout"]]
    gemeinsam = {"commit": stand["commit"], "prereg_sha": stand["prereg_sha"], "mechanik_hash": stand["mechanik_hash"],
                 "code": stand["code"], "startwerte_sha": protokoll.sha256_datei(sw_pfad), "datensicht_seq": sicht["seq"]}
    for v in liste:
        protokoll.versuch(FAMILIE, v.id, datum, pfad=protokoll_pfad, phase="BEGINN", basis=v.basis_id, modell=v.modell,
                          hyperparameter=HYPERPARAMETER[v.modell], merkmale=list(mf.merkmal_namen(v.art)), merkmal_fenster=mf.FENSTER,
                          gitter=list(GITTER), min_validierung=MIN_VALIDIERUNG, embargo_handelstage=meta.EMBARGO_HANDELSTAGE,
                          purge="beide Label-Ausstiege ≤ Ende der Trainings-/Validierungsmenge", schwelle="|p_Kauf − p_Verkauf| > d*",
                          datensatz_sha=ds[v.basis_id]["sha256"], plan=[{k: f[k] for k in PLAN_SCHLUESSEL} for f in plaene],
                          kostenprofile=list(PROFILE), **gemeinsam)
    trainiert: dict[str, dict] = {}
    konf = runner.bot_konfiguration()
    for v in liste:
        melden(f"Training {v.id} …")
        daten = trainer(zeilen[v.basis_id], v, plaene)
        if daten.get("variante") != v.id or daten.get("datensatz_sha") != ds[v.basis_id]["sha256"]:
            raise protokoll.ProtokollFehler(f"Modell {v.id}: Variante oder Datensatz passt nicht")
        befunde = purge_pruefen(daten, zeilen[v.basis_id], plaene)
        if befunde:
            raise protokoll.ProtokollFehler(f"Purge/Embargo/Plan verletzt ({v.id}): {befunde[:3]}")
        if not float(daten["paritaet_max"]) <= 1e-9:
            raise protokoll.ProtokollFehler(f"Modell {v.id}: Laufzeit-Parität {daten['paritaet_max']} > 1e-9")
        basis = meta.basis_strategie(v.basis_id)
        for teil in (daten, {"fenster": [daten["holdout"]]}):                      # Modellbindung (wirft bei Verstoß)
            rf.Richtungsfilter(basis, rf.fenster_aus_json(teil), art=daten["art"], name=v.id, konf=konf, stop_ziel_max=stop_ziel_max())
        trainiert[v.id] = daten
    modelle: dict[str, Path] = {}
    info: dict[str, dict] = {}
    for v in liste:
        daten = trainiert[v.id]
        gepackt = {**daten, "fenster": [_packen(f) for f in daten["fenster"]], "holdout": _packen(daten["holdout"])}
        modelle[v.id] = meta.modell_schreiben(gepackt, modell_ordner)
        geladen = json.loads(modelle[v.id].read_text(encoding="utf-8"))
        for f_alt, f_neu in zip([*daten["fenster"], daten["holdout"]], [*geladen["fenster"], geladen["holdout"]], strict=True):
            for s in ("modell_kauf", "modell_verkauf"):                              # verlustfrei gespeichert (fail-closed)
                if not rf.rechengleich(f_alt.get(s), rf.entpacken(f_neu.get(s))):
                    raise protokoll.ProtokollFehler(f"Modelldatei {v.id}: gespeichertes Modell rechnet anders ({s})")
        huelle = huelle_laden(modelle[v.id], v)
        info[v.id] = {"sha256": mf.datei_sha(modelle[v.id]), "paritaet_max": daten["paritaet_max"],
                      "fenster": [{k: f.get(k) for k in ("test_von", "test_bis", "schwelle", "n_innen", "n_validierung", "n_final",
                                                         "gepurgt_innen", "gepurgt_validierung", "gepurgt_final", "validierung")}
                                  for f in daten["fenster"]],
                      "holdout": {k: daten["holdout"].get(k) for k in ("schwelle", "n_innen", "n_validierung", "n_final")},
                      "wirkung": wirkung(zeilen[v.basis_id], huelle, test_fenster)}
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
        huelle = huelle_laden(modelle[v.id], v)
        for p in PROFILE:
            e = ergebnisse[(v.id, p)]
            signale = e.pop("takt_signale")
            if p == "KOSTEN_X1_5":
                continue                                    # dort sieht das Merkmal Spread/ATR den verschärften Spread
            dp = datensatz_paritaet(zeilen[v.basis_id], huelle, signale)
            if p == "HAUPT":
                info[v.id]["datensatz_paritaet"] = {k: dp[k] for k in ("takt", "direkt", "gleich", "quote")}
            tk = e["bewertung"]["kriterien"]["technik"]
            tk["wert"]["datensatz_paritaet"] = dp["quote"]
            if dp["quote"] != 1.0:
                tk["ok"] = None
                e["bewertung"]["bestanden"] = False
    log = protokoll.lesen(protokoll_pfad)
    haupt = {vid: e for (vid, p), e in ergebnisse.items() if p == "HAUPT"}
    dsr = dsr_familie(haupt, log, [v.id for v in liste])
    auswahl = tt.auswahl({v.id: haupt[v.id]["bewertung"] for v in liste})
    bericht = bericht_daten(ergebnisse, info, dsr, auswahl, sicht, datum, liste, test_fenster)
    md, js = bericht_schreiben(bericht, Path(bericht_ordner), datum)
    sha = hashlib.sha256(js.read_bytes()).hexdigest()
    for v in liste:
        e = haupt[v.id]
        k = e["bewertung"]["kennzahlen"]
        kurz = {"bestanden": e["bewertung"]["bestanden"], "trades": k["n"], "quote": k["quote"], "e_r": k["e_r"],
                "e_r_untergrenze": k["e_r_untergrenze"], "pf_eur": k["pf_eur"], "max_dd_prozent": k["max_dd_prozent"],
                "trades_pro_monat": k["trades_pro_monat"], "technik": e["bewertung"]["kriterien"]["technik"]["ok"],
                "zufall_mittel": k["zufall"]["mittel"], "bestanden_3_25": ergebnisse[(v.id, "GEGENPROBE_3_25")]["bewertung"]["bestanden"]}
        protokoll.versuch(FAMILIE, v.id, datum, pfad=protokoll_pfad, phase="ERGEBNIS", ergebnis=meta._json(kurz), bericht=js.name,
                          bericht_sha=sha, auswahl=auswahl, modell_datei=modelle[v.id].name, modell_sha=info[v.id]["sha256"], **gemeinsam)
    return {"bericht_md": str(md), "bericht_json": str(js), "auswahl": auswahl, "modelle": {k: str(p) for k, p in modelle.items()}}


def _packen(f: Mapping) -> dict:
    return {**f, "modell_kauf": rf.packen(f.get("modell_kauf")), "modell_verkauf": rf.packen(f.get("modell_verkauf"))}


def dsr_familie(haupt: Mapping[str, dict], log: list[dict], ids: Sequence[str]) -> dict[str, dict | None]:
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
def bericht_daten(ergebnisse: Mapping, info: Mapping, dsr: Mapping, auswahl: str | None, sicht: Mapping, datum: str,
                  liste: Sequence[RichtungsVariante], test_fenster: Sequence[tuple[int, int]]) -> dict:
    varianten = []
    for v in liste:
        h, x15, g = (ergebnisse[(v.id, p)] for p in PROFILE)
        zus = tt.zusatz(tt.konfig(), teilperioden_werte=[D(1) if p else D(-1) for p in h["teilperioden"]["positiv"]],
                        gewinnfaktor_kosten=entwicklung._pf_dez(x15["bewertung"]["kennzahlen"]["pf_eur"]), dsr=(dsr.get(v.id) or {}).get("dsr"))
        n = h["bewertung"]["kennzahlen"]["n"]
        ohne = sum(1 for f in info[v.id]["fenster"] if f["schwelle"] is None)
        varianten.append({"id": v.id, "basis": v.basis_id, "modell": v.modell, "haupt": h, "kosten_x1_5": entwicklung._kurz(x15),
                          "gegenprobe_3_25": entwicklung._kurz(g), "zusatz": meta._json(zus), "dsr": dsr.get(v.id),
                          "teilperioden_r": h["teilperioden"]["r_summe"], "training": info[v.id], "fenster_ohne_schwelle": ohne,
                          "nicht_bewertbar": bool(n < int(tore()["tor_85"]["min_trades_oos"]) and ohne > 0)})
    kandidat = None
    if auswahl is not None:
        k = next(x for x in varianten if x["id"] == auswahl)["haupt"]["bewertung"]["kennzahlen"]
        tpm = k["trades_pro_monat"] or 0.0
        kandidat = {"variante": auswahl, "trades_pro_monat": tpm, "monate_fuer_100": (100 / tpm) if tpm > 0 else None,
                    "datum_100_trades_ab_heute": meta._datum_nach_monaten(datum, 100 / tpm) if tpm > 0 else None}
    return {"schema": "f05b_runde3/1", "datum": datum, "lauf": LAUF, "prereg_sha": protokoll.runde(LAUF)["prereg_sha"],
            "einordnung": "Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.",
            "daten": {"f04_datensicht_seq": sicht["body"]["daten"]["f04_datensicht_seq"], "datensicht_seq": sicht["seq"],
                      "datensaetze": {b: {"sha256": d["sha256"][:16], "zaehlung": d["zaehlung"]} for b, d in sicht["body"]["datensaetze"].items()},
                      "holdout": "nicht gezogen"},
            "verfahren": {"gitter": list(GITTER), "min_validierung": MIN_VALIDIERUNG, "embargo_handelstage": meta.EMBARGO_HANDELSTAGE,
                          "merkmal_fenster": mf.FENSTER, "hyperparameter": HYPERPARAMETER, "testfenster": [[a, b] for a, b in test_fenster]},
            "varianten": varianten, "auswahl": auswahl, "kandidat": kandidat,
            "kostenprofile": {p: entwicklung._ohne_swap(entwicklung.kostenprofil(p, entwicklung.startwerte())) for p in PROFILE}}


def bericht_schreiben(b: Mapping, ordner: Path, datum: str) -> tuple[Path, Path]:
    ordner.mkdir(parents=True, exist_ok=True)
    js, md = ordner / f"{datum}_runde3.json", ordner / f"{datum}_runde3.md"
    if js.exists() or md.exists():
        raise FileExistsError(f"{datum}_runde3 existiert schon")
    js.write_text(json.dumps(b, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    md.write_text(markdown(b), encoding="utf-8", newline="\n")
    return md, js


def _jahr(t: int) -> str:
    d = dt.datetime.fromtimestamp(t, dt.UTC)
    return f"{d.year}" if d.month == 1 else f"{d.year}-{d.month:02d}"


def markdown(b: Mapping) -> str:
    p, z, ok = entwicklung._p, entwicklung._z, entwicklung._ok
    zeilen: list[str] = []
    a = zeilen.append
    vs = b["varianten"]
    bestanden = [v["id"] for v in vs if v["haupt"]["bewertung"]["bestanden"]]
    a(f"# Bericht Runde 3 (F-05b, {b['datum']}) – Richtungsmodell auf den Entscheidungspunkten von S-REV-01 und S-REV-02")
    a("")
    a("Nur Prozent, R, Anzahlen und Trades je Monat. Vorregistrierung `docs/bot/prereg/F05B_ENTWURF.md` "
      f"(SHA-256 `{b['prereg_sha'][:16]}…`), Versuchsprotokoll `forschung/versuchsprotokoll.jsonl` (Familie F05B-RICHTUNG, 4 gezählte "
      "Versuche). Der Holdout (ab 01.07.2021) wurde nicht gezogen. Nach V9 die letzte Forschungsrunde.")
    a("")
    a("## Ergebnis in einem Satz")
    a("")
    if bestanden:
        a(f"{len(bestanden)} von {len(vs)} Varianten erfüllen alle Entwicklungskriterien des 85-%-Tors; Holdout-Kandidat nach der "
          f"Auswahlregel: **{b['auswahl']}**.")
        k = b["kandidat"]
        a("")
        a(f"Erwartete Trades je Monat (Entwicklung, Hauptprofil): {z(k['trades_pro_monat'], 1)}; 100 Demo-Trades nach etwa "
          f"{z(k['monate_fuer_100'], 1)} Monaten (ab {b['datum']}: um den {k['datum_100_trades_ab_heute']}).")
    else:
        a(f"**Keine der {len(vs)} Varianten erfüllt alle Entwicklungskriterien des 85-%-Tors. Es gibt keinen Holdout-Kandidaten.** "
          "Nach V9 entscheidet jetzt der Betreiber (weiter forschen mit neuer Idee / Demo-Live bewusst ohne Tor als Datensammlung / Pause).")
    ungueltig = [v["id"] for v in vs if v["haupt"]["bewertung"]["kriterien"]["technik"]["ok"] is not True]
    andere = [f"{v['id']} ({name})" for v in vs for name, kurz in (("Kosten × 1,5", v["kosten_x1_5"]), ("Kommission 3,25", v["gegenprobe_3_25"]))
              if kurz["technik_ok"] is not True or kurz["kriterien"].get("technik") is not True]
    a("")
    a("Technisch gültig im Hauptprofil (keine Sperre, kein Vorfall, Signal-, Trade- und Datensatz-Parität 100 %, Modell-Parität ≤ 1e-9): " + (
        "alle Varianten." if not ungueltig else f"**nicht** bei {', '.join(ungueltig)} – diese gelten als nicht bewertbar = nicht bestanden.")
      + " Gegenproben: " + ("alle 8 Läufe technisch gültig (Datensatz-Parität im Profil Kommission 3,25 geprüft, im Profil Kosten × 1,5 "
                            "nicht anwendbar)." if not andere else f"technisch ungültig: {', '.join(andere)}."))
    a("")
    a("## Kriterien je Variante (Hauptprofil, Testfenster 2013 bis 2021-H1)")
    a("")
    a("| Variante | Trades | T/Monat | Quote | Zufall Mittel / P95 | Quote − Zufall | Wilson-UG | E[R] | E[R]-UG 95 % | GF | ØV/ØG | Max-DD | "
      "50-%-Folge / Schatten | Band/Budget | bestanden |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in vs:
        k = v["haupt"]["bewertung"]["kennzahlen"]
        kr = v["haupt"]["bewertung"]["kriterien"]
        schatten = ", ".join(f"{art} {n}" for art, n in sorted((k.get("schatten") or {}).items())) or "0"
        abstand = None if k["quote"] is None or k["zufall"]["mittel"] is None else 100 * (k["quote"] - k["zufall"]["mittel"])
        a(f"| {v['id']} | {k['n']} | {z(k['trades_pro_monat'], 1)} | {p(k['quote'])} | {p(k['zufall']['mittel'])} / {p(k['zufall']['p95'])} | "
          f"{z(abstand, 1)} Pkt | {p(k['wilson_95'][0]) if k['wilson_95'] else '–'} | {z(k['e_r'], 3)} | {z(k['e_r_untergrenze'], 3)} | "
          f"{z(k['pf_eur'])} | {z(k['verlust_zu_gewinn_eur'])} | {z(k['max_dd_prozent'], 1)} % | {len(k.get('stop50_ereignisse') or [])} / "
          f"{schatten} | {ok(kr['band_budget']['ok'])} | **{ok(v['haupt']['bewertung']['bestanden'])}** |")
    a("")
    vorhanden = list(vs[0]["haupt"]["bewertung"]["kriterien"]) if vs else []
    namen = [n for n in KRITERIEN if n in vorhanden] + [n for n in vorhanden if n not in KRITERIEN]
    a(f"Erfüllt je Kriterium (Anzahl Varianten von {len(vs)}):")
    a("")
    a("| " + " | ".join(namen) + " |")
    a("|" + "---|" * len(namen))
    a("| " + " | ".join(str(sum(1 for v in vs if v["haupt"]["bewertung"]["kriterien"][n]["ok"] is True)) for n in namen) + " |")
    a("")
    nb = [v["id"] for v in vs if v["nicht_bewertbar"]]
    if nb:
        a(f"Nicht bewertbar (< 200 Trades und Testfenster ohne zulässige Schwelle): {', '.join(nb)} – zählt als nicht bestanden.")
        a("")
    a("Schwellen wie F-04/F-05 (config/tore.toml [tor_85]). „Zufall“: zufällige Richtung zu denselben, gefilterten Einstiegszeiten mit "
      "kompletter Ausstiegslogik (1.000 Wiederholungen) – der eigentliche Prüfstein dieser Runde. „50-%-Folge“: Ereignisse der 50-%-Regel in "
      "der Tradefolge; „Schatten“: LOSS_LOCK/STOP50 im OOS-Zeitraum (jedes neue Eintreten zählt). „n. b.“ = nicht bewertbar = nicht bestanden.")
    a("")
    a("## Richtungsvorsprung im Datensatz (ohne Konto und Band)")
    a("")
    a("Je handelbarem Entscheidungspunkt im Testzeitraum die Entscheidung der Hülle aus den Datensatz-Merkmalen. „Quote gewählt“ = Anteil "
      "Gewinn (Label) der gewählten Richtung; „Quote Zufall“ = Mittel aus Kauf und Verkauf an denselben Punkten; die Differenz ist der "
      "reine Richtungsvorsprung. Geometrie = Stop/(Stop + Ziel) (bei Zufallsweg ohne Drift die Trefferquote).")
    a("")
    a("| Variante | Punkte | Embargo | ohne Schwelle | unter Schwelle | durchgelassen | Quote gewählt | Quote Zufall | Vorsprung | "
      "Geometrie | Anteil Kauf | wie Basis |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in vs:
        w = v["training"]["wirkung"]
        e = w["entscheidungen"]
        a(f"| {v['id']} | {w['zeilen']} | {e.get('EMBARGO', 0)} | {e.get('KEINE_SCHWELLE', 0)} | {e.get('UNTER_SCHWELLE', 0)} | "
          f"{e.get('HANDELN', 0)} | {p(w['quote_gewaehlt'])} | {p(w['quote_zufall'])} | {z(w['vorsprung_punkte'], 1)} Pkt | "
          f"{p(w['geometrie_mittel'])} | {p(w['anteil_kauf'])} | {p(w['anteil_wie_basis'])} |")
    a("")
    a("## Schwellen d* je Testfenster (innere Validierung)")
    a("")
    a("d* = kleinste Schwelle aus {0,00; 0,05; …; 0,40} für den Vorsprung |p_Kauf − p_Verkauf| mit der höchsten Wilson-95-%-Untergrenze der "
      "Validierungs-Trefferquote der gewählten Richtung (mindestens 50 Validierungssignale über der Schwelle); „–“ = keine zulässige Schwelle.")
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
    a("Modell-Parität (Standardbibliothek gegen scikit-learn, größte Abweichung über alle Zeilen, Fenster und beide Modelle): " +
      ", ".join(f"{v['id']} {v['training']['paritaet_max']:.1e}" for v in vs) + ".")
    a("")
    a("## Band-Wirkung und Quote Signal → Trade (Takt)")
    a("")
    a("| Variante | Signale | Trades | Signal→Trade | Hebel min/Ø/max | Ablehnungen (häufigste) |")
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
    a("Die Modelle sind auf dem Hauptprofil trainiert und bleiben in allen Profilen gleich. Im Profil „Kosten × 1,5“ sehen Ask-Einstieg, "
      "gespiegelte Abstände, die Prüfung „handelbar“ und das Merkmal Spread/ATR den verschärften Spread: Die Hülle wählt dort andere Punkte "
      "und Richtungen (keine reine Kostenverschärfung derselben Trades).")
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
    a("| Variante | Technik gültig | Signal-Parität (gleich; Takt/direkt) | Trade-Parität (geprüft, Zwang) | Datensatz-Parität | offen am Ende |")
    a("|---|---|---|---|---|---|")
    for v in vs:
        e = v["haupt"]
        pt, ps = e["paritaet"]["trades"], e["paritaet"]["signale"]
        dp = v["training"].get("datensatz_paritaet") or {}
        a(f"| {v['id']} | {ok(e['bewertung']['kriterien']['technik']['ok'])} | {p(ps['quote'], 2)} ({ps['gleich']}; {ps['takt']}/{ps['direkt']}) | "
          f"{p(pt['quote'], 2)} ({pt['geprueft']}, {pt['zwangsausstiege']}) | {p(dp.get('quote'), 2)} | {e['offen_am_ende']} |")
    a("")
    a("## Daten und Verfahren")
    a("")
    a(f"Kerzen: genau die Abzüge der F-04-Datensicht (seq {b['daten']['f04_datensicht_seq']}, Zeitbasis W1). Datensätze (Datensicht F-05b, "
      f"seq {b['daten']['datensicht_seq']}): " + "; ".join(
          f"{bid}: {d['zaehlung'].get('zeilen')} handelbare Punkte (von {d['zaehlung'].get('basissignale')} Basissignalen; nicht handelbar "
          f"{d['zaehlung'].get('nicht_handelbar', 0)}, ohne Merkmale {d['zaehlung'].get('ohne_merkmale', 0)}; davon am Datenende offen "
          f"{d['zaehlung'].get('offen', 0)})" for bid, d in b["daten"]["datensaetze"].items()) +
      ". Je Punkt zwei Labels (Kauf, Verkauf) zu denselben Abständen über die direkte Ausstiegsrechnung des Takts (Hauptprofil, 1 Lot).")
    a("")
    a("Walk-Forward wie F-04/F-05; Purge: beide Label-Ausstiege bis zum Ende der Menge; Embargo 5 Handelstage. Je Fenster ein Kauf- und ein "
      "Verkaufsmodell mit Trainingsgrenzen; die Hülle verweigert Modelle, deren Daten ins Testfenster reichen. Vor 2013 handelt sie nicht.")
    a("")
    a("## Grenzen dieser Auswertung")
    a("")
    for g in GRENZEN:
        a(f"- {g}")
    a("")
    a("Einordnung: " + b["einordnung"])
    a("")
    return "\n".join(zeilen)


KRITERIEN = ("trades", "quote", "erwartung_r", "gewinnfaktor", "verlust_zu_gewinn", "zufallsbasis", "drawdown", "stop50", "band_budget",
             "technik")
GRENZEN = (
    *entwicklung.GRENZEN[:5],
    "Im Profil „Kosten × 1,5“ wählt die Hülle andere Punkte und Richtungen (Spread/ATR, Einstieg und „handelbar“ sehen den verschärften "
    "Spread).",
    "Die Modelle lernen aus 3 Jahren handelbarer Punkte je Fenster (S-REV-02: H4, deutlich weniger); die Schwelle wählt die innere "
    "Validierung aus einem einzigen Jahr – das Ergebnis schwankt entsprechend.",
    "Die Basisvarianten wurden nach den Ergebnissen der Runden 1 und 2 auf denselben Testjahren gewählt; die DSR zählt nur die 4 Versuche "
    "der Familie F05B-RICHTUNG und ist damit eher zu günstig.",
    "Stunde und Wochentag stehen auf der Zeitbasis W1 (im US-Winter 1 h gegen Berlin verschoben), der H4-Spread folgt der Backtest-Regel.",
    "Feiertage außer 1.1. und 25.12. zählen im Embargo als Handelstage.",
    "Das Holdout-Modell ist nur eingefroren; es wird nur mit einem Kandidaten und nach eigener Vorregistrierung im Holdout geprüft.",
)
