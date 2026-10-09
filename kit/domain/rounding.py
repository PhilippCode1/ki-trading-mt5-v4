"""Rundung an der Grenze zum Broker (Herkunft: mt5-trading-ai runner._quantise, stop_level_in_tickschritten, _validate_volume).

Regeln: Volumen nur abrunden (nie aufrunden), unter volume_min kein Trade; SL/TP vom Markt weg aufs Tickraster
(mehr Abstand, nie weniger Schutzabstand als geplant); Mindestabstand stops_level in Points.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from kit.domain.types import ZERO, Side, SymbolSpec


def volumen_abrunden(volumen: Decimal, spec: SymbolSpec) -> Decimal | None:
    """Abrunden auf volume_step; None, wenn das Ergebnis unter volume_min liegt (LOT_ZU_KLEIN). Deckel volume_max."""
    if volumen <= ZERO:
        return None
    schritte = (volumen / spec.volume_step).to_integral_value(rounding=ROUND_FLOOR)
    v = (schritte * spec.volume_step).quantize(spec.volume_step)
    v = min(v, (spec.volume_max / spec.volume_step).to_integral_value(rounding=ROUND_FLOOR) * spec.volume_step)
    if v < spec.volume_min:
        return None
    return v


def auf_raster(preis: Decimal, tick: Decimal, *, aufrunden: bool) -> Decimal:
    schritte = (preis / tick).to_integral_value(rounding=ROUND_CEILING if aufrunden else ROUND_FLOOR)
    return (schritte * tick).quantize(tick)


def sl_runden(sl: Decimal, side: Side, spec: SymbolSpec) -> Decimal:
    """SL vom Markt weg: Long-SL (unter dem Kurs) abrunden, Short-SL (über dem Kurs) aufrunden."""
    return auf_raster(sl, spec.tick_size, aufrunden=side is Side.SELL)


def tp_runden(tp: Decimal, side: Side, spec: SymbolSpec) -> Decimal:
    """TP vom Markt weg: Long-TP (über dem Kurs) aufrunden, Short-TP (unter dem Kurs) abrunden."""
    if tp == ZERO:
        return ZERO
    return auf_raster(tp, spec.tick_size, aufrunden=side is Side.BUY)


def abstand_ok(referenz: Decimal, ziel: Decimal, spec: SymbolSpec) -> bool:
    """Mindestabstand stops_level (Points) zwischen Referenzkurs und SL/TP."""
    if ziel == ZERO:
        return True
    return abs(referenz - ziel) >= spec.point * spec.stops_level


def schutz_richtig(side: Side, einstieg: Decimal, sl: Decimal, tp: Decimal) -> bool:
    """SL liegt auf der Verlustseite, TP (falls gesetzt) auf der Gewinnseite."""
    if sl <= ZERO:
        return False
    if side is Side.BUY:
        return sl < einstieg and (tp == ZERO or tp > einstieg)
    return sl > einstieg and (tp == ZERO or tp < einstieg)


def sl_enger(side: Side, alt: Decimal, neu: Decimal) -> bool:
    """Neuer SL ist enger (näher am Kurs) oder gleich – nie Ausweitung."""
    if alt == ZERO:
        return neu > ZERO
    return neu >= alt if side is Side.BUY else neu <= alt
