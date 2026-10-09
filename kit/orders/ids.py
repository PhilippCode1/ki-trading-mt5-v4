"""Deterministische Auftragskennung und magic-Kodierung (Herkunft: mt5-trading-ai `kennmarke`).

Der magic-Wert ist das einzige Feld, das kein Server umschreibt; der Kommentar kann gekürzt oder ersetzt werden. Deshalb
trägt der magic-Wert Präfix, Namensraum und einen 44-Bit-Digest der client_order_id:
    magic = PRAEFIX << 48 | namensraum << 44 | digest44        (< 2**63)
"""
from __future__ import annotations

import hashlib

from kit.domain.types import Namensraum

PRAEFIX = 0x4B49                   # "KI"
_NS = {Namensraum.STRATEGIE: 1, Namensraum.PROBE: 2}
_NS_RUECK = {v: k for k, v in _NS.items()}
_MASKE44 = (1 << 44) - 1


def client_id(strategie: str, symbol: str, zeit: int, aktion: str, nummer: int = 0) -> str:
    """Stabil über Neustarts: dieselbe Absicht ergibt dieselbe Kennung (keine uuid4)."""
    roh = f"{strategie}|{symbol}|{zeit}|{aktion}|{nummer}"
    return "k" + hashlib.sha256(roh.encode("utf-8")).hexdigest()[:23]


def magic(namensraum: Namensraum, cid: str) -> int:
    digest = int(hashlib.sha256(cid.encode("utf-8")).hexdigest()[:11], 16) & _MASKE44
    return (PRAEFIX << 48) | (_NS[namensraum] << 44) | digest


def namensraum(magic_wert: int) -> Namensraum | None:
    """Namensraum eines eigenen magic-Werts, sonst None (fremd bzw. manuell)."""
    if magic_wert <= 0 or (magic_wert >> 48) != PRAEFIX:
        return None
    return _NS_RUECK.get((magic_wert >> 44) & 0xF)


def ist_eigen(magic_wert: int) -> bool:
    return namensraum(magic_wert) is not None


def kommentar(cid: str) -> str:
    """MT5-Kommentar höchstens 31 Zeichen."""
    return ("kit:" + cid)[:31]
