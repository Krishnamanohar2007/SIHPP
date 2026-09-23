import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, Project
from app.schemas import AlertRead, BulkUploadResult, ProjectCreate, ProjectPage, ProjectPreview, ProjectPreviewCreate, ProjectRead, SummaryStats
from app.services.ml_service import ModelUnavailableError, get_ml_service
from app.services.notifications.dispatcher import NotificationDispatcher


router = APIRouter(tags=["projects"])
PROJECT_COLUMNS = set(ProjectCreate.model_fields)


def filtered_projects(state: str | None, district: str | None, risk_category: str | None, project_type: str | None):
    statement = select(Project)
    for column, value in ((Project.state, state), (Project.district, district), (Project.risk_category, risk_category), (Project.project_type, project_type)):
        if value:
            statement = statement.where(column == value)
    return statement


@router.get("/projects", response_model=ProjectPage)
def list_projects(
    state: str | None = None,
    district: str | None = None,
    risk_category: str | None = None,
    project_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    statement = filtered_projects(state, district, risk_category, project_type)
    try:
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = db.scalars(statement.order_by(Project.project_id).offset(offset).limit(limit)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read projects") from error
    return ProjectPage(items=items, total=total, offset=offset, limit=limit)


@router.get("/projects/geo")
def projects_geo(db: Session = Depends(get_db)):
    try:
        rows = db.execute(select(Project, func.ST_AsGeoJSON(Project.geom)).order_by(Project.project_id)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not build map data") from error
    features = [{"type": "Feature", "id": project.project_id, "geometry": json.loads(geometry), "properties": ProjectRead.model_validate(project).model_dump(mode="json")} for project, geometry in rows]
    return {"type": "FeatureCollection", "features": features}


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project)
    try:
        db.commit()
        db.refresh(project)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Project ID already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not create project") from error
    return project


@router.post("/projects/predict-preview", response_model=ProjectPreview)
def preview_project_prediction(payload: ProjectPreviewCreate):
    try:
        service = get_ml_service()
        prediction = service.predict(project_features(payload.model_dump()))
        explanation = service.explain(project_features(payload.model_dump()))
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    return {**prediction, "shap_factors": explanation["top_contributing_factors"], "recommendations": explanation["recommendations"]}


@router.post("/projects/bulk-upload", response_model=BulkUploadResult, status_code=status.HTTP_201_CREATED)
async def bulk_upload_projects(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV must be 10 MB or smaller")
    try:
        reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
        if not reader.fieldnames or set(reader.fieldnames) != PROJECT_COLUMNS:
            raise HTTPException(422, "CSV headers must match project schema")
        payloads = [ProjectCreate.model_validate(row) for row in reader]
    except UnicodeDecodeError as error:
        raise HTTPException(422, "CSV must use UTF-8 encoding") from error
    except ValidationError as error:
        raise HTTPException(422, detail=error.errors()) from error
    if not payloads:
        raise HTTPException(422, "CSV has no project rows")
    db.add_all(Project(**payload.model_dump()) for payload in payloads)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "CSV contains an existing or duplicate project ID") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "Could not import CSV") from error
    return BulkUploadResult(inserted=len(payloads))


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: Session = Depends(get_db)):
    try:
        project = db.get(Project, project_id)
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read project") from error
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def project_features(project: Project | dict[str, object]) -> dict[str, object]:
    fields = ("project_type", "land_area", "number_of_owners", "compensation_percentage", "legal_disputes", "land_possession_percentage", "rehabilitation_percentage")
    if isinstance(project, dict):
        return {name: project[name] for name in fields}
    return {name: getattr(project, name) for name in fields}


@router.post("/projects/{project_id}/predict")
def predict_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    try:
        return get_ml_service().predict(project_features(project))
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/projects/{project_id}/explain")
def explain_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    try:
        return get_ml_service().explain(project_features(project))
    except ModelUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/stats/summary", response_model=SummaryStats, tags=["stats"])
def summary_stats(db: Session = Depends(get_db)):
    try:
        total = db.scalar(select(func.count()).select_from(Project)) or 0
        counts = db.execute(select(Project.risk_category, func.count()).group_by(Project.risk_category).order_by(Project.risk_category)).all()
        averages = db.execute(select(Project.state, func.avg(Project.delay_probability)).group_by(Project.state).order_by(Project.state)).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not calculate summary") from error
    return {
        "total_projects": total,
        "risk_category_counts": [{"risk_category": category, "count": count} for category, count in counts],
        "average_delay_probability_by_state": [{"state": state, "average_delay_probability": float(average)} for state, average in averages],
    }
@router.post("/alerts/scan-now", tags=["alerts"])
def scan_now():
    try:
        triggered = NotificationDispatcher().scan_projects()
    except ValueError as error:
        raise HTTPException(500, str(error)) from error
    return {"triggered": triggered}

@router.get("/alerts", response_model=list[AlertRead], tags=["alerts"])
def list_alerts(status: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    statement = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(Alert.status == status)
    try:
        return db.scalars(statement).all()
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not read alerts") from error
