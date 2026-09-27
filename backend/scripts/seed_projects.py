"""Load generated project CSV into PostgreSQL after `alembic upgrade head`."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Project
from app.schemas import ProjectCreate


CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "projects.csv"
DERIVED_FIELDS = ("risk_score", "delay_probability", "risk_category")


def main() -> None:
    """Load the portable dataset into the database.

    Seeding never writes back to the CSV. The file is the input here, and
    exporting the database over it would let a stale database overwrite freshly
    generated data. The API still syncs the CSV when a project is written through
    it, which is the case where the database is the newer copy.
    """
    with CSV_PATH.open(encoding="utf-8", newline="") as file:
        payloads = [ProjectCreate.model_validate(row).model_dump() for row in csv.DictReader(file)]
    db = SessionLocal()
    try:
        for payload in payloads:
            # Risk fields are derived. They are seeded as supplied so the register
            # is queryable immediately, then refreshed by the first risk scan.
            db.merge(Project(**{name: value for name, value in payload.items() if value is not None or name not in DERIVED_FIELDS}))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Loaded {len(payloads)} projects from {CSV_PATH}")


if __name__ == "__main__":
    main()
