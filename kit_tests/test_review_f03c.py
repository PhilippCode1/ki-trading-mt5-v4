"""Regressionen zum adversarialen Review der Vorflug-Korrekturen F-03c (3 Prüflinsen, je Befund ein Gegenprüfer)."""
from __future__ import annotations

from decimal import Decimal

from kit import betrieb, cli, paths
from kit.broker.mt5_real import Mt5Terminal
from kit.broker.sim import Fehler, SimTerminal, Uhr
from kit.broker.sim_modul import SimMt5Modul
from kit.config import Konfiguration
from kit.domain.types import Absicht, AccountSnapshot, Action, Bar, HandelsModus, KontoModus, Namensraum, OpStatus, Quote, Side
from kit.gates import tore
from kit.gates.tor_t import auswerten
from kit.orders import ids
from kit.orders.reconcile import Abgleich
from kit.probe.skripte import Skripte
from kit.risk import guards
from kit.run.loop import Bot
from kit.state import sperren as sp
from kit.state.store import Schreibsperre
from kit_tests.hilfen import aufbau, bot_aufbau, eurusd

D = Decimal


# ------------------------------------------------------------------------------------------ KRITISCH
def test_skripte_mehrfach_und_nach_neustart_ohne_fail(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True)
    with Schreibsperre(bot.ablage):
        bot.starten()
        sk = Skripte(bot, "EURUSD", warte=uhr.vor)
        laeufe = [sk.alle(), sk.alle(), Skripte(bot, "EURUSD", warte=uhr.vor).alle()]   # gleiche Instanz, neue Instanz
        neu = Bot(bot.t, bot.ablage, bot.konf, modus=bot.modus, melder=bot.melder, journal_fsync=False)
        neu.starten()
        laeufe.append(Skripte(neu, "EURUSD", warte=uhr.vor).alle())                     # neuer Prozess, gleiche Ablage
    for lauf in laeufe:
        assert not [e.skript for e in lauf if e.urteil == "FAIL"], [(e.skript, e.schritte) for e in lauf if e.urteil == "FAIL"]
    stand = auswerten(neu.journal.lesen(), tore()["tor_t"], mechanik=neu.mechanik, jetzt=uhr())
    assert stand["defekte"] == []


def test_installierte_kopie_besteht_pruefen(tmp_path, monkeypatch):
    app = paths.kit_home() / "app" / "lauf_F-99"
    app.mkdir(parents=True)
    (app / "INSTALLATION.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", app)
    ergebnisse = cli.pruefen(ports=set(), globales_mt5=False, frei_gb=100)
    assert not [t for s, t in ergebnisse if s == "FEHLER"] and any("Installierte Kopie" in t for _, t in ergebnisse)
    monkeypatch.setattr(cli, "ROOT", tmp_path / "irgendwo")                 # kein Repo, keine Installation: weiter FEHLER
    assert any(s == "FEHLER" for s, _ in cli.pruefen(ports=set(), globales_mt5=False, frei_gb=100))


