from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional

from backend.app.intel.news_fetch import _parse_time

import httpx

from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.logging import logger

SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


def _fp(title: str, url: str) -> str:
    raw = f"{title.strip()}|{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _parse_pub(raw: Any) -> Optional[datetime]:
    return _parse_time(raw)


def _cfg() -> dict:
    return (load_yaml_config().get("intel") or {}).get("appbuilder") or {}


def appbuilder_configured() -> bool:
    return bool(get_settings().appbuilder_token or "")


def search_appbuilder(query: str) -> list[dict[str, Any]]:
    """千帆 AppBuilder AI 搜索（国内可达）。"""
    token = get_settings().appbuilder_token
    if not token:
        raise RuntimeError("未配置 APPBUILDER_TOKEN（.env 填写后重启）")

    cfg = _cfg()
    top_k = int(cfg.get("max_results_per_query") or 5)
    recency = str(cfg.get("search_recency_filter") or "week")
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": query}],
        "search_source": str(cfg.get("search_source") or "baidu_search_v2"),
        "resource_type_filter": [{"type": "web", "top_k": top_k}],
        "search_recency_filter": recency,
    }

    timeout = httpx.Timeout(float(cfg.get("timeout_seconds") or 45.0), connect=15.0)
    auth = f"Bearer {token}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            SEARCH_URL,
            headers={
                "Authorization": auth,
                "X-Appbuilder-Authorization": auth,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    out: list[dict[str, Any]] = []
    for it in data.get("references") or []:
        if not isinstance(it, dict):
            continue
        if str(it.get("type") or "web") not in {"web", ""}:
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        url = str(it.get("url") or "")[:1000]
        summary = str(it.get("content") or it.get("snippet") or "")[:2000]
        pub = _parse_pub(it.get("date") or it.get("published_at"))
        out.append(
            {
                "source": "appbuilder",
                "title": title[:500],
                "summary": summary,
                "url": url,
                "published_at": pub or datetime.utcnow(),
                "fingerprint": _fp(title, url),
            }
        )
    return out


def fetch_appbuilder_news_for_symbols(symbols: list[str]) -> list[dict[str, Any]]:
    """对热点股票代码逐个做 AppBuilder AI 搜索。"""
    if not appbuilder_configured():
        logger.warning("AppBuilder skipped: no APPBUILDER_TOKEN")
        return []

    cfg = _cfg()
    if not cfg.get("enabled", True):
        return []

    per_run = int(cfg.get("symbols_per_run") or 12)
    query_tpl = str(cfg.get("query_template") or "A股 {symbol} 股票 最新消息 热点新闻")
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    def add_rows(rows: list[dict[str, Any]], symbol: Optional[str] = None) -> None:
        for r in rows:
            item = dict(r)
            if symbol:
                item["title"] = f"[{symbol}] {item['title']}"[:500]
                item["symbol_hint"] = symbol
                item["fingerprint"] = _fp(item["title"], item.get("url") or "")
            fp = item["fingerprint"]
            if fp in seen:
                continue
            seen.add(fp)
            merged.append(item)

    for symbol in symbols[:per_run]:
        q = query_tpl.format(symbol=symbol)
        try:
            add_rows(search_appbuilder(q), symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("appbuilder search failed %s: %s", symbol, exc)

    if cfg.get("include_market_pulse", True):
        mq = str(cfg.get("market_query") or "A股 今日热点 板块 涨停 政策 新闻")
        try:
            add_rows(search_appbuilder(mq))
        except Exception as exc:  # noqa: BLE001
            logger.warning("appbuilder market pulse failed: %s", exc)

    return merged
