from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

import httpx

from backend.app.core.logging import logger

# AllTick 股票产品码：沪深用 600519.SH / 000001.SZ
PERIOD_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "day": "D",
    "1d": "D",
    "d": "D",
}

QUOTE_TTL_SEC = 20.0
KLINE_TTL_SEC = 45.0
COOLDOWN_SEC = 60.0
# 免费档文档：每个 HTTP 接口 10 秒 1 次，且 10 秒内只能打一个接口；trade-tick 最多 5 代码
MIN_INTERVAL_SEC = 10.0
MAX_TRADE_TICK_CODES = 5
MAX_KLINE_BARS = 500

_lock = threading.Lock()
_cache: dict[str, tuple[Any, float]] = {}
_cooldown_until = 0.0
_last_http_at = 0.0


def reset_rate_limit_state() -> None:
    global _cooldown_until, _last_http_at
    with _lock:
        _cache.clear()
        _cooldown_until = 0.0
        _last_http_at = 0.0


def expire_cache() -> None:
    with _lock:
        for key, (val, _exp) in list(_cache.items()):
            _cache[key] = (val, 0.0)


def _now() -> float:
    return time.monotonic()


def _cache_get(key: str, *, allow_stale: bool) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None
    val, exp = item
    if allow_stale or exp > _now():
        return val
    return None


def _cache_set(key: str, val: Any, ttl: float) -> None:
    _cache[key] = (val, _now() + ttl)


def _in_cooldown() -> bool:
    return _now() < _cooldown_until


def _mark_cooldown() -> None:
    global _cooldown_until
    _cooldown_until = _now() + COOLDOWN_SEC


def _try_begin_http() -> bool:
    """免费档：任意 HTTP 接口之间至少间隔 10 秒。不阻塞请求线程。"""
    global _last_http_at
    now = _now()
    if _in_cooldown():
        return False
    if now - _last_http_at < MIN_INTERVAL_SEC:
        return False
    _last_http_at = now
    return True


