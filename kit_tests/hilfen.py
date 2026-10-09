"""Gemeinsame Testbausteine: Symbolvertrag, SIM-Terminal mit Uhr, Lebenszyklus mit Journal (alles mit erfundenen Werten)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from kit.broker.sim import SimTerminal, Uhr
from kit.domain.types import KontoModus, SymbolSpec
from kit.orders.lifecycle import Lebenszyklus
from kit.state.journal import Journal

D = Decimal


def eurusd(name: str = "EURUSD", stops_level: int = 0) -> SymbolSpec:
    return SymbolSpec(name=name, digits=5, point=D("0.00001"), tick_size=D("0.00001"), tick_value=D("0.86"),
                      contract_size=D("100000"), volume_min=D("0.01"), volume_max=D("100"), volume_step=D("0.01"),
                      stops_level=stops_level, currency_profit="USD", currency_base="EUR")


def aufbau(tmp: Path, *, modus: KontoModus = KontoModus.HEDGING, provision: str = "0", symbol: str = "EURUSD",
           demo_pruefung=None) -> tuple[SimTerminal, Lebenszyklus, Uhr, Journal]:
    uhr = Uhr()
    term = SimTerminal([eurusd(symbol)], modus=modus, provision_je_lot=D(provision), uhr=uhr)
    term.setze_kurs(symbol, "1.10500", "1.10502")
    journal = Journal(tmp / "journal", uhr=uhr)
    lz = Lebenszyklus(term, journal, demo_pruefung=demo_pruefung)
    return term, lz, uhr, journal


MITTWOCH_MITTAG = 1791367200.0          # 2026-10-07 10:00 UTC = 12:00 Berlin (im Handelsfenster)


def bot_aufbau(tmp: Path, *, strategie=None, probe: bool = False, attrappe: bool = False, balance: str = "10000",
               handelsmodus=None, start: float = MITTWOCH_MITTAG):
    """Bot über dem SIM-Terminal (EUR-Konto, konsistente Tickwerte). attrappe=True: echter Adaptercode über die MT5-Attrappe."""
    from kit.broker.mt5_real import Mt5Terminal
    from kit.broker.sim_modul import SimMt5Modul
    from kit.domain.types import HandelsModus
    from kit.run.loop import Bot
    from kit.run.melder import ListenMelder
    from kit.run.trockenlauf import konfiguration, specs
    uhr = Uhr(start)
    liste, kurse = specs()
    sim = SimTerminal(liste, balance=D(balance), provision_je_lot=D("3.25"), hebel=30, uhr=uhr,
                      handelsmodus=handelsmodus or HandelsModus.DEMO)
    for name, kurs in kurse.items():
        spec = sim.specs[name]
        sim.setze_kurs(name, kurs, kurs + spec.point * 12)
    term = sim
    if attrappe:
        term = Mt5Terminal(SimMt5Modul(sim, versatz_s=10800), versatz_s=10800, schluessel_ordner=tmp / "geheim", uhr=uhr,
                           prozess_pruefen=lambda: True)
        term.verbinden()
    melder = ListenMelder()
    bot = Bot(term, tmp / "ablage", konfiguration(), modus="sim", strategie=strategie, probe=probe, melder=melder, journal_fsync=False)
    return sim, uhr, bot, melder


def kerze(sim: SimTerminal, symbol: str, zeit: int, o: str, h: str, lo: str, c: str, spread: int = 12) -> None:
    from kit.domain.types import Bar
    sim.kerze(Bar(symbol, zeit, D(o), D(h), D(lo), D(c), spread))


def ticken(sim: SimTerminal) -> None:
    """Frische Kurse (gleiche Preise, aktuelle Zeit) – plain SIM hält sonst die Zeit des letzten Kurses."""
    for name, q in list(sim._kurse.items()):
        sim.setze_kurs(name, q.bid, q.ask)
