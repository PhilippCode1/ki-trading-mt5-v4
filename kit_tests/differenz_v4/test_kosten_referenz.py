"""Differenztest Kostenmodell kit/backtest/kosten.py gegen die eingefrorene Referenz referenz/reference/economics/costs.py
(Konventionen CT-CONV-SPREAD/CT-CONV-FX, Swap-Tagesfaktor). Privat: costs.py und registers/cost_truth.json liegen nicht im Spiegel.
Über alle FX-Produkte des Registers mit Kurswährung USD oder JPY (generisch, ohne Kontonamen)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit.backtest import kosten

pytestmark = pytest.mark.privat
D = Decimal
KURSE = {"EURUSD": D("1.10006"), "USDJPY": D("110.010")}


@pytest.fixture(scope="module")
def rc():
    from reference.economics import costs
    return costs


def _rt() -> dict[str, float]:
    eurjpy = kosten.kreuzkurs_eurjpy(KURSE)
    return {"EUR": 1.0, "USD": float(KURSE["EURUSD"]), "JPY": float(eurjpy)}


def test_swap_tagesfaktor_wie_referenz(rc):
    for dreifach in (2, 4):
        assert [kosten.swap_faktor(w, dreifach) for w in range(7)] == [rc.swap_day_factor(w, dreifach) for w in range(7)]


def test_umrechnung_wie_referenz(rc):
    rt = _rt()
    for ccy in ("USD", "JPY"):
        betrag = 1234.5
        assert abs(float(D(repr(betrag)) * kosten.eur_je_einheit(ccy, KURSE)) - rc.to_eur(betrag, ccy, rt, 0.0)) < 1e-9


@pytest.mark.parametrize("fx_gebuehr", ["0", "0.003"])
def test_seitenkosten_wie_referenz_ueber_das_register(rc, fx_gebuehr):
    rt = _rt()
    geprueft = 0
    for p in rc.products():
        if not p["symbol_id"].startswith("SYM-CFD-") or p.get("quote_ccy") not in ("USD", "JPY"):
            continue
        tick = D(str(p["tick_size"]["value"]))
        spread = D(str(p["spread"]["value"]))
        tv_kurs = tick * D(100000)                                          # Tickwert je Lot in Kurswährung (Kontrakt 100.000)
        pc = rc.ProductCost(cost_id=p["id"], account_id="A", symbol_id=p["symbol_id"], variant="V", product_class="CFD",
                            account_ccy="EUR", quote_ccy=p["quote_ccy"], unit_ccy=p["quote_ccy"], contract_size=100000.0,
                            price_factor=1.0, tick_size=float(tick), tick_value=float(tv_kurs), spread=float(spread),
                            spread_factor={s: 1.0 for s in rc.SESSIONS}, slip_ticks={s: 0.0 for s in rc.SESSIONS},
                            fees=(("commission", 3.25, "EUR"),), fx_fee=float(fx_gebuehr), swap_markup_pa=0.0, swap_day_count=365,
                            triple_weekday=2, roll_spread_ticks=0.0, rolls_per_year=0.0, liquidation_fee_eur=0.0, margin_rate=0.0,
                            close_out_level=None, statuses=())
        tv_eur = tv_kurs * kosten.eur_je_einheit(p["quote_ccy"], KURSE)        # ungerundet wie die Referenz
        for lots in (D("0.01"), D("0.53"), D("2.40")):
            kit_wert = kosten.seitenkosten(spread, tick, tv_eur, lots, D("3.25"), D(fx_gebuehr))
            ref_wert = rc.side_cost_eur(pc, float(lots), "REGULAR", rt)
            assert abs(float(kit_wert) - ref_wert) <= 1e-9 * max(1.0, ref_wert), (p["id"], lots)
            assert abs(float(kosten.rundreise(spread, tick, tv_eur, lots, D("3.25"), D(fx_gebuehr))) -
                       rc.round_trip_cost_eur(pc, float(lots), rt)) <= 1e-9 * max(1.0, ref_wert)
        geprueft += 1
    assert geprueft >= 7
