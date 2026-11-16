from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.money import round_money
from backend.app.data.market_data import market_data
from backend.app.domain.models import OrderRequest, Side
from backend.app.gateway.factory import build_gateway
from backend.app.models import AccountSnapshotRow, FillRow, IntelPredictionRow, OrderRow, PositionRow
from backend.app.services.risk_alerts import emit_risk_alert
from backend.app.services.settings_service import get_settings_view
from backend.app.services.trading import TradingService


def _quote_configured(db: Session) -> bool:
    md = get_settings_view(db).get("market_data") or {}
    provider = str(md.get("provider") or "ifind")
    if provider == "ifind":
        return bool(str((md.get("ifind") or {}).get("refresh_token") or "").strip())
    if provider == "alltick":
        return bool(str((md.get("alltick") or {}).get("token") or "").strip())
    if provider == "tushare":
        return bool(str((md.get("tushare") or {}).get("token") or "").strip())
    return False


def account_overview(db: Session) -> dict[str, Any]:
    gateway = build_gateway(db)
    acct = gateway.query_account()
    positions = gateway.query_positions()
    quote_ok = _quote_configured(db)
    # SIM 可用 market_data.latest_price；未配置 AllTick 时仍可能有 akshare 价，
    # 但按规格：未配置行情源则盈亏相关显式 quote_status
    fills = db.query(FillRow).order_by(FillRow.id.asc()).all()
    fees = sum(float(f.commission or 0) + float(f.stamp_tax or 0) for f in fills)

    if not quote_ok:
        return {
            "total_equity": round_money(acct.total_equity),
            "cash": round_money(acct.cash),
            "market_value": round_money(acct.market_value),
            "daily_pnl": None,
            "month_pnl": None,
            "total_pnl": None,
            "fees": round_money(fees),
            "quote_status": "unconfigured",
            "positions": [p.model_dump(mode="json") for p in positions],
        }

    unrealized = 0.0
    for p in positions:
        unrealized += (p.market_price - p.avg_cost) * p.quantity

    # 已实现：成交流水粗算（卖出收入 - 买入成本）近似累计
    buy_cost = 0.0
    sell_rev = 0.0
    tz = ZoneInfo(load_yaml_config().get("market", {}).get("timezone", "Asia/Shanghai"))
    now = datetime.now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_realized = 0.0
    month_realized = 0.0
    for f in fills:
        notional = float(f.price) * int(f.quantity)
        created = f.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=tz)
        if f.side == "BUY":
            buy_cost += notional
        else:
            sell_rev += notional
        if created and created >= day_start and f.side == "SELL":
            day_realized += notional - float(f.commission or 0) - float(f.stamp_tax or 0)
        if created and created >= month_start and f.side == "SELL":
            month_realized += notional - float(f.commission or 0) - float(f.stamp_tax or 0)

    initial = float(get_settings().initial_cash)
    sim = get_settings_view(db).get("sim") or {}
    if sim.get("initial_cash") is not None:
        initial = float(sim["initial_cash"])
    total_pnl = float(acct.total_equity) - initial
    # 当日：浮动相对成本的当日盯市 + 账户快照 daily_pnl
    daily_pnl = float(acct.daily_pnl or 0.0) + unrealized
    month_pnl = month_realized + unrealized

    pos_out = []
    for p in positions:
        pnl = (p.market_price - p.avg_cost) * p.quantity
        pnl_pct = (p.market_price / p.avg_cost - 1.0) if p.avg_cost else 0.0
        pos_out.append(
            {
                **p.model_dump(mode="json"),
                "pnl": round_money(pnl),
                "pnl_pct": pnl_pct,
                "quote_status": "ok",
            }
        )

    return {
        "total_equity": round_money(acct.total_equity),
        "cash": round_money(acct.cash),
        "market_value": round_money(acct.market_value),
        "daily_pnl": round_money(daily_pnl),
        "month_pnl": round_money(month_pnl),
        "total_pnl": round_money(total_pnl),
        "fees": round_money(fees),
        "quote_status": "ok",
        "positions": pos_out,
    }


