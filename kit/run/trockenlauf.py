"""Trockenlauf (Plan F-1, F-03 Aufgabe 6): der komplette Takt mit echtem Adaptercode (MT5-Attrappe über dem SIM-Terminal) und
beschleunigter Uhr – Probe-Mechanik und Attrappen-Strategie zugleich, Wochenende, Mittwochs-Rollover (Dreifachswap) mit
offener Position und ein Neustart mitten im Lauf. Ergebnis: Tor-T-Auswertung (0 Defekte gefordert) und Replay = Abgleich.

Kein Markt, keine Handelsidee: Kurse sind ein festgelegter Zufallspfad (Saat), die Strategie ist eine Attrappe.
"""
from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from kit import live_guard
from kit.broker.mt5_real import Mt5Terminal
from kit.broker.sim import SimTerminal, Uhr
from kit.broker.sim_modul import SimMt5Modul
from kit.config import Konfiguration
from kit.domain.types import Bar, OpStatus, SymbolSpec
from kit.gates import tore
from kit.gates.tor_t import auswerten
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.orders.reconcile import Abgleich
from kit.run.loop import Bot
from kit.run.melder import ListenMelder
from kit.state.journal import Journal
from kit.state.store import Schreibsperre
from kit.strategy.attrappe import Attrappe

UTC = dt.UTC
D = Decimal
VERSATZ_S = 3 * 3600                           # Serverzeit = UTC+3 (übliche Sommerzeit-Zone der Broker)
START = dt.datetime(2026, 10, 7, 5, 0, tzinfo=UTC)   # Mittwoch
SWAP = {"EURUSD": (D("-7.5"), D("2.1")), "GBPUSD": (D("-4.2"), D("-1.3")), "USDJPY": (D("9.8"), D("-21.4")),
        "EURJPY": (D("4.1"), D("-15.0"))}


def specs() -> tuple[list[SymbolSpec], dict[str, Decimal]]:
    """Konsistente Verträge für ein EUR-Konto (Tickwerte passen zu den Startkursen – Gegenprobe besteht)."""
    kurse = {"EURUSD": D("1.16300"), "GBPUSD": D("1.34000"), "USDJPY": D("148.000"), "EURJPY": D("172.100")}
    usd = D("0.00001") * 100000 / kurse["EURUSD"]
    jpy = D("0.001") * 100000 / kurse["EURJPY"]

    def fx(name: str, digits: int, tick: Decimal, wert: Decimal, basis: str, gewinn: str) -> SymbolSpec:
        return SymbolSpec(name=name, digits=digits, point=tick, tick_size=tick, tick_value=wert.quantize(D("0.00001")),
                          contract_size=D(100000), volume_min=D("0.01"), volume_max=D(100), volume_step=D("0.01"), stops_level=10,
                          filling="IOC", currency_profit=gewinn, currency_base=basis)
    return ([fx("EURUSD", 5, D("0.00001"), usd, "EUR", "USD"), fx("GBPUSD", 5, D("0.00001"), usd, "GBP", "USD"),
             fx("USDJPY", 3, D("0.001"), jpy, "USD", "JPY"), fx("EURJPY", 3, D("0.001"), jpy, "EUR", "JPY")], kurse)


