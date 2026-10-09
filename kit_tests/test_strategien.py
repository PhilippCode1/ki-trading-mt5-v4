"""Vorregistrierte Strategien F-04 (kit/strategy/rev.py, varianten.py): Handfälle mit von Hand gerechneten SL/TP, Rastertreue,
Stop/Ziel-Verhältnis, Variantenliste, strategie_hash und Laufzeit. Nur synthetische Kerzen (keine Marktdaten)."""
from __future__ import annotations

import json
import random
import time
from decimal import Decimal

import pytest

from kit.domain.types import Bar, Side
from kit.strategy.base import strategie_hash
from kit.strategy.donchian_ref import Params
from kit.strategy.rev import SYMBOLE, Fehlausbruch, MittelwertRueckkehr, punkt, signale, wilder_atr
from kit.strategy.varianten import strategie, varianten

D = Decimal
T0 = 1_600_000_000 // 3600 * 3600


def _bar(symbol: str, i: int, o: str, h: str, lo: str, c: str, spread: int = 10) -> Bar:
    return Bar(symbol, T0 + 3600 * i, D(o), D(h), D(lo), D(c), spread)


def _flach(symbol: str, anzahl: int, c: str, h: str, lo: str) -> list[Bar]:
    return [_bar(symbol, i, c, h, lo, c) for i in range(anzahl)]


# ------------------------------------------------------------------------------------------------ Hilfen
def test_punkt_und_atr_handfall():
    assert punkt("USDJPY") == D("0.001") and punkt("CHFJPY") == D("0.001") and punkt("EURUSD") == D("0.00001")
    # TR: 2 (H−L der ersten Kerze), max(2, |5−1|=4, |3−1|=2) = 4, max(2, |4−5|=1, |2−5|=3) = 3, max(4, |6−3|=3, |2−3|=1) = 4.
    # n = 2: Start = (2+4)/2 = 3 an Index 1; danach (1·3 + 3)/2 = 3; (1·3 + 4)/2 = 3,5
    kerzen = [_bar("X", 0, "1", "2", "0", "1"), _bar("X", 1, "3", "5", "3", "5"), _bar("X", 2, "3", "4", "2", "3"),
              _bar("X", 3, "3", "6", "2", "4")]
    assert wilder_atr(kerzen, 2) == [None, 3.0, 3.0, 3.5]


# ------------------------------------------------------------------------------------------------ S-REV-01
def _rev01_reihe(symbol: str, schluss: list[str], hoch: list[str], tief: list[str], spread: int) -> list[Bar]:
    """Flache Kerzen bis zur Länge 250, danach die angegebenen Kerzen (Eröffnung = voriger Schluss)."""
    if symbol.endswith("JPY"):
        kerzen = _flach(symbol, 250 - len(schluss), "110.000", "110.010", "109.990")
    else:
        kerzen = _flach(symbol, 250 - len(schluss), "1.10000", "1.10010", "1.09990")
    for c, h, lo in zip(schluss, hoch, tief, strict=True):
        kerzen.append(_bar(symbol, len(kerzen), str(kerzen[-1].close), h, lo, c, spread))
    return kerzen


def test_rev01_long_handfall():
    # 249 flache EURUSD-Kerzen (C 1,10000, H 1,10010, L 1,09990, TR 0,00020, ATR 0,00020), Kerze t: C 1,09800, H 1,10010,
    # L 1,09780. Band t: 47 × 1,1 und 1,098 → C_t − SMA = −0,002·47/48, σ = 0,002·√47/48 → z ≈ −6,86 < −2 (erstmals: Vorfenster
    # flach, σ_{t−1} = 0, C_{t−1} = 1,1 ≥ unten_{t−1} = 1,1). TR_t = max(0,0023, 0,0001, 0,0022) = 0,0023;
    # ATR_t = (13·0,0002 + 0,0023)/14 = 0,00035. z_tp 0,5: 0,000175/0,00001 = 17,5 → 18 Ticks. e = 1,09800 + 12·0,00001 = 1,09812.
    # TP = 1,09812 + 0,00018 = 1,09830; SL = 1,09812 − 2·18·0,00001 = 1,09776.
    kerzen = _rev01_reihe("EURUSD", ["1.09800"], ["1.10010"], ["1.09780"], spread=12)
    sig = MittelwertRueckkehr(k=2.0, z_tp=0.5, r=2).signal("EURUSD", kerzen)
    assert sig is not None
    assert (sig.symbol, sig.side, sig.sl, sig.tp, sig.kerze) == ("EURUSD", Side.BUY, D("1.09776"), D("1.09830"), kerzen[-1].time)
    assert sig.grund == "S-REV-01 k=2.0 z=0.50 r=2" and len(sig.grund) <= 40
    # z_tp 0,75: 0,0002625/0,00001 = 26,25 → 27 Ticks; r 3 → 81 Ticks: TP 1,09839, SL 1,09731
    sig = MittelwertRueckkehr(k=2.5, z_tp=0.75, r=3).signal("EURUSD", kerzen)
    assert sig is not None and (sig.side, sig.sl, sig.tp) == (Side.BUY, D("1.09731"), D("1.09839"))