def liquidate_positions(
    db: Session,
    confirm: bool,
    symbol: Optional[str] = None,
) -> dict[str, Any]:
    if not confirm:
        return {"success": False, "message": "需要 confirm=true", "sold_count": 0}
    gateway = build_gateway(db)
    trading = TradingService(db, gateway)
    positions = gateway.query_positions()
    if symbol:
        positions = [p for p in positions if p.symbol == symbol]
    positions = [p for p in positions if p.quantity > 0]
    if not positions:
        return {"success": False, "message": "无持仓可抛售", "sold_count": 0}

    sold = 0
    errors = []
    for p in positions:
        price = market_data.latest_price(p.symbol) or p.market_price or p.avg_cost
        result = trading.place_order(
            OrderRequest(
                symbol=p.symbol,
                side=Side.SELL,
                quantity=p.quantity,
                price=float(price),
                reason="liquidate",
                strategy_id="manual",
            )
        )
        if result.success:
            sold += 1
        else:
            errors.append({"symbol": p.symbol, "message": result.message})
            emit_risk_alert(
                db,
                event_type="LIQUIDATE_FAIL",
                message=result.message or "抛售失败",
                symbol=p.symbol,
                level="error",
                title="一键抛售失败",
            )

    emit_risk_alert(
        db,
        event_type="LIQUIDATE",
        message=f"抛售完成 sold={sold} errors={len(errors)}",
        level="info",
        title="一键抛售",
        detail={"sold": sold, "errors": errors, "symbol": symbol},
    )
    return {
        "success": sold > 0,
        "sold_count": sold,
        "errors": errors,
        "message": "ok" if sold > 0 else (errors[0]["message"] if errors else "抛售失败"),
    }


def symbol_ledger(db: Session, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
    orders = (
        db.query(OrderRow)
        .filter(OrderRow.symbol == symbol)
        .order_by(OrderRow.created_at.desc())
        .limit(limit)
        .all()
    )
    fills = (
        db.query(FillRow)
        .filter(FillRow.symbol == symbol)
        .order_by(FillRow.created_at.desc())
        .limit(limit)
        .all()
    )
    preds = (
        db.query(IntelPredictionRow)
        .filter(IntelPredictionRow.symbol == symbol)
        .order_by(IntelPredictionRow.created_at.desc())
        .limit(limit)
        .all()
    )
    items: list[dict[str, Any]] = []
    for o in orders:
        items.append(
            {
                "kind": "order",
                "id": o.id,
                "side": o.side,
                "quantity": o.quantity,
                "price": o.price,
                "status": o.status,
                "reason": o.reason,
                "message": o.message,
                "created_at": o.created_at,
            }
        )
    for f in fills:
        items.append(
            {
                "kind": "fill",
                "id": f"fill-{f.id}",
                "side": f.side,
                "quantity": f.quantity,
                "price": f.price,
                "status": "FILLED",
                "reason": "fill",
                "message": "",
                "created_at": f.created_at,
            }
        )
    for p in preds:
        items.append(
            {
                "kind": "prediction",
                "id": f"pred-{p.id}",
                "side": p.direction,
                "quantity": None,
                "price": None,
                "status": p.action,
                "reason": p.reason,
                "message": f"confidence={p.confidence}",
                "created_at": p.created_at,
            }
        )
    items.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
    return items[:limit]


def reset_sim_ledger(db: Session, initial_cash: float) -> None:
    db.query(FillRow).delete()
    db.query(OrderRow).delete()
    db.query(PositionRow).delete()
    db.query(AccountSnapshotRow).delete()
    db.add(
        AccountSnapshotRow(
            cash=float(initial_cash),
            market_value=0.0,
            total_equity=float(initial_cash),
            daily_pnl=0.0,
        )
    )
    db.commit()
