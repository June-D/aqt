"""S5 / S6 / S10: 抛售、账户总览、重置模拟资金。"""

from fastapi.testclient import TestClient

from backend.app.core.db import SessionLocal, init_db
from backend.app.main import app
from backend.app.models import AccountSnapshotRow, FillRow, OrderRow, PositionRow


def setup_module():
    init_db()


def _seed_position(symbol="600519", qty=100, cost=10.0, cash=1_000_000.0):
    db = SessionLocal()
    try:
        db.query(FillRow).delete()
        db.query(OrderRow).delete()
        db.query(PositionRow).delete()
        db.query(AccountSnapshotRow).delete()
        if qty > 0:
            db.add(PositionRow(symbol=symbol, quantity=qty, avg_cost=cost))
        db.add(
            AccountSnapshotRow(
                cash=cash,
                market_value=qty * cost,
                total_equity=cash + qty * cost,
                daily_pnl=0.0,
            )
        )
        db.commit()
    finally:
        db.close()


def test_liquidate_requires_confirm_and_handles_empty(monkeypatch):
    """S5: 无持仓明确失败；有持仓则全量卖。"""
    from backend.app.data.market_data import market_data as md_svc

    monkeypatch.setattr(md_svc, "latest_price", lambda symbol: 12.0)
    monkeypatch.setattr(
        "backend.app.services.account_desk.market_data.latest_price",
        lambda symbol: 12.0,
    )
    monkeypatch.setattr("backend.app.risk.gate.is_trading_day", lambda: True)
    monkeypatch.setattr("backend.app.risk.gate.session_open", lambda: True)
    monkeypatch.setattr(
        "backend.app.services.hot_universe.effective_whitelist",
        lambda db: ["600519"],
    )

    c = TestClient(app)
    _seed_position(qty=0)
    no_pos = c.post("/api/positions/liquidate", json={"confirm": True})
    assert no_pos.status_code == 200
    assert no_pos.json().get("success") is False

    _seed_position()
    r = c.post("/api/positions/liquidate", json={"confirm": True})
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    assert body.get("sold_count", 0) >= 1


def test_account_overview_fields(monkeypatch):
    """S6: 总览六项；行情可用时给出盈亏数字。"""
    _seed_position()
    from backend.app.data.market_data import market_data as md_svc

    monkeypatch.setattr(md_svc, "latest_price", lambda symbol: 12.0)
    c = TestClient(app)
    c.put(
        "/api/settings",
        json={
            "section": "market_data",
            "data": {"provider": "alltick", "alltick": {"token": "test-token"}},
        },
    )
    r = c.get("/api/account/overview")
    assert r.status_code == 200
    data = r.json()
    for key in ("total_equity", "cash", "market_value", "daily_pnl", "month_pnl", "total_pnl", "fees"):
        assert key in data
    assert data.get("quote_status") == "ok"
    assert data["market_value"] > 0
    assert data["fees"] >= 0


def test_reset_sim_cash_clears_positions_and_fills():
    """S10: 改模拟资金清空持仓与流水。"""
    _seed_position()
    db = SessionLocal()
    try:
        db.add(
            FillRow(
                order_id="o1",
                symbol="600519",
                side="BUY",
                quantity=100,
                price=10.0,
            )
        )
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    r = c.put(
        "/api/settings",
        json={"section": "sim", "data": {"initial_cash": 500000, "reset": True}},
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(PositionRow).filter(PositionRow.quantity > 0).count() == 0
        assert db.query(FillRow).count() == 0
        snap = db.query(AccountSnapshotRow).order_by(AccountSnapshotRow.id.desc()).first()
        assert snap is not None
        assert abs(float(snap.cash) - 500000) < 0.01
    finally:
        db.close()
