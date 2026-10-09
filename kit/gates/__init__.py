"""Tore (Plan F-1 §5): eingefrorene Schwellen aus config/tore.toml (SHA-256-gepinnt), Tor T, später Trade-Test und Demo-Live."""
from __future__ import annotations

import hashlib
import tomllib
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TORE_PFAD = ROOT / "config" / "tore.toml"
TORE_SHA256 = "a80e29d94cb8d2a8dbd409f9a9398f840b0acef231b25446ae70d3ca27ed69f8"


class ToreVeraendert(RuntimeError):
    """config/tore.toml weicht vom eingefrorenen Stand ab – nichts läuft (fail-closed)."""


def tore(pfad: Path | None = None) -> dict:
    roh = (pfad or TORE_PFAD).read_bytes()
    if hashlib.sha256(roh).hexdigest() != TORE_SHA256:
        raise ToreVeraendert("config/tore.toml weicht vom eingefrorenen Stand ab (SHA-256) – Änderungen nur durch den Betreiber.")
    return tomllib.loads(roh.decode("utf-8"))


def d(wert: object) -> Decimal:
    return Decimal(str(wert))
