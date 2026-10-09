"""Trockenlauf (gekürzt): kompletter Takt über die MT5-Attrappe – Mittwochs-Rollover mit offener Position und Neustart; Wochenende
ohne Einstiege. Der volle 7-Tage-Lauf (1-s-Takt) läuft per `kit trockenlauf` und liegt als Bericht unter berichte/tor_t/."""
from __future__ import annotations

import datetime as dt

from kit.run import trockenlauf
from kit.state.journal import lesen

UTC = dt.UTC


def test_mittwoch_rollover_neustart_null_defekte(tmp_path):
    erg = trockenlauf.laufen(tmp_path, tage=0.9, schritt_s=10, neustart_nach_tagen=0.4)
    assert erg.ok, (erg.tor_t.get("defekte"), erg.replay_abweichungen, erg.abgleich_differenzen, erg.sperren)
    assert erg.neustarts == 1 and erg.replay_gleich
    assert ("2026-10-07", 3, True) in erg.rollover                         # Dreifachswap Mi → Do mit offener Position
    t = erg.tor_t
    assert t["eroeffnen"] > 0 and t["schliessen"] > 0 and t["aendern"] > 0 and t["quote"] == "1.0000"


def test_wochenende_ohne_einstiege(tmp_path):
    start = dt.datetime(2026, 10, 9, 17, 0, tzinfo=UTC)                     # Freitag 19:00 Berlin
    erg = trockenlauf.laufen(tmp_path, start=start, tage=2.7, schritt_s=60, neustart_nach_tagen=1.5)
    assert erg.ok and erg.wochenende
    fr_20 = dt.datetime(2026, 10, 9, 18, 0, tzinfo=UTC).timestamp()       # Freitag 20:00 Berlin
    mo_08 = dt.datetime(2026, 10, 12, 6, 0, tzinfo=UTC).timestamp()       # Montag 08:00 Berlin
    eroeffnet = [s["t"] for s in lesen(tmp_path / "bot" / "journal") if s["art"] == "OP_GEPLANT" and s["daten"]["action"] == "ENTRY_DEAL"]
    assert eroeffnet and not [t for t in eroeffnet if fr_20 <= t < mo_08]
