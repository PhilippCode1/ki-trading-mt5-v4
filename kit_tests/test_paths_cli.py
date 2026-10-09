"""Laufzeitablage und Umgebungsprüfung."""
from __future__ import annotations

import pytest

from kit import cli, paths


def test_ablage_je_modus_unter_kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KIT_HOME", str(tmp_path))
    assert paths.ablage("demo") == tmp_path / "demo"
    assert paths.ablage("backtest") != paths.ablage("demo")
    with pytest.raises(paths.AblageFehler):
        paths.ablage("echtgeld")


def test_echte_ablage_unter_pytest_gesperrt(monkeypatch):
    monkeypatch.delenv("KIT_HOME", raising=False)
    with pytest.raises(paths.AblageFehler):
        paths.kit_home()


def test_lauschende_ports_aus_netstat():
    beispiel = (
        "  Proto  Lokale Adresse  Remoteadresse  Status  PID\n"
        "  TCP    127.0.0.1:22346  0.0.0.0:0  LISTENING  4711\n"
        "  TCP    0.0.0.0:445  0.0.0.0:0  LISTENING  4\n"
        "  TCP    127.0.0.1:50000  127.0.0.1:22345  HERGESTELLT  9\n"
    )
    assert cli.lauschende_ports(lambda: beispiel) == {22346, 445}


def test_pruefen_meldet_fehler_bei_offenen_mcp_ports_und_globalem_mt5():
    erg = dict((t, s) for s, t in cli.pruefen(ports={22345}, globales_mt5=True, frei_gb=100.0))
    assert any(s == "FEHLER" and "22345" in t for t, s in erg.items())
    assert any(s == "FEHLER" and "globalen Python" in t for t, s in erg.items())


def test_pruefen_ok_ohne_befund():
    erg = cli.pruefen(ports=set(), globales_mt5=False, frei_gb=100.0)
    assert all(s != "FEHLER" for s, _ in erg), erg


def test_globales_mt5_auswertung():
    assert cli.globales_mt5_vorhanden(lambda cmd: 0) in (True, None)
    assert cli.globales_mt5_vorhanden(lambda cmd: 3) in (False, None)


def test_version(capsys):
    assert cli.main(["version"]) == 0
    assert "kit " in capsys.readouterr().out


def test_ablage_ausserhalb_von_pytest_nicht_umbiegbar(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("KIT_HOME", str(tmp_path))
    with pytest.raises(paths.AblageFehler):                    # KIT_HOME wäre ein Weg, Sperren zu umgehen
        paths.kit_home()
    monkeypatch.delenv("KIT_HOME")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert tmp_path not in paths.kit_home().parents               # Umgebungsvariable zählt nicht (Shell-API)
