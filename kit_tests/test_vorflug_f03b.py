"""Regressionen zur Vorflug-Prüfung F-03b (recherchierte Semantik der echten MetaTrader5-Python-API, Workflow mit Gegenprüfung):
Serverversatz und Uhrabgleich, Python-API-Schalter, Marktübersicht, ablaufende Retcode-Sperren, Zuordnung über die Positions-ID
(Handschluss und SL/TP mit magic 0), 10009 ohne Deal-Ticket, eigener Auftrag mit Handgrund."""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit import paths
from kit.broker.mt5_real import Mt5Terminal
from kit.broker.seam import BrokerFehler
from kit.broker.sim import Fehler, SimTerminal, Uhr
from kit.broker.sim_modul import SimMt5Modul
from kit.domain.types import Absicht, Action, Bar, Namensraum, OpStatus, SendResult, Side
from kit.orders import ids
from kit.orders.lifecycle import RETCODE_SPERRE_S, Lebenszyklus
from kit.orders.reconcile import Abgleich
from kit.run.loop import Bot, Ende
from kit.run.trockenlauf import konfiguration
from kit.state import sperren as sp
from kit.state.journal import Journal
from kit_tests.hilfen import aufbau, bot_aufbau, eurusd

D = Decimal


def _mt5(versatz_s=10800, terminal_versatz=10800, pc_vor_s=0.0, **kw):
    uhr = Uhr()
    sim = SimTerminal([eurusd(), eurusd("EURJPY")], uhr=uhr)
    sim.setze_kurs("EURUSD", "1.10500", "1.10502")
    modul = SimMt5Modul(sim, versatz_s=versatz_s, **kw)
    pc = Uhr(uhr() + pc_vor_s)
    term = Mt5Terminal(modul, versatz_s=terminal_versatz, schluessel_ordner=paths.kit_home() / "geheim", uhr=pc,
                       prozess_pruefen=lambda: True)
    term.verbinden()
    return sim, uhr, pc, modul, term


def test_ohne_serverversatz_keine_historie_und_kein_start(tmp_path):
    sim, uhr, pc, modul, term = _mt5(terminal_versatz=None)
    with pytest.raises(BrokerFehler, match="Serverversatz"):
        term.deals(0, 10**10)
    bot = Bot(term, tmp_path / "a", konfiguration(), modus="sim", journal_fsync=False)
    with pytest.raises(Ende, match="Serverversatz"):
        bot.starten()


def test_python_api_schalter_sperrt_handel_ohne_sendung(tmp_path):
    sim, uhr, pc, modul, term = _mt5(tradeapi_disabled=True)
    assert term.account().trade_allowed is False
    lz = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit), demo_pruefung=lambda: None if term.account().trade_allowed else "aus")
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.01"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    assert lz.ausfuehren(a, "a1").grund == "NICHT_DEMO"
    assert modul.aufrufe.get("order_send", 0) == 0 and modul.aufrufe.get("order_check", 0) == 0


def test_uhrabweichung_wird_ausgeglichen(tmp_path):
    sim, uhr, pc, modul, term = _mt5(pc_vor_s=8.0)                 # PC-Uhr geht 8 s vor
    term.versatz_s = None

    def schlaf(s):
        uhr.vor(s)
        pc.vor(s)
    assert term.messe_versatz("EURUSD", schlaf=schlaf) == 10800 and abs(term.rest_s + 8) < 0.01
    q = term.quote("EURUSD")
    assert abs(term.zeit() - q.time_msc / 1000) < 0.01               # Kurs wirkt nicht mehr 8 s alt
    lz = Lebenszyklus(term, Journal(tmp_path, uhr=term.zeit))
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.01"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    sim.setze_fehler(ids.magic(Namensraum.PROBE, "a1"), Fehler("TIMEOUT_EXECUTED"))
    op = lz.ausfuehren(a, "a1")
    sim.liefere_spaete()
    schlaf(61)
    lz.klaeren()
    assert op.status is OpStatus.ERLEDIGT and op.gefuellt == D("0.01")   # kein falscher Negativnachweis


def test_symbol_ausserhalb_der_marktuebersicht():
    sim, uhr, pc, modul, term = _mt5()
    modul.nicht_ausgewaehlt.add("EURJPY")
    sim.setze_kurs("EURJPY", "172.100", "172.120")
    assert term.quote("EURJPY").bid == D("172.1")


