"""KI-Meta-Filter F-05 (kit/strategy/meta_filter.py, kit/research/meta.py) ohne scikit-learn: Merkmale gegen eine unabhängige
Rechnung, Modelle aus JSON, Entscheidungen der Hülle, Schwellenregel, Purge und Embargo über den echten Plan, Kerzen wie im Takt
und Signal-Parität der Hülle im Takt (synthetische Kurse, keine Marktdaten)."""
from __future__ import annotations

import datetime as dt
import math
import random
import statistics
from dataclasses import replace
from decimal import Decimal

import pytest

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt
from kit.backtest.kosten import Kostenprofil
from kit.backtest.terminal import BacktestTerminal
from kit.broker.sim import Uhr
from kit.domain.types import Bar, Side
from kit.research import meta, stats
from kit.strategy import meta_filter as mf
from kit.strategy.base import Signal
from kit.strategy.rev import Fehlausbruch, MittelwertRueckkehr
from kit_tests import backtest_hilfen as bh

D = Decimal
UTC = dt.UTC


def utc(*a) -> int:
    return int(dt.datetime(*a, tzinfo=UTC).timestamp())


# ---------------------------------------------------------------------------------------------------- Merkmale
def _wilder(kerzen, n=14):
    trs, vor, atr, out = [], None, None, []
    for b in kerzen:
        h, lo, c = float(b.high), float(b.low), float(b.close)
        tr = h - lo if vor is None else max(h - lo, abs(h - vor), abs(lo - vor))
        vor = c
        if atr is None:
            trs.append(tr)
            atr = statistics.fmean(trs) if len(trs) == n else None
        else:
            atr = (atr * (n - 1) + tr) / n
        out.append(atr)
    return out


def _erwartet(k, side, art, spanne_l=None):
    """Unabhängige Rechnung der Prereg-Merkmale (statistics, eigene ATR) für die letzten FENSTER Kerzen."""
    k = k[-mf.FENSTER:]
    atr = _wilder(k)
    a = atr[-1]
    c = [float(b.close) for b in k]
    sma = statistics.fmean(c[-48:])
    sig = statistics.pstdev(c[-48:])
    t = k[-1]
    hoch, tief = max(float(b.high) for b in k[-20:]), min(float(b.low) for b in k[-20:])
    lokal = dt.datetime.fromtimestamp(t.time, UTC) + (dt.timedelta(hours=2) if _sommer(t.time) else dt.timedelta(hours=1))
    x = [(c[-1] - sma) / sig, sig / a, a / c[-1], sum(v <= a for v in atr[-250:]) / 250,
         t.spread_points * (0.001 if t.symbol.endswith("JPY") else 0.00001) / a, (c[-1] - c[-25]) / a,
         (sma - statistics.fmean(c[-60:-12])) / a, (c[-1] - tief) / (hoch - tief),
         math.sin(2 * math.pi * lokal.hour / 24), math.cos(2 * math.pi * lokal.hour / 24),
         *[1.0 if lokal.weekday() == i else 0.0 for i in range(5)]]
    if art == "REV02":
        spanne = k[-spanne_l - 1:-1]
        tiefe = float(t.high) - max(float(b.high) for b in spanne) if side is Side.SELL else min(float(b.low) for b in spanne) - float(t.low)
        x += [tiefe / a, (float(t.high) - float(t.low)) / a]
    return x


def _sommer(t: int) -> bool:
    d = dt.datetime.fromtimestamp(t, UTC)
    def letzter_sonntag(m):
        tag = dt.datetime(d.year, m, 31, 1, tzinfo=UTC)
        return tag - dt.timedelta(days=(tag.weekday() + 1) % 7)
    return letzter_sonntag(3) <= d < letzter_sonntag(10)


@pytest.mark.parametrize("art", ["REV01", "REV02"])
def test_merkmale_gegen_unabhaengige_rechnung(art):
    kerzen = bh.h1_reihe("USDJPY", stunden=24 * 7 * 10, saat=5)
    assert len(kerzen) > mf.FENSTER + 30
    for ende in (mf.FENSTER, mf.FENSTER + 7, len(kerzen)):
        for side in (Side.BUY, Side.SELL):
            x = mf.merkmale(kerzen[:ende], side, art, spanne_l=20)
            assert len(x) == len(mf.merkmal_namen(art))
            assert x == pytest.approx(_erwartet(kerzen[:ende], side, art, 20), rel=1e-9, abs=1e-12)
    assert mf.merkmale(kerzen[:mf.FENSTER - 1], Side.BUY, art, spanne_l=20) is None


