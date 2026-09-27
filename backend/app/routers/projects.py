"""Project register, prediction, explanation and outcome endpoints."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.schemas import (
    BulkUploadResult,
    Explanation,
    OutcomeCreate,
    Prediction,
    ProjectCreate,
    ProjectPage,
    ProjectPreview,
    ProjectPreviewCreate,
    ProjectRead,
    SnapshotPoint,
    SummaryStats,
)
from app.services import analytics
from app.services.audit import changed_fields, record
from app.services.auth import require, scoped_projects
from app.services.india_locations import india_state_districts, reverse_geocode
from app.services.ml_service import ModelUnavailableError, get_ml_service
from app.services.project_csv import sync_projects_to_csv
from app.services.scoring import capture_snapshot, feature_values, rescore_project


router = APIRouter(tags=["projects"])
PROJECT_COLUMNS = set(ProjectCreate.model_fields)
DERIVED_FIELDS = ("risk_score", "delay_probability", "risk_category")


def filtered_projects(country: str | None, state: str | None, district: str | None, land_type: str | None, risk_category: str | None, project_type: str | None, lifecycle_stage: str | None = None):
    statement = select(Project)
    for column, value in (
        (Project.country, country), (Project.state, state), (Project.district, district),
        (Project.land_type, land_type), (Project.risk_category, risk_category),
        (Project.project_type, project_type), (Project.lifecycle_stage, lifecycle_stage),
    ):
        if value:
            statement = statement.where(column == value)
    return statement


def project_in_scope(db: Session, project_id: str, user: User) -> Project:
    """Fetch a project or fail with the right status for the caller's scope."""
    try:
        project = db.get(Project, project_id)
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read project") from error
    if project is None:
        raise HTTPException(404, "Project not found")
    if not db.scalar(scoped_projects(select(Project.project_id).where(Project.project_id == project_id), user)):
        raise HTTPException(403, "Project outside assigned scope")
    return project


