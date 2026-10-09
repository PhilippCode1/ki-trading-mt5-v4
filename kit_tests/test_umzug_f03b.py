"""Review F-03b (Ablage-Umzug, kit/umzug.py): Startgate über das Umzugsbuch, Steuerdateien zählen nicht als Daten, Sperren-
übernahme statt Sackgasse (inkl. Nachhol-Auslöser, fail-closed bei unlesbarem Altjournal), Teilkopien nie unter dem Endnamen,
Abschließen ohne Quelle, ENDE nach Startfehlern und Strg+C, Versatzmessung mit Ausweichsymbolen nur bei stehendem Kursstrom."""
from __future__ import annotations

import json
import os

import pytest

from kit import bedienung, betrieb, cli, paths, umzug
from kit.broker.seam import BrokerFehler
from kit.config import Konfiguration
from kit.run.loop import Bot
from kit.state import sperren as sp
from kit.state.journal import Journal
from kit.state.journal import lesen as journal_lesen
from kit.state.store import Schreibsperre, stop_setzen, stop_stufe
from kit_tests.test_mt5_adapter import _konf, _paar


def _alte_marke(quelle, ziel):
    """Marke eines Umzugs vor dem Umzugsbuch; der Bestand wird 10 s zurückdatiert. Windows vergibt Zeitstempel nur im Takt
    (~16 ms), und der Vergleich im Code ist bewusst strikt (Gleichstand = nicht umgezogen)."""
    marke = quelle / "UMGEZOGEN.txt"
    marke.write_text(f"Umgezogen nach {ziel} am 2026-10-05 21:00 UTC. Nichts gelöscht.\n", encoding="utf-8")
    frueher = marke.stat().st_mtime - 10
    for datei in quelle.rglob("*"):
        if datei.is_file() and datei != marke:
            os.utime(datei, (frueher, frueher))


def _altbestand(ordner, *, sperre: bool = True):
    j = Journal(ordner / "probe" / "journal", fsync=False)
    j.schreiben("START", "probe", "Bot gestartet")
    j.schreiben("ANKER", "LOSS_LOCK", "Anker", wert="1000")
    if sperre:
        j.schreiben("BOT_SPERRE", "LOSS_LOCK", "Verlust 25 %", stufe=3)
        j.schreiben("SPERRE", "10014", "Einstiege in EURUSD gesperrt", symbol="EURUSD", grund="10014")
        stop_setzen(ordner / "probe", 2)
    for rel, inhalt in (("freigaben/pin.json", b"{}"), ("geheim/hmac.key", b"schluessel")):
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(inhalt)
    return ordner


def _arten(ordner):
    return [s["art"] for s in journal_lesen(ordner / "probe" / "journal")]


def test_altbestand_sperrt_start_terminal_und_pin(tmp_path, monkeypatch, capsys):
    alt = _altbestand(tmp_path / "alt")
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    assert umzug.offene_altbestaende() == [alt]
    with pytest.raises(paths.AblageFehler, match="kit umziehen"):
        umzug.pruefen()
    with pytest.raises(paths.AblageFehler):
        bedienung.starten("lauf/F-99", "probe", popen=None, warte=lambda s: None)
    with pytest.raises(paths.AblageFehler):
        bedienung.pin_setzen()                                         # PIN nie in die leere neue Ablage
    assert cli.main(["rauchtest"]) == 1 and "kit umziehen" in capsys.readouterr().out
    assert not (paths.kit_home() / "geheim").exists()                  # kein Terminalzugriff, kein neuer Schlüssel
    assert bedienung.status("probe")["umzug_offen"] == 1
    assert cli.main(["stop", "--k1"]) == 0                             # kit stop bleibt immer frei


def test_stop_im_ziel_macht_nichts_belegt_und_wird_zusammengefuehrt(tmp_path, monkeypatch):
    alt = _altbestand(tmp_path / "alt")                                # alt: STOP K2, Journal mit Anker
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    assert cli.main(["stop", "--beenden"]) == 0 and cli.main(["stop", "--k1"]) == 0   # Ziel: BEENDEN + STOP K1
    erg = umzug.umziehen()
    assert erg["nicht_kopiert"] == [] and erg["dateien"] == {"probe": 1, "freigaben": 1, "geheim": 1}
    heim = paths.kit_home()
    assert "ANKER" in _arten(heim) and stop_stufe(heim / "probe") == 2 and erg["sperren_uebernommen"] == {"probe": ["STOP-K2"]}
    assert umzug.offene_altbestaende() == []
    umzug.pruefen()