def test_retcode_sperre_laeuft_ab_beobachtungssperre_nicht(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    term.send = lambda req: (term.sendungen.append(req), SendResult(10018))[1]     # Markt geschlossen
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    lz.ausfuehren(a, "a1")
    assert lz.gesperrt("EURUSD") == "RETCODE_10018"
    lz.sperren("EURUSD", "FREMDAKTIVITAET")
    uhr.vor(RETCODE_SPERRE_S + 1)
    assert lz.gesperrt("EURUSD") == "FREMDAKTIVITAET"                   # dauerhafte Sperre bleibt
    del lz.symbol_sperren["EURUSD"]
    assert lz.gesperrt("EURUSD") is None                                  # Retcode-Sperre ist abgelaufen
    lz2 = Lebenszyklus(term, journal)
    lz2.wiederherstellen()
    assert lz2.gesperrt("EURUSD") == "FREMDAKTIVITAET"
    journal.schreiben("BOT_ENTSPERRT", "SYMBOL:EURUSD", "Betreiber")
    lz2.wiederherstellen()
    assert lz2.gesperrt("EURUSD") is None
    assert sp.symbol_sperren(journal.lesen(), uhr()) == {}


def test_status_zeigt_symbolsperren_und_entsperren_symbol(tmp_path, monkeypatch):
    from kit import bedienung
    from kit.state import pin
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    b2 = Bot(bot.t, paths.ablage("probe"), bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    b2.starten()
    b2.lz.sperren("GBPUSD", "FREMDPOSITION")
    assert bedienung.status("probe")["symbol_sperren"] == {"GBPUSD": "FREMDPOSITION"}
    werte = ["richtig-0001", "richtig-0001", "richtig-0001"]
    monkeypatch.setattr(bedienung, "_pin_eingabe", lambda text: werte.pop(0))
    monkeypatch.setattr(pin.time, "sleep", lambda s: None)
    bedienung.pin_setzen()
    assert "SYMBOL:GBPUSD" in bedienung.entsperren("probe", "SYMBOL:GBPUSD")
    b3 = Bot(bot.t, paths.ablage("probe"), bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    b3.starten()
    assert b3.lz.gesperrt("GBPUSD") is None


def _offen(tmp_path, **sim_kw):
    term, lz, uhr, journal = aufbau(tmp_path)
    for k, v in sim_kw.items():
        setattr(term, k, v)
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    op = lz.ausfuehren(a, "a1")
    ab = Abgleich(lz, journal)
    ab.laufen()
    return term, lz, uhr, journal, op, ab


def test_handschluss_mit_magic_null_ist_manueller_eingriff(tmp_path):
    term, lz, uhr, journal, op, ab = _offen(tmp_path)
    d = term.manuell_schliessen(term.positions()[0].ticket)
    assert d.magic == 0
    uhr.vor(5)
    b = ab.laufen()
    assert b.manuelle_eingriffe and lz.symbol_sperren["EURUSD"] == "MANUELLER_EINGRIFF" and not b.fremd_deals


def test_sl_mit_magic_null_ist_eigener_ausstieg_auch_nach_neustart(tmp_path):
    term, lz, uhr, journal, op, ab = _offen(tmp_path, sltp_magic_null=True)
    ab2 = Abgleich(lz, journal)                                          # Neustart zwischen IN- und SL-Deal
    term.kerze(Bar("EURUSD", int(uhr()), D("1.1050"), D("1.1051"), D("1.0990"), D("1.0995")))
    uhr.vor(5)
    b = ab2.laufen()
    assert [x.magic for x in b.server_ausstiege] == [0] and not b.fremd_deals and "EURUSD" not in lz.symbol_sperren
    from kit.risk.limits import Tradebuch
    buch = Tradebuch()
    for s in journal.lesen():
        buch.deal(s)
    assert [t.geschlossen for t in buch.geschlossene(Namensraum.PROBE)] == [True]


def test_fremder_deal_auf_unbekannter_position_bleibt_fremd(tmp_path):
    term, lz, uhr, journal, op, ab = _offen(tmp_path)
    term.fremder_handel("EURUSD", Side.SELL, D("0.20"))
    uhr.vor(5)
    b = ab.laufen()
    assert b.fremd_deals and lz.symbol_sperren["EURUSD"] in ("FREMDAKTIVITAET", "FREMDPOSITION")


def test_erledigt_ohne_deal_ticket_wird_nachgetragen(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    echt = term.send

    def ohne_deal(req):
        res = echt(req)
        return SendResult(res.retcode, order=res.order, deal=0, volume=res.volume, price=res.price)
    term.send = ohne_deal
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    op = lz.ausfuehren(a, "a1")
    assert op.status is OpStatus.ERLEDIGT and op.deals == []
    ab = Abgleich(lz, journal)
    ab.laufen()
    assert op.deals                                                       # beobachtetes Ticket nachgetragen
    del term._pos[term.positions()[0].ticket]                             # Position verschwindet ohne Deal
    uhr.vor(5)
    assert any("POSITION_FEHLT" in x for x in ab.laufen().differenzen)


def test_eigener_auftrag_mit_handgrund_ist_kein_eingriff(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    echt = term._deal

    def als_client(**kw):
        if kw.get("grund") == "EXPERT":
            kw["grund"] = "CLIENT"                                        # Broker meldet Python-Aufträge als CLIENT
        return echt(**kw)
    term._deal = als_client
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    lz.ausfuehren(a, "a1")
    b = Abgleich(lz, journal).laufen()
    assert not b.manuelle_eingriffe and "EURUSD" not in lz.symbol_sperren
