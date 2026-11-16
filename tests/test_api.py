from fastapi.testclient import TestClient

from backend.app.core import config as cfg
from backend.app.core.db import init_db
from backend.app.main import app


def setup_module():
    init_db()
    cfg.get_settings.cache_clear()


def setup_function():
    cfg.get_settings.cache_clear()


def test_health():
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json()["service"] == "aqt-api"


def test_strategy_and_backtest_routes_removed():
    """S1: 策略/回测 API 不再存在。"""
    c = TestClient(app)
    checks = [
        c.get("/api/strategies"),
        c.post("/api/strategies", json={}),
        c.delete("/api/strategies/x"),
        c.post("/api/strategies/x/toggle", json={"enabled": True}),
        c.get("/api/backtests"),
        c.post("/api/backtests", json={}),
        c.post("/api/backtests/scan", json={}),
        c.get("/api/backtests/1"),
    ]
    for r in checks:
        assert r.status_code == 404, f"{r.request.method} {r.request.url.path} => {r.status_code}"


def test_risk_reject_lot_and_oversize():
    c = TestClient(app)
    bad_lot = c.post("/api/orders", json={"symbol": "000001", "side": "BUY", "quantity": 50})
    assert bad_lot.status_code == 200
    assert bad_lot.json()["success"] is False

    big = c.post(
        "/api/orders",
        json={"symbol": "600519", "side": "BUY", "quantity": 1000000, "price": 2000},
    )
    assert big.status_code == 200
    assert big.json()["success"] is False
