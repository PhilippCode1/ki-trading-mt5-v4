"""Tor T aus dem Journal: Fenster je mechanik_hash, Zählung, Quote, jede Null-Toleranz-Art, Urteile; mechanik_hash-Bindung."""
from __future__ import annotations

from pathlib import Path

from kit.gates import ROOT, tore
from kit.gates.tor_t import auswerten, mechanik_dateien, mechanik_hash
from kit.state.journal import Journal

T = tore()["tor_t"]
H = "h" * 64


def _op(j: Journal, n: int, action: str, status: str = "ERLEDIGT", *, absicht: str = "", versuche: int = 1, gefuellt: str = "0.01",
        art: str = "OP_ERGEBNIS", geplant: bool = True) -> None:
    if geplant and art != "OP_LOKAL_ABGELEHNT":
        _op(j, n, action, "GEPLANT", absicht=absicht, versuche=0, gefuellt="0", art="OP_GEPLANT", geplant=False)
    j.schreiben(art, status, "op", op_id=f"op{n}", absicht_id=absicht or f"A{n}", action=action, symbol="EURUSD", side="BUY",
                volume="0.01", sl="1", tp="2", ticket=1, namensraum="PROBE", grund_absicht="", magic=1, status=status, versuche=versuche,
                retcodes=[10009], t_geplant=0.0, t_gesendet=0.0, gefuellt=gefuellt, deals=[], order=0, grund="", negativnachweis=False)


def _journal(tmp: Path, *, eroeffnen=100, schliessen=100, aendern=100, fehler=0) -> Journal:
    j = Journal(tmp / "j", fsync=False)
    j.schreiben("START", "probe", "s", modus="probe", mechanik_hash=H, strategie_hash="", version="x", sperren=[])
    n = 0
    for action, anzahl in (("ENTRY_DEAL", eroeffnen), ("REDUCE_DEAL", schliessen), ("PROTECT_SLTP", aendern)):
        for _ in range(anzahl):
            n += 1
            _op(j, n, action, "ABGELEHNT" if n <= fehler else "ERLEDIGT")
    return j


def test_bestanden_laeuft_und_quote(tmp_path):
    j = _journal(tmp_path)
    s = auswerten(j.lesen(), T, mechanik=H, jetzt=0)
    assert s["urteil"] == "BESTANDEN" and s["gesendet"] == 300 and s["quote"] == "1.0000"
    j2 = _journal(tmp_path / "b", aendern=49)
    assert auswerten(j2.lesen(), T, mechanik=H, jetzt=0)["urteil"] == "LAEUFT"
    j3 = _journal(tmp_path / "c", fehler=16)                                    # 284/300 = 94,7 % < 95 %
    s3 = auswerten(j3.lesen(), T, mechanik=H, jetzt=0)
    assert s3["urteil"] == "NICHT_BESTANDEN" and s3["fehlerfrei"] == 284
    j4 = _journal(tmp_path / "d", fehler=15)                                    # 285/300 = 95 %
    assert auswerten(j4.lesen(), T, mechanik=H, jetzt=0)["urteil"] == "BESTANDEN"


def test_fenster_beginnt_mit_aktuellem_hash(tmp_path):
    j = _journal(tmp_path)
    j.schreiben("START", "probe", "s", modus="probe", mechanik_hash="neu", strategie_hash="", version="x", sperren=[])
    _op(j, 999, "ENTRY_DEAL")
    s = auswerten(j.lesen(), T, mechanik="neu", jetzt=0)
    assert s["gesendet"] == 1 and s["urteil"] == "LAEUFT"
    assert auswerten(j.lesen(), T, mechanik="unbekannt", jetzt=0)["urteil"] == "NICHT_BEWERTBAR"


def test_skripte_und_lokale_ablehnungen_zaehlen_getrennt(tmp_path):
    j = _journal(tmp_path)
    _op(j, 500, "ENTRY_DEAL", "ABGELEHNT", absicht="SK-D06-UNGUELTIG")
    _op(j, 501, "ENTRY_DEAL", "LOKAL_ABGELEHNT", versuche=0, art="OP_LOKAL_ABGELEHNT")
    j.schreiben("SKRIPT", "PASS", "D-06", skript="D-06", kt=[], grund="", schritte=[])
    s = auswerten(j.lesen(), T, mechanik=H, jetzt=0)
    assert s["urteil"] == "BESTANDEN" and s["gesendet"] == 300 and s["lokal_abgelehnt"] == 1 and s["skripte"] == {"D-06": "PASS"}


def _defekt(tmp_path, schreibe) -> list[str]:
    j = _journal(tmp_path)
    schreibe(j)
    saetze = j.lesen()
    s = auswerten(saetze, T, mechanik=H, jetzt=saetze[-1]["t"] + 1000)
    assert s["urteil"] == "NICHT_BESTANDEN"
    return [d["art"] for d in s["defekte"]]


