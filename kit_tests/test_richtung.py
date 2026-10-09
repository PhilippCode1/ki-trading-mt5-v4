"""Richtungsmodell F-05b (kit/strategy/richtung.py, kit/research/richtung.py) ohne scikit-learn: gespiegelte SL/TP per Handrechnung
(auch JPY), Prüfung „handelbar“ wie im Takt (Handelsfenster, Stop ≤ 3 × Ziel nach Rundung, auch bei Kursen unter dem Raster),
Entscheidungen der Hülle, Modellbindung beider Modelle, verlustfreie kompakte Speicherung, Purge über beide Ausstiege, Signal-, Trade-
und Datensatz-Parität im Takt und die Zufallspfad-Gegenprobe (Prereg F05B §3). Synthetische Kurse, keine Marktdaten."""
from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import replace
from decimal import Decimal

import pytest

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt, zufallspaar
from kit.backtest.kosten import Kostenprofil
from kit.domain.types import Bar, Side
from kit.gates import trade_test as tt
from kit.research import meta
from kit.research import richtung as ri
from kit.strategy import meta_filter as mf
from kit.strategy import richtung as rf
from kit.strategy.base import Signal
from kit_tests import backtest_hilfen as bh

D = Decimal
UTC = dt.UTC
KONF = runner.bot_konfiguration()


def utc(*a) -> int:
    return int(dt.datetime(*a, tzinfo=UTC).timestamp())


def _lr(namen, koef, achse=0.0, training=None) -> dict:
    n = len(namen)
    return {"art": "LOGREG", "merkmale": list(namen), "mittel": [0.0] * n, "skala": [1.0] * n, "koeffizienten": list(koef),
            "achsenabschnitt": achse, "training": training or {"fit_bis": 0, "max_t_ent": -1, "max_t_exit": 0, "val_max_t_exit": 0,
                                                                 "val_von": -1}}


class Fest:
    """Basis ohne Idee: Signal an jeder Kerze (Richtung abwechselnd), Ziel/Stop in Ticks um den Einstieg der Basis."""

    name, rueckblick, symbole, max_halte_s = "TEST-FEST", 250, ("EURUSD",), 6 * 3600.0
    L = 20

    def __init__(self, ziel: int = 100, stop: int = 150, zeitrahmen: str = "H1", symbole=("EURUSD",)) -> None:
        self.ziel, self.stop, self.zeitrahmen, self.symbole = ziel, stop, zeitrahmen, tuple(symbole)

    def parameter(self) -> dict:
        return {"ziel": self.ziel, "stop": self.stop}

    def signal(self, symbol, kerzen):
        k = kerzen[-1]
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        p = D("0.001") if symbol.endswith("JPY") else D("0.00001")
        e = rf.einstieg(k, side)
        return Signal(symbol, side, e - side.sign * self.stop * p, e + side.sign * self.ziel * p, k.time, "fest")


# ---------------------------------------------------------------------------------------------------- Spiegeln, handelbar
@pytest.mark.parametrize("symbol,p", [("EURUSD", D("0.00001")), ("USDJPY", D("0.001"))])
def test_spiegeln_gleiche_abstaende_um_den_einstieg_der_richtung(symbol, p):
    k = Bar(symbol, utc(2015, 7, 6, 10), D("1.10000") if symbol == "EURUSD" else D("110.000"), D("1.10300") if symbol == "EURUSD"
            else D("110.300"), D("1.09800") if symbol == "EURUSD" else D("109.800"), D("1.10100") if symbol == "EURUSD" else D("110.100"), 12)
    for basis_side in (Side.BUY, Side.SELL):
        e = rf.einstieg(k, basis_side)
        sig = Signal(symbol, basis_side, e - basis_side.sign * 300 * p, e + basis_side.sign * 100 * p, k.time, "b")
        assert rf.abstaende(sig, k) == (100 * p, 300 * p)
        kauf, verkauf = rf.spiegeln(sig, k, Side.BUY), rf.spiegeln(sig, k, Side.SELL)
        ask, bid = k.close + 12 * p, k.close
        assert (kauf.side, kauf.tp, kauf.sl) == (Side.BUY, ask + 100 * p, ask - 300 * p)
        assert (verkauf.side, verkauf.tp, verkauf.sl) == (Side.SELL, bid - 100 * p, bid + 300 * p)
        assert rf.spiegeln(sig, k, basis_side) == replace(sig, grund=f"{sig.grund} R")       # eigene Richtung unverändert


