"""Versuchsprotokoll F-04 (kit/research/protokoll.py): Anhängen, Hashkette, Vorregistrierung vor der Datensicht, Prüfung.

Git-Teile laufen in einem Wegwerf-Repo unter tmp_path (root = dieses Repo überall); keine echten Kursdaten, kein echtes Protokoll.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from kit.research import protokoll as pk
from kit.research import trials

DATUM = "2026-10-08"
DATEIEN = ["kit/a.py", "kit/b.py", "config/tore.toml", "config/trade_test.toml"]


def _git(repo: Path, *args: str) -> str:
    umgebung = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    erg = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.invalid", "-c", "commit.gpgsign=false",
                          *args], capture_output=True, check=True, env=umgebung)
    return erg.stdout.decode().strip()


def _schreiben(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def _commit(repo: Path) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "t")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _schreiben(r, ".gitattributes", "* -text\n")
    _schreiben(r, "kit/a.py", "A = 1\n")
    _schreiben(r, "kit/b.py", "B = 2\n")
    _schreiben(r, "config/tore.toml", "[t]\nx = 1\n")
    _schreiben(r, "config/trade_test.toml", "[tt]\ny = 2\n")
    _schreiben(r, pk.PREREG_REL, "# Vorregistrierung (Test)\n")
    monkeypatch.setattr(pk, "PREREG_SHA", hashlib.sha256((r / pk.PREREG_REL).read_bytes()).hexdigest())
    _commit(r)
    return r


def _log(repo: Path) -> Path:
    return repo / "forschung" / "versuchsprotokoll.jsonl"


def _idee(n: int) -> dict:
    return {"kind": "IDEA", "actor": "CODING_AGENT", "date": DATUM, "family": "TEST", "note": f"Idee {n} – ü"}


# ---------------------------------------------------------------- Kette und Anhängen
def test_anhaengen_genau_eine_zeile_alte_zeilen_bytegleich(tmp_path):
    pfad = tmp_path / "neu" / "p.jsonl"
    eintraege = []
    for n in range(4):
        vorher = pfad.read_bytes() if pfad.exists() else b""
        eintraege.append(pk.anhaengen(_idee(n), pfad))
        nachher = pfad.read_bytes()
        assert nachher.startswith(vorher) and nachher.count(b"\n") == vorher.count(b"\n") + 1
        assert nachher.endswith(b"\n") and b"\r" not in nachher
    zeilen = pfad.read_text(encoding="utf-8").split("\n")[:-1]
    assert zeilen == [json.dumps(e, ensure_ascii=False, sort_keys=True) for e in eintraege]
    assert pk.lesen(pfad) == eintraege and trials.verify(eintraege) == []
    assert eintraege[0]["prev"] == trials.GENESIS and eintraege[3]["prev"] == eintraege[2]["hash"]
    assert pk.pruefen(pfad, root=tmp_path) == []


def test_lesen_fehlend_leerzeilen_und_kaputtes_json(tmp_path):
    pfad = tmp_path / "p.jsonl"
    assert pk.lesen(pfad) == []
    pk.anhaengen(_idee(0), pfad)
    pfad.write_bytes(pfad.read_bytes() + b"\n  \n")
    assert len(pk.lesen(pfad)) == 1
    pfad.write_bytes(pfad.read_bytes() + b"{kaputt\n")
    with pytest.raises(pk.ProtokollFehler, match="Zeile"):
        pk.lesen(pfad)
    assert pk.pruefen(pfad, root=tmp_path)[0].startswith("LESEN:")


def test_anhaengen_weist_ungueltiges_ab_und_laesst_die_datei_unveraendert(tmp_path):
    pfad = tmp_path / "p.jsonl"
    pk.anhaengen(_idee(0), pfad)
    vorher = pfad.read_bytes()
    for body in ({**_idee(1), "kind": "ERFUNDEN"}, {**_idee(1), "date": "8.10.26"}, {**_idee(1), "wert": Decimal("1.5")},
                 {**_idee(1), "wert": float("nan")}, {"kind": "TRIAL", "actor": "CODING_AGENT", "date": DATUM, "family": "TEST"}):
        with pytest.raises(pk.ProtokollFehler):
            pk.anhaengen(body, pfad)
    assert pfad.read_bytes() == vorher
    pfad.write_bytes(vorher.rstrip(b"\n"))                          # von Hand ohne Zeilenende gespeichert
    with pytest.raises(pk.ProtokollFehler, match="Zeilenumbruch"):
        pk.anhaengen(_idee(1), pfad)


def _manipulieren(zeilen: list[str], art: str) -> list[str]:
    if art == "geaendert":
        e = json.loads(zeilen[1])
        e["body"]["note"] = "nachträglich geändert"
        return [zeilen[0], json.dumps(e, ensure_ascii=False, sort_keys=True), *zeilen[2:]]
    if art == "geloescht":
        return [zeilen[0], *zeilen[2:]]
    return [zeilen[0], zeilen[2], zeilen[1], zeilen[3]]


@pytest.mark.parametrize("art", ["geaendert", "geloescht", "vertauscht"])
def test_manipulation_wird_gemeldet_und_sperrt_das_anhaengen(tmp_path, art):
    pfad = tmp_path / "p.jsonl"
    for n in range(4):
        pk.anhaengen(_idee(n), pfad)
    zeilen = pfad.read_text(encoding="utf-8").split("\n")[:-1]
    pfad.write_text("\n".join(_manipulieren(zeilen, art)) + "\n", encoding="utf-8", newline="\n")
    befunde = pk.pruefen(pfad, root=tmp_path)
    assert any(b.startswith("CHAIN:") for b in befunde), befunde
    with pytest.raises(pk.ProtokollFehler, match="Hashkette"):
        pk.anhaengen(_idee(9), pfad)


def test_konstanten():
    assert pk.FAMILIEN == ("F04-ZIEL-STOP", "F04-REFERENZ", "F04-DATEN")
    assert len(set(pk.CODE_F04)) == len(pk.CODE_F04) and "kit/research/protokoll.py" in pk.CODE_F04
    assert {"kit/config.py", "kit/gates/__init__.py", "kit/backtest/runner.py", "kit/research/entwicklung.py", "kit/cli.py",
            "config/kostenprofil/f04_startwerte.json"} <= set(pk.CODE_F04)
    assert all(not p.startswith("/") and "\\" not in p and ".." not in p for p in pk.CODE_F04)
    assert pk.PFAD == pk.ROOT / "forschung" / "versuchsprotokoll.jsonl" and pk.PREREG_PFAD == pk.ROOT / pk.PREREG_REL


@pytest.mark.privat
def test_prereg_datei_hat_den_gepinnten_sha():
    assert pk.sha256_datei(pk.PREREG_PFAD) == pk.PREREG_SHA


# ---------------------------------------------------------------- Vorregistrierung im Wegwerf-Repo
def test_vorab_traegt_drei_eintraege_ein_und_ist_idempotent(repo):
    log = _log(repo)
    eintraege = pk.vorab("F-04", "OK-TEST", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    kopf = _git(repo, "rev-parse", "HEAD")
    assert [e["body"]["family"] for e in eintraege] == list(pk.FAMILIEN)
    for e in eintraege:
        b = e["body"]
        assert b["kind"] == "PREREG_SIGNED" and b["actor"] == "CODING_AGENT" and b["lauf"] == "F-04" and b["prereg_ok"] == "OK-TEST"
        assert b["commit"] == kopf and b["prereg_sha"] == pk.PREREG_SHA and b["prereg_pfad"] == pk.PREREG_REL
        assert b["code"] == pk.code_hashes(DATEIEN, repo) and b["schwellen_sha"] == pk.sha256_datei(repo / "config/tore.toml")
        assert b["trade_test_sha"] == pk.sha256_datei(repo / "config/trade_test.toml")
    vorher = log.read_bytes()
    assert pk.vorab("F-04", "OK-TEST", DATUM, root=repo, pfad=log, dateien=DATEIEN) == eintraege
    assert log.read_bytes() == vorher and len(pk.lesen(log)) == 3
    assert pk.pruefen(log, root=repo) == []


def test_vorab_verweigert_uncommittete_fehlende_oder_falsche_dateien(repo, monkeypatch):
    log = _log(repo)
    _schreiben(repo, "kit/a.py", "A = 3\n")
    with pytest.raises(pk.ProtokollFehler, match="nicht committet"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    _schreiben(repo, "kit/a.py", "A = 1\n")                          # wieder wie im Commit
    _schreiben(repo, "kit/neu.py", "N = 1\n")                         # unversioniert
    with pytest.raises(pk.ProtokollFehler, match="nicht committet"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=[*DATEIEN, "kit/neu.py"])
    with pytest.raises(pk.ProtokollFehler, match="fehlt"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=[*DATEIEN, "kit/gibtsnicht.py"])
    with pytest.raises(pk.ProtokollFehler, match="prereg_ok"):
        pk.vorab("F-04", " ", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    monkeypatch.setattr(pk, "PREREG_SHA", "0" * 64)
    with pytest.raises(pk.ProtokollFehler, match="PREREG_SHA"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    assert pk.lesen(log) == []


def test_vorab_verweigert_nach_einer_datensicht(repo):
    log = _log(repo)
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"abzug": "ab" * 32}, pfad=log)
    with pytest.raises(pk.ProtokollFehler, match="Datensicht vor der Vorregistrierung"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    assert len(pk.lesen(log)) == 1
    assert "DATA_VIEW_BEFORE_SIGNED_PREREG:0" in pk.pruefen(log, root=repo)


def test_datensicht_und_versuch_nach_vorab_sind_gruen(repo):
    log = _log(repo)
    pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    sicht = pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"EURUSD/H1": "cd" * 32}, pfad=log, zeilen=10)
    assert sicht["body"]["daten"] == {"EURUSD/H1": "cd" * 32} and sicht["body"]["zeilen"] == 10
    v = pk.versuch("F04-ZIEL-STOP", "S-REV-01-k2.0-z0.50-r2", DATUM, pfad=log, code=pk.code_hashes(DATEIEN, repo), trades=3,
                   mechanik_hash=pk._mechanik_hash(repo))
    assert v["body"]["split"] == "DEVELOPMENT" and v["body"]["kind"] == "TRIAL"
    with pytest.raises(pk.ProtokollFehler, match="reservierte"):
        pk.versuch("F04-ZIEL-STOP", "X", DATUM, pfad=log, kind="IDEA")
    assert pk.pruefen(log, root=repo) == []
    assert trials.trial_count(pk.lesen(log), "F04-ZIEL-STOP") == 1


@pytest.mark.parametrize("mit_aenderung", [False, True])
def test_code_nach_der_sicht_geaendert(repo, mit_aenderung):
    log = _log(repo)
    pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    pk.versuch("F04-ZIEL-STOP", "V1", DATUM, pfad=log, code=pk.code_hashes(DATEIEN, repo), mechanik_hash=pk._mechanik_hash(repo))
    _schreiben(repo, "kit/a.py", "A = 1  # Fehler behoben\n")
    _commit(repo)
    if mit_aenderung:
        aenderung = pk.aenderung_nach_sicht(["kit/a.py"], "Rundungsfehler im Werkzeug", DATUM, root=repo, pfad=log)
        assert aenderung["body"]["variant_id"] == "W1" and aenderung["body"]["family"] == pk.WERKZEUG
        assert aenderung["body"]["code"] == {"kit/a.py": pk.sha256_datei(repo / "kit/a.py")}
    v = pk.versuch("F04-ZIEL-STOP", "V2", DATUM, pfad=log, code=pk.code_hashes(DATEIEN, repo), mechanik_hash=pk._mechanik_hash(repo))
    befunde = pk.pruefen(log, root=repo)
    assert befunde == ([] if mit_aenderung else [f"CODE_ABWEICHUNG:{v['seq']}:kit/a.py"])


def test_aenderung_nach_sicht_nur_committet_und_fortlaufend(repo):
    log = _log(repo)
    pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    _schreiben(repo, "kit/b.py", "B = 3\n")
    with pytest.raises(pk.ProtokollFehler, match="nicht committet"):
        pk.aenderung_nach_sicht(["kit/b.py"], "Grund", DATUM, root=repo, pfad=log)
    with pytest.raises(pk.ProtokollFehler, match="Grund"):
        pk.aenderung_nach_sicht(["kit/b.py"], " ", DATUM, root=repo, pfad=log)
    _commit(repo)
    ids = [pk.aenderung_nach_sicht(["kit/b.py"], "Grund", DATUM, root=repo, pfad=log)["body"]["variant_id"] for _ in range(2)]
    assert ids == ["W1", "W2"] and pk.pruefen(log, root=repo) == []


def test_pruefen_meldet_gefaelschte_vorregistrierung(repo, monkeypatch):
    log = _log(repo)
    kopf = _git(repo, "rev-parse", "HEAD")
    echt = pk.code_hashes(DATEIEN, repo)
    basis = {"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": DATUM, "lauf": "F-04", "prereg_pfad": pk.PREREG_REL,
             "prereg_sha": pk.PREREG_SHA, "prereg_ok": "OK", "schwellen_sha": echt["config/tore.toml"],
             "trade_test_sha": echt["config/trade_test.toml"]}
    pk.anhaengen({**basis, "family": "F04-ZIEL-STOP", "commit": kopf, "code": {**echt, "kit/a.py": "f" * 64}}, log)
    pk.anhaengen({**basis, "family": "F04-REFERENZ", "commit": "1" * 40, "code": echt}, log)
    pk.anhaengen({**basis, "family": "F04-DATEN", "commit": kopf, "code": echt, "schwellen_sha": "e" * 64}, log)
    befunde = pk.pruefen(log, root=repo)
    assert "CODE_NICHT_IM_COMMIT:0:kit/a.py" in befunde and "COMMIT_KEIN_VORFAHR:1" in befunde
    assert "CODE_NICHT_IM_COMMIT:2:config/tore.toml" in befunde
    _schreiben(repo, pk.PREREG_REL, "# nachträglich geändert\n")
    assert {f"PREREG_SHA:{i}" for i in range(3)} <= set(pk.pruefen(log, root=repo))



# ---------------------------------------------------------------- Review F-04: Ablaufsicherung
def test_vorab_signiert_vor_der_sicht_neu_und_verweigert_danach(repo):
    log = _log(repo)
    alt = pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    assert pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN) == alt          # unverändert: nichts Neues
    _schreiben(repo, "kit/a.py", "A = 2  # Korrektur vor der Sicht" + chr(10))
    _commit(repo)
    neu = pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    assert [e["seq"] for e in neu] == [3, 4, 5] and neu[0]["body"]["code"]["kit/a.py"] == pk.sha256_datei(repo / "kit/a.py")
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    _schreiben(repo, "kit/a.py", "A = 3  # nach der Sicht" + chr(10))
    _commit(repo)
    with pytest.raises(pk.ProtokollFehler, match="nach der Datensicht"):
        pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)


def test_vorpruefung_bindet_code_mechanik_und_arbeitsbaum(repo):
    log = _log(repo)
    with pytest.raises(pk.ProtokollFehler, match="Vorregistrierung fehlt"):
        pk.vorpruefung(pfad=log, root=repo, dateien=DATEIEN)
    pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    ok = pk.vorpruefung(pfad=log, root=repo, dateien=DATEIEN)
    assert ok["commit"] == _git(repo, "rev-parse", "HEAD") and set(ok["code"]) == set(DATEIEN)
    _schreiben(repo, "kit/b.py", "B = 9" + chr(10))                                          # nicht committet
    with pytest.raises(pk.ProtokollFehler, match="Code weicht"):
        pk.vorpruefung(pfad=log, root=repo, dateien=DATEIEN)
    _commit(repo)
    with pytest.raises(pk.ProtokollFehler, match="Code weicht"):                               # committet, aber nicht signiert
        pk.vorpruefung(pfad=log, root=repo, dateien=DATEIEN)
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    pk.aenderung_nach_sicht(["kit/b.py"], "Werkzeugkorrektur", DATUM, root=repo, pfad=log)
    assert pk.vorpruefung(pfad=log, root=repo, dateien=DATEIEN)["code"]["kit/b.py"] == pk.sha256_datei(repo / "kit/b.py")


def test_vollstaendigkeit_und_umschreiben(repo):
    log = _log(repo)
    assert pk.vollstaendigkeit(log, varianten_ids=["V1"]) == ["LEER"]
    pk.vorab("F-04", "OK", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    assert pk.vollstaendigkeit(log, varianten_ids=["V1"]) == ["DATENSICHT_FEHLT", "BEGINN_FEHLT:V1", "ERGEBNIS_FEHLT:V1"]
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    for phase in ("BEGINN", "ERGEBNIS"):
        pk.versuch("F04-ZIEL-STOP", "V1", DATUM, pfad=log, phase=phase, code=pk.code_hashes(DATEIEN, repo),
                   mechanik_hash=pk._mechanik_hash(repo))
    assert pk.vollstaendigkeit(log, varianten_ids=["V1"]) == [] and pk.pruefen(log, root=repo) == []
    _commit(repo)                                                                              # Protokoll committet
    roh = log.read_bytes()
    zeilen = roh.splitlines(keepends=True)
    log.write_bytes(b"".join(zeilen[:-1]))                                                     # letzte Zeile abgeschnitten
    assert any(b.startswith("UMGESCHRIEBEN") for b in pk.pruefen(log, root=repo))


# ---------------------------------------------------------------- Runde 2 (F-05): eigene Vorregistrierung, Familien, Werkzeug, Code
@pytest.fixture
def repo2(repo, monkeypatch) -> Path:
    _schreiben(repo, pk.PREREG_F05_REL, "# Vorregistrierung F-05 (Test)\n")
    monkeypatch.setattr(pk, "PREREG_F05_SHA", hashlib.sha256((repo / pk.PREREG_F05_REL).read_bytes()).hexdigest())
    _commit(repo)
    return repo


def test_runde_f05_eigene_werte_und_code_liste():
    r = pk.runde("F-05")
    assert r["familien"] == ("F05-META", "F05-DATEN") and r["werkzeug"] == "F05-WERKZEUG" and r["prereg_rel"] == "docs/bot/prereg/F05_ENTWURF.md"
    assert pk.runde("F-04")["familien"] == pk.FAMILIEN and pk.runde("TEST")["prereg_sha"] == pk.PREREG_SHA
    code = pk.CODE_F05
    assert len(set(code)) == len(code) and {"kit/strategy/meta_filter.py", "kit/research/meta.py", "forschung/meta_training.py",
                                            "forschung/runde2.py", "requirements/forschung.lock.txt", "kit/backtest/runner.py",
                                            "kit/research/protokoll.py"} <= set(code)
    assert all(not p.startswith("/") and "\\" not in p and ".." not in p for p in code)
    assert not set(pk.FAMILIEN) & set(pk.FAMILIEN_F05)


def _ok_f05() -> str:
    return f"PREREG-OK: ja für docs/bot/prereg/F05_ENTWURF.md, SHA-256 {pk.PREREG_F05_SHA}"


def test_neusignatur_nach_der_sicht_und_artefakte_der_ergebnisse(repo2):
    log = _log(repo2)
    pk.vorab("F-05", _ok_f05(), DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    pk.datensicht("F05-DATEN", "DATENSATZ", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    code, mech = pk.code_hashes(DATEIEN, repo2), pk._mechanik_hash(repo2)
    _schreiben(repo2, "berichte/forschung/b.json", "{}\n")
    _schreiben(repo2, "forschung/modelle/F05/M1.json", "{\"m\": 1}\n")
    _commit(repo2)
    sha_b, sha_m = pk.sha256_datei(repo2 / "berichte/forschung/b.json"), pk.sha256_datei(repo2 / "forschung/modelle/F05/M1.json")
    pk.versuch("F05-META", "M1", DATUM, pfad=log, phase="ERGEBNIS", code=code, mechanik_hash=mech, bericht="b.json", bericht_sha=sha_b,
               modell_datei="M1.json", modell_sha=sha_m)
    assert pk.pruefen(log, root=repo2) == []
    _schreiben(repo2, "forschung/modelle/F05/M1.json", "{\"m\": 2}\n")                    # Modell nachträglich verändert
    (repo2 / "berichte/forschung/b.json").unlink()                                       # Bericht entfernt
    befunde = pk.pruefen(log, root=repo2)
    assert "MODELL_ABWEICHUNG:3" in befunde and "BERICHT_FEHLT:3" in befunde
    _schreiben(repo2, "PUBLIC_SNAPSHOT.md", "x\n")                                       # öffentlicher Spiegel: Modelle fehlen dort
    (repo2 / "forschung/modelle/F05/M1.json").unlink()
    assert "MODELL_FEHLT:3" not in pk.pruefen(log, root=repo2)
    # neue Vorregistrierung derselben Familie nach der Sicht → Befund (nach der Sicht gilt die erste)
    pk.anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": DATUM, "family": "F05-DATEN", "lauf": "F-05",
                  "prereg_sha": pk.PREREG_F05_SHA, "commit": _git(repo2, "rev-parse", "HEAD"), "code": code}, log)
    assert "NEUSIGNATUR_NACH_SICHT:4" in pk.pruefen(log, root=repo2)


def test_code_f05_umfasst_alle_kit_module_des_ergebnispfads():
    """Jedes kit-Modul, das die Auswertung der Runde 2 lädt, steht in CODE_F05 oder in der Mechanik (mechanik_hash) – sonst könnte
    Code nach der Vorregistrierung unbemerkt geändert werden. Frischer Prozess, damit andere Tests sys.modules nicht vorbelegen."""
    import sys
    skript = ("import json, sys, kit.research.meta, kit.strategy.meta_filter, kit.research.protokoll;"
              "print(json.dumps(sorted(m.__file__ for n, m in sys.modules.items() if (n == 'kit' or n.startswith('kit.')) "
              "and getattr(m, '__file__', None))))")
    erg = subprocess.run([sys.executable, "-B", "-c", skript], cwd=pk.ROOT, capture_output=True, text=True, check=True)
    dateien = {Path(f).resolve().relative_to(pk.ROOT).as_posix() for f in json.loads(erg.stdout)}
    gedeckt = set(pk.CODE_F05) | set(pk.mechanik_dateien(pk.ROOT))
    assert dateien - gedeckt == set()


@pytest.mark.privat
def test_prereg_f05_hat_den_gepinnten_sha():
    assert pk.sha256_datei(pk.ROOT / pk.PREREG_F05_REL) == pk.PREREG_F05_SHA


def test_vorab_f05_neben_f04_beide_verifiziert(repo2):
    log = _log(repo2)
    vier = pk.vorab("F-04", "OK", DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    pk.datensicht("F04-DATEN", "ABZUG", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    with pytest.raises(pk.ProtokollFehler, match="ja"):                                  # Freigabe muss „ja“ und den SHA tragen
        pk.vorab("F-05", f"PREREG-OK: nein für {pk.PREREG_F05_SHA}", DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    with pytest.raises(pk.ProtokollFehler, match="ja"):
        pk.vorab("F-05", "PREREG-OK: ja", DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    fuenf = pk.vorab("F-05", _ok_f05(), DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    assert [e["body"]["family"] for e in fuenf] == list(pk.FAMILIEN_F05) and len(vier) == 3
    assert all(e["body"]["prereg_sha"] == pk.PREREG_F05_SHA and e["body"]["prereg_pfad"] == pk.PREREG_F05_REL for e in fuenf)
    assert pk.pruefen(log, root=repo2) == [] and pk.laeufe(log) == ["F-04", "F-05"]
    assert pk.vollstaendigkeit(log, lauf="F-05", varianten_ids=["M1"]) == ["DATENSICHT_FEHLT", "BEGINN_FEHLT:M1", "ERGEBNIS_FEHLT:M1"]
    pk.datensicht("F05-DATEN", "DATENSATZ", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    for phase in ("BEGINN", "ERGEBNIS"):
        pk.versuch("F05-META", "M1", DATUM, pfad=log, phase=phase, code=pk.code_hashes(DATEIEN, repo2), mechanik_hash=pk._mechanik_hash(repo2))
    assert pk.vollstaendigkeit(log, lauf="F-05", varianten_ids=["M1"]) == [] and pk.pruefen(log, root=repo2) == []
    assert pk.vorpruefung(pfad=log, root=repo2, lauf="F-05", dateien=DATEIEN)["prereg_sha"] == pk.PREREG_F05_SHA
    # gefälschte F-05-Vorregistrierung (falscher SHA) wird gemeldet, die F-04-Einträge bleiben gültig
    falsch = pk.anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": DATUM, "family": "F05-META", "lauf": "F-05",
                           "prereg_sha": "0" * 64, "commit": _git(repo2, "rev-parse", "HEAD"), "code": pk.code_hashes(DATEIEN, repo2)}, log)
    befunde = pk.pruefen(log, root=repo2)
    assert f"PREREG_SHA:{falsch['seq']}" in befunde and all(b.split(":")[1] == str(falsch["seq"]) for b in befunde)


@pytest.mark.parametrize("werkzeug_lauf", ["F-04", "F-05"])
def test_werkzeugaenderung_gilt_nur_im_eigenen_lauf(repo2, werkzeug_lauf):
    log = _log(repo2)
    pk.vorab("F-05", _ok_f05(), DATUM, root=repo2, pfad=log, dateien=DATEIEN)
    pk.datensicht("F05-DATEN", "DATENSATZ", "DEVELOPMENT", DATUM, {"x": "1"}, pfad=log)
    _schreiben(repo2, "kit/a.py", "A = 1  # korrigiert\n")
    _commit(repo2)
    w = pk.aenderung_nach_sicht(["kit/a.py"], "Werkzeugkorrektur", DATUM, root=repo2, pfad=log, lauf=werkzeug_lauf)
    assert w["body"]["family"] == pk.runde(werkzeug_lauf)["werkzeug"]
    v = pk.versuch("F05-META", "M1", DATUM, pfad=log, phase="BEGINN", code=pk.code_hashes(DATEIEN, repo2),
                   mechanik_hash=pk._mechanik_hash(repo2))
    assert pk.pruefen(log, root=repo2) == ([] if werkzeug_lauf == "F-05" else [f"CODE_ABWEICHUNG:{v['seq']}:kit/a.py"])
    if werkzeug_lauf == "F-05":
        assert pk.vorpruefung(pfad=log, root=repo2, lauf="F-05", dateien=DATEIEN)["code"]["kit/a.py"] == pk.sha256_datei(repo2 / "kit/a.py")
    else:
        with pytest.raises(pk.ProtokollFehler, match="Befunden"):
            pk.vorpruefung(pfad=log, root=repo2, lauf="F-05", dateien=DATEIEN)


# ---------------------------------------------------------------- Runde 3 (F-05b)
def test_runde_f05b_eigene_werte_und_code_liste():
    r = pk.runde("F-05b")
    assert r["familien"] == ("F05B-RICHTUNG", "F05B-DATEN") and r["werkzeug"] == "F05B-WERKZEUG"
    assert r["prereg_rel"] == "docs/bot/prereg/F05B_ENTWURF.md" and set(pk.CODE_F05) < set(pk.CODE_F05B)
    assert {"kit/strategy/richtung.py", "kit/research/richtung.py", "forschung/richtung_training.py", "forschung/runde3.py"} <= set(pk.CODE_F05B)
    assert len(set(pk.CODE_F05B)) == len(pk.CODE_F05B)
    assert not set(pk.FAMILIEN_F05B) & (set(pk.FAMILIEN) | set(pk.FAMILIEN_F05))


@pytest.mark.privat
def test_prereg_f05b_hat_den_gepinnten_sha():
    assert pk.sha256_datei(pk.ROOT / pk.PREREG_F05B_REL) == pk.PREREG_F05B_SHA


def test_vorab_f05b_braucht_ja_und_sha(repo, monkeypatch):
    _schreiben(repo, pk.PREREG_F05B_REL, "# Vorregistrierung F-05b (Test)\n")
    monkeypatch.setattr(pk, "PREREG_F05B_SHA", hashlib.sha256((repo / pk.PREREG_F05B_REL).read_bytes()).hexdigest())
    _commit(repo)
    log = _log(repo)
    with pytest.raises(pk.ProtokollFehler, match="ja"):
        pk.vorab("F-05b", f"PREREG-OK: nein für {pk.PREREG_F05B_SHA}", DATUM, root=repo, pfad=log, dateien=DATEIEN)
    e = pk.vorab("F-05b", f"PREREG-OK: ja für docs/bot/prereg/F05B_ENTWURF.md, SHA-256 {pk.PREREG_F05B_SHA}", DATUM, root=repo, pfad=log,
                 dateien=DATEIEN)
    assert [x["body"]["family"] for x in e] == list(pk.FAMILIEN_F05B) and pk.pruefen(log, root=repo) == []
    assert pk.laeufe(log) == ["F-05b"]


def test_code_f05b_umfasst_alle_kit_module_des_ergebnispfads():
    import sys
    skript = ("import json, sys, kit.research.richtung, kit.strategy.richtung;"
              "print(json.dumps(sorted(m.__file__ for n, m in sys.modules.items() if (n == 'kit' or n.startswith('kit.')) "
              "and getattr(m, '__file__', None))))")
    erg = subprocess.run([sys.executable, "-B", "-c", skript], cwd=pk.ROOT, capture_output=True, text=True, check=True)
    dateien = {Path(f).resolve().relative_to(pk.ROOT).as_posix() for f in json.loads(erg.stdout)}
    assert dateien - (set(pk.CODE_F05B) | set(pk.mechanik_dateien(pk.ROOT))) == set()