def test_ziel_mit_daten_uebernimmt_sperren_statt_sackgasse(tmp_path, monkeypatch):
    alt = _altbestand(tmp_path / "alt")
    j = Journal(alt / "probe" / "journal", fsync=False)
    j.schreiben("VORFALL", "DOPPEL_FILL", "Auslöser ohne Sperrsatz (Absturz dazwischen)")
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    heim = paths.kit_home()
    neu = Journal(heim / "probe" / "journal", fsync=False)
    neu.schreiben("START", "probe", "neu begonnen")                    # Ziel schon belegt …
    neu.schreiben("SPERRE", "10018", "Markt zu", symbol="EURUSD", grund="RETCODE_10018", bis=4e9)   # … mit laufender Zeitsperre
    (heim / "freigaben").mkdir(parents=True)
    (heim / "freigaben" / "pin.json").write_bytes(b'{"neu": 1}')
    erg = umzug.umziehen()
    assert erg["nicht_kopiert"] == ["freigaben", "probe"] and erg["dateien"] == {"geheim": 1}
    assert set(erg["sperren_uebernommen"]["probe"]) == {"LOSS_LOCK", "NULLTOLERANZ", "SYMBOL:EURUSD", "STOP-K2"}
    saetze = journal_lesen(heim / "probe" / "journal")
    assert {"LOSS_LOCK", "NULLTOLERANZ"} <= set(sp.aus_journal(saetze)) and stop_stufe(heim / "probe") == 2
    assert "EURUSD" in sp.symbol_sperren(saetze, 5e9)                  # bleibt nach Ablauf der Zeitsperre
    assert (heim / "freigaben" / "pin.json").read_bytes() == b'{"neu": 1}'          # nie überschrieben
    assert umzug.offene_altbestaende() == [] and json.loads((heim / "UMZUG.json").read_text(encoding="utf-8"))["status"] == "fertig"
    umzug.pruefen()
    with pytest.raises(umzug.UmzugFehler, match="nichts"):
        umzug.umziehen(alt)                                            # schon übernommen: keine Doppelübernahme
    Journal(alt / "probe" / "journal", fsync=False).schreiben("BOT_SPERRE", "K2", "später in der alten Ablage")
    assert umzug.offene_altbestaende() == [alt]                        # neue Altdaten öffnen das Tor wieder
    assert "K2" in umzug.umziehen()["sperren_uebernommen"]["probe"]


def test_unlesbares_altjournal_sperrt_fail_closed(tmp_path, monkeypatch):
    alt = _altbestand(tmp_path / "alt", sperre=False)
    datei = next((alt / "probe" / "journal").glob("*.jsonl"))
    datei.write_bytes(datei.read_bytes() + b'{"text": "Takt \xe2\x80')  # Absturz mitten im Schreiben
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    Journal(paths.kit_home() / "probe" / "journal", fsync=False).schreiben("START", "probe", "neu")
    erg = umzug.umziehen()
    assert erg["sperren_uebernommen"]["probe"] == ["NULLTOLERANZ", "STOP-K2"]
    assert stop_stufe(paths.kit_home() / "probe") == 2


def test_abbruch_mitten_in_der_datei_setzt_fort(tmp_path, monkeypatch):
    alt = _altbestand(tmp_path / "alt", sperre=False)
    (alt / "marktdaten").mkdir()
    (alt / "marktdaten" / "gross.bin").write_bytes(os.urandom(3 << 20))
    ziel = tmp_path / "neu"
    echt = umzug.shutil.copyfileobj

    def bricht_ab(src, dst, laenge=0):
        if not src.name.endswith("gross.bin"):
            return echt(src, dst, laenge)
        dst.write(src.read(1 << 20))
        raise OSError(28, "Datenträger voll")
    monkeypatch.setattr(umzug.shutil, "copyfileobj", bricht_ab)
    with pytest.raises(umzug.UmzugFehler, match="erneut ausführen"):
        umzug.umziehen(alt, ziel)
    assert json.loads((ziel / "UMZUG.json").read_text(encoding="utf-8"))["status"] == "laeuft"
    assert not (ziel / "marktdaten" / "gross.bin").exists()            # nie eine halbe Datei unter dem Endnamen
    assert (ziel / "marktdaten" / "gross.bin.umzug-teil").stat().st_size == 1 << 20
    monkeypatch.setenv("KIT_HOME", str(ziel))
    with pytest.raises(paths.AblageFehler, match="abgebrochen"):
        umzug.pruefen()
    monkeypatch.setattr(umzug.shutil, "copyfileobj", echt)
    erg = umzug.umziehen(alt, ziel)
    assert erg["dateien"]["marktdaten"] == 1 and (ziel / "marktdaten" / "gross.bin").read_bytes() == \
        (alt / "marktdaten" / "gross.bin").read_bytes()
    assert not list(ziel.rglob("*.umzug-teil"))
    umzug.pruefen()


