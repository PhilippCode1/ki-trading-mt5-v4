"""T-SIM (Tor T, Plan F-1 §5): zufällige Abläufe gegen den Takt mit allen Fehlerarten des SIM-Terminals, Retcodes aus der Matrix,
Spätlieferungen, SL/TP-Kerzen, entfernten Server-SL, Fremdhandel, Neustarts und Kontowechsel auf REAL.

Invarianten je Ablauf: kein Doppel-Fill; nach dem Ausklingen Journal = Broker (keine offene Operation, keine Differenz, jede
eigene Position mit Operation); keine eigene Position länger als 30 s ohne SL; auf REAL keine einzige Sendung mehr; Replay aus
dem Journal = Laufzeitstand; ein widerlegter Negativnachweis führt immer zur Sperre.

Standard: 60 Abläufe (schnell). Nachweislauf: KIT_TSIM_BEISPIELE=10000 (Bericht unter berichte/tor_t/).
"""
from __future__ import annotations

import os
from dataclasses import replace
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from kit.broker.sim import Fehler
from kit.domain.types import ZERO, Absicht, Action, HandelsModus, Namensraum, OpStatus, Side
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.orders.retcodes import tabelle
from kit.run.loop import Bot, Ende
from kit_tests.hilfen import bot_aufbau, kerze, ticken

D = Decimal
BEISPIELE = int(os.environ.get("KIT_TSIM_BEISPIELE", "60"))
CODES = sorted(tabelle())
FEHLER = st.one_of(
    st.none(), st.none(), st.none(),
    st.builds(Fehler, st.just("REJECT"), st.sampled_from(CODES)),
    st.sampled_from([Fehler("TIMEOUT_NOT_EXECUTED"), Fehler("TIMEOUT_EXECUTED"), Fehler("DISCONNECT_NOT_EXECUTED"),
                     Fehler("DISCONNECT_EXECUTED"), Fehler("DUPLICATE"), Fehler("EXCEPTION"), Fehler("PARTIAL", anteil=D("0.5")),
                     Fehler("REJECT", 10004, einmal=True), Fehler("REJECT", 10021, einmal=True)]))
SCHRITT = st.one_of(
    st.tuples(st.just("auf"), FEHLER, st.sampled_from([Side.BUY, Side.SELL]), st.sampled_from(["0.02", "0.04"])),
    st.tuples(st.just("zu"), st.integers(0, 3), FEHLER),
    st.tuples(st.just("sl"), st.integers(0, 3), FEHLER),
    st.tuples(st.just("zeit"), st.sampled_from([5, 30, 65])),
    st.tuples(st.just("spaet")),
    st.tuples(st.just("kerze"), st.integers(-60, 60)),
    st.tuples(st.just("ohne_sl"), st.integers(0, 3)),
    st.tuples(st.just("neustart")),
    st.tuples(st.just("fremd")),
    st.tuples(st.just("real")),
)


