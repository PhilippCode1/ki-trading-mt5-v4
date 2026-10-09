"""Training des KI-Meta-Filters (Runde 2, F-05) mit scikit-learn – nur in .venv-forschung (requirements/forschung.lock.txt), nie im
Bot: kit/ bleibt Standardbibliothek und rechnet nur mit den eingefrorenen JSON-Parametern (kit.strategy.meta_filter).

trainieren(zeilen, variante, plan) liefert die Modelldatei (Schema meta_filter/1). Je Fenster des Plans:
  1. inneres Modell auf [fit_von, val_von) (Purge: Label-Ausstieg ≤ val_von) → JSON → Wahrscheinlichkeiten der Validierung
     [val_von, test_von) (Purge: Ausstieg ≤ test_von) mit der Standardbibliotheks-Rechnung → Schwelle (kit.research.meta.schwelle_waehlen);
  2. finales Modell auf der ganzen Anpassung [fit_von, test_von) (Purge: Ausstieg ≤ test_von) → JSON, gilt mit der Schwelle im Testfenster.
Ein Modell, das nicht angepasst werden kann (nur eine Klasse), ergibt kein Modell und keine Schwelle (Fenster ohne Trades).
Parität: scikit-learn predict_proba gegen die Standardbibliotheks-Rechnung auf allen Datensatzzeilen (final) bzw. allen
Validierungszeilen (inneres Modell); die größte Abweichung steht in der Datei (`paritaet_max`, Grenze 1e-9 prüft kit.research.meta).
Ein Thread (threadpoolctl), random_state 0: das Training ist wiederholbar.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from kit.research import meta
from kit.strategy import meta_filter as mf

LOCK = Path(__file__).resolve().parents[1] / "requirements" / "forschung.lock.txt"
GEPRUEFT = ("scikit-learn", "numpy", "scipy", "joblib", "threadpoolctl")


def versionen_pruefen(lock: Path = LOCK) -> dict[str, str]:
    """Installierte Versionen = hash-gesperrte Versionen aus requirements/forschung.lock.txt (fail-closed)."""
    gesperrt = dict(re.findall(r"(?m)^([A-Za-z0-9_.-]+)==([^\s;\\]+)", Path(lock).read_text(encoding="utf-8")))
    aus = {}
    for paket in GEPRUEFT:
        ist = importlib.metadata.version(paket)
        if gesperrt.get(paket) != ist:
            raise RuntimeError(f"{paket} {ist} weicht vom Lock ab ({gesperrt.get(paket)}) – .venv-forschung aus dem Lock neu anlegen")
        aus[paket] = ist
    return aus


def _matrix(zeilen: Sequence[Mapping]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([z["x"] for z in zeilen], dtype=np.float64)
    y = np.array([z["label"] if z["label"] is not None else -1 for z in zeilen], dtype=np.int64)
    return x, y


def _neues_modell(art: str):
    if art == "LOGREG":
        return Pipeline([("skalierung", StandardScaler()),
                         ("lr", LogisticRegression(C=1.0, l1_ratio=0.0, solver="lbfgs", max_iter=1000))])
    if art == "HGB":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=50, l2_regularization=0.0,
                                              early_stopping=False, random_state=0)
    raise ValueError(f"unbekannte Modellart {art}")


def anpassen(art: str, x: np.ndarray, y: np.ndarray):
    """Angepasstes Modell oder None (zu wenige Zeilen oder nur eine Klasse)."""
    if len(y) == 0 or len(set(y.tolist())) < 2:
        return None
    m = _neues_modell(art)
    with threadpool_limits(1):
        m.fit(x, y)
    return m


def exportieren(m, art: str, namen: Sequence[str]) -> dict:
    """JSON-Parameter für kit.strategy.meta_filter.wahrscheinlichkeit (Python-floats, exakt als repr)."""
    if art == "LOGREG":
        skal, lr = m.named_steps["skalierung"], m.named_steps["lr"]
        if list(lr.classes_) != [0, 1] or lr.coef_.shape != (1, len(namen)):
            raise ValueError("unerwartete Form der logistischen Regression")
        return {"art": "LOGREG", "merkmale": list(namen), "mittel": [float(v) for v in skal.mean_], "skala": [float(v) for v in skal.scale_],
                "koeffizienten": [float(v) for v in lr.coef_[0]], "achsenabschnitt": float(lr.intercept_[0])}
    if art == "HGB":
        if list(m.classes_) != [0, 1] or m.n_trees_per_iteration_ != 1 or m.is_categorical_ is not None:
            raise ValueError("unerwartete Form von HistGradientBoosting")
        baeume = []
        for iteration in m._predictors:
            (praediktor,) = iteration
            knoten = []
            for n in praediktor.nodes:
                if bool(n["is_categorical"]):
                    raise ValueError("kategoriale Knoten nicht vorgesehen")
                knoten.append([float(n["value"]), int(n["feature_idx"]), float(n["num_threshold"]), bool(n["missing_go_to_left"]),
                               int(n["left"]), int(n["right"]), bool(n["is_leaf"])])
            baeume.append(knoten)
        return {"art": "HGB", "merkmale": list(namen), "basis": float(m._baseline_prediction.reshape(-1)[0]), "baeume": baeume}
    raise ValueError(f"unbekannte Modellart {art}")


def paritaet(m, modell: Mapping, x: np.ndarray) -> float:
    """Größte Abweichung |scikit-learn − Standardbibliothek| der Wahrscheinlichkeit über die Zeilen x."""
    if len(x) == 0:
        return 0.0
    p_sk = m.predict_proba(x)[:, 1]
    return max(abs(float(a) - mf.wahrscheinlichkeit(modell, list(map(float, zeile)))) for a, zeile in zip(p_sk, x, strict=True))


def _sha(modell: Mapping | None) -> str | None:
    if modell is None:
        return None
    return hashlib.sha256(json.dumps(modell, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def fenster_trainieren(zeilen: Sequence[Mapping], art: str, namen: Sequence[str], f: Mapping, x_alle: np.ndarray) -> dict:
    innen = meta.menge(zeilen, f["fit_von"], f["val_von"])
    val = meta.menge(zeilen, f["val_von"], f["test_von"])
    final = meta.menge(zeilen, f["fit_von"], f["test_von"])
    aus = {k: f[k] for k in ("test_von", "test_bis", "embargo_bis", "fit_von", "val_von")}
    aus["grenzen"] = {name: {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None),
                             "max_t_ent": max((z["t_ent"] for z in zs), default=None),
                             "max_t_exit": max((z["t_exit"] for z in zs), default=None)}
                      for name, zs in (("innen", innen), ("validierung", val), ("final", final))}
    aus.update({"n_innen": len(innen), "n_validierung": len(val), "n_final": len(final),
                "gepurgt_innen": meta.gepurgt(zeilen, f["fit_von"], f["val_von"]),
                "gepurgt_validierung": meta.gepurgt(zeilen, f["val_von"], f["test_von"]),
                "gepurgt_final": meta.gepurgt(zeilen, f["fit_von"], f["test_von"]),
                "gewinnquote_innen": (sum(z["label"] for z in innen) / len(innen)) if innen else None})
    xi, yi = _matrix(innen)
    m_innen = anpassen(art, xi, yi)
    schwelle = None
    paritaet_innen = 0.0
    validierung: dict = {"schwelle": None, "kandidaten": []}
    if m_innen is not None and val:
        modell_innen = exportieren(m_innen, art, namen)
        p_val = [mf.wahrscheinlichkeit(modell_innen, z["x"]) for z in val]
        validierung = meta.schwelle_waehlen(p_val, [z["label"] for z in val])
        schwelle = validierung["schwelle"]
        paritaet_innen = paritaet(m_innen, modell_innen, _matrix(val)[0])
        aus["modell_innen_sha"] = _sha(modell_innen)
    xf, yf = _matrix(final)
    m_final = anpassen(art, xf, yf)
    modell = exportieren(m_final, art, namen) if m_final is not None else None
    if modell is None:
        schwelle = None
    else:                                                   # Trainingsgrenzen aus genau den benutzten Zeilen (Hülle prüft fail-closed)
        modell["training"] = {"fit_von": f["fit_von"], "fit_bis": f["test_von"], "n": len(final),
                              "max_t_ent": max(z["t_ent"] for z in final), "max_t_exit": max(z["t_exit"] for z in final),
                              "val_von": f["val_von"], "val_max_t_exit": max((z["t_exit"] for z in val), default=0)}
    aus.update({"validierung": validierung, "schwelle": schwelle, "modell": modell,
                "paritaet_innen": paritaet_innen, "paritaet_final": paritaet(m_final, modell, x_alle) if modell is not None else 0.0})
    return aus


def trainieren(zeilen: list[dict], variante: meta.MetaVariante, plan: Sequence[Mapping]) -> dict:
    versionen = versionen_pruefen()
    namen = mf.merkmal_namen(variante.art)
    if any(len(z["x"]) != len(namen) for z in zeilen):
        raise ValueError("Merkmalsanzahl im Datensatz passt nicht zur Variante")
    x_alle = _matrix(zeilen)[0]
    fenster = [fenster_trainieren(zeilen, variante.modell, namen, f, x_alle) for f in plan]
    basis = meta.basis_strategie(variante.basis_id)
    alle = [f["paritaet_innen"] for f in fenster] + [f["paritaet_final"] for f in fenster]
    if not all(math.isfinite(v) for v in alle):
        raise ValueError("Parität nicht endlich")
    return {"schema": "meta_filter/1", "lauf": meta.LAUF, "variante": variante.id, "basis_variante": variante.basis_id,
            "basis_name": basis.name, "basis_parameter": basis.parameter(), "art": variante.art, "modell_art": variante.modell,
            "merkmale": list(namen), "merkmal_fenster": mf.FENSTER, "hyperparameter": meta.HYPERPARAMETER[variante.modell],
            "versionen": versionen,
            "datensatz_sha": hashlib.sha256(meta.datensatz_text(zeilen).encode("utf-8")).hexdigest(),
            "fenster": [f for f, p in zip(fenster, plan, strict=True) if not p["holdout"]],
            "holdout": next(f for f, p in zip(fenster, plan, strict=True) if p["holdout"]),
            "paritaet_max": max(alle) if alle else 0.0}