def test_rev01_short_handfall_jpy():
    # USDJPY (punkt 0,001): flach C 110,000, H 110,010, L 109,990 (TR 0,02), Kerze t: C 110,200, H 110,220, L 109,990.
    # Band: Ausreißer +0,2 → z ≈ +6,86 > 2,5; Vorfenster flach. TR_t = max(0,23, 0,22, 0,01) = 0,23; ATR_t = (13·0,02 + 0,23)/14
    # = 0,035. z_tp 0,75: 0,02625/0,001 = 26,25 → 27 Ticks. Verkauf: e = Schluss 110,200 (Spread egal).
    # TP = 110,200 − 0,027 = 110,173; SL = 110,200 + 3·27·0,001 = 110,281.
    kerzen = _rev01_reihe("USDJPY", ["110.200"], ["110.220"], ["109.990"], spread=25)
    sig = MittelwertRueckkehr(k=2.5, z_tp=0.75, r=3).signal("USDJPY", kerzen)
    assert sig is not None
    assert (sig.side, sig.sl, sig.tp, sig.kerze) == (Side.SELL, D("110.281"), D("110.173"), kerzen[-1].time)
    # z_tp 0,5: 0,0175/0,001 = 17,5 → 18 Ticks; r 2 → 36: TP 110,182, SL 110,236
    sig = MittelwertRueckkehr(k=2.0, z_tp=0.5, r=2).signal("USDJPY", kerzen)
    assert sig is not None and (sig.side, sig.sl, sig.tp) == (Side.SELL, D("110.236"), D("110.182"))


@pytest.mark.parametrize(("schluss", "hoch", "tief"), [
    (["1.09800", "1.09700"], ["1.10010", "1.09800"], ["1.09780", "1.09680"]),     # Long-Seite
    (["1.10200", "1.10300"], ["1.10220", "1.10320"], ["1.09990", "1.10200"]),     # Short-Seite
])
def test_rev01_nur_erstmals(schluss, hoch, tief):
    # Kerze t−1 fällt bereits aus dem Band (dort Signal); t liegt noch weiter draußen: C_t−1 = 1,098 < unten_{t−1}
    # = SMA_{t−1} − 2σ_{t−1} ≈ 1,0999583 − 2·0,0002857 = 1,099387 → nicht „erstmals“ → kein Signal in t.
    kerzen = _rev01_reihe("EURUSD", schluss, hoch, tief, spread=10)
    s = MittelwertRueckkehr(k=2.0, z_tp=0.5, r=2)
    vorher = s.signal("EURUSD", [kerzen[0]] + kerzen[:-1])          # Fenster bis t−1 (wieder 250 Kerzen)
    assert vorher is not None and vorher.kerze == kerzen[-2].time
    assert s.signal("EURUSD", kerzen) is None


def test_rev01_kein_signal_im_band_nullvola_und_kurzem_fenster():
    s = MittelwertRueckkehr()
    flach = _flach("EURUSD", 250, "1.10000", "1.10010", "1.09990")
    assert s.signal("EURUSD", flach) is None                             # σ_t = 0
    kerzen = _rev01_reihe("EURUSD", ["1.09800"], ["1.10010"], ["1.09780"], spread=12)
    assert s.signal("EURUSD", kerzen[-249:]) is None                     # zu kurzes Fenster
    assert MittelwertRueckkehr(rueckblick=60).signal("EURUSD", kerzen[-60:]) is not None


# ------------------------------------------------------------------------------------------------ S-REV-02
def _rev02_reihe(symbol: str, o: str, h: str, lo: str, c: str, spread: int = 10) -> list[Bar]:
    if symbol.endswith("JPY"):
        kerzen = _flach(symbol, 249, "110.000", "110.050", "109.950")
    else:
        kerzen = _flach(symbol, 249, "1.10000", "1.10050", "1.09950")
    return kerzen + [_bar(symbol, 249, o, h, lo, c, spread)]


