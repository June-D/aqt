from __future__ import annotations

from typing import Optional

import httpx

from backend.app.core.config import get_settings
from backend.app.core.runtime import runtime_state
from backend.app.domain.models import (
    AccountSnapshot,
    OrderRequest,
    OrderStatus,
    PositionView,
    SubmitResult,
)
from backend.app.gateway.base import Gateway


class RemoteXtQuantGateway(Gateway):
    """HTTP client talking to Windows XQA agent."""

    name = "remote_xtquant"

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.gateway_url).rstrip("/")
        self.token = token or settings.gateway_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def submit_order(self, req: OrderRequest) -> SubmitResult:
        if not runtime_state.live_trading_enabled:
            return SubmitResult(
                success=False,
                status=OrderStatus.REJECTED,
                message="live_trading_enabled=false; refuse remote live order",
            )
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.base_url}/orders",
                    headers=self._headers(),
                    json=req.model_dump(mode="json"),
                )
                resp.raise_for_status()
                data = resp.json()
                return SubmitResult.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            return SubmitResult(
                success=False,
                status=OrderStatus.REJECTED,
                message=f"remote agent unreachable: {exc}",
            )

    def cancel_order(self, order_id: str) -> SubmitResult:
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.base_url}/orders/{order_id}/cancel",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return SubmitResult.model_validate(resp.json())
        except Exception as exc:  # noqa: BLE001
            return SubmitResult(success=False, message=f"cancel failed: {exc}")

    def query_positions(self) -> list[PositionView]:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{self.base_url}/positions", headers=self._headers())
            resp.raise_for_status()
            return [PositionView.model_validate(x) for x in resp.json()]

    def query_account(self) -> AccountSnapshot:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{self.base_url}/account", headers=self._headers())
            resp.raise_for_status()
            return AccountSnapshot.model_validate(resp.json())

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/health", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                data["gateway"] = self.name
                return data
        except Exception as exc:  # noqa: BLE001
            return {"gateway": self.name, "ok": False, "error": str(exc)}