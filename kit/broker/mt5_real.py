"""MT5-Adapter (Herkunft: mt5-trading-ai venue/mt5.py RealMt5Terminal, gekürzt und korrigiert).

Grundsätze:
- MetaTrader5 wird nur hier und nur verzögert importiert; das Modul ist injizierbar (Tests: kit/broker/sim_modul.py).
- initialize() nur mit `path`, nie mit login/password/server: der Betreiber meldet sich selbst im Terminal an.
- Läuft kein Terminal, wird keines gestartet (es würde sich mit dem zuletzt gespeicherten Konto anmelden) – BrokerFehler.
- `None` aus positions_get/orders_get/history_deals_get/copy_rates_range ist ein Fehler, nie „leer“ (fail-closed).
- Zeiten: MT5 liefert Server-Wanduhr als Epoche; nach außen gibt der Adapter echtes UTC (versatz_s = Server minus UTC,
  gemessen über Ticks, ganze Stunden). copy_rates_range/history_deals_get erwarten Serverzeit mit UTC-Etikett. Die PC-Uhr wird
  um die gemessene Restabweichung (< 10 min) an die Serveruhr angeglichen (zeit()), sonst wirkten Kurse „alt“ und Deals früh.
  Ohne gemessenen Versatz liefert deals() nichts Falsches, sondern einen Fehler (fail-closed).
- Handel erlaubt nur mit Konto-/EA-Freigabe, Knopf „Algo Trading“ und ohne Terminal-Option „Handel über Python-API aus“.
- Füllart aus der Bitmaske des Symbols (1 FOK, 2 IOC, 4 RETURN) → Auftragskonstante; FOK bevorzugt.
- Decimal an der Grenze: Werte aus MT5 über str(), Werte an MT5 über float(str(Decimal)).
"""
from __future__ import annotations

import datetime as dt
import importlib
import os
import subprocess
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from kit.broker.seam import BrokerFehler
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
from kit.state.store import kontoabdruck

UTC = dt.UTC
TF_SEKUNDEN = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
FENSTER_RAND_S = 14 * 3600                      # größter Zeitzonenversatz: Historienabfragen werden so weit gepolstert
RAND_BEKANNT_S = 3600                           # Polster, sobald der Versatz gemessen ist
VERSATZ_TOLERANZ_S = 600
REASONS = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL", 5: "TP", 6: "SO", 7: "ROLLOVER", 8: "VMARGIN", 9: "SPLIT",
           10: "CORPORATE_ACTION"}
ENTRIES = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}
SYMBOL_HANDEL = {0: "DISABLED", 1: "LONGONLY", 2: "SHORTONLY", 3: "CLOSEONLY", 4: "FULL"}


def _d(wert: Any) -> Decimal:
    return Decimal(str(wert)) if wert is not None else ZERO


def _f(wert: Decimal) -> float:
    return float(str(wert))


def terminal_laeuft() -> bool:
    if os.name != "nt":
        return False
    erg = subprocess.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"], capture_output=True, text=True, check=False,
                         errors="replace")
    return "terminal64.exe" in erg.stdout.lower()