def test_rev02_short_fehlausbruch():
    # Spanne der 20 Kerzen vor t: H 1,10050, Lo 1,09950 (TR 0,0010 → ATR 0,0010). Kerze t: H 1,10080 > H, C 1,10020 < H.
    # TR_t = max(0,0009, 0,0008, 0,0001) = 0,0009; ATR_t = (13·0,001 + 0,0009)/14 = 0,000992857…
    # z_tp 0,5: 49,64… Ticks → 50; e = 1,10020 (Bid) → TP = 1,09970. SL = 1,10080 + 0,0000992857 = 1,1008992… → aufrunden 1,10090.
    kerzen = _rev02_reihe("EURUSD", "1.10000", "1.10080", "1.09990", "1.10020")
    sig = Fehlausbruch(L=20, z_tp=0.5).signal("EURUSD", kerzen)
    assert sig is not None
    assert (sig.side, sig.sl, sig.tp, sig.kerze) == (Side.SELL, D("1.10090"), D("1.09970"), kerzen[-1].time)
    assert sig.grund == "S-REV-02 L=20 z=0.5"


def test_rev02_long_fehlausbruch_jpy():
    # USDJPY: Spanne H 110,050, Lo 109,950 (TR 0,1). Kerze t: L 109,900 < Lo, C 109,980 > Lo, H 110,010.
    # TR_t = max(0,11, 0,01, 0,1) = 0,11; ATR_t = (13·0,1 + 0,11)/14 = 0,1007142…; z_tp 1,0: 100,71… Ticks → 101.
    # e = 109,980 + 15·0,001 = 109,995 (Ask) → TP = 110,096. SL = 109,900 − 0,01007142… = 109,88992… → abrunden 109,889.
    kerzen = _rev02_reihe("USDJPY", "110.000", "110.010", "109.900", "109.980", spread=15)
    sig = Fehlausbruch(L=20, z_tp=1.0).signal("USDJPY", kerzen)
    assert sig is not None
    assert (sig.side, sig.sl, sig.tp) == (Side.BUY, D("109.889"), D("110.096"))


def test_rev02_beidseitig_echter_ausbruch_und_kurzes_fenster():
    s = Fehlausbruch()
    beidseitig = _rev02_reihe("EURUSD", "1.10000", "1.10080", "1.09900", "1.10000")    # H > Hoch und L < Tief
    assert s.signal("EURUSD", beidseitig) is None
    echt = _rev02_reihe("EURUSD", "1.10000", "1.10080", "1.09990", "1.10060")          # Schluss über dem Spannenhoch
    assert s.signal("EURUSD", echt) is None
    gut = _rev02_reihe("EURUSD", "1.10000", "1.10080", "1.09990", "1.10020")
    assert s.signal("EURUSD", gut[-249:]) is None                                     # zu kurzes Fenster


def test_rev02_stop_ueber_drei_ziel_wird_trotzdem_geliefert():
    # Langer Docht: H 1,10500, C 1,10020. TR_t = max(0,0051, 0,0050, 0,0001) = 0,0051; ATR_t = (0,013 + 0,0051)/14 = 0,00129285…
    # z_tp 0,5: 64,64… → 65 Ticks: TP = 1,10020 − 0,00065 = 1,09955. SL = 1,10500 + 0,000129285… → aufrunden 1,10513.
    # |e − SL| = 0,00493 > 3 · 0,00065 = 0,00195 → Signal kommt trotzdem (der Takt lehnt mit STOP_ZU_ZIEL ab).
    kerzen = _rev02_reihe("EURUSD", "1.10000", "1.10500", "1.09990", "1.10020")
    sig = Fehlausbruch(L=20, z_tp=0.5).signal("EURUSD", kerzen)
    assert sig is not None and (sig.side, sig.sl, sig.tp) == (Side.SELL, D("1.10513"), D("1.09955"))
    e = kerzen[-1].close
    assert abs(e - sig.sl) > 3 * abs(sig.tp - e)


# ------------------------------------------------------------------------------------------------ Raster und Verhältnis
def _zufallsreihe(symbol: str, anzahl: int, saat: int) -> list[Bar]:
    rng = random.Random(saat)
    p = punkt(symbol)
    preis = 110.0 if symbol.endswith("JPY") else 1.1
    schritt = preis * 0.002
    out: list[Bar] = []
    c = D(repr(preis)).quantize(p)
    for i in range(anzahl):
        o = c
        c = (o + D(repr(rng.gauss(0.0, schritt))).quantize(p)).quantize(p)
        h = max(o, c) + D(repr(abs(rng.gauss(0.0, schritt)))).quantize(p)
        lo = min(o, c) - D(repr(abs(rng.gauss(0.0, schritt)))).quantize(p)
        out.append(Bar(symbol, T0 + 3600 * i, o, h, lo, c, rng.randint(0, 30)))
    return out


