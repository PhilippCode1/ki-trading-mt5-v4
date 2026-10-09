"""Retcode-Matrix 41 × 5: kit-Einordnung = v4-Referenz (reference/moneypath/retcodes.py), bis auf dokumentierte Abweichungen."""
from __future__ import annotations

from decimal import Decimal

from kit.domain.types import Action
from kit.orders.retcodes import einordnen, tabelle


def test_matrix_gleich_referenz():
    from reference.moneypath import retcodes as ref
    from reference.moneypath.types import Action as RefAction

    assert len(tabelle()) == 41
    for code in tabelle():
        for a in Action:
            kit = einordnen(code, a, ticket=1, volumen=Decimal("0.10"))
            v4 = ref.outcome(code, RefAction(str(a)))
            assert (kit.klasse, kit.retry, kit.reservierung, kit.sperre) == (v4.klass, v4.retry, v4.reservation, v4.block), (code, a)
    for a in Action:
        assert einordnen(99999, a).klasse == ref.outcome(99999, RefAction(str(a))).klass == "UNKNOWN"
