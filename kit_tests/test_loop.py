"""Takt: Start/Neustart, Kill-Stufen, Sperren (überleben Neustart und gelöschten Zustand), Grenzen, Demo-Vorrang, Band-Prüfpunkte,
Abbau nie gesperrt, Technik-Wächter, Drills."""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit.broker.seam import BrokerFehler
from kit.domain.types import Absicht, Action, Bar, DealArt, HandelsModus, Namensraum, OpStatus, SendResult, Side
from kit.orders import ids
from kit.run.loop import Bot, Ende
from kit.state.store import ZustandFehler, stop_setzen
from kit.strategy.attrappe import Attrappe
from kit.strategy.base import Signal
from kit_tests.hilfen import bot_aufbau, ticken

D = Decimal


def _neu(bot: Bot) -> Bot:
    return Bot(bot.t, bot.ablage, bot.konf, modus=bot.modus, strategie=bot.strategie, probe=bot.probe is not None, melder=bot.melder,
               journal_fsync=False)


def _kerzen(uhr) -> list[Bar]:
    t = int(uhr()) // 60 * 60
    return [Bar("EURUSD", t - 60 * (3 - i), D("1.163"), D("1.1635"), D("1.1625"), D("1.163"), 12) for i in range(3)]


def _einstieg(bot, uhr, side=Side.BUY):
    sl, tp = (D("1.15800"), D("1.16700")) if side is Side.BUY else (D("1.16800"), D("1.15900"))
    return bot.einstieg_strategie(Signal("EURUSD", side, sl, tp, int(uhr()) // 60 * 60 - 60), _kerzen(uhr))


def _arten(bot, art):
    return [s for s in bot.journal.lesen() if s["art"] == art]


@pytest.fixture
def strat_bot(tmp_path):
    sim, uhr, bot, melder = bot_aufbau(tmp_path, strategie=Attrappe(symbole=("EURUSD",)))
    bot.starten()
    return sim, uhr, bot, melder


def test_start_anker_und_zustand_fehlt_trotz_journal(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    bot.starten()
    codes = {(s["art"], s["code"]) for s in bot.journal.lesen()}
    assert {("START", "sim"), ("ANKER", "LOSS_LOCK"), ("ANKER", "TAG")} <= codes
    (bot.ablage / "zustand.json").unlink()
    with pytest.raises(ZustandFehler):
        _neu(bot).starten()


def test_einstieg_im_band_und_hoechstens_eine_strategieposition(strat_bot):
    sim, uhr, bot, _ = strat_bot
    op = _einstieg(bot, uhr)
    assert op.status is OpStatus.ERLEDIGT
    p = sim.positions()[0]
    hebel = p.volume * 100000 / sim.account().equity
    assert D("5.25") <= hebel <= D("14.25") and p.sl > 0 and p.tp > 0
    uhr.vor(120)
    ticken(sim)
    assert _einstieg(bot, uhr, Side.SELL) is None
    assert _arten(bot, "SIGNAL")[-1]["daten"]["grund"] == "MAX_STRATEGIEPOSITIONEN"
    pruef = [s for s in _arten(bot, "PRUEFPUNKT")]
    bot.schritt()
    assert any(s["code"] == "FILL" for s in _arten(bot, "PRUEFPUNKT")) or pruef


def test_signal_ungueltig_und_stop_zu_ziel(strat_bot):
    sim, uhr, bot, _ = strat_bot
    t = int(uhr()) // 60 * 60 - 60
    assert bot.einstieg_strategie(Signal("EURUSD", Side.BUY, D("1.17"), D("1.18"), t), _kerzen(uhr)) is None
    assert _arten(bot, "SIGNAL")[-1]["daten"]["grund"] == "SL_TP_UNGUELTIG"
    assert bot.einstieg_strategie(Signal("EURUSD", Side.BUY, D("1.150"), D("1.1650"), t), _kerzen(uhr)) is None
    assert _arten(bot, "SIGNAL")[-1]["daten"]["grund"] == "STOP_ZU_ZIEL"
    assert sim.sendungen == []


def test_k1_datei_sperrt_einstiege_und_ist_aufhebbar(strat_bot):
    sim, uhr, bot, _ = strat_bot
    stop_setzen(bot.ablage, 1)
    bot.schritt()
    assert bot.einstieg_gesperrt(uhr()) == "K1"
    kill = _arten(bot, "KILL")[-1]["daten"]
    assert kill["stufe"] == 1 and kill["dauer_s"] <= 5
    assert _einstieg(bot, uhr) is None and sim.sendungen == []
    stop_setzen(bot.ablage, 0)
    uhr.vor(1)
    bot.schritt()
    assert bot.einstieg_gesperrt(uhr()) is None


def test_k3_datei_flach_in_60s_und_sperre_ueberlebt_neustart(strat_bot):
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    bot.probe = None
    assert sim.positions()
    stop_setzen(bot.ablage, 3)
    for _ in range(60):
        bot.schritt()
        if not sim.positions():
            break
        uhr.vor(1)
    assert not sim.positions()
    flach = _arten(bot, "KILL_FLACH")[-1]["daten"]
    assert flach["dauer_s"] <= 60 and not flach["drill"]
    nach = _neu(bot)
    nach.starten()
    assert nach.einstieg_gesperrt(uhr()) == "SPERRE_K3"
    stop_setzen(bot.ablage, 0)                                    # Datei löschen hebt K3 nicht auf
    nach2 = _neu(nach)
    nach2.starten()
    assert "K3" in nach2.sperren


def test_loss_lock_schliesst_alles_und_sperrt(strat_bot):
    sim, uhr, bot, melder = strat_bot
    _einstieg(bot, uhr)
    sim.kapital(D("-2600"), DealArt.GEBUEHR)                     # Kosten, keine Kapitalbewegung: Anker bleibt
    uhr.vor(5)
    for _ in range(10):
        bot.schritt()
        uhr.vor(1)
    assert "LOSS_LOCK" in bot.sperren and not sim.positions()
    assert any("LOSS_LOCK" in t for _, t in melder.meldungen)


def test_kapitalbewegung_verschiebt_anker_statt_sperre(strat_bot):
    sim, uhr, bot, _ = strat_bot
    uhr.vor(5)
    sim.kapital(D("-4000"))
    uhr.vor(5)
    bot.schritt()
    assert not bot.sperren and bot.loss_anker == D(6000) and bot.einstieg_gesperrt(uhr()) is None


def test_tagesstopp_bis_zum_naechsten_servertag(strat_bot):
    sim, uhr, bot, _ = strat_bot
    sim.kapital(D("-300"), DealArt.GEBUEHR)
    uhr.vor(5)
    bot.schritt()
    assert bot.einstieg_gesperrt(uhr()) == "TAGESSTOPP"
    uhr.vor(86400)
    bot.schritt()
    assert bot.einstieg_gesperrt(uhr()) is None and not bot.sperren


def test_stop50_sperrt_und_schliesst(strat_bot):
    sim, uhr, bot, _ = strat_bot
    m = ids.magic(Namensraum.STRATEGIE, "x")
    for i in range(20):
        for entry, geld in (("IN", "-1"), ("OUT", "-5" if i % 2 else "4")):
            bot.buch.deal({"art": "DEAL", "seq": 10_000 + 2 * i + (entry == "OUT"),
                           "daten": {"position_id": 900 + i, "entry": entry, "geld": geld, "magic": m, "volumen": "0.5", "symbol": "EURUSD",
                                     "zeit": int(uhr()) + i, "reason": "TP", "deal_art": "HANDEL"}})
    bot._grenzen(sim.account())
    assert "STOP50" in bot.sperren and bot.einstieg_gesperrt(uhr()) == "SPERRE_STOP50"


def test_abbau_und_schutz_nie_durch_sperren_blockiert(strat_bot):
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    p = sim.positions()[0]
    stop_setzen(bot.ablage, 1)
    bot.schritt()
    bot._sperren("K2", "Test")
    bot.tagesstopp_tag = bot.tag
    bot.technik_pause_bis = uhr() + 999
    a = Absicht("SCHUTZ-T", Action.PROTECT_SLTP, p.symbol, p.side, p.volume, Namensraum.STRATEGIE, p.sl + D("0.001"), p.tp, p.ticket)
    assert bot.lz.ausfuehren(a, "s1").status is OpStatus.ERLEDIGT
    assert bot.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.STRATEGIE, "TEST").status is OpStatus.ERLEDIGT
    assert not sim.positions()


def test_demo_vorrang_beim_start_und_im_lauf(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path / "a", handelsmodus=HandelsModus.REAL)
    with pytest.raises(Ende):
        bot.starten()
    assert sim.sendungen == [] and "NICHT_DEMO" in {s["code"] for s in bot.journal.lesen() if s["art"] == "BOT_SPERRE"}
    sim2, uhr2, bot2, _ = bot_aufbau(tmp_path / "b", strategie=Attrappe(symbole=("EURUSD",)))
    bot2.starten()
    _einstieg(bot2, uhr2)
    gesendet = len(sim2.sendungen)
    sim2.handelsmodus = HandelsModus.REAL
    stop_setzen(bot2.ablage, 3)                                   # selbst K3 sendet auf REAL nichts
    assert bot2.laufen(schlaf=uhr2.vor) == 2
    assert len(sim2.sendungen) == gesendet and sim2.positions()


def test_band_boden_am_pruefpunkt_stellt_glatt(strat_bot):
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    bot.schutz()                                                  # Prüfpunkt nach Fill: im Band, nichts zu tun
    assert sim.positions()
    sim.kapital(D("10000"))                                       # Equity verdoppelt → Hebel ≈ 2,7 < 5
    ops = bot.pruefpunkt("TAEGLICH")
    assert ops and ops[0].absicht.grund == "BAND_BODEN" and not sim.positions()


def test_band_deckel_baut_ab(strat_bot):
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    vorher = sim.positions()[0].volume
    sim.kapital(D("-6500"), DealArt.GEBUEHR)
    ops = bot.pruefpunkt("TAEGLICH")
    rest = sim.positions()[0].volume
    assert ops and ops[0].absicht.grund == "BAND_DECKEL" and rest < vorher
    assert rest * 100000 / sim.account().equity <= D("14.25")


def test_technik_pause_nach_drei_ablehnungen(tmp_path):
    sim, uhr, bot, melder = bot_aufbau(tmp_path, probe=True)
    bot.starten()
    sim.send = lambda req: (sim.sendungen.append(req), SendResult(10019))[1]   # nicht genug Geld: endgültig abgelehnt
    for name in ("EURUSD", "GBPUSD", "USDJPY"):
        bot.probe.eroeffnen(name, uhr())
    bot.schutz()
    assert bot.einstieg_gesperrt(uhr()) == "TECHNIK_PAUSE" and any("Technik" in t for _, t in melder.meldungen)


def test_drills_ohne_dauerhafte_sperre(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, probe=True)
    bot.starten()
    bot.probe.eroeffnen("EURUSD", uhr())
    assert sim.positions()
    assert bot.drill(1, schlaf=uhr.vor) <= 5 and bot.drill(2, schlaf=uhr.vor) <= 5
    assert bot.drill(3, schlaf=uhr.vor) <= 60 and not sim.positions()
    assert not bot.sperren and bot.einstieg_gesperrt(uhr()) is None
    assert _arten(bot, "KILL_FLACH")[-1]["daten"]["drill"] is True


def test_beenden_datei_und_verbindungsfehler(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    bot.starten()
    (bot.ablage / "BEENDEN").write_text("x", encoding="utf-8")
    assert bot.laufen(schlaf=uhr.vor) == 0 and not (bot.ablage / "BEENDEN").exists()
    assert _arten(bot, "ENDE")[-1]["code"] == "BEENDEN"

    def kaputt():
        raise BrokerFehler("weg")
    sim.positions = kaputt
    assert bot.laufen(schlaf=uhr.vor, max_verbindungsfehler=3) == 3
    assert len([s for s in _arten(bot, "VORFALL") if s["code"] == "VERBINDUNG"]) == 3


def test_laufzeit_bis_und_probe_zyklen(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, probe=True, attrappe=True)
    bot.starten()
    assert bot.laufen(bis=uhr() + 25 * 60, schlaf=uhr.vor) == 0
    ops = [o for o in bot.lz.ops.values() if o.absicht.namensraum is Namensraum.PROBE]
    arten = {o.absicht.action for o in ops if o.status is OpStatus.ERLEDIGT}
    assert arten == {Action.ENTRY_DEAL, Action.PROTECT_SLTP, Action.REDUCE_DEAL}
    je_symbol = {}
    for o in ops:
        if o.absicht.action is Action.ENTRY_DEAL:
            je_symbol.setdefault(o.absicht.symbol, []).append(o.t_geplant)
    for zeiten in je_symbol.values():
        assert all(b - a >= 600 for a, b in zip(zeiten, zeiten[1:], strict=False))          # ≤ 1 Zyklus je 10 min und Symbol


def test_zeitbarriere_schliesst_per_ticket_auch_unter_sperre(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, strategie=Attrappe(symbole=("EURUSD",), max_halte_s=3600))
    bot.starten()
    _einstieg(bot, uhr)
    bot._sperren("K2", "Test")
    uhr.vor(1800)
    ticken(sim)
    bot.handel(uhr())
    assert sim.positions()
    uhr.vor(1801)
    ticken(sim)
    bot.handel(uhr())
    assert not sim.positions()
    assert any(o.absicht.grund == "ZEITBARRIERE" and o.status is OpStatus.ERLEDIGT for o in bot.lz.ops.values())


def test_stop_out_setzt_k2(strat_bot):
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    bot.schutz()
    sim.stop_out(sim.positions()[0].ticket)
    uhr.vor(5)
    bot.schritt()
    assert "STOP_OUT" in bot.sperren and bot.einstieg_gesperrt(uhr()) == "SPERRE_STOP_OUT"
    assert any(s["daten"]["ausloeser"] == "STOP_OUT" for s in _arten(bot, "KILL"))


def test_position_ohne_sl_wird_geschuetzt_sonst_notschluss(strat_bot):
    from dataclasses import replace
    sim, uhr, bot, _ = strat_bot
    _einstieg(bot, uhr)
    bot.schutz()
    p = sim.positions()[0]
    sim._pos[p.ticket] = replace(p, sl=D(0))                          # Server meldet die Position ohne SL
    uhr.vor(5)
    bot.schritt()
    assert sim.positions()[0].sl == p.sl and not bot.sperren         # SL wiederhergestellt, kein Defekt
    sim._pos[p.ticket] = replace(sim.positions()[0], sl=D(0))
    sim.check = lambda req: __import__("kit.domain.types", fromlist=["CheckResult"]).CheckResult(10016)   # SL lässt sich nicht setzen
    for _ in range(8):
        uhr.vor(5)
        ticken(sim)
        bot.schritt()
    assert "NULLTOLERANZ" in bot.sperren
