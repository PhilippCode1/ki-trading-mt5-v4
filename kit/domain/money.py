"""Geld-Helfer: Decimal an der Grenze (float aus MT5 nur über str), Rundung auf Cent."""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")


def dez(wert: object) -> Decimal:
    """Wert verlustfrei in Decimal: float über repr/str (nie Decimal(float) mit Binärrest), Decimal bleibt, int/str direkt."""
    if isinstance(wert, Decimal):
        return wert
    if isinstance(wert, bool):
        raise TypeError("bool ist kein Geldwert")
    if isinstance(wert, float):
        return Decimal(repr(wert))
    if isinstance(wert, (int, str)):
        return Decimal(wert)
    raise TypeError(f"kein Zahlwert: {type(wert).__name__}")


def cent(wert: Decimal) -> Decimal:
    return wert.quantize(CENT, rounding=ROUND_HALF_EVEN)
