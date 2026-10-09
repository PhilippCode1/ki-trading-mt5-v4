"""Demo-Wächter und Live-Riegel (Plan F-1 §4, §6).

- Schreiben nur auf DEMO: Kontomodus DEMO, Konto in der Demo-Allowlist (nur HMAC-Abdruck), richtiges Terminal (falls konfiguriert).
- LIVE ist im Fast-Track hart gesperrt (live_pruefen wirft immer). Freischalten erst in L-01 – und nur durch den Betreiber.
- Die Allowlist liegt unter %LOCALAPPDATA%\\kit\\freigaben\\demo_konten.json; eintragen nur über `kit konto-registrieren`
  (nur bei Kontomodus DEMO).
"""
from __future__ import annotations

import json
from pathlib import Path

from kit.domain.types import HandelsModus


class LiveGesperrt(RuntimeError):
    """Der Live-Pfad ist gesperrt."""


def live_pruefen() -> None:
    raise LiveGesperrt("LIVE ist im Fast-Track hart gesperrt (Plan F-1 §6.2). Freischalten nur der Betreiber nach Tor 95 (L-01).")


def allowlist_pfad(freigaben: Path) -> Path:
    return Path(freigaben) / "demo_konten.json"


def allowlist_laden(freigaben: Path) -> set[str]:
    pfad = allowlist_pfad(freigaben)
    if not pfad.exists():
        return set()
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()                               # unlesbar = leer = nichts erlaubt (fail-closed)
    return {str(x) for x in daten.get("abdruecke", [])}


def konto_registrieren(terminal, freigaben: Path) -> str:
    konto = terminal.account()
    if konto.trade_mode is not HandelsModus.DEMO:
        raise LiveGesperrt(f"Nur DEMO-Konten können registriert werden (Konto ist {konto.trade_mode}).")
    if not konto.abdruck:
        raise LiveGesperrt("Kein Kontoabdruck verfügbar.")
    liste = allowlist_laden(freigaben) | {konto.abdruck}
    pfad = allowlist_pfad(freigaben)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"abdruecke": sorted(liste)}, indent=1), encoding="utf-8")
    return konto.abdruck


def demo_pruefung(terminal, freigaben: Path, *, terminal_daten_pfad: str | None = None):
    """Liefert eine Prüffunktion für den Lebenszyklus: None = senden erlaubt, sonst Grund (fail-closed)."""
    def pruefen() -> str | None:
        konto = terminal.account()
        if konto.trade_mode is not HandelsModus.DEMO:
            return f"Konto ist {konto.trade_mode}, nicht DEMO"
        if not konto.trade_allowed:
            return "Algo Trading/Handel am Terminal nicht freigegeben"
        if konto.abdruck not in allowlist_laden(freigaben):
            return "Demokonto nicht registriert (kit konto-registrieren)"
        if terminal_daten_pfad and getattr(terminal, "info", {}).get("data_path") != terminal_daten_pfad:
            return "Falsches Terminal (Datenpfad weicht ab)"
        return None
    return pruefen
