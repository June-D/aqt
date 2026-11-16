"""XQA execution agent.

Deploy on Windows with broker terminal + xtquant.
Control plane talks via RemoteXtQuantGateway.
Without xtquant, endpoints stay healthy and reject live orders with a clear reason.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from agent.xt_adapter import xt_adapter

APP_TOKEN = os.getenv("GATEWAY_TOKEN", "change-me")

app = FastAPI(title="XQA", version="0.2.0")


class OrderIn(BaseModel):
    symbol: str
    side: str
    quantity: int = Field(gt=0)
    price: Optional[float] = None
    strategy_id: Optional[str] = None
    reason: str = ""


def auth(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != APP_TOKEN:
        raise HTTPException(403, "invalid token")


@app.get("/health")
def health(_: None = Depends(auth)) -> dict[str, Any]:
    h = xt_adapter.health()
    h["ok"] = True
    h["service"] = "xqa"
    h["wired"] = bool(h.get("xtquant_imported") and h.get("account_id_configured") and h.get("userdata_configured"))
    return h


@app.post("/orders")
def place_order(body: OrderIn, _: None = Depends(auth)) -> dict[str, Any]:
    return xt_adapter.place_order(body.symbol, body.side, body.quantity, body.price, body.reason)


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, _: None = Depends(auth)) -> dict[str, Any]:
    return xt_adapter.cancel(order_id)


@app.get("/positions")
def positions(_: None = Depends(auth)) -> list[dict[str, Any]]:
    return xt_adapter.positions()


@app.get("/account")
def account(_: None = Depends(auth)) -> dict[str, Any]:
    return xt_adapter.account()


def run() -> None:
    import uvicorn

    host = os.getenv("AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT", "8100"))
    uvicorn.run("agent.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