class Mt5Terminal:
    def __init__(self, modul: Any = None, *, pfad: str | None = None, versatz_s: float | None = None,
                 schluessel_ordner: Path | None = None, uhr: Callable[[], float] = time.time,
                 prozess_pruefen: Callable[[], bool] | None = terminal_laeuft, mono: Callable[[], float] | None = None) -> None:
        self._mt5 = modul
        self.pfad = pfad
        self.versatz_s = versatz_s
        self.schluessel_ordner = schluessel_ordner
        self.uhr = uhr
        self.prozess_pruefen = prozess_pruefen
        self.info: dict = {}
        self._abdruck: dict[tuple[int, str], str] = {}
        self.mono = mono or (time.monotonic if uhr is time.time else uhr)   # Stellen der PC-Uhr wirkt nicht auf zeit()
        self._basis: float | None = None                # UTC des frischesten Ticks bei der letzten Messung
        self._mono0 = 0.0

    # ------------------------------------------------------------------------------------------------ Verbindung
    def _m(self) -> Any:
        if self._mt5 is None:
            raise BrokerFehler("Terminal nicht verbunden (verbinden() zuerst).")
        return self._mt5

    def verbinden(self) -> dict:
        if self.prozess_pruefen is not None and not self.prozess_pruefen():
            raise BrokerFehler("Kein laufendes MT5-Terminal – bitte selbst starten und mit dem Demokonto anmelden (der Bot startet "
                               "kein Terminal).")
        if self._mt5 is None:
            self._mt5 = importlib.import_module("MetaTrader5")
        mt5 = self._mt5
        ok = mt5.initialize(path=self.pfad) if self.pfad else mt5.initialize()
        if not ok:
            raise BrokerFehler(f"initialize fehlgeschlagen: {mt5.last_error()}")
        info = mt5.terminal_info()
        if info is None:
            raise BrokerFehler("terminal_info() lieferte None")
        if self.pfad and os.path.normcase(os.path.dirname(os.path.abspath(self.pfad))) != os.path.normcase(str(info.path)):
            raise BrokerFehler("Verbunden mit einem anderen Terminal als konfiguriert – Abbruch.")
        self.info = {"build": int(getattr(info, "build", 0)), "connected": bool(getattr(info, "connected", False)),
                     "trade_allowed": bool(getattr(info, "trade_allowed", False)), "maxbars": int(getattr(info, "maxbars", 0)),
                     "tradeapi_disabled": bool(getattr(info, "tradeapi_disabled", False)),
                     "path": str(getattr(info, "path", "")), "data_path": str(getattr(info, "data_path", ""))}
        return dict(self.info)

    def trennen(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def zeit(self) -> float:
        """UTC nach der Serveruhr: seit der letzten Messung Tickzeit + vergangene monotone Zeit; vorher die PC-Uhr."""
        if self._basis is None:
            return self.uhr()
        return self._basis + (self.mono() - self._mono0)

    @property
    def rest_s(self) -> float:
        """Abweichung PC-Uhr gegen Serveruhr (ohne ganze Stunden) – nur Bericht."""
        return self.zeit() - self.uhr()

    def _utc(self, server_s: Any) -> float:
        return float(server_s) - (self.versatz_s or 0.0)

    def _server_dt(self, utc_s: float) -> dt.datetime:
        return dt.datetime.fromtimestamp(utc_s + (self.versatz_s or 0.0), UTC)

    def messe_versatz(self, symbol: str, *, warte_s: float = 0.1, schlaf: Callable[[float], None] = time.sleep,
                      versuche: int = 100) -> float:
        """Server-Wanduhr minus UTC über Ticklesungen (Frischebeweis: Tick rückt vor), auf ganze Stunden gerundet. Fein
        abgefragt (Vorgabe alle 0,1 s, höchstens 10 s), damit der vorgerückte Tick höchstens Bruchteile einer Sekunde alt ist;
        seine UTC-Zeit wird die Basis von zeit() (monoton fortgeschrieben)."""
        mt5 = self._m()
        mt5.symbol_select(symbol, True)                  # ohne Marktübersicht liefert symbol_info_tick None
        erste = mt5.symbol_info_tick(symbol)
        zweite = None
        for _ in range(max(1, versuche)):
            schlaf(warte_s)
            zweite = mt5.symbol_info_tick(symbol)
            if erste is None:                            # erster Tick kommt erst nach dem Abonnement
                erste = zweite
                continue
            if zweite is not None and int(zweite.time_msc) > int(erste.time_msc):
                break
        if erste is None or zweite is None or int(zweite.time_msc) <= int(erste.time_msc):
            raise BrokerFehler(f"{symbol}: Kursstrom steht – Serverversatz nicht messbar (Markt geschlossen?).")
        m = self.mono()
        tick_s = int(zweite.time_msc) / 1000
        differenz = tick_s - self.uhr()
        stunden = round(differenz / 3600)
        if abs(differenz - stunden * 3600) > VERSATZ_TOLERANZ_S or abs(stunden) > 14:
            raise BrokerFehler(f"{symbol}: Versatz {differenz:.0f} s ist keine Ganzstundenzone – nichts gesetzt.")
        self.versatz_s = float(stunden * 3600)
        self._basis, self._mono0 = tick_s - self.versatz_s, m
        return self.versatz_s

    # ------------------------------------------------------------------------------------------------ Lesen
    def account(self) -> AccountSnapshot:
        mt5 = self._m()
        a = mt5.account_info()
        if a is None:
            raise BrokerFehler("account_info() lieferte None – kein angemeldetes Konto.")
        t = mt5.terminal_info()
        modi = {int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)): HandelsModus.DEMO,
                int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1)): HandelsModus.CONTEST,
                int(getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2)): HandelsModus.REAL}
        marge = {int(getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_NETTING", 0)): KontoModus.NETTING,
                 int(getattr(mt5, "ACCOUNT_MARGIN_MODE_EXCHANGE", 1)): KontoModus.EXCHANGE,
                 int(getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2)): KontoModus.HEDGING}
        abdruck = ""
        if self.schluessel_ordner:
            schluessel = (int(a.login), str(a.server))
            if schluessel not in self._abdruck:
                self._abdruck[schluessel] = kontoabdruck(*schluessel, self.schluessel_ordner)
            abdruck = self._abdruck[schluessel]
        erlaubt = bool(getattr(a, "trade_allowed", False)) and bool(getattr(a, "trade_expert", True)) and \
            t is not None and bool(getattr(t, "trade_allowed", False)) and not bool(getattr(t, "tradeapi_disabled", False))
        return AccountSnapshot(trade_mode=modi.get(int(a.trade_mode), HandelsModus.UNBEKANNT),
                               margin_mode=marge.get(int(a.margin_mode), KontoModus.NETTING), currency=str(a.currency),
                               balance=_d(a.balance), equity=_d(a.equity), margin=_d(a.margin), margin_free=_d(a.margin_free),
                               margin_level=_d(getattr(a, "margin_level", 0)), leverage=int(a.leverage), trade_allowed=erlaubt,
                               abdruck=abdruck)

    def _fuellart(self, maske: int) -> str:
        if maske & 1:
            return "FOK"
        if maske & 2:
            return "IOC"
        if maske & 4:
            return "RETURN"
        raise BrokerFehler(f"keine unterstützte Füllart (filling_mode={maske}) – fail-closed")

    def symbol(self, name: str) -> SymbolSpec:
        mt5 = self._m()
        info = mt5.symbol_info(name)
        if info is None or not bool(getattr(info, "visible", True)):
            mt5.symbol_select(name, True)
            info = mt5.symbol_info(name)
        if info is None:
            raise BrokerFehler(f"Symbol {name} beim Broker unbekannt")
        punkt = _d(info.point)
        tick = _d(getattr(info, "trade_tick_size", 0)) or punkt
        return SymbolSpec(name=str(info.name), digits=int(info.digits), point=punkt, tick_size=tick,
                          tick_value=_d(info.trade_tick_value), contract_size=_d(info.trade_contract_size),
                          volume_min=_d(info.volume_min), volume_max=_d(info.volume_max), volume_step=_d(info.volume_step),
                          stops_level=int(info.trade_stops_level), freeze_level=int(info.trade_freeze_level),
                          filling=self._fuellart(int(info.filling_mode)),
                          trade_mode=SYMBOL_HANDEL.get(int(info.trade_mode), "DISABLED"),
                          currency_profit=str(info.currency_profit), currency_base=str(info.currency_base))

    def quote(self, name: str) -> Quote:
        mt5 = self._m()
        t = mt5.symbol_info_tick(name)
        if t is None:                                   # Symbol nicht in der Marktübersicht: einmal auswählen und erneut lesen
            mt5.symbol_select(name, True)
            t = mt5.symbol_info_tick(name)
        if t is None:
            raise BrokerFehler(f"kein Tick für {name}")
        return Quote(name, _d(t.bid), _d(t.ask), int(int(t.time_msc) - (self.versatz_s or 0.0) * 1000))

    def bars(self, name: str, timeframe: str, start: int, ende: int) -> list[Bar]:
        mt5 = self._m()
        tf = getattr(mt5, f"TIMEFRAME_{timeframe}")
        zeilen = mt5.copy_rates_range(name, tf, self._server_dt(start), self._server_dt(ende))
        if zeilen is None:
            raise BrokerFehler(f"copy_rates_range({name}, {timeframe}) lieferte None: {mt5.last_error()}")
        jetzt = self.zeit()                             # dieselbe (angeglichene) Uhr wie Takt und Kursalter
        dauer = TF_SEKUNDEN[timeframe]
        out = []
        for z in zeilen:
            beginn = self._utc(z["time"])
            out.append(Bar(name, int(beginn), _d(z["open"]), _d(z["high"]), _d(z["low"]), _d(z["close"]), int(z["spread"]),
                           is_closed=beginn + dauer <= jetzt))
        return out

    def positions(self) -> list[Position]:
        mt5 = self._m()
        roh = mt5.positions_get()
        if roh is None:
            raise BrokerFehler("positions_get() lieferte None – das ist nicht dasselbe wie ein leeres Buch.")
        kauf = int(getattr(mt5, "POSITION_TYPE_BUY", 0))
        return [Position(int(p.ticket), str(p.symbol), Side.BUY if int(p.type) == kauf else Side.SELL, _d(p.volume),
                         _d(p.price_open), _d(p.sl), _d(p.tp), int(p.magic), str(p.comment), int(self._utc(p.time))) for p in roh]

    def orders(self) -> list[PendingOrder]:
        mt5 = self._m()
        roh = mt5.orders_get()
        if roh is None:
            raise BrokerFehler("orders_get() lieferte None")
        gerade = {int(getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2)), int(getattr(mt5, "ORDER_TYPE_BUY_STOP", 4))}
        return [PendingOrder(int(o.ticket), str(o.symbol), Side.BUY if int(o.type) in gerade else Side.SELL,
                             _d(o.volume_current), _d(o.price_open), _d(o.sl), _d(o.tp), int(o.magic), str(o.comment)) for o in roh]

    def deals(self, seit: int, bis: int) -> list[Deal]:
        mt5 = self._m()
        if self.versatz_s is None:
            raise BrokerFehler("Serverversatz unbekannt – Historie nicht sicher zuordenbar (erst messen).")
        rand = FENSTER_RAND_S if self.versatz_s is None else RAND_BEKANNT_S
        roh = mt5.history_deals_get(self._server_dt(seit - rand), self._server_dt(bis + rand))
        if roh is None:
            raise BrokerFehler(f"history_deals_get lieferte None: {mt5.last_error()}")
        kauf, verkauf = int(getattr(mt5, "DEAL_TYPE_BUY", 0)), int(getattr(mt5, "DEAL_TYPE_SELL", 1))
        kapital = {int(getattr(mt5, n, w)) for n, w in (("DEAL_TYPE_BALANCE", 2), ("DEAL_TYPE_CREDIT", 3),
                                                         ("DEAL_TYPE_CORRECTION", 5), ("DEAL_TYPE_BONUS", 6))}
        out = []
        for d in roh:
            t = int(self._utc(d.time))
            if not seit <= t <= bis:
                continue
            typ = int(d.type)
            art = DealArt.HANDEL if typ in (kauf, verkauf) else DealArt.KAPITAL if typ in kapital else DealArt.GEBUEHR
            seite = Side.BUY if typ == kauf else Side.SELL if typ == verkauf else None
            out.append(Deal(ticket=int(d.ticket), order=int(d.order), position_id=int(d.position_id), symbol=str(d.symbol), side=seite,
                            volume=_d(d.volume), price=_d(d.price), entry=ENTRIES.get(int(d.entry), "NONE"),
                            reason=REASONS.get(int(d.reason), str(d.reason)), magic=int(d.magic), comment=str(d.comment),
                            profit=_d(d.profit), commission=_d(d.commission), swap=_d(d.swap), fee=_d(getattr(d, "fee", 0)), time=t,
                            art=art))
        return out

    # ------------------------------------------------------------------------------------------------ Schreiben
    def _anfrage(self, req: OrderRequest) -> dict:
        mt5 = self._m()
        if req.action is Action.PROTECT_SLTP:
            return {"action": int(mt5.TRADE_ACTION_SLTP), "symbol": req.symbol, "position": int(req.ticket or 0), "sl": _f(req.sl),
                    "tp": _f(req.tp), "magic": int(req.magic)}
        if req.action is Action.CANCEL_PENDING:
            return {"action": int(mt5.TRADE_ACTION_REMOVE), "order": int(req.ticket or 0), "magic": int(req.magic)}
        if req.action not in (Action.ENTRY_DEAL, Action.REDUCE_DEAL):
            raise BrokerFehler(f"{req.action} wird vom Adapter nicht unterstützt")
        tick = mt5.symbol_info_tick(req.symbol)
        if tick is None:
            raise BrokerFehler(f"kein Tick für {req.symbol}")
        info = mt5.symbol_info(req.symbol)
        if info is None:
            raise BrokerFehler(f"Symbol {req.symbol} unbekannt")
        fuell = {"FOK": mt5.ORDER_FILLING_FOK, "IOC": mt5.ORDER_FILLING_IOC, "RETURN": mt5.ORDER_FILLING_RETURN}[
            self._fuellart(int(info.filling_mode))]
        anfrage = {"action": int(mt5.TRADE_ACTION_DEAL), "symbol": req.symbol, "volume": _f(req.volume),
                   "type": int(mt5.ORDER_TYPE_BUY if req.side is Side.BUY else mt5.ORDER_TYPE_SELL),
                   "price": float(tick.ask if req.side is Side.BUY else tick.bid), "deviation": int(req.deviation),
                   "magic": int(req.magic), "comment": req.comment[:31], "type_time": int(mt5.ORDER_TIME_GTC),
                   "type_filling": int(fuell)}
        if req.action is Action.ENTRY_DEAL:
            anfrage["sl"], anfrage["tp"] = _f(req.sl), _f(req.tp)
        else:
            anfrage["position"] = int(req.ticket or 0)
        return anfrage

    def check(self, req: OrderRequest) -> CheckResult:
        mt5 = self._m()
        res = mt5.order_check(self._anfrage(req))
        if res is None:
            raise BrokerFehler(f"order_check lieferte None: {mt5.last_error()}")
        return CheckResult(int(res.retcode), str(getattr(res, "comment", "")), _d(getattr(res, "margin", 0)),
                           _d(getattr(res, "margin_free", 0)))

    def send(self, req: OrderRequest) -> SendResult | None:
        res = self._m().order_send(self._anfrage(req))
        if res is None:
            return None
        return SendResult(int(res.retcode), int(getattr(res, "order", 0) or 0), int(getattr(res, "deal", 0) or 0),
                          _d(getattr(res, "volume", 0)), _d(getattr(res, "price", 0)), str(getattr(res, "comment", "")))
