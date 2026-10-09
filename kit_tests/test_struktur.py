"""Strukturregeln des Fast-Track (Plan F-1 §4, §6)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUSGENOMMEN = {".git", "work", ".uv-cache", ".hypothesis", ".ruff_cache", "__pycache__", ".pytest_cache", "node_modules"}
VERBOTENE_IMPORTE = ("reference", "oracles", "validation", "tools", "tests")
MT5_ERLAUBT = {"kit/broker/mt5_real.py"}


def _dateien(name: str) -> list[Path]:
    treffer = []
    stapel = [ROOT]
    while stapel:
        ordner = stapel.pop()
        for p in ordner.iterdir():
            if p.is_dir():
                if p.name in AUSGENOMMEN or p.name.startswith(".venv"):
                    continue
                stapel.append(p)
            elif p.name == name:
                treffer.append(p)
    return treffer


def _importe(pfad: Path) -> set[str]:
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    namen: set[str] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            namen |= {a.name.split(".")[0] for a in knoten.names}
        elif isinstance(knoten, ast.ImportFrom) and knoten.module and knoten.level == 0:
            namen.add(knoten.module.split(".")[0])
    return namen


def test_keine_regeldatei_ausserhalb_der_wurzel():
    for name in ("CLAUDE.md", "AGENTS.md"):
        fremd = [p.relative_to(ROOT).as_posix() for p in _dateien(name) if p.parent != ROOT]
        assert fremd == [], f"{name} außerhalb der Wurzel würde alte Regeln nachladen: {fremd}"
    assert (ROOT / "CLAUDE.md").is_file()


def test_kit_importiert_keinen_konzeptbestand():
    for pfad in (ROOT / "kit").rglob("*.py"):
        verboten = _importe(pfad) & set(VERBOTENE_IMPORTE)
        assert not verboten, f"{pfad.relative_to(ROOT)} importiert {sorted(verboten)}"


def test_metatrader5_nur_im_adapter():
    for pfad in (ROOT / "kit").rglob("*.py"):
        rel = pfad.relative_to(ROOT).as_posix()
        if "MetaTrader5" in _importe(pfad):
            assert rel in MT5_ERLAUBT, f"{rel} importiert MetaTrader5"


def test_waechter_hook_ist_fail_closed_eingetragen():
    einst = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    eintraege = einst["hooks"]["PreToolUse"]
    assert any(e.get("matcher") == "*" for e in eintraege)
    befehle = [h["command"] for e in eintraege for h in e["hooks"]]
    assert any("agent_waechter.py" in b and b.rstrip().endswith("|| exit 2") for b in befehle)
    assert "|| true" not in json.dumps(einst)
    deny = einst["permissions"]["deny"]
    assert any("live_freigabe.json" in d for d in deny)
    assert any("MetaQuotes" in d for d in deny)


@pytest.mark.privat
def test_referenz_geschlossen_und_konzeptballast_entfernt():
    """Seit F-03f: eingefrorene Referenz nur unter referenz/; Konzeptphase nur noch in den Tags konzept-c11-gruen/-c12-wip."""
    assert (ROOT / "referenz" / "README.md").is_file()
    for alt in ("reference", "oracles", "registers", "tests", "validation", "schemas", "evidence", "archiv", "review",
                "scorecards", "upstream"):
        assert not (ROOT / alt).exists(), f"{alt}/ gehört nach referenz/ bzw. in die Konzept-Tags"
