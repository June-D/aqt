"""S2 / S3: 状态条与 LIVE 密码校验。"""

from fastapi.testclient import TestClient

from backend.app.core.db import init_db
from backend.app.main import app


def setup_module():
    init_db()


REQUIRED_STATUS_KEYS = {
    "mode",
    "live_trading_enabled",
    "auto_trade_enabled",
    "market_data_status",
    "push_status",
    "llm_configured",
    "intel_source_configured",
    "risk_enabled",
    "broker_status",
    "next_run_at",
}


def test_status_bar_has_required_fields():
    """S2: GET /api/system/status-bar 含完整状态字段。"""
    c = TestClient(app)
    r = c.get("/api/system/status-bar")
    assert r.status_code == 200
    data = r.json()
    missing = REQUIRED_STATUS_KEYS - set(data)
    assert not missing, f"missing keys: {missing}"


def test_live_enable_requires_correct_password(monkeypatch):
    """S3: LIVE 开启错误密码拒绝；正确密码成功。"""
    from backend.app.core import config as cfg

    monkeypatch.setenv("APP_PASSWORD", "secret-live")
    cfg.get_settings.cache_clear()

    c = TestClient(app)
    token = c.post("/api/auth/login", json={"username": "aqt", "password": "secret-live"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    bad = c.put(
        "/api/settings",
        headers=headers,
        json={"section": "trading", "data": {"mode": "live"}, "password": "wrong"},
    )
    assert bad.status_code in (400, 401, 403)
    assert "密码" in str(bad.json().get("detail", bad.text))

    ok = c.put(
        "/api/settings",
        headers=headers,
        json={"section": "trading", "data": {"mode": "live"}, "password": "secret-live"},
    )
    assert ok.status_code == 200
    body = ok.json()
    trading = body.get("trading") or body
    assert trading.get("mode") == "live"

    bar = c.get("/api/system/status-bar", headers=headers).json()
    assert bar["mode"] == "live"
    assert bar["live_trading_enabled"] is True

    back = c.put(
        "/api/settings",
        headers=headers,
        json={"section": "trading", "data": {"mode": "sim"}},
    )
    assert back.status_code == 200
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    cfg.get_settings.cache_clear()
