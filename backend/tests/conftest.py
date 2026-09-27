"""Shared test fixtures.

Unit tests run with no services. The API tests need a real PostGIS database
because the schema uses PostGIS geometry, JSONB and ``date_trunc``; they are
skipped unless ``TEST_DATABASE_URL`` is set, for example::

    TEST_DATABASE_URL=postgresql+psycopg2://risk_user:risk_password@localhost:5432/risk_monitor_test
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
for path in (str(BACKEND_ROOT), str(REPO_ROOT / "ml")):
    if path not in sys.path:
        sys.path.insert(0, path)

# Settings are read at import time, so the environment must be complete first.
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://unused:unused@localhost:5432/unused"))
os.environ.setdefault("JWT_SECRET", "test-secret-value-at-least-32-characters-long")
os.environ.setdefault("NOTIFICATION_CHANNELS", "console")
# Tests write projects through the API, which exports the register to CSV. Point
# that export at a throwaway file so a test run never touches data/projects.csv.
os.environ["PROJECTS_CSV_PATH"] = str(Path(tempfile.mkdtemp(prefix="la-test-csv-")) / "projects.csv")


HIGH_RISK_PROJECT = {
    "project_type": "Metro Rail", "land_type": "Residential", "lifecycle_stage": "Compensation",
    "land_area": 240.0, "number_of_owners": 420, "affected_families": 380,
    "approval_timeline_days": 410, "documentation_completeness": 55.0,
    "stakeholder_responsiveness": 48.0, "historical_performance_score": 60.0,
    "compensation_percentage": 35.0, "legal_disputes": 6,
    "land_possession_percentage": 40.0, "rehabilitation_percentage": 30.0,
}
LOW_RISK_PROJECT = {
    "project_type": "Solar Park", "land_type": "Barren", "lifecycle_stage": "Rehabilitation",
    "land_area": 60.0, "number_of_owners": 8, "affected_families": 2,
    "approval_timeline_days": 20, "documentation_completeness": 99.0,
    "stakeholder_responsiveness": 97.0, "historical_performance_score": 96.0,
    "compensation_percentage": 98.0, "legal_disputes": 0,
    "land_possession_percentage": 97.0, "rehabilitation_percentage": 96.0,
}


@pytest.fixture(scope="session", autouse=True)
def isolated_model_dir(tmp_path_factory):
    """Copy the active model bundle to a temporary directory for the test session.

    Retraining writes new bundles and moves the active pointer, so tests must not
    run against the repository's own ``ml/models`` directory.
    """
    from shutil import copytree

    source = REPO_ROOT / "ml" / "models"
    pointer = source / "active.json"
    if not pointer.is_file():
        pytest.skip("no active model bundle to copy; run python ml/train_model.py")
    version = json.loads(pointer.read_text(encoding="utf-8"))["version"]
    target = tmp_path_factory.mktemp("models")
    copytree(source / version, target / version)
    (target / "active.json").write_text(
        json.dumps({"version": version, "path": str(target / version)}, indent=2), encoding="utf-8"
    )
    os.environ["ML_MODELS_DIR"] = str(target)
    os.environ.pop("ML_MODEL_DIR", None)
    yield target
    os.environ.pop("ML_MODELS_DIR", None)


@pytest.fixture(scope="session")
def ml_service(isolated_model_dir):
    from app.services.ml_service import MLService, ModelUnavailableError

    try:
        return MLService()
    except ModelUnavailableError as error:
        pytest.skip(f"No trained model bundle: {error}")


@pytest.fixture
def high_risk() -> dict:
    return dict(HIGH_RISK_PROJECT)


@pytest.fixture
def low_risk() -> dict:
    return dict(LOW_RISK_PROJECT)
