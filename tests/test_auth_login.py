"""单用户登录：无注册；设了 APP_PASSWORD 后所有 /api 需登录。"""

import pytest
from fastapi.testclient import TestClient

from backend.app.core import config as cfg
from backend.app.core.db import init_db
from backend.app.main import app


def setup_module():
    init_db()


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "aqt")
    monkeypatch.setenv("APP_PASSWORD", "desk-pass")
    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


def test_unauthenticated_api_is_401():
    c = TestClient(app)
    r = c.get("/api/system/status-bar")
    assert r.status_code == 401
    assert "未登录" in str(r.json().get("detail", r.text))


def test_login_rejects_wrong_username():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "other", "password": "desk-pass"})
    assert r.status_code == 401


def test_login_rejects_password_only():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"password": "desk-pass"})
    assert r.status_code == 401


def test_login_then_api_ok():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "aqt", "password": "desk-pass"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token
    ok = c.get("/api/system/status-bar", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
