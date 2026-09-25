from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers.projects import router as projects_router
from app.services.notifications import NotificationDispatcher

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router)
notification_scheduler = BackgroundScheduler(timezone="UTC")


@app.on_event("startup")
def start_notification_scheduler() -> None:
    dispatcher = NotificationDispatcher()
    # Seed the alert feed for a new database instead of waiting for the first
    # scheduled scan. Existing open alerts are deduplicated by the dispatcher.
    dispatcher.scan_projects()
    notification_scheduler.add_job(dispatcher.scan_projects, "interval", minutes=settings.notification_scan_interval_minutes, id="risk-notification-scan", replace_existing=True, max_instances=1, coalesce=True)
    if not notification_scheduler.running:
        notification_scheduler.start()


@app.on_event("shutdown")
def stop_notification_scheduler() -> None:
    if notification_scheduler.running:
        notification_scheduler.shutdown(wait=False)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
