"""Runde 2 mit scikit-learn (nur in .venv-forschung; ohne scikit-learn übersprungen): Laufzeit-Parität der eingefrorenen JSON-Modelle
(≤ 1e-9, auch mit fehlenden Werten), Lecktest über die Validierungsgüte (Prereg F-05 §3: ein zukünftiges Merkmal hebt sie deutlich –
vorab festgelegt: AUC +0,10 oder mehr), Trainingskette unabhängig von Kursen ab Testbeginn, Wiederholbarkeit, ganze Modelldatei und die
gespeicherte Paritätsprobe kit_tests/daten/meta_paritaet.json (die test_meta_filter.py ohne scikit-learn nachrechnet).

    .venv-forschung\\Scripts\\python.exe -B -m pytest -q kit_tests/test_meta_sklearn.py
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
from sklearn.metrics import roc_auc_score  # noqa: E402

from forschung import meta_training as mt  # noqa: E402
from kit.backtest.ausstieg import Markt  # noqa: E402
from kit.backtest.kosten import Kostenprofil  # noqa: E402
from kit.domain.types import Bar, Side  # noqa: E402
from kit.research import meta  # noqa: E402
from kit.strategy import meta_filter as mf  # noqa: E402
from kit.strategy.base import Signal  # noqa: E402
from kit_tests import backtest_hilfen as bh  # noqa: E402

D = Decimal
PROBE = Path(__file__).resolve().parent / "daten" / "meta_paritaet.json"


# ---------------------------------------------------------------------------------------------------- Parität
def _daten(n: int, saat: int, nan: float = 0.0) -> tuple:
    rng = np.random.default_rng(saat)
    x = rng.normal(size=(n, 15))
    x[:, 3] = rng.uniform(size=n)                                            # Anteil 0–1 wie Merkmal (4)
    x[:, 10:15] = np.eye(5)[rng.integers(0, 5, size=n)]                       # Wochentag 1-aus-5
    y = (x[:, 0] - 0.5 * x[:, 1] + rng.normal(scale=1.5, size=n) > 0).astype(np.int64)
    if nan:
        x[rng.uniform(size=x.shape) < nan] = np.nan
    return x, y


@pytest.mark.parametrize("art", ["LOGREG", "HGB"])
def test_laufzeit_paritaet_standardbibliothek_gleich_sklearn(art):
    x, y = _daten(4000, 1, nan=0.02 if art == "HGB" else 0.0)
    m = mt.anpassen(art, x, y)
    modell = mt.exportieren(m, art, mf.MERKMALE)
    xt, _ = _daten(2000, 2, nan=0.05 if art == "HGB" else 0.0)
    assert mt.paritaet(m, modell, xt) <= 1e-9 and mt.paritaet(m, modell, x) <= 1e-9
    if art == "HGB":
        assert len(modell["baeume"]) == 200 and any(not k[3] for b in modell["baeume"] for k in b if not k[6])   # NaN-Regel genutzt
    assert json.loads(json.dumps(modell)) == modell                                   # verlustfrei als JSON
    assert mt.anpassen(art, x, np.zeros_like(y)) is None                              # nur eine Klasse → kein Modell


def _probe() -> dict:
    """Kleine, feste Paritätsprobe: je Modellart ein exportiertes Modell, Eingaben (HGB mit fehlenden Werten) und p von scikit-learn."""
    from threadpoolctl import threadpool_limits
    aus = {}
    for art in ("LOGREG", "HGB"):
        x, y = _daten(600, 11, nan=0.03 if art == "HGB" else 0.0)
        m = mt._neues_modell(art)
        if art == "HGB":
            m.set_params(max_iter=20)                                        # klein halten (Datei im Repo)
        with threadpool_limits(1):
            m.fit(x, y)
        modell = mt.exportieren(m, art, mf.MERKMALE)
        xt, _ = _daten(40, 12, nan=0.1 if art == "HGB" else 0.0)
        aus[art] = {"modell": modell, "x": xt.tolist(), "p": [float(v) for v in m.predict_proba(xt)[:, 1]]}
    return aus


def test_paritaetsprobe_ist_echte_sklearn_ausgabe():
    gespeichert = json.loads(PROBE.read_text(encoding="utf-8"))
    neu = json.loads(json.dumps(_probe()))
    assert neu == gespeichert


# ---------------------------------------------------------------------------------------------------- Lecktest (Validierungsgüte)
class Jede:
    """Basis ohne Idee: Signal an jeder Kerze, Richtung abwechselnd, Ziel/Stop in Pips, Zeitbarriere 6 h (weite Abstände: meist
    Zeitbarriere, also Label-Ausstieg Stunden nach der Entscheidung – der Purge an Fenstergrenzen greift)."""

    name, zeitrahmen, rueckblick, symbole, max_halte_s = "TEST-JEDE", "H1", 250, ("EURUSD",), 6 * 3600.0

    def __init__(self, ziel: str = "0.00100", stop: str = "0.00150") -> None:
        self.ziel, self.stop = D(ziel), D(stop)

    def parameter(self) -> dict:
        return {"ziel": str(self.ziel), "stop": str(self.stop)}

    def signal(self, symbol, kerzen):
        k = kerzen[-1]
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        e = k.close + k.spread_points * D("0.00001") if side is Side.BUY else k.close
        return Signal(symbol, side, e - side.sign * self.stop, e + side.sign * self.ziel, k.time, "jede")


def _datensatz(kerzen: list[Bar], basis=None) -> list[dict]:
    profil = Kostenprofil("t", D(0))
    h1 = {"EURUSD": kerzen}
    return meta.datensatz(basis or Jede(), "REV01", meta.takt_kerzen(h1, None, "H1", profil), Markt(h1, profil))[0]


def test_lecktest_zukunftsmerkmal_hebt_die_validierungsguete_deutlich():
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 30, saat=21, sigma=0.002)
    zeilen = [z for z in _datensatz(kerzen) if z["label"] is not None]
    index = {b.time: i for i, b in enumerate(kerzen)}

    def zukunft(z):                                          # „Rendite der nächsten 6 Kerzen“ in Signalrichtung (absichtliches Leck)
        i = index[z["t_kerze"]]
        j = min(i + 6, len(kerzen) - 1)
        return (float(kerzen[j].close) - float(kerzen[i].close)) * (1 if z["side"] == "BUY" else -1) / float(kerzen[i].close)

    n = int(len(zeilen) * 0.6)
    training, validierung = zeilen[:n], zeilen[n:]
    assert len(validierung) > 300

    def auc(mit_leck: bool) -> float:
        def x(zs):
            return np.array([[*z["x"], zukunft(z)] if mit_leck else z["x"] for z in zs])
        m = mt.anpassen("LOGREG", x(training), np.array([z["label"] for z in training]))
        return float(roc_auc_score([z["label"] for z in validierung], m.predict_proba(x(validierung))[:, 1]))
    sauber, leck = auc(False), auc(True)
    assert leck - sauber >= 0.10 and leck >= 0.70, (sauber, leck)


# ---------------------------------------------------------------------------------------------------- Trainingskette
def _fenster(kerzen: list[Bar], anteil: float) -> dict:
    t = kerzen[int(len(kerzen) * anteil)].time // 86400 * 86400 + 12 * 3600          # mittags: Positionen überspannen die Grenze
    v = t - 35 * 86400
    return {"test_von": t, "test_bis": t + 21 * 86400, "embargo_bis": meta.embargo_ende(t), "fit_von": kerzen[0].time,
            "val_von": v, "holdout": False}


@pytest.mark.parametrize("art", ["LOGREG", "HGB"])
def test_trainingskette_haengt_nicht_von_kursen_ab_testbeginn_ab(art):
    a = bh.h1_reihe("EURUSD", stunden=24 * 7 * 30, saat=22, sigma=0.002)
    f = _fenster(a, 0.75)
    anders = bh.h1_reihe("EURUSD", start=a[0].time, stunden=24 * 7 * 30, saat=99, sigma=0.004)
    b = [k for k in a if k.time + 3600 <= f["test_von"]] + [k for k in anders if k.time + 3600 > f["test_von"]]
    assert a != b
    weit = Jede(ziel="0.01000", stop="0.01500")
    za, zb = _datensatz(a, weit), _datensatz(b, weit)
    xa, xb = mt._matrix(za)[0], mt._matrix(zb)[0]
    ta = mt.fenster_trainieren(za, art, mf.MERKMALE, f, xa)
    tb = mt.fenster_trainieren(zb, art, mf.MERKMALE, f, xb)
    for k in ("modell", "schwelle", "validierung", "n_innen", "n_validierung", "n_final", "gepurgt_innen", "gepurgt_validierung",
              "gepurgt_final", "modell_innen_sha"):
        assert ta[k] == tb[k], k
    assert ta["modell"] is not None and ta["modell"]["training"]["max_t_exit"] <= f["test_von"]
    assert ta["gepurgt_innen"] > 0 and ta["gepurgt_validierung"] > 0 and ta["gepurgt_final"] > 0      # der Purge wirkt hier wirklich
    ohne = [z for z in za if f["fit_von"] <= z["t_ent"] < f["test_von"] and z["label"] is not None]
    assert any(z["t_exit"] > f["test_von"] for z in ohne)                                           # sonst sähe das Training Testkurse


def test_training_ist_wiederholbar_und_die_modelldatei_passt_zur_huelle(tmp_path):
    kerzen = bh.h1_reihe("EURUSD", stunden=24 * 7 * 30, saat=23, sigma=0.002)
    zeilen = _datensatz(kerzen)
    erstes = _fenster(kerzen, 0.6)
    h = erstes["test_bis"]
    plan = [erstes, {"test_von": h, "test_bis": None, "embargo_bis": meta.embargo_ende(h), "fit_von": kerzen[0].time,
                     "val_von": h - 35 * 86400, "holdout": True}]
    v = meta.MetaVariante("F05-REV01-HGB", meta.BASIS_REV01, "REV01", "HGB")
    erst = mt.trainieren(zeilen, v, plan)
    assert json.dumps(erst, sort_keys=True) == json.dumps(mt.trainieren(zeilen, v, plan), sort_keys=True)
    assert erst["paritaet_max"] <= 1e-9 and meta.purge_pruefen(erst, zeilen, plan) == []
    pfad = meta.modell_schreiben(erst, tmp_path)
    h = mf.laden(pfad, meta.basis_strategie(meta.BASIS_REV01))
    assert h.fenster_fuer(plan[0]["test_von"]) is not None and mf.laden(pfad, meta.basis_strategie(meta.BASIS_REV01), holdout=True)
    with pytest.raises(FileExistsError):
        meta.modell_schreiben(erst, tmp_path)
