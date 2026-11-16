from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.core.calendar import session_open
from backend.app.core.config import load_yaml_config
from backend.app.core.logging import logger
from backend.app.core.runtime import runtime_state
from backend.app.data.market_data import market_data
from backend.app.domain.models import OrderRequest, Side
from backend.app.gateway.factory import build_gateway
from backend.app.intel.llm_client import predict_from_news
from backend.app.intel.news_fetch import collect_news
from backend.app.intel.sizing import plan_orders
from backend.app.models import (
    IntelPredictionRow,
    IntelRunRow,
    NewsItemRow,
    OrderRow,
    SystemStateRow,
)
from backend.app.services.alerts import emit_alert
from backend.app.services.hot_universe import effective_whitelist, refresh_hot_pool
from backend.app.services.trading import TradingService


def _intel_cfg() -> dict:
    from backend.app.intel.sizing import _intel_cfg as _merged

    return _merged()


def intel_enabled(db: Session) -> bool:
    row = db.get(SystemStateRow, "intel_enabled")
    if row and isinstance(row.value, dict) and "enabled" in row.value:
        return bool(row.value.get("enabled"))
    return bool(_intel_cfg().get("enabled", False))


def set_intel_enabled(db: Session, enabled: bool) -> None:
    row = db.get(SystemStateRow, "intel_enabled")
    if row is None:
        db.add(SystemStateRow(key="intel_enabled", value={"enabled": enabled}))
    else:
        row.value = {"enabled": enabled}
    db.commit()


