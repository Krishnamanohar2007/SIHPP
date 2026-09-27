"""Risk-threshold alert dispatch, driver attribution and delivery logging.

The scan is the platform's automated detection step: it re-scores every project
with the active model, records a metric snapshot, and raises one open alert per
project whose risk crosses the configured threshold. Each alert carries the
explained delay drivers and the ranked corrective actions, so an alert is
actionable on its own without a second API call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Alert, NotificationLog, Project
from app.services.ml_service import ModelUnavailableError, get_ml_service
from app.services.notifications.channels import CHANNEL_TYPES, NotificationChannel
from app.services.scoring import apply_prediction, capture_snapshot, feature_values, score


logger = logging.getLogger(__name__)


def severity_for(risk_score: float) -> str:
    return "High" if risk_score > 75 else "Medium" if risk_score > 60 else "Low"


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

    def _explanation(self, project: Project) -> dict[str, Any]:
        """Best-effort driver attribution; an alert is still raised without it."""
        try:
            service = get_ml_service()
            return service.explain(feature_values(project, service))
        except (ModelUnavailableError, ValueError) as error:
            logger.warning("alert explanation unavailable project=%s error=%s", project.project_id, error)
            return {}

    def dispatch(self, project: Project, db: Session, category: str = "Risk threshold") -> Alert:
        risk_score = float(project.risk_score)
        explanation = self._explanation(project)
        drivers = explanation.get("delay_drivers", [])[:4]
        recommendations = explanation.get("recommendations", [])[:4]
        top_driver = drivers[0]["driver"] if drivers else "multiple factors"
        message = (
            f"Risk alert: {project.project_name} ({project.project_id}) scored {risk_score:.2f}, "
            f"above threshold {self.threshold:.2f}. Leading driver: {top_driver}."
        )
        metadata: dict[str, Any] = {
            "project_id": project.project_id, "project_name": project.project_name,
            "state": project.state, "district": project.district,
            "risk_score": risk_score, "risk_category": project.risk_category,
            "delay_probability": float(project.delay_probability),
            "lifecycle_stage": project.lifecycle_stage,
            "threshold": self.threshold, "top_driver": top_driver,
            "model_version": explanation.get("model_version"),
        }
        alert = Alert(
            project_id=project.project_id,
            risk_score_at_trigger=project.risk_score,
            message=message,
            channel=",".join(channel.name for channel in self.channels),
            status="open",
            severity=severity_for(risk_score),
            category=category,
            drivers=drivers,
            recommendations=recommendations,
        )
        db.add(alert)
        for channel in self.channels:
            try:
                outcome = channel.send(self.recipient, message, metadata)
                db.add(NotificationLog(project_id=project.project_id, channel=channel.name, recipient=self.recipient, status="sent", sent_at=datetime.now(timezone.utc), payload={**metadata, **outcome}))
            except Exception as error:  # a failed transport must not lose the alert
                db.add(NotificationLog(project_id=project.project_id, channel=channel.name, recipient=self.recipient, status="failed", sent_at=None, payload={**metadata, "error": str(error)}))
        return alert

    def scan_projects(self, rescore: bool = True, snapshot: bool = True) -> dict[str, Any]:
        """Re-score the portfolio, snapshot it, and raise alerts over threshold."""
        db = SessionLocal()
        try:
            try:
                service = get_ml_service()
            except ModelUnavailableError as error:
                logger.warning("risk scan skipped: %s", error)
                return {"triggered": 0, "scored": 0, "snapshots": 0, "skipped": str(error)}

            projects = db.scalars(select(Project)).all()
            scored = snapshots = 0
            for project in projects:
                if not rescore:
                    continue
                prediction = score(project, service)
                apply_prediction(project, prediction)
                scored += 1
                if snapshot:
                    capture_snapshot(db, project, prediction, source="scheduled")
                    snapshots += 1
            db.flush()

            # An alert stays deduplicated while it is open or acknowledged; once it
            # is resolved and risk is still high, a fresh alert is raised.
            active_ids = set(db.scalars(
                select(Alert.project_id).where(Alert.status.in_(["open", "acknowledged"]))
            ).all())
            triggered = 0
            for project in projects:
                if float(project.risk_score) > self.threshold and project.project_id not in active_ids:
                    self.dispatch(project, db)
                    triggered += 1
            db.commit()
            return {"triggered": triggered, "scored": scored, "snapshots": snapshots}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
