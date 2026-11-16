from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.app.domain.models import AccountSnapshot, OrderRequest, PositionView, SubmitResult


class Gateway(ABC):
    name: str = "base"

    @abstractmethod
    def submit_order(self, req: OrderRequest) -> SubmitResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> SubmitResult:
        raise NotImplementedError

    @abstractmethod
    def query_positions(self) -> list[PositionView]:
        raise NotImplementedError

    @abstractmethod
    def query_account(self) -> AccountSnapshot:
        raise NotImplementedError

    def health(self) -> dict:
        return {"gateway": self.name, "ok": True}