def test_null_toleranz_jede_art(tmp_path):
    assert _defekt(tmp_path / "1", lambda j: _op(j, 900, "REDUCE_DEAL", absicht="NOTSCHLUSS-5")) == ["POSITION_OHNE_SL"]
    assert _defekt(tmp_path / "2", lambda j: _op(j, 901, "ENTRY_DEAL", gefuellt="0.02")) == ["DOPPEL_FILL"]
    assert _defekt(tmp_path / "3", lambda j: j.schreiben("VORFALL", "NEGPROOF_FALSIFIED", "x")) == ["NEGPROOF_FALSIFIED"]
    assert _defekt(tmp_path / "4", lambda j: j.schreiben("VORFALL", "EIGENER_DEAL_OHNE_OPERATION", "x")) == ["EIGENER_DEAL_OHNE_OPERATION"]
    assert _defekt(tmp_path / "5", lambda j: _op(j, 902, "ENTRY_DEAL", "UNBEKANNT")) == ["UNBEKANNT_ZU_LANG"]
    assert _defekt(tmp_path / "6", lambda j: j.schreiben("ABGLEICH", "DIFFERENZ", "x", differenzen=["POSITION_FEHLT a"])) == \
        ["ABGLEICHDIFFERENZ"]
    assert _defekt(tmp_path / "7", lambda j: j.schreiben("KILL", "K1", "x", stufe=1, ausloeser="a", dauer_s=5.5, drill=True)) == ["KILL_ZEIT"]
    assert _defekt(tmp_path / "8", lambda j: j.schreiben("KILL_FLACH", "K3", "x", ausloeser="a", dauer_s=61, drill=True)) == ["KILL_ZEIT"]
    assert _defekt(tmp_path / "9", lambda j: _op(j, 903, "PROTECT_SLTP", "LOKAL_ABGELEHNT", versuche=0, art="OP_LOKAL_ABGELEHNT")
                   ) == ["SCHUTZ_LOKAL_ABGEWIESEN"]
    assert _defekt(tmp_path / "10", lambda j: j.schreiben("SKRIPT", "FAIL", "D-01", skript="D-01", kt=[], grund="", schritte=[])) == \
        ["SKRIPT_FAIL"]


def test_unbekannt_kurz_ist_kein_defekt(tmp_path):
    j = _journal(tmp_path)
    _op(j, 950, "ENTRY_DEAL", "UNBEKANNT")
    _op(j, 950, "ENTRY_DEAL", "ABGELEHNT", art="OP_GEKLAERT", geplant=False)
    saetze = j.lesen()
    assert auswerten(saetze, T, mechanik=H, jetzt=saetze[-1]["t"] + 10_000)["defekte"] == []


def test_mechanik_hash_bindung(tmp_path):
    for rel in ("kit/orders/a.py", "kit/report/b.py", "kit/live_guard.py", "requirements/bot-runtime.lock.txt"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x", encoding="utf-8")
    muster = list(T["mechanik"])
    h0 = mechanik_hash(tmp_path, muster)
    (tmp_path / "kit/report/b.py").write_text("geändert", encoding="utf-8")
    assert mechanik_hash(tmp_path, muster) == h0                                 # Berichte gehören nicht zur Mechanik
    (tmp_path / "kit/orders/a.py").write_text("geändert", encoding="utf-8")
    assert mechanik_hash(tmp_path, muster) != h0
    echte = {p.relative_to(ROOT).as_posix() for p in mechanik_dateien(muster)}
    assert {"kit/run/loop.py", "kit/orders/lifecycle.py", "kit/risk/band.py", "kit/live_guard.py", "kit/daten/retcodes.json"} <= echte
    assert not any(p.startswith(("kit/gates/", "kit/report/", "kit/strategy/", "kit/research/")) for p in echte)


def test_review_befunde_tor_t(tmp_path):
    j = _journal(tmp_path)
    j.schreiben("SKRIPT", "FAIL", "D-01", skript="D-01", kt=[], grund="", schritte=[])
    j.schreiben("SKRIPT", "PASS", "D-01", skript="D-01", kt=[], grund="", schritte=[])
    s = auswerten(j.lesen(), T, mechanik=H, jetzt=0)
    assert s["skripte"]["D-01"] == "FAIL" and [d["art"] for d in s["defekte"]] == ["SKRIPT_FAIL"]   # PASS überschreibt kein FAIL
    j2 = _journal(tmp_path / "b")
    _op(j2, 700, "REDUCE_DEAL", "ABGELEHNT", absicht="NOTSCHLUSS-9", versuche=0)                    # nie gesendet: trotzdem Defekt
    assert [d["art"] for d in auswerten(j2.lesen(), T, mechanik=H, jetzt=0)["defekte"]] == ["POSITION_OHNE_SL"]
    j3 = Journal(tmp_path / "c", fsync=False)
    j3.schreiben("START", "probe", "s", modus="probe", mechanik_hash="alt", strategie_hash="", version="x", sperren=[])
    _op(j3, 1, "ENTRY_DEAL", "UNBEKANNT")
    j3.schreiben("START", "probe", "s", modus="probe", mechanik_hash=H, strategie_hash="", version="x", sperren=[])
    _op(j3, 1, "ENTRY_DEAL", "ABGELEHNT", art="OP_GEKLAERT", geplant=False)                          # alte Operation: nicht im Fenster
    s3 = auswerten(j3.lesen(), T, mechanik=H, jetzt=0)
    assert s3["gesendet"] == 0
    j4 = _journal(tmp_path / "d", eroeffnen=10, schliessen=0, aendern=0)
    for n in range(20, 30):
        _op(j4, n, "ENTRY_DEAL", "LOKAL_ABGELEHNT", versuche=0, art="OP_LOKAL_ABGELEHNT")
    assert auswerten(j4.lesen(), T, mechanik=H, jetzt=0)["absicht_zu_operation"] == "0.5000"      # nicht doppelt gezählt
    j5 = _journal(tmp_path / "e")
    j5.schreiben("KILL", "K1", "x", stufe=1, ausloeser="STOP-Datei", dauer_s=3600, drill=False)     # nur Drills haben Zielzeiten
    assert auswerten(j5.lesen(), T, mechanik=H, jetzt=0)["defekte"] == []
