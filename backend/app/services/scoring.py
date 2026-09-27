"""Re-score projects with the active model and keep stored risk fields in sync.

The register stores ``risk_score``, ``delay_probability`` and ``risk_category`` so
that listing, filtering and map queries stay cheap. Those columns are derived
values, so whenever a project changes - or a new model version is activated -
they must be refreshed from the model. This module is the single place that does
that, and it is also where metric snapshots are captured.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, ProjectSnapshot
from app.services.ml_service import MLService, ModelUnavailableError, get_ml_service


# Fields the model reads. Kept as a function so the active model card decides.
def feature_values(project: Project | Mapping[str, Any], service: MLService | None = None) -> dict[str, Any]:
    names = (service or get_ml_service()).features
    if isinstance(project, Mapping):
        return {name: project.get(name) for name in names}
    return {name: getattr(project, name, None) for name in names}


def score(project: Project | Mapping[str, Any], service: MLService | None = None) -> dict[str, Any]:
    """Predict for one project without touching the database."""
    active = service or get_ml_service()
    return active.predict(feature_values(project, active))


def apply_prediction(project: Project, prediction: Mapping[str, Any]) -> bool:
    """Write predicted values onto the project. Returns True when something moved."""
    changed = (
        float(project.risk_score or 0) != float(prediction["risk_score"])
        or float(project.delay_probability or 0) != float(prediction["delay_probability"])
        or project.risk_category != prediction["risk_category"]
    )
    project.risk_score = prediction["risk_score"]
    project.delay_probability = prediction["delay_probability"]
    project.risk_category = prediction["risk_category"]
    return changed


def rescore_project(project: Project, service: MLService | None = None) -> dict[str, Any]:
    """Score one project and store the result on it."""
    prediction = score(project, service)
    apply_prediction(project, prediction)
    return prediction


def capture_snapshot(db: Session, project: Project, prediction: Mapping[str, Any], source: str = "scheduled") -> ProjectSnapshot:
    """Append one point to the project's metric history."""
    snapshot = ProjectSnapshot(
        project_id=project.project_id,
        risk_score=prediction["risk_score"],
        delay_probability=prediction["delay_probability"],
        risk_category=prediction["risk_category"],
        lifecycle_stage=project.lifecycle_stage,
        compensation_percentage=project.compensation_percentage,
        land_possession_percentage=project.land_possession_percentage,
        rehabilitation_percentage=project.rehabilitation_percentage,
        documentation_completeness=project.documentation_completeness,
        stakeholder_responsiveness=project.stakeholder_responsiveness,
        legal_disputes=project.legal_disputes,
        stage_risks=dict(prediction.get("lifecycle_risks", {})),
        source=source,
    )
    db.add(snapshot)
    return snapshot


def rescore_all(db: Session, projects: Iterable[Project] | None = None, snapshot: bool = True, source: str = "scheduled") -> dict[str, int]:
    """Re-score the whole register, optionally snapshotting each project.

    Used after a model is activated and by the scheduled monitoring job.
    """
    try:
        service = get_ml_service()
    except ModelUnavailableError:
        return {"scored": 0, "changed": 0, "snapshots": 0, "skipped": "model unavailable"}
    rows = list(projects if projects is not None else db.scalars(select(Project)).all())
    scored = changed = snapshots = 0
    for project in rows:
        prediction = score(project, service)
        if apply_prediction(project, prediction):
            changed += 1
        scored += 1
        if snapshot:
            capture_snapshot(db, project, prediction, source=source)
            snapshots += 1
    return {"scored": scored, "changed": changed, "snapshots": snapshots}
