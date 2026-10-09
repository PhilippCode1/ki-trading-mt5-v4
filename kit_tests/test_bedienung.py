"""Bedienung: Kill-Dateien, PIN/Entsperren (nur Betreiber, nie ohne PIN), Zustand-Wiederherstellung, Status, Tor-T-Export,
Installieren aus einem Tag, Sichern, CLI-Sperren für Agentensitzungen."""
from __future__ import annotations

import subprocess
import zipfile

import pytest

from kit import bedienung, cli, paths, umzug
from kit.gates.tor_t import mechanik_hash
from kit.run.loop import Bot
from kit.state import pin
from kit.state.journal import Journal
from kit.state.store import SchreiberAktiv, Schreibsperre, ZustandFehler, stop_stufe
from kit_tests.hilfen import bot_aufbau


def _bot_in(modus: str, tmp_path):
    sim, uhr, bot, m = bot_aufbau(tmp_path)
    bot2 = Bot(bot.t, paths.ablage(modus), bot.konf, modus=modus, melder=m, journal_fsync=False)
    return sim, uhr, bot2


def test_stop_dateien_und_k1_aufheben():
    assert "K1" in bedienung.stop("probe", stufe=1)
    assert stop_stufe(paths.ablage("probe")) == 1
    assert "aufgehoben" in bedienung.stop("probe", k1_aufheben=True)
    bedienung.stop("probe", stufe=3)
    with pytest.raises(bedienung.BedienFehler):
        bedienung.stop("probe", k1_aufheben=True)                          # K2/K3 nur mit PIN
    assert stop_stufe(paths.ablage("probe")) == 3
    bedienung.stop("probe", beenden=True)
    assert (paths.ablage("probe") / "BEENDEN").exists()


class Eingaben:
    """Ersetzt die interaktive PIN-Eingabe (getpass) – in Tests wie in der Konsole des Betreibers."""

    def __init__(self, monkeypatch, *werte: str) -> None:
        self.werte = list(werte)
        monkeypatch.setattr(bedienung, "_pin_eingabe", lambda text: self.werte.pop(0))
        monkeypatch.setattr(pin.time, "sleep", lambda s: None)


def test_pin_setzen_pruefen_aendern_und_sperre_nach_fehlversuchen(monkeypatch):
    monkeypatch.setattr(pin.time, "sleep", lambda s: None)
    frei = paths.kit_home() / "freigaben"
    with pytest.raises(pin.PinFehler):
        pin.pruefen(frei, "1234567890")                                      # keine PIN gesetzt
    with pytest.raises(pin.PinFehler):
        pin.setzen(frei, "123456789")                                        # zu kurz (< 10)
    pin.setzen(frei, "geheim-0001")
    assert "geheim" not in (frei / "pin.json").read_text(encoding="utf-8")
    pin.pruefen(frei, "geheim-0001")
    with pytest.raises(pin.PinFehler):
        pin.setzen(frei, "neu-1234567")                                      # Ändern nur mit alter PIN
    pin.setzen(frei, "neu-1234567", alt="geheim-0001")
    t = [1000.0]
    for _ in range(5):
        with pytest.raises(pin.PinFehler, match="falsch"):
            pin.pruefen(frei, "falsch-falsch", uhr=lambda: t[0])
    with pytest.raises(pin.PinFehler, match="gesperrt"):
        pin.pruefen(frei, "neu-1234567", uhr=lambda: t[0])                   # auch die richtige PIN: 1 h gesperrt
    t[0] += 3601
    pin.pruefen(frei, "neu-1234567", uhr=lambda: t[0])
    assert not (frei / "pin_fehler.json").exists()


