"""Grenzen fürs ganze Konto (Plan F-1 §4–§5): Tagesbudget/Tagesstopp, LOSS_LOCK, 50-%-Stopp, 95-%-Zähler, Tradebuch.

- Tagesanker = Equity beim ersten Takt des Servertags; Ein-/Auszahlungen verschieben Anker (nie als Gewinn/Verlust).
- Einstieg nur, wenn Verlust bis SL der neuen Position + Restrisiko aller offenen Positionen ≤ Budget% × Anker − heutiger Verlust.
- Tagesstopp: Equity ≤ Anker × (1 − Budget%) → keine Einstiege bis zum nächsten Servertag (Positionen behalten SL/TP).
- LOSS_LOCK: Equity ≤ LOSS-Anker × (1 − 25 %) → alle eigenen Positionen schließen + Sperre (Aufheben nur Betreiber).
- Zählregeln (eingefroren, config/tore.toml): Trade = Strategieposition von Eröffnung bis vollständiger Schließung; Ergebnis =
  Summe aller Deals der Position (inkl. Kommission, Swap, Gebühren); Gewinn nur > 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from kit.domain.types import ZERO, Namensraum
from kit.orders import ids

HUNDERT = Decimal(100)


def budget(anker: Decimal, equity: Decimal, prozent: Decimal) -> Decimal:
    """Noch erlaubter Verlust heute (kann negativ sein)."""
    return anker * prozent / HUNDERT - max(ZERO, anker - equity)


def tagesstopp(anker: Decimal, equity: Decimal, prozent: Decimal) -> bool:
    return anker > ZERO and equity <= anker * (1 - prozent / HUNDERT)


def loss_lock(anker: Decimal, equity: Decimal, prozent: Decimal) -> bool:
    return anker > ZERO and equity <= anker * (1 - prozent / HUNDERT)


@dataclass
class Trade:
    position_id: int
    symbol: str
    namensraum: Namensraum
    seq_auf: int
    t_auf: int
    lots_ein: Decimal = ZERO
    lots_aus: Decimal = ZERO
    ergebnis: Decimal = ZERO
    t_zu: int = 0
    gruende: list[str] = field(default_factory=list)

    @property
    def geschlossen(self) -> bool:
        return self.lots_ein > ZERO and self.lots_aus >= self.lots_ein

    @property
    def gewinn(self) -> bool:
        return self.ergebnis > ZERO


class Tradebuch:
    """Trades aus den DEAL-Sätzen des Journals (Replay = Laufzeit)."""

    def __init__(self) -> None:
        self.trades: dict[int, Trade] = {}

    def deal(self, satz: dict) -> Trade | None:
        d = satz.get("daten", {})
        if satz.get("art") != "DEAL" or d.get("deal_art") != "HANDEL":
            return None
        pid = int(d["position_id"])
        t = self.trades.get(pid)
        lots = Decimal(str(d["volumen"]))
        if t is None:
            ns = ids.namensraum(int(d["magic"]))
            if ns is None or d["entry"] not in ("IN", "INOUT"):
                return None                              # fremd oder ohne beobachtete Eröffnung
            t = self.trades[pid] = Trade(pid, d["symbol"], ns, int(satz["seq"]), int(d["zeit"]))
        if d["entry"] == "IN":
            t.lots_ein += lots
        elif d["entry"] in ("OUT", "OUT_BY"):
            t.lots_aus += lots
        t.ergebnis += Decimal(str(d["geld"]))
        t.gruende.append(str(d["reason"]))
        if t.geschlossen and not t.t_zu:
            t.t_zu = int(d["zeit"])
        return t

    def geschlossene(self, namensraum: Namensraum = Namensraum.STRATEGIE, ab_seq: int = 0) -> list[Trade]:
        return sorted((t for t in self.trades.values() if t.namensraum is namensraum and t.geschlossen and t.seq_auf > ab_seq),
                      key=lambda t: (t.t_zu, t.position_id))


def quote(trades: list[Trade]) -> Decimal:
    return Decimal(sum(1 for t in trades if t.gewinn)) / len(trades) if trades else ZERO


def stop50(trades: list[Trade], fenster: int, ab: int, quote_max: Decimal) -> tuple[bool, Decimal, int]:
    """(ausgelöst, Quote im Fenster, Anzahl im Fenster): ab `ab` Trades Quote der letzten min(n, fenster) ≤ quote_max."""
    if len(trades) < ab:
        return False, quote(trades), len(trades)
    letzte = trades[-fenster:]
    q = quote(letzte)
    return q <= quote_max, q, len(letzte)


def stand95(trades: list[Trade]) -> dict:
    gewinne = sum((t.ergebnis for t in trades if t.ergebnis > ZERO), ZERO)
    verluste = -sum((t.ergebnis for t in trades if t.ergebnis <= ZERO), ZERO)
    return {"trades": len(trades), "gewinner": sum(1 for t in trades if t.gewinn), "quote": str(quote(trades)),
            "gewinnfaktor": str(gewinne / verluste) if verluste > ZERO else ("unendlich" if gewinne > ZERO else "0"),
            "erster": trades[0].t_auf if trades else None, "letzter": trades[-1].t_zu if trades else None}
