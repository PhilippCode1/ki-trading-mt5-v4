"""SIM-Terminal: preisfähiger Test-Broker mit MT5-naher Kontosemantik (Herkunft: v4 reference/moneypath/sim.py für Fehlerarten
und Netting/Hedging, mt5-trading-ai venue/fake.py für die Naht; neu: Kerzenpfad mit SL/TP-Auslösung).

- Hedging: jede Eröffnung ein eigenes Ticket (Positions-ID = Order-Ticket); Schließen nur per Ticket.
- Netting: eine Position je Symbol; gleichgerichtet = IN, gegenläufig = OUT bzw. INOUT.
- Kerzen sind Bid-Kurse; Short-Positionen schließen zum Ask (Bid + Spread). SL vor TP in derselben Kerze; Lücke über den
  SL hinweg füllt zum (schlechteren) Eröffnungskurs.
- Fehlerinjektion je magic: REJECT(code), TIMEOUT_NOT_EXECUTED, TIMEOUT_EXECUTED, DISCONNECT_NOT_EXECUTED,
  DISCONNECT_EXECUTED, PARTIAL(anteil), DUPLICATE, EXCEPTION. *_EXECUTED wird erst mit liefere_spaete() sichtbar.
- Swap: rollover() belastet offene Positionen je Lot (Dreifachtag per Faktor); gebucht wird er wie bei MT5 erst im
  Schließ-Deal (Feld swap), die Equity enthält ihn sofort (Netting-Teilschlüsse ohne Swap – Bot verlangt Hedging).
"""
from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, Decimal

from kit.broker.seam import BrokerFehler
from kit.domain.money import cent, dez
from kit.domain.types import (
    ZERO,
    AccountSnapshot,
    Action,
    Bar,
    CheckResult,
    Deal,
    DealArt,
    HandelsModus,
    KontoModus,
    OrderRequest,
    PendingOrder,
    Position,
    Quote,
    SendResult,
    Side,
    SymbolSpec,
)

FEHLERARTEN = frozenset({"REJECT", "TIMEOUT_NOT_EXECUTED", "TIMEOUT_EXECUTED", "DISCONNECT_NOT_EXECUTED", "DISCONNECT_EXECUTED",
                         "PARTIAL", "DUPLICATE", "EXCEPTION", "DOPPELT_AUSGEFUEHRT"})


