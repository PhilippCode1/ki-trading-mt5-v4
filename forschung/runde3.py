"""Forschungsrunde 3 (F-05b, Richtungsmodell) – Aufruf nur in .venv-forschung (scikit-learn hash-gesperrt):

    .venv-forschung\\Scripts\\python.exe -m forschung.runde3 daten        [--datum JJJJ-MM-TT]
    .venv-forschung\\Scripts\\python.exe -m forschung.runde3 entwicklung  [--datum JJJJ-MM-TT] [--prozesse N]

Vorher `kit forschung vorab --lauf F-05b --prereg-ok "…"`; danach `kit forschung pruefen`. Datenzugriff, Prüfungen und Versuchsprotokoll
laufen über kit.research.richtung (Standardbibliothek); hier wird nur das Training (forschung.richtung_training) eingehängt.
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
    from kit.research import daten, protokoll, richtung

    ap = argparse.ArgumentParser(prog="python -m forschung.runde3", description="Forschungsrunde 3 (F-05b): Richtungsmodell")
    ap.add_argument("schritt", choices=["daten", "entwicklung"])
    ap.add_argument("--datum", help="Datum JJJJ-MM-TT (Standard: heute, UTC)")
    ap.add_argument("--prozesse", type=int, help="parallele Läufe des Takts (Standard: Kerne − 4)")
    a = ap.parse_args(argv)
    datum = a.datum or dt.datetime.now(dt.UTC).date().isoformat()
    try:
        if a.schritt == "daten":
            erg = richtung.daten_eintragen(datum=datum)
        else:
            from forschung import richtung_training
            erg = richtung.ausfuehren(datum=datum, trainer=richtung_training.trainieren, prozesse=a.prozesse)
    except (protokoll.ProtokollFehler, daten.DatenFehler, daten.HoldoutGesperrt, AblageFehler, FileExistsError) as exc:
        print(f"Nicht ausgeführt: {exc}")
        return 1
    print(json.dumps(erg, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
