"""tools/publish.py: Säubern, Export/Ersetzen, Zielprüfung, Scratch-Autor, Hooks. Nur erfundene Werte."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import kit_scan
from tools import publish as pub

ROOT = Path(__file__).resolve().parents[1]
FREMDER_NAME = "Probe" + "kunde"
DOMAIN = "beispiel-firma" + ".example"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\nwork/\n.venv-*/\n*.pyc\n", encoding="utf-8")
    return repo


def test_aufraeumen_behaelt_work_und_venv(tmp_path):
    repo = _repo(tmp_path)
    for rel in ("kit/__pycache__/a.pyc", "work/c09/wichtig.json", ".venv-311/x/__pycache__/b.pyc", ".pytest_cache/v/x", "kit/a.py"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    weg = pub.aufraeumen(repo)
    assert "kit/__pycache__" in weg and ".pytest_cache" in weg
    assert (repo / "work/c09/wichtig.json").is_file()
    assert (repo / ".venv-311/x/__pycache__/b.pyc").is_file()
    assert (repo / "kit/a.py").is_file()


def test_export_positivliste_und_ersetzungen(tmp_path):
    repo = _repo(tmp_path)
    pfad = "C:" + "\\Users\\" + FREMDER_NAME + "\\Downloads"
    dateien = {
        "kit/a.py": f"# Pfad {pfad}\nURL = 'https://{DOMAIN}'\n",
        "docs/intern.md": "geheim intern\n",
        "kit_tests/privat/p.py": "x = 1\n",
        "README.md": "Hallo\n",
    }
    for rel, text in dateien.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    r = {"spiegel": {"positivliste": ["kit/**", "kit_tests/**", "README.md"], "ausschluss": ["kit_tests/privat/**"]}}
    liste = [kit_scan.Eintrag("benutzer", FREMDER_NAME, "Benutzer"), kit_scan.Eintrag("ersetzen", DOMAIN, "<website-domain>")]
    ziel = tmp_path / "export"
    zaehler = pub.exportieren(repo, ziel, r, liste)
    assert (ziel / "kit/a.py").is_file() and (ziel / "README.md").is_file()
    assert not (ziel / "docs/intern.md").exists() and not (ziel / "kit_tests/privat/p.py").exists()
    text = (ziel / "kit/a.py").read_text(encoding="utf-8")
    assert FREMDER_NAME not in text and DOMAIN not in text and "<website-domain>" in text
    assert zaehler.get("ersetzen") == 1
    assert pub.export_pruefen(ziel, liste) == []


def test_export_pruefen_findet_verbotenes(tmp_path):
    ziel = tmp_path / "export"
    ziel.mkdir()
    (ziel / "a.md").write_text("Das " + "Her" + "mes-System und 12.500" + " EU" + "R Startkapital\n", encoding="utf-8")
    (ziel / "b.md").write_text("Server " + DOMAIN + "\n", encoding="utf-8")
    fehler = pub.export_pruefen(ziel, [kit_scan.Eintrag("ersetzen", DOMAIN, "<x>")])
    assert any("a.md" in f for f in fehler) and any("b.md" in f for f in fehler)


def test_ziel_pruefen():
    r = {"spiegel": {"ziel": "x/y"}}
    assert pub.ziel_pruefen(r, lambda p: None)
    assert "privat" in pub.ziel_pruefen(r, lambda p: {"private": True, "size": 5})
    fremd = pub.ziel_pruefen(r, lambda p: {"private": False, "size": 5} if p == "repos/x/y" else None)
    assert fremd and "PUBLIC_SNAPSHOT" in fremd
    assert pub.ziel_pruefen(r, lambda p: {"private": False, "size": 5} if p == "repos/x/y" else {"name": "PUBLIC_SNAPSHOT.md"}) is None
    assert pub.ziel_pruefen(r, lambda p: {"private": False, "size": 0} if p == "repos/x/y" else None) is None


def test_gh_fehlt_ist_nicht_erreichbar(monkeypatch):
    def fehlt(*a, **k):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(pub.subprocess, "run", fehlt)
    assert pub.gh_get("repos/x/y") is None and pub.ziel_pruefen({"spiegel": {"ziel": "x/y"}}) is not None


def test_oeffentlich_ohne_gh_bricht_vor_dem_commit_ab(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "a")
    sp = {"privat_remote": "private", "privat_url": "https://example.invalid/privat.git", "url": "https://example.invalid/oeffentlich.git"}
    _git(repo, "remote", "add", "private", sp["privat_url"])
    _git(repo, "config", "core.hooksPath", ".githooks")
    monkeypatch.setattr(pub.kit_scan, "lade_sperrliste", lambda pfad: [("geheim", "x")])
    pub.pruefe_umgebung(repo, {"spiegel": sp}, False)                         # ohne --oeffentlich egal
    monkeypatch.setattr(pub.shutil, "which", lambda name: None)
    with pytest.raises(pub.Abbruch, match="GitHub CLI"):
        pub.pruefe_umgebung(repo, {"spiegel": sp}, True)


def test_scratch_commit_fester_autor(tmp_path):
    ziel = tmp_path / "scratch"
    ziel.mkdir()
    (ziel / "a.txt").write_text("a", encoding="utf-8")
    pub.scratch_commit(ziel, "Momentaufnahme")
    autor = subprocess.run(["git", "log", "-1", "--format=%an <%ae>"], cwd=ziel, capture_output=True, text=True, check=True).stdout.strip()
    assert autor == f"{pub.AGENT_NAME} <{pub.AGENT_MAIL}>"


@pytest.mark.privat
def test_hook_commit_msg_und_pre_push(tmp_path):
    gut = tmp_path / "gut.txt"
    gut.write_text("F-01: Geldpfad-Kern\n\n[EINGEFROREN-AENDERUNG: Test]\n\nCo-Authored-By: X <x@example.invalid>\n", encoding="utf-8")
    schlecht = tmp_path / "schlecht.txt"
    schlecht.write_text("irgendwas\n", encoding="utf-8")
    assert pub.hook(ROOT, "commit-msg", [str(gut)]) == 0
    assert pub.hook(ROOT, "commit-msg", [str(schlecht)]) == 1
    assert pub.hook(ROOT, "pre-push", ["oeff", "https://github.com/PhilippCode1/ki-trading-mt5-v4.git"]) == 1


def test_changelog_abschnitt(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# CHANGELOG\n\n## F-01 – Datum – T\n- a\n\n## F-00 – x\n- b\n", encoding="utf-8")
    assert pub.changelog_abschnitt(tmp_path, "F-01").endswith("- a")
    try:
        pub.changelog_abschnitt(tmp_path, "F-02")
    except pub.Abbruch as exc:
        assert exc.code == 1
    else:
        raise AssertionError("fehlender Abschnitt muss abbrechen")


def test_spiegel_regeln_halten_betreiberdaten_privat():
    """Seit F-03g ist fast alles öffentlich; privat bleiben die Betreiber-Sicherheitsnotizen, der Großteil von referenz/, die
    Kostenstartwerte und das Spreadprofil, die eingefrorenen Modelle (aus dem privaten Spread abgeleitet) und die lokalen Datensätze."""
    sp = pub.regeln(ROOT)["spiegel"]
    for privat in ("docs/bot/privat/SICHERHEIT_TODO.md", "referenz/registers/evidence.json", "referenz/README.md",
                   "config/kostenprofil/f04_startwerte.json", "config/kostenprofil/f04_spreadprofil.json",
                   "forschung/modelle/F05/F05-REV01-HGB.json", "work/f05/S-REV-01-k2.0-z0.75-r3.jsonl",
                   "forschung/modelle/F05B/F05B-REV01-HGB.json", "work/f05b/S-REV-02-L40-z0.5.jsonl"):
        assert not pub.passt(privat, sp["positivliste"]) or pub.passt(privat, sp["ausschluss"]), privat
    for oeffentlich in ("CLAUDE.md", "HANDOFF.md", "NEXT_PROMPT.md", "deploy/windows-vps/40_bot.ps1", "docs/bot/NOTFALL.md",
                        "kit_tests/differenz_v4/test_t14_buch.py", "referenz/oracles/t14_positions.py", ".github/workflows/ci.yml",
                        "forschung/versuchsprotokoll.jsonl", "berichte/forschung/2026-10-09_runde2.json", "kit/strategy/meta_filter.py"):
        assert pub.passt(oeffentlich, sp["positivliste"]) and not pub.passt(oeffentlich, sp["ausschluss"]), oeffentlich


def test_kerntests_im_spiegel_ohne_referenz_uebersprungen(tmp_path, monkeypatch, capsys):
    from tools import kerntests
    monkeypatch.setattr(kerntests, "ROOT", tmp_path)
    monkeypatch.setattr(kerntests, "REFERENZ", tmp_path / "referenz")
    assert kerntests.main(["--schnell"]) == 2                                   # privat: fehlende Referenz ist ein Fehler
    (tmp_path / "PUBLIC_SNAPSHOT.md").write_text("x", encoding="utf-8")
    assert kerntests.main(["--schnell"]) == 0                                   # Spiegel: Hinweis statt Fehler
    assert "privaten Repo" in capsys.readouterr().out
