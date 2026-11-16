from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional

import httpx

from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.logging import logger
from backend.app.intel.news_fetch import _parse_time


def _fp(title: str, url: str) -> str:
    raw = f"{title.strip()}|{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _parse_pub(raw: Any) -> Optional[datetime]:
    return _parse_time(raw)


def _tavily_cfg() -> dict:
    return (load_yaml_config().get("intel") or {}).get("tavily") or {}


def tavily_configured() -> bool:
    return bool(get_settings().tavily_api_key or "")


def search_tavily(query: str) -> list[dict[str, Any]]:
    """调用 Tavily Search（agent 同款网页搜索）。"""
    api_key = get_settings().tavily_api_key
    if not api_key:
        raise RuntimeError("未配置 TAVILY_API_KEY（.env 填写后重启）")

    cfg = _tavily_cfg()
    payload: dict[str, Any] = {
        "query": query,
        "topic": str(cfg.get("topic") or "news"),
        "search_depth": str(cfg.get("search_depth") or "basic"),
        "max_results": int(cfg.get("max_results_per_query") or 3),
        "include_answer": False,
        "include_raw_content": False,
    }
    time_range = cfg.get("time_range")
    if time_range:
        payload["time_range"] = str(time_range)
    days = cfg.get("days")
    if days is not None:
        payload["days"] = int(days)

    timeout = httpx.Timeout(float(cfg.get("timeout_seconds") or 45.0), connect=15.0)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    out: list[dict[str, Any]] = []
    for it in data.get("results") or []:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        url = str(it.get("url") or "")[:1000]
        summary = str(it.get("content") or "")[:2000]
        pub = _parse_pub(it.get("published_date") or it.get("published_at"))
        out.append(
            {
                "source": "tavily",
                "title": title[:500],
                "summary": summary,
                "url": url,
                "published_at": pub or datetime.utcnow(),
                "fingerprint": _fp(title, url),
            }
        )
    return out


def fetch_tavily_news_for_symbols(symbols: list[str]) -> list[dict[str, Any]]:
    """对热点股票代码逐个 Tavily 搜索，拼成情报新闻列表。"""
    if not tavily_configured():
        logger.warning("Tavily skipped: no TAVILY_API_KEY")
        return []

    cfg = _tavily_cfg()
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
            add_rows(search_tavily(q), symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily search failed %s: %s", symbol, exc)

    if cfg.get("include_market_pulse", True):
        mq = str(cfg.get("market_query") or "A股 今日热点 板块 涨停 政策 新闻")
        try:
            add_rows(search_tavily(mq))
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily market pulse failed: %s", exc)

    return merged