def _takt_prueft(sig: Signal, preis: Decimal) -> bool:
    """Stop/Ziel-Prüfung genau wie kit.run.loop.Bot.einstieg_strategie (gerundete SL/TP gegen den Kurs)."""
    from kit.backtest.terminal import vertrag
    from kit.domain import rounding
    spec = vertrag(sig.symbol)
    sl, tp = rounding.sl_runden(sig.sl, sig.side, spec), rounding.tp_runden(sig.tp, sig.side, spec)
    return not abs(preis - sl) > D(3) * abs(tp - preis)


def test_stop_ziel_wie_im_takt_auch_unter_dem_raster():
    """Befund F-05: frühe EURUSD/GBPUSD-Kerzen haben eine Stelle mehr als das Raster; der Takt rundet SL/TP und lehnt dann Stop = 3 × Ziel
    knapp ab. Die Hülle prüft genauso."""
    t = utc(2015, 7, 6, 10)
    rng = random.Random(3)
    faelle = 0
    for _ in range(400):
        close = D("1.1") + D(rng.randint(0, 99999)) * D("0.000001")                  # 6 Stellen: unter dem Raster
        k = Bar("EURUSD", t, close, close, close, close, rng.randint(0, 20))
        for side in (Side.BUY, Side.SELL):
            e = rf.einstieg(k, side)
            sig = Signal("EURUSD", side, e - side.sign * D("0.00300"), e + side.sign * D("0.00100"), t, "r3")
            assert rf.stop_ziel_ok(sig, k, D(3)) == _takt_prueft(sig, e)
            faelle += int(not rf.stop_ziel_ok(sig, k, D(3)))
    assert faelle > 50                                                                # der Randfall kommt wirklich vor
    k = Bar("EURUSD", t, D("1.10000"), D("1.10000"), D("1.10000"), D("1.10000"), 5)  # auf dem Raster: genau 3 × Ziel ist erlaubt
    sig = Signal("EURUSD", Side.BUY, rf.einstieg(k, Side.BUY) - D("0.00300"), rf.einstieg(k, Side.BUY) + D("0.00100"), t, "r3")
    assert rf.stop_ziel_ok(sig, k, D(3)) and _takt_prueft(sig, rf.einstieg(k, Side.BUY))


def test_handelbar_nur_im_handelsfenster_und_mit_stop_bis_drei_ziel():
    k = Bar("EURUSD", utc(2015, 7, 6, 9), D("1.10000"), D("1.10100"), D("1.09900"), D("1.10000"), 5)   # Mo 11:00 Berlin
    sig = Fest(100, 300).signal("EURUSD", [k])
    kauf, verkauf = rf.spiegeln(sig, k, Side.BUY), rf.spiegeln(sig, k, Side.SELL)
    assert rf.handelbar(k.time + 3600, kauf, verkauf, k, KONF, D(3))
    assert not rf.handelbar(utc(2015, 7, 6, 23), kauf, verkauf, k, KONF, D(3))      # Nacht: außerhalb des Fensters
    weit = Fest(100, 301).signal("EURUSD", [k])
    assert not rf.handelbar(k.time + 3600, rf.spiegeln(weit, k, Side.BUY), rf.spiegeln(weit, k, Side.SELL), k, KONF, D(3))


# ---------------------------------------------------------------------------------------------------- Hülle
def _modelle(art="REV01", kauf_achse=0.5, verkauf_achse=0.0, training=None):
    namen = mf.merkmal_namen(art)
    return _lr(namen, [0.0] * len(namen), kauf_achse, training), _lr(namen, [0.0] * len(namen), verkauf_achse, training)


