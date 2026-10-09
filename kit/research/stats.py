# Herkunft: referenz/reference/research/stats.py (v4-Referenz, Tag konzept-c12-wip), SHA-256
# d1cab5a9f49ec6bb8bfce6ec59dd550a9aa54ea4cbc9703f228c5020b1feb3ce. Unverändert bis auf die Importzeile
# (reference.research → kit.research) und diesen Kopf; Pin in kit/research/HERKUNFT.md (F-04).
"""Statistikrechner der Forschungstore (MP §9.C1, Plan §10, C-06; Formeln in registers/formulas.json FORM-061…068).

Eine Versuchszahl: DSR und OC lesen N und N_eff ausschließlich aus reference/research/trials.dsr_trials (bzw. aus
trials.n_eff derselben Korrelationsmatrix); das Maximum wird über dieselben Versuche gebildet, die der Deflator zählt.
Alle SR-Größen sind je Periode (z. B. Monat), sofern nicht „ann“ im Namen steht. Nur Standardbibliothek (ADR-C06-001).

- PSR/DSR (Bailey/López de Prado 2014): PSR(SR0) = Φ((SR − SR0)·√(T−1)/√(1 − γ3·SR + (γ4−1)/4·SR²)),
  SR0 = √V·E[max_{N_eff}] mit E[max_n] ≈ (1−γ)Φ⁻¹(1−1/n) + γΦ⁻¹(1−1/(n·e)) für n ≥ 2 und exakt ∫x·nφΦ^{n−1} für 1 ≤ n < 2.
  V = max(Querschnittsvarianz der Versuchs-SR, Stichprobenvarianz 1/(T−1) unter der Nullhypothese) – strengere Variante:
  die Querschnittsvarianz korrelierter Versuche unterschätzt sonst die Streuung des Maximums.
- SE der SR: IID (Mertens/Lo) und GMM-Delta-Methode mit Newey-West (Lo 2002); η(q) für die Zeitaggregation.
- PBO/CSCV (Bailey/Borwein/López de Prado/Zhu 2017) mit Blocksummen; optional deterministische Teilmenge der Kombinationen.
- Stationärer Bootstrap (Politis/Romano 1994), Blocklänge nach Politis/White (2004) mit Korrektur Patton/Politis/White (2009).
- SPA (Hansen 2005; konsistente, untere und obere p-Werte) und Romano-Wolf StepM (2005), studentisiert mit Bootstrap-Varianz.
- Nichtlinearer Mehrfachtest-Abschlag (Harvey/Liu 2015): Bonferroni, Šidák, Holm und BHY mit m = N_eff.
"""
from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from statistics import NormalDist

from kit.research import trials as _trials_mod  # nur hashlib/json, kein Zyklus

EULER_GAMMA = 0.5772156649015329
_N01 = NormalDist()


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("p muss in (0, 1) liegen")
    return _N01.inv_cdf(p)


# ---------------------------------------------------------------- Momente und Sharpe
def _finite(r: Sequence[float]) -> list[float]:
    xs = [float(x) for x in r]
    if len(xs) < 3 or any(not math.isfinite(x) for x in xs):
        raise ValueError("mindestens 3 endliche Beobachtungen nötig")
    return xs


def sharpe(r: Sequence[float]) -> float:
    """Mittel / Stichproben-Standardabweichung (ddof = 1); keine Streuung -> Fehler (fail-closed)."""
    xs = _finite(r)
    n = len(xs)
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    if var <= 0.0:
        raise ValueError("Reihe ohne Streuung")
    return mu / math.sqrt(var)


def moments(r: Sequence[float]) -> dict[str, float]:
    """Schiefe γ3 und Kurtosis γ4 (nicht Exzess) aus Populationsmomenten, wie in der PSR-Formel verwendet."""
    xs = _finite(r)
    n = len(xs)
    mu = sum(xs) / n
    m2 = sum((x - mu) ** 2 for x in xs) / n
    if m2 <= 0.0:
        raise ValueError("Reihe ohne Streuung")
    m3 = sum((x - mu) ** 3 for x in xs) / n
    m4 = sum((x - mu) ** 4 for x in xs) / n
    return {"skew": m3 / m2 ** 1.5, "kurt": m4 / m2 ** 2}


