"""Alert inbox and workflow: scan, acknowledge, assign, resolve."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, NotificationLog, Project, User
from app.schemas import (
    AlertAcknowledge,
    AlertAssign,
    AlertRead,
    AlertResolve,
    ScanResult,
)
from app.services.audit import record
from app.services.auth import require, scoped_projects
from app.services.notifications.dispatcher import NotificationDispatcher


router = APIRouter(tags=["alerts"])
OPEN_STATES = ("open", "acknowledged")


def alert_in_scope(db: Session, alert_id: int, user: User) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if not db.scalar(scoped_projects(select(Project.project_id).where(Project.project_id == alert.project_id), user)):
        raise HTTPException(403, "Alert outside assigned scope")
    return alert


def serialise(db: Session, alerts: list[Alert]) -> list[dict]:
    """Attach project identity and delivery attempts to each alert."""
    if not alerts:
        return []
    project_ids = {alert.project_id for alert in alerts}
    projects = {
        row.project_id: row
        for row in db.scalars(select(Project).where(Project.project_id.in_(project_ids))).all()
    }
    deliveries: dict[str, list[dict]] = {}
    for delivery in db.scalars(
        select(NotificationLog).where(NotificationLog.project_id.in_(project_ids)).order_by(NotificationLog.id.desc())
    ).all():
        deliveries.setdefault(delivery.project_id, []).append(
            {"channel": delivery.channel, "status": delivery.status, "sent_at": delivery.sent_at}
        )
    rows = []
    for alert in alerts:
        project = projects.get(alert.project_id)
        rows.append({
            "id": alert.id, "project_id": alert.project_id,
            "project_name": project.project_name if project else None,
            "state": project.state if project else None,
            "district": project.district if project else None,
            "risk_score_at_trigger": float(alert.risk_score_at_trigger),
            "message": alert.message, "created_at": alert.created_at,
            "channel": alert.channel, "status": alert.status,
            "severity": alert.severity, "category": alert.category,
            "drivers": alert.drivers or [], "recommendations": alert.recommendations or [],
            "assigned_to": alert.assigned_to, "acknowledged_by": alert.acknowledged_by,
            "acknowledged_at": alert.acknowledged_at, "resolved_by": alert.resolved_by,
            "resolved_at": alert.resolved_at, "resolution_note": alert.resolution_note,
            "deliveries": deliveries.get(alert.project_id, [])[:6],
        })
    return rows


@router.get("/alerts", response_model=list[AlertRead])
def list_alerts(
    status: str | None = Query(None, pattern="^(open|acknowledged|resolved)$"),
    severity: str | None = Query(None, pattern="^(Low|Medium|High)$"),
    assigned_to_me: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), user: User = Depends(require("alerts.read")),
):
    statement = scoped_projects(select(Alert).join(Project), user).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(Alert.status == status)
    if severity:
        statement = statement.where(Alert.severity == severity)
    if assigned_to_me:
        statement = statement.where(Alert.assigned_to == user.id)
    try:
        return serialise(db, list(db.scalars(statement).all()))
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read alerts") from error


@router.get("/alerts/inbox", response_model=list[AlertRead])
def alert_inbox(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(require("alerts.read"))):
    """Unresolved alerts for the caller's scope, most severe first."""
    statement = (
        scoped_projects(select(Alert).join(Project), user)
        .where(Alert.status.in_(OPEN_STATES))
        .order_by(Alert.risk_score_at_trigger.desc(), Alert.created_at.desc())
        .limit(limit)
    )
    try:
        return serialise(db, list(db.scalars(statement).all()))
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read the alert inbox") from error


@router.post("/alerts/scan-now", response_model=ScanResult)
def scan_now(user: User = Depends(require("alerts.read"))):
    """Run the risk scan immediately instead of waiting for the scheduled job."""
    try:
        return NotificationDispatcher().scan_projects()
    except ValueError as error:
        raise HTTPException(500, str(error)) from error


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(alert_id: int, payload: AlertAcknowledge, db: Session = Depends(get_db), user: User = Depends(require("alerts.write"))):
    alert = alert_in_scope(db, alert_id, user)
    if alert.status == "resolved":
        raise HTTPException(409, "Alert is already resolved")
    alert.status = "acknowledged"
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    record(db, user, "ALERT_ACKNOWLEDGED", "alert", alert_id, {"project_id": alert.project_id, "note": payload.note})
    db.commit()
    return serialise(db, [alert])[0]


@router.post("/alerts/{alert_id}/assign", response_model=AlertRead)
def assign_alert(alert_id: int, payload: AlertAssign, db: Session = Depends(get_db), user: User = Depends(require("alerts.write"))):
    alert = alert_in_scope(db, alert_id, user)
    assignee = db.get(User, payload.user_id)
    if assignee is None or assignee.status != "ACTIVE":
        raise HTTPException(404, "Assignee not found or inactive")
    alert.assigned_to = assignee.id
    record(db, user, "ALERT_ASSIGNED", "alert", alert_id, {"project_id": alert.project_id, "assigned_to": assignee.id})
    db.commit()
    return serialise(db, [alert])[0]


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(alert_id: int, payload: AlertResolve, db: Session = Depends(get_db), user: User = Depends(require("alerts.write"))):
    alert = alert_in_scope(db, alert_id, user)
    if alert.status == "resolved":
        raise HTTPException(409, "Alert is already resolved")
    alert.status = "resolved"
    alert.resolved_by = user.id
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolution_note = payload.resolution_note
    record(db, user, "ALERT_RESOLVED", "alert", alert_id, {"project_id": alert.project_id, "note": payload.resolution_note})
    db.commit()
    return serialise(db, [alert])[0]