def test_pin_befehle_nur_interaktiv_beim_betreiber(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(bedienung.BedienFehler):
        bedienung.pin_setzen()
    with pytest.raises(bedienung.BedienFehler):
        bedienung.entsperren("probe", "ALLE")                              # auch direkt aus Python, nicht nur über die CLI
    monkeypatch.delenv("CLAUDECODE")
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(bedienung.BedienFehler):
        bedienung.entsperren("probe", "ALLE")


def test_entsperren_nur_mit_pin_und_nicht_bei_laufendem_bot(tmp_path, monkeypatch):
    sim, uhr, bot = _bot_in("probe", tmp_path)
    bot.starten()
    bot._sperren("K2", "Test")
    Eingaben(monkeypatch, "irgendwas-123")
    with pytest.raises(pin.PinFehler):
        bedienung.entsperren("probe", "K2")                                 # ohne gesetzte PIN unmöglich
    Eingaben(monkeypatch, "richtig-0001", "richtig-0001")
    bedienung.pin_setzen()
    Eingaben(monkeypatch, "falsch-00011")
    with pytest.raises(pin.PinFehler):
        bedienung.entsperren("probe", "K2")
    Eingaben(monkeypatch, "richtig-0001")
    with Schreibsperre(paths.ablage("probe")), pytest.raises(SchreiberAktiv):
        bedienung.entsperren("probe", "K2")                                 # Bot läuft noch
    Eingaben(monkeypatch, "richtig-0001")
    with pytest.raises(bedienung.BedienFehler):
        bedienung.entsperren("probe", "LOSS_LOCK")                          # nicht aktiv
    Eingaben(monkeypatch, "richtig-0001")
    assert "K2" in bedienung.entsperren("probe", "K2")
    neu = Bot(bot.t, bot.ablage, bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    neu.starten()
    assert not neu.sperren and neu.einstieg_gesperrt(uhr()) is None


def test_gelöschter_zustand_bleibt_gesperrt_bis_betreiber(tmp_path, monkeypatch):
    sim, uhr, bot = _bot_in("probe", tmp_path)
    bot.starten()
    bot._sperren("LOSS_LOCK", "Test")
    (paths.ablage("probe") / "zustand.json").unlink()
    with pytest.raises(ZustandFehler):
        Bot(bot.t, bot.ablage, bot.konf, modus="probe", melder=bot.melder, journal_fsync=False).starten()
    Eingaben(monkeypatch, "richtig-0001", "richtig-0001", "richtig-0001")
    bedienung.pin_setzen()
    bedienung.entsperren("probe", "ZUSTAND")                               # Zustand neu aus dem Journal – Sperre bleibt
    neu = Bot(bot.t, bot.ablage, bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    neu.starten()
    assert "LOSS_LOCK" in neu.sperren


def test_loss_lock_aufheben_setzt_neuen_anker(tmp_path, monkeypatch):
    from decimal import Decimal

    from kit.domain.types import DealArt
    sim, uhr, bot = _bot_in("probe", tmp_path)
    bot.starten()
    sim.kapital(Decimal("-2600"), DealArt.GEBUEHR)
    uhr.vor(5)
    bot.schritt()
    assert "LOSS_LOCK" in bot.sperren
    Eingaben(monkeypatch, "richtig-0001", "richtig-0001", "richtig-0001")
    bedienung.pin_setzen()
    bedienung.entsperren("probe", "LOSS_LOCK")
    neu = Bot(bot.t, bot.ablage, bot.konf, modus="probe", melder=bot.melder, journal_fsync=False)
    neu.starten()
    assert "LOSS_LOCK" not in neu.sperren and neu.loss_anker == sim.account().equity


def test_status_und_tor_t_export_redigiert(tmp_path):
    sim, uhr, bot = _bot_in("probe", tmp_path)
    bot.starten()
    st = bedienung.status("probe")
    assert st["laeuft_vermutlich"] and st["sperren"] == [] and st["pin_gesetzt"] is False and st["demokonten_registriert"] == 0
    stand, pfad = bedienung.tor_t_bericht("probe")
    assert stand["urteil"] == "LAEUFT" and pfad.exists() and pfad.with_suffix(".md").exists()
    text = pfad.with_suffix(".md").read_text(encoding="utf-8")
    assert "Keine Anlageberatung" in text and "Tor T" in text


def test_sichern_ohne_schluessel(tmp_path):
    (paths.kit_home() / "freigaben").mkdir(parents=True)
    (paths.kit_home() / "freigaben" / "pin.json").write_text("{}", encoding="utf-8")
    (paths.kit_home() / "geheim").mkdir(parents=True)
    (paths.kit_home() / "geheim" / "hmac.key").write_bytes(b"x" * 32)
    (paths.kit_home() / "probe" / "journal").mkdir(parents=True)
    (paths.kit_home() / "probe" / "journal" / "a.jsonl").write_text("{}\n", encoding="utf-8")
    z = bedienung.sichern(tmp_path / "sicherung")
    namen = zipfile.ZipFile(z).namelist()
    assert "probe/journal/a.jsonl" in namen and not any(n.startswith("geheim") or n.endswith("pin.json") for n in namen)
    assert any(n.startswith("geheim") for n in zipfile.ZipFile(bedienung.sichern(tmp_path / "s2", mit_schluessel=True)).namelist())


def test_installieren_aus_tag(tmp_path):
    repo = tmp_path / "repo"
    for rel, inhalt in (("kit/__init__.py", "x = 1\n"), ("config/tore.toml", "a = 1\n"), ("requirements/bot-runtime.lock.txt", "n\n"),
                        ("geheim.txt", "nicht mitnehmen\n")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(inhalt, encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@localhost.invalid", "-c", "core.hooksPath=/dev/null"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "x"], check=True)
    subprocess.run([*git, "tag", "lauf/F-99"], check=True)
    with pytest.raises(bedienung.BedienFehler, match="Wächter"):
        bedienung.installieren("lauf/F-99", repo=repo)                    # ohne Wächter im Repo keine Installation
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": [{"command": "py tools/agent_waechter.py"}]}}',
                                                    encoding="utf-8")
    (repo / "tools").mkdir()
    waechter = repo / "tools" / "agent_waechter.py"
    waechter.write_text("import sys\nsys.stdin.buffer.read()\nsys.exit(0)\n", encoding="utf-8")
    with pytest.raises(bedienung.BedienFehler, match="schützt die Laufzeitablage nicht"):
        bedienung.installieren("lauf/F-99", repo=repo)                    # Wächter mit Lücke: keine Installation
    waechter.write_text("import sys\nsys.stdin.buffer.read()\nsys.exit(2)\n", encoding="utf-8")
    ziel = bedienung.installieren("lauf/F-99", repo=repo)
    assert (ziel / "kit" / "__init__.py").exists() and not (ziel / "geheim.txt").exists()
    assert "lauf probe" not in (ziel / "start_probe.cmd").read_text(encoding="utf-8")
    assert "--modus probe --schreiben" in (ziel / "start_probe.cmd").read_text(encoding="utf-8")
    with pytest.raises(bedienung.BedienFehler):
        bedienung.installieren("lauf/F-99", repo=repo)                    # unveränderlich
    with pytest.raises(bedienung.BedienFehler):
        bedienung.installieren("gibt-es-nicht", repo=repo)
    gestartet = []

    class Proc:
        pid = 4711
        ende = None

        def poll(self):
            return self.ende

    def popen(befehl, **kw):
        gestartet.append((befehl, kw["cwd"]))
        return Proc()
    journal = Journal(paths.ablage("probe") / "journal", fsync=False)
    journal.schreiben("START", "probe", "alter Start", mechanik_hash=mechanik_hash(ziel))   # zählt nie als neuer Start
    warten: list[float] = []

    def bot_schreibt_start(s):
        warten.append(s)
        if len(warten) == 2:
            journal.schreiben("START", "probe", "andere Mechanik", mechanik_hash="fremd")
        if len(warten) == 3:                                               # START erst nach der Versatzmessung
            journal.schreiben("START", "probe", "Bot gestartet", mechanik_hash=mechanik_hash(ziel))
    assert bedienung.starten("lauf/F-99", "probe", popen=popen, warte=bot_schreibt_start) == 4711 and len(warten) == 3
    befehl, cwd = gestartet[0]
    assert cwd == ziel and befehl[-5:] == ["kit", "lauf", "--modus", "probe", "--schreiben"]
    with pytest.raises(bedienung.BedienFehler, match="noch keinen START"):
        bedienung.starten("lauf/F-99", "probe", popen=popen, warte=lambda s: None, start_frist_s=20)
    Proc.ende = 1                                                          # Prozess endet sofort (z. B. Schreibmodus verweigert)
    with pytest.raises(bedienung.BedienFehler, match="sofort beendet"):
        bedienung.starten("lauf/F-99", "probe", popen=popen, warte=lambda s: None)
    Proc.ende = None
    (ziel / "kit" / "orders").mkdir(parents=True)
    (ziel / "kit" / "orders" / "x.py").write_text("manipuliert", encoding="utf-8")
    with pytest.raises(bedienung.BedienFehler):
        bedienung.starten("lauf/F-99", "probe", popen=popen, warte=lambda s: None)   # veränderte Installation startet nie
    with pytest.raises(bedienung.BedienFehler):
        bedienung.starten("lauf/F-98", "probe", popen=popen, warte=lambda s: None)


def test_cli_betreiberbefehle_nie_in_agentensitzung(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert cli.main(["pin-setzen"]) == 7
    assert cli.main(["entsperren", "--grund", "ALLE"]) == 7
    assert "Betreiber" in capsys.readouterr().out
    monkeypatch.delenv("CLAUDECODE")
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["entsperren", "--grund", "ALLE"]) == 7


def test_cli_stop_status_lauf_ohne_schreiben(capsys):
    assert cli.main(["stop", "--k1"]) == 0 and stop_stufe(paths.ablage("probe")) == 1
    assert cli.main(["status"]) == 0
    assert cli.main(["lauf", "--modus", "probe"]) == 2 and "Ohne --schreiben" in capsys.readouterr().out


def test_umziehen_kopiert_pruefend_ohne_loeschen(tmp_path):
    quelle, ziel = tmp_path / "alt", tmp_path / "neu"
    for rel in ("probe/journal/2026-10-05.jsonl", "freigaben/demo_konten.json", "geheim/hmac.key", "marktdaten/entwicklung.sqlite"):
        (quelle / rel).parent.mkdir(parents=True, exist_ok=True)
        (quelle / rel).write_bytes(rel.encode())
    (quelle / "probe" / "LOCK").write_bytes(b"")
    erg = umzug.umziehen(quelle, ziel)
    assert erg["dateien"] == {"probe": 1, "freigaben": 1, "geheim": 1, "marktdaten": 1}
    assert (ziel / "geheim" / "hmac.key").read_bytes() == b"geheim/hmac.key" and not (ziel / "probe" / "LOCK").exists()
    assert (quelle / "probe" / "journal" / "2026-10-05.jsonl").exists() and (quelle / "UMGEZOGEN.txt").exists()   # nichts gelöscht
    with Schreibsperre(quelle / "probe"), pytest.raises(umzug.UmzugFehler, match="läuft noch"):
        umzug.umziehen(quelle, tmp_path / "neu2")                            # nicht bei laufendem Bot
    with pytest.raises(umzug.UmzugFehler, match="nichts"):
        umzug.umziehen(tmp_path / "leer", tmp_path / "neu3")


def test_ablage_liegt_im_benutzerprofil_nicht_in_appdata(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("KIT_HOME", raising=False)
    heim = paths.kit_home()
    assert heim.name == "KI-Trading-Bot" and "AppData" not in heim.parts and paths.alte_ablage().name == "kit"