def test_huelle_waehlt_die_besser_geschaetzte_richtung_bei_vorsprung():
    alle = bh.h1_reihe("EURUSD", stunden=24 * 7 * 7, saat=4)
    i = max(j for j in range(mf.FENSTER, len(alle)) if alle[j].time == utc(2015, 2, 17, 9))     # Di 10:00 Berlin, Signal 11:00
    kerzen = alle[:i + 1]
    k = kerzen[-1]
    t_ent = k.time + 3600
    mk, mv = _modelle()                                            # p_Kauf = σ(0,5) ≈ 0,62, p_Verkauf = 0,5 → Vorsprung ≈ 0,12
    def h(*fenster, basis=None):
        return rf.Richtungsfilter(basis or Fest(), list(fenster), art="REV01", name="T", konf=KONF, stop_ziel_max="3")
    assert h().bewerten("EURUSD", kerzen)[3] == "KEIN_FENSTER"
    assert h(rf.Fenster(t_ent - 10, None, t_ent + 1, 0.0, mk, mv)).bewerten("EURUSD", kerzen)[3] == "EMBARGO"
    assert rf.handelbar(t_ent, *(rf.spiegeln(Fest().signal("EURUSD", kerzen), k, s) for s in (Side.BUY, Side.SELL)), k, KONF, D(3))
    sig, pk, pv, e = h(rf.Fenster(t_ent - 1, None, t_ent, 0.10, mk, mv)).bewerten("EURUSD", kerzen)
    assert e == "HANDELN" and sig.side is Side.BUY and pk > pv and abs(pk - pv) > 0.10
    assert sig == rf.spiegeln(Fest().signal("EURUSD", kerzen), k, Side.BUY)              # SL/TP der Kaufrichtung
    assert h(rf.Fenster(t_ent - 1, None, t_ent, 0.15, mk, mv)).bewerten("EURUSD", kerzen)[3] == "UNTER_SCHWELLE"
    mk2, mv2 = _modelle(kauf_achse=0.0, verkauf_achse=0.5)
    verkauf = h(rf.Fenster(t_ent - 1, None, t_ent, 0.10, mk2, mv2)).signal("EURUSD", kerzen)
    assert verkauf.side is Side.SELL and verkauf == rf.spiegeln(Fest().signal("EURUSD", kerzen), k, Side.SELL)
    assert h(rf.Fenster(t_ent - 1, None, t_ent, None, mk, mv)).bewerten("EURUSD", kerzen)[3] == "KEINE_SCHWELLE"
    with pytest.raises(ValueError, match="gemeinsam"):
        h(rf.Fenster(0, None, 1, 0.1, mk, None))
    with pytest.raises(ValueError, match="Testfenster"):
        h(rf.Fenster(0, None, 1, 0.1, mk, mv | {"training": {**mv["training"], "max_t_exit": 5}}))    # Verkaufsmodell sieht Testdaten


def test_entscheidungen_ueber_einen_tag_handelbar_und_nacht():
    """Über volle Tage: in der Nacht NICHT_HANDELBAR, im Handelsfenster HANDELN – die Hülle entscheidet nur an handelbaren Punkten."""
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 7, saat=6)
    mk, mv = _modelle()
    h = rf.Richtungsfilter(Fest(), [rf.Fenster(0, None, 1, 0.05, mk, mv)], art="REV01", name="T", konf=KONF, stop_ziel_max="3")
    ergebnisse = {h.bewerten("EURUSD", kerzen[:i])[3] for i in range(len(kerzen) - 48, len(kerzen))}
    assert ergebnisse == {"HANDELN", "NICHT_HANDELBAR"}


