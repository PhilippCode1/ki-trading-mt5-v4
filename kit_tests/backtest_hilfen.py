"""Synthetische Kerzen für Backtest-Tests (keine Marktdaten): Zufallspfade je Symbol, H1 mit Wochenendpause wie beim Broker
(Serverzeit = UTC + 3 h: Sa 00:00 bis Mo 00:00 Serverzeit geschlossen), H4/D1 auf Servergrenzen aus H1 verdichtet."""
from __future__ import annotations

import datetime as dt
import math
import random
from decimal import ROUND_HALF_EVEN, Decimal

from kit.domain.types import Bar, Side
from kit.strategy.base import Signal

UTC = dt.UTC
D = Decimal
VERSATZ = 3 * 3600
STARTKURSE = {"EURUSD": 1.1, "USDJPY": 110.0, "GBPUSD": 1.3, "CHFJPY": 112.0, "CADJPY": 85.0, "AUDUSD": 0.72, "NZDUSD": 0.68}
SPREADS = {"EURUSD": 2, "USDJPY": 3, "GBPUSD": 4, "CHFJPY": 9, "CADJPY": 8, "AUDUSD": 3, "NZDUSD": 4}
MONTAG = int(dt.datetime(2015, 1, 4, 21, 0, tzinfo=UTC).timestamp())        # So 21:00 UTC = Mo 00:00 Serverzeit


def offen(t: int) -> bool:
    """Markt offen (Serverzeit Mo–Fr)."""
    return dt.datetime.fromtimestamp(t + VERSATZ, UTC).weekday() < 5


def _runden(x: float, symbol: str) -> Decimal:
    stellen = D("0.001") if symbol.endswith("JPY") else D("0.00001")
    return D(repr(x)).quantize(stellen, rounding=ROUND_HALF_EVEN)


def h1_reihe(symbol: str, *, start: int = MONTAG, stunden: int = 24 * 7 * 6, saat: int = 1, sigma: float = 0.0012,
             spread: int | None = None, drift: float = 0.0, luecken: float = 0.0) -> list[Bar]:
    """H1-Kerzen (Bid) eines Zufallspfads über `stunden` Kalenderstunden; geschlossene Stunden ohne Kerze. sigma = relative
    Schwankung je Stunde; luecken = Anteil zufällig fehlender Kerzen (Datenlücken)."""
    rng = random.Random(f"{symbol}-{saat}")
    kurs = STARTKURSE.get(symbol, 1.0)
    sp = SPREADS.get(symbol, 3) if spread is None else spread
    aus: list[Bar] = []
    for h in range(stunden):
        t = start + h * 3600
        if not offen(t):
            continue
        schritte = [kurs]
        for _ in range(6):
            schritte.append(schritte[-1] * math.exp(rng.gauss(drift / 6, sigma / math.sqrt(6))))
        kurs = schritte[-1]
        if luecken and rng.random() < luecken:
            continue
        o, c = _runden(schritte[0], symbol), _runden(schritte[-1], symbol)
        hi, lo = _runden(max(schritte), symbol), _runden(min(schritte), symbol)
        aus.append(Bar(symbol, t, o, max(hi, o, c), min(lo, o, c), c, sp + rng.randint(0, 2)))
    return aus


def verdichten(h1: list[Bar], sekunden: int) -> list[Bar]:
    """H1 → H4/D1 auf Servergrenzen ((t + Versatz) mod Dauer = 0); Spread = Minimum der Teilkerzen."""
    gruppen: dict[int, list[Bar]] = {}
    for b in h1:
        beginn = (b.time + VERSATZ) // sekunden * sekunden - VERSATZ
        gruppen.setdefault(beginn, []).append(b)
    return [Bar(g[0].symbol, t, g[0].open, max(b.high for b in g), min(b.low for b in g), g[-1].close, min(b.spread_points for b in g))
            for t, g in sorted(gruppen.items())]


def markt(symbole=tuple(STARTKURSE), *, wochen: int = 6, saat: int = 1, sigma: float = 0.0012, luecken: float = 0.0) -> dict[str, list[Bar]]:
    return {s: h1_reihe(s, stunden=24 * 7 * wochen, saat=saat, sigma=sigma, luecken=luecken) for s in symbole}


