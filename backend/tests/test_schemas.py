"""Request contract behaviour that protects data quality."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import OutcomeCreate, ProjectCreate


BASE = {
    "project_id": "LAP-9001", "project_name": "Test Corridor", "project_type": "Metro Rail",
    "state": "Karnataka", "district": "Mysuru", "land_area": 120.5, "number_of_owners": 44,
    "compensation_status": "In Progress", "compensation_percentage": 40.0, "legal_disputes": 2,
    "land_possession_status": "Partially Possessed", "land_possession_percentage": 55.0,
    "rehabilitation_status": "In Progress", "rehabilitation_percentage": 35.0,
    "latitude": 12.2958, "longitude": 76.6394,
}


def test_risk_fields_are_optional_because_the_server_scores():
    payload = ProjectCreate.model_validate(BASE)
    assert payload.risk_score is None
    assert payload.delay_probability is None
    assert payload.risk_category is None


def test_consistent_risk_fields_round_trip_from_a_csv_export():
    payload = ProjectCreate.model_validate({**BASE, "risk_score": 72.5, "delay_probability": 0.81, "risk_category": "High"})
    assert payload.risk_category == "High"


def test_inconsistent_risk_category_is_rejected():
    with pytest.raises(ValidationError, match="risk_category must be Medium"):
        ProjectCreate.model_validate({**BASE, "risk_score": 45.0, "delay_probability": 0.4, "risk_category": "High"})


def test_percentages_are_bounded():
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate({**BASE, "compensation_percentage": 140})


def test_lifecycle_defaults_keep_older_payloads_valid():
    payload = ProjectCreate.model_validate(BASE)
    assert payload.lifecycle_stage == "Pre-notification"
    assert payload.documentation_completeness == 100
    assert payload.affected_families == 0


def test_outcome_derives_delay_from_the_realised_schedule():
    late = OutcomeCreate.model_validate({"expected_completion_days": 400, "actual_completion_days": 600})
    assert late.delayed is True
    on_time = OutcomeCreate.model_validate({"expected_completion_days": 400, "actual_completion_days": 410})
    assert on_time.delayed is False


def test_outcome_respects_an_explicit_override():
    recorded = OutcomeCreate.model_validate(
        {"expected_completion_days": 400, "actual_completion_days": 600, "delayed": False, "notes": "Scope revised"}
    )
    assert recorded.delayed is False


def test_csv_export_refuses_to_shrink_the_dataset(tmp_path, monkeypatch):
    """A partially populated database must not overwrite a fuller export."""
    from app.services import project_csv

    target = tmp_path / "projects.csv"
    target.write_text("project_id,project_name\nLAP-0001,One\nLAP-0002,Two\nLAP-0003,Three\n", encoding="utf-8")
    monkeypatch.setenv("PROJECTS_CSV_PATH", str(target))
    monkeypatch.delenv("ALLOW_CSV_SHRINK", raising=False)
    assert project_csv.csv_row_count(target) == 3

    class OneProjectSession:
        """Stands in for a database holding a single project."""

        def scalar(self, *_args, **_kwargs):
            return 1

        def scalars(self, *_args, **_kwargs):
            raise AssertionError("export must be refused before reading projects")

    project_csv.sync_projects_to_csv(OneProjectSession())
    assert project_csv.csv_row_count(target) == 3, "the fuller export must survive"
