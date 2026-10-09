"""Einstiegswächter (nur risikoerhöhend; Schutz und Abbau laufen immer). Reihenfolge: Demo-Vorrang zuerst.

Kursalter, Fehlkurs-Korridor um den letzten Schluss, Spread gegen den Median der letzten Kerzen, Handelsfenster
(Europe/Berlin, Mo–Fr, freitags früher Schluss), Margin-Level.
"""
from __future__ import annotations

import datetime as dt
import statistics
from decimal import Decimal

from kit.config import Konfiguration
from kit.domain.types import ZERO, AccountSnapshot, Bar, HandelsModus, Quote, SymbolSpec
from kit.domain.zeit import nach_berlin

UTC = dt.UTC


def _uhrzeit(text: str) -> dt.time:
    h, m = text.split(":")
    return dt.time(int(h), int(m))


def im_fenster(jetzt_utc: float, konf: Konfiguration) -> bool:
    b = nach_berlin(dt.datetime.fromtimestamp(jetzt_utc, UTC))
    if b.weekday() >= 5:
        return False
    bis = _uhrzeit(konf.freitag_bis) if b.weekday() == 4 else _uhrzeit(konf.fenster_bis)
    return _uhrzeit(konf.fenster_von) <= b.time() < bis


def einstieg(jetzt_utc: float, konto: AccountSnapshot, spec: SymbolSpec, q: Quote, kerzen: list[Bar], konf: Konfiguration,
             margin_min: Decimal) -> str | None:
    """None = Einstieg erlaubt, sonst Grund."""
    if konto.trade_mode is not HandelsModus.DEMO:
        return "NICHT_DEMO"
    if not konto.trade_allowed:
        return "HANDEL_NICHT_ERLAUBT"
    if spec.trade_mode != "FULL":
        return f"SYMBOL_{spec.trade_mode}"
    if not im_fenster(jetzt_utc, konf):
        return "AUSSERHALB_FENSTER"
    alter = jetzt_utc - q.time_msc / 1000
    if alter > konf.kursalter_s:
        return "KURS_ALT"
    if alter < -2.0:
        return "KURS_ZEIT_UNSTIMMIG"                   # Uhr läuft hinter dem Server: Alter wäre nicht messbar
    if q.bid <= ZERO or q.ask < q.bid:
        return "KURS_UNGUELTIG"
    if kerzen:
        schluss = kerzen[-1].close
        mitte = (q.bid + q.ask) / 2
        if schluss > ZERO and abs(mitte - schluss) / schluss * 100 > konf.korridor_prozent:
            return "KURS_AUSSER_KORRIDOR"
        spreads = [b.spread_points for b in kerzen[-50:] if b.spread_points > 0]
        if spreads:
            median = Decimal(str(statistics.median(spreads)))
            if (q.ask - q.bid) / spec.point > konf.spread_faktor * median:
                return "SPREAD_HOCH"
    if konto.margin_level > ZERO and konto.margin_level < margin_min:
        return "MARGIN_NIEDRIG"
    return None
