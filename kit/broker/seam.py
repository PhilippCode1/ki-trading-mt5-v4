"""Die einzige Naht zum Broker. Echtes MT5, MT5-Attrappe und Historien-SIM erfüllen dasselbe Protokoll."""
from __future__ import annotations

from typing import Protocol

from kit.domain.types import (
    AccountSnapshot,
    Bar,
    CheckResult,
    Deal,
    OrderRequest,
    PendingOrder,
    Position,
    Quote,
    SendResult,
    SymbolSpec,
)


class BrokerFehler(RuntimeError):
    """Terminal nicht erreichbar oder unerwartete Antwort (z. B. copy_rates None)."""


class Terminal(Protocol):
    def account(self) -> AccountSnapshot: ...

    def symbol(self, name: str) -> SymbolSpec: ...

    def quote(self, name: str) -> Quote: ...

    def bars(self, name: str, timeframe: str, start: int, ende: int) -> list[Bar]: ...

    def positions(self) -> list[Position]: ...

    def orders(self) -> list[PendingOrder]: ...

    def deals(self, seit: int, bis: int) -> list[Deal]: ...

    def check(self, req: OrderRequest) -> CheckResult: ...

    def send(self, req: OrderRequest) -> SendResult | None:
        """Einzige schreibende Methode. None = Ausgang unbekannt (MT5 order_send liefert None)."""
        ...

    def zeit(self) -> float:
        """Serverzeit in Sekunden (SIM: simulierte Uhr)."""
        ...
