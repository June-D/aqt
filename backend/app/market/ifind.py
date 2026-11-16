from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.app.core.logging import logger

DEFAULT_BASE = "https://quantapi.51ifind.com/api/v1"
QUOTE_TTL_SEC = 10.0
KLINE_TTL_SEC = 45.0
ACCESS_TOKEN_TTL_SEC = 6 * 24 * 3600  # refresh before 7d expiry

_lock = threading.Lock()
_cache: dict[str, tuple[Any, float]] = {}
_access: dict[str, tuple[str, float]] = {}  # refresh_token -> (access_token, exp_mono)


def reset_state() -> None:
    with _lock:
        _cache.clear()
        _access.clear()


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


def _http_err_summary(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    text = str(exc).replace("\n", " ").strip()
    low = text.lower()
    if "token" in low and ("refresh" in low or "access" in low or "=" in text):
        return exc.__class__.__name__
    if text:
        return text[:180]
    return exc.__class__.__name__


def to_ifind_code(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if "." in s:
        return s
    digits = "".join(ch for ch in s if ch.isdigit())[-6:]
    if not digits:
        return s
    if digits.startswith(("5", "6", "9")):
        return f"{digits}.SH"
    return f"{digits}.SZ"


def from_ifind_code(code: str) -> str:
    return str(code).split(".")[0]


def _base_url(base_url: str) -> str:
    return (base_url or DEFAULT_BASE).rstrip("/")


def _access_token(refresh_token: str, base_url: str) -> str:
    rt = (refresh_token or "").strip()
    if not rt:
        raise RuntimeError("iFinD refresh_token 未配置")
    with _lock:
        hit = _access.get(rt)
        if hit and hit[1] > _now():
            return hit[0]
    url = f"{_base_url(base_url)}/get_access_token"
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers={"Content-Type": "application/json", "refresh_token": rt})
        resp.raise_for_status()
        body = resp.json()
    data = body.get("data") if isinstance(body, dict) else None
    token = ""
    if isinstance(data, dict):
        token = str(data.get("access_token") or "").strip()
    if not token and isinstance(body, dict):
        token = str(body.get("access_token") or "").strip()
    if not token:
        err = (body.get("errmsg") if isinstance(body, dict) else None) or "no access_token"
        raise RuntimeError(f"iFinD access_token 失败: {err}")
    with _lock:
        _access[rt] = (token, _now() + ACCESS_TOKEN_TTL_SEC)
    return token


def _post_json(path: str, refresh_token: str, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    at = _access_token(refresh_token, base_url)
    url = f"{_base_url(base_url)}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json", "access_token": at}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("iFinD 响应非 JSON 对象")
    code = body.get("errorcode")
    if code is not None and int(code) != 0:
        raise RuntimeError(f"iFinD errorcode={code} {body.get('errmsg') or ''}".strip())
    return body


def fetch_quotes(
    symbols: list[str],
    refresh_token: str,
    base_url: str = DEFAULT_BASE,
) -> list[dict[str, Any]]:
    codes = [to_ifind_code(s) for s in symbols if s]
    if not codes:
        return []
    body = _post_json(
        "real_time_quotation",
        refresh_token,
        base_url,
        {"codes": ",".join(codes), "indicators": "latest,volume"},
    )
    tables = body.get("tables") or []
    by_code: dict[str, dict[str, Any]] = {}
    for t in tables:
        if not isinstance(t, dict):
            continue
        code = str(t.get("thscode") or "")
        table = t.get("table") if isinstance(t.get("table"), dict) else {}
        latest = table.get("latest")
        if isinstance(latest, list):
            latest = latest[0] if latest else None
        vol = table.get("volume")
        if isinstance(vol, list):
            vol = vol[0] if vol else None
        ts = t.get("time")
        if isinstance(ts, list):
            ts = ts[0] if ts else None
        by_code[code] = {
            "symbol": from_ifind_code(code),
            "code": code,
            "price": float(latest) if latest is not None else None,
            "volume": vol,
            "ts": ts,
            "raw": t,
        }
    out: list[dict[str, Any]] = []
    for raw, code in zip(symbols, codes):
        hit = by_code.get(code)
        if hit:
            out.append(hit)
        else:
            out.append(
                {
                    "symbol": "".join(ch for ch in str(raw) if ch.isdigit())[-6:] or from_ifind_code(code),
                    "code": code,
                    "price": None,
                    "volume": None,
                    "ts": None,
                    "raw": {},
                }
            )
    return out


def _session_window(period: str) -> tuple[str, str, str]:
    """返回 (starttime, endtime, Interval 分钟数字符串)。"""
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    day = now
    if day.weekday() >= 5:
        day = day - timedelta(days=day.weekday() - 4)
    # 盘前取上一个交易日近似：周末已回退；周一盘前也可用上周五
    if now.weekday() == 0 and now.hour < 9:
        day = now - timedelta(days=3)
    elif now.hour < 9 or (now.hour == 9 and now.minute < 15):
        day = day - timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    d = day.strftime("%Y-%m-%d")
    interval = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}.get(period, "5")
    if period in {"day", "1d", "d"}:
        # 日线改走历史接口时由上层处理；这里仍给全日窗口
        interval = "60"
    return f"{d} 09:15:00", f"{d} 15:15:00", interval


