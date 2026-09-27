"""Portfolio analytics: KPIs, geographic trends, timelines and comparatives.

Every function takes the caller's role-scoped project statement, so a district
officer's analytics cover only their district while a policy maker sees the whole
country. Scoping happens in SQL, never after the fact in Python.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.models import Alert, Project, ProjectSnapshot


def _numeric(value: Any, digits: int = 4) -> float:
    return round(float(value or 0), digits)


def kpis(db: Session, scoped: Select) -> dict[str, Any]:
    """Headline performance indicators for the dashboard tiles."""
    subquery = scoped.subquery()
    row = db.execute(select(
        func.count(),
        func.avg(subquery.c.delay_probability),
        func.avg(subquery.c.risk_score),
        func.sum(case((subquery.c.risk_category == "High", 1), else_=0)),
        func.sum(case((subquery.c.risk_category == "Medium", 1), else_=0)),
        func.sum(case((subquery.c.risk_category == "Low", 1), else_=0)),
        func.avg(subquery.c.compensation_percentage),
        func.avg(subquery.c.land_possession_percentage),
        func.avg(subquery.c.rehabilitation_percentage),
        func.avg(subquery.c.documentation_completeness),
        func.avg(subquery.c.stakeholder_responsiveness),
        func.avg(subquery.c.approval_timeline_days),
        func.sum(subquery.c.legal_disputes),
        func.sum(subquery.c.affected_families),
        func.sum(subquery.c.land_area),
    ).select_from(subquery)).one()

    total = int(row[0] or 0)
    # Outcome accuracy: among projects with a recorded outcome, how often the
    # model's stored probability agreed with what actually happened.
    outcome = db.execute(select(
        func.count(),
        func.sum(case((and_(subquery.c.delayed.is_(True), subquery.c.delay_probability >= 0.5), 1),
                      (and_(subquery.c.delayed.is_(False), subquery.c.delay_probability < 0.5), 1), else_=0)),
        func.sum(case((subquery.c.delayed.is_(True), 1), else_=0)),
        func.avg(subquery.c.actual_completion_days),
        func.avg(subquery.c.expected_completion_days),
    ).select_from(subquery).where(subquery.c.delayed.isnot(None))).one()
    labelled = int(outcome[0] or 0)

    open_alerts = db.scalar(
        select(func.count()).select_from(Alert).where(Alert.project_id.in_(select(subquery.c.project_id)), Alert.status == "open")
    ) or 0
    return {
        "total_projects": total,
        "high_risk_projects": int(row[3] or 0),
        "medium_risk_projects": int(row[4] or 0),
        "low_risk_projects": int(row[5] or 0),
        "high_risk_share": _numeric((int(row[3] or 0) / total) if total else 0),
        "average_delay_probability": _numeric(row[1]),
        "average_risk_score": _numeric(row[2], 2),
        "average_compensation_percentage": _numeric(row[6], 2),
        "average_possession_percentage": _numeric(row[7], 2),
        "average_rehabilitation_percentage": _numeric(row[8], 2),
        "average_documentation_completeness": _numeric(row[9], 2),
        "average_stakeholder_responsiveness": _numeric(row[10], 2),
        "average_approval_timeline_days": _numeric(row[11], 1),
        "total_legal_disputes": int(row[12] or 0),
        "total_affected_families": int(row[13] or 0),
        "total_land_area": _numeric(row[14], 2),
        "open_alerts": int(open_alerts),
        "projects_with_outcome": labelled,
        "outcome_agreement": _numeric((int(outcome[1] or 0) / labelled) if labelled else 0),
        "observed_delay_rate": _numeric((int(outcome[2] or 0) / labelled) if labelled else 0),
        "average_actual_completion_days": _numeric(outcome[3], 1),
        "average_expected_completion_days": _numeric(outcome[4], 1),
    }


def geography_trends(db: Session, scoped: Select, level: str = "state") -> list[dict[str, Any]]:
    """Aggregate delay exposure by state or by district."""
    subquery = scoped.subquery()
    if level not in {"state", "district"}:
        raise ValueError("level must be 'state' or 'district'")
    key = subquery.c.district if level == "district" else subquery.c.state
    grouping = [subquery.c.state, subquery.c.district] if level == "district" else [subquery.c.state]
    rows = db.execute(
        select(
            *grouping,
            func.count(),
            func.avg(subquery.c.delay_probability),
            func.avg(subquery.c.risk_score),
            func.sum(case((subquery.c.risk_category == "High", 1), else_=0)),
            func.avg(subquery.c.compensation_percentage),
            func.sum(subquery.c.legal_disputes),
            func.sum(subquery.c.affected_families),
        ).select_from(subquery).group_by(*grouping).order_by(func.avg(subquery.c.delay_probability).desc())
    ).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        offset = 2 if level == "district" else 1
        entry = {
            "state": row[0],
            "district": row[1] if level == "district" else None,
            "projects": int(row[offset] or 0),
            "average_delay_probability": _numeric(row[offset + 1]),
            "average_risk_score": _numeric(row[offset + 2], 2),
            "high_risk_projects": int(row[offset + 3] or 0),
            "average_compensation_percentage": _numeric(row[offset + 4], 2),
            "legal_disputes": int(row[offset + 5] or 0),
            "affected_families": int(row[offset + 6] or 0),
        }
        entry["high_risk_share"] = _numeric((entry["high_risk_projects"] / entry["projects"]) if entry["projects"] else 0)
        result.append(entry)
    return result


def timeline(db: Session, scoped: Select, days: int = 90, bucket: str = "day") -> list[dict[str, Any]]:
    """Portfolio risk over time, built from the snapshot history."""
    if bucket not in {"day", "week", "month"}:
        raise ValueError("bucket must be 'day', 'week' or 'month'")
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    project_ids = select(scoped.subquery().c.project_id)
    period = func.date_trunc(bucket, ProjectSnapshot.captured_at)
    rows = db.execute(
        select(
            period.label("period"),
            func.count(),
            func.avg(ProjectSnapshot.delay_probability),
            func.avg(ProjectSnapshot.risk_score),
            func.sum(case((ProjectSnapshot.risk_category == "High", 1), else_=0)),
            func.avg(ProjectSnapshot.compensation_percentage),
            func.avg(ProjectSnapshot.land_possession_percentage),
            func.avg(ProjectSnapshot.rehabilitation_percentage),
        )
        .where(ProjectSnapshot.project_id.in_(project_ids), ProjectSnapshot.captured_at >= since)
        .group_by(period).order_by(period)
    ).all()
    return [{
        "period": row[0].isoformat() if row[0] else None,
        "snapshots": int(row[1] or 0),
        "average_delay_probability": _numeric(row[2]),
        "average_risk_score": _numeric(row[3], 2),
        "high_risk_projects": int(row[4] or 0),
        "average_compensation_percentage": _numeric(row[5], 2),
        "average_possession_percentage": _numeric(row[6], 2),
        "average_rehabilitation_percentage": _numeric(row[7], 2),
    } for row in rows]


def project_timeline(db: Session, project_id: str, days: int = 365) -> list[dict[str, Any]]:
    """One project's recorded metric history, for its detail chart."""
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = db.scalars(
        select(ProjectSnapshot)
        .where(ProjectSnapshot.project_id == project_id, ProjectSnapshot.captured_at >= since)
        .order_by(ProjectSnapshot.captured_at)
    ).all()
    return [{
        "captured_at": row.captured_at.isoformat(),
        "risk_score": _numeric(row.risk_score, 2),
        "delay_probability": _numeric(row.delay_probability),
        "risk_category": row.risk_category,
        "lifecycle_stage": row.lifecycle_stage,
        "compensation_percentage": _numeric(row.compensation_percentage, 2),
        "land_possession_percentage": _numeric(row.land_possession_percentage, 2),
        "rehabilitation_percentage": _numeric(row.rehabilitation_percentage, 2),
        "stage_risks": row.stage_risks,
        "source": row.source,
    } for row in rows]


