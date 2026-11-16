from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.runtime import runtime_state
from backend.app.gateway.factory import build_gateway
from backend.app.intel.appbuilder_search import appbuilder_configured
from backend.app.intel.llm_client import load_llm_settings
from backend.app.intel.pipeline import intel_enabled
from backend.app.models import AuditLogRow, SystemStateRow

SETTINGS_KEY = "app_settings"


def _get_store(db: Session) -> dict[str, Any]:
    row = db.get(SystemStateRow, SETTINGS_KEY)
    if row and isinstance(row.value, dict):
        return dict(row.value)
    return {}


def _save_store(db: Session, store: dict[str, Any]) -> None:
    row = db.get(SystemStateRow, SETTINGS_KEY)
    if row is None:
        db.add(SystemStateRow(key=SETTINGS_KEY, value=store))
    else:
        row.value = store
    db.commit()


def get_trading_mode(db: Session) -> str:
    store = _get_store(db)
    trading = store.get("trading") or {}
    mode = str(trading.get("mode") or "sim").lower()
    return "live" if mode == "live" else "sim"


def apply_trading_mode(db: Session, mode: str) -> None:
    mode = "live" if mode == "live" else "sim"
    runtime_state.live_trading_enabled = mode == "live"


def verify_app_password(password: Optional[str]) -> None:
    expected = get_settings().app_password
    if not expected:
        # 未设置登录密码时仍要求显式确认口令为空或任意非空二次确认
        if password is None:
            raise HTTPException(400, "开启 LIVE 需要确认密码")
        return
    if not password or not hmac.compare_digest(password, expected):
        raise HTTPException(403, "密码错误")


def get_settings_view(db: Session) -> dict[str, Any]:
    store = _get_store(db)
    yaml_cfg = load_yaml_config()
    intel = yaml_cfg.get("intel") or {}
    alerts = yaml_cfg.get("alerts") or {}
    market_data = yaml_cfg.get("market_data") or {}
    trading = store.get("trading") or {"mode": "sim"}
    if "mode" not in trading:
        trading["mode"] = "sim"
    return {
        "trading": trading,
        "llm": {
            **{k: v for k, v in load_llm_settings(db).items() if k != "api_key"},
            "api_key": "***" if load_llm_settings(db).get("api_key") else "",
            "configured": bool(load_llm_settings(db).get("api_key")),
        },
        "intel": store.get("intel") or {
            "enabled": intel_enabled(db),
            "news_provider": intel.get("news_provider"),
            "poll_interval_seconds": intel.get("poll_interval_seconds", 300),
            "min_confidence": intel.get("min_confidence", 0.7),
            "sell_mode": intel.get("sell_mode", "all"),
            "trade_pct": intel.get("trade_pct", 0.1),
            "max_holdings": intel.get("max_holdings", 10),
            "max_orders_per_day": intel.get("max_orders_per_day", 30),
            "allow_auto_sell": intel.get("allow_auto_sell", True),
        },
        "hot_pool": store.get("hot_pool") or intel.get("hot_pool") or {},
        "market_data": store.get("market_data") or market_data,
        "risk_rules": store.get("risk_rules") or yaml_cfg.get("risk") or {},
        "alerts": store.get("alerts") or alerts,
        "sim": store.get("sim") or {"initial_cash": get_settings().initial_cash},
        "broker": store.get("broker") or {
            "gateway_url": get_settings().gateway_url,
            "configured": bool(get_settings().gateway_token and get_settings().gateway_token != "change-me"),
        },
    }


