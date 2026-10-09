"""Redigieren vor jedem Export (Plan F-1 §6.5): Der Agent sieht nur Kennzahlen, Quoten, Abstände und Zählungen.

Entfernt werden Schlüssel mit Kontokennungen oder Geldbeträgen; lange Ziffernfolgen (≥ 6 Stellen, z. B. Kontonummern,
Tickets) in Texten werden maskiert. Hashes (Hex-Zeichenketten) bleiben erhalten.
"""
from __future__ import annotations

import re

STAEMME = ("login", "passw", "server", "konto", "account", "investor", "email", "company", "firma", "balance", "equity", "margin",
           "profit", "geld", "anker", "betrag", "wert", "kapital", "kosten", "gebuehr", "swap", "abdruck", "pfad", "path", "saldo",
           "ergebnis", "provision", "commission")
ZIFFERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")
HASH = re.compile(r"[0-9a-f]{16,64}")


def _verboten(schluessel: str) -> bool:
    norm = re.sub(r"[_\-. ]", "", schluessel.lower())
    return norm in ("name", "ticket", "deal", "order", "positionid") or any(s in norm for s in STAEMME)


def redigieren(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: redigieren(v) for k, v in obj.items() if not _verboten(str(k))}
    if isinstance(obj, (list, tuple)):
        return [redigieren(v) for v in obj]
    if isinstance(obj, str):
        return obj if HASH.fullmatch(obj) else ZIFFERN.sub("######", obj)
    if isinstance(obj, int) and not isinstance(obj, bool) and abs(obj) >= 10**7:
        return "######"                                  # Kontonummern/Tickets als Zahl
    return obj
