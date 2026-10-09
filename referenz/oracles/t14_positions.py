"""T-14 Orderwirkungen: Positionen und Cash unabhängig aus Broker-Deals rekonstruieren (Fraction, nur Standardbibliothek).

Buchungsregeln (MQL5-Positionsführung, Plan §8 K8), eigenständig implementiert:
  NETTING/EXCHANGE: je Symbol eine Nettomenge; Summe aller vorzeichenbehafteten Deals (IN, OUT, INOUT).
  HEDGING:          je Positions-ID (ticket) eine Menge; IN eröffnet/erhöht das Ticket, OUT/OUT_BY vermindert es.
  Cash:             Summe der Deal-Cashbeträge; Gebühren: Summe der Deal-Gebühren.
Rückgabe: {schlüssel: menge} ohne Nullpositionen (Schlüssel = Symbol bei Netting, Ticket bei Hedging).
"""
from __future__ import annotations

from fractions import Fraction as F


def _signed(deal: dict) -> F:
    q = F(str(deal["qty"]))
    return q if deal["side"] == "BUY" else -q


def reconstruct(mode: str, deals: list[dict]) -> dict[str, F]:
    seen: set[str] = set()
    book: dict[str, F] = {}
    for d in deals:
        if d["deal_id"] in seen:
            continue
        seen.add(d["deal_id"])
        key = d["symbol"] if mode in ("NETTING", "EXCHANGE") else d["ticket"]
        book[key] = book.get(key, F(0)) + _signed(d)
    return {k: v for k, v in book.items() if v != 0}


def net_by_symbol(mode: str, deals: list[dict]) -> dict[str, F]:
    seen: set[str] = set()
    out: dict[str, F] = {}
    for d in deals:
        if d["deal_id"] in seen:
            continue
        seen.add(d["deal_id"])
        out[d["symbol"]] = out.get(d["symbol"], F(0)) + _signed(d)
    return {k: v for k, v in out.items() if v != 0}


def cash(deals: list[dict]) -> F:
    return sum((F(str(d.get("cash", "0"))) for d in {d["deal_id"]: d for d in deals}.values()), F(0))


def fees(deals: list[dict]) -> F:
    return sum((F(str(d.get("fee", "0"))) for d in {d["deal_id"]: d for d in deals}.values()), F(0))


def reversal_deals(deals: list[dict]) -> list[str]:
    """Deals, die eine Nettoposition über null hinweg umkehren (unabhängig vom gemeldeten entry-Feld)."""
    pos: dict[str, F] = {}
    out = []
    for d in deals:
        before = pos.get(d["symbol"], F(0))
        after = before + _signed(d)
        if before != 0 and after != 0 and (before > 0) != (after > 0):
            out.append(d["deal_id"])
        pos[d["symbol"]] = after
    return out
