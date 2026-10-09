"""Differenztests gegen die eingefrorene v4-Referenz: referenz/ auf den Importpfad (reference.*, oracles.*)."""
from __future__ import annotations

import sys
from pathlib import Path

REFERENZ = str(Path(__file__).resolve().parents[2] / "referenz")
if REFERENZ not in sys.path:
    sys.path.insert(0, REFERENZ)
