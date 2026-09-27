"""Synchronize database-backed projects to the portable CSV dataset."""
from __future__ import annotations

import csv
import logging
import os
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Project
from app.schemas import ProjectCreate


logger = logging.getLogger(__name__)
PROJECT_COLUMNS = tuple(ProjectCreate.model_fields)


def projects_csv_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "data" / "projects.csv"
    return Path(os.getenv("PROJECTS_CSV_PATH", default))


def csv_row_count(path: Path) -> int:
    """Number of data rows currently in the export, excluding the header."""
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8", newline="") as file:
        return max(sum(1 for _ in file) - 1, 0)


def sync_projects_to_csv(db: Session) -> None:
    """Export all saved projects to the portable CSV.

    The export is refused when it would shrink the file, because the database is
    then not the newer copy: a partially seeded or test database would otherwise
    silently destroy the dataset the file holds. Set ``ALLOW_CSV_SHRINK=true`` for
    the deliberate case, such as exporting after projects were removed on purpose.
    """
    path = projects_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    existing = csv_row_count(path)
    if total < existing and os.getenv("ALLOW_CSV_SHRINK", "false").lower() != "true":
        logger.warning(
            "skipped CSV export: database has %s projects, %s already exports %s. "
            "Set ALLOW_CSV_SHRINK=true to export anyway.", total, path, existing,
        )
        return
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
