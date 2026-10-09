"""Vorregistrierte Rückkehr-Strategien F-04 (docs/bot/prereg/F04_ENTWURF.md §2–3, keine Handelsidee mit belegtem Vorteil):
S-REV-01 Rückkehr zum Mittelwert (H1) und S-REV-02 Fehlausbruch zurück in die Spanne (H4).

Die Strategie liefert nur Richtung, Server-SL und Server-TP absolut auf dem Tickraster; Größe, Band, Budget, Handelsfenster und
die Prüfung Stop ≤ 3 × Ziel gehören dem Takt. Indikatoren rechnen in float, Ticks und Preise in Decimal.
Gemeinsam: e = erwarteter Einstieg (Kauf close + spread·punkt = Ask, Verkauf close = Bid), Ziel tp_ticks = ceil(z_tp·ATR/punkt)
(mindestens 1, Ceil über Decimal(repr(z_tp·ATR)) – die Division durch die Zehnerpotenz punkt ist exakt), TP = e ± tp_ticks·punkt.
ATR = Wilder (n 14) über das übergebene Fenster. Kein Signal bei zu kurzem Fenster oder ATR ≤ 0 bzw. nicht endlich."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from kit.domain.types import Bar, Side
from kit.strategy.base import Signal, Strategie

SYMBOLE = ("EURUSD", "USDJPY", "GBPUSD", "CHFJPY", "CADJPY", "AUDUSD", "NZDUSD")
_PUNKT_JPY = Decimal("0.001")
_PUNKT = Decimal("0.00001")


def punkt(symbol: str) -> Decimal:
    """Tickgröße = Point: 0.001 für *JPY, sonst 0.00001."""
    return _PUNKT_JPY if symbol.endswith("JPY") else _PUNKT


def wilder_atr(kerzen: Sequence[Bar], n: int = 14) -> list[float | None]:
    """Wilder-ATR über das Fenster: TR_0 = H−L, sonst max(H−L, |H−C_vor|, |L−C_vor|); Start = Mittel der ersten n TR (Index n−1),
    danach ((n−1)·ATR + TR)/n. Vor dem Start None."""
    out: list[float | None] = []
    trs: list[float] = []
    atr: float | None = None
    vor: float | None = None
    for b in kerzen:
        h, lo = float(b.high), float(b.low)
        tr = h - lo if vor is None else max(h - lo, abs(h - vor), abs(lo - vor))
        vor = float(b.close)
        if atr is None:
            trs.append(tr)
            if len(trs) == n:
                atr = sum(trs) / n
        else:
            atr = ((n - 1) * atr + tr) / n
        out.append(atr)
    return out


def _atr_t(kerzen: Sequence[Bar], n: int) -> float | None:
    """ATR an der letzten Kerze; None, wenn nicht verfügbar, ≤ 0 oder nicht endlich."""
    atr = wilder_atr(kerzen, n)[-1] if kerzen else None
    return atr if atr is not None and math.isfinite(atr) and atr > 0 else None


def _ziel_ticks(abstand: float, p: Decimal) -> int:
    """ceil(abstand/punkt), mindestens 1 Tick."""
    return max(1, int((Decimal(repr(abstand)) / p).to_integral_value(rounding=ROUND_CEILING)))


def _einstieg(k: Bar, side: Side, p: Decimal) -> Decimal:
    """Kurs, den Takt und SIM verwenden: Kauf zum Ask (close + spread·punkt), Verkauf zum Bid (close)."""
    return k.close + k.spread_points * p if side is Side.BUY else k.close


def _band(werte: list[float], k: float) -> tuple[float, float, float]:
    """(unten, oben, σ) aus Mittel und Populations-Standardabweichung (ddof 0)."""
    n = len(werte)
    mittel = sum(werte) / n
    sigma = math.sqrt(sum([(x - mittel) * (x - mittel) for x in werte]) / n)
    return mittel - k * sigma, mittel + k * sigma, sigma


@dataclass
class MittelwertRueckkehr:
    """S-REV-01 (H1): Long, wenn der Schluss erstmals unter SMA − k·σ fällt (Vorkerze noch ≥ ihrem Band), Short spiegelbildlich.
    SMA/σ der Schlusskurse über n Kerzen inkl. t. TP = e ± ceil(z_tp·ATR) Ticks, SL = e ∓ r·tp_ticks Ticks (Stop/Ziel = r exakt)."""

    n: int = 48
    k: float = 2.0
    z_tp: float = 0.5
    r: int = 2
    atr_n: int = 14
    symbole: tuple[str, ...] = SYMBOLE
    zeitrahmen: str = "H1"
    rueckblick: int = 250
    max_halte_s: float | None = 86400.0
    name: str = "S-REV-01"

    def parameter(self) -> dict:
        return {"n": str(self.n), "k": str(self.k), "z_tp": str(self.z_tp), "r": str(self.r), "atr_n": str(self.atr_n),
                "rueckblick": str(self.rueckblick), "max_halte_s": str(self.max_halte_s)}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        n = self.n
        if len(kerzen) < max(self.rueckblick, n + 1):
            return None
        c = [float(b.close) for b in kerzen[-n - 1:]]          # Schlüsse t−n … t
        basis = c[0]
        d = [x - basis for x in c]                               # verschoben: konstante Reihe → σ exakt 0
        unten, oben, sigma = _band(d[1:], self.k)               # t−n+1 … t
        if sigma <= 0 or unten <= d[-1] <= oben:                # Nullvola oder Schluss im Band (häufigster Fall): früh raus
            return None
        unten_v, oben_v, _ = _band(d[:-1], self.k)               # t−n … t−1
        if d[-1] < unten and d[-2] >= unten_v:
            side = Side.BUY
        elif d[-1] > oben and d[-2] <= oben_v:
            side = Side.SELL
        else:
            return None
        atr = _atr_t(kerzen, self.atr_n)
        if atr is None:
            return None
        p = punkt(symbol)
        kt = kerzen[-1]
        e = _einstieg(kt, side, p)
        tp_ticks = _ziel_ticks(self.z_tp * atr, p)
        tp = e + side.sign * tp_ticks * p
        sl = e - side.sign * (self.r * tp_ticks) * p
        return Signal(symbol, side, sl, tp, kt.time, f"S-REV-01 k={self.k:.1f} z={self.z_tp:.2f} r={self.r}"[:40])


@dataclass
class Fehlausbruch:
    """S-REV-02 (H4): Spanne H/Lo = max(high)/min(low) der L Kerzen vor t (ohne t). Short, wenn high_t > H und close_t < H;
    Long, wenn low_t < Lo und close_t > Lo; beides zugleich → kein Signal. SL = Extrem von t ± sl_puffer·ATR, vom Markt weg aufs
    Raster. Ein Signal mit |e − SL| > max_stop_ziel·|TP − e| wird trotzdem geliefert: der Takt lehnt es mit STOP_ZU_ZIEL ab und
    journalisiert die Ablehnung (zählt in der Quote Signal → Trade); max_stop_ziel ist hier nur dokumentiert (geht in den Hash)."""

    L: int = 20
    z_tp: float = 0.5
    sl_puffer: float = 0.1
    max_stop_ziel: int = 3
    atr_n: int = 14
    symbole: tuple[str, ...] = SYMBOLE
    zeitrahmen: str = "H4"
    rueckblick: int = 250
    max_halte_s: float | None = 86400.0
    name: str = "S-REV-02"

    def parameter(self) -> dict:
        return {"L": str(self.L), "z_tp": str(self.z_tp), "sl_puffer": str(self.sl_puffer), "max_stop_ziel": str(self.max_stop_ziel),
                "atr_n": str(self.atr_n), "rueckblick": str(self.rueckblick), "max_halte_s": str(self.max_halte_s)}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        if len(kerzen) < max(self.rueckblick, self.L + 1):
            return None
        spanne = kerzen[-self.L - 1:-1]                           # t−L … t−1 (Decimal-Vergleiche, exakt)
        hoch = max(b.high for b in spanne)
        tief = min(b.low for b in spanne)
        kt = kerzen[-1]
        kurz = kt.high > hoch and kt.close < hoch
        lang = kt.low < tief and kt.close > tief
        if kurz == lang:                                         # keins oder beides zugleich
            return None
        atr = _atr_t(kerzen, self.atr_n)
        if atr is None:
            return None
        p = punkt(symbol)
        side = Side.BUY if lang else Side.SELL
        e = _einstieg(kt, side, p)
        tp = e + side.sign * _ziel_ticks(self.z_tp * atr, p) * p
        puffer = Decimal(repr(self.sl_puffer * atr))
        if lang:
            sl = ((kt.low - puffer) / p).to_integral_value(rounding=ROUND_FLOOR) * p
        else:
            sl = ((kt.high + puffer) / p).to_integral_value(rounding=ROUND_CEILING) * p
        return Signal(symbol, side, sl, tp, kt.time, f"S-REV-02 L={self.L} z={self.z_tp:.1f}"[:40])


def signale(strategie: Strategie, symbol: str, kerzen: Sequence[Bar]) -> list[Signal | None]:
    """Signalfolge über eine ganze Kerzenreihe, genau wie der Takt ruft: je Index i das Fenster der letzten rueckblick Kerzen bis i."""
    rb = strategie.rueckblick
    kerzen = list(kerzen)
    return [strategie.signal(symbol, kerzen[max(0, i - rb + 1):i + 1]) for i in range(len(kerzen))]
