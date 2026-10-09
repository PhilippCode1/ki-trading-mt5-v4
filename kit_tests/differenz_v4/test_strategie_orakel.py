"""Gegenproben der F-04-Strategien gegen die öffentlichen v4-Orakel (nur synthetische Kerzen):
- S-BL-01 (kit/strategy/donchian_ref.py) = O-STR-2 tfd1 (oracles/tfd1_oracle.py), Selbsttest, Trennschärfe gegen sbase;
- Präfix-Invarianz nach T-09 (oracles/t09_causal.py, ≥ 200 feindliche Suffixe) für S-REV-01, S-REV-02 und S-BL-01,
  samt Mutation „Vorgriff“, die die Prüfung erkennen muss;
- privat: donchian_ref.run bitgleich zu reference/research/baseline.py."""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from decimal import Decimal

import pytest

from kit.domain.types import Bar
from kit.strategy import donchian_ref
from kit.strategy.donchian_ref import Kerze, Params
from kit.strategy.rev import Fehlausbruch, MittelwertRueckkehr, punkt, signale
from oracles import t09_causal, tfd1_oracle

TOL = 1e-9
SAATEN = [(11, 500), (12, 525), (13, 550), (14, 575), (15, 600), (16, 625), (17, 650), (18, 700)]
HALBE_SPREADS = (0.0, 0.01, 0.05)


def _kerzen(roh: list[dict]) -> list[Kerze]:
    return [Kerze(**d) for d in roh]


def _tupel(t: donchian_ref.Trade) -> tuple:
    return (t.direction, t.signal_bar, t.entry_bar, t.entry_price, t.exit_bar, t.exit_price, t.exit_reason)


def trade_abweichungen(unsere: list[tuple], andere: list[tuple], tol: float = TOL) -> list[str]:
    """Abweichungen zweier Trade-Listen (Richtung, Signal-, Einstiegs-, Ausstiegskerze, Grund exakt; Preise mit Toleranz)."""
    out = [f"Anzahl {len(unsere)} ≠ {len(andere)}"] if len(unsere) != len(andere) else []
    for i, (a, b) in enumerate(zip(unsere, andere, strict=False)):
        if (a[0], a[1], a[2], a[4], a[6]) != (b[0], b[1], b[2], b[4], b[6]):
            out.append(f"Trade {i}: {a} ≠ {b}")
        elif abs(a[3] - b[3]) > tol or abs(a[5] - b[5]) > tol:
            out.append(f"Trade {i}: Preise {a[3]}/{a[5]} ≠ {b[3]}/{b[5]}")
    return out


def _faelle() -> list[tuple[str, list[dict], float]]:
    faelle = [(f"saat{s}-hs{hs}", tfd1_oracle.make_bars(s, n, gap_rate=0.03, short_rate=0.02), hs) for s, n in SAATEN
              for hs in HALBE_SPREADS]
    faelle += [(f"luecklos-hs{hs}", tfd1_oracle.make_bars(99, 600), hs) for hs in HALBE_SPREADS]
    return faelle


# ------------------------------------------------------------------------------------------------ S-BL-01 gegen tfd1
def test_bl01_gleich_tfd1_orakel():
    gesamt = 0
    for name, roh, hs in _faelle():
        lauf = donchian_ref.run(_kerzen(roh), hs, Params())
        unsere = [_tupel(t) for t in lauf.trades]
        assert trade_abweichungen(unsere, tfd1_oracle.tfd1(roh, hs)) == [], name
        gesamt += len(unsere)
    assert gesamt >= 60, gesamt                       # Test ist nicht leer: genug Trades über alle Fälle


def test_bl01_selbsttest_handrechnung():
    lauf = donchian_ref.run(_kerzen(tfd1_oracle.selftest_bars()), 0.01, Params())
    t = (lauf.trades or [lauf.open_trade])[0]
    assert t is not None
    for feld, soll in tfd1_oracle.SELFTEST_EXPECT.items():
        assert getattr(t, feld) == pytest.approx(soll, abs=TOL), feld


def test_bl01_trennschaerfe_gegen_sbase():
    for s, n in SAATEN:
        roh = tfd1_oracle.make_bars(s, n, gap_rate=0.03, short_rate=0.02)
        unsere = [_tupel(t) for t in donchian_ref.run(_kerzen(roh), 0.0, Params()).trades]
        assert trade_abweichungen(unsere, tfd1_oracle.sbase(roh)) != [], s


# ------------------------------------------------------------------------------------------------ Präfix-Invarianz (T-09)
def praefix_verstoesse(werte: Callable[[list, int], object], praefix: list, suffixe: list[tuple[str, list]]) -> list[str]:
    """Namen der Suffixe, bei denen sich ein Wert bis zum Präfixende ändert. werte(kerzen, P) liefert alles, was nach Kerze P−1
    feststeht; es muss für Präfix+Suffix gleich dem Lauf nur auf dem Präfix sein."""
    p = len(praefix)
    soll = werte(praefix, p)
    return [name for name, suffix in suffixe if werte(praefix + suffix, p) != soll]


SYMBOL = "USDJPY"
SPANNE = Decimal("0.150")
T0 = 1_600_000_000 // 3600 * 3600
RB = 80                                             # kleinerer rueckblick nur für die Laufzeit dieses Tests
P_REV = RB + 120


