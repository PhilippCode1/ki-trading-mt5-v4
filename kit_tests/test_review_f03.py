"""Regressionen zu den Befunden der zwei unabhängigen F-03-Reviews (Sicherheit; Risiko/Tore) – je Befund ein Test."""
from __future__ import annotations

import os
import time
from decimal import Decimal

import pytest

from kit import betrieb, live_guard, paths
from kit.broker.sim import Fehler
from kit.domain.types import Absicht, Action, HandelsModus, KontoModus, Namensraum, OpStatus, SendResult, Side
from kit.gates import tore
from kit.gates.tor_t import auswerten
from kit.orders import ids
from kit.run.loop import Bot, Ende
from kit.state.journal import Journal
from kit.state.store import stop_setzen
from kit.strategy.attrappe import Attrappe
from kit.strategy.base import Signal, strategie_hash
from kit_tests.hilfen import bot_aufbau, ticken
from kit_tests.test_loop import _arten, _einstieg, _kerzen, _neu

D = Decimal


def _start(tmp_path, **kw):
    sim, uhr, bot, melder = bot_aufbau(tmp_path, strategie=Attrappe(symbole=("EURUSD", "GBPUSD")), **kw)
    bot.starten()
    return sim, uhr, bot, melder


# ------------------------------------------------------------------------------------------ Sicherheit
def test_einzelprobe_trotz_sperre_verweigert(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True)
    live_guard.konto_registrieren(bot.t, paths.kit_home() / "freigaben")
    ablage = paths.ablage("probe")
    vor = Bot(bot.t, ablage, bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    vor.starten()
    vor._sperren("K2", "Test")
    with pytest.raises(live_guard.LiveGesperrt, match="SPERRE_K2"):
        betrieb.probe_einzel(bot.t, bot.konf, warte=uhr.vor)
    assert not [r for r in sim.sendungen if r.action is Action.ENTRY_DEAL]


def test_kapital_und_stop_out_ueberleben_fehler_im_selben_takt(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    _einstieg(bot, uhr)
    bot.schutz()
    uhr.vor(5)
    sim.kapital(D("10000"))
    sim.stop_out(sim.positions()[0].ticket)
    echt = sim.account
    aufrufe = {"n": 0}

    def zweiter_aufruf_kaputt():
        aufrufe["n"] += 1
        if aufrufe["n"] == 3:                                      # nach dem Abgleich (1: Demo-Wache, 2: Abgleich): None
            from kit.broker.seam import BrokerFehler
            raise BrokerFehler("account_info None")
        return echt()
    sim.account = zweiter_aufruf_kaputt
    uhr.vor(5)
    with pytest.raises(Exception):                                 # noqa: B017
        bot.schutz()
    sim.account = echt
    assert "STOP_OUT" in bot.sperren and bot.loss_anker == D(20000)
    nach = _neu(bot)
    nach.starten()                                                  # Neustart: Anker und Sperre aus dem Journal
    assert "STOP_OUT" in nach.sperren and nach.loss_anker == D(20000)


def test_tagesanker_zaehlt_einzahlung_am_tageswechsel_nicht_doppelt(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    uhr.t = 1791410397.0                                            # Mi 23:59:57 Serverzeit = UTC (SIM ohne Versatz)
    ticken(sim)
    sim.kapital(D("1000"))
    uhr.vor(10)                                                     # erster Takt des neuen Servertags sieht die Einzahlung
    ticken(sim)
    bot.schutz()
    assert bot.tag_anker == sim.account().equity == D(11000)
    assert bot.einstieg_gesperrt(uhr()) is None


def test_journal_ausloeser_ohne_sperrsatz_wird_nachgeholt(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    bot.journal.schreiben("DEAL", "STOP_OUT", "x", deal=1, position_id=1, symbol="EURUSD", entry="OUT", reason="SO", magic=0,
                          deal_art="HANDEL", geld="-5", preis="1", volumen="0.1", zeit=int(uhr()))
    bot.journal.schreiben("VORFALL", "DOPPEL_FILL", "x")
    nach = _neu(bot)
    nach.starten()
    assert {"STOP_OUT", "NULLTOLERANZ"} <= set(nach.sperren)


def test_kein_zweiter_abbau_fuer_dasselbe_ticket(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    _einstieg(bot, uhr)
    p = sim.positions()[0]
    echt = sim.send
    sim.send = lambda req: (sim.sendungen.append(req), None)[1]     # Ausgang unbekannt
    erste = bot.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.STRATEGIE, "PROBE_ZU")
    assert erste.status is OpStatus.UNBEKANNT
    sim.send = echt
    vorher = len(sim.sendungen)
    assert bot.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.STRATEGIE, "K3") is None
    a = Absicht("X", Action.REDUCE_DEAL, p.symbol, p.side.opposite, p.volume, Namensraum.STRATEGIE, ticket=p.ticket)
    assert bot.lz.ausfuehren(a, "x1").grund == "TICKET_OFFENER_ABBAU" and len(sim.sendungen) == vorher


def test_kein_sturm_nach_endgueltiger_ablehnung(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    _einstieg(bot, uhr)
    bot.schutz()
    p = sim.positions()[0]
    sim.send = lambda req: (sim.sendungen.append(req), SendResult(10018))[1]        # Markt geschlossen
    stop_setzen(bot.ablage, 3)
    vorher = len(sim.sendungen)
    for _ in range(60):
        uhr.vor(1)
        ticken(sim)
        bot.schritt()
    assert 1 <= len(sim.sendungen) - vorher <= 3 and sim.positions() == [p]           # 30 s, dann 60 s Pause – kein Sturm


def test_kein_zweiter_strategie_einstieg_waehrend_erster_offen(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    cid_magic = ids.magic(Namensraum.STRATEGIE, ids.client_id("ATTRAPPE", "EURUSD", int(uhr()) // 60 * 60 - 60, "ENTRY"))
    sim.setze_fehler(cid_magic, Fehler("TIMEOUT_EXECUTED"))
    assert _einstieg(bot, uhr).status is OpStatus.UNBEKANNT
    sig = Signal("GBPUSD", Side.BUY, D("1.33400"), D("1.34400"), int(uhr()) // 60 * 60 - 60)
    assert bot.einstieg_strategie(sig, _kerzen(uhr)) is None
    assert _arten(bot, "SIGNAL")[-1]["daten"]["grund"] == "OFFENE_OPERATION"


def test_netting_konto_wird_verweigert(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    sim.modus = KontoModus.NETTING
    with pytest.raises(Ende, match="HEDGING"):
        bot.starten()
    assert sim.sendungen == []


def test_k3_zeit_laeuft_ab_sperre_auch_ueber_neustart(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    _einstieg(bot, uhr)
    echt = sim.send
    sim.send = lambda req: (sim.sendungen.append(req), SendResult(10018))[1]
    bot._sperren("K3", "Test")
    t_sperre = uhr()
    uhr.vor(600)                                                    # Prozess stand 10 min (oder Markt zu)
    sim.send = echt
    ticken(sim)
    nach = _neu(bot)
    nach.starten()
    for _ in range(5):
        nach.schritt()
        uhr.vor(1)
    flach = _arten(nach, "KILL_FLACH")[-1]["daten"]
    assert flach["dauer_s"] >= 600 and not sim.positions() and t_sperre < uhr()


def test_kill_dauer_nicht_aus_alter_dateizeit(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    bot.schritt()
    stop_setzen(bot.ablage, 1)
    os.utime(bot.ablage / "STOP", (time.time() - 3600, time.time() - 3600))   # kopierte Datei mit alter Änderungszeit
    bot.schritt()
    assert _arten(bot, "KILL")[-1]["daten"]["dauer_s"] <= 5


def test_drill_geht_den_echten_weg_und_raeumt_auf(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, probe=True)
    bot.starten()
    dauer = bot.drill(1, schlaf=uhr.vor)
    assert 1 <= dauer <= 5 and not (bot.ablage / "STOP").exists() and not bot.k1 and not bot.sperren
    stop_setzen(bot.ablage, 1)
    with pytest.raises(RuntimeError):
        bot.drill(2, schlaf=uhr.vor)                               # nie über eine echte STOP-Datei hinweg


def test_entsperrter_vorfall_sperrt_nach_wiederherstellung_nicht_erneut(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    bot.lz.vorfall("NEGPROOF_FALSIFIED", "alt")
    bot.journal.schreiben("BOT_ENTSPERRT", "NULLTOLERANZ", "Betreiber")
    bot.lz.wiederherstellen()
    bot._vorfaelle_gesehen = len(bot.lz.vorfaelle)
    nach = _neu(bot)
    nach.starten()
    assert "NULLTOLERANZ" not in nach.sperren


def test_technik_pause_ueberlebt_neustart(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    bot.journal.schreiben("TECHNIK_PAUSE", "AUFFAELLIG", "x", fehler=3, fenster=3)
    nach = _neu(bot)
    nach.starten()
    assert nach.einstieg_gesperrt(uhr()) == "TECHNIK_PAUSE"


# ------------------------------------------------------------------------------------------ Risiko und Tore
def test_doppelte_ausfuehrung_wird_erkannt(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    cid = ids.client_id("ATTRAPPE", "EURUSD", int(uhr()) // 60 * 60 - 60, "ENTRY")
    sim.setze_fehler(ids.magic(Namensraum.STRATEGIE, cid), Fehler("DOPPELT_AUSGEFUEHRT", einmal=True))
    _einstieg(bot, uhr)
    uhr.vor(5)
    bot.schritt()
    assert len(sim.positions()) == 2 and "NULLTOLERANZ" in bot.sperren
    stand = auswerten(bot.journal.lesen(), tore()["tor_t"], mechanik=bot.mechanik, jetzt=uhr())
    assert "DOPPEL_FILL" in [d["art"] for d in stand["defekte"]]


def test_strategie_hash_enthaelt_zeitbarriere():
    assert strategie_hash(Attrappe()) != strategie_hash(Attrappe(max_halte_s=3600))


def test_pruefpunkt_nach_fehler_wird_nachgeholt(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    uhr.t = 1791401400.0                                            # 21:30 Berlin
    ticken(sim)
    echt = bot.bewertet

    def kaputt(w):
        raise ConnectionError("kurz weg")
    bot.bewertet = kaputt
    with pytest.raises(ConnectionError):
        bot.schritt()
    bot.bewertet = echt
    uhr.vor(1)
    bot.schritt()
    assert [s for s in _arten(bot, "PRUEFPUNKT") if s["code"] == "TAEGLICH"]


def test_umrechnung_waehlt_symbol_vorher_aus(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    gewaehlt = []
    echt = sim.symbol
    sim.symbol = lambda n: (gewaehlt.append(n), echt(n))[1]
    assert bot.umrechnung("EUR", "JPY") is not None and "EURJPY" in gewaehlt


def test_kontowechsel_waehrend_sendung_ist_vorfall(tmp_path):
    sim, uhr, bot, _ = _start(tmp_path)
    echt = sim.send

    def senden_und_wechseln(req):
        res = echt(req)
        sim.handelsmodus = HandelsModus.REAL
        return res
    sim.send = senden_und_wechseln
    _einstieg(bot, uhr)
    assert "NICHT_DEMO_SENDUNG" in [v["art"] for v in bot.lz.vorfaelle]


def test_unbekannt_dauer_ab_sendung(tmp_path):
    j = Journal(tmp_path / "j", fsync=False)
    h = "h" * 64
    j.schreiben("START", "probe", "s", modus="probe", mechanik_hash=h, strategie_hash="", version="x", sperren=[])
    basis = {"op_id": "o1", "absicht_id": "A", "action": "ENTRY_DEAL", "symbol": "EURUSD", "side": "BUY", "volume": "0.01", "sl": "1",
             "tp": "2", "ticket": None, "namensraum": "PROBE", "grund_absicht": "", "magic": 1, "versuche": 1, "retcodes": [],
             "t_geplant": 1000.0, "gefuellt": "0", "deals": [], "order": 0, "grund": "", "negativnachweis": False}
    j.schreiben("OP_GEPLANT", "GEPLANT", "x", **{**basis, "status": "GEPLANT", "t_gesendet": 0.0})
    j.schreiben("OP_GEKLAERT", "UNBEKANNT", "x", **{**basis, "status": "UNBEKANNT", "t_gesendet": 1000.0})
    j.schreiben("OP_GEKLAERT", "ABGELEHNT", "x", **{**basis, "status": "ABGELEHNT", "t_gesendet": 1000.0})
    saetze = j.lesen()
    stand = auswerten(saetze, tore()["tor_t"], mechanik=h, jetzt=saetze[-1]["t"])
    assert "UNBEKANNT_ZU_LANG" in [d["art"] for d in stand["defekte"]]   # Sendung lag lange vor dem ersten UNBEKANNT-Satz


def test_sim_netting_bucht_swap_beim_schliessen():
    from kit.broker.sim import SimTerminal
    from kit_tests.hilfen import eurusd
    sim = SimTerminal([eurusd()], modus=KontoModus.NETTING)
    sim.setze_kurs("EURUSD", "1.10500", "1.10502")
    from kit.domain.types import OrderRequest
    sim.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("1"), magic=1, sl=D("1.09"), tp=D("1.12")))
    sim.rollover({"EURUSD": (D("-7"), D("2"))})
    sim.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.SELL, D("1"), magic=1))
    assert sim.deals(0, 2**40)[-1].swap == D("-7") and not sim._swap.get(sim.deals(0, 2**40)[0].position_id)


def test_redigieren_maskiert_zahlen_und_behaelt_hashes():
    from kit.report.redact import redigieren
    r = redigieren({"text": "Konto 1234567ABC", "nummer": 51234567, "mechanik_hash": "a80e29d94cb8d2a8", "saldo": 5,
                    "schritte": 604800})
    assert r == {"text": "Konto ######ABC", "nummer": "######", "mechanik_hash": "a80e29d94cb8d2a8", "schritte": 604800}


def test_abgleich_findet_deals_trotz_versatzsprung(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True)
    bot.starten()
    bot.probe = None
    term = bot.t
    a = Absicht("P1", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.01"), Namensraum.PROBE, D("1.15800"), D("1.16700"))
    op = bot.lz.ausfuehren(a, "p1")
    for _ in range(3):
        uhr.vor(5)
        bot.schutz()
    term.versatz_s += 3600                                           # Broker stellt die Serverzeit um (Messung noch alt)
    p = sim.positions()[0]
    bot.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.PROBE, "PROBE_ZU")
    for _ in range(3):
        uhr.vor(5)
        bot.schutz()
    assert op.status is OpStatus.ERLEDIGT and "NULLTOLERANZ" not in bot.sperren
    assert not _arten(bot, "ABGLEICH")[-1]["daten"]["differenzen"]