class Markt:
    """Zufallspfad je Symbol (Minutenkerzen, Bid); Wochenende ohne Kerzen, Lücke zur Wiedereröffnung; Rollover um Server-00:00."""

    def __init__(self, sim: SimTerminal, kurse: dict[str, Decimal], saat: int, sigma: float = 0.00012) -> None:
        self.sim = sim
        self.kurs = {k: float(v) for k, v in kurse.items()}
        self.zufall = random.Random(saat)
        self.sigma = sigma
        self.spread = {"EURUSD": 12, "GBPUSD": 16, "USDJPY": 14, "EURJPY": 20}
        self.letzte_minute: int | None = None
        self.rollover: list[tuple[str, int, bool]] = []          # (Servertag, Faktor, eigene Position offen)
        self.war_zu = False
        for s, k in self.kurs.items():
            self._kurs_setzen(s, k)

    @staticmethod
    def offen(t: float) -> bool:
        w = dt.datetime.fromtimestamp(t, UTC)
        return not (w.weekday() == 5 or (w.weekday() == 4 and w.hour >= 21) or (w.weekday() == 6 and w.hour < 21))

    def _kurs_setzen(self, s: str, k: float) -> None:
        spec = self.sim.specs[s]
        bid = D(str(round(k, spec.digits)))
        self.sim.setze_kurs(s, bid, bid + spec.point * self.spread[s])

    def takt(self, t: float) -> None:
        minute = int(t // 60)
        if self.letzte_minute is None:
            self.letzte_minute = minute
            return
        while self.letzte_minute < minute:
            beginn = self.letzte_minute * 60
            self.letzte_minute += 1
            server = dt.datetime.fromtimestamp(beginn + 60 + VERSATZ_S, UTC)
            if server.hour == 0 and server.minute == 0 and server.weekday() in (1, 2, 3, 4, 5):
                faktor = 3 if server.weekday() == 3 else 1            # Nacht Mi → Do: Dreifachswap
                offen = any(ids.ist_eigen(p.magic) for p in self.sim.positions())
                self.sim.rollover(SWAP, faktor)
                self.rollover.append(((server - dt.timedelta(days=1)).date().isoformat(), faktor, offen))
            if not self.offen(beginn):
                self.war_zu = True
                continue
            for s in self.kurs:
                spec = self.sim.specs[s]
                o = self.kurs[s]
                if self.war_zu:
                    o *= 1 + self.zufall.choice((-1, 1)) * 0.002          # Wochenend-Lücke
                schritte = [o]
                for _ in range(4):
                    schritte.append(schritte[-1] * math.exp(self.zufall.gauss(0.0, self.sigma / 2)))
                c = schritte[-1]
                rund = spec.digits
                bar = Bar(s, beginn, D(str(round(o, rund))), D(str(round(max(schritte), rund))), D(str(round(min(schritte), rund))),
                          D(str(round(c, rund))), self.spread[s])
                self.sim.kerze(bar)
                self.kurs[s] = c
            self.war_zu = False


@dataclass
class Ergebnis:
    von: str
    bis: str
    schritte: int = 0
    neustarts: int = 0
    tor_t: dict = field(default_factory=dict)
    trades: int = 0
    rollover: list = field(default_factory=list)
    wochenende: bool = False
    replay_gleich: bool = False
    replay_abweichungen: list = field(default_factory=list)
    abgleich_differenzen: list = field(default_factory=list)
    sperren: list = field(default_factory=list)
    meldungen: int = 0

    @property
    def ok(self) -> bool:
        return (not self.tor_t.get("defekte") and self.replay_gleich and not self.abgleich_differenzen and not self.sperren
                and self.tor_t.get("urteil") in ("LAEUFT", "BESTANDEN"))


def konfiguration() -> Konfiguration:
    return Konfiguration("", ("EURUSD", "GBPUSD"), ("EURUSD", "GBPUSD", "USDJPY"), probe_takt_min=10.0)


def laufen(ablage: Path, *, start: dt.datetime = START, tage: float = 7.0, schritt_s: float = 1.0, saat: int = 7,
           neustart_nach_tagen: float | None = 2.3) -> Ergebnis:
    uhr = Uhr(start.timestamp())
    liste, kurse = specs()
    sim = SimTerminal(liste, balance=D(10000), provision_je_lot=D("3.25"), hebel=30, uhr=uhr)
    markt = Markt(sim, kurse, saat)
    modul = SimMt5Modul(sim, versatz_s=VERSATZ_S)
    term = Mt5Terminal(modul, versatz_s=VERSATZ_S, schluessel_ordner=ablage / "geheim", uhr=uhr, prozess_pruefen=lambda: True)
    term.verbinden()
    freigaben = ablage / "freigaben"
    live_guard.konto_registrieren(term, freigaben)
    pruefung = live_guard.demo_pruefung(term, freigaben)
    konf = konfiguration()
    melder = ListenMelder()
    strategie = Attrappe(symbole=("EURUSD", "GBPUSD"), abstand=240, sl_prozent=D("0.45"), tp_prozent=D("0.35"))
    ende = start.timestamp() + tage * 86400
    neustart = start.timestamp() + neustart_nach_tagen * 86400 if neustart_nach_tagen else None
    erg = Ergebnis(start.isoformat(), dt.datetime.fromtimestamp(ende, UTC).isoformat())

    def neuer_bot() -> Bot:
        b = Bot(term, ablage / "bot", konf, modus="trocken", strategie=strategie, probe=True, demo_pruefung=pruefung, melder=melder,
                journal_fsync=False)
        b.starten()
        return b

    with Schreibsperre(ablage / "bot"):
        bot = neuer_bot()
        while uhr() < ende:
            markt.takt(uhr())
            bot.schritt()
            erg.schritte += 1
            if neustart is not None and uhr() >= neustart:
                neustart = None
                erg.neustarts += 1
                bot = neuer_bot()                 # Prozessneustart: alles aus Journal und Zustand
            uhr.vor(schritt_s)
        bot.schutz()
        saetze = bot.journal.lesen()
        erg.tor_t = auswerten(saetze, tore()["tor_t"], mechanik=bot.mechanik, jetzt=uhr())
        erg.trades = len(bot.buch.geschlossene())
        erg.sperren = sorted(bot.sperren)
        lz2 = Lebenszyklus(term, Journal(ablage / "bot" / "journal", uhr=uhr, fsync=False), demo_pruefung=pruefung)
        lz2.wiederherstellen()
        for oid, op in bot.lz.ops.items():
            nach = lz2.ops.get(oid)
            if nach is None or (nach.status, nach.gefuellt) != (op.status, op.gefuellt):
                erg.replay_abweichungen.append(f"{oid}: {op.status}/{op.gefuellt} ≠ {nach and nach.status}/{nach and nach.gefuellt}")
        erg.replay_gleich = not erg.replay_abweichungen and len(lz2.ops) == len(bot.lz.ops) and \
            not any(o.status in (OpStatus.GEPLANT, OpStatus.GESENDET) for o in lz2.ops.values())
        assert bot.abgleich is not None
        erg.abgleich_differenzen = Abgleich(lz2, lz2.j, ab_zeit=bot.abgleich.ab_zeit).laufen().differenzen
    erg.rollover = markt.rollover
    erg.wochenende = any(not Markt.offen(start.timestamp() + h * 3600) for h in range(int(tage * 24)))
    erg.meldungen = len(melder.meldungen)
    return erg