def test_kompakte_speicherung_ist_verlustfrei():
    rng = random.Random(1)
    knoten = []
    for i in range(15):
        blatt = i >= 7
        knoten.append([rng.uniform(-1, 1), 0 if blatt else rng.randint(0, 14), 0.0 if blatt else rng.uniform(-3, 3), rng.random() < 0.5,
                       0 if blatt else 2 * i + 1, 0 if blatt else 2 * i + 2, blatt])
    hgb = {"art": "HGB", "merkmale": list(mf.MERKMALE), "basis": -0.3, "baeume": [knoten] * 3, "training": {"fit_bis": 0}}
    gepackt = rf.packen(hgb)
    assert "baeume" not in gepackt and rf.rechengleich(hgb, rf.entpacken(json.loads(json.dumps(gepackt))))
    assert len(json.dumps(gepackt)) < 0.75 * len(json.dumps(hgb))
    x = [rng.uniform(-3, 3) for _ in range(15)]
    assert mf.wahrscheinlichkeit(hgb, x) == mf.wahrscheinlichkeit(rf.entpacken(gepackt), x)
    lr = _lr(mf.MERKMALE, [0.1] * 15)
    assert rf.packen(lr) is lr and rf.entpacken(lr) is lr
    anders = rf.entpacken(gepackt) | {"basis": -0.31}
    assert not rf.rechengleich(hgb, anders)


# ---------------------------------------------------------------------------------------------------- Purge beider Ausstiege
def test_purge_ueber_beide_ausstiege_und_trainer_mutation():
    rng = random.Random(2)
    zeilen = []
    for _ in range(5000):
        t = rng.randrange(utc(2010, 1, 1), utc(2021, 7, 1)) // 3600 * 3600
        ek, ev = t + rng.choice((3600, 86400, 3 * 86400)), t + rng.choice((3600, 86400, 3 * 86400))
        zeilen.append({"t_ent": t, "label_k": rng.randint(0, 1), "label_v": rng.randint(0, 1), "t_exit_k": ek, "t_exit_v": ev,
                       "t_exit": max(ek, ev), "x": [0.0] * 15})
    zeilen.sort(key=lambda z: z["t_ent"])
    plan = meta.plan()
    for f in plan:
        for z in ri.menge(zeilen, f["fit_von"], f["test_von"]):
            assert z["t_exit_k"] <= f["test_von"] and z["t_exit_v"] <= f["test_von"]
    def datei(mengen_fn):
        fenster = []
        for f in plan:
            def g(zs):
                return {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None),
                        "max_t_ent": max((z["t_ent"] for z in zs), default=None), "max_t_exit": max((z["t_exit"] for z in zs), default=None)}
            innen, val, final = (mengen_fn(zeilen, f["fit_von"], f["val_von"]), mengen_fn(zeilen, f["val_von"], f["test_von"]),
                                 mengen_fn(zeilen, f["fit_von"], f["test_von"]))
            tr = {"fit_von": f["fit_von"], "fit_bis": f["test_von"], "n": len(final), "max_t_exit": g(final)["max_t_exit"],
                  "max_t_ent": g(final)["max_t_ent"], "val_max_t_exit": g(val)["max_t_exit"], "val_von": f["val_von"]}
            fenster.append({**{k: f[k] for k in ri.PLAN_SCHLUESSEL}, "grenzen": {"innen": g(innen), "validierung": g(val), "final": g(final)},
                            "modell_kauf": {"training": tr}, "modell_verkauf": {"training": tr}})
        return {"fenster": fenster[:-1], "holdout": fenster[-1]}
    assert ri.purge_pruefen(datei(ri.menge), zeilen, plan) == []
    nur_kauf = datei(lambda z, von, bis: [x for x in z if von <= x["t_ent"] < bis and x["t_exit_k"] <= bis])   # Mutation: Purge nur Kauf
    assert {b.split(":")[0] for b in ri.purge_pruefen(nur_kauf, zeilen, plan)} >= {"anzahl", "grenze", "modellgrenze"}
    kurz = datei(ri.menge)
    kurz["fenster"][0]["embargo_bis"] = plan[0]["test_von"] + 3600
    assert ri.purge_pruefen(kurz, zeilen, plan) == ["plan:Fenster der Modelldatei weichen vom registrierten Plan ab",
                                                    f"embargo:{plan[0]['test_von']}"]
    luecke = datei(ri.menge)
    del luecke["fenster"][2]
    assert ri.purge_pruefen(luecke, zeilen, plan)[0].startswith("plan:")
    ohne = datei(ri.menge)
    del ohne["holdout"]["grenzen"]
    assert {b.split(":")[0] for b in ri.purge_pruefen(ohne, zeilen, plan)} == {"grenzen_fehlen", "modellgrenze"}
    ungleich = datei(ri.menge)
    ungleich["fenster"][1]["modell_verkauf"] = {"training": {**ungleich["fenster"][1]["modell_kauf"]["training"], "n": 1}}
    assert any(b.startswith("modellgrenze:modell_verkauf") for b in ri.purge_pruefen(ungleich, zeilen, plan))
    assert any(b.startswith("modellgrenze:kauf_verkauf_ungleich") for b in ri.purge_pruefen(ungleich, zeilen, plan))


