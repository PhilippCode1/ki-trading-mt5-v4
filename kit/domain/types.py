"""Typen des Geldpfads (Herkunft: v4 reference/moneypath/types.py und mt5-trading-ai venue/protocol.py, für einen Betreiber
zusammengeführt). Preise, Volumina und Geld sind Decimal; Signale/Statistik dürfen float rechnen, nie der Geldpfad."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal(0)


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class Action(StrEnum):
    """Aktionsart (Spalten der Retcode-Matrix registers/retcodes.json)."""

    ENTRY_DEAL = "ENTRY_DEAL"          # risikoerhöhender Markt-Deal mit SL (und TP) im Auftrag
    REDUCE_DEAL = "REDUCE_DEAL"        # Abbau per Positions-Ticket (nie freie Gegenorder)
    PROTECT_SLTP = "PROTECT_SLTP"      # SL/TP einer Position setzen bzw. enger ziehen
    PLACE_PENDING = "PLACE_PENDING"    # risikoerhöhende Pending-Order (nur Probe-Skripte)
    CANCEL_PENDING = "CANCEL_PENDING"  # Pending-Order löschen


RISIKO_ERHOEHEND = frozenset({Action.ENTRY_DEAL, Action.PLACE_PENDING})
SCHUETZEND = frozenset({Action.REDUCE_DEAL, Action.PROTECT_SLTP, Action.CANCEL_PENDING})


class Namensraum(StrEnum):
    STRATEGIE = "STRATEGIE"
    PROBE = "PROBE"


class KontoModus(StrEnum):
    NETTING = "NETTING"
    EXCHANGE = "EXCHANGE"
    HEDGING = "HEDGING"


class HandelsModus(StrEnum):
    DEMO = "DEMO"
    CONTEST = "CONTEST"
    REAL = "REAL"
    UNBEKANNT = "UNBEKANNT"


class OpStatus(StrEnum):
    GEPLANT = "GEPLANT"            # im Journal (fsync), noch nicht gesendet
    GESENDET = "GESENDET"          # Sendeaufruf läuft bzw. ohne Antwort
    ERLEDIGT = "ERLEDIGT"          # Ziel erreicht (Fill/SLTP gesetzt/Order gelöscht)
    TEILWEISE = "TEILWEISE"        # Teil-Fill, Rest unbestätigt (Reservierung bis Negativnachweis)
    ABGELEHNT = "ABGELEHNT"        # vom Broker abgelehnt bzw. Negativnachweis: nicht ausgeführt
    UNBEKANNT = "UNBEKANNT"        # Ausgang offen: Reservierung bleibt, keine Risikozunahme im Symbol
    LOKAL_ABGELEHNT = "LOKAL_ABGELEHNT"  # nie gesendet (Sperre, offene Operation, Prüfung)


OFFEN = frozenset({OpStatus.GEPLANT, OpStatus.GESENDET, OpStatus.TEILWEISE, OpStatus.UNBEKANNT})


class DealArt(StrEnum):
    HANDEL = "HANDEL"              # BUY/SELL
    KAPITAL = "KAPITAL"            # BALANCE (Ein-/Auszahlung), CREDIT, BONUS, CORRECTION
    GEBUEHR = "GEBUEHR"            # CHARGE, COMMISSION, Zinsen
    SONSTIGES = "SONSTIGES"


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    digits: int
    point: Decimal
    tick_size: Decimal
    tick_value: Decimal            # Wert eines Ticks je 1,0 Lot in Kontowährung
    contract_size: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    stops_level: int = 0           # Mindestabstand SL/TP in Points
    freeze_level: int = 0
    filling: str = "IOC"           # erlaubte Füllart (aus der Bitmaske abgeleitet)
    trade_mode: str = "FULL"       # Symbol-Handelsmodus (FULL, LONGONLY, SHORTONLY, CLOSEONLY, DISABLED)
    currency_profit: str = "USD"
    currency_base: str = "EUR"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    time_msc: int                  # Serverzeit in ms


@dataclass(frozen=True)
class Bar:
    symbol: str
    time: int                      # Serverzeit Kerzenbeginn (s)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    spread_points: int = 0
    is_closed: bool = True


@dataclass(frozen=True)
class OrderRequest:
    action: Action
    symbol: str
    side: Side
    volume: Decimal
    magic: int
    comment: str = ""
    sl: Decimal = ZERO             # 0 = kein SL (bei ENTRY_DEAL verboten)
    tp: Decimal = ZERO
    ticket: int | None = None      # Positions-Ticket (REDUCE/PROTECT) bzw. Order-Ticket (CANCEL)
    price: Decimal = ZERO          # 0 = Markt
    deviation: int = 20
    filling: str = "IOC"


@dataclass(frozen=True)
class CheckResult:
    retcode: int                   # 0 = Prüfung bestanden (MT5 order_check)
    comment: str = ""
    margin: Decimal = ZERO
    margin_free: Decimal = ZERO


@dataclass(frozen=True)
class SendResult:
    retcode: int
    order: int = 0
    deal: int = 0
    volume: Decimal = ZERO
    price: Decimal = ZERO
    comment: str = ""


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    side: Side
    volume: Decimal
    price_open: Decimal
    sl: Decimal
    tp: Decimal
    magic: int
    comment: str = ""
    time: int = 0                  # Eröffnung, Serverzeit (s)


@dataclass(frozen=True)
class PendingOrder:
    ticket: int
    symbol: str
    side: Side
    volume: Decimal
    price: Decimal
    sl: Decimal
    tp: Decimal
    magic: int
    comment: str = ""


@dataclass(frozen=True)
class Deal:
    ticket: int
    order: int
    position_id: int
    symbol: str
    side: Side | None              # None bei Nicht-Handelsdeals
    volume: Decimal
    price: Decimal
    entry: str                     # IN, OUT, INOUT, OUT_BY, NONE
    reason: str                    # CLIENT, MOBILE, WEB, EXPERT, SL, TP, SO, ROLLOVER, VMARGIN, SPLIT, …
    magic: int
    comment: str
    profit: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    time: int                      # Serverzeit (s)
    art: DealArt = DealArt.HANDEL

    @property
    def geld(self) -> Decimal:
        return self.profit + self.commission + self.swap + self.fee


@dataclass(frozen=True)
class AccountSnapshot:
    trade_mode: HandelsModus
    margin_mode: KontoModus
    currency: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    margin_free: Decimal
    margin_level: Decimal          # Prozent; 0 = keine Marge belegt
    leverage: int
    trade_allowed: bool            # Knopf „Algo Trading“ bzw. Kontofreigabe
    abdruck: str = ""              # HMAC des Kontos (nie die Nummer)


@dataclass
class Absicht:
    """Was eine Strategie, der Abgleich oder ein Kill will; die Größe ist bereits gerundet (Lots)."""

    absicht_id: str
    action: Action
    symbol: str
    side: Side
    volume: Decimal
    namensraum: Namensraum = Namensraum.STRATEGIE
    sl: Decimal = ZERO
    tp: Decimal = ZERO
    ticket: int | None = None
    grund: str = ""


@dataclass
class Operation:
    """Eine Orderoperation = eine journalisierte Absicht samt aller Sendeversuche (Zähleinheit von Tor T)."""

    op_id: str                     # = client_order_id (deterministisch)
    absicht: Absicht
    magic: int
    status: OpStatus = OpStatus.GEPLANT
    versuche: int = 0
    retcodes: list[int] = field(default_factory=list)
    t_geplant: float = 0.0
    t_gesendet: float = 0.0
    gefuellt: Decimal = ZERO
    deals: list[int] = field(default_factory=list)
    order: int = 0
    grund: str = ""                # bei LOKAL_ABGELEHNT/ABGELEHNT: Code der Ablehnung
    negativnachweis: bool = False

    @property
    def reserviert(self) -> Decimal:
        """Worst-Case-Reservierung in Lots: nur risikoerhöhend, solange der Ausgang nicht endgültig ist."""
        if self.absicht.action not in RISIKO_ERHOEHEND or self.status not in OFFEN:
            return ZERO
        return max(self.absicht.volume - self.gefuellt, ZERO)
