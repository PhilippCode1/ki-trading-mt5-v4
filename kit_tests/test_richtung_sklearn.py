"""Runde 3 mit scikit-learn (nur .venv-forschung; ohne scikit-learn übersprungen): Training des Richtungsmodells – Laufzeit-Parität beider
Modelle ≤ 1e-9, Schwelle d* aus der Validierung, Trainingskette unabhängig von Kursen ab Testbeginn (bei wirksamem Purge), Wiederholbarkeit,
verlustfreie Modelldatei, die die Hülle lädt, und der Lecktest über die Validierungsgüte (Zukunftsmerkmal hebt die AUC um ≥ 0,10).

    .venv-forschung\\Scripts\\python.exe -B -m pytest -q kit_tests/test_richtung_sklearn.py
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
from sklearn.metrics import roc_auc_score  # noqa: E402

from forschung import meta_training as mt  # noqa: E402
from forschung import richtung_training as rt  # noqa: E402
from kit.backtest import runner  # noqa: E402
from kit.backtest.ausstieg import Markt  # noqa: E402
from kit.backtest.kosten import Kostenprofil  # noqa: E402
from kit.domain.types import Side  # noqa: E402
from kit.research import meta  # noqa: E402
from kit.research import richtung as ri  # noqa: E402
from kit.strategy import meta_filter as mf  # noqa: E402
from kit.strategy import richtung as rf  # noqa: E402
from kit.strategy.base import Signal  # noqa: E402
from kit_tests import backtest_hilfen as bh  # noqa: E402

D = Decimal
KONF = runner.bot_konfiguration()


class Jede:
    """Basis ohne Idee: Signal an jeder Kerze; Ziel/Stop in Preisabstand (weit: Ausstieg meist an der Zeitbarriere)."""

    name, zeitrahmen, rueckblick, symbole, max_halte_s = "TEST-JEDE-R", "H1", 250, ("EURUSD",), 6 * 3600.0

    def __init__(self, ziel: str = "0.00400", stop: str = "0.01200") -> None:
        self.ziel, self.stop = D(ziel), D(stop)

    def parameter(self) -> dict:
        return {"ziel": str(self.ziel), "stop": str(self.stop)}

    def signal(self, symbol, kerzen):
        k = kerzen[-1]
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        e = rf.einstieg(k, side)
        return Signal(symbol, side, e - side.sign * self.stop, e + side.sign * self.ziel, k.time, "jede")


def _datensatz(kerzen, basis=None) -> list[dict]:
    profil = Kostenprofil("t", D(0))
    h1 = {"EURUSD": kerzen}
    return ri.datensatz(basis or Jede(), "REV01", meta.takt_kerzen(h1, None, "H1", profil), Markt(h1, profil), KONF)[0]


def _fenster(kerzen, anteil: float) -> dict:
    t = kerzen[int(len(kerzen) * anteil)].time // 86400 * 86400 + 12 * 3600
    while dt.datetime.fromtimestamp(t, dt.UTC).weekday() != 2:                       # Mittwoch 12:00 UTC: Handel läuft über die Grenze
        t += 86400
    return {"test_von": t, "test_bis": t + 21 * 86400, "embargo_bis": meta.embargo_ende(t), "fit_von": kerzen[0].time,
            "val_von": t - 35 * 86400, "holdout": False}


@pytest.mark.parametrize("art", ["LOGREG", "HGB"])
def test_trainingskette_unabhaengig_von_kursen_ab_testbeginn(art):
    a = bh.h1_reihe("EURUSD", stunden=24 * 7 * 32, saat=31, sigma=0.002)
    f = _fenster(a, 0.75)
    anders = bh.h1_reihe("EURUSD", start=a[0].time, stunden=24 * 7 * 32, saat=77, sigma=0.004)
    b = [k for k in a if k.time + 3600 <= f["test_von"]] + [k for k in anders if k.time + 3600 > f["test_von"]]
    za, zb = _datensatz(a), _datensatz(b)
    tv = f["test_von"]
    ueber_a = {z["t_ent"]: (z["label_k"], z["label_v"]) for z in za if z["t_ent"] < tv < (z["t_exit"] or 0)}
    ueber_b = {z["t_ent"]: (z["label_k"], z["label_v"]) for z in zb if z["t_ent"] < tv < (z["t_exit"] or 0)}
    assert ueber_a and any(ueber_a[t] != ueber_b.get(t) for t in ueber_a)          # ohne Purge sähe das Training die neuen Kurse
    assert any(z["t_exit_k"] > tv >= z["t_exit_v"] for z in za if z["t_ent"] < tv and z["t_exit"]) or \
        any(z["t_exit_v"] > tv >= z["t_exit_k"] for z in za if z["t_ent"] < tv and z["t_exit"])
    ta = rt.fenster_trainieren(za, art, mf.MERKMALE, f, rt._x(za))
    tb = rt.fenster_trainieren(zb, art, mf.MERKMALE, f, rt._x(zb))
    for k in ("modell_kauf", "modell_verkauf", "schwelle", "validierung", "grenzen", "n_innen", "n_validierung", "n_final",
              "gepurgt_innen", "gepurgt_validierung", "gepurgt_final", "modell_innen_sha"):
        assert ta[k] == tb[k], k
    assert ta["modell_kauf"] is not None and ta["gepurgt_final"] > 0 and ta["gepurgt_validierung"] > 0
    assert ta["paritaet_final"] <= 1e-9 and ta["paritaet_innen"] <= 1e-9


def test_training_wiederholbar_datei_verlustfrei_und_ladbar(tmp_path):
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 32, saat=32, sigma=0.002)
    zeilen = _datensatz(kerzen)
    erstes = _fenster(kerzen, 0.6)
    h = erstes["test_bis"]
    plan = [erstes, {"test_von": h, "test_bis": None, "embargo_bis": meta.embargo_ende(h), "fit_von": kerzen[0].time,
                     "val_von": h - 35 * 86400, "holdout": True}]
    v = ri.RichtungsVariante("F05B-REV01-HGB", meta.BASIS_REV01, "REV01", "HGB")
    erst = rt.trainieren(zeilen, v, plan)
    assert json.dumps(erst, sort_keys=True) == json.dumps(rt.trainieren(zeilen, v, plan), sort_keys=True)
    assert erst["paritaet_max"] <= 1e-9 and ri.purge_pruefen(erst, zeilen, plan) == []
    gepackt = {**erst, "fenster": [ri._packen(f) for f in erst["fenster"]], "holdout": ri._packen(erst["holdout"])}
    pfad = meta.modell_schreiben(gepackt, tmp_path)
    geladen = json.loads(pfad.read_text(encoding="utf-8"))
    for alt, neu in zip([*erst["fenster"], erst["holdout"]], [*geladen["fenster"], geladen["holdout"]], strict=True):
        for s in ("modell_kauf", "modell_verkauf"):
            assert rf.rechengleich(alt[s], rf.entpacken(neu[s]))
    assert len(pfad.read_bytes()) < 0.65 * len(json.dumps(erst, separators=(",", ":")))
    huelle = ri.huelle_laden(pfad, v)
    assert huelle.fenster_fuer(plan[0]["test_von"]) is not None and ri.huelle_laden(pfad, v, holdout=True).fenster_fuer(10**10)


def test_kaufmodell_lernt_aus_kauflabels_und_die_huelle_kauft():
    """Zuordnung gegen Vertauschung: Gewinnt Kauf fast immer und Verkauf fast nie, schätzt das Kaufmodell höher, die Validierung wählt
    Kauf und die Hülle handelt BUY mit den SL/TP der Kaufrichtung."""
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 32, saat=34, sigma=0.002)
    zeilen = _datensatz(kerzen)
    rng = __import__("random").Random(5)
    for z in zeilen:
        if z["label_k"] is not None:
            z["label_k"], z["label_v"] = int(rng.random() < 0.9), int(rng.random() < 0.1)
    f = _fenster(kerzen, 0.75)
    for art in ("LOGREG", "HGB"):
        t = rt.fenster_trainieren(zeilen, art, mf.MERKMALE, f, rt._x(zeilen))
        z0 = next(z for z in zeilen if z["t_ent"] >= f["test_von"])
        assert mf.wahrscheinlichkeit(t["modell_kauf"], z0["x"]) > 0.7 > 0.3 > mf.wahrscheinlichkeit(t["modell_verkauf"], z0["x"])
        assert t["validierung"]["quote"] > 0.8 and t["schwelle"] is not None
        f_r = rf.Fenster(f["test_von"], f["test_bis"], f["embargo_bis"], t["schwelle"], t["modell_kauf"], t["modell_verkauf"])
        assert ri.entscheidung(f_r, {**z0, "t_ent": f["embargo_bis"]})[:2] == ("HANDELN", "BUY")


def test_lecktest_zukunftsmerkmal_hebt_die_validierungsguete_deutlich():
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 30, saat=33, sigma=0.002)
    zeilen = [z for z in _datensatz(kerzen, Jede("0.00100", "0.00150")) if z["label_k"] is not None]
    index = {b.time: i for i, b in enumerate(kerzen)}

    def zukunft(z):                                          # „Rendite der nächsten 6 Kerzen“ (absichtliches Leck)
        i = index[z["t_kerze"]]
        return (float(kerzen[min(i + 6, len(kerzen) - 1)].close) - float(kerzen[i].close)) / float(kerzen[i].close)

    n = int(len(zeilen) * 0.6)
    training, validierung = zeilen[:n], zeilen[n:]

    def auc(mit_leck: bool) -> float:
        def x(zs):
            return np.array([[*z["x"], zukunft(z)] if mit_leck else z["x"] for z in zs])
        m = mt.anpassen("LOGREG", x(training), np.array([z["label_k"] for z in training]))
        return float(roc_auc_score([z["label_k"] for z in validierung], m.predict_proba(x(validierung))[:, 1]))
    sauber, leck = auc(False), auc(True)
    assert leck - sauber >= 0.10, (sauber, leck)                       # vorab festgelegt: AUC +0,10 oder mehr
