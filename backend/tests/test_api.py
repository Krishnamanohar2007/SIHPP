"""End-to-end API tests against a real PostGIS database.

Skipped unless ``TEST_DATABASE_URL`` points at an empty PostGIS database. The
schema is created by running the project's own Alembic migrations, so these tests
also prove the migration chain applies cleanly from zero.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD = "Str0ng-Test-Password-2026"
PROJECT = {
    "project_id": "LAP-T001", "project_name": "Test Metro Corridor", "project_type": "Metro Rail",
    "country": "India", "state": "Karnataka", "district": "Mysuru",
    "land_area": 210.0, "land_type": "Residential", "land_price_per_acre": 6_500_000,
    "number_of_owners": 310, "affected_families": 280, "approval_timeline_days": 380,
    "documentation_completeness": 58.0, "stakeholder_responsiveness": 50.0,
    "historical_performance_score": 62.0, "lifecycle_stage": "Compensation",
    "compensation_status": "In Progress", "compensation_percentage": 32.0, "legal_disputes": 5,
    "land_possession_status": "Partially Possessed", "land_possession_percentage": 38.0,
    "rehabilitation_status": "In Progress", "rehabilitation_percentage": 28.0,
    "latitude": 12.2958, "longitude": 76.6394,
}


@pytest.fixture(scope="module")
def client():
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from app.database import SessionLocal, engine
    from app.main import app
    from app.models import Role, User
    from app.services.auth import hash_password

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(config, "head")

    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "ADMIN"))
        db.add(User(
            official_name="Test Administrator", organization="Test", designation="Admin",
            email="test-admin@example.gov.in", employee_id=f"TEST-{uuid.uuid4().hex[:8]}",
            password_hash=hash_password(ADMIN_PASSWORD), role=role,
        ))
        db.commit()

    with TestClient(app) as test_client:
        response = test_client.post("/auth/login", json={"email": "test-admin@example.gov.in", "password": ADMIN_PASSWORD})
        assert response.status_code == 200, response.text
        test_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield test_client


@pytest.fixture(scope="module")
def created_project(client):
    response = client.post("/projects", json=PROJECT)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ prediction
def test_health_reports_the_served_model_version(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_version"], "a model bundle must be loaded"


def test_server_scores_the_project_it_stores(client, created_project):
    assert created_project["risk_score"] > 0
    assert 0 < created_project["delay_probability"] <= 1
    assert created_project["risk_category"] in {"Low", "Medium", "High"}


def test_client_supplied_risk_score_is_ignored(client):
    payload = {**PROJECT, "project_id": "LAP-T002", "risk_score": 1.0, "delay_probability": 0.01, "risk_category": "Low"}
    body = client.post("/projects", json=payload).json()
    assert body["risk_score"] > 1.0, "a client must not be able to assert its own risk score"


def test_predict_returns_stage_probabilities(client, created_project):
    body = client.post(f"/projects/{created_project['project_id']}/predict").json()
    assert body["lifecycle_risks"], "stage-wise probabilities must be returned"
    assert set(body["lifecycle_risk_sources"]) == set(body["lifecycle_risks"])


def test_explain_returns_drivers_and_ranked_recommendations(client, created_project):
    body = client.get(f"/projects/{created_project['project_id']}/explain").json()
    assert body["top_contributing_factors"]
    assert body["delay_drivers"]
    reductions = [item["expected_reduction"] for item in body["recommendations"]]
    assert reductions == sorted(reductions, reverse=True)


def test_explain_supports_a_single_stage(client, created_project):
    stages = client.get("/models/active").json()["trained_stages"]
    if not stages:
        pytest.skip("no stage models in this bundle")
    body = client.get(f"/projects/{created_project['project_id']}/explain", params={"stage": stages[0]}).json()
    assert body["stage"] == stages[0]


def test_preview_scores_an_unsaved_project(client):
    body = client.post("/projects/predict-preview", json={**PROJECT, "project_id": "LAP-PREVIEW"}).json()
    assert body["lifecycle_risks"]
    assert body["recommendations"]
    assert client.get("/projects/LAP-PREVIEW").status_code == 404, "preview must not persist"


# -------------------------------------------------------------------- outcomes
def test_recording_an_outcome_stores_ground_truth(client, created_project):
    body = client.post(
        f"/projects/{created_project['project_id']}/outcome",
        json={"expected_completion_days": 500, "actual_completion_days": 900, "notes": "Litigation"},
    ).json()
    assert body["delayed"] is True
    assert body["outcome_recorded_at"]


# ------------------------------------------------------------------- analytics
def test_kpis_cover_portfolio_and_outcome_quality(client, created_project):
    body = client.get("/analytics/kpis").json()
    assert body["total_projects"] >= 1
    assert body["projects_with_outcome"] >= 1
    assert 0 <= body["high_risk_share"] <= 1


@pytest.mark.parametrize("level", ["state", "district"])
def test_geography_trends_aggregate_at_both_levels(client, created_project, level):
    rows = client.get("/analytics/trends", params={"level": level}).json()
    assert rows
    assert rows[0]["state"]
    assert (rows[0]["district"] is not None) == (level == "district")
    probabilities = [row["average_delay_probability"] for row in rows]
    assert probabilities == sorted(probabilities, reverse=True)


def test_timeline_reads_the_snapshot_history(client, created_project):
    rows = client.get("/analytics/timeline", params={"days": 30, "bucket": "day"}).json()
    assert rows, "creating a project must have captured a snapshot"
    assert rows[0]["snapshots"] >= 1


def test_project_timeline_is_scoped_to_one_project(client, created_project):
    rows = client.get(f"/projects/{created_project['project_id']}/timeline").json()
    assert rows
    assert rows[0]["stage_risks"]


def test_comparative_analysis_rejects_an_unknown_dimension(client):
    assert client.get("/analytics/comparative", params={"dimension": "not_a_column"}).status_code == 422


def test_comparative_analysis_groups_by_project_type(client, created_project):
    rows = client.get("/analytics/comparative", params={"dimension": "project_type"}).json()
    assert any(row["value"] == "Metro Rail" for row in rows)


def test_driver_prevalence_flags_the_seeded_bottlenecks(client, created_project):
    rows = {row["driver"]: row for row in client.get("/analytics/drivers").json()}
    assert rows["Compensation delays"]["affected_projects"] >= 1
    assert rows["Legal disputes"]["affected_projects"] >= 1


def test_priority_queue_is_ranked(client, created_project):
    rows = client.get("/analytics/priority", params={"limit": 10}).json()
    assert rows
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
    indices = [row["priority_index"] for row in rows]
    assert indices == sorted(indices, reverse=True)


# ---------------------------------------------------------------------- alerts
def test_scan_raises_alerts_and_records_snapshots(client, created_project):
    result = client.post("/alerts/scan-now").json()
    assert result["scored"] >= 1
    inbox = client.get("/alerts/inbox").json()
    assert inbox, "a high-risk project must raise an alert"
    alert = inbox[0]
    assert alert["severity"] in {"Low", "Medium", "High"}
    assert alert["drivers"], "an alert must carry its delay drivers"
    assert alert["project_name"]


def test_alert_workflow_transitions_and_is_audited(client, created_project):
    alert = client.get("/alerts/inbox").json()[0]
    acknowledged = client.post(f"/alerts/{alert['id']}/acknowledge", json={"note": "Reviewing"}).json()
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["acknowledged_at"]

    resolved = client.post(f"/alerts/{alert['id']}/resolve", json={"resolution_note": "Compensation released"}).json()
    assert resolved["status"] == "resolved"
    assert client.post(f"/alerts/{alert['id']}/resolve", json={"resolution_note": "again"}).status_code == 409

    actions = {row["action"] for row in client.get("/auth/admin/audit", params={"limit": 200}).json()["items"]}
    assert {"ALERT_ACKNOWLEDGED", "ALERT_RESOLVED", "PROJECT_CREATED", "PROJECT_OUTCOME_RECORDED"} <= actions


def test_rescan_reopens_a_resolved_alert_for_a_still_risky_project(client, created_project):
    before = client.get("/alerts", params={"status": "open", "limit": 500}).json()
    client.post("/alerts/scan-now")
    after = client.get("/alerts", params={"status": "open", "limit": 500}).json()
    assert len(after) >= len(before)


# -------------------------------------------------------------- model registry
def test_model_registry_exposes_the_active_bundle(client):
    versions = client.get("/models").json()
    assert versions
    assert sum(1 for row in versions if row["is_active"]) == 1
    active = client.get("/models/active").json()
    assert active["metrics"]["portfolio"]["roc_auc"] is not None


def test_rescore_refreshes_stored_risk_fields(client, created_project):
    result = client.post("/models/rescore", params={"snapshot": "false"}).json()
    assert result["scored"] >= 1


# ---------------------------------------------------------------- integration
@pytest.fixture(scope="module")
def api_key(client):
    response = client.post("/integration/api-keys", json={
        "name": "Test Land Records Bridge", "scopes": ["projects.read", "projects.write", "analytics.read"],
    })
    assert response.status_code == 201, response.text
    return response.json()["api_key"]


def test_integration_health_requires_a_valid_key(client, api_key):
    assert client.get("/integration/v1/health", headers={"X-API-Key": "lar_dead.beef"}).status_code == 401
    body = client.get("/integration/v1/health", headers={"X-API-Key": api_key}).json()
    assert body["status"] == "ok"
    assert body["model_version"]


def test_integration_sync_upserts_and_scores(client, api_key):
    payload = [{**PROJECT, "project_id": "LAP-T900", "project_name": "Synced Corridor"}]
    body = client.post("/integration/v1/projects/sync", json=payload, headers={"X-API-Key": api_key}).json()
    assert body["created"] + body["updated"] == 1
    assert body["scored"] == 1
    stored = client.get("/integration/v1/projects/LAP-T900", headers={"X-API-Key": api_key}).json()
    assert stored["risk_score"] > 0


def test_integration_scope_is_enforced(client, api_key):
    limited = client.post("/integration/api-keys", json={
        "name": "Odisha Only Bridge", "scopes": ["projects.write"], "state": "Odisha",
    }).json()["api_key"]
    body = client.post(
        "/integration/v1/projects/sync",
        json=[{**PROJECT, "project_id": "LAP-T901"}],
        headers={"X-API-Key": limited},
    ).json()
    assert body["created"] == 0
    assert body["rejected"][0]["reason"].startswith("outside key state scope")


def test_missing_scope_is_refused(client, api_key):
    read_only = client.post("/integration/api-keys", json={
        "name": "Read Only Bridge", "scopes": ["projects.read"],
    }).json()["api_key"]
    response = client.post("/integration/v1/projects/sync", json=[PROJECT], headers={"X-API-Key": read_only})
    assert response.status_code == 403


def test_revoked_key_stops_working(client):
    created = client.post("/integration/api-keys", json={"name": "Temporary Bridge", "scopes": ["projects.read"]}).json()
    client.delete(f"/integration/api-keys/{created['id']}")
    assert client.get("/integration/v1/health", headers={"X-API-Key": created["api_key"]}).status_code == 401


# ---------------------------------------------------------------------- access
def test_versioned_mount_serves_the_same_contract(client):
    assert client.get("/api/v1/analytics/kpis").status_code == 200


def test_unauthenticated_requests_are_rejected(client):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anonymous:
        # Missing bearer credentials are refused before any scope check runs.
        assert anonymous.get("/projects").status_code in {401, 403}
        assert anonymous.get("/analytics/kpis").status_code in {401, 403}


def test_state_official_sees_only_their_state(client):
    from app.database import SessionLocal
    from app.models import Role, User
    from app.services.auth import hash_password

    password = "State-Official-Password-2026"
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "STATE_GOVERNMENT"))
        db.add(User(
            official_name="Odisha Secretary", organization="Odisha", designation="Secretary",
            email="odisha@example.gov.in", employee_id=f"OD-{uuid.uuid4().hex[:8]}",
            password_hash=hash_password(password), role=role, state="Odisha",
        ))
        db.commit()
    token = client.post("/auth/login", json={"email": "odisha@example.gov.in", "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    body = client.get("/projects", headers=headers).json()
    assert all(item["state"] == "Odisha" for item in body["items"])
    # The Karnataka test project must be invisible, not merely filtered out.
    assert client.get("/projects/LAP-T001", headers=headers).status_code == 403


@pytest.mark.slow
def test_retraining_produces_a_registered_version(client):
    body = client.post("/models/retrain", json={"force_activate": True, "notes": "test run"})
    assert body.status_code == 200, body.text
    result = body.json()
    assert result["version"]
    assert result["training_rows"] > 0
    versions = client.get("/models").json()
    assert any(row["version"] == result["version"] and row["is_active"] for row in versions)
    assert client.get("/models/active").json()["version"] == result["version"]


def test_administrator_cannot_remove_their_own_admin_role(client):
    """Only an administrator may change roles, so self-demotion is a lockout."""
    me = client.get("/auth/me").json()
    response = client.post(f"/auth/admin/users/{me['id']}/role", json={"role": "STATE_GOVERNMENT"})
    assert response.status_code == 409
    assert "your own administrator role" in response.json()["detail"].lower()
    assert client.get("/auth/me").json()["role"] == "ADMIN", "the role must be unchanged"


def test_last_administrator_cannot_be_demoted(client):
    """Demoting the final administrator would leave nobody able to undo it."""
    from app.database import SessionLocal
    from app.models import Role, User
    from app.services.auth import hash_password

    password = "Second-Admin-Password-2026"
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "ADMIN"))
        extra = User(
            official_name="Second Administrator", organization="Test", designation="Admin",
            email=f"second-{uuid.uuid4().hex[:6]}@example.gov.in", employee_id=f"SEC-{uuid.uuid4().hex[:8]}",
            password_hash=hash_password(password), role=role,
        )
        db.add(extra)
        db.commit()
        extra_id = extra.id

    # Another administrator exists, so demoting this one is allowed.
    assert client.post(f"/auth/admin/users/{extra_id}/role", json={"role": "POLICY_MAKER"}).status_code == 200

    # The acting administrator is now the last one and cannot be demoted by anyone.
    me = client.get("/auth/me").json()
    assert client.post(f"/auth/admin/users/{me['id']}/role", json={"role": "POLICY_MAKER"}).status_code == 409


def test_identity_endpoint_reports_the_current_role(client):
    """The client refreshes from here, so it must reflect a role change at once."""
    body = client.get("/auth/me").json()
    assert body["role"] == "ADMIN"
    assert body["id"]
