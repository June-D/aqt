from __future__ import annotations

from itertools import product
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.logging import logger
from backend.app.domain.models import PositionView
from backend.app.gateway.base import Gateway
from backend.app.models import AccountSnapshotRow
from backend.app.services.alerts import emit_alert


def reconcile(db: Session, gateway: Gateway) -> dict[str, Any]:
    try:
        account = gateway.query_account()
        positions = gateway.query_positions()
    except Exception as exc:  # noqa: BLE001
        emit_alert(db, "error", "网关对账失败", str(exc), {"gateway": gateway.name})
        return {"ok": False, "error": str(exc)}

    snap = AccountSnapshotRow(
        cash=account.cash,
        market_value=account.market_value,
        total_equity=account.total_equity,
        daily_pnl=account.daily_pnl,
    )
    db.add(snap)
    db.commit()

    drift = _position_drift(positions)
    if drift:
        emit_alert(db, "warn", "持仓对账差异", "；".join(drift), {"items": drift})
    logger.info("reconcile ok gateway=%s equity=%s", gateway.name, account.total_equity)
    return {
        "ok": True,
        "gateway": gateway.name,
        "equity": account.total_equity,
        "positions": len(positions),
        "drift": drift,
    }


def _position_drift(positions: list[PositionView]) -> list[str]:
    issues = []
    for p in positions:
        if p.quantity < 0:
            issues.append(f"{p.symbol} 数量为负")
        if p.quantity % 100 != 0:
            issues.append(f"{p.symbol} 数量非整手")
    return issues


def param_grid(grid: dict[str, list], limit: int = 12) -> list[dict]:
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    combos = []
    for tuple_vals in product(*values):
        combos.append(dict(zip(keys, tuple_vals)))
        if len(combos) >= limit:
            break
    return combos