class Lauf:
    def __init__(self, tmp) -> None:
        self.sim, self.uhr, self.bot, _ = bot_aufbau(tmp)
        self.bot.starten()
        self.n = 0
        self.real_ab: int | None = None
        self.beendet = False

    def eigene(self):
        return [p for p in self.sim.positions() if ids.ist_eigen(p.magic)]

    def _senden(self, a: Absicht, fehler: Fehler | None) -> None:
        if self.beendet:
            return
        self.n += 1
        cid = ids.client_id("TSIM", a.symbol, int(self.uhr()), a.absicht_id, self.n)
        if fehler is not None:
            self.sim.setze_fehler(ids.magic(a.namensraum, cid), fehler)
        self.bot.lz.ausfuehren(a, cid)

    def schutz(self) -> None:
        if self.beendet:
            return
        try:
            self.bot.schutz()
        except Ende:
            self.beendet = True

    def zeit(self, s: int) -> None:
        for _ in range(s // 5):
            self.uhr.vor(5)
            ticken(self.sim)
            self.schutz()

    def schritt(self, s: tuple) -> None:
        art = s[0]
        q = self.sim.quote("EURUSD")
        if art == "auf":
            _, fehler, side, lots = s
            preis = q.ask if side is Side.BUY else q.bid
            sl, tp = preis - side.sign * D("0.0030"), preis + side.sign * D("0.0030")
            self._senden(Absicht(f"A{self.n}", Action.ENTRY_DEAL, "EURUSD", side, D(lots), Namensraum.PROBE, sl, tp), fehler)
        elif art in ("zu", "sl", "ohne_sl"):
            eigene = self.eigene()
            if not eigene:
                return
            p = eigene[s[1] % len(eigene)]
            if art == "zu":
                self._senden(Absicht(f"Z{p.ticket}-{self.n}", Action.REDUCE_DEAL, p.symbol, p.side.opposite, p.volume, Namensraum.PROBE,
                                     ticket=p.ticket), s[2])
            elif art == "sl" and p.sl > ZERO:
                neu = p.sl + p.side.sign * D("0.0005")
                self._senden(Absicht(f"S{p.ticket}-{self.n}", Action.PROTECT_SLTP, p.symbol, p.side, p.volume, Namensraum.PROBE, neu, p.tp,
                                     p.ticket), s[2])
            elif art == "ohne_sl":
                self.sim._pos[p.ticket] = replace(p, sl=ZERO)            # Server hat den SL verloren
        elif art == "zeit":
            self.zeit(s[1])
            return
        elif art == "spaet":
            self.sim.liefere_spaete()
        elif art == "kerze":
            mitte = q.bid
            neu = mitte + D(s[1]) * D("0.0001")
            hoch, tief = max(mitte, neu) + D("0.0002"), min(mitte, neu) - D("0.0002")
            kerze(self.sim, "EURUSD", int(self.uhr()) // 60 * 60, str(mitte), str(hoch), str(tief), str(neu))
        elif art == "neustart" and not self.beendet:
            self.bot = Bot(self.bot.t, self.bot.ablage, self.bot.konf, modus="sim", melder=self.bot.melder, journal_fsync=False)
            try:
                self.bot.starten()
            except Ende:
                self.beendet = True
        elif art == "fremd":
            self.sim.setze_kurs("GBPUSD", "1.34000", "1.34016")
            self.sim.fremder_handel("GBPUSD", Side.BUY, D("0.10"))
        elif art == "real" and self.real_ab is None:
            self.sim.handelsmodus = HandelsModus.REAL
            self.real_ab = len(self.sim.sendungen)
        self.uhr.vor(1)
        ticken(self.sim)
        self.schutz()


@settings(max_examples=BEISPIELE)
@given(st.lists(SCHRITT, min_size=3, max_size=14))
def test_tsim(tmp_path_factory, schritte):
    lauf = Lauf(tmp_path_factory.mktemp("tsim"))
    for s in schritte:
        lauf.schritt(s)
        for op in lauf.bot.lz.ops.values():                         # kein Doppel-Fill, nie mehr als beabsichtigt
            assert op.gefuellt <= op.absicht.volume
        for p in lauf.eigene():
            assert p.volume <= D("0.04")
    lauf.zeit(70)
    lauf.zeit(70)
    if lauf.real_ab is not None:
        assert len(lauf.sim.sendungen) == lauf.real_ab               # auf REAL keine einzige Sendung mehr
        return
    bot = lauf.bot
    offen = [o for o in bot.lz.ops.values() if o.status in (OpStatus.GEPLANT, OpStatus.GESENDET, OpStatus.UNBEKANNT, OpStatus.TEILWEISE)]
    assert not offen, [(o.op_id, o.status) for o in offen]
    for p in lauf.eigene():
        assert p.sl > ZERO                                             # Schutz wiederhergestellt oder Position geschlossen
        assert bot.lz.op_mit_magic(p.magic) is not None
    assert bot.abgleich is not None
    b = bot.abgleich.laufen()
    assert not b.differenzen and not b.unerwartet
    if any(v["art"] == "NEGPROOF_FALSIFIED" for v in bot.lz.vorfaelle):
        assert "NULLTOLERANZ" in bot.sperren
    replay = Lebenszyklus(bot.t, bot.journal)
    replay.wiederherstellen()
    assert {k: (o.status, o.gefuellt) for k, o in replay.ops.items()} == {k: (o.status, o.gefuellt) for k, o in bot.lz.ops.items()}
