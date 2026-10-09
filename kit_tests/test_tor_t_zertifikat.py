"""Tor-T-Zertifikat: nur bei BESTANDEN, Urteil aus dem redigierten Export nachgerechnet, keine offene Operation am Fensterende,
gebunden an mechanik_hash, Commit, tore.toml und Export-SHA; Belege nur mit demselben mechanik_hash; exklusiv und nie überschreiben;
Fenster im Export; CLI und sauberer Arbeitsbaum ohne Export."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from kit import bedienung, cli
from kit.gates import ROOT, TORE_SHA256, tore, zertifikat
from kit.gates.tor_t import auswerten
from kit.report.redact import redigieren
from kit.state.journal import Journal

T = tore()["tor_t"]
H = "4fab5281ae45e39df25fb2c54065ef50a091e0a321c10afec67d0b40f7be3b93"   # der in den Belegen genannte mechanik_hash


def _op(j: Journal, n: int, action: str, status: str = "ERLEDIGT") -> None:
    gemeinsam = {"op_id": f"op{n}", "absicht_id": f"A{n}", "action": action, "symbol": "EURUSD", "side": "BUY", "volume": "0.01", "sl": "1",
                 "tp": "2", "ticket": 1, "namensraum": "PROBE", "grund_absicht": "", "magic": 1, "retcodes": [10009], "t_geplant": 0.0,
                 "t_gesendet": 0.0, "deals": [], "order": 0, "grund": "", "negativnachweis": False}
    j.schreiben("OP_GEPLANT", "GEPLANT", "op", **gemeinsam, status="GEPLANT", versuche=0, gefuellt="0")
    j.schreiben("OP_ERGEBNIS", status, "op", **gemeinsam, status=status, versuche=1, gefuellt="0.01")


def _export(tmp, *, eroeffnen=100, schliessen=100, aendern=100, fehler=0, kills=(), offen=0) -> tuple[dict, Path]:
    j = Journal(tmp / "j", fsync=False)
    j.schreiben("START", "probe", "s", modus="probe", mechanik_hash=H, strategie_hash="", version="x", sperren=[])
    n = 0
    for action, anzahl in (("ENTRY_DEAL", eroeffnen), ("REDUCE_DEAL", schliessen), ("PROTECT_SLTP", aendern)):
        for _ in range(anzahl):
            n += 1
            _op(j, n, action, "ABGELEHNT" if n <= fehler else "ERLEDIGT")
    for stufe, dauer, drill in kills:
        j.schreiben("KILL", "K", "k", stufe=stufe, dauer_s=dauer, drill=drill)
    for i in range(offen):
        _op(j, 900 + i, "ENTRY_DEAL", "GESENDET")                          # Sendung am Fensterende ohne Ergebnis
    stand = redigieren(auswerten(j.lesen(), T, mechanik=H, jetzt=0))
    pfad = tmp / "tor_t-probe-export.json"
    pfad.write_text(json.dumps(stand, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return stand, pfad


@pytest.fixture
def gleicher_hash(monkeypatch):
    monkeypatch.setattr(zertifikat, "mechanik_hash", lambda root=ROOT: H)


def test_zertifikat_bei_bestanden(tmp_path, gleicher_hash):
    stand, export = _export(tmp_path, kills=((1, 1.0, True), (2, 1.02, True), (3, 1.1, True), (3, 230000.0, False)))
    ziel = tmp_path / "aus"
    j, m = zertifikat.erstellen(export, datum="2099-01-01", commit="c" * 40, ziel=ziel)
    z = json.loads(j.read_text(encoding="utf-8"))
    assert z["urteil"] == "BESTANDEN" and z["mechanik_hash"] == H and z["commit"] == "c" * 40 and z["tore_toml_sha256"] == TORE_SHA256
    assert z["modus"] == "probe" and z["offen"] == 0 and z["python"].count(".") == 1
    kopie = ziel / z["export"]["datei"]
    assert kopie.read_bytes() == export.read_bytes() and z["export"]["sha256"] == hashlib.sha256(export.read_bytes()).hexdigest()
    assert z["zaehlungen"] == {"gesendet": 300, "eroeffnen": 100, "schliessen": 100, "aendern": 100, "fehlerfrei": 300}
    assert z["fenster"]["fenster_ab_seq"] == stand["fenster_ab_seq"] and z["fenster"]["fenster_bis_seq"] == stand["fenster_bis_seq"] > 600
    assert z["fenster"]["fenster_von_utc"].endswith("+00:00") and z["defekte"] == []
    assert z["kills"]["K3"] == {"drills": 1, "drill_max_s": 1.1, "ziel_max_s": T["kill_k3_max_s"], "echt": 1}   # echter Kill ohne Zielzeit
    assert [b["datei"] for b in z["belege"]] == list(zertifikat.BELEGE)
    assert all(b["sha256"] == zertifikat.sha256(ROOT / "berichte" / "tor_t" / b["datei"]) for b in z["belege"])
    text = m.read_text(encoding="utf-8")
    assert "**Urteil: BESTANDEN**" in text and H in text and "Keine Anlageberatung" in text and "1 echt" in text
    assert "keine T-PROBE-Skripte" in text                                  # das synthetische Fenster enthält keine Skripte
    assert zertifikat.urteil_nachrechnen(json.loads(kopie.read_text(encoding="utf-8")), T) == "BESTANDEN"   # reproduzierbar
    with pytest.raises(zertifikat.ZertifikatFehler, match="existiert schon"):
        zertifikat.erstellen(export, datum="2099-01-01", commit="c" * 40, ziel=ziel)


FAELLE = {"laeuft": "Nachgerechnetes", "quote": "Nachgerechnetes", "skript_fail": "Nachgerechnetes", "defekt": "Nachgerechnetes",
          "zaehlung": "Nachgerechnetes", "quote_text": "Quote im Export", "offen": "offen", "hash": "mechanik_hash",
          "mindestens": "Schwellen", "quote_min": "Schwellen", "kill": "Kill-Drill", "beleg": "Beleg", "urteil": "nicht BESTANDEN"}


@pytest.mark.parametrize("fall", sorted(FAELLE))
def test_kein_zertifikat(tmp_path, gleicher_hash, monkeypatch, fall):
    stand, export = _export(tmp_path, aendern=49 if fall == "laeuft" else 100, fehler=16 if fall in ("quote", "urteil") else 0,
                            kills=((2, 6.0, True),) if fall == "kill" else (), offen=1 if fall == "offen" else 0)
    if fall == "offen":
        assert stand["urteil"] == "BESTANDEN" and stand["offen"] == 1           # das Tor allein würde bestehen
    aenderung = {"zaehlung": {"eroeffnen": 99}, "quote_text": {"quote": "0.9999"}, "skript_fail": {"skripte": {"D-01": "FAIL"}},
                "defekt": {"defekte": [{"art": "ABGLEICHDIFFERENZ", "seq": 1, "text": "x"}]}, "hash": {"mechanik_hash": "b" * 64},
                "mindestens": {"mindestens": {**stand["mindestens"], "min_operationen": 30}}, "quote_min": {"quote_min": "0.90"},
                "kill": {"defekte": []}, "beleg": {"mechanik_hash": "a" * 64}}.get(fall, {})
    if fall == "beleg":
        monkeypatch.setattr(zertifikat, "mechanik_hash", lambda root=ROOT: "a" * 64)
    if fall != "urteil":                                                          # Export behauptet BESTANDEN – die Prüfung muss greifen
        stand.update(aenderung, urteil="BESTANDEN")
        export.write_text(json.dumps(stand), encoding="utf-8")
    ziel = tmp_path / "aus"
    with pytest.raises(zertifikat.ZertifikatFehler, match=FAELLE[fall]):
        zertifikat.erstellen(export, datum="2099-01-01", commit="c" * 40, ziel=ziel)
    assert not ziel.exists() or not any(ziel.iterdir())


def test_exklusiv_und_aufgeraeumt(tmp_path, gleicher_hash):
    _, export = _export(tmp_path)
    ziel = tmp_path / "aus"
    ziel.mkdir()
    (ziel / "2099-01-01.md").write_text("vorhanden", encoding="utf-8")
    with pytest.raises(zertifikat.ZertifikatFehler, match="existiert schon"):
        zertifikat.erstellen(export, datum="2099-01-01", commit="c" * 40, ziel=ziel)
    assert [p.name for p in ziel.iterdir()] == ["2099-01-01.md"] and (ziel / "2099-01-01.md").read_text(encoding="utf-8") == "vorhanden"


def test_fenster_und_offen_im_export(tmp_path):
    stand, _ = _export(tmp_path, eroeffnen=1, schliessen=1, aendern=1)
    roh = auswerten(Journal(tmp_path / "j", fsync=False).lesen(), T, mechanik=H, jetzt=0)
    felder = ("fenster_ab_seq", "fenster_bis_seq", "fenster_von_utc", "fenster_bis_utc", "offen")
    assert {k: stand[k] for k in felder} == {k: roh[k] for k in felder}             # redigieren lässt sie unverändert
    assert stand["fenster_bis_seq"] > stand["fenster_ab_seq"] and stand["offen"] == 0 and stand["urteil"] == "LAEUFT"


def test_cli_und_sauberer_commit(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        cli.main(["tor-t", "--stand", "--ohne-export", "--zertifikat"])
    original = bedienung.tor_t_zertifikat
    monkeypatch.setattr(bedienung, "tor_t_zertifikat", lambda modus: ({"urteil": "BESTANDEN"}, Path("x.json"), Path("x.md")))
    assert cli.main(["tor-t", "--stand", "--zertifikat"]) == 0 and "Zertifikat: x.json" in capsys.readouterr().out

    def verweigert(modus):
        raise bedienung.BedienFehler("Arbeitsbaum nicht sauber")
    monkeypatch.setattr(bedienung, "tor_t_zertifikat", verweigert)
    assert cli.main(["tor-t", "--stand", "--zertifikat"]) != 0
    monkeypatch.setattr(bedienung, "tor_t_zertifikat", original)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@localhost.invalid", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run([*git, "add", "a.txt"], check=True)
    subprocess.run([*git, "commit", "-qm", "a"], check=True)
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")                  # Arbeitsbaum nicht sauber → nichts exportieren
    with pytest.raises(bedienung.BedienFehler, match="nicht sauber"):
        bedienung.tor_t_zertifikat("probe", repo=tmp_path)
    assert not (Path(os.environ["KIT_HOME"]) / "export").exists()