def test_merkmale_zeit_berlin_sommer_winter_und_wochenende():
    basis = bh.h1_reihe("EURUSD", stunden=24 * 7 * 6, saat=2)[:mf.FENSTER]
    letzte = basis[-1]
    for t, stunde, wt in ((utc(2015, 7, 6, 10), 12, 0), (utc(2015, 12, 4, 10), 11, 4), (utc(2015, 3, 29, 0), 1, None),
                          (utc(2015, 3, 29, 1), 3, None), (utc(2015, 10, 25, 1), 2, None)):
        k = [*basis[:-1], replace(letzte, time=t)]
        x = mf.merkmale(k, Side.BUY, "REV01")
        assert x[8] == pytest.approx(math.sin(2 * math.pi * stunde / 24)) and x[9] == pytest.approx(math.cos(2 * math.pi * stunde / 24))
        assert x[10:15] == ([0.0] * 5 if wt is None else [1.0 if i == wt else 0.0 for i in range(5)])    # Sonntag → alle 0


def test_merkmale_ausbruchstiefe_richtung_und_nullvola():
    k = bh.h1_reihe("EURUSD", stunden=24 * 7 * 6, saat=3)[:mf.FENSTER]
    t = k[-1]
    hoch = max(b.high for b in k[-21:-1])
    tief = min(b.low for b in k[-21:-1])
    k_sell = [*k[:-1], replace(t, high=hoch + D("0.00050"), low=t.low, close=hoch - D("0.00010"))]
    k_buy = [*k[:-1], replace(t, low=tief - D("0.00030"), high=t.high, close=tief + D("0.00010"))]
    a_sell = mf.merkmale(k_sell, Side.SELL, "REV02", spanne_l=20)
    a_buy = mf.merkmale(k_buy, Side.BUY, "REV02", spanne_l=20)
    assert a_sell[15] == pytest.approx(0.0005 / _wilder(k_sell)[-1]) and a_buy[15] == pytest.approx(0.0003 / _wilder(k_buy)[-1])
    flach = [Bar("EURUSD", b.time, D("1.1"), D("1.1"), D("1.1"), D("1.1"), 2) for b in k]
    assert mf.merkmale(flach, Side.BUY, "REV01") is None                                  # ATR 0 → keine Merkmale
    with pytest.raises(ValueError):
        mf.merkmale(k, Side.BUY, "REV02")                                                  # REV02 braucht die Spannenlänge


# ---------------------------------------------------------------------------------------------------- Modelle aus JSON
def _lr(namen, koef, achse=0.0, mittel=None, skala=None, training=None) -> dict:
    n = len(namen)
    return {"art": "LOGREG", "merkmale": list(namen), "mittel": mittel or [0.0] * n, "skala": skala or [1.0] * n, "koeffizienten": koef,
            "achsenabschnitt": achse, "training": training or {"fit_bis": 0, "max_t_ent": -1, "max_t_exit": 0, "val_max_t_exit": 0,
                                                                 "val_von": -1}}


def test_wahrscheinlichkeit_logreg_und_hgb_handrechnung():
    lr = _lr(["a", "b"], [0.5, -1.0], 0.1, [1.0, 2.0], [2.0, 4.0])
    assert mf.wahrscheinlichkeit(lr, [3.0, 6.0]) == pytest.approx(1 / (1 + math.exp(0.4)), abs=1e-15)
    hgb = {"art": "HGB", "merkmale": ["a"], "basis": -0.2,
           "baeume": [[[0.0, 0, 1.5, True, 1, 2, False], [0.3, 0, 0.0, False, 0, 0, True], [-0.1, 0, 0.0, False, 0, 0, True]]]}
    assert mf.wahrscheinlichkeit(hgb, [1.0]) == pytest.approx(1 / (1 + math.exp(-0.1)))
    assert mf.wahrscheinlichkeit(hgb, [1.5]) == pytest.approx(1 / (1 + math.exp(-0.1)))               # x ≤ Schwelle → links
    assert mf.wahrscheinlichkeit(hgb, [2.0]) == pytest.approx(1 / (1 + math.exp(0.3)))
    assert mf.wahrscheinlichkeit(hgb, [float("nan")]) == pytest.approx(1 / (1 + math.exp(-0.1)))     # fehlend → links
    assert mf.wahrscheinlichkeit(_lr(["a"], [1.0]), [-800.0]) == 0.0 and mf.wahrscheinlichkeit(_lr(["a"], [1.0]), [800.0]) == 1.0
    with pytest.raises(ValueError):
        mf.wahrscheinlichkeit(lr, [1.0])


