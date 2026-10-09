"""VPS-Betrieb: geplante Tagessicherung ohne Konsole (nie beim Agenten, Schlüssel nur interaktiv), Tor-T-Stand ohne
Exportdatei für den 15-min-Status, VPS-Skripte nur ASCII (Windows PowerShell 5.1 liest Dateien ohne BOM als ANSI)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kit import cli, paths

ROOT = Path(__file__).resolve().parents[1]


def _ohne_agent(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)


def test_tagessicherung_ohne_konsole_aber_nie_beim_agenten(monkeypatch, tmp_path):
    _ohne_agent(monkeypatch)
    assert cli.main(["sichern", "--ziel", str(tmp_path / "s")]) == 0           # Aufgabe des Bot-Benutzers
    assert list((tmp_path / "s").glob("kit-sicherung-*.zip"))
    assert cli.main(["sichern", "--ziel", str(tmp_path / "k"), "--mit-schluessel"]) == 7   # Schlüssel nur interaktiv
    assert not (tmp_path / "k").exists()
    monkeypatch.setenv("CLAUDECODE", "1")
    assert cli.main(["sichern", "--ziel", str(tmp_path / "a")]) == 7            # Agentensitzung: nie
    assert not (tmp_path / "a").exists()


def test_tor_t_ohne_export(capsys):
    assert cli.main(["tor-t", "--stand", "--ohne-export"]) == 0
    assert "Tor T" in capsys.readouterr().out and not (paths.kit_home() / "export").exists()
    assert cli.main(["tor-t", "--stand"]) == 0 and list((paths.kit_home() / "export").glob("tor_t-probe-*.json"))


def test_vps_skripte_nur_ascii():
    skripte = sorted((ROOT / "deploy" / "windows-vps").glob("*.ps*1"))
    assert len(skripte) >= 10
    for s in skripte:
        assert s.read_bytes().isascii(), s.name


def test_wiederherstellen_aus_sicherung(tmp_path, monkeypatch):
    import zipfile

    from kit import bedienung, umzug
    from kit.state import sperren as sp
    from kit.state.journal import Journal
    from kit.state.journal import lesen as journal_lesen
    alt = tmp_path / "laptop"
    monkeypatch.setenv("KIT_HOME", str(alt))
    j = Journal(alt / "probe" / "journal", fsync=False)
    j.schreiben("START", "probe", "Bot gestartet")
    j.schreiben("BOT_SPERRE", "K2", "Test", stufe=2)
    (alt / "geheim").mkdir()
    (alt / "geheim" / "hmac.key").write_bytes(b"schluessel")
    zip_datei = bedienung.sichern(tmp_path / "s", mit_schluessel=True)
    neu = tmp_path / "vps"
    monkeypatch.setenv("KIT_HOME", str(neu))
    erg = umzug.wiederherstellen(zip_datei)
    assert erg["dateien"]["probe"] == 1 and erg["hinweis"] == ""
    assert "K2" in sp.aus_journal(journal_lesen(neu / "probe" / "journal"))
    assert (neu / "geheim" / "hmac.key").read_bytes() == b"schluessel"
    umzug.pruefen()
    boese = tmp_path / "boese.zip"
    with zipfile.ZipFile(boese, "w") as z:
        z.writestr("../ausserhalb.txt", "x")
    with pytest.raises(umzug.UmzugFehler, match="Unzulässig"):
        umzug.wiederherstellen(boese)
    assert cli.main(["wiederherstellen", "--aus", str(tmp_path / "fehlt.zip")]) == 1


def test_lokal_toml_nur_terminal_und_symbolnamen():
    from kit import config

    assert config.laden().terminal_pfad == ""                                  # Repo: rechnerneutral
    lokal = paths.kit_home() / "lokal.toml"
    lokal.parent.mkdir(parents=True, exist_ok=True)
    lokal.write_text("[terminal]\npfad = 'C:\\KI-Trading\\mt5-demo\\terminal64.exe'\n[symbol_namen]\nEURUSD = \"EURUSD.a\"\n",
                     encoding="utf-8")
    k = config.laden()
    assert k.terminal_pfad.endswith("terminal64.exe") and k.broker_name("EURUSD") == "EURUSD.a"
    for falsch in ("[zeiten]\nfenster_bis = \"23:59\"\n", "[terminal]\npfad = 'x'\nlogin = 1\n", "[terminal]\nanderes = 1\n"):
        lokal.write_text(falsch, encoding="utf-8")
        with pytest.raises(ValueError):
            config.laden()                                                      # Schwellen/Fenster nie am Repo vorbei


def test_ablage_nicht_ueber_testvariablen_umlenkbar(tmp_path):
    """Außerhalb von pytest dürfen PYTEST_CURRENT_TEST + KIT_HOME die Ablage nicht umbiegen (Sperren-Umgehung)."""
    import os
    import subprocess
    import sys
    umgebung = {**os.environ, "PYTEST_CURRENT_TEST": "x", "KIT_HOME": str(tmp_path / "fremd"), "KIT_ALTE_ABLAGEN": ""}
    code = ("from kit import paths, umzug\n"
            "try:\n    paths.kit_home(); print('UMGELENKT')\nexcept paths.AblageFehler:\n    print('GESPERRT')\n"
            "print('ALT', len(umzug.alte_ablagen()) > 0)")
    aus = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=umgebung, capture_output=True, text=True, check=True).stdout
    assert "GESPERRT" in aus and "ALT True" in aus


def test_veraenderte_installation_startet_nie(tmp_path, monkeypatch, capsys):
    """Autostart-Pfad (start_probe.cmd → kit lauf) prüft den mechanik_hash wie kit starten; Exit 2 = kein Neustart."""
    import json
    app = tmp_path / "app" / "lauf_F-99"
    app.mkdir(parents=True)
    (app / "INSTALLATION.json").write_text(json.dumps({"mechanik_hash": "veraendert"}), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", app)
    monkeypatch.setattr(cli, "installiert", lambda: True)
    assert "Installation verändert" in (cli.installation_veraendert() or "")
    assert cli.main(["lauf", "--modus", "probe", "--schreiben"]) == 2
    assert "Schreibmodus verweigert" in capsys.readouterr().out
