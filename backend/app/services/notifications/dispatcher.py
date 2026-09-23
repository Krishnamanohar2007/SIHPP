"""Risk-threshold alert dispatch and audit logging."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Alert, NotificationLog, Project
from app.services.notifications.channels import CHANNEL_TYPES, NotificationChannel


class NotificationDispatcher:
    def __init__(self, channels: list[str] | None = None) -> None:
        settings = get_settings()
        names = channels or settings.notification_channels
        unknown = set(names) - set(CHANNEL_TYPES)
        if unknown:
            raise ValueError(f"Unknown notification channels: {', '.join(sorted(unknown))}")
        self.channels: list[NotificationChannel] = [CHANNEL_TYPES[name]() for name in names]
        self.threshold = settings.notification_risk_threshold
        self.recipient = settings.notification_recipient

    def dispatch(self, project: Project, db: Session) -> Alert:
        risk_score = float(project.risk_score)
        message = f"Risk alert: {project.project_name} ({project.project_id}) has risk score {risk_score:.2f}, above threshold {self.threshold:.2f}."
        metadata: dict[str, Any] = {"project_id": project.project_id, "project_name": project.project_name, "risk_score": risk_score, "risk_category": project.risk_category, "threshold": self.threshold}
        alert = Alert(project_id=project.project_id, risk_score_at_trigger=project.risk_score, message=message, channel=",".join(channel.name for channel in self.channels), status="open")
        db.add(alert)
        for channel in self.channels:
            try:
                outcome = channel.send(self.recipient, message, metadata)
                db.add(NotificationLog(project_id=project.project_id, channel=channel.name, recipient=self.recipient, status="sent", sent_at=datetime.now(timezone.utc), payload={**metadata, **outcome}))
            except Exception as error:
                db.add(NotificationLog(project_id=project.project_id, channel=channel.name, recipient=self.recipient, status="failed", sent_at=None, payload={**metadata, "error": str(error)}))
        return alert

    def scan_projects(self) -> int:
        db = SessionLocal()
        try:
            projects = db.scalars(select(Project).where(Project.risk_score > self.threshold)).all()
            active_project_ids = set(db.scalars(select(Alert.project_id).where(Alert.status == "open")).all())
            triggered = 0
            for project in projects:
                if project.project_id not in active_project_ids:
                    self.dispatch(project, db)
                    triggered += 1
            db.commit()
            return triggered
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
