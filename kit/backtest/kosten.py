"""Kostenmodell des Backtests (Plan F-1 §5, Prereg F-04 §1): Spread, Kommission, Swap und Umrechnung in die Kontowährung EUR.

Konventionen (wie referenz/reference/economics/costs.py; Differenztest kit_tests/differenz_v4/test_kosten_referenz.py):
- Spread = voller Spread in Preiseinheiten (Kerzenfeld spread in Points · point). Im Takt steckt er im Kurs: Kauf zum Ask = Bid + Spread,
  Verkauf zum Bid, Short-SL/TP lösen am Ask aus. seitenkosten() weist ihn für Bericht, Zufallsreferenz und Handrechnung aus:
  je Seite halber Spread · pv, pv = Tickwert / Tickgröße (Wert einer Preiseinheit je Lot in EUR).
- Kommission je Lot und Seite in EUR (Deal-Feld commission; der SIM rundet je Deal auf Cent).
- Swap: MT5-Swappunkte je Lot und Nacht (long, short) · point · Kontraktgröße in der Gewinnwährung, in EUR zum Kurs des Rollovers;
  gebucht zum Servertageswechsel für die Nacht des endenden Servertags: Mo, Di, Do, Fr ×1, Mi ×3 (Dreifachtag), Sa/So 0.
- Umrechnung: EUR je Einheit der Gewinnwährung aus Mittelkursen: USD = 1/EURUSD, JPY = 1/(EURUSD · USDJPY) (Kreuzkurs EURJPY).
  Tickwert (EUR je Tick und Lot) = Tickgröße · Kontraktgröße · EUR je Einheit, auf 8 Nachkommastellen gerundet (Bankrundung).
- Kosten × f (Gegenprobe): Spread × f (auf ganze Points aufgerundet), Kommission × f, Swap-Belastungen × f (Gutschriften bleiben).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal

from kit.domain.types import ZERO, Side

UTC = dt.UTC
EINS = Decimal(1)
TAG_S = 86400
TICKWERT_STELLEN = Decimal("0.00000001")
UMRECHNUNGSKURSE = ("EURUSD", "USDJPY")


@dataclass(frozen=True)
class Kostenprofil:
    name: str
    provision_je_lot_seite: Decimal = ZERO                                   # EUR je Lot und Seite
    swap_punkte: Mapping[str, tuple[Decimal, Decimal]] = field(default_factory=dict)   # Symbol → (long, short) Punkte je Lot und Nacht
    dreifachtag: int = 2                                                     # 0 = Montag; Mittwoch = Dreifachswap
    faktor: Decimal = EINS                                                   # Kosten × f (Gegenprobe)
    fx_gebuehr: Decimal = ZERO                                               # Umrechnungsgebühr auf Fremdwährungsbeträge (Demo: 0)

    def mal(self, f: Decimal | str | int, name: str | None = None) -> Kostenprofil:
        return replace(self, faktor=self.faktor * Decimal(str(f)), name=name or f"{self.name} x{f}")

    def provision(self) -> Decimal:
        return self.provision_je_lot_seite * self.faktor

    def spread_points(self, roh: int) -> int:
        if self.faktor == EINS:
            return roh
        return int((Decimal(roh) * self.faktor).to_integral_value(rounding=ROUND_CEILING))

    def swap(self, symbol: str, side: Side) -> Decimal:
        """Swappunkte je Lot und Nacht für die Richtung; Belastungen (negativ) werden mit dem Faktor verschärft."""
        lang, kurz = self.swap_punkte.get(symbol, (ZERO, ZERO))
        p = lang if side is Side.BUY else kurz
        return p * self.faktor if p < ZERO else p

    def beschreibung(self) -> dict:
        """JSON-taugliche Beschreibung (Versuchsprotokoll, Bericht)."""
        return {"name": self.name, "provision_je_lot_seite": str(self.provision_je_lot_seite), "faktor": str(self.faktor),
                "dreifachtag": self.dreifachtag, "fx_gebuehr": str(self.fx_gebuehr),
                "swap_punkte": {s: [str(a), str(b)] for s, (a, b) in sorted(self.swap_punkte.items())}}

    @classmethod
    def aus_dict(cls, d: Mapping) -> Kostenprofil:
        return cls(name=str(d["name"]), provision_je_lot_seite=Decimal(str(d.get("provision_je_lot_seite", "0"))),
                   swap_punkte={s: (Decimal(str(w[0])), Decimal(str(w[1]))) for s, w in dict(d.get("swap_punkte", {})).items()},
                   dreifachtag=int(d.get("dreifachtag", 2)), faktor=Decimal(str(d.get("faktor", "1"))),
                   fx_gebuehr=Decimal(str(d.get("fx_gebuehr", "0"))))


def mitte(bid: Decimal, ask: Decimal) -> Decimal:
    return (bid + ask) / 2


def eur_je_einheit(waehrung: str, mitten: Mapping[str, Decimal]) -> Decimal | None:
    """EUR je Einheit der Gewinnwährung aus Mittelkursen (EUR-Konto); None = Kurs fehlt (fail-closed beim Aufrufer)."""
    if waehrung == "EUR":
        return EINS
    eurusd = mitten.get("EURUSD")
    if waehrung == "USD":
        return EINS / eurusd if eurusd and eurusd > ZERO else None
    if waehrung == "JPY":
        eurjpy = kreuzkurs_eurjpy(mitten)
        return EINS / eurjpy if eurjpy else None
    return None


def kreuzkurs_eurjpy(mitten: Mapping[str, Decimal]) -> Decimal | None:
    eurusd, usdjpy = mitten.get("EURUSD"), mitten.get("USDJPY")
    if not eurusd or not usdjpy or eurusd <= ZERO or usdjpy <= ZERO:
        return None
    return eurusd * usdjpy


def tickwert(tick_size: Decimal, contract_size: Decimal, eur: Decimal) -> Decimal:
    """EUR je Tick und Lot (wie MT5 SYMBOL_TRADE_TICK_VALUE auf einem EUR-Konto)."""
    return (tick_size * contract_size * eur).quantize(TICKWERT_STELLEN, rounding=ROUND_HALF_EVEN)


def seitenkosten(spread_preis: Decimal, tick_size: Decimal, tick_value: Decimal, lots: Decimal, provision: Decimal,
                 fx_gebuehr: Decimal = ZERO) -> Decimal:
    """Kosten einer Seite in EUR: halber Spread · pv (mit Umrechnungsgebühr) + Kommission je Lot."""
    pv = tick_value / tick_size
    return lots * (spread_preis / 2 * pv * (EINS + fx_gebuehr) + provision)


def rundreise(spread_preis: Decimal, tick_size: Decimal, tick_value: Decimal, lots: Decimal, provision: Decimal,
              fx_gebuehr: Decimal = ZERO) -> Decimal:
    return 2 * seitenkosten(spread_preis, tick_size, tick_value, lots, provision, fx_gebuehr)


def swap_je_lot(punkte: Decimal, point: Decimal, contract_size: Decimal, eur: Decimal) -> Decimal:
    """Swap je Lot und Nacht in EUR (ungerundet; der SIM rundet je Position und Nacht auf Cent)."""
    return punkte * point * contract_size * eur


def swap_faktor(wochentag: int, dreifachtag: int = 2) -> int:
    """Nächte je Servertag (0 = Montag): Wochenende 0, Dreifachtag 3, sonst 1 (wie costs.swap_day_factor)."""
    if wochentag in (5, 6):
        return 0
    return 3 if wochentag == dreifachtag else 1


def servertag_wechsel(von: float, bis: float, versatz_s: int) -> list[int]:
    """UTC-Zeitpunkte B mit von < B ≤ bis, an denen ein Servertag beginnt (Serverzeit 00:00)."""
    erster = int((von + versatz_s) // TAG_S + 1) * TAG_S - versatz_s
    return list(range(erster, int(bis) + 1, TAG_S))


def wochentag_der_nacht(wechsel: int, versatz_s: int) -> int:
    """Wochentag des Servertags, der am Wechsel endet (die Nacht, für die der Swap gebucht wird)."""
    return dt.datetime.fromtimestamp(wechsel + versatz_s - 1, UTC).weekday()
