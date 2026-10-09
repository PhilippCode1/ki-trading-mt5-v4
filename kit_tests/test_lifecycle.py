"""Lebenszyklus: Journal vor Netz, Demo-Vorrang, Neuversuche, SL-Pflicht, Wiederherstellung, Doppelmeldungen."""
from __future__ import annotations

from decimal import Decimal

from kit.broker.sim import Fehler
from kit.domain.types import Absicht, Action, Namensraum, OpStatus, Side
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.state.journal import Journal
from kit_tests.hilfen import aufbau

D = Decimal


def _einstieg(aid="I1", vol="0.10", sl="1.10000", tp="1.10800", side=Side.BUY) -> Absicht:
    return Absicht(aid, Action.ENTRY_DEAL, "EURUSD", side, D(vol), Namensraum.STRATEGIE, D(sl), D(tp))


def test_journal_vor_jeder_sendung(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    original = term.send
    beobachtet = []

    def spion(req):
        saetze = journal.lesen()
        beobachtet.append([s["art"] for s in saetze if s["daten"].get("magic") == req.magic])
        return original(req)
    term.send = spion
    op = lz.ausfuehren(_einstieg(), "c1")
    assert op.status is OpStatus.ERLEDIGT and op.gefuellt == D("0.10")
    assert beobachtet == [["OP_GEPLANT", "OP_GESENDET"]]          # fsync-Journal liegt vor dem Netz


def test_demo_vorrang_sperrt_auch_schutz(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    lz.ausfuehren(_einstieg(), "c1")
    ticket = term.positions()[0].ticket
    lz.demo_pruefung = lambda: "Konto ist REAL"
    for a in (_einstieg("I2"), Absicht("R", Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.10"), Namensraum.STRATEGIE, ticket=ticket),
              Absicht("P", Action.PROTECT_SLTP, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D("1.10100"), ticket=ticket)):
        op = lz.ausfuehren(a, f"x-{a.absicht_id}")
        assert op.status is OpStatus.LOKAL_ABGELEHNT and op.grund == "NICHT_DEMO"
    assert len(term.sendungen) == 1


def test_sl_pflicht_und_ticketpflicht(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    assert lz.ausfuehren(_einstieg(sl="0"), "c1").grund == "SL_FEHLT"
    assert lz.ausfuehren(Absicht("R", Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.1")), "c2").grund == "TICKET_FEHLT"
    assert term.sendungen == []


def test_kennung_wird_nie_zweimal_gesendet(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    lz.ausfuehren(_einstieg(), "c1")
    assert lz.ausfuehren(_einstieg("I9"), "c1").grund == "OP_EXISTIERT"
    assert len(term.sendungen) == 1


def test_requote_neuversuch_dann_erfolg(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(ids.magic(Namensraum.STRATEGIE, "c1"), Fehler("REJECT", 10004, einmal=True))
    op = lz.ausfuehren(_einstieg(), "c1")
    assert op.status is OpStatus.ERLEDIGT and op.versuche == 2 and op.retcodes == [10004, 10009]


def test_check_ablehnung_sendet_nicht(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    op = lz.ausfuehren(_einstieg(sl="1.10600"), "c1")                  # SL über dem Kurs
    assert op.status is OpStatus.ABGELEHNT and op.grund == "CHECK_10016" and term.sendungen == []


def test_ausnahme_beim_senden_ist_unbekannt(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(ids.magic(Namensraum.STRATEGIE, "c1"), Fehler("EXCEPTION"))
    op = lz.ausfuehren(_einstieg(), "c1")
    assert op.status is OpStatus.UNBEKANNT and lz.reserviert("EURUSD") == D("0.10")
    assert lz.ausfuehren(_einstieg("I2"), "c2").grund == "STATE_BLOCK"


def test_absturz_nach_sendung_wiederherstellung(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(ids.magic(Namensraum.STRATEGIE, "c1"), Fehler("TIMEOUT_EXECUTED"))
    lz.ausfuehren(_einstieg(), "c1")
    term.liefere_spaete()
    neu = Lebenszyklus(term, Journal(tmp_path / "journal", uhr=uhr))
    neu.wiederherstellen()
    assert neu.ops["c1"].status is OpStatus.UNBEKANNT
    neu.klaeren()
    assert neu.ops["c1"].status is OpStatus.ERLEDIGT and neu.ops["c1"].gefuellt == D("0.10")


def test_teilfill_rest_bleibt_reserviert_bis_nachweis(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(ids.magic(Namensraum.STRATEGIE, "c1"), Fehler("PARTIAL", anteil=D("0.3")))
    op = lz.ausfuehren(_einstieg(), "c1")
    assert op.status is OpStatus.TEILWEISE and lz.reserviert("EURUSD") == D("0.07")
    uhr.vor(61)
    lz.klaeren()
    assert op.status is OpStatus.ERLEDIGT and lz.reserviert("EURUSD") == 0 and op.gefuellt == D("0.03")