def comparative(db: Session, scoped: Select, dimension: str = "project_type") -> list[dict[str, Any]]:
    """Compare delay exposure across a categorical dimension."""
    columns = {
        "project_type": "project_type", "land_type": "land_type", "lifecycle_stage": "lifecycle_stage",
        "risk_category": "risk_category", "state": "state", "compensation_status": "compensation_status",
        "land_possession_status": "land_possession_status", "rehabilitation_status": "rehabilitation_status",
    }
    if dimension not in columns:
        raise ValueError(f"dimension must be one of {', '.join(sorted(columns))}")
    subquery = scoped.subquery()
    key = subquery.c[columns[dimension]]
    rows = db.execute(
        select(
            key, func.count(), func.avg(subquery.c.delay_probability), func.avg(subquery.c.risk_score),
            func.sum(case((subquery.c.risk_category == "High", 1), else_=0)),
            func.avg(subquery.c.land_area), func.sum(subquery.c.affected_families),
        ).select_from(subquery).group_by(key).order_by(func.avg(subquery.c.delay_probability).desc())
    ).all()
    return [{
        "dimension": dimension,
        "value": row[0],
        "projects": int(row[1] or 0),
        "average_delay_probability": _numeric(row[2]),
        "average_risk_score": _numeric(row[3], 2),
        "high_risk_projects": int(row[4] or 0),
        "average_land_area": _numeric(row[5], 2),
        "affected_families": int(row[6] or 0),
    } for row in rows]


