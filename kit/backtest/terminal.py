"""BacktestTerminal: das SIM-Terminal (kit.broker.sim, unverändert) mit den Ergänzungen für Historienkerzen.

- Verträge der 7 FX-Symbole wie im Rauchtest (Tick = Point, Kontrakt 100.000, Volumen 0,01/0,01/500, stops_level 0); Gewinnwährung
  aus dem Namen. Die Tickwerte folgen dem Kurs: nach jedem Schritt aus den Mittelkursen von EURUSD und USDJPY (kosten.tickwert).
  Ergebnisse von SL/TP-Ausführungen innerhalb einer Kerze rechnen mit dem Tickwert vom Schluss davor (kein Vorgriff).
- Kreuzkurs EURJPY als nicht handelbares Hilfssymbol (Handelsmodus DISABLED), damit die Tickwert-Gegenprobe des Takts für JPY-Paare
  einen Umrechnungskurs findet – wie im echten Terminal.
- Kerzen je Zeitrahmen: H1 sind die abgespielten Kerzen (SL/TP-Auslösung). Höhere Zeitrahmen (H4) kommen erst mit ihrem Schluss
  in den Speicher. bars() liefert nie eine Kerze, deren Schluss nach der Uhr liegt (Vorgriffsprüfung, fail-closed).
  Eine H4-Kerze trägt den Spread der H1-Kerze mit demselben Schluss (der Quote, zu der der Takt einsteigt), damit der erwartete
  Einstieg e der Strategie (Schluss + Spread) gleich dem Fill ist wie bei H1 (Review F-04); fehlt diese H1-Kerze, bleibt ihr eigener.
- Spread je Kerze aus den Daten, mit dem Kostenfaktor verschärft; Kommission je Deal (Kostenprofil); Swap per swap_buchen().
- Serverversatz fest (versatz_s), wie bei der Umrechnung der Kerzenzeiten beim Datenabzug.
"""
from __future__ import annotations

import bisect
from collections.abc import Callable, Iterable
from dataclasses import replace
from decimal import Decimal

from kit.backtest import kosten
from kit.backtest.kosten import Kostenprofil
from kit.broker.sim import SimTerminal
from kit.domain.types import ZERO, Bar, HandelsModus, KontoModus, OrderRequest, SendResult, Side, SymbolSpec

TF_S = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
H1 = "H1"
D = Decimal


class VorgriffFehler(RuntimeError):
    """Eine Kerze wäre vor ihrem Schluss sichtbar geworden (Look-ahead) – der Backtest bricht ab."""


def punkt(symbol: str) -> Decimal:
    return D("0.001") if symbol.endswith("JPY") else D("0.00001")


def vertrag(symbol: str, tick_value: Decimal = ZERO, *, handelbar: bool = True) -> SymbolSpec:
    """Vertrag wie im Rauchtest (docs/bot/RAUCHTEST.md); tick_value folgt im Lauf dem Kurs."""
    p = punkt(symbol)
    return SymbolSpec(name=symbol, digits=3 if symbol.endswith("JPY") else 5, point=p, tick_size=p, tick_value=tick_value,
                      contract_size=D(100000), volume_min=D("0.01"), volume_max=D(500), volume_step=D("0.01"), stops_level=0,
                      filling="FOK", trade_mode="FULL" if handelbar else "DISABLED", currency_profit=symbol[3:6], currency_base=symbol[:3])


