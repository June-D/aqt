"""iFinD HTTP 行情适配：报价解析、K 线缓存、空 token 保留。"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from backend.app.core.db import init_db
from backend.app.main import app
from backend.app.market import ifind


def setup_module():
    init_db()


def setup_function():
    ifind.reset_state()


def test_to_ifind_code():
    assert ifind.to_ifind_code("600519") == "600519.SH"
    assert ifind.to_ifind_code("000001") == "000001.SZ"
    assert ifind.to_ifind_code("600519.SH") == "600519.SH"


def test_fetch_quotes_parses_tables(monkeypatch):
    payload = {
        "errorcode": 0,
        "errmsg": "Success!",
        "tables": [
            {
                "thscode": "600519.SH",
                "table": {"latest": [1286.0], "volume": [100]},
                "time": ["2026-10-14 15:00:00"],
            },
            {
                "thscode": "000001.SZ",
                "table": {"latest": [11.5]},
            },
        ],
    }

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, **kwargs):
            assert "real_time_quotation" in url
            return _Resp()

    monkeypatch.setattr(ifind, "_access_token", lambda _rt, _base: "atk")
    monkeypatch.setattr(httpx, "Client", _Client)
    out = ifind.fetch_quotes(["600519", "000001"], "refresh-tok")
    assert out[0]["symbol"] == "600519"
    assert out[0]["price"] == 1286.0
    assert out[1]["price"] == 11.5


def test_kline_second_call_uses_cache(monkeypatch):
    calls = {"n": 0}

    def fake(*_a, **_k):
        calls["n"] += 1
        return [{"ts": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]

    monkeypatch.setattr(ifind, "fetch_kline", fake)
    s1, b1, _ = ifind.safe_fetch_kline("600519", "5m", "rt")
    s2, b2, m2 = ifind.safe_fetch_kline("600519", "5m", "rt")
    assert s1 == "ok" and s2 == "ok"
    assert calls["n"] == 1
    assert b1 == b2 and m2 == "cached"


def test_market_data_empty_ifind_token_keeps_previous():
    c = TestClient(app)
    c.put(
        "/api/settings",
        json={
            "section": "market_data",
            "data": {
                "provider": "ifind",
                "ifind": {"refresh_token": "keep-me", "base_url": "https://quantapi.51ifind.com/api/v1"},
            },
        },
    )
    c.put(
        "/api/settings",
        json={
            "section": "market_data",
            "data": {
                "provider": "ifind",
                "ifind": {"refresh_token": "", "base_url": "https://quantapi.51ifind.com/api/v1"},
            },
        },
    )
    view = c.get("/api/settings").json()
    assert view["market_data"]["provider"] == "ifind"
    assert view["market_data"]["ifind"]["refresh_token"] == "keep-me"


def test_quotes_unconfigured_ifind():
    c = TestClient(app)
    c.put(
        "/api/settings",
        json={"section": "market_data", "data": {"provider": "ifind", "ifind": {"refresh_token": ""}}},
    )
    # force clear
    from backend.app.core.db import SessionLocal
    from backend.app.models import SystemStateRow

    db = SessionLocal()
    try:
        row = db.get(SystemStateRow, "app_settings")
        if row and isinstance(row.value, dict):
            val = dict(row.value)
            md = dict(val.get("market_data") or {})
            md["provider"] = "ifind"
            md["ifind"] = {"refresh_token": ""}
            val["market_data"] = md
            row.value = val
            db.commit()
    finally:
        db.close()

    r = c.get("/api/market/quotes", params={"symbols": "600519"})
    assert r.status_code == 200
    assert r.json()["status"] == "unconfigured"
    assert r.json()["provider"] == "ifind"