def driver_summary(db: Session, scoped: Select) -> list[dict[str, Any]]:
    """Portfolio-level count of projects breaching each delay-driver threshold.

    This is a deterministic prevalence view. It answers "how widespread is each
    bottleneck", which complements the per-project SHAP attribution.
    """
    subquery = scoped.subquery()
    total = db.scalar(select(func.count()).select_from(subquery)) or 0
    checks = [
        ("Pending approvals", subquery.c.approval_timeline_days > 180, "Approval pending beyond 180 days"),
        ("Compensation delays", subquery.c.compensation_percentage < 60, "Compensation disbursement below 60%"),
        ("Legal disputes", subquery.c.legal_disputes >= 3, "Three or more pending disputes"),
        ("Incomplete documentation", subquery.c.documentation_completeness < 80, "Documentation below 80% complete"),
        ("Rehabilitation status", subquery.c.rehabilitation_percentage < 60, "Rehabilitation below 60% complete"),
        ("Possession bottlenecks", subquery.c.land_possession_percentage < 60, "Possession below 60%"),
        ("Administrative bottlenecks", subquery.c.stakeholder_responsiveness < 60, "Stakeholder responsiveness below 60%"),
    ]
    summary: list[dict[str, Any]] = []
    for driver, condition, description in checks:
        row = db.execute(
            select(func.count(), func.avg(subquery.c.delay_probability)).select_from(subquery).where(condition)
        ).one()
        affected = int(row[0] or 0)
        summary.append({
            "driver": driver,
            "criterion": description,
            "affected_projects": affected,
            "share": _numeric((affected / total) if total else 0),
            "average_delay_probability": _numeric(row[1]),
        })
    summary.sort(key=lambda item: item["affected_projects"], reverse=True)
    return summary


def priority_queue(db: Session, scoped: Select, limit: int = 20) -> list[dict[str, Any]]:
    """Projects ranked for intervention: exposure times delay likelihood."""
    subquery = scoped.subquery()
    # Exposure proxy: land value at stake, scaled to crore, times delay likelihood.
    exposure = (subquery.c.land_area * subquery.c.land_price_per_acre / 10_000_000)
    priority = (subquery.c.delay_probability * (exposure + subquery.c.affected_families / 100.0))
    rows = db.execute(
        select(
            subquery.c.project_id, subquery.c.project_name, subquery.c.project_type, subquery.c.state,
            subquery.c.district, subquery.c.lifecycle_stage, subquery.c.risk_score, subquery.c.risk_category,
            subquery.c.delay_probability, subquery.c.affected_families, subquery.c.legal_disputes,
            exposure.label("exposure_crore"), priority.label("priority_index"),
        ).select_from(subquery).order_by(priority.desc()).limit(max(1, min(limit, 200)))
    ).all()
    return [{
        "project_id": row.project_id,
        "project_name": row.project_name,
        "project_type": row.project_type,
        "state": row.state,
        "district": row.district,
        "lifecycle_stage": row.lifecycle_stage,
        "risk_score": _numeric(row.risk_score, 2),
        "risk_category": row.risk_category,
        "delay_probability": _numeric(row.delay_probability),
        "affected_families": int(row.affected_families or 0),
        "legal_disputes": int(row.legal_disputes or 0),
        "exposure_crore": _numeric(row.exposure_crore, 2),
        "priority_index": _numeric(row.priority_index, 3),
        "rank": index + 1,
    } for index, row in enumerate(rows)]


def stage_exposure(db: Session, scoped: Select) -> list[dict[str, Any]]:
    """Average modelled probability per lifecycle stage, from the latest snapshots.

    Snapshots store the per-stage probabilities produced at capture time, so this
    reads history rather than re-running the model over the whole portfolio.
    """
    project_ids = select(scoped.subquery().c.project_id)
    latest = (
        select(ProjectSnapshot.project_id, func.max(ProjectSnapshot.captured_at).label("captured_at"))
        .where(ProjectSnapshot.project_id.in_(project_ids))
        .group_by(ProjectSnapshot.project_id).subquery()
    )
    rows = db.scalars(
        select(ProjectSnapshot).join(
            latest,
            and_(ProjectSnapshot.project_id == latest.c.project_id, ProjectSnapshot.captured_at == latest.c.captured_at),
        )
    ).all()
    totals: dict[str, list[float]] = {}
    for snapshot in rows:
        for stage, probability in (snapshot.stage_risks or {}).items():
            totals.setdefault(stage, []).append(float(probability))
    return [{
        "stage": stage,
        "projects": len(values),
        "average_delay_probability": _numeric(sum(values) / len(values)) if values else 0.0,
        "high_risk_projects": sum(1 for value in values if value >= 0.6),
    } for stage, values in totals.items()]