def update_settings_section(
    db: Session,
    section: str,
    data: dict[str, Any],
    password: Optional[str] = None,
) -> dict[str, Any]:
    store = _get_store(db)
    data = dict(data or {})

    if section == "trading":
        mode = str(data.get("mode") or "sim").lower()
        if mode == "live":
            verify_app_password(password)
        store["trading"] = {"mode": "live" if mode == "live" else "sim"}
        apply_trading_mode(db, store["trading"]["mode"])
        _save_store(db, store)
        db.add(
            AuditLogRow(
                action="TRADING_MODE",
                detail={"mode": store["trading"]["mode"]},
            )
        )
        db.commit()
    elif section == "intel":
        enabled = data.pop("enabled", None)
        store["intel"] = {**(store.get("intel") or {}), **data}
        if enabled is not None:
            from backend.app.intel.pipeline import set_intel_enabled

            set_intel_enabled(db, bool(enabled))
            store["intel"]["enabled"] = bool(enabled)
        _save_store(db, store)
    elif section == "llm":
        from backend.app.intel.llm_client import save_llm_settings

        save_llm_settings(
            db,
            api_key=str(data.get("api_key") or ""),
            base_url=str(data.get("base_url") or "https://api.openai.com/v1"),
            model=str(data.get("model") or "gpt-4o-mini"),
        )
    elif section == "sim":
        cash = data.get("initial_cash")
        reset = bool(data.get("reset", True))
        store["sim"] = {**(store.get("sim") or {}), "initial_cash": float(cash if cash is not None else get_settings().initial_cash)}
        _save_store(db, store)
        if reset and cash is not None:
            from backend.app.services.account_desk import reset_sim_ledger

            reset_sim_ledger(db, float(cash))
    elif section == "market_data":
        prev = dict(store.get("market_data") or {})
        merged = {**prev, **data}
        # 空 token 表示保留原值（与 LLM api_key 一致）
        for vendor, key in (("alltick", "token"), ("ifind", "refresh_token"), ("tushare", "token")):
            incoming = data.get(vendor)
            if not isinstance(incoming, dict):
                continue
            block = {**(prev.get(vendor) or {}), **incoming}
            if not str(incoming.get(key) or "").strip():
                block[key] = str((prev.get(vendor) or {}).get(key) or "")
            merged[vendor] = block
        if not str(merged.get("provider") or "").strip():
            merged["provider"] = "ifind"
        store["market_data"] = merged
        _save_store(db, store)
    elif section in {"hot_pool", "risk_rules", "alerts", "broker"}:
        store[section] = {**(store.get(section) or {}), **data}
        _save_store(db, store)
    else:
        raise HTTPException(400, f"未知配置分区: {section}")

    return get_settings_view(db)


def _market_data_status(db: Session) -> str:
    md = get_settings_view(db).get("market_data") or {}
    provider = str(md.get("provider") or "ifind")
    if provider == "ifind":
        token = ((md.get("ifind") or {}).get("refresh_token") or "").strip()
        return "configured" if token else "unconfigured"
    if provider == "alltick":
        token = ((md.get("alltick") or {}).get("token") or "").strip()
        return "configured" if token else "unconfigured"
    if provider == "tushare":
        token = ((md.get("tushare") or {}).get("token") or "").strip()
        return "configured" if token else "unconfigured"
    return "unconfigured"


def _push_status(db: Session) -> str:
    alerts = get_settings_view(db).get("alerts") or {}
    token = str(alerts.get("pushplus_token") or "").strip()
    return "configured" if token else "unconfigured"


def status_bar(db: Session) -> dict[str, Any]:
    mode = get_trading_mode(db)
    apply_trading_mode(db, mode)
    gateway = build_gateway(db)
    health = gateway.health() if hasattr(gateway, "health") else {"ok": False}
    llm = load_llm_settings(db)
    yaml_intel = load_yaml_config().get("intel") or {}
    interval = int((get_settings_view(db).get("intel") or {}).get("poll_interval_seconds") or yaml_intel.get("poll_interval_seconds") or 300)
    tz = ZoneInfo(load_yaml_config().get("market", {}).get("timezone", "Asia/Shanghai"))
    next_run = datetime.now(tz) + timedelta(seconds=interval)

    broker_ok = bool(health.get("ok")) if mode == "live" else True
    return {
        "mode": mode,
        "live_trading_enabled": runtime_state.live_trading_enabled,
        "auto_trade_enabled": intel_enabled(db),
        "market_data_status": _market_data_status(db),
        "push_status": _push_status(db),
        "llm_configured": bool(llm.get("api_key")),
        "intel_source_configured": appbuilder_configured()
        or str(yaml_intel.get("news_provider") or "") == "rss",
        "risk_enabled": True,
        "broker_status": "ok" if broker_ok else "down",
        "gateway_type": "remote_xtquant" if mode == "live" else "sim",
        "gateway_health": health,
        "next_run_at": next_run.isoformat(),
        "as_of": datetime.utcnow().isoformat(),
    }
