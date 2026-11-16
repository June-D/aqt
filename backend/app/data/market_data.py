from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.app.core.config import ROOT_DIR
from backend.app.core.logging import logger
from backend.app.domain.models import Bar

CACHE_DIR = ROOT_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".SH") or s.endswith(".SZ"):
        return s.split(".")[0]
    return s


def to_akshare_symbol(symbol: str) -> str:
    code = normalize_symbol(symbol)
    return code


class MarketDataService:
    """Fetch and cache A-share daily bars via akshare, with offline fallback."""

    def __init__(self, cache_ttl_hours: int = 12) -> None:
        self.cache_ttl_hours = cache_ttl_hours

    def _cache_path(self, symbol: str) -> Path:
        return CACHE_DIR / f"{normalize_symbol(symbol)}_daily.csv"

    def _is_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < self.cache_ttl_hours * 3600

    def fetch_daily(
        self,
        symbol: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
        force_refresh: bool = False,
    ) -> list[Bar]:
        code = normalize_symbol(symbol)
        path = self._cache_path(code)
        df: Optional[pd.DataFrame] = None

        if not force_refresh and self._is_fresh(path):
            df = pd.read_csv(path, parse_dates=["date"])
        else:
            df = self._download(code)
            if df is None or df.empty:
                if path.exists():
                    logger.warning("akshare failed for %s, using stale cache", code)
                    df = pd.read_csv(path, parse_dates=["date"])
                else:
                    logger.warning("akshare failed for %s, generating synthetic bars", code)
                    df = self._synthetic(code)
                    df.to_csv(path, index=False)
            else:
                df.to_csv(path, index=False)

        assert df is not None
        if "date" not in df.columns and "日期" in df.columns:
            df = df.rename(columns={"日期": "date"})

        df["date"] = pd.to_datetime(df["date"]).dt.date
        if start:
            df = df[df["date"] >= start]
        if end:
            df = df[df["date"] <= end]
        df = df.sort_values("date")

        bars: list[Bar] = []
        for _, row in df.iterrows():
            bars.append(
                Bar(
                    symbol=code,
                    dt=row["date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                )
            )
        return bars

    def latest_price(self, symbol: str) -> float:
        bars = self.fetch_daily(symbol)
        if not bars:
            return 0.0
        return bars[-1].close

    def fetch_minute(self, symbol: str, period: str = "5") -> list[dict]:
        """Intraday bars for research; falls back to empty list."""
        code = normalize_symbol(symbol)
        path = CACHE_DIR / f"{code}_min_{period}.csv"
        df = None
        if self._is_fresh(path):
            df = pd.read_csv(path)
        else:
            df = self._download_minute(code, period)
            if df is not None and not df.empty:
                df.to_csv(path, index=False)
        if df is None or df.empty:
            return []
        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "symbol": code,
                    "time": str(row.get("time") or row.get("时间") or ""),
                    "open": float(row.get("open") or row.get("开盘") or 0),
                    "high": float(row.get("high") or row.get("最高") or 0),
                    "low": float(row.get("low") or row.get("最低") or 0),
                    "close": float(row.get("close") or row.get("收盘") or 0),
                    "volume": float(row.get("volume") or row.get("成交量") or 0),
                }
            )
        return rows[-240:]

    def _download_minute(self, code: str, period: str) -> Optional[pd.DataFrame]:
        try:
            import akshare as ak

            raw = ak.stock_zh_a_hist_min_em(symbol=code, period=period, adjust="qfq")
            if raw is None or raw.empty:
                return None
            return raw
        except Exception as exc:  # noqa: BLE001
            logger.warning("minute download failed for %s: %s", code, exc)
            return None

    def _download(self, code: str) -> Optional[pd.DataFrame]:
        try:
            import akshare as ak

            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y%m%d")
            raw = ak.stock_zh_a_hist(
                symbol=to_akshare_symbol(code),
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            if raw is None or raw.empty:
                return None
            rename = {
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
            }
            df = raw.rename(columns=rename)
            keep = ["date", "open", "high", "low", "close", "volume"]
            return df[keep]
        except Exception as exc:  # noqa: BLE001
            logger.exception("download failed for %s: %s", code, exc)
            return None

    def _synthetic(self, code: str, days: int = 260) -> pd.DataFrame:
        """Deterministic synthetic series for offline/dev smoke tests."""
        import math

        seed = sum(ord(c) for c in code) % 97 + 1
        price = 10.0 + seed
        rows = []
        start = date.today() - timedelta(days=int(days * 1.5))
        d = start
        i = 0
        while len(rows) < days:
            if d.weekday() < 5:
                ret = math.sin((i + seed) / 7.0) * 0.01 + math.cos((i + seed) / 13.0) * 0.005
                open_p = price
                close_p = max(1.0, price * (1 + ret))
                high_p = max(open_p, close_p) * 1.005
                low_p = min(open_p, close_p) * 0.995
                rows.append(
                    {
                        "date": d.isoformat(),
                        "open": round(open_p, 2),
                        "high": round(high_p, 2),
                        "low": round(low_p, 2),
                        "close": round(close_p, 2),
                        "volume": 1_000_000 + i * 1000,
                    }
                )
                price = close_p
                i += 1
            d += timedelta(days=1)
        return pd.DataFrame(rows)


market_data = MarketDataService()