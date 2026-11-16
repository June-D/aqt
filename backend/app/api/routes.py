from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.auth import auth_required, issue_token, revoke_token
from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.db import get_db
from backend.app.core.runtime import runtime_state
from backend.app.data.market_data import market_data
from backend.app.domain.models import OrderRequest, Side
from backend.app.gateway.factory import build_gateway
from backend.app.models import (
    AccountSnapshotRow,
    AuditLogRow,
    IntelPredictionRow,
    IntelRunRow,
    NewsItemRow,
    OrderRow,
)
from backend.app.services.account_desk import account_overview, liquidate_positions, symbol_ledger
from backend.app.services.reconcile import reconcile
from backend.app.services.risk_alerts import list_risk_alerts, mark_risk_alert_read
from backend.app.services.settings_service import get_settings_view, status_bar, update_settings_section
from backend.app.services.trading import TradingService

router = APIRouter()


class ManualOrderIn(BaseModel):
    symbol: str
    side: Side
    quantity: int = Field(gt=0)
    price: Optional[float] = None
    reason: str = "manual"


class SystemPatchIn(BaseModel):
    live_trading_enabled: Optional[bool] = None


class LoginIn(BaseModel):
    username: str = ""
    password: str


class SettingsPutIn(BaseModel):
    section: str
    data: dict[str, Any] = Field(default_factory=dict)
    password: Optional[str] = None


class LiquidateIn(BaseModel):
    confirm: bool = False
    symbol: Optional[str] = None


@router.get("/health")
def health():
    return {"ok": True, "service": "aqt-api"}


@router.get("/auth/status")
def auth_status():
    return {"required": auth_required()}


@router.post("/auth/login")
def login(body: LoginIn):
    token = issue_token(body.password, username=body.username)
    return {"token": token}


@router.post("/auth/logout")
def logout(request: Request):
    header = request.headers.get("authorization") or ""
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    revoke_token(token)
    return {"ok": True}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    bar = status_bar(db)
    settings = get_settings()
    return {
        **bar,
        "initial_cash": settings.initial_cash,
        "auth_required": auth_required(),
    }


@router.get("/system/status-bar")
def system_status_bar(db: Session = Depends(get_db)):
    return status_bar(db)


@router.get("/settings")
def get_settings_api(db: Session = Depends(get_db)):
    return get_settings_view(db)


@router.put("/settings")
def put_settings_api(body: SettingsPutIn, db: Session = Depends(get_db)):
    return update_settings_section(db, body.section, body.data, body.password)


@router.post("/system/control")
def system_control(body: SystemPatchIn, db: Session = Depends(get_db)):
    if body.live_trading_enabled is not None:
        # 兼容旧调用；正式路径走 /settings trading
        mode = "live" if body.live_trading_enabled else "sim"
        update_settings_section(
            db,
            "trading",
            {"mode": mode},
            password=get_settings().app_password or "",
        )
    return status_bar(db)


