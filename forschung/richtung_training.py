"""Training des Richtungsmodells (Runde 3, F-05b) mit scikit-learn – nur in .venv-forschung; im Bot nur JSON-Parameter
(kit.strategy.richtung, Standardbibliothek). Modellarten, Export, Parität und Versionsprüfung aus forschung.meta_training.

trainieren(zeilen, variante, plan) liefert die Modelldatei (Schema richtung/1). Je Fenster des Plans:
  1. innere Modelle (Kauf, Verkauf) auf [fit_von, val_von) (Purge: beide Ausstiege ≤ val_von) → p_Kauf, p_Verkauf der Validierung
     [val_von, test_von) (Purge: ≤ test_von) mit der Standardbibliotheks-Rechnung → gewählte Richtung und Vorsprung |p_K − p_V| →
     Schwelle d* (kit.research.meta.schwelle_waehlen auf dem Vorsprung, Treffer = Label der gewählten Richtung, mindestens 50);
  2. finale Modelle auf [fit_von, test_von) → JSON mit Trainingsgrenzen (gleiche Zeilen für beide Modelle).
Parität scikit-learn ↔ Standardbibliothek für beide Modelle auf allen Zeilen (final) bzw. der Validierung (innen), ≤ 1e-9 prüft
kit.research.richtung.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence

import numpy as np

from forschung import meta_training as mt
from kit.research import meta
from kit.research import richtung as ri
from kit.strategy import meta_filter as mf


def _x(zeilen: Sequence[Mapping]) -> np.ndarray:
    if not zeilen:
        return np.empty((0, 0), dtype=np.float64)                  # leere Menge → anpassen liefert None (Fenster ohne Trades)
    return np.array([z["x"] for z in zeilen], dtype=np.float64)


def _y(zeilen: Sequence[Mapping], feld: str) -> np.ndarray:
    return np.array([z[feld] for z in zeilen], dtype=np.int64)


def _grenzen(zs: Sequence[Mapping]) -> dict:
    return {"n": len(zs), "min_t_ent": min((z["t_ent"] for z in zs), default=None), "max_t_ent": max((z["t_ent"] for z in zs), default=None),
            "max_t_exit": max((z["t_exit"] for z in zs), default=None)}


def fenster_trainieren(zeilen: Sequence[Mapping], art: str, namen: Sequence[str], f: Mapping, x_alle: np.ndarray) -> dict:
    innen = ri.menge(zeilen, f["fit_von"], f["val_von"])
    val = ri.menge(zeilen, f["val_von"], f["test_von"])
    final = ri.menge(zeilen, f["fit_von"], f["test_von"])
    aus = {k: f[k] for k in ri.PLAN_SCHLUESSEL}
    aus["grenzen"] = {"innen": _grenzen(innen), "validierung": _grenzen(val), "final": _grenzen(final)}
    aus.update({"n_innen": len(innen), "n_validierung": len(val), "n_final": len(final),
                "gepurgt_innen": ri.gepurgt(zeilen, f["fit_von"], f["val_von"]),
                "gepurgt_validierung": ri.gepurgt(zeilen, f["val_von"], f["test_von"]),
                "gepurgt_final": ri.gepurgt(zeilen, f["fit_von"], f["test_von"])})
    xi = _x(innen)
    mk, mv = mt.anpassen(art, xi, _y(innen, "label_k")), mt.anpassen(art, xi, _y(innen, "label_v"))
    schwelle, paritaet_innen = None, 0.0
    validierung: dict = {"schwelle": None, "kandidaten": []}
    if mk is not None and mv is not None and val:
        jk, jv = mt.exportieren(mk, art, namen), mt.exportieren(mv, art, namen)
        vorsprung, treffer = [], []
        for z in val:
            pk, pv = mf.wahrscheinlichkeit(jk, z["x"]), mf.wahrscheinlichkeit(jv, z["x"])
            vorsprung.append(abs(pk - pv))
            treffer.append(z["label_k"] if pk >= pv else z["label_v"])
        validierung = meta.schwelle_waehlen(vorsprung, treffer, gitter=ri.GITTER, min_n=ri.MIN_VALIDIERUNG)
        schwelle = validierung["schwelle"]
        xv = _x(val)
        paritaet_innen = max(mt.paritaet(mk, jk, xv), mt.paritaet(mv, jv, xv))
        aus["modell_innen_sha"] = [mt._sha(jk), mt._sha(jv)]
    xf = _x(final)
    fk, fv = mt.anpassen(art, xf, _y(final, "label_k")), mt.anpassen(art, xf, _y(final, "label_v"))
    modell_kauf = modell_verkauf = None
    paritaet_final = 0.0
    if fk is not None and fv is not None:
        training = {"fit_von": f["fit_von"], "fit_bis": f["test_von"], "n": len(final), "max_t_ent": max(z["t_ent"] for z in final),
                    "max_t_exit": max(z["t_exit"] for z in final), "val_von": f["val_von"],
                    "val_max_t_exit": max((z["t_exit"] for z in val), default=0)}
        modell_kauf = {**mt.exportieren(fk, art, namen), "training": training}
        modell_verkauf = {**mt.exportieren(fv, art, namen), "training": training}
        paritaet_final = max(mt.paritaet(fk, modell_kauf, x_alle), mt.paritaet(fv, modell_verkauf, x_alle))
    else:
        schwelle = None
    aus.update({"validierung": validierung, "schwelle": schwelle, "modell_kauf": modell_kauf, "modell_verkauf": modell_verkauf,
                "paritaet_innen": paritaet_innen, "paritaet_final": paritaet_final})
    return aus


def trainieren(zeilen: list[dict], variante: ri.RichtungsVariante, plan: Sequence[Mapping]) -> dict:
    versionen = mt.versionen_pruefen()
    namen = mf.merkmal_namen(variante.art)
    if any(len(z["x"]) != len(namen) for z in zeilen):
        raise ValueError("Merkmalsanzahl im Datensatz passt nicht zur Variante")
    x_alle = _x(zeilen)
    fenster = [fenster_trainieren(zeilen, variante.modell, namen, f, x_alle) for f in plan]
    basis = meta.basis_strategie(variante.basis_id)
    alle = [f["paritaet_innen"] for f in fenster] + [f["paritaet_final"] for f in fenster]
    if not all(math.isfinite(v) for v in alle):
        raise ValueError("Parität nicht endlich")
    return {"schema": "richtung/1", "lauf": ri.LAUF, "variante": variante.id, "basis_variante": variante.basis_id,
            "basis_name": basis.name, "basis_parameter": basis.parameter(), "art": variante.art, "modell_art": variante.modell,
            "merkmale": list(namen), "merkmal_fenster": mf.FENSTER, "hyperparameter": ri.HYPERPARAMETER[variante.modell],
            "versionen": versionen, "datensatz_sha": hashlib.sha256(meta.datensatz_text(zeilen).encode("utf-8")).hexdigest(),
            "fenster": [f for f, p in zip(fenster, plan, strict=True) if not p["holdout"]],
            "holdout": next(f for f, p in zip(fenster, plan, strict=True) if p["holdout"]),
            "paritaet_max": max(alle) if alle else 0.0}
