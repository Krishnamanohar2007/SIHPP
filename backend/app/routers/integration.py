"""Integration API for external land-acquisition and government systems.

Two surfaces live here:

* ``/integration/api-keys`` - administrators issue, list and revoke service keys.
* ``/integration/v1/*``     - machine endpoints authenticated with ``X-API-Key``.

The machine endpoints deliberately mirror the interactive ones but use key scopes
and the key's geographic limits instead of a user role, so an external system can
push records in and pull scored records back without a human session.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiClient, Project, User
from app.schemas import (
    ApiClientCreate,
    ApiClientCreated,
    ApiClientRead,
    IngestResult,
    ProjectCreate,
    ProjectRead,
)
from app.services import analytics
from app.services.audit import record
from app.services.auth import require
from app.services.integration import SCOPES, generate_key, require_scope, scoped_for_client
from app.services.ml_service import ModelUnavailableError, get_ml_service
from app.services.scoring import capture_snapshot, feature_values, rescore_project


router = APIRouter(prefix="/integration", tags=["integration"])
DERIVED_FIELDS = ("risk_score", "delay_probability", "risk_category")


# --------------------------------------------------------------- key management
@router.get("/scopes")
def available_scopes(user: User = Depends(require("integration.manage"))):
    return [{"scope": scope, "description": description} for scope, description in SCOPES.items()]


@router.get("/api-keys", response_model=list[ApiClientRead])
def list_api_keys(db: Session = Depends(get_db), user: User = Depends(require("integration.manage"))):
    return db.scalars(select(ApiClient).order_by(ApiClient.created_at.desc())).all()


@router.post("/api-keys", response_model=ApiClientCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiClientCreate, db: Session = Depends(get_db), user: User = Depends(require("integration.manage"))):
    """Issue a key. The secret is returned once and never stored in clear text."""
    unknown = sorted(set(payload.scopes) - set(SCOPES))
    if unknown:
        raise HTTPException(422, f"Unknown scopes: {', '.join(unknown)}")
    if db.scalar(select(ApiClient).where(ApiClient.name == payload.name)):
        raise HTTPException(409, "An API client with that name already exists")
    api_key, prefix, digest = generate_key()
    client = ApiClient(
        name=payload.name, key_prefix=prefix, key_hash=digest, scopes=payload.scopes,
        state=payload.state, district=payload.district, created_by=user.id,
    )
    db.add(client)
    record(db, user, "API_KEY_ISSUED", "api_client", prefix, {
        "name": payload.name, "scopes": payload.scopes, "state": payload.state, "district": payload.district,
    })
    try:
        db.commit()
        db.refresh(client)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not issue the API key") from error
    return {**ApiClientRead.model_validate(client).model_dump(), "api_key": api_key}


@router.delete("/api-keys/{client_id}", response_model=ApiClientRead)
def revoke_api_key(client_id: int, db: Session = Depends(get_db), user: User = Depends(require("integration.manage"))):
    client = db.get(ApiClient, client_id)
    if client is None:
        raise HTTPException(404, "API client not found")
    client.status = "REVOKED"
    record(db, user, "API_KEY_REVOKED", "api_client", client.key_prefix, {"name": client.name})
    try:
        db.commit()
        db.refresh(client)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not revoke the API key") from error
    return client


# ------------------------------------------------------------ machine endpoints
@router.get("/v1/projects", response_model=list[ProjectRead])
def integration_projects(
    state: str | None = None,
    district: str | None = None,
    risk_category: str | None = None,
    updated_since: datetime | None = Query(None, description="Return only projects changed after this timestamp"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("projects.read")),
):
    """Scored project records for downstream systems, with incremental sync."""
    statement = scoped_for_client(select(Project), client)
    for column, value in ((Project.state, state), (Project.district, district), (Project.risk_category, risk_category)):
        if value:
            statement = statement.where(column == value)
    if updated_since:
        statement = statement.where(Project.updated_at >= updated_since)
    return db.scalars(statement.order_by(Project.updated_at.desc()).offset(offset).limit(limit)).all()


@router.get("/v1/projects/{project_id}", response_model=ProjectRead)
def integration_project(project_id: str, db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("projects.read"))):
    project = db.scalar(scoped_for_client(select(Project).where(Project.project_id == project_id), client))
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/v1/projects/{project_id}/prediction")
def integration_prediction(project_id: str, db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("projects.read"))):
    """Prediction plus explanation in one response, for external dashboards."""
    project = db.scalar(scoped_for_client(select(Project).where(Project.project_id == project_id), client))
    if project is None:
        raise HTTPException(404, "Project not found")
    try:
        service = get_ml_service()
        values = feature_values(project, service)
        return {"project_id": project_id, **service.predict(values), "explanation": service.explain(values)}
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/v1/projects/sync", response_model=IngestResult)
def integration_sync(
    payloads: list[ProjectCreate],
    db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("projects.write")),
):
    """Upsert a batch of project records and score each one.

    Rows outside the key's geographic limits are rejected individually rather
    than failing the whole batch, so a partial feed still makes progress.
    """
    if not payloads:
        raise HTTPException(422, "Send at least one project record")
    if len(payloads) > 500:
        raise HTTPException(413, "Send at most 500 records per request")
    try:
        service = get_ml_service()
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error

    created = updated = scored = 0
    rejected: list[dict] = []
    for payload in payloads:
        if client.state and payload.state != client.state:
            rejected.append({"project_id": payload.project_id, "reason": f"outside key state scope ({client.state})"})
            continue
        if client.district and payload.district != client.district:
            rejected.append({"project_id": payload.project_id, "reason": f"outside key district scope ({client.district})"})
            continue
        values = {name: value for name, value in payload.model_dump().items() if name not in DERIVED_FIELDS}
        project = db.get(Project, payload.project_id)
        if project is None:
            project = Project(**values)
            db.add(project)
            created += 1
        else:
            for field, value in values.items():
                setattr(project, field, value)
            updated += 1
        prediction = rescore_project(project, service)
        db.flush()
        capture_snapshot(db, project, prediction, source="integration")
        scored += 1

    record(db, None, "INTEGRATION_SYNC", "api_client", client.key_prefix, {
        "received": len(payloads), "created": created, "updated": updated, "rejected": len(rejected),
    })
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not synchronise the batch") from error
    return IngestResult(received=len(payloads), created=created, updated=updated, scored=scored, rejected=rejected)


@router.get("/v1/analytics/kpis")
def integration_kpis(db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("analytics.read"))):
    return analytics.kpis(db, scoped_for_client(select(Project), client))


@router.get("/v1/analytics/trends")
def integration_trends(
    level: str = Query("state", pattern="^(state|district)$"),
    db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("analytics.read")),
):
    return analytics.geography_trends(db, scoped_for_client(select(Project), client), level)


@router.get("/v1/health")
def integration_health(db: Session = Depends(get_db), client: ApiClient = Depends(require_scope("projects.read"))):
    """Connectivity probe for an integrating system, including the model version."""
    total = db.scalar(select(func.count()).select_from(scoped_for_client(select(Project), client).subquery())) or 0
    try:
        version = get_ml_service().version
    except ModelUnavailableError:
        version = None
    return {
        "status": "ok",
        "client": client.name,
        "scopes": client.scopes,
        "visible_projects": int(total),
        "model_version": version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