class FesteSignale:
    """Teststrategie: liefert genau die vorgegebenen Signale (Symbol, Kerzenbeginn) → (Richtung, SL-Ticks, TP-Ticks) relativ zum
    Einstiegskurs e (Kauf Ask, Verkauf Bid) – für Handrechnungen und Mutationstests."""

    def __init__(self, plan: dict[tuple[str, int], tuple[Side, int, int]], *, symbole=("EURUSD",), zeitrahmen: str = "H1",
                 rueckblick: int = 3, max_halte_s: float | None = None, name: str = "TEST-FEST") -> None:
        self._plan = plan
        self.symbole = tuple(symbole)
        self.zeitrahmen = zeitrahmen
        self.rueckblick = rueckblick
        self.max_halte_s = max_halte_s
        self.name = name

    def parameter(self) -> dict:
        return {"plan": len(self._plan)}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        if len(kerzen) < self.rueckblick:
            return None
        k = kerzen[-1]
        p = self._plan.get((symbol, k.time))
        if p is None:
            return None
        side, sl_ticks, tp_ticks = p
        pt = D("0.001") if symbol.endswith("JPY") else D("0.00001")
        e = k.close + k.spread_points * pt if side is Side.BUY else k.close
        return Signal(symbol, side, e - side.sign * sl_ticks * pt, e + side.sign * tp_ticks * pt, k.time, "test")


class Zufallsrichtung:
    """Teststrategie ohne Idee: alle `abstand` Kerzen ein Signal mit Richtung aus einem Hash der Kerzenzeit, feste Abstände."""

    def __init__(self, *, symbole=("EURUSD",), abstand: int = 3, sl_ticks: int = 400, tp_ticks: int = 400, max_halte_s: float = 3 * 3600,
                 saat: int = 7) -> None:
        self.symbole = tuple(symbole)
        self.zeitrahmen = "H1"
        self.rueckblick = 3
        self.abstand = abstand
        self.sl_ticks, self.tp_ticks = sl_ticks, tp_ticks
        self.max_halte_s = max_halte_s
        self.saat = saat
        self.name = "TEST-ZUFALL"

    def parameter(self) -> dict:
        return {"abstand": self.abstand, "sl": self.sl_ticks, "tp": self.tp_ticks, "saat": self.saat}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        if len(kerzen) < self.rueckblick:
            return None
        k = kerzen[-1]
        if (k.time // 3600) % self.abstand:
            return None
        side = Side.BUY if random.Random(f"{self.saat}-{symbol}-{k.time}").random() < 0.5 else Side.SELL
        pt = D("0.001") if symbol.endswith("JPY") else D("0.00001")
        e = k.close + k.spread_points * pt if side is Side.BUY else k.close
        return Signal(symbol, side, e - side.sign * self.sl_ticks * pt, e + side.sign * self.tp_ticks * pt, k.time, "zufall")


def synthetische_db(pfad, *, start: int, wochen: int, saat: int = 1, sigma: float = 0.0012) -> dict[str, list[Bar]]:
    """SQLite im Format von kit.research.daten (Abzüge H1/H4/D1 mit Status OK und Hash) aus synthetischen Kerzen – für die
    Ende-zu-Ende-Prüfung der Auswertung ohne echte Kursdaten. Gespeichert wird wie beim echten Abzug in Serverzeit (UTC + 3 h);
    zurück kommen die Kerzen in UTC."""
    from kit.research import daten
    h1 = {s: h1_reihe(s, start=start, stunden=24 * 7 * wochen, saat=saat, sigma=sigma) for s in STARTKURSE}
    con = daten._db(pfad)
    with con:
        for tf, sek in (("H1", 3600), ("H4", 14400), ("D1", 86400)):
            for s, bars in h1.items():
                reihe = bars if tf == "H1" else verdichten(bars, sek)
                server = [Bar(b.symbol, b.time + VERSATZ, b.open, b.high, b.low, b.close, b.spread_points) for b in reihe]
                cur = con.execute("INSERT INTO abzug (gezogen, symbol, zeitrahmen, start, ende, anzahl, erster, letzter, sha256, status) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)", ("synthetisch", s, tf, "2010-01-01", "2021-06-30", len(reihe),
                                                                    daten._iso(server[0].time), daten._iso(server[-1].time),
                                                                    daten.kerzen_hash(server), "OK"))
                con.executemany("INSERT INTO kerze VALUES (?,?,?,?,?,?,?)",          # gespeichert wie der echte Abzug: Serverzeit
                                [(cur.lastrowid, b.time + VERSATZ, str(b.open), str(b.high), str(b.low), str(b.close), b.spread_points)
                                 for b in reihe])
    con.close()
    return h1
