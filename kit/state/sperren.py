"""Dauerhafte Bot-Sperren (Plan F-1 §4, §6.3): im Journal (BOT_SPERRE/BOT_ENTSPERRT) und im Zustand – fail-closed gilt die
Vereinigung. Aufheben nur über `kit entsperren` mit der PIN des Betreibers (BOT_ENTSPERRT schreibt nur diese Funktion).

Stufen: K3 = eigene Positionen flach + keine Einstiege; K2 = keine Einstiege (Schutz läuft). K1 (STOP-Datei), Tagesstopp und
Technik-Pause sind vorübergehend und stehen nicht hier.
"""
from __future__ import annotations

from collections.abc import Iterable

K3_GRUENDE = frozenset({"K3", "LOSS_LOCK", "STOP50"})
GRUENDE = frozenset({"K2", "K3", "LOSS_LOCK", "STOP50", "STOP_OUT", "NULLTOLERANZ", "NICHT_DEMO"})


def aus_journal(saetze: Iterable[dict]) -> dict[str, dict]:
    aktiv: dict[str, dict] = {}
    for s in saetze:
        if s.get("art") == "BOT_SPERRE":
            aktiv.setdefault(s["code"], {"seq": s["seq"], "t": s["t"], "text": s.get("text", "")})
        elif s.get("art") == "BOT_ENTSPERRT":
            if s["code"] == "ALLE":
                aktiv.clear()
            else:
                aktiv.pop(s["code"], None)
    return aktiv


def symbol_sperren(saetze: Iterable[dict], jetzt: float) -> dict[str, str]:
    """Aktive Symbolsperren des Lebenszyklus (dauerhafte und noch laufende Retcode-Sperren) nach Aufhebungen durch den Betreiber."""
    dauerhaft: dict[str, list[str]] = {}
    zeitweise: dict[str, tuple[str, float]] = {}
    for s in saetze:
        d = s.get("daten", {})
        if s.get("art") == "SPERRE":
            if d.get("bis"):
                zeitweise[d["symbol"]] = (d["grund"], float(d["bis"]))
            elif d["grund"] not in dauerhaft.setdefault(d["symbol"], []):
                dauerhaft[d["symbol"]].append(d["grund"])
        elif s.get("art") == "BOT_ENTSPERRT":
            if s["code"] == "ALLE":
                dauerhaft.clear()
                zeitweise.clear()
            elif s["code"].startswith("SYMBOL:"):
                dauerhaft.pop(s["code"][7:], None)
                zeitweise.pop(s["code"][7:], None)
    aktiv = {sym: grund for sym, (grund, bis) in zeitweise.items() if jetzt < bis}
    return {**aktiv, **{sym: " + ".join(g) for sym, g in dauerhaft.items()}}     # dauerhafte Gründe gehen vor, alle sichtbar


def stufe(aktiv: Iterable[str]) -> int:
    gruende = set(aktiv)
    if gruende & K3_GRUENDE:
        return 3
    return 2 if gruende else 0


def letzte_entsperrung(saetze: Iterable[dict], grund: str) -> int:
    """seq der letzten Aufhebung dieses Grundes (oder ALLE); 0 = nie."""
    seq = 0
    for s in saetze:
        if s.get("art") == "BOT_ENTSPERRT" and s["code"] in (grund, "ALLE"):
            seq = int(s["seq"])
    return seq