# ---------------------------------------------------------------------------------------------------- Hülle
class Immer:
    """Basis ohne Idee: Signal an jeder Kerze; merkt sich die Länge des übergebenen Fensters."""

    name, zeitrahmen, rueckblick, symbole, max_halte_s = "TEST-IMMER", "H1", 250, ("EURUSD",), 86400.0

    def __init__(self) -> None:
        self.laengen: list[int] = []

    def parameter(self) -> dict:
        return {}

    def signal(self, symbol, kerzen):
        self.laengen.append(len(kerzen))
        k = kerzen[-1]
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        e = k.close + k.spread_points * D("0.00001") if side is Side.BUY else k.close
        return Signal(symbol, side, e - side.sign * D("0.00200"), e + side.sign * D("0.00100"), k.time, "immer")


def test_huelle_entscheidet_nach_fenster_embargo_schwelle():
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 7, saat=4)
    t_ent = kerzen[-1].time + 3600
    modell = _lr(mf.MERKMALE, [0.0] * 15, 0.0)                       # p = 0,5 für jede Eingabe
    def huelle(*fenster):
        return mf.MetaFilter(Immer(), list(fenster), art="REV01", name="T")
    assert huelle().bewerten("EURUSD", kerzen)[2] == "KEIN_FENSTER"
    assert huelle(mf.Fenster(t_ent - 10, t_ent, t_ent - 9, 0.4, modell)).bewerten("EURUSD", kerzen)[2] == "KEIN_FENSTER"    # bis exklusiv
    assert huelle(mf.Fenster(t_ent - 10, None, t_ent + 1, 0.4, modell)).bewerten("EURUSD", kerzen)[2] == "EMBARGO"
    assert huelle(mf.Fenster(t_ent - 10, None, t_ent, None, modell)).bewerten("EURUSD", kerzen)[2] == "KEINE_SCHWELLE"
    assert huelle(mf.Fenster(t_ent - 1, t_ent + 1, t_ent, 0.5, modell)).bewerten("EURUSD", kerzen)[2] == "UNTER_SCHWELLE"  # p > Schwelle
    h = huelle(mf.Fenster(t_ent - 1, t_ent + 1, t_ent, 0.49, modell))
    sig, p, e = h.bewerten("EURUSD", kerzen)
    assert e == "HANDELN" and p == 0.5 and h.signal("EURUSD", kerzen) == sig
    assert h.rueckblick == mf.FENSTER and set(h.basis.laengen) == {250}                 # die Basis sieht genau ihr Fenster
    assert huelle(mf.Fenster(0, None, 1, 0.4, modell)).bewerten("EURUSD", kerzen[:mf.FENSTER - 1])[2] == "KEINE_MERKMALE"
    with pytest.raises(ValueError):
        huelle(mf.Fenster(0, None, 1, 0.5, _lr(mf.MERKMALE_REV02, [0.0] * 17)))       # Modellmerkmale passen nicht zur Art


