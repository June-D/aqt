"""S4: 风控与告警合并；PushPlus 未配置仍落库。"""

from fastapi.testclient import TestClient

from backend.app.core.db import SessionLocal, init_db
from backend.app.main import app
from backend.app.services.risk_alerts import emit_risk_alert, list_risk_alerts


def setup_module():
    init_db()


def test_risk_alert_persists_when_push_unconfigured():
    db = SessionLocal()
    try:
        row = emit_risk_alert(
            db,
            event_type="LOT_SIZE",
            message="数量必须为 100 的整数倍",
            symbol="000001",
            level="warn",
            detail={"qty": 50},
        )
        assert row.id is not None
        assert row.push_status == "unconfigured"
        rows = list_risk_alerts(db, limit=5)
        assert any(r.id == row.id for r in rows)
    finally:
        db.close()

    c = TestClient(app)
    r = c.get("/api/risk-alerts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(item.get("event_type") == "LOT_SIZE" for item in data)
