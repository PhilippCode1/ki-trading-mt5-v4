"""Zeit ohne tzdata: UTC ↔ Europe/Berlin über die feste EU-Sommerzeitregel (letzter Sonntag im März 01:00 UTC bis
letzter Sonntag im Oktober 01:00 UTC). Serverzeit = UTC + gemessener Versatz (MT5 liefert Serverzeit)."""
from __future__ import annotations

import datetime as dt

UTC = dt.UTC


def _letzter_sonntag(jahr: int, monat: int) -> dt.date:
    tag = dt.date(jahr, monat, 31)
    return tag - dt.timedelta(days=(tag.weekday() + 1) % 7)


def berlin_offset(zeitpunkt_utc: dt.datetime) -> dt.timedelta:
    if zeitpunkt_utc.tzinfo is None:
        raise ValueError("UTC-Zeitpunkt ohne Zeitzone")
    t = zeitpunkt_utc.astimezone(UTC)
    beginn = dt.datetime.combine(_letzter_sonntag(t.year, 3), dt.time(1), UTC)
    ende = dt.datetime.combine(_letzter_sonntag(t.year, 10), dt.time(1), UTC)
    return dt.timedelta(hours=2 if beginn <= t < ende else 1)


def nach_berlin(zeitpunkt_utc: dt.datetime) -> dt.datetime:
    off = berlin_offset(zeitpunkt_utc)
    return (zeitpunkt_utc.astimezone(UTC) + off).replace(tzinfo=dt.timezone(off))


def berlin_tag(zeitpunkt_utc: dt.datetime) -> dt.date:
    return nach_berlin(zeitpunkt_utc).date()


def aus_epoch(sekunden: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(sekunden, UTC)
