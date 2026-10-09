"""Retcode-Semantik je Aktionsart (Daten: kit/daten/retcodes.json, Kopie von registers/retcodes.json).

Unbekannter Code → UNKNOWN (fail-closed: keine Freigabe, kein Neusenden ohne Negativnachweis).
Abweichung von v4: Code 0 („Done“ am MetaQuotes-Demo-Server) gilt nur mit Ticket und Volumen > 0 als DONE, sonst UNKNOWN.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from importlib import resources

from kit.domain.types import ZERO, Action

KLASSEN = ("DONE", "PARTIAL", "PLACED", "NOT_EXECUTED", "REJECT_FINAL", "UNKNOWN", "NOOP_OK", "RECONCILE")


@dataclass(frozen=True)
class Ergebnis:
    code: int
    klasse: str
    retry: str
    reservierung: str
    sperre: str | None      # SYMBOL, ACCOUNT oder None
    bekannt: bool


@lru_cache(maxsize=1)
def tabelle() -> dict[int, dict]:
    roh = resources.files("kit.daten").joinpath("retcodes.json").read_text(encoding="utf-8")
    return {c["code"]: c for c in json.loads(roh)["codes"]}


def einordnen(code: object, action: Action, *, ticket: int = 0, volumen: Decimal = ZERO) -> Ergebnis:
    if isinstance(code, bool) or not isinstance(code, int):
        return Ergebnis(-1, "UNKNOWN", "NUR_NACH_NEGATIVNACHWEIS", "BEHALTEN", None, False)
    if code == 0:
        if ticket and volumen > ZERO:       # SL/TP-Änderungen ohne Menge bestätigt der Abgleich über die Position
            return Ergebnis(0, "DONE", "KEINER", "VERBRAUCHEN", None, True)
        return Ergebnis(0, "UNKNOWN", "NUR_NACH_NEGATIVNACHWEIS", "BEHALTEN", None, True)
    eintrag = tabelle().get(code)
    if eintrag is None:
        return Ergebnis(code, "UNKNOWN", "NUR_NACH_NEGATIVNACHWEIS", "BEHALTEN", None, False)
    a = eintrag["actions"][str(action)]
    return Ergebnis(code, a["class"], a["retry"], a["reservation"], eintrag["block"], True)
