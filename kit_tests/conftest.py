"""Gemeinsame Einstellungen der kit-Tests.

- MetaTrader5 ist in Tests gesperrt (Attrappe statt echtem Terminal): jeder Zugriff auf das Modul wirft.
- Die echte Laufzeitablage ist gesperrt: KIT_HOME zeigt immer auf einen temporären Ordner.
- Im öffentlichen Spiegel (Wurzel trägt PUBLIC_SNAPSHOT.md) werden die mit `privat` markierten Tests übersprungen.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from hypothesis import settings

settings.register_profile("kit", derandomize=True, database=None, deadline=None, max_examples=200)
settings.load_profile("kit")

OEFFENTLICHER_SPIEGEL = (Path(__file__).resolve().parents[1] / "PUBLIC_SNAPSHOT.md").is_file()


class _GesperrtesModul(types.ModuleType):
    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)                 # Werkzeuge (z. B. hypothesis) tasten Module nach __file__ ab
        raise RuntimeError("MetaTrader5 ist in kit_tests gesperrt – die SIM-Attrappe verwenden.")


sys.modules["MetaTrader5"] = _GesperrtesModul("MetaTrader5")


def pytest_configure(config):
    config.addinivalue_line("markers", "privat: braucht Dateien, die nur im privaten Repo liegen (im öffentlichen Spiegel ausgelassen)")


def pytest_collection_modifyitems(config, items):
    if not OEFFENTLICHER_SPIEGEL:
        return
    ueberspringen = pytest.mark.skip(reason="öffentlicher Spiegel: braucht Dateien, die nur im privaten Repo liegen")
    for item in items:
        if "privat" in item.keywords:
            item.add_marker(ueberspringen)


@pytest.fixture(autouse=True)
def _kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KIT_HOME", str(tmp_path / "kit_home"))
    monkeypatch.setenv("KIT_SPERRLISTE", str(tmp_path / "keine_sperrliste.txt"))