def fetch_kline(
    symbol: str,
    period: str,
    refresh_token: str,
    base_url: str = DEFAULT_BASE,
    limit: int = 120,
) -> list[dict[str, Any]]:
    code = to_ifind_code(symbol)
    period = period or "5m"
    if period in {"day", "1d", "d"}:
        end = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start = end - timedelta(days=max(int(limit) + 30, 60))
        body = _post_json(
            "cmd_history_quotation",
            refresh_token,
            base_url,
            {
                "codes": code,
                "indicators": "open,high,low,close,volume",
                "startdate": start.isoformat(),
                "enddate": end.isoformat(),
                "functionpara": {"Fill": "Blank"},
            },
        )
    else:
        start, end, interval = _session_window(period)
        body = _post_json(
            "high_frequency",
            refresh_token,
            base_url,
            {
                "codes": code,
                "indicators": "open,high,low,close,volume",
                "starttime": start,
                "endtime": end,
                "functionpara": {"Interval": interval},
            },
        )
    tables = body.get("tables") or []
    if not tables or not isinstance(tables[0], dict):
        return []
    t0 = tables[0]
    table = t0.get("table") if isinstance(t0.get("table"), dict) else {}
    times = table.get("time") or t0.get("time") or []
    opens = table.get("open") or []
    highs = table.get("high") or []
    lows = table.get("low") or []
    closes = table.get("close") or []
    vols = table.get("volume") or []
    n = max(len(closes), len(times))
    bars: list[dict[str, Any]] = []
    for i in range(n):
        bars.append(
            {
                "ts": times[i] if i < len(times) else None,
                "open": float(opens[i] if i < len(opens) else 0) or 0.0,
                "high": float(highs[i] if i < len(highs) else 0) or 0.0,
                "low": float(lows[i] if i < len(lows) else 0) or 0.0,
                "close": float(closes[i] if i < len(closes) else 0) or 0.0,
                "volume": float(vols[i] if i < len(vols) else 0) or 0.0,
            }
        )
    if limit and len(bars) > limit:
        bars = bars[-int(limit) :]
    return bars


def safe_fetch_quotes(
    symbols: list[str], refresh_token: str, base_url: str = DEFAULT_BASE
) -> tuple[str, list[dict[str, Any]], str]:
    key = "iq:" + ",".join(to_ifind_code(s) for s in symbols if s)
    with _lock:
        fresh = _cache_get(key, allow_stale=False)
        if fresh is not None:
            return "ok", fresh, "cached"
    try:
        quotes = fetch_quotes(symbols, refresh_token, base_url)
    except Exception as exc:  # noqa: BLE001
        summary = _http_err_summary(exc)
        logger.warning("ifind quotes failed: %s", summary)
        with _lock:
            stale = _cache_get(key, allow_stale=True)
        if stale is not None:
            return "ok", stale, "cached"
        return "error", [], summary
    with _lock:
        _cache_set(key, quotes, QUOTE_TTL_SEC)
    return "ok", quotes, ""


def safe_fetch_kline(
    symbol: str,
    period: str,
    refresh_token: str,
    base_url: str = DEFAULT_BASE,
    limit: int = 120,
) -> tuple[str, list[dict[str, Any]], str]:
    key = f"ik:{to_ifind_code(symbol)}:{period}:{limit}"
    with _lock:
        fresh = _cache_get(key, allow_stale=False)
        if fresh is not None:
            return "ok", fresh, "cached"
    try:
        bars = fetch_kline(symbol, period, refresh_token, base_url, limit=limit)
    except Exception as exc:  # noqa: BLE001
        summary = _http_err_summary(exc)
        logger.warning("ifind kline failed: %s %s %s", summary, symbol, period)
        with _lock:
            stale = _cache_get(key, allow_stale=True)
        if stale is not None:
            return "ok", stale, "cached"
        return "error", [], summary
    with _lock:
        _cache_set(key, bars, KLINE_TTL_SEC)
    return "ok", bars, ""
