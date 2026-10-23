"""Seed one demonstration account per role, with the data each role needs.

Every role sees a different slice of the platform, so a demonstration needs an
account per role and projects placed where those accounts can reach them. This
script creates that set, assigns project level access, records realised outcomes
so the continuous learning loop has labels, and leaves one registration request
pending so the approval workflow can be shown.

The script is idempotent: an account that already exists is left untouched.

    docker compose -f docker/docker-compose.yml --env-file docker/.env \
      exec backend python scripts/seed_demo_users.py

These are demonstration credentials for a local stack. Never seed them into an
environment that is reachable from a network you do not control.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Project, RegistrationRequest, Role, User
from app.services.auth import hash_password


PASSWORD = "Bhoomi-Setu-Demo-2026"

# The demonstration state and district are chosen because the seeded register
# holds projects there; a scoped account over an empty area shows nothing.
STATE = "Karnataka"
DISTRICT = "Mysuru"

ACCOUNTS = [
    {
        "role": "POLICY_MAKER",
        "email": "policy.maker@bhoomisetu.gov.in",
        "name": "Policy Maker (Demonstration)",
        "designation": "Adviser, Infrastructure",
        "organization": "NITI Policy Cell",
        "state": None, "district": None,
        "note": "National view. Reads everything, edits nothing. Governs models and integration keys.",
    },
    {
        "role": "STATE_GOVERNMENT",
        "email": "state.karnataka@bhoomisetu.gov.in",
        "name": "State Secretary (Demonstration)",
        "designation": "Secretary, Revenue",
        "organization": f"Government of {STATE}",
        "state": STATE, "district": None,
        "note": f"Sees only {STATE}. Read and audit, no write.",
    },
    {
        "role": "DISTRICT_ADMINISTRATION",
        "email": "district.mysuru@bhoomisetu.gov.in",
        "name": "District Collector (Demonstration)",
        "designation": "Deputy Commissioner",
        "organization": f"{DISTRICT} District Administration",
        "state": STATE, "district": DISTRICT,
        "note": f"Sees only {DISTRICT}. Creates and edits projects there, works alerts, records outcomes.",
    },
    {
        "role": "LAND_ACQUISITION_AUTHORITY",
        "email": "authority.mysuru@bhoomisetu.gov.in",
        "name": "Acquisition Officer (Demonstration)",
        "designation": "Special Land Acquisition Officer",
        "organization": f"{DISTRICT} Land Acquisition Unit",
        "state": STATE, "district": DISTRICT,
        "note": "Sees only assigned projects. Edits them, works alerts, records outcomes. Cannot create projects.",
    },
    {
        "role": "PROJECT_IMPLEMENTING_AGENCY",
        "email": "agency.mysuru@bhoomisetu.gov.in",
        "name": "Implementing Agency (Demonstration)",
        "designation": "Project Manager",
        "organization": "National Infrastructure Agency",
        "state": STATE, "district": DISTRICT,
        "note": "Sees only assigned projects. Reads and works alerts; no project write.",
    },
]

# Roles whose visibility comes from explicit project assignment rather than area.
PROJECT_SCOPED = {"LAND_ACQUISITION_AUTHORITY", "PROJECT_IMPLEMENTING_AGENCY"}
ASSIGNED_PROJECTS = 6
OUTCOMES_TO_RECORD = 48
SEED_NOTE = "Recorded during demonstration seeding."


def ensure_accounts(db) -> list[tuple[str, str, str]]:
    created = []
    for spec in ACCOUNTS:
        existing = db.scalar(select(User).where(User.email == spec["email"]))
        if existing is not None:
            created.append((spec["role"], spec["email"], "already present"))
            continue
        role = db.scalar(select(Role).where(Role.code == spec["role"]))
        if role is None:
            created.append((spec["role"], spec["email"], "role missing, skipped"))
            continue
        db.add(User(
            official_name=spec["name"],
            organization=spec["organization"],
            designation=spec["designation"],
            email=spec["email"],
            employee_id=f"DEMO-{spec['role'][:12]}",
            password_hash=hash_password(PASSWORD),
            state=spec["state"],
            district=spec["district"],
            role=role,
        ))
        created.append((spec["role"], spec["email"], "created"))
    db.flush()
    return created


def assign_projects(db) -> dict[str, list[str]]:
    """Give the project-scoped roles something to see.

    Highest risk first, so the assigned set exercises alerts and recommendations
    rather than quiet projects.
    """
    assignments: dict[str, list[str]] = {}
    pool = db.scalars(
        select(Project)
        .where(Project.district == DISTRICT)
        .order_by(Project.risk_score.desc())
        .limit(ASSIGNED_PROJECTS * 2)
    ).all()
    if not pool:
        pool = db.scalars(select(Project).order_by(Project.risk_score.desc()).limit(ASSIGNED_PROJECTS * 2)).all()

    for spec in ACCOUNTS:
        if spec["role"] not in PROJECT_SCOPED:
            continue
        user = db.scalar(select(User).where(User.email == spec["email"]))
        if user is None:
            continue
        # Interleave so the two roles overlap partially but not completely.
        offset = 0 if spec["role"] == "LAND_ACQUISITION_AUTHORITY" else 3
        chosen = pool[offset:offset + ASSIGNED_PROJECTS]
        for project in chosen:
            if project not in user.projects:
                user.projects.append(project)
        assignments[spec["email"]] = [project.project_id for project in chosen]
    db.flush()
    return assignments


def record_outcomes(db) -> int:
    """Record realised schedules so the learning loop and its indicators populate.

    Both outcomes are represented: projects that slipped and projects that did
    not, so the reported agreement between prediction and reality is meaningful
    rather than uniformly one value.
    """
    seeded = db.scalars(select(Project).where(Project.outcome_notes == SEED_NOTE).order_by(Project.project_id)).all()
    fresh = db.scalars(
        select(Project).where(Project.delayed.is_(None)).order_by(Project.project_id)
        .limit(max(0, OUTCOMES_TO_RECORD - len(seeded)))
    ).all()
    now = datetime.now(timezone.utc)

    # Deriving the outcome purely from the prediction would make the reported
    # agreement exactly 1.0, which says nothing. Every fifth project is recorded
    # against its prediction, so the indicator reflects a realistic disagreement
    # between what the model expected and what the register observed.
    for index, project in enumerate(seeded + fresh):
        predicted_slip = float(project.delay_probability) >= 0.5
        slipped = (not predicted_slip) if index % 5 == 4 else predicted_slip
        sanctioned = 540
        project.expected_completion_days = sanctioned
        project.actual_completion_days = int(sanctioned * (1.45 if slipped else 0.95))
        project.delayed = slipped
        project.outcome_recorded_at = now
        project.outcome_notes = SEED_NOTE
    db.flush()
    return len(seeded) + len(fresh)


def ensure_pending_registration(db) -> str:
    """Leave one request pending so the approval workflow has something to show."""
    email = "new.officer@bhoomisetu.gov.in"
    existing = db.scalar(select(RegistrationRequest).where(RegistrationRequest.email == email))
    if existing is not None:
        return "already present"

    uploads = Path("/app/uploads")
    uploads.mkdir(parents=True, exist_ok=True)
    document = uploads / "demo-registration-document.pdf"
    if not document.exists():
        # A minimal valid PDF, so the reviewer's download link resolves.
        document.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n"
        )
    db.add(RegistrationRequest(
        official_name="Awaiting Approval (Demonstration)",
        organization=f"{DISTRICT} Land Acquisition Unit",
        designation="Assistant Commissioner",
        email=email,
        employee_id="DEMO-PENDING-001",
        state=STATE,
        district=DISTRICT,
        requested_role="DISTRICT_ADMINISTRATION",
        document_path=str(document),
    ))
    db.flush()
    return "created"


def main() -> None:
    with SessionLocal() as db:
        accounts = ensure_accounts(db)
        assignments = assign_projects(db)
        outcomes = record_outcomes(db)
        pending = ensure_pending_registration(db)
        db.commit()

    print("\nDemonstration accounts")
    print(f"  password for every account below: {PASSWORD}\n")
    for role, email, status in accounts:
        print(f"  {role:<28} {email:<40} {status}")

    print("\nProject access")
    for email, ids in assignments.items():
        print(f"  {email:<40} {', '.join(ids)}")

    print(f"\nRecorded outcomes: {outcomes} projects")
    print(f"Pending registration request: {pending}")
    print("\nThese are local demonstration credentials. Do not seed them anywhere public.")


if __name__ == "__main__":
    main()