# ------------------------------------------------------------------------------------------ HOCH
def test_entsperren_alle_setzt_anker_und_zaehlfenster_nicht_zurueck(tmp_path, monkeypatch):
    from kit import bedienung
    from kit.state import pin
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    b = Bot(bot.t, paths.ablage("probe"), bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    b.starten()
    anker = b.loss_anker
    b._sperren("NULLTOLERANZ", "Test")
    b.lz.sperren("GBPUSD", "MANUELLER_EINGRIFF")
    werte = ["richtig-0001"] * 3
    monkeypatch.setattr(bedienung, "_pin_eingabe", lambda text: werte.pop(0))
    monkeypatch.setattr(pin.time, "sleep", lambda s: None)
    bedienung.pin_setzen()
    bedienung.entsperren("probe", "ALLE")
    saetze = b.journal.lesen()
    assert sp.letzte_entsperrung(saetze, "LOSS_LOCK") == 0 and sp.letzte_entsperrung(saetze, "STOP50") == 0
    sim.kapital(D("-100"), __import__("kit.domain.types", fromlist=["DealArt"]).DealArt.GEBUEHR)
    neu = Bot(bot.t, paths.ablage("probe"), bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    neu.starten()
    assert neu.loss_anker == anker and not neu.sperren and neu.lz.gesperrt("GBPUSD") is None


# ------------------------------------------------------------------------------------------ MITTEL
def _client_lz(tmp_path, spaet_nach_s: float):
    term, lz, uhr, journal = aufbau(tmp_path)
    echt = term._deal

    def als_client(**kw):
        if kw.get("grund") == "EXPERT":
            kw["grund"] = "CLIENT"
        return echt(**kw)
    term._deal = als_client
    a = Absicht("A", Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.10"), Namensraum.PROBE, D("1.10000"), D("1.11000"))
    term.setze_fehler(ids.magic(Namensraum.PROBE, "a1"), Fehler("TIMEOUT_EXECUTED"))
    op = lz.ausfuehren(a, "a1")
    uhr.vor(spaet_nach_s)
    if spaet_nach_s > 60:
        lz.klaeren()                                                       # Negativnachweis vor der Spätlieferung
    term.liefere_spaete()
    uhr.vor(1)
    b = Abgleich(lz, journal).laufen()
    return lz, op, b


def test_spaeter_fill_mit_handgrund_vor_negativnachweis(tmp_path):
    lz, op, b = _client_lz(tmp_path, 10)
    assert op.status is OpStatus.ERLEDIGT and op.gefuellt == D("0.10") and "EURUSD" not in lz.symbol_sperren


def test_spaeter_fill_mit_handgrund_nach_negativnachweis_wird_gemeldet(tmp_path):
    lz, op, b = _client_lz(tmp_path, 61)
    assert "NEGPROOF_FALSIFIED" in [v["art"] for v in lz.vorfaelle] and lz.symbol_sperren.get("EURUSD")


def _mt5(pc_vor_s=0.0, mono=None):
    uhr = Uhr()
    sim = SimTerminal([eurusd(), eurusd("EURJPY.a")], uhr=uhr)
    sim.setze_kurs("EURUSD", "1.10500", "1.10502")
    pc = Uhr(uhr() + pc_vor_s)
    term = Mt5Terminal(SimMt5Modul(sim, versatz_s=10800), versatz_s=None, uhr=pc, mono=mono, prozess_pruefen=lambda: True,
                       schluessel_ordner=paths.kit_home() / "geheim")
    term.verbinden()
    return sim, uhr, pc, term


def test_kerzen_abschluss_nach_angeglichener_uhr():
    sim, uhr, pc, term = _mt5(pc_vor_s=120.0)                       # PC-Uhr geht 2 min vor

    def schlaf(s):
        uhr.vor(s)
        pc.vor(s)
    term.messe_versatz("EURUSD", schlaf=schlaf)
    beginn = int(uhr()) // 60 * 60
    sim.kerze(Bar("EURUSD", beginn - 60, D("1.1"), D("1.11"), D("1.09"), D("1.105")))
    sim.kerze(Bar("EURUSD", beginn, D("1.1"), D("1.11"), D("1.09"), D("1.105")))
    k = term.bars("EURUSD", "M1", beginn - 120, beginn + 120)
    assert [b.is_closed for b in k] == [True, False]                  # laufende Kerze bleibt offen


def test_stellen_der_pc_uhr_veraendert_zeit_nicht():
    mono = Uhr(500.0)
    sim, uhr, pc, term = _mt5(mono=mono)

    def schlaf(s):
        uhr.vor(s)
        pc.vor(s)
        mono.vor(s)
    term.messe_versatz("EURUSD", schlaf=schlaf)
    vorher = term.zeit()
    pc.vor(-300)                                                       # Zeitsynchronisation stellt die PC-Uhr zurück
    assert term.zeit() == vorher
    schlaf(10)
    assert abs(term.zeit() - uhr()) < 0.2


def test_kurszeit_in_der_zukunft_ist_unstimmig():
    konf = Konfiguration("", ("EURUSD",), ("EURUSD",))
    t = 1791367200.0
    konto = AccountSnapshot(HandelsModus.DEMO, KontoModus.HEDGING, "EUR", D(1), D(1), D(0), D(1), D(0), 30, True)
    q = Quote("EURUSD", D("1.163"), D("1.16312"), int((t + 5) * 1000))
    assert guards.einstieg(t, konto, eurusd(), q, [], konf, D(300)) == "KURS_ZEIT_UNSTIMMIG"


def test_umrechnung_findet_kreuzpaar_mit_suffix(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path)
    from kit.domain.types import SymbolSpec
    spec = sim.specs["EURJPY"]
    sim.specs["EURJPY.a"] = SymbolSpec(**{**spec.__dict__, "name": "EURJPY.a"})
    del sim.specs["EURJPY"]
    sim.setze_kurs("EURJPY.a", "172.100", "172.120")
    del sim._kurse["EURJPY"]
    bot.konf = Konfiguration("", ("EURUSD",), ("EURUSD",), symbol_namen={"EURUSD": "EURUSD.a"})
    assert bot.umrechnung("EUR", "JPY") is not None


def test_erster_tick_erst_nach_abonnement():
    sim, uhr, pc, term = _mt5()
    modul = term._mt5
    echt = modul.symbol_info_tick
    aufrufe = {"n": 0}

    def verzoegert(name):
        aufrufe["n"] += 1
        return None if aufrufe["n"] == 1 else echt(name)
    modul.symbol_info_tick = verzoegert

    def schlaf(s):
        uhr.vor(s)
        pc.vor(s)
    assert term.messe_versatz("EURUSD", schlaf=schlaf) == 10800


# ------------------------------------------------------------------------------------------ NIEDRIG
def test_alle_sperrgruende_sichtbar(tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path)
    lz.sperren("EURUSD", "MANUELLER_EINGRIFF")
    lz.sperren("EURUSD", "FREMDPOSITION")
    lz.sperren("EURUSD", "FREMDPOSITION")                              # derselbe Grund wird nicht erneut journalisiert
    assert sp.symbol_sperren(journal.lesen(), uhr()) == {"EURUSD": "MANUELLER_EINGRIFF + FREMDPOSITION"}
    assert lz.gesperrt("EURUSD") == "MANUELLER_EINGRIFF"
    assert sum(1 for s in journal.lesen() if s["art"] == "SPERRE") == 2


def test_rauchtest_nennt_ursachen_getrennt(tmp_path):
    uhr = Uhr()
    sim = SimTerminal([eurusd(), eurusd("GBPUSD")], uhr=uhr)
    for s in ("EURUSD", "GBPUSD"):
        sim.setze_kurs(s, "1.10500", "1.10502")
    modul = SimMt5Modul(sim, versatz_s=10800, tradeapi_disabled=True)
    term = Mt5Terminal(modul, versatz_s=10800, schluessel_ordner=paths.kit_home() / "geheim", uhr=uhr, prozess_pruefen=lambda: True)
    erg = betrieb.rauchtest(term, Konfiguration("", ("EURUSD", "GBPUSD"), ("EURUSD",)), versatz_messen=False)
    text = " ".join(erg["befunde"])
    assert "Python-API" in text and "Knopf" not in text and erg["terminal"]["tradeapi_disabled"] is True
