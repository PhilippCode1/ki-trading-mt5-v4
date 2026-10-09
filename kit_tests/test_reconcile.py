"""Abgleich: Server-Ausstieg ohne Halt, Stop-out → K2, manueller Eingriff/Fremdposition sperren, Schutzpflicht, Kapital."""
from __future__ import annotations

from decimal import Decimal

from kit.domain.types import Absicht, Action, Bar, Namensraum, OpStatus, Side
from kit.orders.reconcile import Abgleich
from kit_tests.hilfen import aufbau

D = Decimal


def _einstieg(lz, cid="c1", sl="1.10000", tp="1.10800"):
    return lz.ausfuehren(Absicht(f"I-{cid}", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D(sl), D(tp)), cid)


def test_server_sl_ist_eigener_ausstieg_ohne_halt(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg(lz)
    ab.laufen()
    uhr.vor(60)
    term.kerze(Bar("EURUSD", int(uhr()), D("1.10400"), D("1.10450"), D("1.09900"), D("1.10000")))
    b = ab.laufen()
    assert len(b.server_ausstiege) == 1 and b.server_ausstiege[0].reason == "SL"
    assert not b.k2 and "EURUSD" not in lz.symbol_sperren and b.differenzen == []
    assert _einstieg(lz, "c2").status is OpStatus.ERLEDIGT          # weiterhandeln möglich


def test_stop_out_ist_k2(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg(lz)
    term.stop_out(term.positions()[0].ticket)
    b = ab.laufen()
    assert b.k2 and [v["art"] for v in lz.vorfaelle] == ["STOP_OUT"]


def test_manueller_eingriff_und_fremdposition_sperren(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg(lz)
    term.manuell_schliessen(term.positions()[0].ticket, "MOBILE")
    b = ab.laufen()
    assert b.manuelle_eingriffe and lz.symbol_sperren["EURUSD"] == "MANUELLER_EINGRIFF"
    term2, lz2, uhr2, journal2 = aufbau(tmp_path / "zwei")
    fremd = term2.fremder_handel("EURUSD", Side.SELL, D("0.50"))
    b2 = Abgleich(lz2, journal2).laufen()
    assert b2.fremde and lz2.symbol_sperren["EURUSD"] in {"FREMDAKTIVITAET", "FREMDPOSITION"}
    assert all(a.ticket != fremd.ticket for _, a in b2.aktionen)    # Fremdpositionen nie anfassen
    assert _einstieg(lz2).grund == "STATE_BLOCK"


def test_eigene_position_ohne_sl_wird_geschuetzt_oder_geschlossen(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg(lz)
    p = term.positions()[0]
    from dataclasses import replace
    term._pos[p.ticket] = replace(p, sl=D("0"))                      # Broker hat den SL verloren
    b = ab.laufen()
    assert [a.action for _, a in b.aktionen] == [Action.PROTECT_SLTP] and b.aktionen[0][1].sl == D("1.10000")
    uhr.vor(31)
    b = ab.laufen()
    assert [a.action for _, a in b.aktionen] == [Action.REDUCE_DEAL]
    cid, a = b.aktionen[0]
    assert lz.ausfuehren(a, cid).status is OpStatus.ERLEDIGT and term.positions() == []


def test_einzahlung_ist_kapital_kein_verlust(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.kapital(D("-250"))
    b = Abgleich(lz, journal).laufen()
    assert b.kapital == D("-250") and not b.fremd_deals and not lz.symbol_sperren