def sr_se_iid(sr: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    arg = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if n_obs < 3 or arg <= 0.0:
        raise ValueError("SE nicht bestimmbar")
    return math.sqrt(arg / (n_obs - 1))


def newey_west_lags(n: int) -> int:
    """Standardwahl floor(4·(n/100)^(2/9)) (Newey/West 1994)."""
    return int(4.0 * (n / 100.0) ** (2.0 / 9.0))


def sr_se_hac(r: Sequence[float], lags: int | None = None) -> float:
    """SE der SR je Periode nach Lo (2002) mit GMM-Delta-Methode und Newey-West-Bartlett-Gewichten (serielle Korrelation)."""
    xs = _finite(r)
    n = len(xs)
    lags = newey_west_lags(n) if lags is None else lags
    if not 0 <= lags < n:
        raise ValueError("ungültige Lag-Zahl")
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / n
    if var <= 0.0:
        raise ValueError("Reihe ohne Streuung")
    sd = math.sqrt(var)
    u1 = [x - mu for x in xs]
    u2 = [(x - mu) ** 2 - var for x in xs]
    g1, g2 = 1.0 / sd, -mu / (2.0 * sd ** 3)
    # gᵀΩg = Σ_j w_j·(Γ_j + Γ_jᵀ) projiziert: mit v_t = g1·u1_t + g2·u2_t ist gᵀΓ_j g = (1/n)Σ v_t v_{t−j}
    v = [g1 * a + g2 * b for a, b in zip(u1, u2, strict=True)]
    omega = sum(x * x for x in v) / n
    for j in range(1, lags + 1):
        w = 1.0 - j / (lags + 1.0)
        omega += 2.0 * w * sum(v[t] * v[t - j] for t in range(j, n)) / n
    return math.sqrt(max(omega, 0.0) / n)


def lo_eta(rhos: Sequence[float], q: int) -> float:
    """Faktor η(q) der Zeitaggregation nach Lo (2002): SR(q) = η(q)·SR mit Autokorrelationen ρ_1…ρ_{q−1}."""
    if q < 1 or len(rhos) < q - 1 or any(not (math.isfinite(r) and -1.0 <= r <= 1.0) for r in rhos[: q - 1]):
        raise ValueError("q >= 1 und mindestens q − 1 Autokorrelationen in [−1, 1] nötig (fail-closed)")
    s = q + 2.0 * sum((q - k) * rhos[k - 1] for k in range(1, q))
    if not s > 0.0:
        raise ValueError("Autokorrelationen unzulässig")
    return q / math.sqrt(s)


# ---------------------------------------------------------------- erwartetes Maximum, PSR, DSR
def expected_max_exact(n: float, steps: int = 800) -> float:
    """E[max von n unabhängigen N(0,1)] für reelles n ≥ 1: ∫ x·n·φ(x)·Φ(x)^{n−1} dx (Simpson auf [−10, 10])."""
    if n < 1.0:
        raise ValueError("n >= 1 nötig")
    if n == 1.0:
        return 0.0
    a, b = -10.0, 10.0
    h = (b - a) / steps
    tot = 0.0
    for i in range(steps + 1):
        x = a + i * h
        w = 1 if i in (0, steps) else (4 if i % 2 else 2)
        tot += w * x * n * norm_pdf(x) * norm_cdf(x) ** (n - 1.0)
    return tot * h / 3.0


def blp_expected_max(n: float) -> float:
    """Näherung Bailey/López de Prado (2014), definiert für n >= 2."""
    if n < 2.0:
        raise ValueError("BLP-Näherung erst ab n >= 2")
    return (1.0 - EULER_GAMMA) * norm_ppf(1.0 - 1.0 / n) + EULER_GAMMA * norm_ppf(1.0 - 1.0 / (n * math.e))


def expected_max(n: float) -> float:
    """E[max_n] für die DSR (standardnormal): exakte Integration für 1 <= n < 2, sonst max(exakt, Bailey/López de Prado).
    Strengere Variante (C-06, Prüfbefund S-01): die BLP-Näherung liegt für 2 <= n < ≈ 2,7 unter dem exakten Wert – so bleibt der
    Deflator stetig und monoton in N_eff (mehr effektive Versuche nie mildere Hürde)."""
    if not (math.isfinite(n) and n >= 1.0):
        raise ValueError("N_eff >= 1 nötig")
    exact = expected_max_exact(n)
    return exact if n < 2.0 else max(exact, blp_expected_max(n))


def psr(sr: float, sr0: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    arg = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if n_obs < 3 or arg <= 0.0:
        raise ValueError("PSR nicht bestimmbar")
    return norm_cdf((sr - sr0) * math.sqrt(n_obs - 1) / math.sqrt(arg))


def check_trials(trials: Mapping) -> tuple[int, float]:
    """Nur die Ausgabe von trials.dsr_trials (Typ TrialCount) ist zulässig: N int >= 1, 1 <= N_eff <= N (INT-08)."""
    if not isinstance(trials, _trials_mod.TrialCount) or not (isinstance(trials.scope, str) and trials.scope):
        raise ValueError("Versuchszahl nur aus trials.dsr_trials (TrialCount mit Geltungsbereich)")
    n, ne = trials.get("N"), trials.get("N_eff")
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= 1 and isinstance(ne, (int, float))
            and not isinstance(ne, bool) and math.isfinite(ne) and 1.0 <= ne <= n + 1e-9):
        raise ValueError("Versuchszahl nur aus trials.dsr_trials (N >= 1, 1 <= N_eff <= N)")
    return n, float(ne)


def dsr(best: Sequence[float], trials: Mapping, trial_srs: Sequence[float] | None = None) -> dict:
    """Deflated Sharpe Ratio der besten Variante. Deflator SR0 mit N_eff derselben Versuche (eine Versuchszahl)."""
    n_trials, n_eff = check_trials(trials)
    xs = _finite(best)
    t = len(xs)
    sr = sharpe(xs)
    m = moments(xs)
    v_null = 1.0 / (t - 1)
    v_cross = None
    if trial_srs is not None:
        if len(trial_srs) != n_trials or any(not math.isfinite(s) for s in trial_srs):
            raise ValueError("trial_srs muss genau N endliche Versuchs-SR enthalten")
        if n_trials >= 2:
            mean_sr = sum(trial_srs) / n_trials
            v_cross = sum((s - mean_sr) ** 2 for s in trial_srs) / (n_trials - 1)
    v = max(v_null, v_cross or 0.0)
    sr0 = math.sqrt(v) * expected_max(n_eff)
    return {"sr": sr, "sr0": sr0, "dsr": psr(sr, sr0, t, m["skew"], m["kurt"]), "N": n_trials, "N_eff": n_eff,
            "var_sr": v, "var_source": "QUERSCHNITT" if v_cross is not None and v_cross > v_null else "NULL_STICHPROBE",
            "n_obs": t, "skew": m["skew"], "kurt": m["kurt"]}


# ---------------------------------------------------------------- PBO / CSCV
def pbo_cscv(series: Sequence[Sequence[float]], s_blocks: int, max_combinations: int | None = None,
             seed: int = 0) -> dict:
    """PBO nach CSCV. series: N Strategien × T Beobachtungen. Die ersten T mod S Beobachtungen werden verworfen.
    max_combinations: deterministische Zufallsteilmenge (nur für die OC; Näherungsfehler wird ausgewiesen)."""
    n = len(series)
    if n < 2 or s_blocks < 2 or s_blocks % 2:
        raise ValueError("mindestens 2 Strategien und gerade Blockzahl S >= 2")
    t = len(series[0])
    if any(len(x) != t for x in series):
        raise ValueError("gleich lange Reihen nötig")
    if any(not math.isfinite(v) for x in series for v in x):
        raise ValueError("nur endliche Beobachtungen (fail-closed)")
    size = t // s_blocks
    if size < 2:
        raise ValueError("zu wenige Beobachtungen je Block")
    start = t - size * s_blocks
    sums = [[0.0] * s_blocks for _ in range(n)]
    sq = [[0.0] * s_blocks for _ in range(n)]
    for i, x in enumerate(series):
        for b in range(s_blocks):
            seg = x[start + b * size: start + (b + 1) * size]
            sums[i][b] = math.fsum(seg)
            sq[i][b] = math.fsum(v * v for v in seg)
    tot_s = [math.fsum(r) for r in sums]
    tot_q = [math.fsum(r) for r in sq]
    half = s_blocks // 2
    m_obs = half * size
    # Jede IS-Menge aus S/2 Blöcken = Teilmenge A der ersten und B der zweiten Blockhälfte mit |A| + |B| = S/2:
    # Teilsummen je Hälfte per Bitmaske vorberechnet (gleiche Kombinationsmenge wie itertools.combinations, schneller).
    lo_blocks, hi_blocks = list(range(half)), list(range(half, s_blocks))

    def subset_table(blocks: list[int], vals: list[float]) -> list[float]:
        tab = [0.0] * (1 << len(blocks))
        for mask in range(1, 1 << len(blocks)):
            low = mask & -mask
            j = low.bit_length() - 1
            tab[mask] = tab[mask ^ low] + vals[blocks[j]]
        return tab

    lo_s = [subset_table(lo_blocks, sums[i]) for i in range(n)]
    hi_s = [subset_table(hi_blocks, sums[i]) for i in range(n)]
    lo_q = [subset_table(lo_blocks, sq[i]) for i in range(n)]
    hi_q = [subset_table(hi_blocks, sq[i]) for i in range(n)]
    masks_by_pop: dict[int, list[int]] = {}
    for mask in range(1 << half):
        masks_by_pop.setdefault(bin(mask).count("1"), []).append(mask)
    combos = [(a, b) for k_lo in range(half + 1) for a in masks_by_pop.get(k_lo, []) for b in masks_by_pop.get(half - k_lo, [])]
    n_all = math.comb(s_blocks, half)
    if len(combos) != n_all:
        raise AssertionError("Kombinationszahl")
    if max_combinations is not None and max_combinations < n_all:
        rng = random.Random(seed)
        combos = [combos[k] for k in sorted(rng.sample(range(n_all), max_combinations))]
    inv_m = 1.0 / m_obs
    dof = m_obs - 1

    def sr_of(sv: float, qv: float) -> float:
        var = (qv - sv * sv * inv_m) / dof
        return (sv * inv_m) / math.sqrt(var) if var > 0 else 0.0

    below = 0
    losses = 0
    sum_x = sum_y = sum_xx = sum_xy = 0.0
    rng_n = range(n)
    for a, b in combos:
        is_sr = [sr_of(lo_s[i][a] + hi_s[i][b], lo_q[i][a] + hi_q[i][b]) for i in rng_n]
        best = 0
        for i in rng_n:
            if is_sr[i] > is_sr[best]:
                best = i
        s_in = lo_s[best][a] + hi_s[best][b]
        q_in = lo_q[best][a] + hi_q[best][b]
        o = sr_of(tot_s[best] - s_in, tot_q[best] - q_in)
        lower = equal = 0
        for i in rng_n:
            if i == best:
                continue
            si = lo_s[i][a] + hi_s[i][b]
            oi = sr_of(tot_s[i] - si, tot_q[i] - (lo_q[i][a] + hi_q[i][b]))
            if oi < o:
                lower += 1
            elif oi == o:
                equal += 1
        rank = 1 + lower + 0.5 * equal
        omega = rank / (n + 1)
        if math.log(omega / (1.0 - omega)) <= 0.0:
            below += 1
        if o < 0.0:
            losses += 1
        x = is_sr[best]
        sum_x += x
        sum_y += o
        sum_xx += x * x
        sum_xy += x * o
    k = len(combos)
    sxx = sum_xx - sum_x * sum_x / k
    slope = (sum_xy - sum_x * sum_y / k) / sxx if sxx > 1e-15 else 0.0
    return {"pbo": below / k, "n_combinations": k, "n_combinations_total": n_all, "exact": k == n_all,
            "prob_oos_loss": losses / k, "degradation_slope": slope, "s_blocks": s_blocks, "dropped_obs": start}


# ---------------------------------------------------------------- stationärer Bootstrap
def stationary_indices(n: int, mean_block: float, rng: random.Random) -> list[int]:
    """Politis/Romano (1994): neuer Blockstart mit Wahrscheinlichkeit 1/mean_block, sonst Fortsetzung (zyklisch)."""
    if n < 1 or not (math.isfinite(mean_block) and 1.0 <= mean_block <= n):
        raise ValueError("n >= 1 und mittlere Blocklänge in [1, n]")
    p = 1.0 / mean_block
    rnd = rng.random
    cur = int(rnd() * n)
    idx = [cur]
    for _ in range(n - 1):
        cur = int(rnd() * n) if rnd() < p else (cur + 1 if cur + 1 < n else 0)
        idx.append(cur)
    return idx


def optimal_block_length(x: Sequence[float]) -> float:
    """Blocklänge für den stationären Bootstrap nach Politis/White (2004) mit Korrektur Patton/Politis/White (2009)."""
    xs = _finite(x)
    n = len(xs)
    mu = sum(xs) / n
    d = [v - mu for v in xs]
    k_n = max(5, math.ceil(math.sqrt(math.log10(n))))
    m_max = math.ceil(math.sqrt(n)) + k_n
    b_max = math.ceil(min(3.0 * math.sqrt(n), n / 3.0))
    c = 2.0
    g0 = sum(v * v for v in d) / n
    if g0 <= 0.0:
        raise ValueError("Reihe ohne Streuung")
    acov = [g0] + [sum(d[t] * d[t - k] for t in range(k, n)) / n for k in range(1, min(m_max + k_n, n - 1) + 1)]
    rho = [a / g0 for a in acov]
    bound = c * math.sqrt(math.log10(n) / n)
    m_hat = None
    for m in range(0, len(rho) - k_n):
        if all(abs(rho[m + j]) < bound for j in range(1, k_n + 1)):
            m_hat = m
            break
    if m_hat is None:
        m_hat = m_max
    big_m = min(2 * max(m_hat, 1), m_max, len(acov) - 1)

    def lam(s: float) -> float:
        a = abs(s)
        return 1.0 if a <= 0.5 else (2.0 * (1.0 - a) if a <= 1.0 else 0.0)

    g_hat = sum(lam(k / big_m) * acov[abs(k)] for k in range(-big_m, big_m + 1))
    big_g = sum(lam(k / big_m) * abs(k) * acov[abs(k)] for k in range(-big_m, big_m + 1))
    d_sb = 2.0 * g_hat * g_hat
    if big_g == 0.0 or d_sb <= 0.0:
        return 1.0
    b = (2.0 * big_g * big_g / d_sb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    return float(min(max(b, 1.0), b_max))


def _boot_means(series: Sequence[Sequence[float]], b_reps: int, mean_block: float, seed: int) -> list[list[float]]:
    n = len(series[0])
    rng = random.Random(seed)
    out = []
    for _ in range(b_reps):
        idx = stationary_indices(n, mean_block, rng)
        out.append([sum(map(x.__getitem__, idx)) / n for x in series])
    return out


def _boot_omega(boots: Sequence[Sequence[float]], dbar: Sequence[float], n: int) -> list[float]:
    """Bootstrap-Standardabweichung von √n·d̄_k; Varianz 0 ist nicht studentisierbar (fail-closed)."""
    out = []
    for k in range(len(dbar)):
        v = sum((math.sqrt(n) * (bm[k] - dbar[k])) ** 2 for bm in boots) / len(boots)
        if not v > 0.0:
            raise ValueError("Bootstrap-Varianz 0 (Blocklänge zu groß oder Reihe konstant)")
        out.append(math.sqrt(v))
    return out


def spa_test(d: Sequence[Sequence[float]], b_reps: int, mean_block: float | None = None, seed: int = 0,
             indices: Sequence[Sequence[int]] | None = None) -> dict:
    """Hansen (2005) SPA. d[k][t] = Leistung von Modell k gegenüber dem Benchmark (positiv = besser);
    H0: max_k E[d_k] <= 0. Studentisierung mit der Bootstrap-Varianz von √n·d̄_k; p-Werte konsistent/unten/oben."""
    k_models = len(d)
    if k_models < 1:
        raise ValueError("mindestens ein Modell")
    xs = [_finite(x) for x in d]
    n = len(xs[0])
    if any(len(x) != n for x in xs):
        raise ValueError("gleich lange Reihen nötig")
    if mean_block is None:
        mean_block = max(optimal_block_length(x) for x in xs)
    dbar = [sum(x) / n for x in xs]
    if indices is None:
        boots = _boot_means(xs, b_reps, mean_block, seed)
    else:                                                  # feste Indizes (Orakelvergleich, REQ-016)
        if len(indices) != b_reps or any(len(idx) != n or not all(0 <= i < n for i in idx) for idx in indices):
            raise ValueError("indices: b_reps Listen mit je n gültigen Indizes")
        boots = [[sum(map(x.__getitem__, idx)) / n for x in xs] for idx in indices]
    omega = _boot_omega(boots, dbar, n)
    t_stat = max(0.0, max(math.sqrt(n) * dbar[k] / omega[k] for k in range(k_models)))
    thr = math.sqrt(2.0 * math.log(math.log(n)))          # Hansen (2005), definiert ab n >= 3 (_finite verlangt n >= 3)
    mu_c = [dbar[k] if math.sqrt(n) * dbar[k] / omega[k] <= -thr else 0.0 for k in range(k_models)]
    mu_l = [min(dbar[k], 0.0) for k in range(k_models)]
    counts = {"consistent": 0, "lower": 0, "upper": 0}
    for bm in boots:
        for name, mu in (("consistent", mu_c), ("lower", mu_l), ("upper", [0.0] * k_models)):
            tb = max(0.0, max(math.sqrt(n) * (bm[k] - dbar[k] + mu[k]) / omega[k] for k in range(k_models)))
            if tb >= t_stat:
                counts[name] += 1
    return {"t_spa": t_stat, "p_consistent": counts["consistent"] / b_reps, "p_lower": counts["lower"] / b_reps,
            "p_upper": counts["upper"] / b_reps, "b_reps": b_reps, "mean_block": mean_block, "n_obs": n,
            "p_mc_se": math.sqrt(max(counts["consistent"] / b_reps * (1 - counts["consistent"] / b_reps), 1.0 / b_reps) / b_reps)}


def romano_wolf_stepm(d: Sequence[Sequence[float]], b_reps: int, alpha: float, mean_block: float | None = None,
                      seed: int = 0) -> dict:
    """Romano/Wolf (2005) StepM, studentisiert: identifiziert Modelle mit E[d_k] > 0 bei familienweitem Fehler alpha."""
    xs = [_finite(x) for x in d]
    k_models = len(xs)
    if k_models < 1 or not 0.0 < alpha < 1.0 or b_reps < 1:
        raise ValueError("mindestens ein Modell, 0 < alpha < 1, b_reps >= 1")
    n = len(xs[0])
    if any(len(x) != n for x in xs):
        raise ValueError("gleich lange Reihen nötig")
    if mean_block is None:
        mean_block = max(optimal_block_length(x) for x in xs)
    dbar = [sum(x) / n for x in xs]
    boots = _boot_means(xs, b_reps, mean_block, seed)
    omega = _boot_omega(boots, dbar, n)
    t = [math.sqrt(n) * dbar[k] / omega[k] for k in range(k_models)]
    active = set(range(k_models))
    rejected: list[int] = []
    steps = []
    while active:
        maxima = sorted(max(math.sqrt(n) * (bm[k] - dbar[k]) / omega[k] for k in active) for bm in boots)
        crit = maxima[min(len(maxima) - 1, math.ceil((1.0 - alpha) * len(maxima)) - 1)]
        new = sorted(k for k in active if t[k] > crit)
        steps.append({"critical": crit, "rejected": new})
        if not new:
            break
        rejected += new
        active -= set(new)
    return {"rejected": sorted(rejected), "t": t, "steps": steps, "alpha": alpha, "b_reps": b_reps, "mean_block": mean_block}


# ---------------------------------------------------------------- nichtlinearer Mehrfachtest-Abschlag
def _p_two_sided(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2.0))


def haircut_sharpe(sr_ann: float, years: float, m: float, method: str = "BONFERRONI",
                   other_p: Sequence[float] = ()) -> dict:
    """Harvey/Liu (2015): angepasster p-Wert, daraus die abgeschlagene SR. Nichtlinear: je höher die SR und je kleiner
    m (= N_eff), desto kleiner der relative Abschlag. HOLM/BHY brauchen die p-Werte der übrigen Versuche (other_p)."""
    if sr_ann <= 0.0 or years <= 0.0 or m < 1.0:
        raise ValueError("sr_ann > 0, years > 0 und m >= 1 nötig")
    t = sr_ann * math.sqrt(years)
    p = _p_two_sided(t)
    if method == "BONFERRONI":
        p_adj = min(1.0, m * p)
    elif method == "SIDAK":
        p_adj = -math.expm1(m * math.log1p(-p))              # genau auch für sehr kleine p (C06-S-07)
    elif method in ("HOLM", "BHY"):
        if any(not (math.isfinite(x) and 0.0 <= x <= 1.0) for x in other_p) or abs(len(other_p) + 1 - m) > 1e-9:
            raise ValueError("HOLM/BHY brauchen die p-Werte aller übrigen Versuche (Anzahl + 1 = m, Werte in [0, 1])")
        ps = sorted([p, *other_p])
        mm = len(ps)
        rank = ps.index(p) + 1
        if method == "HOLM":
            p_adj = min(1.0, max((mm - j + 1) * ps[j - 1] for j in range(1, rank + 1)))
        else:
            c_m = sum(1.0 / j for j in range(1, mm + 1))
            p_adj = min(1.0, min(ps[j - 1] * mm * c_m / j for j in range(rank, mm + 1)))
    else:
        raise ValueError("unbekannte Methode")
    if p_adj >= 1.0:
        t_adj = 0.0
    elif p_adj <= 0.0:
        if p > 0.0:
            raise ValueError("angepasster p-Wert ausgelöscht (p > 0, p_adj = 0) – fail-closed statt stillem Wegfall des Abschlags")
        t_adj = abs(t)                                        # p selbst 0 (|t| jenseits der Darstellung): kein messbarer Abschlag
    else:
        t_adj = -norm_ppf(p_adj / 2.0)                        # genauer als Φ⁻¹(1 − p/2) für kleine p
    sr_adj = max(0.0, t_adj) / math.sqrt(years)
    return {"t": t, "p": p, "p_adj": p_adj, "sr_adj": sr_adj, "haircut": min(1.0, max(0.0, 1.0 - sr_adj / sr_ann)), "method": method, "m": m}


# ---------------------------------------------------------------- Unsicherheit von Anteilen, Mittelwerten und Quantilen
Z95 = 1.959963984540054


def mean_ci(mean: float, se: float, z: float = Z95) -> list[float]:
    """Normal-KI für Mittelwerte bzw. geschichtete Summen (MC-Stichproben >= 30; MP §11.2, W-18)."""
    if not (math.isfinite(mean) and math.isfinite(se) and se >= 0.0):
        raise ValueError("Mittel und SE endlich, SE >= 0")
    return [mean - z * se, mean + z * se]


def ratio_ci(rate: float, se: float, z: float = Z95) -> list[float]:
    """KI eines Anteils bzw. Quotienten aus Delta-Methoden-SE auf der Logit-Skala (bleibt in [0, 1])."""
    if not (0.0 <= rate <= 1.0 and math.isfinite(se) and se >= 0.0):
        raise ValueError("Anteil in [0, 1], SE >= 0")
    if rate in (0.0, 1.0) or se == 0.0:
        return [max(0.0, rate - z * se), min(1.0, rate + z * se)]
    lg = math.log(rate / (1.0 - rate))
    half = z * se / (rate * (1.0 - rate))
    return [1.0 / (1.0 + math.exp(-(lg - half))), 1.0 / (1.0 + math.exp(-(lg + half)))]


def quantile_ci(values: Sequence[float | None], q: float, z: float = Z95) -> list[float | None]:
    """Verteilungsfreies Ordnungsstatistik-KI des q-Quantils; None (zensiert) zählt als +∞, eine Grenze jenseits der
    beobachteten Werte wird als None ("> Horizont") ausgewiesen."""
    n = len(values)
    if n < 1 or not 0.0 < q < 1.0:
        raise ValueError("n >= 1, 0 < q < 1")
    xs = sorted(values, key=lambda v: (v is None, v if v is not None else 0.0))
    half = z * math.sqrt(n * q * (1.0 - q))
    lo_i = max(0, math.floor(n * q - half) - 1)
    hi_i = min(n - 1, math.ceil(n * q + half))
    return [xs[lo_i], xs[hi_i]]



def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("0 <= k <= n, n > 0")
    p = k / n
    den = 1.0 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def weighted_rate(k_w: float, n_w: float, n_eff_samples: float) -> dict:
    """Gewichteter Anteil mit Wilson-Intervall über die effektive Stichprobengröße (Kish)."""
    p = k_w / n_w if n_w > 0 else 0.0
    ne = max(1.0, n_eff_samples)
    lo, hi = wilson(round(p * ne), max(1, round(ne)))
    return {"rate": p, "wilson_95": [lo, hi], "mc_se": math.sqrt(p * (1 - p) / ne), "n_eff": ne}
