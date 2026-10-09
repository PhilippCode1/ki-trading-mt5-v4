"""Nur-Lese-Hülle: check/send sind verboten (Rauchtest, Datenabzug)."""
from __future__ import annotations

from typing import Any

from kit.domain.types import OrderRequest


class ReadOnlyTerminal:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name in ("check", "send", "order_send", "order_check"):
            raise PermissionError(f"{name} ist im Nur-Lese-Modus verboten")
        return getattr(self._inner, name)

    def check(self, req: OrderRequest) -> None:
        raise PermissionError("check ist im Nur-Lese-Modus verboten")

    def send(self, req: OrderRequest) -> None:
        raise PermissionError("send ist im Nur-Lese-Modus verboten")
