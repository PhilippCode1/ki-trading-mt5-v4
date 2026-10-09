"""Typen des Geldpfads: Kontomodus, Aktionsart, Richtung, Versuchs- und Absichtszustände, Tickets, Deals (mit DEAL_REASON)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal(0)


class Mode(StrEnum):
    NETTING = "NETTING"
    EXCHANGE = "EXCHANGE"
    HEDGING = "HEDGING"


class Action(StrEnum):
    """Aktionsart (Retcode-Matrix, UNKNOWN-Regeln)."""

    ENTRY_DEAL = "ENTRY_DEAL"          # risikoerhöhender Markt-Deal (IOC/FOK) mit angehängtem SL
    REDUCE_DEAL = "REDUCE_DEAL"        # Abbau per Ticket (nie Reversal)
    PROTECT_SLTP = "PROTECT_SLTP"      # Positions-SL setzen/verschärfen
    PLACE_PENDING = "PLACE_PENDING"    # risikoerhöhende Pending-Order (nie auf Netting mit offener Position)
    CANCEL_PENDING = "CANCEL_PENDING"  # Pending-Order entfernen


INCREASING = frozenset({Action.ENTRY_DEAL, Action.PLACE_PENDING})
PROTECTIVE = frozenset({Action.REDUCE_DEAL, Action.PROTECT_SLTP, Action.CANCEL_PENDING})


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class AttemptStatus(StrEnum):
    JOURNALED = "JOURNALED"      # im Journal, Sendung angestoßen (Journal vor Netz)
    SENT = "SENT"                # Sendeaufruf erfolgt, keine Antwort
    DONE = "DONE"                # Broker meldet Ausführung (Deals folgen/sind da)
    PARTIAL = "PARTIAL"          # Teilausführung, Rest unbestätigt
    PLACED = "PLACED"            # Pending-Order liegt
    NOT_EXECUTED = "NOT_EXECUTED"  # Broker bestätigt Nichtausführung bzw. Negativnachweis
    UNKNOWN = "UNKNOWN"          # Ausgang unbekannt (Timeout/Verbindung/Fehler): Reservierung bleibt
    REFUSED = "REFUSED"          # lokal abgelehnt (PTC/Fencing/Journal), nie gesendet


OPEN_ATTEMPT = frozenset({AttemptStatus.JOURNALED, AttemptStatus.SENT, AttemptStatus.PARTIAL, AttemptStatus.UNKNOWN,
                          AttemptStatus.PLACED})


@dataclass
class Ticket:
    ticket_id: str
    symbol: str
    qty: Decimal          # vorzeichenbehaftet: + long, − short
    sl: Decimal           # 0 = kein Schutz
    origin: str = "OWN"   # OWN oder FOREIGN


@dataclass
class Intent:
    intent_id: str
    symbol: str
    action: Action
    side: Side
    qty: Decimal                  # Zielmenge (Betrag, Lots)
    reserved: Decimal             # Worst-Case-Reservierung in Lots (nur risikoerhöhend)
    filled: Decimal = ZERO
    status: str = "OPEN"          # OPEN, DONE, CLOSED
    alloc: tuple[tuple[str, Decimal], ...] = ()   # Strategiezuordnung (Anteile, Summe 1)
    ticket: str | None = None


@dataclass
class Attempt:
    attempt_id: str
    intent_id: str
    action: Action
    symbol: str
    side: Side
    qty: Decimal
    sl: Decimal
    epoch: int
    ticket: str | None = None
    order_type: str = "IOC"
    status: AttemptStatus = AttemptStatus.JOURNALED
    filled: Decimal = ZERO
    order_id: str | None = None
    retcode: int | None = None
    resolved_not_executed: bool = False
    cancel_reason: str | None = None   # CANCEL_PENDING: Stornogrund der Anfrage (L-MAR-XACCT R4, ptc.CANCEL_REASONS), sonst None


DEAL_REASON_SO = "DEAL_REASON_SO"   # Stop-out des Brokers (MQL5 ENUM_DEAL_REASON; Semantik ENTWURF bis zum Killer-Test, OI-022)
# Bekannte Werte von DEAL_REASON (MQL5 ENUM_DEAL_REASON); nur DEAL_REASON_SO hat eine eigene Semantik (Broker-Close-out), jeder andere
# Wert – auch DEAL_REASON_SL/TP – ändert an der Einordnung eines Deals ohne eigenen Versuch nichts (FOREIGN_ACTIVITY, strenger)
DEAL_REASONS = frozenset({"DEAL_REASON_CLIENT", "DEAL_REASON_MOBILE", "DEAL_REASON_WEB", "DEAL_REASON_EXPERT", "DEAL_REASON_SL",
                          "DEAL_REASON_TP", DEAL_REASON_SO, "DEAL_REASON_ROLLOVER", "DEAL_REASON_VMARGIN", "DEAL_REASON_SPLIT",
                          "DEAL_REASON_CORPORATE_ACTION"})


@dataclass(frozen=True)
class Deal:
    """Brokerbeobachtung (autoritativ für Bestände)."""

    deal_id: str
    symbol: str
    side: Side
    qty: Decimal
    entry: str                # IN, OUT, INOUT, OUT_BY
    ticket: str               # Positions-ID
    cash: Decimal = ZERO      # Gewinn/Verlust + Gebühren in Kontowährung
    fee: Decimal = ZERO
    attempt_id: str | None = None   # aus Kommentar/Magic zugeordnet; None = unbekannt
    order_sl: Decimal | None = None  # SL der auslösenden Order (Netting übernimmt ihn für die Position)
    reason: str | None = None        # DEAL_REASON des Brokers (z. B. DEAL_REASON_SO); None = nicht geliefert (strengere Einordnung)


@dataclass
class Incident:
    kind: str
    detail: str
    t: int = 0


@dataclass
class Journal:
    """Nur anhängendes Journal (Eingaben + abgeleitete Sendungen); fällt es aus, gilt nur das Notfalljournal."""

    entries: list[dict] = field(default_factory=list)
    emergency: list[dict] = field(default_factory=list)
    ok: bool = True
