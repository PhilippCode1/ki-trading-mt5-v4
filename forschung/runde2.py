"""Forschungsrunde 2 (F-05, KI-Meta-Filter) – Aufruf nur in .venv-forschung (scikit-learn hash-gesperrt):

    .venv-forschung\\Scripts\\python.exe -m forschung.runde2 daten        [--datum JJJJ-MM-TT]
    .venv-forschung\\Scripts\\python.exe -m forschung.runde2 entwicklung  [--datum JJJJ-MM-TT] [--prozesse N]

Vorher `kit forschung vorab --lauf F-05 --prereg-ok "…"`; danach `kit forschung pruefen`. Datenzugriff, Prüfungen und Versuchsprotokoll
laufen über kit.research.meta (Standardbibliothek); hier wird nur das Training (forschung.meta_training) eingehängt.
Liest nur die Entwicklungskerzen der F-04-Datensicht, nie den Holdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys


def main(argv: list[str] | None = None) -> int:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    from kit.paths import AblageFehler
    from kit.research import daten, meta, protokoll

    ap = argparse.ArgumentParser(prog="python -m forschung.runde2", description="Forschungsrunde 2 (F-05): KI-Meta-Filter")
    ap.add_argument("schritt", choices=["daten", "entwicklung"])
    ap.add_argument("--datum", help="Datum JJJJ-MM-TT (Standard: heute, UTC)")
    ap.add_argument("--prozesse", type=int, help="parallele Läufe des Takts (Standard: Kerne − 4)")
    a = ap.parse_args(argv)
    datum = a.datum or dt.datetime.now(dt.UTC).date().isoformat()
    try:
        if a.schritt == "daten":
            erg = meta.daten_eintragen(datum=datum)
        else:
            from forschung import meta_training
            erg = meta.ausfuehren(datum=datum, trainer=meta_training.trainieren, prozesse=a.prozesse)
    except (protokoll.ProtokollFehler, daten.DatenFehler, daten.HoldoutGesperrt, AblageFehler, FileExistsError) as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1
    print(json.dumps(erg, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
