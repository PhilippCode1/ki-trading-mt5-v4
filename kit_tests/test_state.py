"""Journal (Hashkette, Schema-Sperre) und Zustand (atomar, fail-closed, Ein-Schreiber, STOP, Kontoabdruck)."""
from __future__ import annotations

import pytest

from kit.state import store
from kit.state.journal import Journal, JournalFehler


def test_journal_kette_und_wiederlesen(tmp_path):
    j = Journal(tmp_path)
    j.schreiben("START", "OK", "Start", modus="sim")
    j.schreiben("OP_GEPLANT", "GEPLANT", "x", op_id="k1", volume="0.10")
    saetze = Journal(tmp_path).lesen()
    assert [s["seq"] for s in saetze] == [1, 2] and saetze[1]["prev"] == saetze[0]["h"]
    j2 = Journal(tmp_path)
    j2.schreiben("STOP", "OK", "Ende")
    assert len(j2.lesen()) == 3


def test_journal_manipulation_wird_erkannt(tmp_path):
    j = Journal(tmp_path)
    j.schreiben("A", "OK", "eins", wert="1")
    j.schreiben("B", "OK", "zwei", wert="2")
    datei = next(tmp_path.glob("*.jsonl"))
    datei.write_text(datei.read_text(encoding="utf-8").replace('"wert": "1"', '"wert": "9"'), encoding="utf-8")
    with pytest.raises(JournalFehler):
        Journal(tmp_path)


@pytest.mark.parametrize("schluessel", ["login", "Server", "password", "name"])
def test_journal_verbietet_kontokennungen(tmp_path, schluessel):
    with pytest.raises(ValueError):
        Journal(tmp_path).schreiben("X", "OK", "x", **{"konto_info": {schluessel: "x"}})


def test_zustand_atomar_und_fail_closed(tmp_path):
    s = store.StateStore(tmp_path)
    assert s.laden(journal_vorhanden=False) == {}
    with pytest.raises(store.ZustandFehler):
        s.laden(journal_vorhanden=True)                 # gelöschter Zustand ist kein Ausweg aus Sperren
    s.speichern({"sperren": {"LOSS_LOCK": True}})
    assert s.laden(journal_vorhanden=True) == {"sperren": {"LOSS_LOCK": True}}
    s.datei.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(store.ZustandFehler):
        s.laden(journal_vorhanden=True)


def test_zweiter_schreiber_scheitert(tmp_path):
    with store.Schreibsperre(tmp_path):
        with pytest.raises(store.SchreiberAktiv):
            with store.Schreibsperre(tmp_path):
                pass
    with store.Schreibsperre(tmp_path):
        pass                                          # nach Freigabe wieder möglich


def test_stop_stufen(tmp_path):
    assert store.stop_stufe(tmp_path) == 0
    store.stop_setzen(tmp_path, 2)
    assert store.stop_stufe(tmp_path) == 2
    (tmp_path / "STOP").write_text("???", encoding="utf-8")
    assert store.stop_stufe(tmp_path) == 1            # unlesbar = K1
    store.stop_setzen(tmp_path, 0)
    assert store.stop_stufe(tmp_path) == 0


def test_kontoabdruck_hmac_ohne_klartext(tmp_path):
    a = store.kontoabdruck(51234567, "Demo-Server", tmp_path / "geheim")
    assert a == store.kontoabdruck(51234567, "Demo-Server", tmp_path / "geheim")
    assert a != store.kontoabdruck(51234568, "Demo-Server", tmp_path / "geheim")
    assert "51234567" not in a and len(a) == 32
    assert a != store.kontoabdruck(51234567, "Demo-Server", tmp_path / "anderer_schluessel")