def test_laden_prueft_schema_und_basis(tmp_path):
    import json
    basis = MittelwertRueckkehr(k=2.0, z_tp=0.75, r=3)
    daten = {"schema": "meta_filter/1", "variante": "V", "basis_name": basis.name, "basis_parameter": basis.parameter(), "art": "REV01",
             "fenster": [{"test_von": 1, "test_bis": 2, "embargo_bis": 2, "schwelle": None, "modell": None}],
             "holdout": {"test_von": 2, "test_bis": None, "embargo_bis": 3, "schwelle": 0.6, "modell": _lr(mf.MERKMALE, [0.0] * 15)}}
    pfad = tmp_path / "m.json"
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    h = mf.laden(pfad, basis)
    assert h.name == "V" and h.modell_sha == mf.datei_sha(pfad) and h.fenster_fuer(1) is not None and h.fenster_fuer(5) is None
    assert mf.laden(pfad, basis, holdout=True).fenster_fuer(10**10).schwelle == 0.6
    with pytest.raises(ValueError):
        mf.laden(pfad, MittelwertRueckkehr(k=2.5, z_tp=0.75, r=3))
    pfad.write_text(json.dumps({**daten, "schema": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        mf.laden(pfad, basis)


# ---------------------------------------------------------------------------------------------------- Schwellenregel
def test_schwelle_kleinste_mit_hoechster_wilson_untergrenze_mindestens_20():
    p = [0.52] * 30 + [0.62] * 30 + [0.95] * 10
    y = [0] * 15 + [1] * 15 + [1] * 24 + [0] * 6 + [1] * 10
    w = meta.schwelle_waehlen(p, y)
    assert w["schwelle"] == 0.55 and w["n"] == 40 and w["treffer"] == 34 and w["wilson_unten"] == stats.wilson(34, 40)[0]
    assert [c["n"] for c in w["kandidaten"]] == [70, 40, 40, 10, 10, 10, 10, 10, 10]   # 0,55 und 0,60 gleich gut → die kleinere
    assert meta.schwelle_waehlen([0.7] * 19, [1] * 19)["schwelle"] is None             # < 20 über jeder Schwelle
    gleich = meta.schwelle_waehlen([0.7] * 25, [1] * 25)
    assert gleich["schwelle"] == 0.50                                                    # Gleichstand → kleinste Schwelle
    assert meta.schwelle_waehlen([0.5] * 30, [1] * 30)["schwelle"] is None             # p = 0,5 liegt nicht über 0,50


# ---------------------------------------------------------------------------------------------------- Plan, Purge, Embargo
def test_embargo_fuenf_handelstage():
    assert meta.embargo_ende(utc(2013, 1, 1)) == utc(2013, 1, 9)          # Di 1.1. frei → Mi 2. bis Di 8. → ab Mi 9.1.
    assert meta.embargo_ende(utc(2021, 1, 1)) == utc(2021, 1, 11)         # Fr 1.1. frei → Mo 4. bis Fr 8. → ab Mo 11.1.
    assert meta.embargo_ende(utc(2021, 7, 1)) == utc(2021, 7, 8)          # Do → Do (Holdout)
    assert meta.embargo_ende(utc(2016, 1, 2)) == utc(2016, 1, 11)         # Sa: ab Mo 04.01. fünf Tage → Mo 11.01.
    assert meta.embargo_ende(utc(2017, 1, 1)) == utc(2017, 1, 9)          # So
    assert meta.embargo_ende(utc(2015, 12, 22)) == utc(2015, 12, 30)      # 25.12. zählt nicht


def test_plan_wie_f04_mit_holdout_modell():
    p = meta.plan()
    assert [(f["test_von"], f["test_bis"]) for f in p[:-1]] == meta.entwicklung.fenster()
    assert p[0]["test_von"] == utc(2013, 1, 1) and p[0]["fit_von"] == utc(2010, 1, 1) and p[0]["val_von"] == utc(2012, 1, 1)
    assert p[-2]["test_von"] == utc(2021, 1, 1) and p[-2]["test_bis"] == utc(2021, 7, 1)
    assert p[-1] == {"test_von": utc(2021, 7, 1), "test_bis": None, "embargo_bis": utc(2021, 7, 8), "fit_von": utc(2018, 7, 1),
                     "val_von": utc(2020, 7, 1), "holdout": True}
    assert all(f["fit_von"] < f["val_von"] < f["test_von"] < f["embargo_bis"] for f in p)


def _zeilen(n=6000, saat=1) -> list[dict]:
    rng = random.Random(saat)
    aus = []
    for _ in range(n):
        t = rng.randrange(utc(2010, 1, 1), utc(2021, 7, 1)) // 3600 * 3600
        offen = rng.random() < 0.01
        aus.append({"t_ent": t, "t_exit": None if offen else t + rng.choice((3600, 7200, 86400, 3 * 86400)),
                    "label": None if offen else rng.randint(0, 1), "x": [0.0] * 15})
    return sorted(aus, key=lambda z: z["t_ent"])


def test_purge_keine_trainingszeile_ueberlappt_das_testfenster(monkeypatch):
    zeilen = _zeilen()
    plan = meta.plan()
    for f in plan:
        innen, val, final = (meta.menge(zeilen, f["fit_von"], f["val_von"]), meta.menge(zeilen, f["val_von"], f["test_von"]),
                             meta.menge(zeilen, f["fit_von"], f["test_von"]))
        assert innen and val and final
        assert all(z["t_exit"] <= f["val_von"] and f["fit_von"] <= z["t_ent"] < f["val_von"] for z in innen)
        assert all(z["t_exit"] <= f["test_von"] and f["val_von"] <= z["t_ent"] < f["test_von"] for z in val)
        assert all(z["t_exit"] <= f["test_von"] for z in final) and all(z["label"] is not None for z in final)
        rand = [z for z in zeilen if f["fit_von"] <= z["t_ent"] < f["test_von"]]
        assert meta.gepurgt(zeilen, f["fit_von"], f["test_von"]) == len(rand) - len(final) > 0
    datei = _modelldatei(zeilen, plan, meta.menge)
    assert meta.purge_pruefen(datei, zeilen, plan) == []
    # Mutation nur im Trainer: Mengen ohne Purge (meta.menge bleibt unverändert) → Anzahl und Grenzen fallen auf
    ohne_purge = _modelldatei(zeilen, plan, lambda z, von, bis: [x for x in z if von <= x["t_ent"] < bis and x["label"] is not None])
    befunde = meta.purge_pruefen(ohne_purge, zeilen, plan)
    assert {b.split(":")[0] for b in befunde} >= {"anzahl", "grenze", "modellgrenze"} and len(befunde) > 20
    kurz = _modelldatei(zeilen, plan, meta.menge)
    kurz["fenster"][0]["embargo_bis"] = plan[0]["test_von"] + 3600                    # Embargo eine Stunde statt 5 Handelstage
    assert meta.purge_pruefen(kurz, zeilen, plan) == ["plan:Fenster der Modelldatei weichen vom registrierten Plan ab",
                                                      f"embargo:{plan[0]['test_von']}"]
    luecke = _modelldatei(zeilen, plan, meta.menge)
    del luecke["fenster"][3]                                                          # ein Testfenster fehlt
    assert meta.purge_pruefen(luecke, zeilen, plan)[0].startswith("plan:")
    ohne_angabe = _modelldatei(zeilen, plan, meta.menge)
    del ohne_angabe["holdout"]["grenzen"]
    assert meta.purge_pruefen(ohne_angabe, zeilen, plan) == [f"grenzen_fehlen:{n}:{plan[-1]['test_von']}"
                                                             for n in ("innen", "validierung", "final")]


def _modelldatei(zeilen, plan, mengen_fn) -> dict:
    """Modelldatei, wie forschung/meta_training.py sie schreibt (Grenzen aus den benutzten Mengen; Modell ohne Gewichte)."""
    def g(zs):
        return {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None), "max_t_ent": max((z["t_ent"] for z in zs), default=None),
                "max_t_exit": max((z["t_exit"] for z in zs if z["t_exit"] is not None), default=None)}
    fenster = []
    for f in plan:
        innen, val, final = (mengen_fn(zeilen, f["fit_von"], f["val_von"]), mengen_fn(zeilen, f["val_von"], f["test_von"]),
                             mengen_fn(zeilen, f["fit_von"], f["test_von"]))
        gf, gv = g(final), g(val)
        fenster.append({**{k: f[k] for k in meta.PLAN_SCHLUESSEL}, "grenzen": {"innen": g(innen), "validierung": gv, "final": gf},
                        "modell": {"training": {"fit_bis": f["test_von"], "max_t_exit": gf["max_t_exit"], "max_t_ent": gf["max_t_ent"],
                                                "val_max_t_exit": gv["max_t_exit"], "val_von": f["val_von"]}}})
    return {"fenster": fenster[:-1], "holdout": fenster[-1]}


def _plan_modelle(plan) -> list[mf.Fenster]:
    """Je Fenster ein Modell mit genau seinen Trainingsgrenzen (wie forschung/meta_training.py sie schreibt)."""
    return [mf.Fenster(f["test_von"], f["test_bis"], f["embargo_bis"], 0.5,
                       _lr(mf.MERKMALE, [0.0] * 15, training={"fit_bis": f["test_von"], "max_t_ent": f["test_von"] - 3600,
                                                              "max_t_exit": f["test_von"], "val_max_t_exit": f["test_von"],
                                                              "val_von": f["val_von"]}))
            for f in plan]


def test_modell_ist_an_sein_fenster_gebunden_mutationen_werden_verweigert():
    plan = meta.plan()
    richtig = _plan_modelle(plan)
    mf.MetaFilter(Immer(), richtig[:-1], art="REV01", name="T")                         # Entwicklung: 9 Fenster
    mf.MetaFilter(Immer(), richtig[-1:], art="REV01", name="T")                         # Holdout allein
    verschoben = [replace(f, modell=g.modell) for f, g in zip(richtig[:-2], richtig[1:-1], strict=True)]
    with pytest.raises(ValueError, match="reichen ins Testfenster"):                     # Modell des Folgefensters
        mf.MetaFilter(Immer(), verschoben, art="REV01", name="T")
    with pytest.raises(ValueError, match="reichen ins Testfenster"):                     # Holdout-Modell im Fenster 2021-H1
        mf.MetaFilter(Immer(), [*richtig[:-2], replace(richtig[-2], modell=richtig[-1].modell)], art="REV01", name="T")
    with pytest.raises(ValueError, match="überlappen"):
        mf.MetaFilter(Immer(), [replace(richtig[0], test_bis=None), richtig[1]], art="REV01", name="T")
    with pytest.raises(ValueError, match="Embargo"):
        mf.MetaFilter(Immer(), [replace(richtig[0], embargo_bis=richtig[0].test_von)], art="REV01", name="T")
    ohne = dict(richtig[0].modell)
    del ohne["training"]
    with pytest.raises(ValueError, match="Trainingsgrenzen"):
        mf.MetaFilter(Immer(), [replace(richtig[0], modell=ohne)], art="REV01", name="T")
    halb = {**richtig[0].modell, "training": {k: v for k, v in richtig[0].modell["training"].items() if k != "val_max_t_exit"}}
    with pytest.raises(ValueError, match="Trainingsgrenzen"):                          # Validierungsgrenze ist Pflicht
        mf.MetaFilter(Immer(), [replace(richtig[0], modell=halb)], art="REV01", name="T")


def test_huelle_handelt_nie_im_embargo_und_vor_dem_ersten_fenster():
    plan = meta.plan()
    modell = _lr(mf.MERKMALE, [0.0] * 15, 1.0)
    h = mf.MetaFilter(Immer(), [mf.Fenster(f["test_von"], f["test_bis"], f["embargo_bis"], 0.5, modell) for f in plan[:-1]], art="REV01",
                      name="T")
    for f in plan[:-1]:
        assert h.fenster_fuer(f["test_von"]) is not None and h.fenster_fuer(f["test_von"]).embargo_bis == f["embargo_bis"]
    assert h.fenster_fuer(utc(2012, 12, 31, 23)) is None and h.fenster_fuer(utc(2021, 7, 1)) is None


# ---------------------------------------------------------------------------------------------------- Kerzen wie im Takt
@pytest.mark.parametrize("faktor", ["1", "1.5"])
def test_takt_kerzen_gleich_dem_terminal(faktor):
    h1 = {"EURUSD": bh.h1_reihe("EURUSD", stunden=24 * 7 * 3, saat=6, luecken=0.08)}
    h4 = {"EURUSD": bh.verdichten(h1["EURUSD"], 14400)}
    profil = Kostenprofil("t", D(0)).mal(faktor) if faktor != "1" else Kostenprofil("t", D(0))
    zeiten = sorted(b.time for b in h1["EURUSD"])
    uhr = Uhr(zeiten[0] + 3600)
    term = BacktestTerminal(["EURUSD"], kostenprofil=profil, balance=D(10000), uhr=uhr)
    zeiger, tf_zeiger = {"EURUSD": 0}, {"EURUSD": 0}
    for t in zeiten:
        uhr.t = float(t + 3600)
        runner._kerzen_abspielen(term, h1, zeiger, t)
        runner._zeitrahmen_einstellen(term, h4, tf_zeiger, "H4", t + 3600)
    ende = zeiten[-1] + 3600                                       # H4-Kerzen, die erst nach dem letzten Schritt schließen, sieht der Takt nie
    assert term.bars("EURUSD", "H4", 0, 2**40) == [b for b in meta.takt_kerzen(h1, h4, "H4", profil)["EURUSD"] if b.time + 14400 <= ende]
    assert term.bars("EURUSD", "H1", 0, 2**40) == meta.takt_kerzen(h1, None, "H1", profil)["EURUSD"]
    assert meta.takt_kerzen(h1, h4, "H4", profil)["EURUSD"] != [replace(b, spread_points=profil.spread_points(b.spread_points))
                                                                 for b in h4["EURUSD"]]          # die H4-Regel greift wirklich


# ---------------------------------------------------------------------------------------------------- Parität im Takt
def _spread_modell(namen) -> dict:
    """Entscheidung hängt stark am Spread/ATR (Merkmal 5) – ein falscher Spread kippt die Entscheidung (Mutationstest)."""
    koef = [0.0] * len(namen)
    koef[4] = -40.0
    return _lr(namen, koef, 0.0, [0.0] * len(namen), [1.0] * len(namen))


@pytest.mark.parametrize("art", ["REV01", "REV02"])
def test_signal_paritaet_der_huelle_im_takt(art, tmp_path):
    h1 = bh.markt(("EURUSD",), wochen=26, saat=8, sigma=0.0025)
    h4 = {"EURUSD": bh.verdichten(h1["EURUSD"], 14400)}
    basis = (MittelwertRueckkehr(k=1.5, z_tp=0.5, r=2, symbole=("EURUSD",)) if art == "REV01"
             else Fehlausbruch(L=20, z_tp=0.5, symbole=("EURUSD",)))
    profil = Kostenprofil("t", D(0))
    namen = mf.merkmal_namen(art)
    markt = Markt(h1, profil)
    kerzen = meta.takt_kerzen(h1, h4, basis.zeitrahmen, profil)
    zeilen, _ = meta.datensatz(basis, art, kerzen, markt)
    assert len(zeilen) >= 10
    roh = [mf.wahrscheinlichkeit(_spread_modell(namen), z["x"]) for z in zeilen]
    schwelle = statistics.median(roh)
    h = mf.MetaFilter(basis, [mf.Fenster(0, None, 1, schwelle, _spread_modell(namen))], art=art, name="T")
    erg = runner.laufen(h, h1, tmp_path / "a", runner.Einstellungen(profil), tf_kerzen=h4 if art == "REV02" else None)
    direkt = sum(1 for p in roh if p > schwelle)
    sp = paritaet.signal_paritaet(erg.signale, h, kerzen, markt.schritte)
    assert sp["quote"] == 1.0 and sp["takt"] == direkt > 0
    assert paritaet.trade_paritaet(erg.details, markt, h.max_halte_s)["quote"] == 1.0 and erg.technik_ok
    if art == "REV02":                                                     # Mutation: H4-Spread roh statt wie im Takt
        falsch = paritaet.signal_paritaet(erg.signale, h, h4, markt.schritte, spread_points=profil.spread_points)
        assert falsch["quote"] < 1.0


# ---------------------------------------------------------------------------------------------------- Paritätsprobe (ohne sklearn)
def test_paritaetsprobe_scikit_learn_ohne_scikit_learn_nachgerechnet():
    """kit_tests/daten/meta_paritaet.json: Modelle und p von scikit-learn (erzeugt und geprüft in test_meta_sklearn.py, .venv-forschung);
    hier rechnet die Standardbibliothek nach – Laufzeit-Parität ≤ 1e-9 auch in jeder Umgebung ohne scikit-learn."""
    import json
    from pathlib import Path
    probe = json.loads((Path(__file__).resolve().parent / "daten" / "meta_paritaet.json").read_text(encoding="utf-8"))
    assert set(probe) == {"LOGREG", "HGB"}
    for teil in probe.values():
        assert len(teil["x"]) == len(teil["p"]) == 40
        assert max(abs(mf.wahrscheinlichkeit(teil["modell"], x) - p) for x, p in zip(teil["x"], teil["p"], strict=True)) <= 1e-9
    assert any(math.isnan(v) for x in probe["HGB"]["x"] for v in x)                     # fehlende Werte sind dabei
