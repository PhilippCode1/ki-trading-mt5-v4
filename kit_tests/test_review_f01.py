"""Regressionstests zu den Befunden des unabhängigen Code-Reviews in Lauf F-01 (je Befund mindestens ein Test)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit.broker.sim import Fehler, SimTerminal
from kit.domain.types import (
    Absicht,
    Action,
    Bar,
    DealArt,
    HandelsModus,
    KontoModus,
    Namensraum,
    OpStatus,
    OrderRequest,
    Side,
)
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.orders.reconcile import Abgleich
from kit.orders.retcodes import einordnen
from kit.state import store
from kit.state.journal import Journal
from kit_tests.hilfen import aufbau, eurusd

D = Decimal


def _einstieg(aid="I1", vol="0.10", sl="1.10000", tp="1.10800") -> Absicht:
    return Absicht(aid, Action.ENTRY_DEAL, "EURUSD", Side.BUY, D(vol), Namensraum.STRATEGIE, D(sl), D(tp))


def _m(cid: str) -> int:
    return ids.magic(Namensraum.STRATEGIE, cid)


# ---------------------------------------------------------------------------------------------- Lebenszyklus
def test_lokale_ablehnung_ueberdeckt_nie_echte_operation_nach_neustart(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(_m("c1"), Fehler("TIMEOUT_EXECUTED"))
    lz.ausfuehren(_einstieg(), "c1")
    assert lz.ausfuehren(_einstieg(), "c1").grund == "OP_EXISTIERT"
    neu = Lebenszyklus(term, Journal(tmp_path / "journal", uhr=uhr))
    neu.wiederherstellen()
    assert neu.ops["c1"].status is OpStatus.UNBEKANNT and neu.reserviert("EURUSD") == D("0.10")
    assert neu.ausfuehren(_einstieg(), "c1").grund == "OP_EXISTIERT"
    assert len(term.sendungen) == 1


def test_spaeter_rest_nach_teil_negativnachweis_wird_gemeldet(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(_m("c1"), Fehler("PARTIAL", anteil=D("0.3")))
    op = lz.ausfuehren(_einstieg(), "c1")
    uhr.vor(61)
    lz.klaeren()
    assert op.status is OpStatus.ERLEDIGT and op.gefuellt == D("0.03")
    term._ausfuehren(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.07"), magic=op.magic, sl=D("1.10000")), None)
    lz.klaeren()
    assert op.gefuellt == D("0.10") and "NEGPROOF_FALSIFIED" in [v["art"] for v in lz.vorfaelle]
    assert lz.gesperrt("EURUSD") == "NEGPROOF_FALSIFIED"


def test_operation_wird_nur_einmal_angestossen(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(_m("c1"), Fehler("TIMEOUT_EXECUTED"))
    op = lz.ausfuehren(_einstieg(), "c1")
    lz.senden(op)
    lz.senden(op)
    assert len(term.sendungen) == 1


def test_standard_demo_pruefung_ist_fail_closed(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.handelsmodus = HandelsModus.REAL
    assert lz.ausfuehren(_einstieg(), "c1").grund == "NICHT_DEMO" and term.sendungen == []
    term.handelsmodus = HandelsModus.DEMO

    def kaputt():
        raise ConnectionError("weg")
    term.account = kaputt
    assert lz.ausfuehren(_einstieg("I2"), "c2").grund == "NICHT_DEMO" and term.sendungen == []


def test_neue_operation_sendet_nur_den_rest_der_absicht(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(_m("c1"), Fehler("PARTIAL", anteil=D("0.3")))
    lz.ausfuehren(_einstieg(), "c1")
    uhr.vor(61)
    lz.klaeren()
    op2 = lz.ausfuehren(_einstieg(), "c2")
    assert term.sendungen[-1].volume == D("0.07") and op2.status is OpStatus.ERLEDIGT
    assert lz.ausfuehren(_einstieg(), "c3").grund == "ABSICHT_ERFUELLT"


def test_fehler_vor_der_sendung_ist_abgelehnt_und_blockiert_nicht(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.check = lambda req: None
    op = lz.ausfuehren(_einstieg(), "c1")
    assert op.status is OpStatus.ABGELEHNT and op.grund.startswith("VOR_SENDUNG") and term.sendungen == []
    assert lz.gesperrt("EURUSD") is None


def test_kontoweite_sperre_bei_account_retcode(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.setze_fehler(_m("c1"), Fehler("REJECT", 10027))
    assert lz.ausfuehren(_einstieg(), "c1").status is OpStatus.ABGELEHNT
    assert lz.ausfuehren(_einstieg("I2"), "c2").grund == "STATE_BLOCK" and len(term.sendungen) == 1


def test_pending_orders_nicht_freigegeben(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    a = Absicht("P", Action.PLACE_PENDING, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.09"))
    assert lz.ausfuehren(a, "p1").grund == "PENDING_NICHT_FREIGEGEBEN" and term.sendungen == []


def test_retcode_null_bei_sltp_nur_ueber_abgleich():
    assert einordnen(0, Action.PROTECT_SLTP, ticket=5).klasse == "UNKNOWN"
    assert einordnen(0, Action.CANCEL_PENDING, ticket=5).klasse == "UNKNOWN"


# ---------------------------------------------------------------------------------------------- Zustand und Journal
@pytest.mark.parametrize(("roh", "stufe"), [("﻿K3\r\n".encode(), 3), ("K3\r\n".encode("utf-16"), 3), (b"K1 K3", 3),
                                            (b"k2", 2), (b"???", 1)])
def test_stop_datei_jede_kodierung(tmp_path, roh, stufe):
    (tmp_path / "STOP").write_bytes(roh)
    assert store.stop_stufe(tmp_path) == stufe


def test_journal_uhr_rueckwaerts_ueber_tagesgrenze(tmp_path):
    t = [1_790_000_000.0 + 86400]
    j = Journal(tmp_path, uhr=lambda: t[0])
    j.schreiben("A", "OK", "a")
    t[0] -= 86400
    j.schreiben("B", "OK", "b")
    assert [s["art"] for s in Journal(tmp_path, uhr=lambda: t[0]).lesen()] == ["A", "B"]


def test_journal_abgerissene_letzte_zeile_wird_verworfen(tmp_path):
    j = Journal(tmp_path)
    j.schreiben("A", "OK", "a")
    datei = next(tmp_path.glob("*.jsonl"))
    with open(datei, "ab") as fh:
        fh.write(b'{"seq": 2, "t": 1')
    arten = [s["art"] + ":" + s["code"] for s in Journal(tmp_path).lesen()]
    assert arten == ["A:OK", "VORFALL:JOURNAL_REST_VERWORFEN"]


@pytest.mark.parametrize("schluessel", ["account_login", "login_nr", "trade_server", "kontonr", "Name", "e_mail_adresse"])
def test_journal_verbietet_schluesselvarianten(tmp_path, schluessel):
    with pytest.raises(ValueError):
        Journal(tmp_path).schreiben("X", "OK", "x", **{schluessel: "1"})


def test_speichern_wiederholt_bei_sperre_und_scheitert_fail_closed(tmp_path, monkeypatch):
    s = store.StateStore(tmp_path)
    echt = store.os.replace
    zaehler = {"n": 0}

    def blockiert_zweimal(a, b):
        zaehler["n"] += 1
        if zaehler["n"] <= 2:
            raise PermissionError("gesperrt")
        return echt(a, b)
    monkeypatch.setattr(store.os, "replace", blockiert_zweimal)
    monkeypatch.setattr(store.time, "sleep", lambda s: None)
    s.speichern({"a": 1})
    assert s.laden(journal_vorhanden=True) == {"a": 1}

    def immer(a, b):
        raise PermissionError("dauerhaft")
    monkeypatch.setattr(store.os, "replace", immer)
    with pytest.raises(store.ZustandFehler):
        s.speichern({"a": 2})


# ---------------------------------------------------------------------------------------------- SIM
def _term(modus=KontoModus.HEDGING) -> SimTerminal:
    t = SimTerminal([eurusd()], modus=modus)
    t.setze_kurs("EURUSD", "1.10000", "1.10002")
    return t


def test_luecke_ueber_tp_fuellt_zum_eroeffnungskurs():
    t = _term()
    t.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), magic=7, sl=D("1.09900"), tp=D("1.10100")))
    aus = t.kerze(Bar("EURUSD", 1, D("1.10200"), D("1.10250"), D("1.09800"), D("1.10000")))
    assert aus[0].reason == "TP" and aus[0].price == D("1.10200")


def test_netting_fremdhandel_verschmilzt():
    t = _term(KontoModus.NETTING)
    t.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), magic=7, sl=D("1.09")))
    t.fremder_handel("EURUSD", Side.BUY, D("0.20"))
    assert len(t.positions()) == 1 and t.positions()[0].volume == D("0.30")
    assert t.deals(0, 2**62)[-1].reason == "CLIENT"


# ---------------------------------------------------------------------------------------------- Abgleich
def _einstieg_lz(lz, cid="c1"):
    return lz.ausfuehren(Absicht(f"I-{cid}", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D("1.10000"),
                                 D("1.10800")), cid)


def test_kein_fehlalarm_nach_schluss_per_ticket(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg_lz(lz)
    p = term.positions()[0]
    lz.ausfuehren(Absicht("R", Action.REDUCE_DEAL, "EURUSD", Side.SELL, p.volume, Namensraum.STRATEGIE, ticket=p.ticket), "r1")
    assert ab.laufen().differenzen == [] and ab.laufen().differenzen == []


def test_kein_fehlalarm_bei_netting_aufstockung(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path, modus=KontoModus.NETTING)
    ab = Abgleich(lz, journal)
    _einstieg_lz(lz, "c1")
    lz.ops["c1"].status = OpStatus.ERLEDIGT
    a2 = Absicht("I-c2", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.STRATEGIE, D("1.10000"), D("1.10800"))
    term.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), magic=_m("c2"), sl=D("1.10000")))
    lz.planen(a2, "c2")
    lz.ops["c2"].status, lz.ops["c2"].gefuellt = OpStatus.ERLEDIGT, D("0.10")
    lz.ops["c2"].deals = [d.ticket for d in term.deals(0, 2**62) if d.magic == _m("c2")]
    assert ab.laufen().differenzen == []


def test_spaet_sichtbarer_stop_out_wird_erkannt(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    _einstieg_lz(lz)
    t0 = uhr()
    ab.laufen()
    uhr.vor(30)
    ab.laufen()
    uhr.t = t0 + 10
    term.stop_out(term.positions()[0].ticket)          # bei t0+10 ausgeführt, erst nach dem Lauf t0+30 sichtbar
    uhr.t = t0 + 31
    assert ab.laufen().k2


def test_neustart_zaehlt_deals_nicht_doppelt(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.kapital(D("500"))
    assert Abgleich(lz, journal).laufen().kapital == D("500")
    j2 = Journal(tmp_path / "journal", uhr=uhr)
    lz2 = Lebenszyklus(term, j2)
    lz2.wiederherstellen()
    assert Abgleich(lz2, j2).laufen().kapital == 0
    assert sum(1 for s in j2.lesen() if s["art"] == "DEAL") == 1


def test_gebuehren_sind_kosten_nicht_kapital(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.kapital(D("-40"), art=DealArt.GEBUEHR)
    b = Abgleich(lz, journal).laufen()
    assert b.kosten == D("-40") and b.kapital == 0


def test_netting_mit_fremdvolumen_keine_automatische_aktion(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path, modus=KontoModus.NETTING)
    _einstieg_lz(lz)
    term.fremder_handel("EURUSD", Side.BUY, D("0.20"))
    b = Abgleich(lz, journal).laufen()
    assert b.aktionen == [] and any("Fremdvolumen" in m for m in b.meldungen)


def test_abgleich_journalisiert_nur_bei_aenderung(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    ab = Abgleich(lz, journal)
    ab.laufen()
    uhr.vor(5)
    ab.laufen()
    uhr.vor(5)
    ab.laufen()
    assert sum(1 for s in journal.lesen() if s["art"] == "ABGLEICH") == 1
