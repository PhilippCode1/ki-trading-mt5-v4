"""Attrappe des MetaTrader5-Pakets, getrieben vom SIM-Terminal: lässt den echten Adaptercode (mt5_real.Mt5Terminal) in CI und
Trockenlauf vollständig laufen. Zählt Aufrufe (order_send/order_check) für Nur-Lese-Nachweise. Serverzeit = UTC + versatz_s."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from kit.broker.sim import SimTerminal
from kit.domain.types import ZERO, Action, DealArt, HandelsModus, KontoModus, OrderRequest, Side

UTC = dt.UTC


class SimMt5Modul:
    TRADE_ACTION_DEAL, TRADE_ACTION_SLTP, TRADE_ACTION_REMOVE = 1, 6, 8
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_BUY_STOP = 0, 1, 2, 4
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    ORDER_TIME_GTC = 0
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL = 0, 1, 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING, ACCOUNT_MARGIN_MODE_EXCHANGE, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 0, 1, 2
    POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
    DEAL_TYPE_BUY, DEAL_TYPE_SELL, DEAL_TYPE_BALANCE, DEAL_TYPE_CREDIT, DEAL_TYPE_CHARGE = 0, 1, 2, 3, 4
    DEAL_TYPE_CORRECTION, DEAL_TYPE_BONUS, DEAL_TYPE_COMMISSION = 5, 6, 7
    TIMEFRAME_M1, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 1, 16385, 16388, 16408
    TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE_PARTIAL = 10009, 10008, 10010

    _TRADE_MODE = {HandelsModus.DEMO: 0, HandelsModus.CONTEST: 1, HandelsModus.REAL: 2}
    _MARGIN_MODE = {KontoModus.NETTING: 0, KontoModus.EXCHANGE: 1, KontoModus.HEDGING: 2}
    _ENTRY = {"IN": 0, "OUT": 1, "INOUT": 2, "OUT_BY": 3, "NONE": 0}
    _REASON = {"CLIENT": 0, "MOBILE": 1, "WEB": 2, "EXPERT": 3, "SL": 4, "TP": 5, "SO": 6}
    _FUELL = {"FOK": 1, "IOC": 2, "RETURN": 4}
    _SYMBOL = {"DISABLED": 0, "LONGONLY": 1, "SHORTONLY": 2, "CLOSEONLY": 3, "FULL": 4}

    def __init__(self, sim: SimTerminal, *, versatz_s: int = 3 * 3600, pfad: str = "C:/Programme/MT5", login: int = 0,
                 server: str = "Sim-Demo", terminal_trade_allowed: bool = True, connected: bool = True,
                 tradeapi_disabled: bool = False) -> None:
        self.tradeapi_disabled = tradeapi_disabled
        self.nicht_ausgewaehlt: set[str] = set()       # Symbole außerhalb der Marktübersicht (Tick None bis symbol_select)
        self.sim = sim
        self.versatz_s = versatz_s
        self.pfad = pfad
        self.login = login or int("5" + "1234567")
        self.server = server
        self.terminal_trade_allowed = terminal_trade_allowed
        self.connected = connected
        self.aufrufe: dict[str, int] = {}
        self.initialize_kwargs: dict = {}

    def _zaehle(self, name: str) -> None:
        self.aufrufe[name] = self.aufrufe.get(name, 0) + 1

    # ------------------------------------------------------------------------------------------------ Verbindung
    def initialize(self, path: str | None = None, **kwargs: Any) -> bool:
        if {"login", "password", "server"} & set(kwargs):
            raise AssertionError("initialize mit Zugangsdaten ist verboten")
        self.initialize_kwargs = {"path": path, **kwargs}
        return True

    def shutdown(self) -> None:
        self._zaehle("shutdown")

    def last_error(self) -> tuple[int, str]:
        return (1, "Success")

    def terminal_info(self) -> SimpleNamespace:
        return SimpleNamespace(build=6230, connected=self.connected, trade_allowed=self.terminal_trade_allowed, maxbars=100000,
                               path=self.pfad, data_path=self.pfad + "/Daten", company="Sim Ltd", name="SIM",
                               tradeapi_disabled=self.tradeapi_disabled)

    def account_info(self) -> SimpleNamespace:
        a = self.sim.account()
        return SimpleNamespace(login=self.login, server=self.server, name="Probe", company="Sim Ltd",
                               trade_mode=self._TRADE_MODE[a.trade_mode], margin_mode=self._MARGIN_MODE[a.margin_mode],
                               currency=a.currency, balance=float(a.balance), equity=float(a.equity), margin=float(a.margin),
                               margin_free=float(a.margin_free), margin_level=float(a.margin_level), leverage=a.leverage,
                               trade_allowed=a.trade_allowed, trade_expert=True)

    # ------------------------------------------------------------------------------------------------ Lesen
    def symbol_info(self, name: str) -> SimpleNamespace | None:
        s = self.sim.specs.get(name)
        if s is None:
            return None
        return SimpleNamespace(name=s.name, digits=s.digits, point=float(s.point), trade_tick_size=float(s.tick_size),
                               trade_tick_value=float(s.tick_value), trade_contract_size=float(s.contract_size),
                               volume_min=float(s.volume_min), volume_max=float(s.volume_max), volume_step=float(s.volume_step),
                               trade_stops_level=s.stops_level, trade_freeze_level=s.freeze_level, filling_mode=self._FUELL[s.filling],
                               trade_mode=self._SYMBOL[s.trade_mode], currency_profit=s.currency_profit, currency_base=s.currency_base,
                               visible=True)

    def symbol_select(self, name: str, enable: bool = True) -> bool:
        self.nicht_ausgewaehlt.discard(name)
        return name in self.sim.specs

    def symbol_info_tick(self, name: str) -> SimpleNamespace | None:
        q = self.sim._kurse.get(name)
        if q is None or name in self.nicht_ausgewaehlt:
            return None
        server_ms = int(self.sim.uhr() * 1000) + self.versatz_s * 1000
        return SimpleNamespace(time=server_ms // 1000, time_msc=server_ms, bid=float(q.bid), ask=float(q.ask))

    def positions_get(self) -> tuple:
        return tuple(SimpleNamespace(ticket=p.ticket, symbol=p.symbol, type=0 if p.side is Side.BUY else 1, volume=float(p.volume),
                                     price_open=float(p.price_open), sl=float(p.sl), tp=float(p.tp), magic=p.magic, comment=p.comment,
                                     time=p.time + self.versatz_s, profit=0.0, swap=0.0) for p in self.sim.positions())

    def orders_get(self) -> tuple:
        return tuple(SimpleNamespace(ticket=o.ticket, symbol=o.symbol, type=2 if o.side is Side.BUY else 3,
                                     volume_current=float(o.volume), price_open=float(o.price), sl=float(o.sl), tp=float(o.tp),
                                     magic=o.magic, comment=o.comment) for o in self.sim.orders())

    def history_deals_get(self, von: dt.datetime, bis: dt.datetime) -> tuple:
        a, b = von.timestamp() - self.versatz_s, bis.timestamp() - self.versatz_s
        typ = {DealArt.KAPITAL: 2, DealArt.GEBUEHR: 4, DealArt.SONSTIGES: 4}
        return tuple(SimpleNamespace(ticket=d.ticket, order=d.order, position_id=d.position_id, symbol=d.symbol,
                                     type=(0 if d.side is Side.BUY else 1) if d.art is DealArt.HANDEL else typ[d.art],
                                     volume=float(d.volume), price=float(d.price), entry=self._ENTRY.get(d.entry, 0),
                                     reason=self._REASON.get(d.reason, 0), magic=d.magic, comment=d.comment, profit=float(d.profit),
                                     commission=float(d.commission), swap=float(d.swap), fee=float(d.fee), time=d.time + self.versatz_s)
                     for d in self.sim.deals(int(a), int(b)))

    def copy_rates_range(self, symbol: str, timeframe: int, von: dt.datetime, bis: dt.datetime) -> list[dict] | None:
        self._zaehle("copy_rates_range")
        if symbol not in self.sim.specs:
            return None
        a, b = von.timestamp() - self.versatz_s, bis.timestamp() - self.versatz_s
        return [{"time": bar.time + self.versatz_s, "open": float(bar.open), "high": float(bar.high), "low": float(bar.low),
                 "close": float(bar.close), "tick_volume": 0, "spread": bar.spread_points, "real_volume": 0}
                for bar in self.sim.bars(symbol, str(timeframe), int(a), int(b))]

    # ------------------------------------------------------------------------------------------------ Schreiben
    def _req(self, r: dict) -> OrderRequest:
        if r["action"] == self.TRADE_ACTION_SLTP:
            pos = next((p for p in self.sim.positions() if p.ticket == r["position"]), None)
            return OrderRequest(Action.PROTECT_SLTP, r["symbol"], pos.side if pos else Side.BUY, pos.volume if pos else ZERO,
                                magic=r.get("magic", 0), sl=Decimal(str(r["sl"])), tp=Decimal(str(r["tp"])), ticket=r["position"])
        if r["action"] == self.TRADE_ACTION_REMOVE:
            return OrderRequest(Action.CANCEL_PENDING, "", Side.BUY, ZERO, magic=r.get("magic", 0), ticket=r["order"])
        seite = Side.BUY if r["type"] == self.ORDER_TYPE_BUY else Side.SELL
        aktion = Action.REDUCE_DEAL if r.get("position") else Action.ENTRY_DEAL
        return OrderRequest(aktion, r["symbol"], seite, Decimal(str(r["volume"])), magic=r["magic"], comment=r.get("comment", ""),
                            sl=Decimal(str(r.get("sl", 0))), tp=Decimal(str(r.get("tp", 0))), ticket=r.get("position") or None,
                            deviation=r.get("deviation", 20))

    def order_check(self, request: dict) -> SimpleNamespace | None:
        self._zaehle("order_check")
        res = self.sim.check(self._req(request))
        return SimpleNamespace(retcode=res.retcode, comment=res.comment, margin=0.0, margin_free=0.0)

    def order_send(self, request: dict) -> SimpleNamespace | None:
        self._zaehle("order_send")
        res = self.sim.send(self._req(request))
        if res is None:
            return None
        return SimpleNamespace(retcode=res.retcode, order=res.order, deal=res.deal, volume=float(res.volume), price=float(res.price),
                               comment="Done" if res.retcode == 10009 else "")