def _http_err_summary(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    text = str(exc).replace("\n", " ").strip()
    low = text.lower()
    if "token=" in low or "token:" in low:
        return exc.__class__.__name__
    if text:
        return text[:180]
    return exc.__class__.__name__


def _decode_body(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code in {401, 429}:
        resp.raise_for_status()
    try:
        body = resp.json()
    except Exception:
        resp.raise_for_status()
        raise
    if not isinstance(body, dict):
        resp.raise_for_status()
        return {}
    ret = body.get("ret")
    if ret is not None and str(ret) not in {"200", "0"}:
        code = int(ret) if str(ret).isdigit() else 400
        if code in {401, 429, 605}:
            syn = httpx.Response(code, request=resp.request)
            raise httpx.HTTPStatusError(f"HTTP {code}", request=resp.request, response=syn)
        hint = str(body.get("msg") or body.get("message") or "").strip()[:80]
        raise RuntimeError(f"AllTick ret={ret}" + (f" {hint}" if hint else ""))
    resp.raise_for_status()
    return body


def _get_json(url: str, token: str, query: dict[str, Any], timeout: float) -> dict[str, Any]:
    query = dict(query)
    query["trace"] = f"aqt-{uuid.uuid4().hex[:12]}"
    params = {
        "token": token,
        "query": json.dumps(query, ensure_ascii=False, separators=(",", ":")),
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        return _decode_body(resp)


def to_alltick_code(symbol: str) -> str:
    s = "".join(ch for ch in str(symbol) if ch.isdigit())[-6:]
    if not s:
        return str(symbol)
    if s.startswith(("5", "6", "9")):
        return f"{s}.SH"
    return f"{s}.SZ"


def from_alltick_code(code: str) -> str:
    return str(code).split(".")[0]


def fetch_quotes(symbols: list[str], token: str, base_url: str) -> list[dict[str, Any]]:
    """批量最新价。未配置 token 时由上层拦截，这里直接请求。"""
    if not token:
        raise RuntimeError("AllTick token 未配置")
    codes = [to_alltick_code(s) for s in symbols if s]
    if not codes:
        return []
    req_codes = codes[:MAX_TRADE_TICK_CODES]
    query = {
        "trace": "aqt",
        "data": {"symbol_list": [{"code": c} for c in req_codes]},
    }
    url = f"{base_url.rstrip('/')}/quote-stock-b-api/trade-tick"
    body = _get_json(url, token, query, 15.0)
    tick_list = ((body.get("data") or {}).get("tick_list")) or body.get("tick_list") or []
    out: list[dict[str, Any]] = []
    by_code = {str(t.get("code")): t for t in tick_list if isinstance(t, dict)}
    for raw, code in zip(symbols, codes):
        t = by_code.get(code) or {}
        price = t.get("price") or t.get("last_price") or t.get("close")
        out.append(
            {
                "symbol": from_alltick_code(code) if not raw else "".join(ch for ch in str(raw) if ch.isdigit())[-6:] or raw,
                "code": code,
                "price": float(price) if price is not None else None,
                "volume": t.get("volume"),
                "ts": t.get("tick_time") or t.get("timestamp"),
                "raw": t,
            }
        )
    return out


def fetch_kline(
    symbol: str,
    period: str,
    token: str,
    base_url: str,
    limit: int = 120,
) -> list[dict[str, Any]]:
    if not token:
        raise RuntimeError("AllTick token 未配置")
    code = to_alltick_code(symbol)
    kline_type = PERIOD_MAP.get(period, PERIOD_MAP.get(period.lower(), "5"))
    n = min(int(limit), MAX_KLINE_BARS)
    query = {
        "trace": "aqt",
        "data": {
            "code": code,
            "kline_type": int(kline_type) if str(kline_type).isdigit() else kline_type,
            "kline_timestamp_end": 0,
            "query_kline_num": n,
            "adjust_type": 0,
        },
    }
    if not str(kline_type).isdigit():
        query["data"]["kline_type"] = 8

    url = f"{base_url.rstrip('/')}/quote-stock-b-api/kline"
    body = _get_json(url, token, query, 20.0)
    rows = ((body.get("data") or {}).get("kline_list")) or body.get("kline_list") or []
    bars: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp") or r.get("tick_time") or r.get("t")
        bars.append(
            {
                "ts": ts,
                "open": float(r.get("open", 0) or 0),
                "high": float(r.get("high", 0) or 0),
                "low": float(r.get("low", 0) or 0),
                "close": float(r.get("close", 0) or 0),
                "volume": float(r.get("volume", 0) or 0),
            }
        )
    return bars


def _safe_cached(key: str) -> tuple[Any | None, Any | None]:
    with _lock:
        if _in_cooldown():
            return None, _cache_get(key, allow_stale=True)
        fresh = _cache_get(key, allow_stale=False)
        if fresh is not None:
            return fresh, None
        return None, _cache_get(key, allow_stale=True)


def _on_http_error(key: str, summary: str, status_code: int | None) -> tuple[str, Any | None, str]:
    logger.warning("alltick %s", summary)
    with _lock:
        if status_code in {401, 429, 605}:
            _mark_cooldown()
        stale = _cache_get(key, allow_stale=True)
    return summary, stale


def safe_fetch_quotes(symbols: list[str], token: str, base_url: str) -> tuple[str, list[dict[str, Any]], str]:
    key = "q:" + ",".join(to_alltick_code(s) for s in symbols if s)
    fresh, stale = _safe_cached(key)
    if fresh is not None:
        return "ok", fresh, "cached"
    if not _try_begin_http():
        if stale is not None:
            return "ok", stale, "cached"
        return "error", [], "限频等待"
    try:
        quotes = fetch_quotes(symbols, token, base_url)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else None
        summary, cached = _on_http_error(key, _http_err_summary(exc), code)
        if cached is not None:
            return "ok", cached, f"{code} cached" if code else "cached"
        return "error", [], summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("alltick quotes failed: %s", _http_err_summary(exc))
        with _lock:
            cached = _cache_get(key, allow_stale=True)
        if cached is not None:
            return "ok", cached, "cached"
        return "error", [], _http_err_summary(exc)
    with _lock:
        _cache_set(key, quotes, QUOTE_TTL_SEC)
    return "ok", quotes, ""


def safe_fetch_kline(
    symbol: str, period: str, token: str, base_url: str, limit: int = 120
) -> tuple[str, list[dict[str, Any]], str]:
    key = f"k:{to_alltick_code(symbol)}:{period}:{limit}"
    fresh, stale = _safe_cached(key)
    if fresh is not None:
        return "ok", fresh, "cached"
    if not _try_begin_http():
        if stale is not None:
            return "ok", stale, "cached"
        return "error", [], "限频等待"
    try:
        bars = fetch_kline(symbol, period, token, base_url, limit=limit)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else None
        summary, cached = _on_http_error(key, f"{_http_err_summary(exc)} {symbol} {period}", code)
        if cached is not None:
            return "ok", cached, f"{code} cached" if code else "cached"
        return "error", [], summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("alltick kline failed: %s", _http_err_summary(exc))
        with _lock:
            cached = _cache_get(key, allow_stale=True)
        if cached is not None:
            return "ok", cached, "cached"
        return "error", [], _http_err_summary(exc)
    with _lock:
        _cache_set(key, bars, KLINE_TTL_SEC)
    return "ok", bars, ""
