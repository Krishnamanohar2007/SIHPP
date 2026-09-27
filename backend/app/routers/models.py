"""Model registry: inspect the served model, retrain, activate, re-score."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ModelVersion, User
from app.schemas import ModelVersionRead, RescoreResult, RetrainRequest, RetrainResult
from app.services.audit import record
from app.services.auth import require
from app.services.ml_service import ModelUnavailableError, get_ml_service, reload_ml_service
from app.services.scoring import rescore_all
from app.services.training import retrain as run_retrain, set_active_pointer


router = APIRouter(prefix="/models", tags=["models"])


@router.get("/active")
def active_model(user: User = Depends(require("analytics.read"))):
    """Model card of the version currently serving predictions."""
    try:
        return get_ml_service().model_info()
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("", response_model=list[ModelVersionRead])
def list_versions(db: Session = Depends(get_db), user: User = Depends(require("analytics.read"))):
    try:
        return db.scalars(select(ModelVersion).order_by(ModelVersion.trained_at.desc())).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read the model registry") from error


@router.post("/retrain", response_model=RetrainResult)
def retrain_models(payload: RetrainRequest, db: Session = Depends(get_db), user: User = Depends(require("models.manage"))):
    """Train a new bundle from the seed history plus recorded outcomes.

    The new version is activated only when it scores at least as well as the
    current one, unless the caller forces activation.
    """
    try:
        result = run_retrain(db, actor=user, force_activate=payload.force_activate, notes=payload.notes)
        db.commit()
    except ModelUnavailableError as error:
        db.rollback()
        raise HTTPException(503, str(error)) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not register the trained model") from error
    return result


@router.post("/{version}/activate", response_model=ModelVersionRead)
def activate_version(version: str, db: Session = Depends(get_db), user: User = Depends(require("models.manage"))):
    """Switch serving to a specific registered version, including a rollback."""
    target = db.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if target is None:
        raise HTTPException(404, "Model version not found")
    try:
        set_active_pointer(version)
    except ModelUnavailableError as error:
        raise HTTPException(409, str(error)) from error
    for existing in db.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))).all():
        existing.is_active = False
    target.is_active = True
    record(db, user, "MODEL_ACTIVATED", "model_version", version, {"metrics": target.metrics})
    try:
        db.commit()
        db.refresh(target)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not activate the model version") from error
    return target


@router.post("/reload")
def reload_model(user: User = Depends(require("models.manage"))):
    """Reload the bundle from disk without restarting the API process."""
    try:
        return reload_ml_service().model_info()
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/rescore", response_model=RescoreResult)
def rescore_portfolio(snapshot: bool = True, db: Session = Depends(get_db), user: User = Depends(require("models.manage"))):
    """Re-score every project with the active model, refreshing stored risk fields."""
    try:
        result = rescore_all(db, snapshot=snapshot, source="rescore")
        record(db, user, "PORTFOLIO_RESCORED", "project", "all", result)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not re-score the portfolio") from error
    return {"scored": result.get("scored", 0), "changed": result.get("changed", 0),
            "snapshots": result.get("snapshots", 0), "skipped": result.get("skipped")}
