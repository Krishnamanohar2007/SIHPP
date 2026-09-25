"""Synchronize database-backed projects to the portable CSV dataset."""
from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.schemas import ProjectCreate


PROJECT_COLUMNS = tuple(ProjectCreate.model_fields)


def projects_csv_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "data" / "projects.csv"
    return Path(os.getenv("PROJECTS_CSV_PATH", default))


def sync_projects_to_csv(db: Session) -> None:
    """Atomically export all saved projects, including newly created records."""
    path = projects_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    projects = db.scalars(select(Project).order_by(Project.project_id)).all()
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=PROJECT_COLUMNS)
        writer.writeheader()
        for project in projects:
            writer.writerow({column: getattr(project, column) for column in PROJECT_COLUMNS})
    try:
        temporary.replace(path)
    except OSError:
        # Windows Docker file bind mounts do not permit an atomic rename over
        # the mounted target. Copying preserves the same exported contents.
        shutil.copyfile(temporary, path)
        temporary.unlink(missing_ok=True)
