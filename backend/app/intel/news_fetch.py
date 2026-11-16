from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from backend.app.core.config import load_yaml_config
from backend.app.core.logging import logger

_UA = {"User-Agent": "Mozilla/5.0 (compatible; AQT-Intel/1.1)"}


def coerce_stored_published_at(
    published_at: Optional[datetime], created_at: Optional[datetime]
) -> Optional[datetime]:
    """旧数据把北京墙钟当 UTC 存了；比入库时间快 5h+ 时按上海时间改回 UTC。"""
    if published_at is None:
        return None
    if created_at is not None and published_at - created_at >= timedelta(hours=5):
        return _to_utc_naive(published_at, naive_is_shanghai=True)
    return published_at


def _fp(title: str, url: str) -> str:
    raw = f"{title.strip()}|{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return re.sub(r"\s+", " ", el.text).strip()


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _to_utc_naive(dt: datetime, *, naive_is_shanghai: bool) -> datetime:
    """库内时间一律 UTC naive；前端再格式化成北京时间。"""
    if dt.tzinfo is None:
        if naive_is_shanghai:
            dt = dt.replace(tzinfo=_SHANGHAI)
        else:
            return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_time(raw: Any) -> Optional[datetime]:
    """把常见时间字段解析成 UTC naive datetime。无时区按北京时间。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return _to_utc_naive(raw, naive_is_shanghai=True)

    if isinstance(raw, str):
        s = raw.strip()
        if len(s) == 8 and s.isdigit() and s.startswith(("19", "20")):
            try:
                return _to_utc_naive(datetime.strptime(s, "%Y%m%d"), naive_is_shanghai=True)
            except ValueError:
                return None
        if s.isdigit():
            raw = int(s)
        else:
            for fmt, n in (
                ("%Y-%m-%d %H:%M:%S", 19),
                ("%Y-%m-%d %H:%M", 16),
                ("%Y/%m/%d %H:%M:%S", 19),
                ("%Y-%m-%dT%H:%M:%S", 19),
            ):
                if "T" in fmt and ("Z" in s or "+" in s[10:] or s.count("-") > 2):
                    continue
                try:
                    return _to_utc_naive(datetime.strptime(s[:n], fmt), naive_is_shanghai=True)
                except ValueError:
                    continue
            try:
                return _to_utc_naive(
                    datetime.fromisoformat(s.replace("Z", "+00:00")),
                    naive_is_shanghai=True,
                )
            except ValueError:
                pass
            try:
                dt = parsedate_to_datetime(s)
                return _to_utc_naive(dt, naive_is_shanghai=True)
            except Exception:  # noqa: BLE001
                return None

    if isinstance(raw, (int, float)):
        ts = int(raw)
        if ts > 10_000_000_000:  # ms
            ts //= 1000
        try:
            return datetime.utcfromtimestamp(ts)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _parse_rss(xml_text: str, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items:
        title = _text(item.find("title")) or _text(item.find("{http://www.w3.org/2005/Atom}title"))
        link_el = item.find("link")
        url = ""
        if link_el is not None:
            url = (link_el.get("href") or link_el.text or "").strip()
        if not url:
            url = _text(item.find("{http://www.w3.org/2005/Atom}link"))
        desc = _text(item.find("description")) or _text(item.find("summary"))
        if not desc:
            desc = _text(item.find("{http://www.w3.org/2005/Atom}summary"))
        pub = _parse_time(
            _text(item.find("pubDate"))
            or _text(item.find("published"))
            or _text(item.find("{http://www.w3.org/2005/Atom}published"))
            or _text(item.find("{http://www.w3.org/2005/Atom}updated"))
        )
        if not title:
            continue
        out.append(
            {
                "source": source,
                "title": title[:500],
                "summary": (desc or "")[:2000],
                "url": url[:1000],
                "published_at": pub,
                "fingerprint": _fp(title, url),
            }
        )
    return out


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def fetch_http_json(cfg: dict) -> list[dict[str, Any]]:
    url = cfg.get("url") or ""
    if not url:
        return []
    headers = {**_UA, **(cfg.get("headers") or {})}
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("http news source failed %s: %s", cfg.get("name"), exc)
        return []

    items = _dig(data, cfg.get("items_path") or "") if cfg.get("items_path") else data
    if isinstance(items, dict):
        items = items.get("list") or items.get("items") or items.get("data") or []
    if not isinstance(items, list):
        return []

    title_f = cfg.get("title_field") or "title"
    summary_f = cfg.get("summary_field") or "summary"
    url_f = cfg.get("url_field") or "url"
    time_f = cfg.get("time_field") or "published_at"
    source = str(cfg.get("name") or "http")
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get(title_f) or "").strip()
        if not title:
            continue
        summary = str(it.get(summary_f) or it.get("content") or it.get("digest") or "")[:2000]
        link = str(it.get(url_f) or it.get("link") or it.get("url_w") or "")[:1000]
        pub = _parse_time(it.get(time_f) or it.get("ctime") or it.get("showTime") or it.get("date"))
        out.append(
            {
                "source": source,
                "title": title[:500],
                "summary": summary,
                "url": link,
                "published_at": pub,
                "fingerprint": _fp(title, link),
            }
        )
    return out


def fetch_rss(name: str, url: str) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, headers=_UA)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "json" in ctype or resp.text.lstrip().startswith("{"):
                data = resp.json()
                lst = _dig(data, "result.data") or data.get("data") or []
                if isinstance(lst, list):
                    out = []
                    for it in lst:
                        if not isinstance(it, dict):
                            continue
                        title = str(it.get("title") or "").strip()
                        if not title:
                            continue
                        link = str(it.get("url") or it.get("link") or "")
                        summary = str(it.get("intro") or it.get("summary") or "")
                        pub = _parse_time(it.get("ctime") or it.get("time") or it.get("pubDate"))
                        out.append(
                            {
                                "source": name,
                                "title": title[:500],
                                "summary": summary[:2000],
                                "url": link[:1000],
                                "published_at": pub,
                                "fingerprint": _fp(title, link),
                            }
                        )
                    return out
            return _parse_rss(resp.text, name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rss failed %s: %s", name, exc)
        return []


def fetch_akshare_briefs() -> list[dict[str, Any]]:
    """央视新闻联播摘要：必须传当天日期，akshare 默认是 20240424。"""
    try:
        import akshare as ak

        day = datetime.now().strftime("%Y%m%d")
        df = ak.news_cctv(date=day)
        if df is None or df.empty:
            # 周末/未更新时回退昨天
            yday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            df = ak.news_cctv(date=yday)
            day = yday
        if df is None or df.empty:
            return []
        pub = _parse_time(day) or datetime.utcnow()
        out = []
        for _, row in df.head(20).iterrows():
            title = str(row.get("title") or row.get("新闻标题") or "").strip()
            if not title:
                continue
            summary = str(row.get("content") or row.get("新闻内容") or "")[:2000]
            out.append(
                {
                    "source": "cctv",
                    "title": title[:500],
                    "summary": summary,
                    "url": f"https://tv.cctv.com/lm/xwlb/day/{day}.shtml",
                    "published_at": pub,
                    "fingerprint": _fp(title, f"cctv:{day}"),
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("akshare news failed: %s", exc)
        return []


def collect_news(limit: int = 40, focus_symbols: Optional[list[str]] = None) -> list[dict[str, Any]]:
    cfg = load_yaml_config().get("intel") or {}
    max_age_hours = int(cfg.get("max_age_hours", 48))
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    provider = str(cfg.get("news_provider") or "appbuilder").lower()
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    def add_many(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            fp = r["fingerprint"]
            if fp in seen:
                continue
            pub = r.get("published_at")
            if isinstance(pub, datetime) and pub < cutoff:
                continue
            seen.add(fp)
            merged.append(r)

    if provider in {"appbuilder", "hybrid"} and focus_symbols:
        from backend.app.intel.appbuilder_search import fetch_appbuilder_news_for_symbols

        add_many(fetch_appbuilder_news_for_symbols(focus_symbols))

    if provider == "tavily" and focus_symbols:
        from backend.app.intel.tavily_news import fetch_tavily_news_for_symbols

        add_many(fetch_tavily_news_for_symbols(focus_symbols))

    # RSS：纯 rss，或 hybrid / 搜索无结果时兜底
    need_rss = provider in {"rss", "hybrid"} or (provider in {"appbuilder", "tavily"} and not merged)
    if need_rss:
        for feed in cfg.get("rss_feeds") or []:
            add_many(fetch_rss(str(feed.get("name") or "rss"), str(feed.get("url") or "")))
        for src in cfg.get("http_sources") or []:
            add_many(fetch_http_json(src))
        add_many(fetch_akshare_briefs())

    def sort_key(item: dict[str, Any]) -> datetime:
        pub = item.get("published_at")
        return pub if isinstance(pub, datetime) else datetime.min

    merged.sort(key=sort_key, reverse=True)
    return merged[:limit]
