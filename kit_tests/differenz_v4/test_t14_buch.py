"""Differenztest gegen das v4-Orakel T-14: Positionsbuch aus Broker-Deals (kit) = Orakel = SIM-Wahrheit."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from kit.broker.sim import SimTerminal
from kit.domain.types import Action, KontoModus, OrderRequest, Side
from kit.orders.reconcile import buch_aus_deals
from kit_tests.hilfen import eurusd
from kit_tests.orakel import t14_positions as t14

ROOT = Path(__file__).resolve().parents[2]
PINS = {"t14_positions.py": "7ab1850e8d3cfbddd760d2f8b29a49008b4f4d71f14ac764f92292859595b483",
        "t15_unknown.py": "d92f8672c442003e421ba04be3406ab208a5daa46f0f71ae37877a80a0a938e7"}

SCHRITT = st.tuples(st.sampled_from(["auf", "zu", "teil"]), st.sampled_from(["BUY", "SELL"]), st.integers(1, 40))


def _wahrheit(term: SimTerminal, modus: KontoModus) -> dict[str, Fraction]:
    out: dict[str, Fraction] = {}
    for p in term.positions():
        k = str(p.ticket) if modus is KontoModus.HEDGING else p.symbol
        out[k] = out.get(k, Fraction(0)) + Fraction(str(p.volume)) * p.side.sign
    return {k: v for k, v in out.items() if v}


def _lauf(modus: KontoModus, schritte) -> None:
    term = SimTerminal([eurusd()], modus=modus)
    term.setze_kurs("EURUSD", "1.10500", "1.10502")
    for art, seite, n in schritte:
        vol = Decimal(n) * Decimal("0.01")
        pos = term.positions()
        if art == "auf" or not pos:
            term.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side(seite), vol, magic=1))
        else:
            p = pos[0]
            menge = p.volume if art == "zu" else min(vol, p.volume)
            term.send(OrderRequest(Action.REDUCE_DEAL, "EURUSD", p.side.opposite, menge, magic=1, ticket=p.ticket))
    deals = term.deals(0, 2**62)
    kit = {k: Fraction(str(v)) for k, v in buch_aus_deals(modus, deals).items()}
    orakel = t14.reconstruct(str(modus), [{"deal_id": str(d.ticket), "symbol": d.symbol, "side": str(d.side), "qty": str(d.volume),
                                          "ticket": str(d.position_id)} for d in deals if d.side is not None])
    assert kit == orakel
    assert kit == _wahrheit(term, modus)


@settings(max_examples=300)
@given(st.lists(SCHRITT, max_size=30))
def test_hedging_buch_gleich_orakel(schritte):
    _lauf(KontoModus.HEDGING, schritte)


@settings(max_examples=300)
@given(st.lists(SCHRITT, max_size=30))
def test_netting_buch_gleich_orakel(schritte):
    _lauf(KontoModus.NETTING, schritte)


def test_orakel_kopien_sha_gepinnt():
    for name, sha in PINS.items():
        assert hashlib.sha256((ROOT / "kit_tests" / "orakel" / name).read_bytes()).hexdigest() == sha


def test_orakel_kopien_gleich_original():
    for name in PINS:
        assert (ROOT / "kit_tests" / "orakel" / name).read_bytes() == (ROOT / "referenz" / "oracles" / name).read_bytes()
