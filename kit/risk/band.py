"""Hebelband (versiegelt, D5) für einen Betreiber: Buchhebel = Nominal / Equity (Plan F-1 §4).

Einstieg (Namensraum STRATEGIE, höchstens eine Strategieposition):
  Hebel nach dem Fill im Korridor [unten, oben] UND rechnerisch beim Kurs = TP noch ≥ unten UND beim Kurs = SL (nach Kosten)
  noch ≤ oben; zusätzlich Gesamthebel aller eigenen Positionen ≤ oben und Verlust bis SL ≤ Tagesbudget.
  Größe: kleinstes Volumen auf dem Raster, das die Untergrenzen erfüllt; jede Obergrenze und das Budget werden danach exakt
  geprüft – sonst kein Trade (nie größer als nötig).
Probe (V4): nur Obergrenze und Budget, keine Untergrenze.
Prüfpunkte (täglich und nach jedem Fill): Strategiehebel < Boden → Strategieposition glattstellen; Gesamthebel > Deckel →
  abbauen bis ≤ oben (zuerst Strategie, dann Probe). Zwangsausstiege sind eigene Ausstiegsart (BAND_BODEN, BAND_DECKEL).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from kit.domain import rounding
from kit.domain.types import ZERO, Position, Side, SymbolSpec
from kit.risk.sizing import ergebnis, kosten, nominal

UNENDLICH = Decimal("Infinity")


@dataclass(frozen=True)
class Band:
    boden: Decimal
    deckel: Decimal
    unten: Decimal
    oben: Decimal
    max_strategiepositionen: int = 1

    @classmethod
    def aus_toren(cls, t: dict) -> Band:
        b = t["band"]
        return cls(Decimal(b["boden"]), Decimal(b["deckel"]), Decimal(b["korridor_unten"]), Decimal(b["korridor_oben"]),
                   int(b["max_strategiepositionen"]))


@dataclass(frozen=True)
class Bewertet:
    """Eigene Position mit aktuellem Nominal (Kontowährung) und Restrisiko bis SL (inkl. Schließkosten)."""

    position: Position
    spec: SymbolSpec
    nominal: Decimal
    restrisiko: Decimal
    strategie: bool


@dataclass(frozen=True)
class Groesse:
    lots: Decimal | None
    grund: str
    hebel: Decimal = ZERO
    hebel_tp: Decimal = ZERO
    hebel_sl: Decimal = ZERO
    verlust_sl: Decimal = ZERO


def hebel(nominal_summe: Decimal, equity: Decimal) -> Decimal:
    return nominal_summe / equity if equity > ZERO else UNENDLICH


def _raster(lots: Decimal, spec: SymbolSpec, *, auf: bool) -> Decimal:
    schritte = (lots / spec.volume_step).to_integral_value(rounding=ROUND_CEILING if auf else ROUND_FLOOR)
    return (schritte * spec.volume_step).quantize(spec.volume_step)


def _kennzahlen(spec: SymbolSpec, waehrung: str, side: Side, einstieg: Decimal, sl: Decimal, tp: Decimal, lots: Decimal,
                equity: Decimal, provision: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    k = kosten(lots, provision)
    h0 = hebel(nominal(spec, einstieg, lots, waehrung), equity - kosten(lots, provision, 1))
    htp = hebel(nominal(spec, tp, lots, waehrung), equity + ergebnis(spec, side, einstieg, tp, lots) - k)
    verlust = -ergebnis(spec, side, einstieg, sl, lots) + k
    hsl = hebel(nominal(spec, sl, lots, waehrung), equity - verlust)
    return h0, htp, hsl, verlust


def einstieg_strategie(band: Band, spec: SymbolSpec, waehrung: str, side: Side, einstieg: Decimal, sl: Decimal, tp: Decimal, *,
                       equity: Decimal, offene: list[Bewertet], budget: Decimal, provision: Decimal) -> Groesse:
    if tp <= ZERO or not rounding.schutz_richtig(side, einstieg, sl, tp):
        return Groesse(None, "SL_TP_UNGUELTIG")
    if sum(1 for b in offene if b.strategie) >= band.max_strategiepositionen:
        return Groesse(None, "MAX_STRATEGIEPOSITIONEN")
    if equity <= ZERO:
        return Groesse(None, "EQUITY_NICHT_POSITIV")
    je_lot0 = nominal(spec, einstieg, Decimal(1), waehrung)
    je_lot_tp = nominal(spec, tp, Decimal(1), waehrung)
    gewinn_tp = ergebnis(spec, side, einstieg, tp, Decimal(1)) - kosten(Decimal(1), provision)
    if je_lot0 <= ZERO or je_lot_tp <= ZERO:
        return Groesse(None, "NOMINAL_FEHLT")
    unter0 = band.unten * equity / je_lot0
    nenner = je_lot_tp - band.unten * gewinn_tp
    if nenner <= ZERO:
        return Groesse(None, "BAND_TP_UNERREICHBAR")
    unter_tp = band.unten * equity / nenner
    lots = max(_raster(max(unter0, unter_tp), spec, auf=True), spec.volume_min)
    if lots > spec.volume_max:
        return Groesse(None, "VOLUMEN_UEBER_MAXIMUM")
    h0, htp, hsl, verlust = _kennzahlen(spec, waehrung, side, einstieg, sl, tp, lots, equity, provision)
    rest_nominal = sum((b.nominal for b in offene), ZERO)
    rest_risiko = sum((b.restrisiko for b in offene), ZERO)
    gesamt0 = hebel(rest_nominal + nominal(spec, einstieg, lots, waehrung), equity)
    gesamt_sl = hebel(rest_nominal + nominal(spec, sl, lots, waehrung), equity - verlust - rest_risiko)
    werte = {"hebel": h0, "hebel_tp": htp, "hebel_sl": hsl, "verlust_sl": verlust}
    if not (band.unten <= h0 <= band.oben) or htp < band.unten:
        return Groesse(None, "BAND_UNTERGRENZE", **werte)
    if hsl > band.oben or gesamt0 > band.oben or gesamt_sl > band.oben:
        return Groesse(None, "BAND_OBERGRENZE", **werte)
    if verlust + rest_risiko > budget:
        return Groesse(None, "TAGESBUDGET", **werte)
    return Groesse(lots, "OK", **werte)


def einstieg_probe(band: Band, spec: SymbolSpec, waehrung: str, side: Side, einstieg: Decimal, sl: Decimal, *, equity: Decimal,
                   offene: list[Bewertet], budget: Decimal, provision: Decimal) -> Groesse:
    if not rounding.schutz_richtig(side, einstieg, sl, ZERO):
        return Groesse(None, "SL_TP_UNGUELTIG")
    lots = spec.volume_min
    verlust = -ergebnis(spec, side, einstieg, sl, lots) + kosten(lots, provision)
    rest_nominal = sum((b.nominal for b in offene), ZERO)
    rest_risiko = sum((b.restrisiko for b in offene), ZERO)
    g0 = hebel(rest_nominal + nominal(spec, einstieg, lots, waehrung), equity)
    gsl = hebel(rest_nominal + nominal(spec, sl, lots, waehrung), equity - verlust - rest_risiko)
    if g0 > band.oben or gsl > band.oben:
        return Groesse(None, "BAND_OBERGRENZE", g0, ZERO, gsl, verlust)
    if verlust + rest_risiko > budget:
        return Groesse(None, "TAGESBUDGET", g0, ZERO, gsl, verlust)
    return Groesse(lots, "OK", g0, ZERO, gsl, verlust)


@dataclass(frozen=True)
class Zwang:
    ticket: int
    symbol: str
    side: Side
    lots: Decimal
    grund: str               # BAND_BODEN, BAND_DECKEL


def pruefpunkt(band: Band, offene: list[Bewertet], equity: Decimal) -> list[Zwang]:
    """Zwangsausstiege am Prüfpunkt. Nur Abbau, nie Aufbau."""
    aus: list[Zwang] = []
    strat = [b for b in offene if b.strategie]
    h_strat = hebel(sum((b.nominal for b in strat), ZERO), equity)
    if strat and h_strat < band.boden:
        aus += [Zwang(b.position.ticket, b.position.symbol, b.position.side, b.position.volume, "BAND_BODEN") for b in strat]
        return aus
    gesamt = sum((b.nominal for b in offene), ZERO)
    if hebel(gesamt, equity) <= band.deckel:
        return aus
    ueber = gesamt - band.oben * equity                    # so viel Nominal muss weg
    for b in sorted(offene, key=lambda x: (not x.strategie, -x.nominal)):
        if ueber <= ZERO:
            break
        je_lot = b.nominal / b.position.volume
        lots = min(_raster(ueber / je_lot, b.spec, auf=True), b.position.volume)
        rest = b.position.volume - lots
        if ZERO < rest < b.spec.volume_min:
            lots = b.position.volume
        aus.append(Zwang(b.position.ticket, b.position.symbol, b.position.side, lots, "BAND_DECKEL"))
        ueber -= je_lot * lots
    return aus
