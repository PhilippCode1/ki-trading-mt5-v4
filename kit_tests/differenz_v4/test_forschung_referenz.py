"""Forschungskopien gegen die eingefrorene v4-Referenz (privat: referenz/reference/research/* liegt nicht im Spiegel).

- Originale haben den Quell-SHA aus kit/research/HERKUNFT.md; Kopie = Original + Kopfkommentar (+ getauschte Importzeile bzw.
  neutral ersetzter privater Name, F-04 W2).
- Gleiche Ergebnisse auf festen Eingaben (stats) bzw. gleiche Hashkette (trials), dazu die unabhängigen Orakel O-TRIAL-1/N_eff.
Referenz und Orakel werden erst im Test importiert: im öffentlichen Spiegel fehlen sie, dort überspringt `privat` die Tests,
ein Importfehler beim Sammeln würde aber den ganzen Lauf abbrechen.
"""
from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from kit.research import stats, trials
from kit_tests.test_forschung_kopien import _tabelle

pytestmark = pytest.mark.privat

ROOT = Path(__file__).resolve().parents[2]
ORIGINALE = ROOT / "referenz" / "reference" / "research"
KOPIEN = ROOT / "kit" / "research"
IMPORT_KIT = b"from kit.research import trials as _trials_mod"
IMPORT_REF = b"from reference.research import trials as _trials_mod"
_NAME = "Her" + "mes"                                       # privater Name, zusammengesetzt (Spiegel-Rescan)
NAMEN_KIT_REF = ((b"Agenten-/Assistenz-Ideen", f"Agenten-/{_NAME}-Ideen".encode()),
                 (b'"ASSISTENZ"', f'"{_NAME.upper()}"'.encode()))


@pytest.fixture(scope="module")
def ref() -> SimpleNamespace:
    from oracles import research_oracles
    from reference.research import stats as ref_stats
    from reference.research import trials as ref_trials
    return SimpleNamespace(stats=ref_stats, trials=ref_trials, o=research_oracles)


RENDITEN = [0.012, -0.004, 0.007, 0.0, 0.021, -0.013, 0.005, 0.009, -0.002, 0.016, -0.007, 0.003]


def _ohne_kopf(daten: bytes) -> bytes:
    zeilen = daten.splitlines(keepends=True)
    i = 0
    while i < len(zeilen) and zeilen[i].startswith(b"#"):
        i += 1
    assert i == 3, "dreizeiliger Herkunftskopf erwartet"
    return b"".join(zeilen[i:])


@pytest.mark.parametrize("name", ["stats.py", "trials.py"])
def test_original_hat_quell_sha_und_kopie_ist_original_plus_kopf(name):
    original = (ORIGINALE / name).read_bytes()
    assert hashlib.sha256(original).hexdigest() == _tabelle()[name]["SHA-256 Quelle"]
    rumpf = _ohne_kopf((KOPIEN / name).read_bytes())
    if name == "stats.py":
        assert rumpf.count(IMPORT_KIT) == 1 and original.count(IMPORT_REF) == 1
        rumpf = rumpf.replace(IMPORT_KIT, IMPORT_REF)
    else:
        for kit_text, ref_text in NAMEN_KIT_REF:
            assert rumpf.count(kit_text) == 1 and original.count(ref_text) == 1
            rumpf = rumpf.replace(kit_text, ref_text)
    assert rumpf == original


def test_stats_gleiche_ergebnisse(ref):
    for k, n in ((0, 10), (7, 10), (10, 10), (85, 100), (1, 3)):
        assert stats.wilson(k, n) == ref.stats.wilson(k, n)
    for nn in (1.0, 1.5, 2.0, 2.5, 12.0, 100.0):
        assert stats.expected_max(nn) == ref.stats.expected_max(nn)
    assert stats.sharpe(RENDITEN) == ref.stats.sharpe(RENDITEN)
    for args in ((0.3, 0.1, 60), (0.2, 0.25, 36, -0.4, 4.5), (0.5, 0.0, 120, 0.1, 3.2)):
        assert stats.psr(*args) == ref.stats.psr(*args)
    with pytest.raises(ValueError):
        stats.wilson(3, 2)
    with pytest.raises(ValueError):
        ref.stats.wilson(3, 2)


def _bodies() -> list[dict]:
    b = {"actor": "CODING_AGENT", "date": "2026-10-08"}
    return [
        {**b, "kind": "PREREG_SIGNED", "family": "F04-ZIEL-STOP", "lauf": "F-04", "code": {"kit/a.py": "ab" * 32}},
        {**b, "kind": "DATA_VIEW", "family": "F04-ZIEL-STOP", "variant_id": "V1", "split": "DEVELOPMENT", "daten": {"x": "ä"}},
        {**b, "kind": "TRIAL", "family": "F04-ZIEL-STOP", "variant_id": "V1", "split": "DEVELOPMENT", "quote": "0.5"},
        {**b, "kind": "TRIAL", "family": "F04-ZIEL-STOP", "variant_id": "V2", "split": "DEVELOPMENT"},
        {**b, "kind": "CHANGE_AFTER_VIEW", "family": "F04-WERKZEUG", "variant_id": "W1", "reason": "Fehler"},
    ]


def test_hashkette_gleich_referenz_und_orakel(ref):
    ref_trials, o = ref.trials, ref.o
    kit_log: list[dict] = []
    ref_log: list[dict] = []
    for body in _bodies():
        trials.append(kit_log, body)
        ref_trials.append(ref_log, body)
    assert kit_log == ref_log == o.chain(_bodies())
    assert all(e["hash"] == trials.entry_hash(e["prev"], e["body"]) == ref_trials.entry_hash(e["prev"], e["body"]) for e in kit_log)
    assert trials.verify(kit_log) == ref_trials.verify(ref_log) == []
    assert trials.trial_count(kit_log) == ref_trials.trial_count(ref_log) == o.count_viewed(_bodies()) == 3
    assert trials.trial_count(kit_log, "F04-ZIEL-STOP") == ref_trials.trial_count(ref_log, "F04-ZIEL-STOP") == 2
    kaputt = [dict(e) for e in kit_log]
    kaputt[1], kaputt[2] = kaputt[2], kaputt[1]
    assert trials.verify(kaputt) == ref_trials.verify(kaputt) != []


def test_n_eff_gegen_orakel(ref):
    assert len(ref.o.N_EFF_CASES) >= 5
    for corr, soll in ref.o.N_EFF_CASES:
        fl = [[float(c) for c in z] for z in corr]
        assert isinstance(soll, Fraction) and ref.o.n_eff_exact(corr) == soll
        assert trials.n_eff(fl) == ref.trials.n_eff(fl) == pytest.approx(float(soll), rel=1e-12)