def test_wirkung_zaehlt_gewaehlte_richtung_gegen_zufall_per_handrechnung():
    namen = mf.MERKMALE
    mk, mv = _lr(namen, [0.0] * 15, 1.0), _lr(namen, [0.0] * 15, 0.0)              # Kauf geschätzt besser (0,73 gegen 0,5)
    koef = [0.0] * 15
    koef[0] = 5.0
    mk2 = _lr(namen, koef, 0.0)                                                        # Fenster 2: Kauf nur bei x0 > 0
    t0, t1 = utc(2015, 1, 1), utc(2015, 2, 1)
    h = rf.Richtungsfilter(Fest(), [rf.Fenster(t0, t1, t0 + 86400, 0.10, mk, mv), rf.Fenster(t1, None, t1 + 86400, 0.10, mk2, mv)],
                           art="REV01", name="T", konf=KONF, stop_ziel_max="3")
    def z(t, x0, lk, lv, basis="SELL", geo=0.75):
        return {"t_ent": t, "x": [x0] + [0.0] * 14, "label_k": lk, "label_v": lv, "basis_side": basis, "geometrie": geo}
    zeilen = [z(t0 + 3600, 0.0, 1, 0), z(t0 + 2 * 86400, 0.0, 1, 0), z(t0 + 3 * 86400, 0.0, 0, 1, "BUY"),
              z(t1 + 2 * 86400, 1.0, 1, 1), z(t1 + 3 * 86400, -1.0, 0, 1, geo=0.5), z(t1 + 4 * 86400, 0.01, 1, 0)]
    w = ri.wirkung(zeilen, h, [(t0, utc(2015, 3, 1))])
    # Zeile 1 Embargo; 2, 3 Kauf (Vorsprung 0,23); 4 Kauf (x0 = 1); 5 Verkauf (p_K = σ(−5)); 6 Vorsprung 0,0125 < 0,10
    assert w["entscheidungen"] == {"EMBARGO": 1, "HANDELN": 4, "UNTER_SCHWELLE": 1} and w["durchgelassen_mit_label"] == 4
    assert w["quote_gewaehlt"] == 3 / 4 and w["quote_zufall"] == (0.5 + 0.5 + 1 + 0.5) / 4
    assert w["vorsprung_punkte"] == pytest.approx(100 * (3 - 2.5) / 4) and w["anteil_kauf"] == 3 / 4
    assert w["anteil_wie_basis"] == 2 / 4 and w["geometrie_mittel"] == pytest.approx((0.75 * 3 + 0.5) / 4)


