"""Probe-Mechanik (Plan F-1 §4, Tor T): je Probe-Symbol höchstens ein Zyklus je `takt_min` Minuten:
Öffnen (volume_min, SL+TP im Auftrag) → nach `sl_enger_nach_s` SL enger ziehen → nach `schliessen_nach_s` per Ticket schließen.

- Eigener magic-Namensraum PROBE; zählt nie für Trefferquoten-Tore.
- Unbedingte DEMO-Prüfung über Takt und Lebenszyklus (auch ein offener Live-Riegel ändert daran nichts).
- Einstiege nur über die gemeinsamen Wächter, Sperren, Tagesbudget und Band-Obergrenze (V4: keine Untergrenze).
- Zustandslos über Neustarts: Phase ergibt sich aus Alter und SL der offenen Probe-Position.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kit.domain import rounding
from kit.domain.types import ZERO, Absicht, Action, Namensraum, OpStatus, Position, Side
from kit.orders import ids
from kit.risk import band as bandmod
from kit.risk import guards, limits, sizing

if TYPE_CHECKING:
    from kit.run.loop import Bot


class ProbeMechanik:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.naechster: dict[str, float] = {}
        self.zyklen = 0

    def _abstand(self, spec) -> object:
        return spec.point * max(spec.stops_level + 50, self.bot.konf.probe_abstand_points)

    def schritt(self, jetzt: float) -> None:
        bot, t, konf = self.bot, self.bot.t, self.bot.konf
        eigene = [p for p in t.positions() if ids.namensraum(p.magic) is Namensraum.PROBE]
        for p in eigene:
            alter = jetzt - p.time
            if alter >= konf.probe_schliessen_nach_s:
                bot.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.PROBE, "PROBE_ZU")
            elif alter >= konf.probe_sl_enger_nach_s:
                self._enger(p)
        belegt = {p.symbol for p in eigene} | {o.absicht.symbol for o in bot.lz.offene()}
        for sym in konf.probe_symbole:
            name = konf.broker_name(sym)
            if name in belegt or jetzt < self.naechster.get(name, 0.0):
                continue
            self.eroeffnen(name, jetzt)

    def eroeffnen(self, name: str, jetzt: float, *, side: Side | None = None, kennung: str = "") -> object:
        bot, t = self.bot, self.bot.t
        self.naechster[name] = jetzt + bot.konf.probe_takt_min * 60
        side = side or (Side.BUY if self.zyklen % 2 == 0 else Side.SELL)
        konto = bot._konto()
        spec = t.symbol(name)
        q = t.quote(name)
        kerzen = [b for b in t.bars(name, "M1", int(jetzt - 3600), int(jetzt)) if b.is_closed]
        grund = bot.einstieg_gesperrt(jetzt) or bot.offener_einstieg() or \
            guards.einstieg(jetzt, konto, spec, q, kerzen, bot.konf, bot.margin_min)
        preis = q.ask if side is Side.BUY else q.bid
        abstand = self._abstand(spec)
        sl = rounding.sl_runden(preis - side.sign * abstand, side, spec)
        tp = rounding.tp_runden(preis + side.sign * abstand, side, spec)
        if not grund:
            grund = sizing.gegenprobe(spec, bot.umrechnung(konto.currency, spec.currency_profit))
        if not grund:
            g = bandmod.einstieg_probe(bot.band, spec, konto.currency, side, preis, sl, equity=konto.equity,
                                       offene=bot.bewertet(konto.currency),
                                       budget=limits.budget(bot.tag_anker, konto.equity, bot.budget_prozent),
                                       provision=bot.konf.provision_je_lot_seite)
            grund = "" if g.lots is not None else g.grund
        if grund:
            bot._signal_eintrag(Namensraum.PROBE, name, side, "ABGELEHNT", grund)
            return None
        self.zyklen += 1
        a = Absicht(kennung or f"P-{name}-{int(jetzt)}", Action.ENTRY_DEAL, name, side, spec.volume_min, Namensraum.PROBE, sl, tp,
                    grund="Probe")
        op = bot.lz.ausfuehren(a, ids.client_id("PROBE", name, int(jetzt), "ENTRY", self.zyklen))
        bot._signal_eintrag(Namensraum.PROBE, name, side, str(op.status), op.grund, operation=op.op_id)
        if op.status is not OpStatus.LOKAL_ABGELEHNT:
            bot._fill = True
        return op

    def ziel_sl(self, p: Position) -> object:
        spec = self.bot.t.symbol(p.symbol)
        enger = spec.point * self.bot.konf.probe_sl_enger_points
        return rounding.sl_runden(p.price_open - p.side.sign * (self._abstand(spec) - enger), p.side, spec)

    def _enger(self, p: Position) -> None:
        bot, t = self.bot, self.bot.t
        neu = self.ziel_sl(p)
        if p.sl == neu or not rounding.sl_enger(p.side, p.sl, neu):
            return
        absicht_id = f"PS-{p.ticket}"
        if any(o.absicht.absicht_id == absicht_id and o.status is not OpStatus.LOKAL_ABGELEHNT for o in bot.lz.ops.values()):
            return
        spec = t.symbol(p.symbol)
        q = t.quote(p.symbol)
        kurs = q.bid if p.side is Side.BUY else q.ask
        if not rounding.schutz_richtig(p.side, kurs, neu, ZERO) or not rounding.abstand_ok(kurs, neu, spec):
            return                                   # Kurs schon zu nah am neuen SL – nicht ändern, Zyklus schließt planmäßig
        a = Absicht(absicht_id, Action.PROTECT_SLTP, p.symbol, p.side, p.volume, Namensraum.PROBE, neu, p.tp, p.ticket, "Probe SL enger")
        bot.lz.ausfuehren(a, ids.client_id("PROBE", p.symbol, p.ticket, "SLTP"))
