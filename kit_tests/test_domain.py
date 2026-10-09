"""Rundung, Geld, Zeit, Kennungen, Retcode-Regel Code 0."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kit.domain import money, rounding, zeit
from kit.domain.types import Action, Namensraum, Side
from kit.orders import ids
from kit.orders.retcodes import einordnen
from kit_tests.hilfen import eurusd

D = Decimal


@given(st.decimals(min_value=D("0"), max_value=D("150"), places=4))
def test_volumen_nur_abrunden(v):
    spec = eurusd()
    r = rounding.volumen_abrunden(v, spec)
    if r is None:
        assert v < spec.volume_min or v <= 0
    else:
        assert spec.volume_min <= r <= min(v, spec.volume_max)
        assert r % spec.volume_step == 0


def test_sl_tp_vom_markt_weg():
    spec = eurusd()
    assert rounding.sl_runden(D("1.104996"), Side.BUY, spec) == D("1.10499")
    assert rounding.sl_runden(D("1.105004"), Side.SELL, spec) == D("1.10501")
    assert rounding.tp_runden(D("1.106004"), Side.BUY, spec) == D("1.10601")
    assert rounding.tp_runden(D("1.103996"), Side.SELL, spec) == D("1.10399")
    assert rounding.schutz_richtig(Side.BUY, D("1.1"), D("1.09"), D("1.12"))
    assert not rounding.schutz_richtig(Side.BUY, D("1.1"), D("1.11"), D("0"))
    assert rounding.sl_enger(Side.BUY, D("1.09"), D("1.095")) and not rounding.sl_enger(Side.BUY, D("1.09"), D("1.08"))
    assert rounding.sl_enger(Side.SELL, D("1.11"), D("1.105")) and not rounding.sl_enger(Side.SELL, D("1.11"), D("1.12"))
    assert rounding.abstand_ok(D("1.10500"), D("1.10400"), eurusd(stops_level=50))
    assert not rounding.abstand_ok(D("1.10500"), D("1.10480"), eurusd(stops_level=50))


def test_dez_float_verlustfrei():
    assert money.dez(1.1) == D("1.1")
    assert money.dez("0.10") == D("0.10")
    with pytest.raises(TypeError):
        money.dez(True)
    assert money.cent(D("1.005")) == D("1.00")


def test_berlin_sommerzeit_grenzen():
    vor = dt.datetime(2026, 3, 29, 0, 59, tzinfo=dt.UTC)
    nach = dt.datetime(2026, 3, 29, 1, 0, tzinfo=dt.UTC)
    assert zeit.berlin_offset(vor) == dt.timedelta(hours=1)
    assert zeit.berlin_offset(nach) == dt.timedelta(hours=2)
    assert zeit.berlin_offset(dt.datetime(2026, 10, 25, 0, 59, tzinfo=dt.UTC)) == dt.timedelta(hours=2)
    assert zeit.berlin_offset(dt.datetime(2026, 10, 25, 1, 0, tzinfo=dt.UTC)) == dt.timedelta(hours=1)
    assert zeit.berlin_tag(dt.datetime(2026, 7, 1, 22, 30, tzinfo=dt.UTC)) == dt.date(2026, 7, 2)
    with pytest.raises(ValueError):
        zeit.berlin_offset(dt.datetime(2026, 7, 1))


def test_kennung_deterministisch_und_magic_namensraum():
    a = ids.client_id("S-REV-01", "EURUSD", 1790000000, "ENTRY_DEAL")
    assert a == ids.client_id("S-REV-01", "EURUSD", 1790000000, "ENTRY_DEAL")
    assert a != ids.client_id("S-REV-01", "EURUSD", 1790000000, "ENTRY_DEAL", 1)
    m = ids.magic(Namensraum.PROBE, a)
    assert 0 < m < 2**63 and ids.namensraum(m) is Namensraum.PROBE and ids.ist_eigen(m)
    assert ids.namensraum(ids.magic(Namensraum.STRATEGIE, a)) is Namensraum.STRATEGIE
    assert not ids.ist_eigen(0) and not ids.ist_eigen(123456)
    assert len(ids.kommentar(a)) <= 31


def test_retcode_null_nur_mit_ticket_und_volumen():
    assert einordnen(0, Action.ENTRY_DEAL, ticket=5, volumen=D("0.1")).klasse == "DONE"
    assert einordnen(0, Action.ENTRY_DEAL, ticket=0, volumen=D("0.1")).klasse == "UNKNOWN"
    assert einordnen(0, Action.ENTRY_DEAL, ticket=5, volumen=D("0")).klasse == "UNKNOWN"
    assert einordnen(10009, Action.ENTRY_DEAL).klasse == "DONE"
    assert einordnen(12345678, Action.REDUCE_DEAL).klasse == "UNKNOWN"
    assert einordnen("10009", Action.ENTRY_DEAL).klasse == "UNKNOWN"
