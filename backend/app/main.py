"""API application: routers, scheduled jobs and startup bootstrap."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import ModelVersion, Role, User
from app.routers.alerts import router as alerts_router
from app.routers.analytics import router as analytics_router
from app.routers.auth import router as auth_router
from app.routers.integration import router as integration_router
from app.routers.models import router as models_router
from app.routers.projects import router as projects_router
from app.services.auth import hash_password
from app.services.ml_service import ModelUnavailableError, get_ml_service
from app.services.notifications import NotificationDispatcher
from app.services.training import register_version


logger = logging.getLogger(__name__)
settings = get_settings()

DESCRIPTION = """
AI-enabled decision support for land-acquisition delay risk.

* Portfolio and per-stage delay prediction with SHAP explanations
* Automated risk scanning, alert workflow and audit trail
* Role-scoped analytics: geographic trends, timelines and comparatives
* Continuous learning from recorded project outcomes
* API-key integration surface for external government systems
"""

app = FastAPI(title=settings.app_name, version="1.0.0", description=DESCRIPTION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROUTERS = (projects_router, auth_router, analytics_router, alerts_router, models_router, integration_router)
for router in ROUTERS:
    app.include_router(router)
    # Versioned mount. External clients pin /api/v1; the unprefixed paths stay in
    # place so the existing frontend and any current integration keep working.
    app.include_router(router, prefix="/api/v1", include_in_schema=False)

scheduler = BackgroundScheduler(timezone="UTC")


def bootstrap_admin() -> None:
    """Create the configured bootstrap administrator when it does not exist."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    email = settings.bootstrap_admin_email.lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            return
        role = db.scalar(select(Role).where(Role.code == "ADMIN"))
        if role is None:
            logger.warning("bootstrap admin skipped: ADMIN role is missing, run migrations first")
            return
        db.add(User(
            official_name="Bootstrap Administrator", organization="Bhoomi Setu",
            designation="Administrator", email=email, employee_id="BOOTSTRAP-ADMIN",
            password_hash=hash_password(settings.bootstrap_admin_password), role=role,
        ))
        db.commit()


def register_bundled_model() -> None:
    """Record the model bundle shipped on disk so the registry is never empty."""
    try:
        service = get_ml_service()
    except ModelUnavailableError as error:
        logger.warning("model registry bootstrap skipped: %s", error)
        return
    with SessionLocal() as db:
        if db.scalar(select(ModelVersion).where(ModelVersion.version == service.version)):
            return
        register_version(db, service.card, actor=None, activate=True, notes="Bundled model detected at startup")
        db.commit()


def run_risk_scan() -> None:
    """Scheduled job: re-score, snapshot and raise threshold alerts."""
    try:
        result = NotificationDispatcher().scan_projects()
        logger.info("risk scan complete %s", result)
    except Exception:  # a scheduler job must never take the process down
        logger.exception("risk scan failed")


def run_scheduled_retrain() -> None:
    """Optional scheduled continuous learning, disabled unless configured."""
    from app.services.training import retrain

    try:
        with SessionLocal() as db:
            result = retrain(db, actor=None, notes="Scheduled retraining")
            db.commit()
        logger.info("scheduled retraining complete %s", result)
    except Exception:
        logger.exception("scheduled retraining failed")


@app.on_event("startup")
def on_startup() -> None:
    bootstrap_admin()
    register_bundled_model()
    # Seed the alert feed and snapshot history for a new database instead of
    # waiting a full interval for the first scheduled scan. This runs as a job a
    # few seconds from now rather than inline: scanning a large register takes
    # longer than a container healthcheck window, and startup must not block on
    # it. Open alerts are deduplicated, so an extra scan is harmless.
    scheduler.add_job(run_risk_scan, "date", run_date=datetime.now(timezone.utc) + timedelta(seconds=5), id="initial-risk-scan", replace_existing=True)
    scheduler.add_job(
        run_risk_scan, "interval", minutes=settings.notification_scan_interval_minutes,
        id="risk-notification-scan", replace_existing=True, max_instances=1, coalesce=True,
    )
    if settings.retrain_interval_hours > 0:
        scheduler.add_job(
            run_scheduled_retrain, "interval", hours=settings.retrain_interval_hours,
            id="continuous-learning-retrain", replace_existing=True, max_instances=1, coalesce=True,
        )
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, object]:
    try:
        version = get_ml_service().version
    except ModelUnavailableError:
        version = None
    return {"status": "ok", "environment": settings.environment, "model_version": version}
