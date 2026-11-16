from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import load_yaml_config
from backend.app.core.logging import logger
from backend.app.models import SystemStateRow

HOT_POOL_KEY = "intel_hot_pool"


def _norm_code(raw: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 6:
        code = digits[-6:]
        if code[0] in {"0", "3", "6"} and not code.startswith(("8", "4")):
            # 排除部分北交所/老三板常见形态；北交所 8/4 开头已挡
            return code
    return None


def _pick_col(cols: list, names: tuple[str, ...]) -> Optional[str]:
    for c in names:
        if c in cols:
            return c
    return None


def _cell(row: Any, col: Optional[str]) -> str:
    if not col:
        return ""
    val = row.get(col)
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none"} else s


def _rows_from_df(df, limit: int) -> list[dict[str, str]]:
    if df is None or getattr(df, "empty", True):
        return []
    cols = list(df.columns)
    code_col = _pick_col(cols, ("代码", "股票代码", "code", "symbol", "证券代码"))
    if code_col is None:
        code_col = cols[1] if len(cols) > 1 else cols[0]
    name_col = _pick_col(cols, ("名称", "股票名称", "股票简称", "name", "证券简称"))
    industry_col = _pick_col(cols, ("行业", "所属行业", "industry", "板块"))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        code = _norm_code(row.get(code_col))
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(
            {
                "symbol": code,
                "name": _cell(row, name_col),
                "industry": _cell(row, industry_col),
            }
        )
        if len(out) >= limit:
            break
    return out


def _codes_from_df(df, limit: int) -> list[str]:
    return [r["symbol"] for r in _rows_from_df(df, limit)]


def merge_hot_entries(*groups: list[dict[str, str]], limit: int = 80) -> list[dict[str, str]]:
    by: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for group in groups:
        for raw in group:
            code = _norm_code((raw or {}).get("symbol"))
            if not code:
                continue
            name = str((raw or {}).get("name") or "").strip()
            industry = str((raw or {}).get("industry") or "").strip()
            if code not in by:
                if len(order) >= limit:
                    continue
                by[code] = {"symbol": code, "name": name, "industry": industry}
                order.append(code)
            else:
                if not by[code]["name"] and name:
                    by[code]["name"] = name
                if not by[code]["industry"] and industry:
                    by[code]["industry"] = industry
    return [by[c] for c in order[:limit]]


def fetch_hot_entries(top_n: int = 80, include_up_rank: bool = True) -> list[dict[str, str]]:
    """东财人气榜 / 飙升榜 → 代码 + 名称 + 行业（行业列有则带上）。"""
    import akshare as ak

    groups: list[list[dict[str, str]]] = []
    try:
        groups.append(_rows_from_df(ak.stock_hot_rank_em(), top_n))
    except Exception as exc:  # noqa: BLE001
        logger.warning("hot rank fetch failed: %s", exc)
    if include_up_rank:
        try:
            groups.append(_rows_from_df(ak.stock_hot_up_em(), max(20, top_n // 2)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("hot up rank fetch failed: %s", exc)
    return merge_hot_entries(*groups, limit=top_n)


def fetch_hot_symbols(top_n: int = 80, include_up_rank: bool = True) -> list[str]:
    return [r["symbol"] for r in fetch_hot_entries(top_n=top_n, include_up_rank=include_up_rank)]


def _index_code_name_industry(df) -> tuple[dict[str, str], dict[str, str]]:
    names: dict[str, str] = {}
    industries: dict[str, str] = {}
    if df is None or getattr(df, "empty", True):
        return names, industries
    cols = list(df.columns)
    code_col = _pick_col(cols, ("A股代码", "证券代码", "code", "代码", "symbol")) or cols[0]
    name_col = _pick_col(cols, ("A股简称", "证券简称", "name", "名称", "股票简称"))
    industry_col = _pick_col(cols, ("所属行业", "行业", "industry", "板块"))
    for _, row in df.iterrows():
        code = _norm_code(row.get(code_col))
        if not code:
            continue
        nm = _cell(row, name_col)
        ind = _cell(row, industry_col)
        if nm:
            names[code] = nm
        if ind:
            industries[code] = ind
    return names, industries


def _fill_blank_profiles(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    need_name = any(not e.get("name") for e in entries)
    need_ind = any(not e.get("industry") for e in entries)
    if not need_name and not need_ind:
        return entries
    names: dict[str, str] = {}
    industries: dict[str, str] = {}
    try:
        import akshare as ak

        if need_name:
            nmap, _ = _index_code_name_industry(ak.stock_info_a_code_name())
            names.update(nmap)
        if need_ind:
            for fn, arg in (
                ("stock_info_sz_name_code", "A股列表"),
                ("stock_info_sh_name_code", "主板A股"),
            ):
                getter = getattr(ak, fn, None)
                if getter is None:
                    continue
                try:
                    nmap, imap = _index_code_name_industry(getter(symbol=arg) if arg else getter())
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s failed: %s", fn, exc)
                    continue
                names.update(nmap)
                industries.update(imap)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stock profile table failed: %s", exc)
        return entries
    for e in entries:
        if not e.get("name"):
            e["name"] = names.get(e["symbol"]) or ""
        if not e.get("industry"):
            e["industry"] = industries.get(e["symbol"]) or ""
    return entries


def _hot_cfg() -> dict:
    return (load_yaml_config().get("intel") or {}).get("hot_pool") or {}


def save_hot_pool(
    db: Session,
    symbols: list[str],
    meta: Optional[dict] = None,
    entries: Optional[list[dict[str, str]]] = None,
) -> None:
    prev: dict[str, dict[str, str]] = {}
    row = db.get(SystemStateRow, HOT_POOL_KEY)
    if row and isinstance(row.value, dict):
        for raw in row.value.get("entries") or []:
            if not isinstance(raw, dict):
                continue
            code = _norm_code(raw.get("symbol"))
            if code:
                prev[code] = {
                    "symbol": code,
                    "name": str(raw.get("name") or "").strip(),
                    "industry": str(raw.get("industry") or "").strip(),
                }
    by_new = {e["symbol"]: e for e in (entries or []) if e.get("symbol")}
    stored: list[dict[str, str]] = []
    for s in symbols:
        code = _norm_code(s)
        if not code:
            continue
        cur = dict(by_new.get(code) or {"symbol": code, "name": "", "industry": ""})
        old = prev.get(code) or {}
        if not cur.get("name"):
            cur["name"] = old.get("name") or ""
        if not cur.get("industry"):
            cur["industry"] = old.get("industry") or ""
        cur["symbol"] = code
        stored.append(cur)
    value = {
        "symbols": symbols,
        "entries": stored,
        "updated_at": datetime.utcnow().isoformat(),
        **(meta or {}),
    }
    if row is None:
        db.add(SystemStateRow(key=HOT_POOL_KEY, value=value))
    else:
        row.value = value
    db.commit()


def load_hot_pool(db: Session) -> list[str]:
    row = db.get(SystemStateRow, HOT_POOL_KEY)
    if row and isinstance(row.value, dict):
        raw = row.value.get("symbols") or []
        out = []
        for s in raw:
            code = _norm_code(s)
            if code:
                out.append(code)
        return out
    return []


def load_hot_entries(db: Session) -> list[dict[str, str]]:
    row = db.get(SystemStateRow, HOT_POOL_KEY)
    symbols = load_hot_pool(db)
    by: dict[str, dict[str, str]] = {}
    if row and isinstance(row.value, dict):
        for raw in row.value.get("entries") or []:
            if not isinstance(raw, dict):
                continue
            code = _norm_code(raw.get("symbol"))
            if not code:
                continue
            by[code] = {
                "symbol": code,
                "name": str(raw.get("name") or "").strip(),
                "industry": str(raw.get("industry") or "").strip(),
            }
    return [
        by.get(s) or {"symbol": s, "name": "", "industry": ""}
        for s in symbols
    ]


def refresh_hot_pool(db: Session) -> list[str]:
    cfg = _hot_cfg()
    if not cfg.get("enabled", True):
        return load_hot_pool(db)
    top_n = int(cfg.get("top_n", 80))
    include_up = bool(cfg.get("include_up_rank", True))
    try:
        entries = fetch_hot_entries(top_n=top_n, include_up_rank=include_up)
        entries = _fill_blank_profiles(entries)
        symbols = [e["symbol"] for e in entries]
    except Exception as exc:  # noqa: BLE001
        logger.warning("refresh hot pool failed: %s", exc)
        return load_hot_pool(db)
    if symbols:
        save_hot_pool(db, symbols, {"source": "eastmoney_hot", "top_n": top_n}, entries=entries)
    return symbols or load_hot_pool(db)


def effective_whitelist(db: Optional[Session] = None) -> list[str]:
    """
    交易/情报可用标的池：
    - hot: 仅热点
    - static: 仅 risk.whitelist
    - merge: 热点 ∪ 手工白名单 ∪ extra（默认）
    """
    risk = load_yaml_config().get("risk") or {}
    cfg = _hot_cfg()
    static = [_norm_code(s) for s in (risk.get("whitelist") or [])]
    static = [s for s in static if s]
    extra = [_norm_code(s) for s in (cfg.get("extra_symbols") or [])]
    extra = [s for s in extra if s]
    bl = {c for c in ([_norm_code(s) for s in (risk.get("blacklist") or [])] + [_norm_code(s) for s in (cfg.get("blacklist") or [])]) if c}

    hot: list[str] = []
    if cfg.get("enabled", True) and db is not None:
        hot = load_hot_pool(db)

    mode = str(cfg.get("mode") or "merge").lower()
    if not cfg.get("enabled", True) or mode == "static":
        universe = static
    elif mode == "hot":
        universe = list(dict.fromkeys(hot + extra))
    else:
        universe = list(dict.fromkeys(hot + static + extra))

    return [s for s in universe if s not in bl]


def hot_pool_status(db: Session) -> dict[str, Any]:
    cfg = _hot_cfg()
    row = db.get(SystemStateRow, HOT_POOL_KEY)
    symbols = load_hot_pool(db)
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "mode": cfg.get("mode") or "merge",
        "top_n": int(cfg.get("top_n", 80)),
        "count": len(symbols),
        "updated_at": (row.value or {}).get("updated_at") if row and isinstance(row.value, dict) else None,
        "sample": symbols[:12],
    }