# ---------------------------------------------------------------------------------------------------- Takt: Parität, Zufallspfad
def _modell_zufaellig(namen, saat):
    """Richtung ohne Information: Koeffizienten zufällig auf Stunde/Wochentag – die Wahl ist vom Kurs unabhängig."""
    rng = random.Random(saat)
    koef = [0.0] * len(namen)
    for i in range(8, len(namen)):
        koef[i] = rng.uniform(-2, 2)
    return _lr(namen, koef, 0.0)


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_paritaet_der_huelle_im_takt_und_datensatz(tf, tmp_path):
    h1 = bh.markt(("EURUSD",), wochen=26, saat=8, sigma=0.0025)
    h4 = {"EURUSD": bh.verdichten(h1["EURUSD"], 14400)}
    basis = Fest(120, 300, tf)
    art = "REV02" if tf == "H4" else "REV01"
    namen = mf.merkmal_namen(art)
    profil = Kostenprofil("t", D(0))
    markt = Markt(h1, profil)
    kerzen = meta.takt_kerzen(h1, h4, tf, profil)
    zeilen, zaehlung = ri.datensatz(basis, art, kerzen, markt, KONF)
    assert zaehlung["nicht_handelbar"] > 0 and len(zeilen) >= 10
    koef = [0.0] * len(namen)
    koef[4] = -40.0                                                    # Spread/ATR entscheidet mit (falscher Spread kippt)
    mk = _lr(namen, koef, 0.4)
    mv = _modell_zufaellig(namen, 3)
    h = rf.Richtungsfilter(basis, [rf.Fenster(0, None, 1, 0.0, mk, mv)], art=art, name="T", konf=KONF, stop_ziel_max="3")
    erg = runner.laufen(h, h1, tmp_path / "a", runner.Einstellungen(profil), tf_kerzen=h4 if tf == "H4" else None)
    sp = paritaet.signal_paritaet(erg.signale, h, kerzen, markt.schritte)
    assert sp["quote"] == 1.0 and sp["takt"] > 0
    assert paritaet.trade_paritaet(erg.details, markt, h.max_halte_s)["quote"] == 1.0 and erg.technik_ok
    dp = ri.datensatz_paritaet(zeilen, h, [[s["symbol"], s["kerze"], s["side"]] for s in erg.signale])
    assert dp["quote"] == 1.0 and dp["takt"] == sp["takt"]
    assert {s["side"] for s in erg.signale} == {"BUY", "SELL"}
    _seite_passt_zum_label(zeilen, erg)


def _seite_passt_zum_label(zeilen, erg) -> None:
    """Die gehandelte Richtung trägt SL/TP und Label ihrer Seite im Datensatz (Kauf: _k, Verkauf: _v) – sichert die Zuordnung
    Kauf-Label → Kauf-Modell → BUY-Order gegen Vertauschung (Profil ohne Kommission und Swap: Vorzeichen gleich)."""
    nach_zeit = {(z["symbol"], z["t_ent"]): z for z in zeilen}
    assert erg.details
    for d in erg.details:
        z = nach_zeit[(d.symbol, d.t_auf)]
        s = "k" if d.side is Side.BUY else "v"
        assert (D(z[f"sl_{s}"]), D(z[f"tp_{s}"])) == (d.sl, d.tp)
        if d.grund in ("SL", "TP", "ZEITBARRIERE") and z[f"label_{s}"] is not None:
            assert z[f"label_{s}"] == int(d.ergebnis > 0), (d.symbol, d.t_auf, d.side)


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_paritaet_mit_kursen_unter_dem_raster_und_stop_gleich_drei_ziel(tf, tmp_path):
    """Befund F-05: Kurse mit einer Stelle mehr als das Raster und Stop = 3 × Ziel (wie S-REV-01). Die Hülle lässt nur Punkte durch, die
    der Takt nicht mit STOP_ZU_ZIEL ablehnt; Labels und gehandelte Trades bleiben gleich."""
    roh = bh.markt(("EURUSD",), wochen=26, saat=14, sigma=0.0025)["EURUSD"]
    feiner = [replace(b, open=b.open + D("0.000003") * (i % 7), high=b.high + D("0.000006"), low=b.low,
                      close=b.close + D("0.000003") * (i % 7)) for i, b in enumerate(roh)]
    h1 = {"EURUSD": [replace(b, high=max(b.high, b.open, b.close), low=min(b.low, b.open, b.close)) for b in feiner]}
    h4 = {"EURUSD": bh.verdichten(h1["EURUSD"], 14400)}
    basis = Fest(100, 300, tf)
    art = "REV02" if tf == "H4" else "REV01"
    namen = mf.merkmal_namen(art)
    profil = Kostenprofil("t", D(0))
    markt = Markt(h1, profil)
    kerzen = meta.takt_kerzen(h1, h4, tf, profil)
    zeilen, zaehlung = ri.datensatz(basis, art, kerzen, markt, KONF)
    stop_regel = 0
    for b in kerzen["EURUSD"]:
        sig = basis.signal("EURUSD", [b])
        kauf, verkauf = rf.spiegeln(sig, b, Side.BUY), rf.spiegeln(sig, b, Side.SELL)
        stop_regel += int(not (rf.stop_ziel_ok(kauf, b, D(3)) and rf.stop_ziel_ok(verkauf, b, D(3))))
    assert stop_regel > 20 and zaehlung["nicht_handelbar"] > 0 and len(zeilen) >= 10
    h = rf.Richtungsfilter(basis, [rf.Fenster(0, None, 1, 0.0, _modell_zufaellig(namen, 5), _modell_zufaellig(namen, 6))], art=art,
                           name="T", konf=KONF, stop_ziel_max="3")
    erg = runner.laufen(h, h1, tmp_path / "r", runner.Einstellungen(profil), tf_kerzen=h4 if tf == "H4" else None)
    assert not any(s["grund"] == "STOP_ZU_ZIEL" for s in erg.signale)
    assert paritaet.signal_paritaet(erg.signale, h, kerzen, markt.schritte)["quote"] == 1.0
    assert paritaet.trade_paritaet(erg.details, markt, h.max_halte_s)["quote"] == 1.0 and erg.technik_ok
    assert ri.datensatz_paritaet(zeilen, h, [[s["symbol"], s["kerze"], s["side"]] for s in erg.signale])["quote"] == 1.0
    _seite_passt_zum_label(zeilen, erg)