@router.get("/orders")
def get_orders(db: Session = Depends(get_db), limit: int = 100):
    rows = db.query(OrderRow).order_by(OrderRow.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "symbol": r.symbol,
            "side": r.side,
            "quantity": r.quantity,
            "price": r.price,
            "filled_quantity": r.filled_quantity,
            "filled_price": r.filled_price,
            "status": r.status,
            "reason": r.reason,
            "message": r.message,
            "gateway": r.gateway,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/orders")
def post_order(body: ManualOrderIn, db: Session = Depends(get_db)):
    gateway = build_gateway(db)
    trading = TradingService(db, gateway)
    result = trading.place_order(
        OrderRequest(
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
            price=body.price,
            reason=body.reason,
        )
    )
    return result.model_dump(mode="json")


@router.post("/orders/{order_id}/cancel")
def post_cancel(order_id: str, db: Session = Depends(get_db)):
    gateway = build_gateway(db)
    trading = TradingService(db, gateway)
    return trading.cancel_order(order_id).model_dump(mode="json")


@router.get("/positions")
def get_positions(db: Session = Depends(get_db)):
    overview = account_overview(db)
    return overview.get("positions") or []


@router.post("/positions/liquidate")
def post_liquidate(body: LiquidateIn, db: Session = Depends(get_db)):
    return liquidate_positions(db, confirm=body.confirm, symbol=body.symbol)


@router.get("/positions/{symbol}/ledger")
def get_symbol_ledger(symbol: str, db: Session = Depends(get_db), limit: int = 50):
    return symbol_ledger(db, symbol, limit=limit)


@router.get("/account")
def get_account(db: Session = Depends(get_db)):
    gateway = build_gateway(db)
    return gateway.query_account().model_dump(mode="json")


@router.get("/account/overview")
def get_account_overview(db: Session = Depends(get_db)):
    return account_overview(db)


@router.get("/account/history")
def account_history(db: Session = Depends(get_db), limit: int = 100):
    rows = (
        db.query(AccountSnapshotRow)
        .order_by(AccountSnapshotRow.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "cash": r.cash,
            "market_value": r.market_value,
            "total_equity": r.total_equity,
            "daily_pnl": r.daily_pnl,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/risk/events")
@router.get("/risk-alerts")
def risk_alerts(db: Session = Depends(get_db), limit: int = 100):
    rows = list_risk_alerts(db, limit=limit)
    return [
        {
            "id": r.id,
            "event_type": r.event_type,
            "level": r.level,
            "title": r.title,
            "symbol": r.symbol,
            "message": r.message,
            "detail": r.detail,
            "push_status": r.push_status,
            "read": r.read,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/risk-alerts/{alert_id}/read")
def read_risk_alert(alert_id: int, db: Session = Depends(get_db)):
    row = mark_risk_alert_read(db, alert_id)
    if row is None:
        raise HTTPException(404, "not found")
    return {"ok": True}


@router.get("/audit")
def get_audit(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(AuditLogRow).order_by(AuditLogRow.id.desc()).limit(limit).all()
    return [{"id": r.id, "action": r.action, "detail": r.detail, "created_at": r.created_at} for r in rows]


@router.get("/market/quotes")
def market_quotes(symbols: str = "", db: Session = Depends(get_db)):
    from backend.app.market.service import get_quotes

    syms = [s.strip() for s in symbols.replace("，", ",").split(",") if s.strip()]
    return get_quotes(db, syms)


@router.get("/market/kline")
def market_kline(symbol: str, period: str = "5m", limit: int = 120, db: Session = Depends(get_db)):
    from backend.app.market.service import get_kline

    return get_kline(db, symbol, period=period, limit=limit)


@router.get("/market/board")
def market_board(symbol: Optional[str] = None, period: str = "5m", db: Session = Depends(get_db)):
    from backend.app.market.service import board_payload

    return board_payload(db, symbol=symbol, period=period)


@router.get("/market/{symbol}/daily")
def get_daily(symbol: str, start: Optional[date] = None, end: Optional[date] = None):
    bars = market_data.fetch_daily(symbol, start=start, end=end)
    return [b.model_dump(mode="json") for b in bars[-240:]]


@router.get("/market/{symbol}/minute")
def get_minute(symbol: str, period: str = "5"):
    return market_data.fetch_minute(symbol, period=period)


@router.post("/system/reconcile")
def post_reconcile(db: Session = Depends(get_db)):
    gateway = build_gateway(db)
    return reconcile(db, gateway)


class LlmConfigIn(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


class IntelToggleIn(BaseModel):
    enabled: bool


@router.get("/intel/status")
def intel_status(db: Session = Depends(get_db)):
    from backend.app.intel.llm_client import load_llm_settings
    from backend.app.intel.pipeline import intel_enabled
    from backend.app.intel.scheduler import intel_scheduler
    from backend.app.services.hot_universe import effective_whitelist, hot_pool_status

    llm = load_llm_settings(db)
    cfg = load_yaml_config().get("intel") or {}
    wl = effective_whitelist(db)
    hot = hot_pool_status(db)
    from backend.app.intel.appbuilder_search import appbuilder_configured
    from backend.app.intel.tavily_news import tavily_configured

    provider = str(cfg.get("news_provider") or "appbuilder")
    search_ok = appbuilder_configured() if provider in {"appbuilder", "hybrid"} else (
        tavily_configured() if provider == "tavily" else True
    )
    return {
        "enabled": intel_enabled(db),
        "scheduler_running": intel_scheduler.running,
        "poll_interval_seconds": int(cfg.get("poll_interval_seconds", 900)),
        "whitelist_count": len(wl),
        "whitelist_ok": bool(wl) or not cfg.get("require_whitelist", True),
        "hot_pool": hot,
        "news_provider": provider,
        "tavily_configured": tavily_configured(),
        "appbuilder_configured": appbuilder_configured(),
        "search_configured": search_ok,
        "llm_configured": bool(llm.get("api_key")),
        "llm_base_url": llm.get("base_url"),
        "llm_model": llm.get("model"),
        "rules": {
            "max_position_pct": cfg.get("max_position_pct", 0.1),
            "max_buy_cash_pct": cfg.get("max_buy_cash_pct", 0.15),
            "max_holdings": cfg.get("max_holdings", 10),
            "max_new_buys_per_run": cfg.get("max_new_buys_per_run", 3),
            "max_per_sector": cfg.get("max_per_sector", 3),
            "min_confidence": cfg.get("min_confidence", 0.6),
            "sell_fraction_on_down": cfg.get("sell_fraction_on_down", 0.5),
            "reopen_cooldown_minutes": cfg.get("reopen_cooldown_minutes", 30),
        },
    }


@router.post("/intel/hot-pool/refresh")
def intel_hot_pool_refresh(db: Session = Depends(get_db)):
    from backend.app.services.hot_universe import hot_pool_status, refresh_hot_pool

    symbols = refresh_hot_pool(db)
    return {"ok": True, "count": len(symbols), "hot_pool": hot_pool_status(db)}


@router.post("/intel/toggle")
def intel_toggle(body: IntelToggleIn, db: Session = Depends(get_db)):
    from backend.app.intel.pipeline import set_intel_enabled

    set_intel_enabled(db, body.enabled)
    return {"enabled": body.enabled}


@router.get("/intel/llm")
def get_llm(db: Session = Depends(get_db)):
    from backend.app.intel.llm_client import load_llm_settings

    llm = load_llm_settings(db)
    return {
        "api_key": "***" if llm.get("api_key") else "",
        "base_url": llm.get("base_url"),
        "model": llm.get("model"),
        "configured": bool(llm.get("api_key")),
    }


@router.post("/intel/llm")
def post_llm(body: LlmConfigIn, db: Session = Depends(get_db)):
    from backend.app.intel.llm_client import save_llm_settings

    return save_llm_settings(db, body.api_key, body.base_url, body.model)


@router.get("/intel/news")
def intel_news(db: Session = Depends(get_db), limit: int = 50):
    from datetime import timedelta

    from backend.app.intel.news_fetch import coerce_stored_published_at

    cfg = load_yaml_config().get("intel") or {}
    max_age = int(cfg.get("max_age_hours", 48))
    cutoff = datetime.utcnow() - timedelta(hours=max_age)
    rows = (
        db.query(NewsItemRow)
        .filter(
            (NewsItemRow.published_at >= cutoff)
            | ((NewsItemRow.published_at.is_(None)) & (NewsItemRow.created_at >= cutoff))
        )
        .order_by(NewsItemRow.published_at.desc().nullslast(), NewsItemRow.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "source": r.source,
            "title": r.title,
            "summary": r.summary,
            "url": r.url,
            "published_at": coerce_stored_published_at(r.published_at, r.created_at),
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/intel/runs")
def intel_runs(db: Session = Depends(get_db), limit: int = 30):
    rows = db.query(IntelRunRow).order_by(IntelRunRow.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "news_count": r.news_count,
            "pred_count": r.pred_count,
            "order_count": r.order_count,
            "message": r.message,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/intel/predictions")
def intel_predictions(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(IntelPredictionRow).order_by(IntelPredictionRow.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "symbol": r.symbol,
            "direction": r.direction,
            "confidence": r.confidence,
            "sector": r.sector,
            "reason": r.reason,
            "action": r.action,
            "order_id": r.order_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]