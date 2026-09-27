"""Continuous learning: retrain from recorded outcomes and register model versions.

Training data is assembled from two sources:

1. the seed history shipped with the repository (``data/training_history.csv``),
2. every project in the database that has a recorded outcome, which is the label
   officials enter through ``POST /projects/{id}/outcome``.

Database labels win on conflict, so a real recorded outcome always replaces the
synthetic row for the same project. A run produces a new versioned bundle, stores
its metrics in ``model_versions``, and only switches serving over when the new
bundle's portfolio ROC AUC is at least as good as the active one.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelVersion, Project, User
from app.services.audit import record
from app.services.ml_service import ModelUnavailableError, get_ml_service, models_root, reload_ml_service


def ml_package_dir() -> Path:
    """Directory holding the training scripts (``/ml`` in the container image)."""
    default = Path(__file__).resolve().parents[3] / "ml"
    return Path(os.getenv("ML_PACKAGE_DIR", default))


def history_csv_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "data" / "training_history.csv"
    return Path(os.getenv("TRAINING_HISTORY_PATH", default))


def _import_trainer():
    """Import ``ml/train_model.py`` without turning ``ml`` into a package."""
    directory = str(ml_package_dir())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    try:
        import train_model  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - depends on deployment layout
        raise ModelUnavailableError(f"Training code not found in {directory}") from error
    return train_model


def labelled_rows(db: Session) -> pd.DataFrame:
    """Projects with a recorded outcome, shaped like the training history."""
    projects = db.scalars(select(Project).where(Project.delayed.isnot(None))).all()
    if not projects:
        return pd.DataFrame()
    try:
        service = get_ml_service()
        features = service.features
        stages = service.stages
    except ModelUnavailableError:
        features, stages = [], []
    rows: list[dict[str, Any]] = []
    for project in projects:
        row: dict[str, Any] = {name: getattr(project, name, None) for name in features}
        row.update({
            "project_id": project.project_id,
            "risk_score": float(project.risk_score),
            "delay_probability": float(project.delay_probability),
            "delayed": int(bool(project.delayed)),
            "expected_completion_days": project.expected_completion_days,
            "actual_completion_days": project.actual_completion_days,
        })
        # A recorded portfolio outcome is the only label an official supplies. Stage
        # labels stay unknown and are left absent so training ignores this row for
        # the per-stage models rather than inventing a label.
        for stage in stages:
            row[f"delayed_{stage.lower().replace(' ', '_')}"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def training_frame(db: Session) -> tuple[pd.DataFrame, str, int]:
    """Merge the seed history with database-recorded outcomes."""
    frames: list[pd.DataFrame] = []
    sources: list[str] = []
    path = history_csv_path()
    if path.is_file():
        seed = pd.read_csv(path)
        frames.append(seed)
        sources.append(f"seed:{path.name}({len(seed)})")
    database = labelled_rows(db)
    if not database.empty:
        sources.append(f"database:recorded_outcomes({len(database)})")
    if not frames and database.empty:
        raise ModelUnavailableError("No training data: seed history is missing and no outcomes are recorded")

    if frames and not database.empty:
        seed = frames[0]
        # Database rows override seed rows for the same project, then any extra
        # stage labels from the seed row are preserved where the database is blank.
        merged = seed.set_index("project_id")
        updates = database.set_index("project_id")
        shared = merged.index.intersection(updates.index)
        for column in updates.columns:
            if column not in merged.columns:
                merged[column] = None
            replacement = updates.loc[shared, column]
            merged.loc[shared, column] = merged.loc[shared, column].where(replacement.isna(), replacement)
        extra = updates.loc[updates.index.difference(merged.index)]
        frame = pd.concat([merged, extra]).reset_index()
    elif frames:
        frame = frames[0]
    else:
        frame = database

    return frame, " + ".join(sources), len(frame)


def register_version(db: Session, card: dict[str, Any], actor: User | None, activate: bool, notes: str | None = None) -> ModelVersion:
    """Insert one model_versions row, optionally making it the served version."""
    version = ModelVersion(
        version=card["version"],
        algorithm=card.get("algorithm", "unknown"),
        training_source=card.get("training_source", "unknown")[:255],
        training_rows=int(card.get("training_rows", 0)),
        artifact_path=str(models_root() / card["version"]),
        feature_names=list(card.get("features", [])),
        metrics=card.get("metrics", {}),
        is_active=activate,
        notes=notes,
        created_by=actor.id if actor is not None else None,
    )
    if activate:
        for existing in db.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))).all():
            existing.is_active = False
    db.add(version)
    return version


def _auc(metrics: dict[str, Any]) -> float | None:
    value = ((metrics or {}).get("portfolio") or {}).get("roc_auc")
    return None if value is None else float(value)


def set_active_pointer(version: str) -> None:
    """Point the model loader at a specific bundle and reload serving."""
    directory = models_root() / version
    if not (directory / "model_card.json").is_file():
        raise ModelUnavailableError(f"Model bundle {version} is not on disk")
    (models_root() / "active.json").write_text(
        json.dumps({"version": version, "path": str(directory)}, indent=2), encoding="utf-8"
    )
    reload_ml_service()


def retrain(db: Session, actor: User | None = None, force_activate: bool = False, notes: str | None = None) -> dict[str, Any]:
    """Train a new bundle, register it, and activate it when it is not worse."""
    trainer = _import_trainer()
    frame, source, rows = training_frame(db)
    version = datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    try:
        card = trainer.train_bundle(frame, version, source, mirror=False)
    except trainer.InsufficientLabelsError as error:
        raise ModelUnavailableError(f"Not enough labelled data to retrain: {error}") from error

    active = db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    new_auc = _auc(card.get("metrics", {}))
    current_auc = _auc(active.metrics if active else {})
    improved = force_activate or current_auc is None or new_auc is None or new_auc >= current_auc
    register_version(db, card, actor, activate=improved, notes=notes)
    record(db, actor, "MODEL_RETRAINED", "model_version", version, {
        "rows": rows, "source": source, "roc_auc": new_auc,
        "previous_roc_auc": current_auc, "activated": improved,
    })

    if improved:
        set_active_pointer(version)
    return {
        "version": version,
        "activated": improved,
        "training_rows": rows,
        "training_source": source,
        "roc_auc": new_auc,
        "previous_roc_auc": current_auc,
        "metrics": card.get("metrics", {}),
    }