def test_nur_die_verkaufsrichtung_verletzt_die_rundungsregel():
    t = utc(2015, 7, 6, 9)
    for close in (D("1.1") + D(i) * D("0.000001") for i in range(1, 2000)):
        k = Bar("EURUSD", t, close, close, close, close, 0)
        sig = Fest(100, 300).signal("EURUSD", [k])
        kauf, verkauf = rf.spiegeln(sig, k, Side.BUY), rf.spiegeln(sig, k, Side.SELL)
        if rf.stop_ziel_ok(kauf, k, D(3)) and not rf.stop_ziel_ok(verkauf, k, D(3)):
            assert not rf.handelbar(t + 3600, kauf, verkauf, k, KONF, D(3))
            assert not _takt_prueft(verkauf, rf.einstieg(k, Side.SELL)) and _takt_prueft(kauf, rf.einstieg(k, Side.BUY))
            return
    raise AssertionError("kein Fall gefunden, in dem nur der Verkauf die Regel verletzt")


def test_zufallspfad_gegenprobe_keine_quote_ueber_der_zufallsbasis(tmp_path):
    """Prereg F05B §3: Auf einem Zufallspfad ohne Richtungsinformation wählt die Hülle die Richtung vom Kurs unabhängig; ihre Quote liegt
    beim Zufallsmittel, und das Kriterium „Quote > 95. Perzentil der Zufallsbasis“ ist nicht erfüllt."""
    h1 = bh.markt(("EURUSD",), wochen=40, saat=12, sigma=0.002)
    basis = Fest(100, 150)
    namen = mf.merkmal_namen("REV01")
    h = rf.Richtungsfilter(basis, [rf.Fenster(0, None, 1, 0.0, _modell_zufaellig(namen, 1), _modell_zufaellig(namen, 2))], art="REV01",
                           name="T", konf=KONF, stop_ziel_max="3")
    profil = Kostenprofil("t", D(0))
    erg = runner.laufen(h, h1, tmp_path / "z", runner.Einstellungen(profil))
    markt = Markt(h1, profil)
    zufall = [zufallspaar(markt, d.symbol, d.t_auf, abs(d.preis_auf - d.sl), abs(d.tp - d.preis_auf), d.lots, h.max_halte_s)
              for d in erg.details]
    assert len(erg.trades) >= 150
    z = tt.zufallsbasis(zufall, 1000, 4042, "95")
    quote = sum(1 for t in erg.trades if t.gewinn) / len(erg.trades)
    assert abs(quote - z["mittel"]) < 0.05 and not quote > z["p95"]
