"""SIM-Terminal: Eröffnen/Schließen, Gewinn in Kontowährung, Kerzenpfad (SL zuerst, Lücke), Prüfungen."""
from __future__ import annotations

from decimal import Decimal

from kit.broker.sim import SimTerminal
from kit.domain.types import Action, Bar, KontoModus, OrderRequest, Side
from kit_tests.hilfen import eurusd

D = Decimal


def _term(modus=KontoModus.HEDGING) -> SimTerminal:
    t = SimTerminal([eurusd()], modus=modus, provision_je_lot=D("3.00"))
    t.setze_kurs("EURUSD", "1.10000", "1.10002")
    return t


def _auf(t, side=Side.BUY, vol="0.10", sl="1.09000", tp="1.11000", magic=7):
    return t.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", side, D(vol), magic=magic, sl=D(sl), tp=D(tp)))


def test_gewinn_in_kontowaehrung():
    t = _term()
    _auf(t)
    p = t.positions()[0]
    t.setze_kurs("EURUSD", "1.10102", "1.10104")
    r = t.send(OrderRequest(Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.10"), magic=7, ticket=p.ticket))
    assert r.retcode == 10009 and not t.positions()
    aus = t.deals(0, 2**62)[-1]
    assert aus.profit == D("8.60")          # 100 Punkte × 0,86 EUR × 0,10 Lot
    assert aus.commission == D("-0.30")


def test_kerze_sl_vor_tp_und_luecke():
    t = _term()
    _auf(t, sl="1.09900", tp="1.10100")
    aus = t.kerze(Bar("EURUSD", 1, D("1.10000"), D("1.10200"), D("1.09800"), D("1.10050")))
    assert aus[0].reason == "SL" and aus[0].price == D("1.09900")
    _auf(t, sl="1.09900", tp="1.10100", magic=8)
    aus = t.kerze(Bar("EURUSD", 2, D("1.09500"), D("1.09600"), D("1.09400"), D("1.09550")))
    assert aus[0].reason == "SL" and aus[0].price == D("1.09500")     # Lücke: schlechterer Eröffnungskurs


def test_short_schliesst_zum_ask():
    t = _term()
    _auf(t, side=Side.SELL, sl="1.10200", tp="1.09900")
    aus = t.kerze(Bar("EURUSD", 1, D("1.10000"), D("1.10010"), D("1.09895"), D("1.10000"), spread_points=10))
    assert aus == []                         # Ask-Tief 1.09905 erreicht TP 1.09900 nicht
    aus = t.kerze(Bar("EURUSD", 2, D("1.10000"), D("1.10010"), D("1.09880"), D("1.10000"), spread_points=10))
    assert aus[0].reason == "TP"


def test_netting_eine_position_je_symbol():
    t = _term(KontoModus.NETTING)
    _auf(t, vol="0.10")
    _auf(t, vol="0.20", magic=9)
    assert len(t.positions()) == 1 and t.positions()[0].volume == D("0.30")
    _auf(t, side=Side.SELL, vol="0.40", sl="1.11000", tp="1.09000", magic=10)
    p = t.positions()[0]
    assert p.side is Side.SELL and p.volume == D("0.10") and t.deals(0, 2**62)[-1].entry == "INOUT"


def test_pruefung_lehnt_ab():
    t = _term()
    req = OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.015"), magic=1, sl=D("1.09"))
    assert t.check(req).retcode == 10014
    req = OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), magic=1, sl=D("1.10100"))
    assert t.check(req).retcode == 10016
    req = OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("90"), magic=1, sl=D("1.09"))
    assert t.check(req).retcode == 10019
    assert t.check(OrderRequest(Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.10"), magic=1, ticket=999)).retcode == 10036


def test_kapitalbewegung_ist_kein_handel():
    t = _term()
    d = t.kapital(D("500"))
    assert d.side is None and d.geld == D("500") and t.account().balance == D("10500")
