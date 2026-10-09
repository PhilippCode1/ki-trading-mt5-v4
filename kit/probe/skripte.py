"""D-Skripte (docs/SIM_SPEC.md §8) und Killer-Tests (registers/killer_tests.json) mit deklariertem Soll-Ergebnis – für Hedging-
Demokonten. Jede Operation trägt die Kennung `SK-…` und zählt in Tor T getrennt; jedes Skript endet PASS, FAIL oder
NICHT_TESTBAR (mit Grund) und wird als SKRIPT-Satz journalisiert. Nur kleinstes Volumen, nur DEMO (Lebenszyklus-Vorrang).

Voraussetzung: der Aufrufer hält die Schreibsperre der Ablage, der Bot ist gestartet (Journal, Abgleich), der Markt ist offen.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from kit.domain import rounding
from kit.domain.types import ZERO, Absicht, Action, Namensraum, Operation, OpStatus, Position, Side
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.orders.reconcile import Abgleich
from kit.state.store import SchreiberAktiv, Schreibsperre

if TYPE_CHECKING:
    from kit.run.loop import Bot

NICHT_TESTBAR = {
    "D-02": ("KT-17", "nur Netting-Konto (Bot verlangt Hedging)"),
    "D-03": ("KT-18", "nur Netting-Konto (Bot verlangt Hedging)"),
    "D-05": ("KT-20", "Pending-Orders sind im Fast-Track nicht freigegeben"),
    "D-07": ("KT-09", "Teilausführung ist auf Demo nicht provozierbar (in T-SIM belegt)"),
    "D-08": ("KT-05", "Netztrennung wird auf Demo nicht ausgelöst (in T-SIM belegt)"),
}


@dataclass
class Schritt:
    schritt: str
    soll: str
    ist: str
    ok: bool


@dataclass
class Ergebnis:
    skript: str
    kt: list[str]
    schritte: list[Schritt] = field(default_factory=list)
    grund: str = ""

    @property
    def urteil(self) -> str:
        if self.grund:
            return "NICHT_TESTBAR"
        return "PASS" if self.schritte and all(s.ok for s in self.schritte) else "FAIL"

    def pruefe(self, name: str, soll: str, ist: object, ok: bool) -> bool:
        self.schritte.append(Schritt(name, soll, str(ist), bool(ok)))
        return bool(ok)


class SkriptGesperrt(RuntimeError):
    """Einstiege sind gesperrt (Sperre, K1, Tagesstopp, Technik-Pause) – Skripte eröffnen nichts."""


def _code(op: Operation) -> set[int]:
    codes = set(op.retcodes)
    if op.grund.startswith(("CHECK_", "RETCODE_")):
        codes.add(int(op.grund.split("_", 1)[1]))
    return codes


def _ist(op: Operation) -> str:
    """Status, Codes und Stufe (CHECK = schon order_check, SEND = erst order_send) – misst, wo der Server ablehnt."""
    stufe = "CHECK" if op.grund.startswith("CHECK_") else "SEND" if op.versuche else "-"
    return f"{op.status} {sorted(_code(op))} {stufe}"


class Skripte:
    def __init__(self, bot: Bot, symbol: str, *, warte: Callable[[float], None] = time.sleep) -> None:
        self.bot = bot
        self.t = bot.t
        self.symbol = bot.konf.broker_name(symbol)
        self.warte = warte
        self._n = 0
        self._lauf = self._neuer_lauf()

    def _neuer_lauf(self) -> str:
        """Eindeutige Kennung je Skriptlauf (sonst gilt eine Absicht aus einem früheren Lauf als erfüllt)."""
        basis = int(self.t.zeit())
        lauf, n = str(basis), 1
        while any(o.absicht.absicht_id.startswith("SK-") and o.absicht.absicht_id.endswith(f"-{lauf}")
                  for o in self.bot.lz.ops.values()):
            lauf, n = f"{basis}.{n}", n + 1
        return lauf

    # ------------------------------------------------------------------------------------------------ Hilfen
    def _op(self, kennung: str, action: Action, side: Side, lots: Decimal, sl: Decimal = ZERO, tp: Decimal = ZERO,
            ticket: int | None = None) -> Operation:
        if action is Action.ENTRY_DEAL:
            gesperrt = self.bot.einstieg_gesperrt(self.t.zeit()) or self.bot.offener_einstieg()
            if gesperrt and not gesperrt.startswith("DRILL_"):
                raise SkriptGesperrt(gesperrt)
        self._n += 1
        a = Absicht(f"SK-{kennung}-{self._lauf}", action, self.symbol, side, lots, Namensraum.PROBE, sl, tp, ticket, "Skript")
        op = self.bot.lz.ausfuehren(a, ids.client_id("SKRIPT", self.symbol, int(self.t.zeit()), kennung, self._n))
        for _ in range(70):                       # UNBEKANNT/TEILWEISE: bis zum Negativnachweis klären, nie neu senden
            if op.status not in (OpStatus.UNBEKANNT, OpStatus.TEILWEISE, OpStatus.GESENDET):
                break
            self.warte(1.0)
            self.bot.lz.klaeren()
        return op

    def _position(self, op: Operation) -> Position | None:
        for _ in range(10):
            p = next((p for p in self.t.positions() if p.magic == op.magic), None)
            if p is not None:
                return p
            self.warte(1.0)
        return None

    def _ticket_weg(self, ticket: int) -> bool:
        for _ in range(10):
            if not any(p.ticket == ticket for p in self.t.positions()):
                return True
            self.warte(1.0)
        return False

    def _schutz(self, side: Side) -> tuple[Decimal, Decimal]:
        spec = self.t.symbol(self.symbol)
        q = self.t.quote(self.symbol)
        preis = q.ask if side is Side.BUY else q.bid
        abstand = spec.point * max(spec.stops_level + 50, self.bot.konf.probe_abstand_points)
        return (rounding.sl_runden(preis - side.sign * abstand, side, spec), rounding.tp_runden(preis + side.sign * abstand, side, spec))

    def _enger(self, p: Position) -> Decimal:
        spec = self.t.symbol(self.symbol)
        return rounding.sl_runden(p.sl + p.side.sign * spec.point * self.bot.konf.probe_sl_enger_points, p.side, spec)

    def _vmin(self) -> Decimal:
        return self.t.symbol(self.symbol).volume_min

    def _markt_offen(self) -> str:
        q = self.t.quote(self.symbol)
        alter = self.t.zeit() - q.time_msc / 1000
        if alter > self.bot.konf.kursalter_s:
            return "Markt geschlossen oder Kurs veraltet"
        if alter < -2.0:
            return "Kurszeit liegt in der Zukunft – Uhrabgleich prüfen"
        return ""

    def _deal_menge(self, magic: int, seit: float) -> tuple[Decimal, set[int]]:
        deals = [d for d in self.t.deals(int(seit) - 120, int(self.t.zeit()) + 120) if d.magic == magic]
        return sum((d.volume for d in deals), ZERO), {d.position_id for d in deals}

    # ------------------------------------------------------------------------------------------------ Skripte
    def d01(self) -> Ergebnis:
        e = Ergebnis("D-01", ["KT-04", "KT-07", "KT-21", "KT-23", "KT-24"])
        e.grund = self._markt_offen()
        if e.grund:
            return e
        vmin = self._vmin()
        sl, tp = self._schutz(Side.BUY)
        t0 = self.t.zeit()
        op1 = self._op("D01-AUF", Action.ENTRY_DEAL, Side.BUY, vmin * 2, sl, tp)
        if not e.pruefe("Eröffnen 2× volume_min mit SL+TP (Füllart aus Bitmaske)", "ERLEDIGT", op1.status, op1.status is OpStatus.ERLEDIGT):
            return e
        p = self._position(op1)
        e.pruefe("Position mit SL und TP auf dem Server, magic erhalten", "SL/TP gleich Auftrag", p and (p.sl, p.tp),
                 p is not None and p.sl == sl and p.tp == tp)
        if p is None:
            return e
        latenz = None
        for _ in range(120):
            if self._deal_menge(op1.magic, t0)[0] > ZERO:
                latenz = self.t.zeit() - t0
                break
            self.warte(0.5)
        e.pruefe("KT-24 Deal in der Historie sichtbar", "< 60 s", f"{latenz} s", latenz is not None and latenz < 60)
        neu = self._enger(p)
        op2 = self._op("D01-SL", Action.PROTECT_SLTP, Side.BUY, p.volume, neu, p.tp, p.ticket)
        p2 = self._position(op1)
        e.pruefe("KT-07 SL enger, nie ohne SL", "ERLEDIGT, SL = neu", (op2.status, p2 and p2.sl),
                 op2.status is OpStatus.ERLEDIGT and p2 is not None and p2.sl == neu)
        op3 = self._op("D01-TEIL", Action.REDUCE_DEAL, Side.SELL, vmin, ticket=p.ticket)
        p3 = self._position(op1)
        e.pruefe("Teilabbau per Ticket", "ERLEDIGT, Rest = volume_min", (op3.status, p3 and p3.volume),
                 op3.status is OpStatus.ERLEDIGT and p3 is not None and p3.volume == vmin)
        op4 = self._op("D01-ZU", Action.REDUCE_DEAL, Side.SELL, vmin, ticket=p.ticket)
        e.pruefe("Vollabbau per Ticket", "ERLEDIGT, Position weg", op4.status, op4.status is OpStatus.ERLEDIGT and self._ticket_weg(p.ticket))
        for op in (op1, op3, op4):
            menge, pos_ids = self._deal_menge(op.magic, t0)
            e.pruefe(f"KT-23 Menge nur aus Deals ({op.absicht.absicht_id})", str(op.gefuellt), menge, menge == op.gefuellt)
            e.pruefe(f"KT-04 Kette Order→Deal→Position ({op.absicht.absicht_id})", str(p.ticket), sorted(pos_ids), pos_ids == {p.ticket})
        return e

    def d04(self) -> Ergebnis:
        e = Ergebnis("D-04", ["KT-19", "KT-22"])
        e.grund = self._markt_offen()
        if e.grund:
            return e
        vmin = self._vmin()
        sl, tp = self._schutz(Side.BUY)
        op_a = self._op("D04-A", Action.ENTRY_DEAL, Side.BUY, vmin, sl, tp)
        op_b = self._op("D04-B", Action.ENTRY_DEAL, Side.BUY, vmin, sl, tp)
        pa, pb = self._position(op_a), self._position(op_b)
        if not e.pruefe("Zwei gleichgerichtete Tickets", "2 Positionen", (pa and pa.ticket, pb and pb.ticket),
                        pa is not None and pb is not None and pa.ticket != pb.ticket):
            for p in (pa, pb):
                if p is not None:
                    self._op(f"D04-AUFR-{p.ticket}", Action.REDUCE_DEAL, Side.SELL, p.volume, ticket=p.ticket)
            return e
        op_x = self._op("D04-ZU-GROSS", Action.REDUCE_DEAL, Side.SELL, vmin * 2, ticket=pa.ticket)
        e.pruefe("Zu große Schließmenge", "ABGELEHNT 10013/10014/10038", _ist(op_x),
                 op_x.status is OpStatus.ABGELEHNT and bool(_code(op_x) & {10013, 10014, 10038}))
        pa_nach = next((p for p in self.t.positions() if p.ticket == pa.ticket), None)
        e.pruefe("Position nach Ablehnung unverändert", str(vmin), pa_nach and pa_nach.volume, pa_nach is not None and pa_nach.volume == vmin)
        op_a2 = self._op("D04-ZU-A", Action.REDUCE_DEAL, Side.SELL, vmin, ticket=pa.ticket)
        op_b2 = self._op("D04-ZU-B", Action.REDUCE_DEAL, Side.SELL, vmin, ticket=pb.ticket)
        e.pruefe("Schließen je Ticket", "beide ERLEDIGT, flach", (op_a2.status, op_b2.status),
                 op_a2.status is OpStatus.ERLEDIGT and op_b2.status is OpStatus.ERLEDIGT and self._ticket_weg(pa.ticket)
                 and self._ticket_weg(pb.ticket))
        return e

    def d06(self) -> Ergebnis:
        e = Ergebnis("D-06", ["KT-07", "KT-22"])
        e.grund = self._markt_offen()
        if e.grund:
            return e
        vmin = self._vmin()
        sl, tp = self._schutz(Side.BUY)
        op = self._op("D06-AUF", Action.ENTRY_DEAL, Side.BUY, vmin, sl, tp)
        p = self._position(op)
        if not e.pruefe("Eröffnen", "ERLEDIGT", op.status, op.status is OpStatus.ERLEDIGT and p is not None):
            return e
        neu = self._enger(p)
        op_t = self._op("D06-ENGER", Action.PROTECT_SLTP, Side.BUY, vmin, neu, p.tp, p.ticket)
        e.pruefe("SL verschärfen", "ERLEDIGT", op_t.status, op_t.status is OpStatus.ERLEDIGT)
        op_g = self._op("D06-GLEICH", Action.PROTECT_SLTP, Side.BUY, vmin, neu, p.tp, p.ticket)
        e.pruefe("Gleicher Wert", "10025 oder 10016 (keine Änderung)", _ist(op_g), bool(_code(op_g) & {10025, 10016}))
        p_gleich = self._position(op)
        e.pruefe("SL/TP nach gleichem Wert unverändert", str(neu), p_gleich and p_gleich.sl,
                 p_gleich is not None and p_gleich.sl == neu and p_gleich.tp == p.tp)
        q = self.t.quote(self.symbol)
        spec = self.t.symbol(self.symbol)
        falsch = rounding.sl_runden(q.bid + spec.point * self.bot.konf.probe_abstand_points, Side.SELL, spec)
        op_u = self._op("D06-UNGUELTIG", Action.PROTECT_SLTP, Side.BUY, vmin, falsch, p.tp, p.ticket)
        e.pruefe("Ungültiger SL (über Bid bei Long)", "ABGELEHNT 10016/10013", _ist(op_u),
                 op_u.status is OpStatus.ABGELEHNT and bool(_code(op_u) & {10016, 10013}))
        p_nach = self._position(op)
        e.pruefe("SL nach Ablehnung unverändert", str(neu), p_nach and p_nach.sl, p_nach is not None and p_nach.sl == neu)
        op_z = self._op("D06-ZU", Action.REDUCE_DEAL, Side.SELL, vmin, ticket=p.ticket)
        e.pruefe("Schließen", "ERLEDIGT", op_z.status, op_z.status is OpStatus.ERLEDIGT and self._ticket_weg(p.ticket))
        op_c = self._op("D06-GESCHLOSSEN", Action.PROTECT_SLTP, Side.BUY, vmin, neu, p.tp, p.ticket)
        e.pruefe("SL/TP auf geschlossenem Ticket", "ABGELEHNT 10036/10013", _ist(op_c),
                 op_c.status is OpStatus.ABGELEHNT and bool(_code(op_c) & {10036, 10013}))
        return e

    def d09(self) -> Ergebnis:
        e = Ergebnis("D-09", ["KT-05", "KT-25"])
        e.grund = self._markt_offen()
        if e.grund:
            return e
        sl, tp = self._schutz(Side.BUY)
        self._n += 1
        a = Absicht(f"SK-D09-ABSTURZ-{self._lauf}", Action.ENTRY_DEAL, self.symbol, Side.BUY, self._vmin(), Namensraum.PROBE, sl, tp,
                    grund="Skript")
        cid = ids.client_id("SKRIPT", self.symbol, int(self.t.zeit()), "D09", self._n)
        op = self.bot.lz.planen(a, cid)            # Journal geschrieben – „Absturz“ vor der Sendung
        e.pruefe("Journal vor Netz", "GEPLANT", op.status, op.status is OpStatus.GEPLANT)
        lz2 = Lebenszyklus(self.t, self.bot.journal, demo_pruefung=self.bot.demo_pruefung)
        lz2.wiederherstellen()
        op2 = lz2.ops.get(cid)
        e.pruefe("Neustart: Ausgang offen", "UNBEKANNT", op2 and op2.status, op2 is not None and op2.status is OpStatus.UNBEKANNT)
        frueh = lz2.negativnachweis(cid)
        e.pruefe("Vorzeitiger Negativnachweis", "NEGPROOF_INSUFFICIENT", frueh, frueh == "NEGPROOF_INSUFFICIENT")
        zweit = lz2.planen(a, cid + "x")
        e.pruefe("Neusenden gesperrt", "INTENT_HAS_OPEN_ATTEMPT", zweit.grund, zweit.grund == "INTENT_HAS_OPEN_ATTEMPT")
        self.warte(lz2.negativnachweis_s + 1)
        lz2.klaeren()
        e.pruefe("Negativnachweis nach Fenster", "ABGELEHNT", op2 and op2.status,
                 op2 is not None and op2.status is OpStatus.ABGELEHNT and op2.negativnachweis)
        e.pruefe("Kein Fill (nie gesendet)", "0 Positionen/Deals", self._deal_menge(op.magic, op.t_geplant)[0],
                 self._deal_menge(op.magic, op.t_geplant)[0] == ZERO and not any(p.magic == op.magic for p in self.t.positions()))
        self.bot.lz.wiederherstellen()
        self.bot._vorfaelle_gesehen = len(self.bot.lz.vorfaelle)
        return e

    def d10(self) -> Ergebnis:
        e = Ergebnis("D-10", ["KT-31", "KT-32"])
        e.grund = self._markt_offen()
        if not e.grund and any(ids.ist_eigen(p.magic) for p in self.t.positions()):
            e.grund = "eigene Positionen offen – Kill-Drill nur ohne andere eigene Positionen"
        if e.grund:
            return e
        sl, tp = self._schutz(Side.BUY)
        op = self._op("D10-AUF", Action.ENTRY_DEAL, Side.BUY, self._vmin(), sl, tp)
        p = self._position(op)
        if not e.pruefe("Eröffnen", "ERLEDIGT", op.status, op.status is OpStatus.ERLEDIGT and p is not None):
            return e
        d1 = self.bot.drill(1, schlaf=self.warte)
        e.pruefe("K1 wirksam", "≤ 5 s", f"{d1:.2f} s", d1 <= 5)
        self.bot.drill_stufe = 2
        try:
            gesperrt = self.bot.einstieg_gesperrt(self.t.zeit())
            neu = self._enger(p)
            op_s = self._op("D10-SCHUTZ-K2", Action.PROTECT_SLTP, Side.BUY, p.volume, neu, p.tp, p.ticket)
        finally:
            self.bot.drill_stufe = 0
        e.pruefe("K2: Einstiege gesperrt", "gesperrt", gesperrt, gesperrt is not None)
        e.pruefe("KT-32 Schutzrecht unter K2", "ERLEDIGT", op_s.status, op_s.status is OpStatus.ERLEDIGT)
        d2 = self.bot.drill(2, schlaf=self.warte)
        e.pruefe("K2 wirksam", "≤ 5 s", f"{d2:.2f} s", d2 <= 5)
        d3 = self.bot.drill(3, schlaf=self.warte)
        e.pruefe("K3 flach", "≤ 60 s", f"{d3:.1f} s", d3 <= 60 and not any(ids.ist_eigen(x.magic) for x in self.t.positions()))
        return e

    def d12(self) -> Ergebnis:
        e = Ergebnis("D-12", ["KT-12", "KT-16"])
        self.bot.schutz()
        assert self.bot.abgleich is not None
        frisch = Abgleich(self.bot.lz, self.bot.journal, ab_zeit=self.bot.abgleich.ab_zeit)
        b = frisch.laufen()
        e.pruefe("Wiederholte Lieferung nach Neustart", "0 neue Deals, 0 Differenzen", (b.neue_deals, b.differenzen),
                 b.neue_deals == 0 and not b.differenzen)
        try:
            with Schreibsperre(self.bot.ablage):
                zweiter = "zweiter Schreiber erhielt die Sperre"
        except SchreiberAktiv:
            zweiter = "verweigert"
        e.pruefe("KT-16 Zweiter Schreiber", "verweigert", zweiter, zweiter == "verweigert")
        return e

    # ------------------------------------------------------------------------------------------------ Ablauf
    def alle(self, nur: list[str] | None = None) -> list[Ergebnis]:
        aus = []
        self._lauf = self._neuer_lauf()
        gesperrt = self.bot.einstieg_gesperrt(self.t.zeit())
        if gesperrt:                                     # nie trotz Sperre eröffnen; laufendes K3 erst abschließen
            if self.bot._k3_aktiv():
                self.bot._k3()
            nur = nur or ["D-01", "D-04", "D-06", "D-09", "D-10", "D-12"]
        skripte = {"D-01": self.d01, "D-04": self.d04, "D-06": self.d06, "D-09": self.d09, "D-10": self.d10, "D-12": self.d12}
        for name, f in skripte.items():
            if nur and name not in nur:
                continue
            if gesperrt:
                aus.append(Ergebnis(name, [], grund=f"Einstiege gesperrt ({gesperrt})"))
                continue
            try:
                e = f()
            except SkriptGesperrt as exc:
                e = Ergebnis(name, [], grund=f"Einstiege gesperrt ({exc})")
            except Exception as exc:  # noqa: BLE001 - ein Skriptfehler ist ein Befund, kein Absturz
                e = Ergebnis(name, [])
                e.pruefe("Ausnahme", "keine", f"{type(exc).__name__}: {exc}"[:200], False)
            self.bot.schutz()
            aus.append(e)
        for skript, (kt, grund) in NICHT_TESTBAR.items():
            if not nur or skript in nur:
                aus.append(Ergebnis(skript, [kt], grund=grund))
        for e in aus:
            self.bot.journal.schreiben("SKRIPT", e.urteil, f"{e.skript}: {e.urteil}", skript=e.skript, kt=e.kt, grund=e.grund,
                                       schritte=[asdict(s) for s in e.schritte])
        return aus