def _rev_kerzen(werte: list[float | None], start: int, vor: Decimal | None) -> list[Bar]:
    """Preise → H1-Kerzen (Eröffnung = voriger Schluss, Hoch/Tief = max/min ± feste Spanne, Spread fest). Unbrauchbare Werte
    (None/NaN/inf/≤ 0/> 1e6) → Kerze entfällt (Lücke in der Zeitachse)."""
    p = punkt(SYMBOL)
    out: list[Bar] = []
    for i, v in enumerate(werte):
        if v is None or not math.isfinite(v) or v <= 0 or v > 1e6:
            continue
        c = Decimal(repr(v)).quantize(p)
        if c <= 0:
            continue
        o = c if vor is None else vor
        out.append(Bar(SYMBOL, T0 + 3600 * (start + i), o, max(o, c) + SPANNE, min(o, c) - SPANNE, c, 20))
        vor = c
    return out


def _rev_daten() -> tuple[list[Bar], list[tuple[str, list[Bar]]]]:
    preise = t09_causal.base_series(4711, P_REV)
    praefix = _rev_kerzen(preise, 0, None)
    suffixe = [(name, _rev_kerzen(werte, P_REV, praefix[-1].close)) for name, werte in t09_causal.suffixes(preise)]
    assert len(praefix) == P_REV and len(suffixe) >= t09_causal.MIN_SUFFIXES
    return praefix, suffixe


def _rev_werte(s) -> Callable[[list, int], object]:
    return lambda kerzen, p: signale(s, SYMBOL, kerzen)[:p]


def _rev_vorgriff(s) -> Callable[[list, int], object]:
    """Mutation: das Fenster reicht eine Kerze in die Zukunft (bars[i+1])."""
    rb = s.rueckblick
    return lambda kerzen, p: [s.signal(SYMBOL, kerzen[max(0, i - rb + 1):i + 2]) for i in range(len(kerzen))][:p]


@pytest.fixture(scope="module")
def rev_daten():
    return _rev_daten()


@pytest.mark.parametrize("strategie", [MittelwertRueckkehr(k=2.0, rueckblick=RB), Fehlausbruch(L=20, rueckblick=RB)],
                         ids=["S-REV-01", "S-REV-02"])
def test_praefix_invarianz_rev(rev_daten, strategie):
    praefix, suffixe = rev_daten
    assert sum(x is not None for x in signale(strategie, SYMBOL, praefix)) >= 2      # Präfix enthält Signale
    assert praefix_verstoesse(_rev_werte(strategie), praefix, suffixe) == []


def test_praefix_pruefung_erkennt_vorgriff(rev_daten):
    praefix, suffixe = rev_daten
    verstoesse = praefix_verstoesse(_rev_vorgriff(MittelwertRueckkehr(k=2.0, rueckblick=RB)), praefix, suffixe)
    assert verstoesse, "Mutation mit Vorgriff wurde nicht erkannt"
    assert any(n.startswith("jump-up-50") for n in verstoesse)


P_BL = 400
SPANNE_BL = 0.2


def _bl_kerzen(werte: list[float | None], vor: float | None) -> list[Kerze]:
    """Preise → D1-Kerzen; None/NaN/inf → ungültige Kerze (Index bleibt erhalten)."""
    out: list[Kerze] = []
    for v in werte:
        if v is None or not math.isfinite(v):
            nan = float("nan")
            out.append(Kerze(nan, nan, nan, nan, valid=False))
            continue
        o = v if vor is None else vor
        out.append(Kerze(max(o, v) + SPANNE_BL, min(o, v) - SPANNE_BL, v, o))
        vor = v
    return out


def _bl_werte(kerzen: list, p: int) -> object:
    lauf = donchian_ref.run(kerzen, 0.01, Params())
    return lauf.signals[:p], lauf.stops[:p], [dataclasses.astuple(t) for t in lauf.trades if t.exit_bar is not None and t.exit_bar < p]


def _bl_vorgriff(kerzen: list, p: int) -> object:
    """Mutation: Signal und Stopp der Kerze i aus der Kerze i+1."""
    lauf = donchian_ref.run(kerzen, 0.01, Params())
    return (lauf.signals[1:] + [0])[:p], (lauf.stops[1:] + [None])[:p]


def test_praefix_invarianz_bl01_und_vorgriff():
    preise = t09_causal.base_series(2028, P_BL, vol=1.0)
    praefix = _bl_kerzen(preise, None)
    suffixe = [(name, _bl_kerzen(werte, preise[-1])) for name, werte in t09_causal.suffixes(preise)]
    assert len(suffixe) >= t09_causal.MIN_SUFFIXES
    lauf = donchian_ref.run(praefix, 0.01, Params())
    assert len(lauf.trades) >= 2 and any(s != 0 for s in lauf.signals)                  # Präfix ist nicht trivial,
    assert lauf.open_trade is not None and lauf.open_trade.stop != lauf.open_trade.initial_stop  # am Ende offen und nachgeführt
    assert praefix_verstoesse(_bl_werte, praefix, suffixe) == []
    assert praefix_verstoesse(_bl_vorgriff, praefix, suffixe) != []


# ------------------------------------------------------------------------------------------------ privat: Referenzcode
@pytest.mark.privat
def test_bl01_bitgleich_referenz_baseline():
    from reference.research import baseline

    for name, roh, hs in _faelle():
        for modus in ("full_bar", "close_only"):
            unser = donchian_ref.run(_kerzen(roh), hs, Params(entry_bar_mode=modus))
            ref = baseline.run([baseline.Bar(**d) for d in roh], hs, baseline.Params(entry_bar_mode=modus))
            assert [dataclasses.astuple(t) for t in unser.trades] == [dataclasses.astuple(t) for t in ref.trades], (name, modus)
            assert unser.stops == ref.stops and unser.signals == ref.signals and unser.blocked == ref.blocked, (name, modus)
            offen = (unser.open_trade, ref.open_trade)
            assert (offen == (None, None)) or (None not in offen and dataclasses.astuple(offen[0]) == dataclasses.astuple(offen[1]))
