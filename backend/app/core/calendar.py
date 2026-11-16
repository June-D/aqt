from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

from backend.app.core.config import ROOT_DIR, load_yaml_config


@lru_cache
def _calendar_cfg() -> dict:
    path = ROOT_DIR / "configs" / "calendar.yaml"
    if not path.exists():
        return {"holidays": [], "makeup_days": []}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_days(values: list) -> set[date]:
    out: set[date] = set()
    for v in values or []:
        if isinstance(v, date):
            out.add(v)
        else:
            out.add(date.fromisoformat(str(v)))
    return out


def is_trading_day(d: Optional[date] = None) -> bool:
    d = d or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    cfg = _calendar_cfg()
    holidays = _parse_days(cfg.get("holidays") or [])
    makeup = _parse_days(cfg.get("makeup_days") or [])
    if d in holidays:
        return False
    if d in makeup:
        return True
    return d.weekday() < 5


def session_open(now: Optional[datetime] = None) -> bool:
    cfg = load_yaml_config()
    tz = ZoneInfo(cfg.get("market", {}).get("timezone", "Asia/Shanghai"))
    now = now or datetime.now(tz)
    if not is_trading_day(now.date()):
        return False
    t = now.timetz().replace(tzinfo=None)
    for s in cfg.get("market", {}).get("sessions", []):
        start = datetime.strptime(s["start"], "%H:%M").time()
        end = datetime.strptime(s["end"], "%H:%M").time()
        if start <= t <= end:
            return True
    return False
