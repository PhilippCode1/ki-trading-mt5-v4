"""Kerntests: feste Liste der Orakel- und Geldpfad-Testmodule der eingefrorenen Referenz (referenz/, weiter grün zu halten).

Die Liste ist bei 05d7adc (Tag konzept-c12-wip) nachweislich grün (seit F-03f 4.405 Tests, ~55 s mit Python 3.12). Seit F-03f liegt der
ganze Referenzblock geschlossen unter referenz/ (reference, oracles, registers, tests, validation, schemas, tools/regfmt.py,
docs/*_SPEC.md); pytest läuft dort, damit die relativen Pfade der eingefrorenen Module unverändert stimmen.
Aufruf mit dem Interpreter .venv-312 (Referenzinterpreter):

  .venv-312\\Scripts\\python.exe -B tools/kerntests.py            voll
  .venv-312\\Scripts\\python.exe -B tools/kerntests.py --schnell  ohne test_t09_causal (~10 s weniger)
  .venv-312\\Scripts\\python.exe -B tools/kerntests.py --liste    nur Modulliste ausgeben
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENZ = ROOT / "referenz"

MODULE = (
    # Geldpfad
    "test_moneypath_invariants", "test_c10_moneypath", "test_c11_mp_band_kill", "test_c11_mp_ptc_v3", "test_c12_b2_moneypath",
    "test_c12_ptc_quote_params", "test_t13_ptc", "test_t14_effects", "test_t15_t16", "test_tca", "test_retcodes",
    "test_killer_calendar", "test_c10_killer_gate",
    # Politik und Risiko
    "test_t01_leverage", "test_t02_band", "test_t02_coupled", "test_t04_ledger", "test_t06_gap", "test_worstcase",
    "test_construction", "test_c08_limits", "test_c08_policy", "test_c08_riskmetrics", "test_c10_scale_guard",
    "test_c12_construction_scale", "test_params_sealed",
    # Kosten und Marge
    "test_t05_margin", "test_t07_costs", "test_esma", "test_contracts",
    # Forschung
    "test_baseline_tfd1", "test_t09_causal", "test_research_stats", "test_research_core",
    # Struktur
    "test_oracle_independence",
)
SCHNELL_OHNE = {"test_t09_causal"}


def basetemp() -> Path:
    eigen = os.environ.get("KIT_PYTEST_BASETEMP")
    if eigen:
        return Path(eigen)
    return Path(tempfile.gettempdir()) / "kit-kern"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kerntests (Orakel/Geldpfad der Konzeptphase)")
    ap.add_argument("--schnell", action="store_true")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--ci", action="store_true", help="ohne Fortschrittsanzeige")
    a = ap.parse_args(argv)
    if not (REFERENZ / "tests").is_dir() and (ROOT / "PUBLIC_SNAPSHOT.md").is_file():
        print("Öffentlicher Spiegel: referenz/ ist hier nur auszugsweise enthalten; die Kerntests laufen im privaten Repo.")
        return 0
    module = [m for m in MODULE if not (a.schnell and m in SCHNELL_OHNE)]
    fehlend = [m for m in module if not (REFERENZ / "tests" / f"{m}.py").is_file()]
    if fehlend:
        print("Kerntests fehlen: " + ", ".join(fehlend), file=sys.stderr)
        return 2
    if a.liste:
        print("\n".join(module))
        return 0
    cmd = [sys.executable, "-B", "-m", "pytest", *[f"tests/{m}.py" for m in module], "-q", "-m", "not veraltung",
           "-p", "no:cacheprovider", f"--basetemp={basetemp()}"]
    if a.ci:
        cmd.append("--no-header")
    return subprocess.call(cmd, cwd=REFERENZ)


if __name__ == "__main__":
    raise SystemExit(main())
