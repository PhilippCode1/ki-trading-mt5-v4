"""T-09-Orakel (kausale Strategie, R-01): adversariale Suffixe für die Präfixinvarianz und handrechenbare Fälle.

Unabhängig vom Referenzkern (nur Standardbibliothek, Fraction). Die Präfixinvarianz selbst ist metamorph: Für jedes Suffix
müssen alle Werte bis zum Präfixende bytegleich zum Lauf nur auf dem Präfix sein. Die Suffixe sind absichtlich feindlich
(D4-Entwurf §2.6: NaN, ±50-%-Sprünge, konstant, Nullvola, gespiegelt, Extremvola) und deterministisch erzeugt.
"""
from __future__ import annotations

import math
import random
from fractions import Fraction

MIN_SUFFIXES = 200


def suffixes(prefix: list[float], n_random: int = 160) -> list[tuple[str, list[float | None]]]:
    """Mindestens 200 feindliche Suffixe (Name, Werte). Längen 1…400, Werte bewusst extrem."""
    last = prefix[-1]
    out: list[tuple[str, list[float | None]]] = []
    for length in (1, 5, 60, 400):
        out += [
            (f"nan-{length}", [float("nan")] * length),
            (f"none-{length}", [None] * length),
            (f"jump-up-50-{length}", [last * 1.5] * length),
            (f"jump-down-50-{length}", [last * 0.5] * length),
            (f"constant-{length}", [last] * length),
            (f"zero-vol-zero-{length}", [0.0] * length),
            (f"mirrored-{length}", list(reversed(prefix))[:length]),
            (f"extreme-vol-{length}", [last * (10.0 if i % 2 else 0.1) for i in range(length)]),
            (f"alternating-{length}", [last + (1.0 if i % 2 else -1.0) * last * 0.2 for i in range(length)]),
            (f"trend-up-{length}", [last * (1 + 0.01 * (i + 1)) for i in range(length)]),
            (f"trend-down-{length}", [last * (1 - 0.002 * (i + 1)) for i in range(length)]),
        ]
    out.append(("spike-inf", [float("inf"), last]))
    out.append(("spike-neg", [-last * 100.0, last]))
    out.append(("huge", [1e300] * 10))
    out.append(("tiny", [1e-300] * 10))
    for seed in range(n_random):
        rng = random.Random(1000 + seed)
        length = rng.randint(1, 300)
        vol = last * rng.choice((0.0005, 0.005, 0.05, 0.5))
        p, seq = last, []
        for _ in range(length):
            p = p + rng.gauss(0.0, vol)
            seq.append(None if rng.random() < 0.02 else p)
        out.append((f"random-{seed}", seq))
    assert len(out) >= MIN_SUFFIXES, len(out)
    return out


def base_series(seed: int, n: int, start: float = 100.0, vol: float = 0.4) -> list[float]:
    """Deterministischer synthetischer Preispfad (Zufallsbewegung); keine Marktdaten."""
    rng = random.Random(seed)
    p, out = start, []
    for _ in range(n):
        p += rng.gauss(0.0, vol)
        out.append(p)
    return out


# --- Handfälle (exakt mit Fraction) -----------------------------------------------------------------------------------
def ewma_exact(xs: list[Fraction], span: int) -> list[Fraction]:
    a = Fraction(2, span + 1)
    out, s = [], None
    for x in xs:
        s = x if s is None else s + a * (x - s)
        out.append(s)
    return out


EWMA_CASES = [  # (Werte, span, erwartete EWMA)
    ([Fraction(1), Fraction(2), Fraction(3)], 3, [Fraction(1), Fraction(3, 2), Fraction(9, 4)]),
    ([Fraction(10), Fraction(10), Fraction(0)], 1, [Fraction(10), Fraction(10), Fraction(0)]),
    ([Fraction(4), Fraction(0)], 7, [Fraction(4), Fraction(3)]),
]


def vol_lag1_exact(prices: list[Fraction], span: int) -> list[float | None]:
    """v[t] = sqrt(EWMA(r²) über r[1..t−1]); r[t] = p[t] − p[t−1]."""
    rets = [None] + [prices[t] - prices[t - 1] for t in range(1, len(prices))]
    a = Fraction(2, span + 1)
    s, out = None, [None]
    for t in range(1, len(prices)):
        out.append(math.sqrt(s) if s is not None and s > 0 else None)  # nur r[..t−1]
        r = rets[t]
        s = r * r if s is None else s + a * (r * r - s)
    return out


def fdm_two(rho: Fraction, w1: Fraction = Fraction(1, 2), w2: Fraction = Fraction(1, 2), cap: float = 2.5) -> float:
    """FDM zweier Prognosen: 1/sqrt(wᵀCw) mit nichtnegativer Korrelation, gedeckelt."""
    r = max(rho, Fraction(0))
    var = w1 * w1 + w2 * w2 + 2 * w1 * w2 * r
    return min(cap, 1.0 / math.sqrt(var))


FDM_CASES = [(Fraction(1), 1.0), (Fraction(0), math.sqrt(2)), (Fraction(-1, 2), math.sqrt(2)), (Fraction(1, 2), 1 / math.sqrt(0.75))]

ROUND_CASES = [  # (q, lot_step, erwartet) – AG-2: bei Gleichstand Richtung 0 (geringeres Risiko)
    (2.5, 1.0, 2.0), (-2.5, 1.0, -2.0), (2.51, 1.0, 3.0), (0.5, 1.0, 0.0), (0.49, 1.0, 0.0), (0.07, 0.1, 0.1), (-0.05, 0.1, 0.0),
]

# O-STR-3: Ausführung zur Eröffnung t+1 zur Spreadseite; Stopp zum schlechteren Wert aus Stoppkurs und Eröffnungslücke
FILL_CASES = [  # (Menge, Eröffnung t+1, halber Spread, erwarteter Preis)
    (1.0, 100.0, 0.5, 100.5), (-3.0, 100.0, 0.5, 99.5), (2.0, 98.25, 0.0, 98.25),
]
STOP_CASES = [  # (long?, Stopp, Eröffnung, Tief, Hoch, erwarteter Fill)
    (True, 95.0, 90.0, 89.0, 92.0, 90.0),     # Lücke unter den Stopp: Fill zur Eröffnung (schlechter)
    (True, 95.0, 97.0, 94.0, 98.0, 95.0),     # Spanne erreicht den Stopp: Fill zum Stopp
    (True, 95.0, 97.0, 96.0, 98.0, None),     # nicht erreicht
    (False, 105.0, 110.0, 108.0, 111.0, 110.0),  # Short: Lücke über den Stopp
    (False, 105.0, 103.0, 102.0, 106.0, 105.0),
]
