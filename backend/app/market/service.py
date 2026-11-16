from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.market import alltick, ifind
from backend.app.services.hot_universe import load_hot_entries, load_hot_pool
from backend.app.services.settings_service import get_settings_view


def _md_cfg(db: Session) -> dict[str, Any]:
    return get_settings_view(db).get("market_data") or {}


def _alltick_creds(db: Session) -> tuple[str, str]:
    md = _md_cfg(db)
    at = md.get("alltick") or {}
    token = str(at.get("token") or "").strip()
    base = str(at.get("base_url") or "https://quote.alltick.co").strip()
    return token, base


def _ifind_creds(db: Session) -> tuple[str, str]:
    md = _md_cfg(db)
    fi = md.get("ifind") or {}
    token = str(fi.get("refresh_token") or "").strip()
    base = str(fi.get("base_url") or ifind.DEFAULT_BASE).strip()
    return token, base


def provider_name(db: Session) -> str:
    return str((_md_cfg(db).get("provider") or "ifind")).lower()


def get_quotes(db: Session, symbols: list[str]) -> dict[str, Any]:
    provider = provider_name(db)
    if provider == "tushare":
        token = str(((_md_cfg(db).get("tushare") or {}).get("token") or "")).strip()
        if not token:
            return {
                "status": "unconfigured",
                "provider": "tushare",
                "quotes": [],
                "message": "Tushare 待配置（第一期未实现适配）",
            }
        return {
            "status": "unconfigured",
            "provider": "tushare",
            "quotes": [],
            "message": "Tushare 适配未实现，请改用 iFinD 或 AllTick",
        }

    if provider == "alltick":
        token, base = _alltick_creds(db)
        if not token:
            return {
                "status": "unconfigured",
                "provider": "alltick",
                "quotes": [],
                "message": "AllTick token 未配置",
            }
        status, quotes, err = alltick.safe_fetch_quotes(symbols, token, base)
        return {"status": status, "provider": "alltick", "quotes": quotes, "message": err}

    # default / ifind
    token, base = _ifind_creds(db)
    if not token:
        return {
            "status": "unconfigured",
            "provider": "ifind",
            "quotes": [],
            "message": "iFinD refresh_token 未配置",
        }
    status, quotes, err = ifind.safe_fetch_quotes(symbols, token, base)
    return {"status": status, "provider": "ifind", "quotes": quotes, "message": err}


def get_kline(db: Session, symbol: str, period: str = "5m", limit: int = 120) -> dict[str, Any]:
    provider = provider_name(db)
    period = period or "5m"
    if provider == "tushare":
        return {
            "status": "unconfigured",
            "provider": "tushare",
            "symbol": symbol,
            "period": period,
            "bars": [],
            "message": "Tushare 适配未实现，请改用 iFinD 或 AllTick",
        }
    if provider == "alltick":
        token, base = _alltick_creds(db)
        if not token:
            return {
                "status": "unconfigured",
                "provider": "alltick",
                "symbol": symbol,
                "period": period,
                "bars": [],
                "message": "AllTick token 未配置",
            }
        status, bars, err = alltick.safe_fetch_kline(symbol, period, token, base, limit=limit)
        return {
            "status": status,
            "provider": "alltick",
            "symbol": symbol,
            "period": period,
            "bars": bars,
            "message": err,
        }

    token, base = _ifind_creds(db)
    if not token:
        return {
            "status": "unconfigured",
            "provider": "ifind",
            "symbol": symbol,
            "period": period,
            "bars": [],
            "message": "iFinD refresh_token 未配置",
        }
    status, bars, err = ifind.safe_fetch_kline(symbol, period, token, base, limit=limit)
    return {
        "status": status,
        "provider": "ifind",
        "symbol": symbol,
        "period": period,
        "bars": bars,
        "message": err,
    }


def board_payload(db: Session, symbol: Optional[str] = None, period: str = "5m") -> dict[str, Any]:
    hot = load_hot_pool(db)
    entries = load_hot_entries(db)
    focus = symbol or (hot[0] if hot else "")
    quote_syms = list(hot if hot else ([focus] if focus else []))
    if focus and focus in quote_syms:
        quote_syms = [focus] + [s for s in quote_syms if s != focus]
    # iFinD：可同刷；报价短 TTL，K 线长缓存。AllTick 免费档仍有进程内闸门。
    kline_resp = (
        get_kline(db, focus, period=period)
        if focus
        else {
            "status": "ok",
            "provider": provider_name(db),
            "period": period,
            "bars": [],
            "message": "无热点标的",
        }
    )
    quotes_resp = get_quotes(db, quote_syms)
    qmap = {str(q.get("symbol")): q for q in (quotes_resp.get("quotes") or []) if isinstance(q, dict)}
    hot_rows = []
    for e in entries:
        q = qmap.get(e["symbol"]) or {}
        hot_rows.append(
            {
                "symbol": e["symbol"],
                "name": e.get("name") or "",
                "industry": e.get("industry") or "",
                "price": q.get("price"),
            }
        )
    if not hot_rows and hot:
        hot_rows = [
            {"symbol": s, "name": "", "industry": "", "price": (qmap.get(s) or {}).get("price")}
            for s in hot
        ]
    return {
        "hot_symbols": hot,
        "hot_rows": hot_rows,
        "focus": focus,
        "quotes": quotes_resp,
        "kline": kline_resp,
    }