def run_intel_cycle(db: Session, force: bool = False) -> dict[str, Any]:
    cfg = _intel_cfg()
    if not force and not intel_enabled(db):
        return {"ok": False, "message": "情报交易未开启"}

    # 先刷新东财热点池，再合并手工白名单
    refresh_hot_pool(db)
    whitelist = effective_whitelist(db)
    if cfg.get("require_whitelist", True) and not whitelist:
        msg = "交易池为空：热点池拉取失败且 risk.whitelist 为空，请检查网络或配置"
        emit_alert(db, "warn", "情报交易未执行", msg)
        run = IntelRunRow(status="BLOCKED", message=msg)
        db.add(run)
        db.commit()
        return {"ok": False, "message": msg}

    gateway = build_gateway(db)
    # LIVE 全自动：remote 网关必须开 LIVE；sim 可在模拟盘跑通
    if gateway.name != "sim" and not runtime_state.live_trading_enabled:
        msg = "LIVE 未开启，远程网关拒绝情报下单"
        run = IntelRunRow(status="BLOCKED", message=msg)
        db.add(run)
        db.commit()
        return {"ok": False, "message": msg}

    run = IntelRunRow(status="RUNNING", message=f"交易池 {len(whitelist)} 只，抓取新闻中")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        news = collect_news(
            limit=int(cfg.get("max_news_per_run", 40)),
            focus_symbols=whitelist,
        )
        stored = 0
        for n in news:
            exists = db.query(NewsItemRow).filter(NewsItemRow.fingerprint == n["fingerprint"]).first()
            if exists:
                if n.get("published_at") and exists.published_at != n.get("published_at"):
                    exists.published_at = n["published_at"]
                continue
            db.add(
                NewsItemRow(
                    source=n["source"],
                    title=n["title"],
                    summary=n.get("summary") or "",
                    url=n.get("url") or "",
                    published_at=n.get("published_at"),
                    fingerprint=n["fingerprint"],
                )
            )
            stored += 1
        db.commit()
        run.news_count = len(news)

        if not news:
            run.status = "DONE"
            run.message = "未抓到新闻"
            db.commit()
            return {"ok": True, "run_id": run.id, "message": run.message, "orders": []}

        preds = predict_from_news(db, news, focus_symbols=whitelist)
        # 交易池过滤
        if whitelist:
            preds = [p for p in preds if p["symbol"] in whitelist]

        can_trade = session_open()
        order_count = 0
        results: list[dict[str, Any]] = []

        if not can_trade:
            for p in preds:
                db.add(
                    IntelPredictionRow(
                        run_id=run.id,
                        symbol=p["symbol"],
                        direction=p["direction"],
                        confidence=p["confidence"],
                        sector=p.get("sector") or "",
                        reason=p.get("reason") or "",
                        action="PREDICT_ONLY",
                    )
                )
            run.pred_count = len(preds)
            run.order_count = 0
            run.status = "DONE"
            run.message = f"盘外仅预测：新闻{len(news)} 入库{stored} 预测{len(preds)} 下单0"
            run.detail = {"results": [], "trade_skipped": "off_session"}
            db.commit()
            logger.info("intel run #%s %s", run.id, run.message)
            return {
                "ok": True,
                "run_id": run.id,
                "message": run.message,
                "orders": [],
                "predictions": preds,
                "news_count": len(news),
            }

        cooldown = int(cfg.get("reopen_cooldown_minutes", 30))
        since = datetime.utcnow() - timedelta(minutes=cooldown)
        recent_buys = {
            r.symbol
            for r in db.query(OrderRow)
            .filter(OrderRow.strategy_id == "intel_llm", OrderRow.side == "BUY", OrderRow.created_at >= since)
            .filter(OrderRow.status.in_(["SUBMITTED", "FILLED", "PARTIAL"]))
            .all()
        }
        preds = [p for p in preds if not (p["direction"] == "UP" and p["symbol"] in recent_buys)]

        account = gateway.query_account()
        positions = gateway.query_positions()
        prices = {p["symbol"]: float(market_data.latest_price(p["symbol"]) or 0) for p in preds}
        for pos in positions:
            prices.setdefault(pos.symbol, float(pos.market_price or market_data.latest_price(pos.symbol) or 0))

        planned = plan_orders(preds, account.cash, account.total_equity, positions, prices)
        trading = TradingService(db, gateway)

        pred_by_symbol = {p["symbol"]: p for p in preds}
        for plan in planned:
            base = pred_by_symbol.get(plan.symbol) or {
                "direction": "UP" if plan.side == "BUY" else "DOWN",
                "confidence": plan.confidence,
                "sector": plan.sector,
                "reason": plan.reason,
            }
            pred_row = IntelPredictionRow(
                run_id=run.id,
                symbol=plan.symbol,
                direction=base.get("direction") or ("UP" if plan.side == "BUY" else "DOWN"),
                confidence=float(base.get("confidence") or plan.confidence),
                sector=str(base.get("sector") or plan.sector),
                reason=str(base.get("reason") or plan.reason),
                action=plan.side,
            )
            req = OrderRequest(
                symbol=plan.symbol,
                side=Side.BUY if plan.side == "BUY" else Side.SELL,
                quantity=plan.quantity,
                price=prices.get(plan.symbol),
                strategy_id="intel_llm",
                reason=plan.reason[:200],
            )
            result = trading.place_order(req)
            pred_row.order_id = result.order_id
            if result.success:
                order_count += 1
                pred_row.action = f"{plan.side}_OK"
            else:
                pred_row.action = f"{plan.side}_REJECT"
                pred_row.reason = f"{pred_row.reason} | {result.message}"
            db.add(pred_row)
            results.append(
                {
                    "symbol": plan.symbol,
                    "side": plan.side,
                    "quantity": plan.quantity,
                    "success": result.success,
                    "message": result.message,
                    "order_id": result.order_id,
                }
            )

        planned_syms = {p.symbol for p in planned}
        for p in preds:
            if p["symbol"] in planned_syms:
                continue
            db.add(
                IntelPredictionRow(
                    run_id=run.id,
                    symbol=p["symbol"],
                    direction=p["direction"],
                    confidence=p["confidence"],
                    sector=p.get("sector") or "",
                    reason=p.get("reason") or "",
                    action="SKIP",
                )
            )

        run.pred_count = len(preds)
        run.order_count = order_count
        run.status = "DONE"
        run.message = f"新闻{len(news)} 入库{stored} 预测{len(preds)} 下单{order_count}"
        run.detail = {"results": results}
        db.commit()
        logger.info("intel run #%s %s", run.id, run.message)
        return {
            "ok": True,
            "run_id": run.id,
            "message": run.message,
            "orders": results,
            "predictions": preds,
            "news_count": len(news),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("intel cycle failed")
        run.status = "ERROR"
        run.message = str(exc)
        db.commit()
        emit_alert(db, "error", "情报交易失败", str(exc))
        return {"ok": False, "run_id": run.id, "message": str(exc)}
