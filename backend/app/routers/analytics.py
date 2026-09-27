"""Portfolio analytics endpoints backing the decision-support dashboards."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.schemas import (
    ComparativeDimension,
    ComparativeRow,
    DriverPrevalence,
    GeographyLevel,
    GeographyTrend,
    KpiSummary,
    PriorityRow,
    StageExposure,
    TimelineBucket,
    TimelinePoint,
)
from app.services import analytics
from app.services.auth import require, scoped_projects


router = APIRouter(prefix="/analytics", tags=["analytics"])


def scope(db: Session, user: User, state: str | None = None, district: str | None = None, project_type: str | None = None):
    """Role-scoped project statement, narrowed further by optional filters."""
    statement = scoped_projects(select(Project), user)
    for column, value in ((Project.state, state), (Project.district, district), (Project.project_type, project_type)):
        if value:
            statement = statement.where(column == value)
    return statement


@router.get("/kpis", response_model=KpiSummary)
def kpis(
    state: str | None = None, district: str | None = None, project_type: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    try:
        return analytics.kpis(db, scope(db, user, state, district, project_type))
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not calculate indicators") from error


@router.get("/trends", response_model=list[GeographyTrend])
def geography_trends(
    level: GeographyLevel = "state",
    state: str | None = None, project_type: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    """Delay exposure aggregated by state or district."""
    try:
        return analytics.geography_trends(db, scope(db, user, state, None, project_type), level)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not calculate trends") from error


@router.get("/timeline", response_model=list[TimelinePoint])
def timeline(
    days: int = Query(90, ge=1, le=3650), bucket: TimelineBucket = "day",
    state: str | None = None, district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    """Portfolio risk over time, from the recorded snapshot history."""
    try:
        return analytics.timeline(db, scope(db, user, state, district), days, bucket)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not build the timeline") from error


@router.get("/comparative", response_model=list[ComparativeRow])
def comparative(
    dimension: ComparativeDimension = "project_type",
    state: str | None = None, district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    try:
        return analytics.comparative(db, scope(db, user, state, district), dimension)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not build the comparison") from error


@router.get("/drivers", response_model=list[DriverPrevalence])
def drivers(
    state: str | None = None, district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    """How widespread each delay driver is across the scoped portfolio."""
    try:
        return analytics.driver_summary(db, scope(db, user, state, district))
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not summarise drivers") from error


@router.get("/priority", response_model=list[PriorityRow])
def priority(
    limit: int = Query(20, ge=1, le=200),
    state: str | None = None, district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    """Projects ranked for intervention by exposure weighted delay likelihood."""
    try:
        return analytics.priority_queue(db, scope(db, user, state, district), limit)
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not build the priority queue") from error


@router.get("/stage-exposure", response_model=list[StageExposure])
def stage_exposure(
    state: str | None = None, district: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require("analytics.read")),
):
    """Average modelled delay probability per lifecycle stage."""
    try:
        return analytics.stage_exposure(db, scope(db, user, state, district))
    except SQLAlchemyError as error:
        raise HTTPException(500, "Could not summarise stage exposure") from error
