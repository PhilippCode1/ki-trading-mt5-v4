"""Pin der Forschungskopien (kit/research/stats.py, trials.py): Bytes = Spalte „SHA-256 Kopie“ in kit/research/HERKUNFT.md.

Öffentlich (braucht nur kit/); der Vergleich mit den Originalen unter referenz/ liegt in differenz_v4/test_forschung_referenz.py.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from kit.research import stats, trials

FORSCHUNG = Path(__file__).resolve().parents[1] / "kit" / "research"
KOPIEN = ("stats.py", "trials.py")


def _tabelle() -> dict[str, dict[str, str]]:
    """Zeilen der Herkunftstabelle als {Datei: {Spalte: Wert}} (Backticks entfernt)."""
    zeilen = [z.strip() for z in (FORSCHUNG / "HERKUNFT.md").read_text(encoding="utf-8").splitlines() if z.strip().startswith("|")]
    kopf = [s.strip() for s in zeilen[0].strip("|").split("|")]
    out = {}
    for z in zeilen[2:]:
        werte = [s.strip().strip("`") for s in z.strip("|").split("|")]
        eintrag = dict(zip(kopf, werte, strict=True))
        out[eintrag["Datei"]] = eintrag
    return out


def test_kopien_haben_den_gepinnten_sha():
    tabelle = _tabelle()
    assert set(KOPIEN) <= set(tabelle)
    for name in KOPIEN:
        soll = tabelle[name]["SHA-256 Kopie"]
        assert re.fullmatch(r"[0-9a-f]{64}", soll), name
        assert hashlib.sha256((FORSCHUNG / name).read_bytes()).hexdigest() == soll, f"{name} weicht vom Pin ab"


def test_kopfkommentar_nennt_den_quell_sha():
    tabelle = _tabelle()
    for name in KOPIEN:
        text = (FORSCHUNG / name).read_text(encoding="utf-8")
        kopf = "".join(z for z in text.splitlines() if z.startswith("#")).replace("# ", "").replace("#", "")
        assert text.startswith("# Herkunft: ") and tabelle[name]["SHA-256 Quelle"] in kopf


def test_stats_importiert_die_kit_kopie_von_trials():
    baum = ast.parse((FORSCHUNG / "stats.py").read_text(encoding="utf-8"))
    module = {k.module for k in ast.walk(baum) if isinstance(k, ast.ImportFrom)}
    module |= {a.name for k in ast.walk(baum) if isinstance(k, ast.Import) for a in k.names}
    assert "kit.research" in module
    assert not any(m and m.split(".")[0] in ("reference", "referenz", "oracles") for m in module)
    assert stats._trials_mod is trials