def test_abschliessen_ohne_quelle_fail_closed(tmp_path):
    heim = paths.kit_home()
    Journal(heim / "probe" / "journal", fsync=False).schreiben("START", "probe", "teilweise kopiert")
    (heim / "UMZUG.json").write_text(json.dumps({"status": "laeuft", "von": str(tmp_path / "weg"), "belegt": []}), encoding="utf-8")
    with pytest.raises(paths.AblageFehler):
        umzug.pruefen()
    assert cli.main(["umziehen", "--abschliessen"]) == 0
    umzug.pruefen()
    for m in ("probe", "demo"):                                        # auch der noch nicht kopierte Modus
        assert "K2" in sp.aus_journal(journal_lesen(heim / m / "journal")) and stop_stufe(heim / m) == 2
    with pytest.raises(umzug.UmzugFehler):
        umzug.abschliessen()


def test_alte_marke_bleibt_gueltig_und_aufgehobene_sperren_kommen_nicht_zurueck(tmp_path, monkeypatch):
    heim = paths.kit_home()
    a = _altbestand(tmp_path / "a")                                    # mit dem Stand vor dem Buch umgezogen …
    for teil in ("probe", "freigaben", "geheim"):
        umzug.shutil.copytree(a / teil, heim / teil)
    _alte_marke(a, heim)
    Journal(heim / "probe" / "journal", fsync=False).schreiben("BOT_ENTSPERRT", "ALLE", "Betreiber (PIN)")   # … dann entsperrt
    b = tmp_path / "b"
    (b / "freigaben").mkdir(parents=True)
    (b / "freigaben" / "demo_konten.json").write_bytes(b"[]")
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", os.pathsep.join([str(a), str(b)]))
    assert umzug.offene_altbestaende() == [b]
    umzug.umziehen()
    assert umzug.offene_altbestaende() == []                           # Marke von A gilt auch mit gefülltem Buch
    Journal(a / "probe" / "journal", fsync=False).schreiben("BOT_SPERRE", "K2", "später in der alten Ablage")
    assert umzug.offene_altbestaende() == [a]
    erg = umzug.umziehen(a)
    assert erg["sperren_uebernommen"] == {"probe": ["K2"]}             # nur Neues; LOSS_LOCK, EURUSD, STOP bleiben aufgehoben
    assert umzug.offene_altbestaende() == []
    Journal(a / "probe" / "journal", fsync=False).schreiben("BOT_SPERRE", "STOP50", "noch später")
    assert umzug.umziehen(a)["sperren_uebernommen"] == {"probe": ["STOP50"]}   # Stand je Quelle: K2 nicht doppelt


def test_ende_ueber_frisches_journal_haelt_die_kette(tmp_path):
    ordner = tmp_path / "j"
    alt = Journal(ordner, fsync=False)
    alt.schreiben("START", "probe", "Bot gestartet")
    Journal(ordner, fsync=False).schreiben("VORFALL", "X", "stand schon auf der Platte, als Strg+C kam")
    betrieb._ende_falls_gestartet(alt, 0, "ABBRUCH", "Takt beendet")
    assert [s["art"] for s in journal_lesen(ordner)] == ["START", "VORFALL", "ENDE"]   # Kette intakt, kein Doppel-seq


def test_mehrere_altbestaende_und_laufender_bot(tmp_path, monkeypatch):
    a, b = _altbestand(tmp_path / "a", sperre=False), _altbestand(tmp_path / "b", sperre=False)
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", os.pathsep.join([str(a), str(b)]))
    with pytest.raises(umzug.UmzugFehler, match="Mehrere"):
        umzug.umziehen()
    with Schreibsperre(paths.kit_home() / "schreiber"), pytest.raises(umzug.UmzugFehler, match="läuft noch"):
        umzug.umziehen(a)                                              # Bot in der neuen Ablage läuft
    assert umzug.umziehen(a)["dateien"]["probe"] == 1
    assert umzug.offene_altbestaende() == [b]
    erg = umzug.umziehen(b)                                            # zweiter Bestand: Ziel belegt → nur Sperren (keine)
    assert erg["nicht_kopiert"] == ["freigaben", "geheim", "probe"] and erg["sperren_uebernommen"] == {}
    assert umzug.offene_altbestaende() == []


