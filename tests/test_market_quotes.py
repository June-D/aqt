"""S7 / S8: AllTick 未配置不返回假价。"""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.db import SessionLocal, init_db
from backend.app.main import app
from backend.app.market import alltick
from backend.app.models import SystemStateRow


def setup_module():
    init_db()


@pytest.fixture(autouse=True)
def _reset_alltick_gate(monkeypatch):
    alltick.reset_rate_limit_state()
    monkeypatch.setattr(alltick, "MIN_INTERVAL_SEC", 0.0)


def _clear_alltick():
    db = SessionLocal()
    try:
        row = db.get(SystemStateRow, "app_settings")
        if row and isinstance(row.value, dict):
            val = dict(row.value)
            md = dict(val.get("market_data") or {})
            md["provider"] = "alltick"
            md["alltick"] = {"token": ""}
            val["market_data"] = md
            row.value = val
            db.commit()
    finally:
        db.close()


def test_quotes_unconfigured_no_fake_price():
    """S7: AllTick 未配置 → 明确未配置，无伪造价格。"""
    _clear_alltick()
    c = TestClient(app)
    r = c.get("/api/market/quotes", params={"symbols": "600519,000001"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "unconfigured"
    assert data.get("provider") == "alltick"
    # 不得出现假数字报价
    quotes = data.get("quotes") or []
    assert quotes == [] or all(q.get("price") is None for q in quotes)


def test_kline_unconfigured_no_fake_bars():
    """S8: K 线未配置 → 明确未配置；支持 period。"""
    _clear_alltick()
    c = TestClient(app)
    r = c.get("/api/market/kline", params={"symbol": "600519", "period": "5m"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "unconfigured"
    assert data.get("period") == "5m"
    assert data.get("bars") == []


def test_quotes_configured_calls_adapter(monkeypatch):
    c = TestClient(app)
    c.put(
        "/api/settings",
        json={
            "section": "market_data",
            "data": {"provider": "alltick", "alltick": {"token": "tok-demo"}},
        },
    )

    def fake_quotes(symbols, token, base_url):
        assert token == "tok-demo"
        return [{"symbol": s, "price": 10.5, "name": s} for s in symbols]

    monkeypatch.setattr(
        "backend.app.market.alltick.fetch_quotes",
        fake_quotes,
    )
    r = c.get("/api/market/quotes", params={"symbols": "600519"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data["quotes"][0]["price"] == 10.5


def test_board_includes_hot_rows_name_industry(monkeypatch):
    c = TestClient(app)
    c.put(
        "/api/settings",
        json={
            "section": "market_data",
            "data": {"provider": "alltick", "alltick": {"token": "tok-demo"}},
        },
    )

    monkeypatch.setattr(
        "backend.app.market.service.load_hot_pool",
        lambda db: ["600519", "000001"],
    )
    monkeypatch.setattr(
        "backend.app.market.service.load_hot_entries",
        lambda db: [
            {"symbol": "600519", "name": "贵州茅台", "industry": "白酒"},
            {"symbol": "000001", "name": "平安银行", "industry": "银行"},
        ],
    )
    monkeypatch.setattr(
        "backend.app.market.alltick.fetch_quotes",
        lambda symbols, token, base_url: [{"symbol": s, "price": 1.0} for s in symbols],
    )
    monkeypatch.setattr(
        "backend.app.market.alltick.fetch_kline",
        lambda *a, **k: [],
    )
    r = c.get("/api/market/board", params={"period": "5m"})
    assert r.status_code == 200
    rows = r.json().get("hot_rows") or []
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["name"] == "贵州茅台"
    assert rows[0]["industry"] == "白酒"
    assert rows[0]["price"] == 1.0
