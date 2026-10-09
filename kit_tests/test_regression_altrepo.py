"""Regressionen aus dem Altrepo (mt5-trading-ai, tests/test_zweige_mt5.py) – je Fall die Lehre, übertragen auf kit.

Herkunft (nur gelesen, nicht ausgeführt): test_ohne_ergebnis_gibt_es_keinen_erfolgscode, test_ein_benannter_fehlercode_ist_keine_
fuellung, test_ein_fill_ohne_ticket_latcht_den_halt…, test_ohne_gemeldete_fuellart_wird_nicht_geraten, test_ohne_tick_meldet_das_
terminal_keinen_kurs, test_ohne_konto_info_ist_das_terminal_nicht_verfuegbar, test_ein_unabfragbarer_bestand_verhindert_die_
schliessung, test_shutdown_ohne_sitzung_tut_nichts…, test_ein_terminal_das_sich_nicht_aufbaut_ist_kein_venue.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from kit import paths
from kit.broker.mt5_real import Mt5Terminal
from kit.broker.seam import BrokerFehler
from kit.broker.sim import SimTerminal, Uhr
from kit.broker.sim_modul import SimMt5Modul
from kit.domain.types import Absicht, Action, Namensraum, OpStatus, Side
from kit.orders.lifecycle import Lebenszyklus
from kit.state.journal import Journal
from kit_tests.hilfen import eurusd

D = Decimal


def _paar():
    uhr = Uhr()
    sim = SimTerminal([eurusd()], uhr=uhr)
    sim.setze_kurs("EURUSD", "1.10500", "1.10502")
    modul = SimMt5Modul(sim, versatz_s=0)
    term = Mt5Terminal(modul, versatz_s=0, schluessel_ordner=paths.kit_home() / "geheim", uhr=uhr, prozess_pruefen=lambda: True)
    term.verbinden()
    return sim, modul, term


def _einstieg():
    return Absicht("R1", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D("1.10000"), D("1.11000"))


def _antwort(modul, **felder):
    modul.order_send = lambda req: SimpleNamespace(**{"retcode": 10009, "order": 0, "deal": 0, "volume": 0.0, "price": 0.0,
                                                      "comment": "", **felder})


def test_ohne_ergebnis_kein_erfolg(tmp_path):
    sim, modul, term = _paar()
    modul.order_send = lambda req: None
    op = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit)).ausfuehren(_einstieg(), "r1")
    assert op.status is OpStatus.UNBEKANNT and op.retcodes == [-1]


def test_benannter_fehlercode_ist_keine_fuellung(tmp_path):
    sim, modul, term = _paar()
    _antwort(modul, retcode=10019, order=77, volume=0.1)            # NO_MONEY trotz Ticket und Menge
    op = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit)).ausfuehren(_einstieg(), "r1")
    assert op.status is OpStatus.ABGELEHNT and op.gefuellt == 0


def test_fill_ohne_ticket_ist_unbekannt_nicht_erledigt(tmp_path):
    sim, modul, term = _paar()
    _antwort(modul, volume=0.1)                                     # DONE mit Menge, aber ohne Order- und Deal-Ticket
    lz = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit))
    op = lz.ausfuehren(_einstieg(), "r1")
    assert op.status is OpStatus.UNBEKANNT and lz.reserviert("EURUSD")


def test_ohne_gemeldete_fuellart_wird_nicht_geraten():
    sim, modul, term = _paar()
    alt = modul.symbol_info
    modul.symbol_info = lambda n: SimpleNamespace(**{**vars(alt(n)), "filling_mode": 0})
    with pytest.raises(BrokerFehler, match="Füllart"):
        term.symbol("EURUSD")


def test_ohne_tick_kein_kurs_und_keine_sendung(tmp_path):
    sim, modul, term = _paar()
    modul.symbol_info_tick = lambda n: None
    with pytest.raises(BrokerFehler):
        term.quote("EURUSD")
    op = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit)).ausfuehren(_einstieg(), "r1")
    assert op.status is OpStatus.ABGELEHNT and modul.aufrufe.get("order_send", 0) == 0


def test_ohne_konto_info_nicht_verfuegbar_und_demo_waechter_sperrt(tmp_path):
    sim, modul, term = _paar()
    modul.account_info = lambda: None
    with pytest.raises(BrokerFehler):
        term.account()
    op = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit)).ausfuehren(_einstieg(), "r1")
    assert op.grund == "NICHT_DEMO" and modul.aufrufe.get("order_send", 0) == 0


def test_unabfragbarer_bestand_ist_kein_leeres_buch():
    sim, modul, term = _paar()
    modul.positions_get = lambda: None
    with pytest.raises(BrokerFehler, match="nicht dasselbe"):
        term.positions()


def test_trennen_ohne_sitzung_tut_nichts_und_kein_terminal_kein_aufbau():
    sim = SimTerminal([eurusd()])
    term = Mt5Terminal(None, prozess_pruefen=lambda: False)
    term.trennen()                                                  # ohne Modul: kein Fehler, kein Import
    with pytest.raises(BrokerFehler, match="Kein laufendes"):
        term.verbinden()
    modul = SimMt5Modul(sim)
    modul.initialize = lambda path=None: False
    with pytest.raises(BrokerFehler, match="initialize"):
        Mt5Terminal(modul, prozess_pruefen=lambda: True).verbinden()
