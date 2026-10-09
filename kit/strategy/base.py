"""Schnittstelle zwischen Strategie und Takt. Die Strategie entscheidet nur Richtung, SL und TP; Größe, Band, Budget, Sperren
und Ausführung gehören dem Takt. strategie_hash bindet Zählungen (Tore 85/95/50) an Code und Parameter."""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from kit.domain.types import Bar, Side


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    sl: Decimal
    tp: Decimal
    kerze: int                 # Beginn der Signalkerze (UTC, s) – macht die Auftragskennung stabil über Neustarts
    grund: str = ""


class Strategie(Protocol):
    name: str
    zeitrahmen: str            # z. B. "H1"
    rueckblick: int            # benötigte abgeschlossene Kerzen
    symbole: tuple[str, ...]
    max_halte_s: float | None  # Zeitbarriere (None = nur SL/TP); der Takt schließt per Ticket

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None: ...

    def parameter(self) -> dict: ...


def strategie_hash(s: Strategie) -> str:
    quelle = inspect.getsource(inspect.getmodule(type(s)) or type(s))
    felder = {k: v for k, v in vars(s).items() if not k.startswith("_")}       # alle Einstellungen inkl. Zeitbarriere
    roh = json.dumps({"name": s.name, "zeitrahmen": s.zeitrahmen, "rueckblick": s.rueckblick, "symbole": list(s.symbole),
                      "max_halte_s": getattr(s, "max_halte_s", None), "felder": felder, "parameter": s.parameter(),
                      "quelle": quelle}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()
