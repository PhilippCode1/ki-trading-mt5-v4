"""Schnelle Ausstiegsrechnung mit genau den Regeln von SIM und Takt – für die Parität (Takt gegen direkte Rechnung) und die
Zufallsbasis des Trade-Tests (zufällige Richtung, gleiche Einstiegszeiten, komplette Ausstiegslogik, ≥ 1.000 Wiederholungen).

Regeln (kit.broker.sim.SimTerminal.kerze, kit.run.loop.Bot.handel, kit.backtest.runner):
- Schritte = H1-Schlüsse aller Symbole. Je Schritt zuerst die Kerze des Symbols (falls vorhanden): Lücke über SL bzw. TP → Eröffnungskurs,
  sonst SL vor TP innerhalb der Kerze; Kauf löst am Bid (Kerze), Verkauf am Ask (Kerze + Spread) aus.
- Danach Zeitbarriere: jetzt − Eröffnung ≥ max_halte_s → Schließen zum aktuellen Kurs des Symbols (Kauf Bid, Verkauf Ask).
- Ergebnis in EUR wie der SIM: Gewinn = Cent(Δ/tick · Tickwert · Lots), Tickwert bei SL/TP vom Schritt davor, bei der Zeitbarriere
  vom aktuellen Schritt; Kommission je Seite Cent(Provision · Lots); Swap je Servertageswechsel Cent(Swap je Lot · Lots · Faktor),
  ein Wechsel genau beim Schluss zählt nur bei der Zeitbarriere (Rollover vor dem Takt, nach der Kerze).
Nicht nachgebildet: Zwangsausstiege des Takts (Band-Prüfpunkt, K3) – sie erscheinen in der Parität als Abweichung mit Grund.
"""
from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from kit.backtest import kosten
from kit.backtest.kosten import Kostenprofil
from kit.backtest.terminal import TF_S, punkt
from kit.domain.money import cent
from kit.domain.types import ZERO, Bar, Side

H1_S = TF_S["H1"]
D = Decimal


@dataclass(frozen=True)
class Ausgang:
    t: int
    preis: Decimal
    grund: str                     # "SL", "TP", "ZEITBARRIERE", "OFFEN" (Datenende)
    ergebnis: Decimal = ZERO       # EUR inkl. Kommission und Swap
    gewinn_brutto: Decimal = ZERO
    swap: Decimal = ZERO


class Markt:
    """Kerzen (H1, Spread nach Kostenprofil), Schrittzeiten und Umrechnungskurse wie im Runner."""

    def __init__(self, h1: Mapping[str, Sequence[Bar]], kostenprofil: Kostenprofil, *, versatz_s: int = 10800) -> None:
        self.profil = kostenprofil
        self.versatz_s = versatz_s
        self.kerzen = {s: list(k) for s, k in h1.items()}
        self.schluss = {s: [b.time + H1_S for b in k] for s, k in self.kerzen.items()}
        self.schritte = sorted({t for z in self.schluss.values() for t in z})
        self._mitten: dict[str, tuple[list[int], list[Decimal]]] = {}
        for s in kosten.UMRECHNUNGSKURSE:
            if s in self.kerzen:
                self._mitten[s] = (self.schluss[s], [b.close + self.spread(b) / 2 for b in self.kerzen[s]])

    def spread(self, b: Bar) -> Decimal:
        return punkt(b.symbol) * self.profil.spread_points(b.spread_points)

    def kurs(self, symbol: str, t: int) -> tuple[Decimal, Decimal] | None:
        """(Bid, Ask) nach dem Schritt t: Schluss der letzten Kerze mit Schluss ≤ t."""
        i = bisect.bisect_right(self.schluss[symbol], t) - 1
        if i < 0:
            return None
        b = self.kerzen[symbol][i]
        return b.close, b.close + self.spread(b)

    def eur(self, waehrung: str, t: int, *, inklusive: bool) -> Decimal | None:
        """EUR je Einheit nach dem letzten Umrechnungsstand: Kerzen mit Schluss ≤ t (inklusive) bzw. < t."""
        mitten: dict[str, Decimal] = {}
        for s, (zeiten, werte) in self._mitten.items():
            i = (bisect.bisect_right(zeiten, t) if inklusive else bisect.bisect_left(zeiten, t)) - 1
            if i >= 0:
                mitten[s] = werte[i]
        return kosten.eur_je_einheit(waehrung, mitten)

    def tickwert(self, symbol: str, t: int, *, inklusive: bool) -> Decimal:
        p = punkt(symbol)
        eur = self.eur(symbol[3:6], t, inklusive=inklusive)
        if eur is None:
            raise ValueError(f"{symbol}: kein Umrechnungskurs bei {t}")
        return kosten.tickwert(p, D(100000), eur)


