"""兼容旧 emit_alert 调用，统一落到 risk_alerts。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models import RiskAlertRow
from backend.app.services.risk_alerts import emit_risk_alert, list_risk_alerts, mark_risk_alert_read


def emit_alert(
    db: Session,
    level: str,
    title: str,
    message: str,
    detail: Optional[dict] = None,
) -> RiskAlertRow:
    return emit_risk_alert(
        db,
        event_type=title,
        message=message,
        level=level,
        detail=detail,
        title=title,
    )


def list_alerts(db: Session, unread_only: bool = False, limit: int = 100):
    rows = list_risk_alerts(db, limit=limit)
    if unread_only:
        rows = [r for r in rows if not r.read]
    return rows


def mark_read(db: Session, alert_id: int):
    return mark_risk_alert_read(db, alert_id)