def active_service():
    try:
        return get_ml_service()
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/projects", response_model=ProjectPage)
def list_projects(
    country: str | None = None,
    state: str | None = None,
    district: str | None = None,
    land_type: str | None = None,
    risk_category: str | None = None,
    project_type: str | None = None,
    lifecycle_stage: str | None = None,
    min_delay_probability: float | None = Query(None, ge=0, le=1),
    sort: str = Query("project_id", pattern="^(project_id|project_name|risk_score|delay_probability|state|district|lifecycle_stage)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), user: User = Depends(require("projects.read")),
):
    statement = scoped_projects(
        filtered_projects(country, state, district, land_type, risk_category, project_type, lifecycle_stage), user
    )
    if min_delay_probability is not None:
        statement = statement.where(Project.delay_probability >= min_delay_probability)
    column = getattr(Project, sort)
    statement = statement.order_by(column.desc() if order == "desc" else column.asc())
    try:
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = db.scalars(statement.offset(offset).limit(limit)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read projects") from error
    return ProjectPage(items=items, total=total, offset=offset, limit=limit)


@router.get("/projects/geo")
def projects_geo(
    risk_category: str | None = None,
    min_delay_probability: float | None = Query(None, ge=0, le=1),
    db: Session = Depends(get_db), user: User = Depends(require("projects.read")),
):
    """GeoJSON feature collection for the risk map, with optional risk filters."""
    statement = scoped_projects(select(Project, func.ST_AsGeoJSON(Project.geom)), user)
    if risk_category:
        statement = statement.where(Project.risk_category == risk_category)
    if min_delay_probability is not None:
        statement = statement.where(Project.delay_probability >= min_delay_probability)
    try:
        rows = db.execute(statement.order_by(Project.project_id)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not build map data") from error
    features = [{"type": "Feature", "id": project.project_id, "geometry": json.loads(geometry), "properties": ProjectRead.model_validate(project).model_dump(mode="json")} for project, geometry in rows]
    return {"type": "FeatureCollection", "features": features}


@router.get("/projects/filter-options")
def project_filter_options(
    country: str | None = None,
    state: str | None = None,
    district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("projects.read")),
):
    """Return dependent geographic filter values for country, state, and district."""
    try:
        reference = india_state_districts() if not country or country == "India" else {}
        countries = sorted(set(db.scalars(select(Project.country).distinct()).all()) | {"India"})
        state_query = select(Project.state).distinct()
        if country:
            state_query = state_query.where(Project.country == country)
        database_states = db.scalars(state_query.order_by(Project.state)).all()
        states = sorted(set(database_states) | set(reference))
        district_query = select(Project.district).distinct()
        if country:
            district_query = district_query.where(Project.country == country)
        if state:
            district_query = district_query.where(Project.state == state)
        database_districts = db.scalars(district_query.order_by(Project.district)).all()
        districts = sorted(set(database_districts) | set(reference.get(state, [])))
        land_types = db.scalars(select(Project.land_type).distinct().order_by(Project.land_type)).all()
        project_types = db.scalars(select(Project.project_type).distinct().order_by(Project.project_type)).all()
        stages = db.scalars(select(Project.lifecycle_stage).distinct().order_by(Project.lifecycle_stage)).all()
        return {"countries": countries, "states": states, "districts": districts, "land_types": land_types, "project_types": project_types, "lifecycle_stages": stages, "risk_categories": ["Low", "Medium", "High"], "reference_loaded": bool(reference)}
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not load filter options") from error


@router.get("/locations/reverse")
def location_from_coordinates(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    try:
        return reverse_geocode(latitude, longitude)
    except ValueError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(require("projects.write"))):
    if user.role.code == "LAND_ACQUISITION_AUTHORITY":
        raise HTTPException(403, "An authority can only manage an assigned project")
    if user.role.code in {"DISTRICT_ADMINISTRATION", "LAND_ACQUISITION_AUTHORITY"} and payload.district != user.district:
        raise HTTPException(403, "Project outside assigned district")
    values = payload.model_dump()
    # Derived risk fields are always produced by the active model, so a client
    # cannot assert a risk score the model does not support.
    for field in DERIVED_FIELDS:
        values.pop(field, None)
    project = Project(**values)
    prediction = rescore_project(project, active_service())
    db.add(project)
    try:
        db.flush()
        capture_snapshot(db, project, prediction, source="created")
        record(db, user, "PROJECT_CREATED", "project", project.project_id, {
            "state": project.state, "district": project.district,
            "risk_score": prediction["risk_score"], "model_version": prediction["model_version"],
        })
        db.commit()
        db.refresh(project)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Project ID already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not create project") from error
    try:
        sync_projects_to_csv(db)
    except OSError as error:
        raise HTTPException(500, "Project saved, but CSV synchronization failed") from error
    return project


@router.put("/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(require("projects.write"))):
    if payload.project_id != project_id:
        raise HTTPException(422, "Project ID cannot be changed")
    project = project_in_scope(db, project_id, user)
    if user.role.code == "DISTRICT_ADMINISTRATION" and payload.district != user.district:
        raise HTTPException(403, "Project outside assigned district")
    before = {name: getattr(project, name) for name in ProjectCreate.model_fields}
    for field, value in payload.model_dump().items():
        if field in DERIVED_FIELDS:
            continue
        setattr(project, field, value)
    prediction = rescore_project(project, active_service())
    after = {name: getattr(project, name) for name in ProjectCreate.model_fields}
    try:
        capture_snapshot(db, project, prediction, source="updated")
        record(db, user, "PROJECT_UPDATED", "project", project_id, {
            "changes": changed_fields(before, after), "model_version": prediction["model_version"],
        })
        db.commit()
        db.refresh(project)
        sync_projects_to_csv(db)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not update project") from error
    except OSError as error:
        raise HTTPException(500, "Project updated, but CSV synchronization failed") from error
    return project


@router.post("/projects/predict-preview", response_model=ProjectPreview)
def preview_project_prediction(payload: ProjectPreviewCreate, user: User = Depends(require("projects.write"))):
    """Score an unsaved project so an officer sees risk before committing it."""
    service = active_service()
    values = feature_values(payload.model_dump(), service)
    try:
        prediction = service.predict(values)
        explanation = service.explain(values)
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    return {
        **prediction,
        "top_contributing_factors": explanation["top_contributing_factors"],
        "delay_drivers": explanation["delay_drivers"],
        "recommendations": explanation["recommendations"],
    }


@router.post("/projects/bulk-upload", response_model=BulkUploadResult, status_code=status.HTTP_201_CREATED)
async def bulk_upload_projects(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require("projects.write"))):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV must be 10 MB or smaller")
    try:
        reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
        required = PROJECT_COLUMNS - set(DERIVED_FIELDS)
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = sorted(required - set(reader.fieldnames or []))
            raise HTTPException(422, f"CSV is missing required columns: {', '.join(missing)}")
        payloads = [ProjectCreate.model_validate(row) for row in reader]
    except UnicodeDecodeError as error:
        raise HTTPException(422, "CSV must use UTF-8 encoding") from error
    except ValidationError as error:
        raise HTTPException(422, detail=error.errors()) from error
    if not payloads:
        raise HTTPException(422, "CSV has no project rows")
    service = active_service()
    projects = []
    for payload in payloads:
        values = payload.model_dump()
        for field in DERIVED_FIELDS:
            values.pop(field, None)
        project = Project(**values)
        rescore_project(project, service)
        projects.append(project)
    db.add_all(projects)
    try:
        db.flush()
        record(db, user, "PROJECTS_BULK_IMPORTED", "project", f"{len(projects)} rows", {
            "project_ids": [project.project_id for project in projects][:50],
            "model_version": service.version,
        })
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "CSV contains an existing or duplicate project ID") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not import CSV") from error
    try:
        sync_projects_to_csv(db)
    except OSError as error:
        raise HTTPException(500, "Projects saved, but CSV synchronization failed") from error
    return BulkUploadResult(inserted=len(payloads), scored=len(projects))


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require("projects.read"))):
    return project_in_scope(db, project_id, user)