def test_alte_marke_ohne_umzugsbuch_gilt_fuer_aeltere_dateien(tmp_path, monkeypatch):
    alt = _altbestand(tmp_path / "alt", sperre=False)
    _alte_marke(alt, paths.kit_home())                                 # Umzug mit dem Stand vor dem Umzugsbuch
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    assert umzug.offene_altbestaende() == [] and umzug.offene_altbestaende(ziel=paths.kit_home().parent / "anders") == [alt]
    spaeter = alt / "probe" / "journal" / "2099-01-01.jsonl"
    spaeter.write_bytes(b"x")
    os.utime(spaeter, (4e9, 4e9))
    assert umzug.offene_altbestaende() == [alt]


def test_drill_stop_zaehlt_nicht(tmp_path, monkeypatch):
    alt = tmp_path / "alt"
    (alt / "probe").mkdir(parents=True)
    (alt / "probe" / "STOP").write_text("K3 DRILL\n", encoding="utf-8")
    monkeypatch.setenv("KIT_ALTE_ABLAGEN", str(alt))
    assert umzug.offene_altbestaende() == []
    stop_setzen(alt / "probe", 2)                                      # echte STOP-Absicht allein öffnet das Tor
    assert umzug.offene_altbestaende() == [alt]
    assert umzug.umziehen()["sperren_uebernommen"] == {"probe": ["STOP-K2"]}


def test_versatz_ausweichsymbol_nur_bei_stehendem_kursstrom():
    sim, modul, term, uhr = _paar()
    term.versatz_s = None
    konf = Konfiguration("", ("EURUSD", "GBPUSD", "USDJPY"), ("EURUSD", "GBPUSD", "USDJPY"))
    with pytest.raises(BrokerFehler) as fehler:
        betrieb._versatz_messen(term, konf, lambda s: None, None)      # Kursstrom steht überall: jede Ursache genannt
    assert all(s in str(fehler.value) for s in ("EURUSD", "GBPUSD", "USDJPY"))
    betrieb._versatz_messen(term, konf, uhr.vor, "GBPUSD")             # Ticks laufen: gemessen
    assert term.versatz_s == 3 * 3600
    aufrufe: list[str] = []

    def keine_zone(symbol, **kw):
        aufrufe.append(symbol)
        raise BrokerFehler(f"{symbol}: Versatz 1800 s ist keine Ganzstundenzone – nichts gesetzt.")
    term.messe_versatz = keine_zone
    with pytest.raises(BrokerFehler, match="Ganzstundenzone"):
        betrieb._versatz_messen(term, konf, lambda s: None, None)
    assert aufrufe == ["EURUSD"]                                       # anderer Fehler: kein Ausweichen


def test_ende_auch_wenn_der_start_nach_start_satz_scheitert(monkeypatch):
    sim, modul, term, uhr = _paar()
    betrieb.konto_registrieren(term)

    def kaputt(self):
        raise BrokerFehler("account_info() lieferte None – kein angemeldetes Konto.")
    monkeypatch.setattr(Bot, "_konto", kaputt)
    with pytest.raises(BrokerFehler):
        betrieb.probe_einzel(term, _konf(), warte=uhr.vor)
    saetze = journal_lesen(paths.ablage("probe") / "journal")
    assert [s["art"] for s in saetze if s["art"] in ("START", "ENDE")] == ["START", "ENDE"]
    assert bedienung.status("probe")["laeuft_vermutlich"] is False


def test_strg_c_im_takt_schreibt_ende(monkeypatch):
    sim, modul, term, uhr = _paar()
    betrieb.konto_registrieren(term)

    def strg_c(self):
        raise KeyboardInterrupt
    monkeypatch.setattr(Bot, "schritt", strg_c)
    monkeypatch.setattr(betrieb, "_versatz_messen", lambda *a: None)  # Versatz ist in der Attrappe schon gesetzt
    with pytest.raises(KeyboardInterrupt):
        betrieb.lauf(term, _konf(), "probe")
    saetze = journal_lesen(paths.ablage("probe") / "journal")
    assert [(s["art"], s["code"]) for s in saetze if s["art"] in ("START", "ENDE")] == [("START", "probe"), ("ENDE", "ABBRUCH")]


def test_sichern_nur_betreiber(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert cli.main(["sichern", "--ziel", str(tmp_path / "s"), "--mit-schluessel"]) == 7
    assert not (tmp_path / "s").exists()
