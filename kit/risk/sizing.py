"""Nominal, Gewinn/Verlust und Tickwert-Gegenprobe (Herkunft: mt5-trading-ai risk/sizing.py und waehrung.py, gekürzt).

- Nominal in Kontowährung: ist die Basiswährung die Kontowährung (EURUSD auf EUR-Konto), ist das Nominal je Lot die
  Kontraktgröße; sonst Preis / Tickgröße × Tickwert (der Tickwert enthält die Umrechnung zum aktuellen Kurs).
- Gewinn/Verlust: Kursabstand / Tickgröße × Tickwert × Lots (lineare FX-/CFD-Verträge).
- Gegenprobe: Tickwert muss zu Tickgröße × Kontraktgröße × Umrechnung (aus einem Kreuzkurs) passen, sonst kein Einstieg.
"""
from __future__ import annotations

from decimal import Decimal

from kit.domain.types import ZERO, Side, SymbolSpec

GEGENPROBE_TOLERANZ = Decimal("0.03")


def nominal(spec: SymbolSpec, preis: Decimal, lots: Decimal, waehrung: str) -> Decimal:
    if spec.currency_base == waehrung:
        return spec.contract_size * lots
    return preis / spec.tick_size * spec.tick_value * lots


def ergebnis(spec: SymbolSpec, side: Side, einstieg: Decimal, kurs: Decimal, lots: Decimal) -> Decimal:
    """Gewinn (+) bzw. Verlust (−) in Kontowährung, ohne Kosten."""
    return (kurs - einstieg) * side.sign / spec.tick_size * spec.tick_value * lots


def kosten(lots: Decimal, provision_je_lot_seite: Decimal, seiten: int = 2) -> Decimal:
    return lots * provision_je_lot_seite * seiten


def umrechnung_aus_kurs(waehrung: str, gewinnwaehrung: str, symbol: str, bid: Decimal, ask: Decimal) -> Decimal | None:
    """Kontowährung je Einheit der Gewinnwährung aus dem Kurs eines Kreuzsymbols (KONTO+GEWINN oder GEWINN+KONTO)."""
    mitte = (bid + ask) / 2
    if mitte <= ZERO:
        return None
    if symbol.startswith(waehrung) and gewinnwaehrung in symbol[len(waehrung):]:
        return 1 / mitte
    if symbol.startswith(gewinnwaehrung) and waehrung in symbol[len(gewinnwaehrung):]:
        return mitte
    return None


def gegenprobe(spec: SymbolSpec, umrechnung: Decimal | None) -> str | None:
    """None = Tickwert plausibel; sonst Grund. Ohne Umrechnung (Kreuzkurs fehlt) fail-closed."""
    if spec.tick_value <= ZERO or spec.tick_size <= ZERO or spec.contract_size <= ZERO:
        return "TICKWERT_FEHLT"
    if umrechnung is None:
        return "UMRECHNUNG_FEHLT"
    erwartet = spec.tick_size * spec.contract_size * umrechnung
    if abs(spec.tick_value - erwartet) > erwartet * GEGENPROBE_TOLERANZ:
        return "TICKWERT_UNPLAUSIBEL"
    return None