@router.post("/projects/{project_id}/predict", response_model=Prediction)
def predict_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require("projects.read"))):
    project = project_in_scope(db, project_id, user)
    service = active_service()
    try:
        return service.predict(feature_values(project, service))
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/projects/{project_id}/explain", response_model=Explanation)
def explain_project(
    project_id: str,
    stage: str | None = Query(None, description="Explain one lifecycle stage instead of the portfolio model"),
    db: Session = Depends(get_db), user: User = Depends(require("projects.read")),
):
    project = project_in_scope(db, project_id, user)
    service = active_service()
    try:
        return service.explain(feature_values(project, service), stage=stage)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/projects/{project_id}/timeline", response_model=list[SnapshotPoint])
def project_history(
    project_id: str,
    days: int = Query(365, ge=1, le=3650),
    db: Session = Depends(get_db), user: User = Depends(require("projects.read")),
):
    project_in_scope(db, project_id, user)
    return analytics.project_timeline(db, project_id, days)


@router.post("/projects/{project_id}/outcome", response_model=ProjectRead)
def record_outcome(project_id: str, payload: OutcomeCreate, db: Session = Depends(get_db), user: User = Depends(require("projects.outcome"))):
    """Record the realised schedule. This is the label the models retrain on."""
    project = project_in_scope(db, project_id, user)
    project.expected_completion_days = payload.expected_completion_days
    project.actual_completion_days = payload.actual_completion_days
    project.delayed = bool(payload.delayed)
    project.outcome_notes = payload.notes
    project.outcome_recorded_at = datetime.now(timezone.utc)
    record(db, user, "PROJECT_OUTCOME_RECORDED", "project", project_id, {
        "expected_completion_days": payload.expected_completion_days,
        "actual_completion_days": payload.actual_completion_days,
        "delayed": project.delayed,
    })
    try:
        db.commit()
        db.refresh(project)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not record outcome") from error
    return project


@router.get("/stats/summary", response_model=SummaryStats, tags=["stats"])
def summary_stats(db: Session = Depends(get_db), user: User = Depends(require("analytics.read"))):
    """Legacy summary kept for backward compatibility with existing clients."""
    try:
        scoped = scoped_projects(select(Project), user).subquery()
        total = db.scalar(select(func.count()).select_from(scoped)) or 0
        counts = db.execute(select(scoped.c.risk_category, func.count()).group_by(scoped.c.risk_category).order_by(scoped.c.risk_category)).all()
        averages = db.execute(select(scoped.c.state, func.avg(scoped.c.delay_probability)).group_by(scoped.c.state).order_by(scoped.c.state)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not calculate summary") from error
    return {
        "total_projects": total,
        "risk_category_counts": [{"risk_category": category, "count": count} for category, count in counts],
        "average_delay_probability_by_state": [{"state": state, "average_delay_probability": float(average)} for state, average in averages],
    }
