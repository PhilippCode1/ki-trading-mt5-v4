"""D-Skripte/Killer-Tests über den echten Adaptercode (MT5-Attrappe): auf dem SIM alles PASS; REAL → 0 Sendungen."""
from __future__ import annotations

import pytest

from kit.domain.types import HandelsModus
from kit.gates import tore
from kit.gates.tor_t import auswerten
from kit.probe.skripte import NICHT_TESTBAR, Skripte
from kit.run.loop import Ende
from kit.state.store import Schreibsperre
from kit_tests.hilfen import bot_aufbau


def test_alle_skripte_pass_auf_sim(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True)
    with Schreibsperre(bot.ablage):
        bot.starten()
        ergebnisse = Skripte(bot, "EURUSD", warte=uhr.vor).alle()
    urteile = {e.skript: e.urteil for e in ergebnisse}
    fehl = {e.skript: [s for s in e.schritte if not s.ok] for e in ergebnisse if e.urteil == "FAIL"}
    assert not fehl, fehl
    assert {k for k, v in urteile.items() if v == "PASS"} == {"D-01", "D-04", "D-06", "D-09", "D-10", "D-12"}
    assert {k for k, v in urteile.items() if v == "NICHT_TESTBAR"} == set(NICHT_TESTBAR)
    assert not any(p.magic for p in sim.positions())
    stand = auswerten(bot.journal.lesen(), tore()["tor_t"], mechanik=bot.mechanik, jetzt=uhr())
    assert stand["defekte"] == [] and stand["gesendet"] == stand["schliessen"] == 1     # Skripte getrennt; nur das K3-Schließen zählt
    assert stand["skripte"]["D-01"] == "PASS" and all(k["dauer_s"] <= 60 for k in stand["kills"])


def test_skript_auswahl_und_geschlossener_markt(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True)
    bot.starten()
    sk = Skripte(bot, "EURUSD", warte=uhr.vor)
    assert [e.skript for e in sk.alle(["D-12", "D-07"])] == ["D-12", "D-07"]
    sk._markt_offen = lambda: "Markt geschlossen oder Kurs veraltet"
    assert sk.d01().urteil == "NICHT_TESTBAR" and not sim.sendungen


def test_probe_und_skripte_auf_real_senden_nie(tmp_path):
    sim, uhr, bot, _ = bot_aufbau(tmp_path, attrappe=True, probe=True, handelsmodus=HandelsModus.REAL)
    with pytest.raises(Ende):
        bot.starten()
    assert bot.probe.eroeffnen("EURUSD", uhr()) is None
    sk = Skripte(bot, "EURUSD", warte=uhr.vor)
    assert all(e.urteil == "NICHT_TESTBAR" for e in sk.alle())          # Sperre NICHT_DEMO: Skripte eröffnen nichts
    with pytest.raises(Exception):                                         # noqa: B017 - direkter Aufruf: gesperrt
        sk.d01()
    assert sim.sendungen == [] and sim.pruefungen == 0
