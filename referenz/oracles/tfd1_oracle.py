"""O-STR-2 (R-02): unabhängiges Orakel der TF-D1-Semantik nach dem Regeltext R1–R8 (Wilder-ATR exakt mit Fraction) und
das S-BASE-Gegenmodell (v3 s_base: Schlusskanal, Niveau statt Kreuzung, |ΔClose|-Glättung, Ausführung am Signalschluss
ohne Spread, statischer Schlusskurs-Stopp, Kanalausstieg), um zu zeigen, dass der Differenztest Abweichungen erkennt.
Nur Standardbibliothek; keine Kenntnis des Referenzcodes."""
from __future__ import annotations

import random
from fractions import Fraction


def make_bars(seed: int, n: int, gap_rate: float = 0.0, short_rate: float = 0.0) -> list[dict]:
    """Synthetische Tageskerzen (keine Marktdaten): Zufallsbewegung mit Trendphasen, optional Lücken/Kurzsitzungen."""
    rng = random.Random(seed)
    p, out = 100.0, []
    drift = 0.0
    for i in range(n):
        if i % 120 == 0:
            drift = rng.choice((-0.35, 0.0, 0.35))
        o = p + rng.gauss(0.0, 0.3)
        c = o + drift + rng.gauss(0.0, 0.8)
        h = max(o, c) + abs(rng.gauss(0.0, 0.4))
        lo = min(o, c) - abs(rng.gauss(0.0, 0.4))
        out.append({"high": h, "low": lo, "close": c, "open": o, "valid": rng.random() >= gap_rate,
                    "short_session": rng.random() < short_rate})
        p = c
    return out


def tfd1(bars: list[dict], hs: float, entry_n: int = 55, trail_n: int = 20, atr_n: int = 20, k: float = 2.0) -> list[tuple]:
    """Trades als (Richtung, Signalkerze, Einstiegskerze, Einstiegspreis, Ausstiegskerze, Ausstiegspreis, Grund)."""
    n = len(bars)
    # R8: True Range und Wilder-ATR (Fraction), Start mit dem Mittel der ersten atr_n gültigen TR
    atr: list[Fraction | None] = [None] * n
    last_close, trs, cur = None, [], None
    for i, b in enumerate(bars):
        if not b["valid"]:
            continue
        hi, lo = Fraction(b["high"]), Fraction(b["low"])
        tr = hi - lo if last_close is None else max(hi - lo, abs(hi - last_close), abs(lo - last_close))
        last_close = Fraction(b["close"])
        if cur is None:
            trs.append(tr)
            if len(trs) == atr_n:
                cur = sum(trs) / atr_n
                atr[i] = cur
        else:
            cur = ((atr_n - 1) * cur + tr) / atr_n
            atr[i] = cur

    def win(t: int, m: int) -> list[dict] | None:          # Kerzen t−m..t−1, alle gültig
        if t - m < 0:
            return None
        w = bars[t - m:t]
        return w if all(x["valid"] for x in w) else None

    trades, pos, pend = [], None, None
    for t, b in enumerate(bars):
        entered = False
        if pend and pend[2] == t:
            if pos is None and b["valid"] and not b["short_session"]:
                d, s_bar = k * float(atr[pend[1]]), pend[1]
                px = b["open"] + hs if pend[0] > 0 else b["open"] - hs
                pos = {"dir": pend[0], "sig": s_bar, "ent": t, "px": px, "stop": px - d if pend[0] > 0 else px + d,
                       "trailed": False}
                entered = True
            pend = None
        if pos and b["valid"]:
            if pos["dir"] > 0:
                o, probe = b["open"] - hs, b["low"] - hs
                fill = o if (not entered and o <= pos["stop"]) else (pos["stop"] if probe <= pos["stop"] else None)
            else:
                o, probe = b["open"] + hs, b["high"] + hs
                fill = o if (not entered and o >= pos["stop"]) else (pos["stop"] if probe >= pos["stop"] else None)
            if fill is not None:
                trades.append((pos["dir"], pos["sig"], pos["ent"], pos["px"], t, fill,
                               "TRAIL_STOP" if pos["trailed"] else "INITIAL_STOP"))
                pos = None
        if pos:
            w = win(t + 1, trail_n)
            if w:
                lvl = min(x["low"] for x in w) if pos["dir"] > 0 else max(x["high"] for x in w)
                if (pos["dir"] > 0 and lvl > pos["stop"]) or (pos["dir"] < 0 and lvl < pos["stop"]):
                    pos["stop"], pos["trailed"] = lvl, True
        if pos is None and b["valid"] and t >= 1 and bars[t - 1]["valid"] and atr[t] is not None:
            w_t, w_p = win(t, entry_n), win(t - 1, entry_n)
            if w_t and w_p:
                up_t, lo_t = max(x["high"] for x in w_t), min(x["low"] for x in w_t)
                up_p, lo_p = max(x["high"] for x in w_p), min(x["low"] for x in w_p)
                lg = b["close"] > up_t and bars[t - 1]["close"] <= up_p
                sh = b["close"] < lo_t and bars[t - 1]["close"] >= lo_p
                if lg != sh:
                    pend = (1 if lg else -1, t, t + 1)
    return trades


def sbase(bars: list[dict], entry_n: int = 55, exit_n: int = 20, atr_n: int = 20, k: float = 2.0) -> list[tuple]:
    """Gegenmodell v3 s_base (nur zur Trennschärfe des Differenztests; ungültige Kerzen werden hier ignoriert)."""
    closes = [b["close"] for b in bars]
    trades, pos, atr = [], None, None
    for t in range(1, len(closes)):
        d = abs(closes[t] - closes[t - 1])
        atr = d if atr is None else atr + (d - atr) / atr_n
        if t < entry_n:
            continue
        hi, lo = max(closes[t - entry_n:t]), min(closes[t - entry_n:t])
        if pos:
            ex_hi, ex_lo = max(closes[t - exit_n:t]), min(closes[t - exit_n:t])
            stop_hit = closes[t] <= pos[3] if pos[0] > 0 else closes[t] >= pos[3]
            chan = closes[t] < ex_lo if pos[0] > 0 else closes[t] > ex_hi
            if stop_hit or chan:
                trades.append((pos[0], pos[1], pos[1], pos[2], t, closes[t], "STOP" if stop_hit else "CHANNEL"))
                pos = None
        if pos is None:
            if closes[t] > hi:
                pos = (1, t, closes[t], closes[t] - k * atr)
            elif closes[t] < lo:
                pos = (-1, t, closes[t], closes[t] + k * atr)
    return trades


def selftest_bars() -> list[dict]:
    """Handfall (wie der v3-Selbsttest): Seitwärts 100, dann +0,5/Tag, dann −0,8/Tag; High/Low = Schluss ± 0,2."""
    out, price = [], 100.0
    for i in range(160):
        if 80 <= i < 120:
            price += 0.5
        elif i >= 120:
            price -= 0.8
        out.append({"high": price + 0.2, "low": price - 0.2, "close": price, "open": price, "valid": True,
                    "short_session": False})
    return out


# Handrechnung zum Selbsttest (half_spread 0,01): Signal t=80 (C 100,5 > U 100,2, C_79 100 ≤ 100,2),
# Einstieg t=81 zu 101,0 + 0,01; ATR_80 = (19·0,4 + 0,7)/20 = 0,415; D = 0,83; Anfangsstopp 100,18.
SELFTEST_EXPECT = {"direction": 1, "signal_bar": 80, "entry_bar": 81, "entry_price": 101.01, "stop_distance": 0.83,
                   "initial_stop": 100.18}