class Uhr:
    """Simulierte Uhr (Sekunden)."""

    def __init__(self, start: float = 1_790_000_000.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def vor(self, sekunden: float) -> None:
        self.t += sekunden


@dataclass(frozen=True)
class Fehler:
    art: str
    code: int | None = None
    anteil: Decimal | None = None
    einmal: bool = False

    def __post_init__(self) -> None:
        if self.art not in FEHLERARTEN:
            raise ValueError(f"unbekannte Fehlerart {self.art}")


class SimTerminal:
    def __init__(self, specs: list[SymbolSpec], *, modus: KontoModus = KontoModus.HEDGING,
                 handelsmodus: HandelsModus = HandelsModus.DEMO, balance: Decimal = Decimal("10000"), waehrung: str = "EUR",
                 provision_je_lot: Decimal = ZERO, hebel: int = 30, uhr: Callable[[], float] | None = None,
                 trade_allowed: bool = True, sltp_magic_null: bool = False) -> None:
        self.specs = {s.name: s for s in specs}
        self.sltp_magic_null = sltp_magic_null          # manche Broker tragen bei SL/TP-Schlüssen magic 0 ein
        self.modus = modus
        self.handelsmodus = handelsmodus
        self.balance = balance
        self.waehrung = waehrung
        self.provision_je_lot = provision_je_lot
        self.hebel = hebel
        self.uhr = uhr or Uhr()
        self.trade_allowed = trade_allowed
        self._kurse: dict[str, Quote] = {}
        self._pos: dict[int, Position] = {}
        self._orders: dict[int, PendingOrder] = {}
        self._deals: list[Deal] = []
        self._deal_zeiten: list[int] = []
        self._bars: dict[str, list[Bar]] = {}
        self._bar_zeiten: dict[str, list[int]] = {}
        self._spaet: list[Callable[[], object]] = []
        self._fehler: dict[int, Fehler] = {}
        self._swap: dict[int, Decimal] = {}
        self.sendungen: list[OrderRequest] = []
        self.pruefungen = 0
        self._n = 1000

    # ------------------------------------------------------------------------------------------------ Hilfen
    def _id(self) -> int:
        self._n += 1
        return self._n

    def zeit(self) -> float:
        return self.uhr()

    def setze_kurs(self, symbol: str, bid: object, ask: object) -> None:
        self._kurse[symbol] = Quote(symbol, dez(bid), dez(ask), int(self.uhr() * 1000))

    def setze_fehler(self, magic: int, fehler: Fehler) -> None:
        self._fehler[magic] = fehler

    def gesendet(self, magic: int) -> int:
        return sum(1 for r in self.sendungen if r.magic == magic)

    def _gewinn(self, pos: Position, preis: Decimal, volumen: Decimal) -> Decimal:
        spec = self.specs[pos.symbol]
        diff = (preis - pos.price_open) * pos.side.sign
        return cent(diff / spec.tick_size * spec.tick_value * volumen)

    def _ausstiegskurs(self, pos: Position) -> Decimal:
        q = self._kurse[pos.symbol]
        return q.bid if pos.side is Side.BUY else q.ask

    def _deal(self, *, order: int, position_id: int, symbol: str, side: Side | None, volumen: Decimal, preis: Decimal, entry: str,
              grund: str, magic: int, kommentar: str, gewinn: Decimal = ZERO, provision: Decimal = ZERO,
              art: DealArt = DealArt.HANDEL, swap: Decimal = ZERO) -> Deal:
        d = Deal(ticket=self._id(), order=order, position_id=position_id, symbol=symbol, side=side, volume=volumen, price=preis,
                 entry=entry, reason=grund, magic=magic, comment=kommentar, profit=gewinn, commission=provision, swap=swap, fee=ZERO,
                 time=int(self.uhr()), art=art)
        self._deal_anhaengen(d)
        self.balance += gewinn + provision + swap
        return d

    def _provision(self, volumen: Decimal) -> Decimal:
        return -cent(self.provision_je_lot * volumen)

    # ------------------------------------------------------------------------------------------------ Lesen
    def account(self) -> AccountSnapshot:
        schwebend = ZERO
        marge = ZERO
        for p in self._pos.values():
            if p.symbol in self._kurse:
                schwebend += self._gewinn(p, self._ausstiegskurs(p), p.volume)
                spec = self.specs[p.symbol]
                marge += p.volume * self._kurse[p.symbol].bid * spec.tick_value / spec.tick_size / self.hebel
        equity = self.balance + schwebend + sum(self._swap.values(), ZERO)
        marge = cent(marge)
        stand = cent(equity / marge * 100) if marge > ZERO else ZERO
        return AccountSnapshot(trade_mode=self.handelsmodus, margin_mode=self.modus, currency=self.waehrung, balance=self.balance,
                               equity=equity, margin=marge, margin_free=equity - marge, margin_level=stand, leverage=self.hebel,
                               trade_allowed=self.trade_allowed)

    def symbol(self, name: str) -> SymbolSpec:
        if name not in self.specs:
            raise BrokerFehler(f"Symbol {name} unbekannt")
        return self.specs[name]

    def quote(self, name: str) -> Quote:
        if name not in self._kurse:
            raise BrokerFehler(f"kein Kurs für {name}")
        return self._kurse[name]

    def bars(self, name: str, timeframe: str, start: int, ende: int) -> list[Bar]:
        zeiten = self._bar_zeiten.get(name, [])
        return self._bars.get(name, [])[bisect.bisect_left(zeiten, start):bisect.bisect_right(zeiten, ende)]

    def positions(self) -> list[Position]:
        return sorted(self._pos.values(), key=lambda p: p.ticket)

    def orders(self) -> list[PendingOrder]:
        return sorted(self._orders.values(), key=lambda o: o.ticket)

    def _deal_anhaengen(self, d: Deal) -> None:
        i = bisect.bisect_right(self._deal_zeiten, d.time)
        self._deal_zeiten.insert(i, d.time)
        self._deals.insert(i, d)

    def deals(self, seit: int, bis: int) -> list[Deal]:
        return self._deals[bisect.bisect_left(self._deal_zeiten, seit):bisect.bisect_right(self._deal_zeiten, bis)]

    # ------------------------------------------------------------------------------------------------ Prüfen
    def _stops_ok(self, side: Side, sl: Decimal, tp: Decimal, spec: SymbolSpec) -> bool:
        q = self._kurse[spec.name]
        abstand = spec.point * spec.stops_level
        if side is Side.BUY:
            return (sl == ZERO or sl <= q.bid - abstand) and (tp == ZERO or tp >= q.bid + abstand)
        return (sl == ZERO or sl >= q.ask + abstand) and (tp == ZERO or tp <= q.ask - abstand)

    def _volumen_ok(self, v: Decimal, spec: SymbolSpec) -> bool:
        return spec.volume_min <= v <= spec.volume_max and (v / spec.volume_step) == (v / spec.volume_step).to_integral_value()

    def check(self, req: OrderRequest) -> CheckResult:
        self.pruefungen += 1
        spec = self.specs.get(req.symbol)
        if spec is None or req.symbol not in self._kurse:
            return CheckResult(10013, "Symbol/Kurs fehlt")
        if not self.trade_allowed:
            return CheckResult(10027, "AutoTrading aus")
        if spec.trade_mode == "DISABLED":
            return CheckResult(10017, "Handel gesperrt")
        if req.action is Action.ENTRY_DEAL:
            if spec.trade_mode == "CLOSEONLY":
                return CheckResult(10044, "nur Schließen")
            if not self._volumen_ok(req.volume, spec):
                return CheckResult(10014, "Volumen ungültig")
            if not self._stops_ok(req.side, req.sl, req.tp, spec):
                return CheckResult(10016, "Stops ungültig")
            q = self._kurse[req.symbol]
            noetig = req.volume * q.ask * spec.tick_value / spec.tick_size / self.hebel
            if noetig > self.account().margin_free:
                return CheckResult(10019, "nicht genug Geld")
        elif req.action in (Action.REDUCE_DEAL, Action.PROTECT_SLTP):
            pos = self._pos.get(req.ticket or -1)
            if pos is None:
                return CheckResult(10036, "Position geschlossen")
            if req.action is Action.REDUCE_DEAL and (not self._volumen_ok(req.volume, spec) or req.volume > pos.volume):
                return CheckResult(10014, "Volumen ungültig")
            if req.action is Action.PROTECT_SLTP and not self._stops_ok(pos.side, req.sl, req.tp, spec):
                return CheckResult(10016, "Stops ungültig")
        return CheckResult(0)

    # ------------------------------------------------------------------------------------------------ Senden
    def send(self, req: OrderRequest) -> SendResult | None:
        self.sendungen.append(req)
        f = self._fehler.get(req.magic)
        if f is not None and f.einmal:
            del self._fehler[req.magic]
        if f is not None:
            if f.art == "EXCEPTION":
                raise ConnectionError("SIM: Verbindung verloren")
            if f.art == "REJECT":
                return SendResult(int(f.code or 10006))
            if f.art == "TIMEOUT_NOT_EXECUTED":
                return None
            if f.art == "DISCONNECT_NOT_EXECUTED":
                return SendResult(10031)
            if f.art in ("TIMEOUT_EXECUTED", "DISCONNECT_EXECUTED"):
                self._spaet.append(lambda: self._ausfuehren(req, None))
                return None if f.art == "TIMEOUT_EXECUTED" else SendResult(10031)
        res = self._ausfuehren(req, f.anteil if f is not None and f.art == "PARTIAL" else None)
        if f is not None and f.art == "DOPPELT_AUSGEFUEHRT":
            self._ausfuehren(req, None)                    # Broker führt denselben Auftrag ein zweites Mal aus (neues Ticket)
        if f is not None and f.art == "DUPLICATE" and res.deal:
            self._deal_anhaengen(next(d for d in reversed(self._deals) if d.ticket == res.deal))   # Zeile doppelt gemeldet
        return res

    def liefere_spaete(self) -> None:
        offen, self._spaet = self._spaet, []
        for ausfuehren in offen:
            ausfuehren()

    def _ausfuehren(self, req: OrderRequest, anteil: Decimal | None) -> SendResult:
        spec = self.specs[req.symbol]
        if req.action is Action.ENTRY_DEAL:
            return self._eroeffnen(req, spec, anteil)
        if req.action is Action.REDUCE_DEAL:
            return self._reduzieren(req, spec, anteil)
        if req.action is Action.PROTECT_SLTP:
            pos = self._pos.get(req.ticket or -1)
            if pos is None:
                return SendResult(10036)
            if pos.sl == req.sl and pos.tp == req.tp:
                return SendResult(10025)
            self._pos[pos.ticket] = replace(pos, sl=req.sl, tp=req.tp)
            return SendResult(10009, order=self._id())
        if req.action is Action.PLACE_PENDING:
            oid = self._id()
            self._orders[oid] = PendingOrder(oid, req.symbol, req.side, req.volume, req.price, req.sl, req.tp, req.magic, req.comment)
            return SendResult(10009, order=oid, volume=req.volume, price=req.price)
        if self._orders.pop(req.ticket or -1, None) is None:
            return SendResult(10013)
        return SendResult(10009, order=req.ticket or 0)

    def _menge(self, volumen: Decimal, anteil: Decimal | None, spec: SymbolSpec) -> Decimal:
        if anteil is None:
            return volumen
        return ((volumen * anteil) / spec.volume_step).to_integral_value(rounding=ROUND_FLOOR) * spec.volume_step

    def _eroeffnen(self, req: OrderRequest, spec: SymbolSpec, anteil: Decimal | None) -> SendResult:
        q = self._kurse[req.symbol]
        preis = q.ask if req.side is Side.BUY else q.bid
        menge = self._menge(req.volume, anteil, spec)
        if menge <= ZERO:
            return SendResult(10006)
        order = self._id()
        if self.modus is KontoModus.HEDGING:
            self._pos[order] = Position(order, req.symbol, req.side, menge, preis, req.sl, req.tp, req.magic, req.comment, int(self.uhr()))
            d = self._deal(order=order, position_id=order, symbol=req.symbol, side=req.side, volumen=menge, preis=preis, entry="IN",
                           grund="EXPERT", magic=req.magic, kommentar=req.comment, provision=self._provision(menge))
        else:
            d = self._netting(order, req, menge, preis, "EXPERT")
        return SendResult(10009 if menge == req.volume else 10010, order=order, deal=d.ticket, volume=menge, price=preis)

    def _netting(self, order: int, req: OrderRequest, menge: Decimal, preis: Decimal, grund: str) -> Deal:
        alt = next((p for p in self._pos.values() if p.symbol == req.symbol), None)
        if alt is None:
            self._pos[order] = Position(order, req.symbol, req.side, menge, preis, req.sl, req.tp, req.magic, req.comment, int(self.uhr()))
            return self._deal(order=order, position_id=order, symbol=req.symbol, side=req.side, volumen=menge, preis=preis, entry="IN",
                              grund=grund, magic=req.magic, kommentar=req.comment, provision=self._provision(menge))
        if alt.side is req.side:
            neu_v = alt.volume + menge
            mittel = ((alt.price_open * alt.volume + preis * menge) / neu_v).quantize(self.specs[req.symbol].tick_size)
            self._pos[alt.ticket] = replace(alt, volume=neu_v, price_open=mittel, sl=req.sl, tp=req.tp)
            return self._deal(order=order, position_id=alt.ticket, symbol=req.symbol, side=req.side, volumen=menge, preis=preis,
                              entry="IN", grund=grund, magic=req.magic, kommentar=req.comment, provision=self._provision(menge))
        schliessen = min(menge, alt.volume)
        gewinn = self._gewinn(alt, preis, schliessen)
        rest = alt.volume - schliessen
        ueber = menge - schliessen
        offen = self._swap.get(alt.ticket, ZERO)
        swap = offen if rest <= ZERO else cent(offen * schliessen / alt.volume)
        self._swap[alt.ticket] = offen - swap
        if rest > ZERO:
            self._pos[alt.ticket] = replace(alt, volume=rest)
            entry = "OUT"
        elif ueber > ZERO:
            self._pos[alt.ticket] = replace(alt, side=req.side, volume=ueber, price_open=preis, sl=req.sl, tp=req.tp)
            entry = "INOUT"
        else:
            del self._pos[alt.ticket]
            entry = "OUT"
        return self._deal(order=order, position_id=alt.ticket, symbol=req.symbol, side=req.side, volumen=menge, preis=preis, entry=entry,
                          grund=grund, magic=req.magic, kommentar=req.comment, gewinn=gewinn, provision=self._provision(menge), swap=swap)

    def _schliessen(self, pos: Position, menge: Decimal, preis: Decimal, grund: str, magic: int, kommentar: str) -> Deal:
        gewinn = self._gewinn(pos, preis, menge)
        offen = self._swap.get(pos.ticket, ZERO)
        swap = offen if menge >= pos.volume else cent(offen * menge / pos.volume)
        if menge >= pos.volume:
            del self._pos[pos.ticket]
            self._swap.pop(pos.ticket, None)
        else:
            self._pos[pos.ticket] = replace(pos, volume=pos.volume - menge)
            self._swap[pos.ticket] = offen - swap
        return self._deal(order=self._id(), position_id=pos.ticket, symbol=pos.symbol, side=pos.side.opposite, volumen=menge, preis=preis,
                          entry="OUT", grund=grund, magic=magic, kommentar=kommentar, gewinn=gewinn, provision=self._provision(menge),
                          swap=swap)

    def rollover(self, je_lot: dict[str, tuple[Decimal, Decimal]], faktor: int = 1) -> None:
        """Swap je Lot (Long, Short) in Kontowährung für alle offenen Positionen; Dreifachtag mit faktor=3."""
        for p in self._pos.values():
            lang, kurz = je_lot.get(p.symbol, (ZERO, ZERO))
            betrag = cent((lang if p.side is Side.BUY else kurz) * p.volume * faktor)
            self._swap[p.ticket] = self._swap.get(p.ticket, ZERO) + betrag

    def _reduzieren(self, req: OrderRequest, spec: SymbolSpec, anteil: Decimal | None) -> SendResult:
        pos = self._pos.get(req.ticket or -1)
        if pos is None:
            return SendResult(10036)
        if req.side is pos.side or req.volume > pos.volume:
            return SendResult(10038)
        menge = self._menge(req.volume, anteil, spec)
        if menge <= ZERO:
            return SendResult(10006)
        d = self._schliessen(pos, menge, self._ausstiegskurs(pos), "EXPERT", req.magic, req.comment)
        return SendResult(10009 if menge == req.volume else 10010, order=d.order, deal=d.ticket, volume=menge, price=d.price)

    # ------------------------------------------------------------------------------------------------ Markt und Umwelt
    def kerze(self, bar: Bar) -> list[Deal]:
        """Eine abgeschlossene Kerze (Bid) abspielen: SL/TP auslösen (SL zuerst, Lücke = Eröffnungskurs), dann Kurs = Schluss."""
        spec = self.specs[bar.symbol]
        spread = spec.point * bar.spread_points
        zeiten = self._bar_zeiten.setdefault(bar.symbol, [])
        i = bisect.bisect_right(zeiten, bar.time)
        zeiten.insert(i, bar.time)
        self._bars.setdefault(bar.symbol, []).insert(i, bar)
        aus: list[Deal] = []
        for pos in [p for p in self.positions() if p.symbol == bar.symbol]:
            # Reihenfolge: Lücken am Eröffnungskurs zuerst (erster Preis der Kerze), dann innerhalb der Kerze SL vor TP.
            if pos.side is Side.BUY:
                o, h, lo = bar.open, bar.high, bar.low
                treffer = ((pos.sl > ZERO and o <= pos.sl, o, "SL"), (pos.tp > ZERO and o >= pos.tp, o, "TP"),
                           (pos.sl > ZERO and lo <= pos.sl, pos.sl, "SL"), (pos.tp > ZERO and h >= pos.tp, pos.tp, "TP"))
            else:
                o, h, lo = bar.open + spread, bar.high + spread, bar.low + spread
                treffer = ((pos.sl > ZERO and o >= pos.sl, o, "SL"), (pos.tp > ZERO and o <= pos.tp, o, "TP"),
                           (pos.sl > ZERO and h >= pos.sl, pos.sl, "SL"), (pos.tp > ZERO and lo <= pos.tp, pos.tp, "TP"))
            for getroffen, preis, grund in treffer:
                if getroffen:
                    aus.append(self._schliessen(pos, pos.volume, preis, grund, 0 if self.sltp_magic_null else pos.magic, pos.comment))
                    break
        self.setze_kurs(bar.symbol, bar.close, bar.close + spread)
        return aus

    def fremder_handel(self, symbol: str, side: Side, volumen: Decimal, *, magic: int = 0, grund: str = "CLIENT") -> Position:
        q = self._kurse[symbol]
        preis = q.ask if side is Side.BUY else q.bid
        order = self._id()
        if self.modus is not KontoModus.HEDGING:          # Netting: Fremdvolumen verschmilzt mit der vorhandenen Position
            req = OrderRequest(Action.ENTRY_DEAL, symbol, side, volumen, magic=magic)
            d = self._netting(order, req, volumen, preis, grund)
            vorhanden = next((p for p in self._pos.values() if p.symbol == symbol), None)
            return vorhanden or Position(d.position_id, symbol, side, ZERO, preis, ZERO, ZERO, magic)
        pos = Position(order, symbol, side, volumen, preis, ZERO, ZERO, magic, "", int(self.uhr()))
        self._pos[order] = pos
        self._deal(order=order, position_id=order, symbol=symbol, side=side, volumen=volumen, preis=preis, entry="IN", grund=grund,
                   magic=magic, kommentar="", provision=self._provision(volumen))
        return pos

    def manuell_schliessen(self, ticket: int, grund: str = "CLIENT") -> Deal:
        """Handschluss im Terminal: Grund CLIENT, magic 0 (die Oberfläche kennt keinen magic)."""
        pos = self._pos[ticket]
        return self._schliessen(pos, pos.volume, self._ausstiegskurs(pos), grund, 0, "")

    def stop_out(self, ticket: int) -> Deal:
        pos = self._pos[ticket]
        return self._schliessen(pos, pos.volume, self._ausstiegskurs(pos), "SO", pos.magic, "[so]")

    def kapital(self, betrag: Decimal, art: DealArt = DealArt.KAPITAL) -> Deal:
        return self._deal(order=0, position_id=0, symbol="", side=None, volumen=ZERO, preis=ZERO, entry="NONE", grund="CLIENT", magic=0,
                          kommentar="", gewinn=betrag, art=art)
