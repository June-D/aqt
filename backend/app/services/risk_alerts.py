from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import load_yaml_config
from backend.app.core.logging import logger
from backend.app.models import RiskAlertRow, SystemStateRow


def _pushplus_token(db: Session) -> str:
    row = db.get(SystemStateRow, "app_settings")
    if row and isinstance(row.value, dict):
        alerts = row.value.get("alerts") or {}
        token = str(alerts.get("pushplus_token") or "").strip()
        if token:
            return token
    return str((load_yaml_config().get("alerts") or {}).get("pushplus_token") or "").strip()


def _pushplus_topic(db: Session) -> str:
    row = db.get(SystemStateRow, "app_settings")
    if row and isinstance(row.value, dict):
        alerts = row.value.get("alerts") or {}
        topic = str(alerts.get("pushplus_topic") or "").strip()
        if topic:
            return topic
    return str((load_yaml_config().get("alerts") or {}).get("pushplus_topic") or "").strip()


def _try_pushplus(db: Session, title: str, content: str) -> str:
    token = _pushplus_token(db)
    if not token:
        return "unconfigured"
    payload: dict[str, Any] = {
        "token": token,
        "title": title[:100],
        "content": content[:2000],
        "template": "txt",
    }
    topic = _pushplus_topic(db)
    if topic:
        payload["topic"] = topic
    try:
        import httpx

        resp = httpx.post("https://www.pushplus.plus/send", json=payload, timeout=8.0)
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and int(data.get("code", 0)) == 200:
            return "ok"
        logger.warning("pushplus failed: %s %s", resp.status_code, data)
        return "failed"
    except Exception:  # noqa: BLE001
        logger.exception("pushplus request error")
        return "failed"


def emit_risk_alert(
    db: Session,
    event_type: str,
    message: str,
    symbol: Optional[str] = None,
    level: str = "warn",
    detail: Optional[dict] = None,
    title: Optional[str] = None,
) -> RiskAlertRow:
    title = title or event_type
    row = RiskAlertRow(
        event_type=event_type,
        level=level,
        title=title,
        symbol=symbol,
        message=message,
        detail=detail or {},
        push_status="pending",
        read=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row.push_status = _try_pushplus(db, title, f"[{event_type}] {symbol or '-'} {message}")
    db.commit()
    db.refresh(row)
    return row


def list_risk_alerts(db: Session, limit: int = 100) -> list[RiskAlertRow]:
    return db.query(RiskAlertRow).order_by(RiskAlertRow.id.desc()).limit(limit).all()


def mark_risk_alert_read(db: Session, alert_id: int) -> Optional[RiskAlertRow]:
    row = db.get(RiskAlertRow, alert_id)
    if row is None:
        return None
    row.read = True
    db.commit()
    db.refresh(row)
    return row
