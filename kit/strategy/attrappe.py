"""Attrappen-Strategie NUR für Trockenlauf und Tests (keine Handelsidee, kein Vorteil): alle `abstand` Kerzen ein Signal mit
abwechselnder Richtung, SL/TP in festen Prozentabständen. Zählt nie für ein Tor (eigener strategie_hash)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kit.domain.types import Bar, Side
from kit.strategy.base import Signal


@dataclass
class Attrappe:
    symbole: tuple[str, ...] = ("EURUSD",)
    zeitrahmen: str = "M1"
    rueckblick: int = 5
    abstand: int = 240
    sl_prozent: Decimal = Decimal("0.25")
    tp_prozent: Decimal = Decimal("0.20")
    name: str = "ATTRAPPE"
    max_halte_s: float | None = None

    def parameter(self) -> dict:
        return {"abstand": self.abstand, "sl_prozent": str(self.sl_prozent), "tp_prozent": str(self.tp_prozent)}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        if len(kerzen) < self.rueckblick:
            return None
        k = kerzen[-1]
        nummer = k.time // 60
        if nummer % self.abstand:
            return None
        side = Side.BUY if (nummer // self.abstand) % 2 == 0 else Side.SELL
        sl = k.close * (1 - side.sign * self.sl_prozent / 100)
        tp = k.close * (1 + side.sign * self.tp_prozent / 100)
        return Signal(symbol, side, sl, tp, k.time, "Attrappe")
