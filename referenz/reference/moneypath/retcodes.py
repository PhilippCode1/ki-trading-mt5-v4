"""Retcode-Semantik je Aktionsart (einzige Quelle: registers/retcodes.json). Unbekannter Code -> UNKNOWN (fail-closed)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reference.moneypath.types import Action

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Outcome:
    code: int
    klass: str          # DONE, PARTIAL, PLACED, NOT_EXECUTED, REJECT_FINAL, UNKNOWN, NOOP_OK, RECONCILE
    retry: str
    reservation: str
    block: str | None   # SYMBOL, ACCOUNT oder None
    known: bool


@lru_cache(maxsize=1)
def table() -> dict[int, dict]:
    data = json.loads((ROOT / "registers" / "retcodes.json").read_text(encoding="utf-8"))
    return {c["code"]: c for c in data["codes"]}


def outcome(code: object, action: Action) -> Outcome:
    """Semantik eines Rückgabecodes für eine Aktionsart; alles Unbekannte ist UNKNOWN (kein Freigeben, kein Neusenden)."""
    if not isinstance(code, int) or isinstance(code, bool) or code not in table():
        return Outcome(code if isinstance(code, int) else -1, "UNKNOWN", "NUR_NACH_NEGATIVNACHWEIS", "BEHALTEN", None, False)
    entry = table()[code]
    a = entry["actions"][str(action)]
    return Outcome(code, a["class"], a["retry"], a["reservation"], entry["block"], True)