def _treffer(b: Bar, side: Side, sl: Decimal, tp: Decimal, spread: Decimal) -> tuple[Decimal, str] | None:
    """Reihenfolge wie SimTerminal.kerze: Lücke am Eröffnungskurs (SL, dann TP), dann innerhalb der Kerze SL vor TP."""
    if side is Side.BUY:
        o, h, lo = b.open, b.high, b.low
        faelle = ((sl > ZERO and o <= sl, o, "SL"), (tp > ZERO and o >= tp, o, "TP"), (sl > ZERO and lo <= sl, sl, "SL"),
                  (tp > ZERO and h >= tp, tp, "TP"))
    else:
        o, h, lo = b.open + spread, b.high + spread, b.low + spread
        faelle = ((sl > ZERO and o >= sl, o, "SL"), (tp > ZERO and o <= tp, o, "TP"), (sl > ZERO and h >= sl, sl, "SL"),
                  (tp > ZERO and lo <= tp, tp, "TP"))
    for getroffen, preis, grund in faelle:
        if getroffen:
            return preis, grund
    return None


def simulieren(m: Markt, symbol: str, side: Side, preis_auf: Decimal, sl: Decimal, tp: Decimal, lots: Decimal, t_auf: int,
               max_halte_s: float | None) -> Ausgang:
    """Ausstieg und EUR-Ergebnis einer Position, eröffnet beim Schritt t_auf zum Kurs preis_auf."""
    schluss, kerzen = m.schluss[symbol], m.kerzen[symbol]
    k = bisect.bisect_right(schluss, t_auf)
    i = bisect.bisect_right(m.schritte, t_auf)
    aus: tuple[int, Decimal, str] | None = None
    while i < len(m.schritte):
        jetzt = m.schritte[i]
        if k < len(kerzen) and schluss[k] == jetzt:
            b = kerzen[k]
            k += 1
            t = _treffer(b, side, sl, tp, m.spread(b))
            if t is not None:
                aus = (jetzt, t[0], t[1])
                break
        if max_halte_s and jetzt - t_auf >= max_halte_s:
            q = m.kurs(symbol, jetzt)
            assert q is not None
            aus = (jetzt, q[0] if side is Side.BUY else q[1], "ZEITBARRIERE")
            break
        i += 1
    if aus is None:
        return Ausgang(m.schritte[-1] if m.schritte else t_auf, ZERO, "OFFEN")
    t_zu, preis_zu, grund = aus
    tv = m.tickwert(symbol, t_zu, inklusive=grund == "ZEITBARRIERE")
    p = punkt(symbol)
    brutto = cent((preis_zu - preis_auf) * side.sign / p * tv * lots)
    provision = -cent(m.profil.provision() * lots) * 2
    swap = _swap(m, symbol, side, lots, t_auf, t_zu, grund)
    return Ausgang(t_zu, preis_zu, grund, brutto + provision + swap, brutto, swap)


def _swap(m: Markt, symbol: str, side: Side, lots: Decimal, t_auf: int, t_zu: int, grund: str) -> Decimal:
    summe = ZERO
    punkte = m.profil.swap(symbol, side)
    if punkte == ZERO:
        return ZERO
    p = punkt(symbol)
    for b in kosten.servertag_wechsel(t_auf, t_zu, m.versatz_s):
        if b == t_zu and grund != "ZEITBARRIERE":
            continue                                          # SL/TP in der Kerze vor dem Wechsel: Rollover danach
        # Umrechnung wie im Runner: Wechsel auf einem Schritt nach dessen Kerzen, Wechsel in einer Lücke mit dem Stand davor –
        # beides sind die Kerzen mit Schluss ≤ b.
        eur = m.eur(symbol[3:6], b, inklusive=True) or ZERO
        faktor = kosten.swap_faktor(kosten.wochentag_der_nacht(b, m.versatz_s), m.profil.dreifachtag)
        summe += cent(kosten.swap_je_lot(punkte, p, D(100000), eur) * lots * faktor)
    return summe


def zufallspaar(m: Markt, symbol: str, t_auf: int, sl_abstand: Decimal, tp_abstand: Decimal, lots: Decimal,
                max_halte_s: float | None) -> tuple[bool, bool]:
    """(Gewinn bei Kauf, Gewinn bei Verkauf) zur selben Einstiegszeit mit denselben Abständen (Zufallsbasis)."""
    q = m.kurs(symbol, t_auf)
    if q is None:
        raise ValueError(f"{symbol}: kein Kurs bei {t_auf}")
    bid, ask = q
    kauf = simulieren(m, symbol, Side.BUY, ask, ask - sl_abstand, ask + tp_abstand, lots, t_auf, max_halte_s)
    verkauf = simulieren(m, symbol, Side.SELL, bid, bid + sl_abstand, bid - tp_abstand, lots, t_auf, max_halte_s)
    return kauf.ergebnis > ZERO, verkauf.ergebnis > ZERO
