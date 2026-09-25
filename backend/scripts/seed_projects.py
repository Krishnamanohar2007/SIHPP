"""Load generated project CSV into PostgreSQL after `alembic upgrade head`."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Project
from app.schemas import ProjectCreate
from app.services.project_csv import sync_projects_to_csv


CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "projects.csv"


def main() -> None:
    with CSV_PATH.open(encoding="utf-8", newline="") as file:
        payloads = [ProjectCreate.model_validate(row).model_dump() for row in csv.DictReader(file)]
    db = SessionLocal()
    try:
        for payload in payloads:
            db.merge(Project(**payload))
        db.commit()
        # Preserve database-created projects too, so a future fresh database
        # can be reconstructed from this portable dataset.
        sync_projects_to_csv(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Loaded {len(payloads)} projects from {CSV_PATH}")


if __name__ == "__main__":
    main()