class BacktestTerminal(SimTerminal):
    def __init__(self, symbole: Iterable[str], *, kostenprofil: Kostenprofil, balance: Decimal, uhr: Callable[[], float],
                 hebel: int = 100, versatz_s: int = 10800) -> None:
        liste = [vertrag(s) for s in symbole]
        if any(s.currency_profit == "JPY" for s in liste) and "EURJPY" not in {s.name for s in liste}:
            liste.append(vertrag("EURJPY", handelbar=False))
        super().__init__(liste, modus=KontoModus.HEDGING, handelsmodus=HandelsModus.DEMO, balance=balance, waehrung="EUR",
                         provision_je_lot=kostenprofil.provision(), hebel=hebel, uhr=uhr)
        self.kostenprofil = kostenprofil
        self.versatz_s = float(versatz_s)                 # vom Takt gelesen (Servertag, Tagesanker)
        self.mitten: dict[str, Decimal] = {}
        self.eroeffnung: dict[int, SymbolSpec] = {}       # Positionsticket → Vertrag (Tickwert) bei Eröffnung
        self._tf: dict[tuple[str, str], list[Bar]] = {}
        self._tf_zeiten: dict[tuple[str, str], list[int]] = {}

    # ------------------------------------------------------------------------------------------------ Kerzen
    def kerze_spielen(self, bar: Bar) -> list:
        """H1-Kerze abspielen (SL/TP nach SIM-Regeln); Spread mit dem Kostenfaktor."""
        spread = self.kostenprofil.spread_points(bar.spread_points)
        if spread != bar.spread_points:
            bar = replace(bar, spread_points=spread)
        if bar.time + TF_S[H1] > self.uhr() + 1e-9:
            raise VorgriffFehler(f"{bar.symbol}: H1-Kerze {bar.time} vor ihrem Schluss abgespielt")
        return self.kerze(bar)

    def zeitrahmen_kerze(self, bar: Bar, zeitrahmen: str) -> None:
        """Abgeschlossene Kerze eines höheren Zeitrahmens in den Speicher (erst ab ihrem Schluss sichtbar)."""
        if bar.time + TF_S[zeitrahmen] > self.uhr() + 1e-9:
            raise VorgriffFehler(f"{bar.symbol}: {zeitrahmen}-Kerze {bar.time} vor ihrem Schluss eingestellt")
        h1 = self._bars.get(bar.symbol)
        if h1 and h1[-1].time + TF_S[H1] == bar.time + TF_S[zeitrahmen]:
            spread = h1[-1].spread_points                 # schon mit dem Kostenfaktor
        else:
            spread = self.kostenprofil.spread_points(bar.spread_points)
        if spread != bar.spread_points:
            bar = replace(bar, spread_points=spread)
        schluessel = (bar.symbol, zeitrahmen)
        zeiten = self._tf_zeiten.setdefault(schluessel, [])
        if zeiten and bar.time <= zeiten[-1]:
            raise ValueError(f"{bar.symbol} {zeitrahmen}: Kerzen nicht aufsteigend")
        zeiten.append(bar.time)
        self._tf.setdefault(schluessel, []).append(bar)

    def bars(self, name: str, timeframe: str, start: int, ende: int) -> list[Bar]:
        if timeframe == H1:
            aus = super().bars(name, timeframe, start, ende)
        else:
            zeiten = self._tf_zeiten.get((name, timeframe), [])
            liste = self._tf.get((name, timeframe), [])
            aus = liste[bisect.bisect_left(zeiten, start):bisect.bisect_right(zeiten, ende)]
        if aus and aus[-1].time + TF_S[timeframe] > self.uhr() + 1e-9:
            raise VorgriffFehler(f"{name} {timeframe}: Kerze {aus[-1].time} ist noch nicht abgeschlossen")
        return aus

    # ------------------------------------------------------------------------------------------------ Umrechnung, Swap
    def umrechnung_aktualisieren(self) -> None:
        """Mittelkurse der Umrechnungssymbole aus den aktuellen Kursen; Kreuzkurs EURJPY; Tickwerte aller Symbole."""
        for s in kosten.UMRECHNUNGSKURSE:
            q = self._kurse.get(s)
            if q is not None:
                self.mitten[s] = kosten.mitte(q.bid, q.ask)
        eurjpy = kosten.kreuzkurs_eurjpy(self.mitten)
        if eurjpy is not None and "EURJPY" in self.specs:
            self.setze_kurs("EURJPY", eurjpy, eurjpy)
        for name, spec in list(self.specs.items()):
            eur = kosten.eur_je_einheit(spec.currency_profit, self.mitten)
            if eur is None:
                continue
            tv = kosten.tickwert(spec.tick_size, spec.contract_size, eur)
            if tv != spec.tick_value:
                self.specs[name] = replace(spec, tick_value=tv)

    def swap_buchen(self, faktor: int) -> None:
        """Rollover für alle offenen Positionen: Swappunkte des Profils, umgerechnet zum aktuellen Kurs."""
        if faktor <= 0 or not self._pos:
            return
        je_lot: dict[str, tuple[Decimal, Decimal]] = {}
        for p in self._pos.values():
            if p.symbol in je_lot:
                continue
            spec = self.specs[p.symbol]
            eur = kosten.eur_je_einheit(spec.currency_profit, self.mitten) or ZERO
            je_lot[p.symbol] = (kosten.swap_je_lot(self.kostenprofil.swap(p.symbol, Side.BUY), spec.point, spec.contract_size, eur),
                                kosten.swap_je_lot(self.kostenprofil.swap(p.symbol, Side.SELL), spec.point, spec.contract_size, eur))
        self.rollover(je_lot, faktor)

    # ------------------------------------------------------------------------------------------------ Eröffnung (Vertrag merken)
    def _eroeffnen(self, req: OrderRequest, spec: SymbolSpec, anteil: Decimal | None) -> SendResult:
        res = super()._eroeffnen(req, spec, anteil)
        if res.order:
            self.eroeffnung[res.order] = self.specs[req.symbol]
        return res