@pytest.mark.parametrize("symbol", ["EURUSD", "USDJPY"])
def test_rastertreue_und_stop_ziel_verhaeltnis(symbol):
    p = punkt(symbol)
    kerzen = _zufallsreihe(symbol, 700, saat=7 if symbol == "EURUSD" else 8)
    for v in varianten()[:12]:
        s = strategie(v)
        sigs = [x for x in signale(s, symbol, kerzen) if x is not None]
        assert len(sigs) >= 3, v.id
        zeit = {b.time: b for b in kerzen}
        for sig in sigs:
            b = zeit[sig.kerze]
            e = b.close + b.spread_points * p if sig.side is Side.BUY else b.close
            assert sig.sl % p == 0 and sig.tp % p == 0, (v.id, sig)
            ziel = (sig.tp - e) * sig.side.sign / p
            assert ziel == ziel.to_integral_value() and ziel >= 1, (v.id, sig)
            assert (e - sig.sl) * sig.side.sign > 0                       # SL auf der Verlustseite
            if isinstance(s, MittelwertRueckkehr):
                assert abs(e - sig.sl) == s.r * abs(sig.tp - e), (v.id, sig)


def test_signale_ruft_wie_der_takt():
    class Aufzeichner(MittelwertRueckkehr):
        def signal(self, symbol, kerzen):
            fenster.append((kerzen[0].time, kerzen[-1].time, len(kerzen)))
            return None

    fenster: list[tuple[int, int, int]] = []
    kerzen = _zufallsreihe("EURUSD", 10, saat=1)
    assert signale(Aufzeichner(rueckblick=4), "EURUSD", kerzen) == [None] * 10
    assert fenster[0] == (kerzen[0].time, kerzen[0].time, 1)
    assert fenster[3] == (kerzen[0].time, kerzen[3].time, 4)
    assert fenster[9] == (kerzen[6].time, kerzen[9].time, 4)


# ------------------------------------------------------------------------------------------------ Varianten und Hash
def test_varianten_liste():
    vs = varianten()
    assert [v.id for v in vs] == [
        "S-REV-01-k2.0-z0.50-r2", "S-REV-01-k2.0-z0.50-r3", "S-REV-01-k2.0-z0.75-r2", "S-REV-01-k2.0-z0.75-r3",
        "S-REV-01-k2.5-z0.50-r2", "S-REV-01-k2.5-z0.50-r3", "S-REV-01-k2.5-z0.75-r2", "S-REV-01-k2.5-z0.75-r3",
        "S-REV-02-L20-z0.5", "S-REV-02-L20-z1.0", "S-REV-02-L40-z0.5", "S-REV-02-L40-z1.0", "S-BL-01"]
    assert all(v.familie == "F04-ZIEL-STOP" and v.zaehlt for v in vs[:12])
    assert vs[12].familie == "F04-REFERENZ" and not vs[12].zaehlt
    s = strategie(vs[6])
    assert isinstance(s, MittelwertRueckkehr) and (s.n, s.k, s.z_tp, s.r) == (48, 2.5, 0.75, 2)
    assert (s.name, s.zeitrahmen, s.rueckblick, s.max_halte_s, s.symbole) == ("S-REV-01", "H1", 250, 86400, SYMBOLE)
    f = strategie(vs[11])
    assert isinstance(f, Fehlausbruch) and (f.L, f.z_tp, f.sl_puffer, f.max_stop_ziel) == (40, 1.0, 0.1, 3)
    assert (f.name, f.zeitrahmen, f.rueckblick, f.max_halte_s) == ("S-REV-02", "H4", 250, 86400)
    assert strategie(vs[12]) == Params(55, 20, 20, 2.0, "full_bar")
    assert SYMBOLE == ("EURUSD", "USDJPY", "GBPUSD", "CHFJPY", "CADJPY", "AUDUSD", "NZDUSD")
    for v in vs:
        json.dumps(v.parameter)


def test_strategie_hash_unterscheidet_alle_zwoelf():
    objekte = [strategie(v) for v in varianten()[:12]]
    hashes = {strategie_hash(s) for s in objekte}
    assert len(hashes) == 12
    assert strategie_hash(strategie(varianten()[0])) == strategie_hash(MittelwertRueckkehr())     # deterministisch
    for s in objekte:
        par = s.parameter()
        assert all(isinstance(w, str) for w in par.values()) and json.loads(json.dumps(par)) == par


# ------------------------------------------------------------------------------------------------ Laufzeit
def test_laufzeit_rev01():
    kerzen = _zufallsreihe("EURUSD", 2250, saat=3)
    s = MittelwertRueckkehr(k=2.0)
    fenster = [kerzen[i - 250:i] for i in range(250, 2250)]
    start = time.perf_counter()
    treffer = sum(s.signal("EURUSD", f) is not None for f in fenster)
    dauer = time.perf_counter() - start
    assert treffer > 0
    assert dauer < 2.0, f"2.000 Aufrufe dauerten {dauer:.2f} s"
