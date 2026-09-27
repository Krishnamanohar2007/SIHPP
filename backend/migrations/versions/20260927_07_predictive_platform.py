"""Predictive platform: outcomes, snapshots, model registry, API clients, alert workflow."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260927_07"
down_revision = "20260927_06"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("alerts.write", "Acknowledge, assign and resolve alerts"),
    ("models.manage", "Retrain and activate prediction models"),
    ("integration.manage", "Issue and revoke integration API keys"),
    ("projects.outcome", "Record realised project outcomes"),
    ("audit.read", "Read the audit trail"),
]
# role code -> permission codes granted by this migration
GRANTS = {
    "LAND_ACQUISITION_AUTHORITY": ["alerts.write", "projects.outcome", "analytics.read"],
    "DISTRICT_ADMINISTRATION": ["alerts.write", "projects.outcome", "analytics.read"],
    "PROJECT_IMPLEMENTING_AGENCY": ["alerts.write", "analytics.read"],
    "STATE_GOVERNMENT": ["alerts.read", "audit.read"],
    "POLICY_MAKER": ["alerts.read", "audit.read"],
}


def upgrade():
    # --- realised outcomes, the ground truth for continuous learning ---------
    op.add_column("projects", sa.Column("expected_completion_days", sa.Integer()))
    op.add_column("projects", sa.Column("actual_completion_days", sa.Integer()))
    op.add_column("projects", sa.Column("delayed", sa.Boolean()))
    op.add_column("projects", sa.Column("outcome_recorded_at", sa.DateTime(timezone=True)))
    op.add_column("projects", sa.Column("outcome_notes", sa.Text()))
    op.add_column("projects", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("projects", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_projects_delayed", "projects", ["delayed"])
    op.create_index("ix_projects_lifecycle_stage", "projects", ["lifecycle_stage"])

    # --- metric history, powering timeline and comparative analytics --------
    op.create_table(
        "project_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("project_id", sa.String(20), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("delay_probability", sa.Numeric(6, 4), nullable=False),
        sa.Column("risk_category", sa.String(10), nullable=False),
        sa.Column("lifecycle_stage", sa.String(40), nullable=False),
        sa.Column("compensation_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("land_possession_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("rehabilitation_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("documentation_completeness", sa.Numeric(5, 2), nullable=False),
        sa.Column("stakeholder_responsiveness", sa.Numeric(5, 2), nullable=False),
        sa.Column("legal_disputes", sa.Integer, nullable=False),
        sa.Column("stage_risks", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("source", sa.String(30), nullable=False, server_default="scheduled"),
    )
    op.create_index("ix_project_snapshots_project_captured", "project_snapshots", ["project_id", "captured_at"])
    op.create_index("ix_project_snapshots_captured_at", "project_snapshots", ["captured_at"])

    # --- model registry, so every prediction is traceable to a version ------
    op.create_table(
        "model_versions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version", sa.String(60), nullable=False, unique=True),
        sa.Column("algorithm", sa.String(80), nullable=False),
        sa.Column("training_source", sa.String(255), nullable=False),
        sa.Column("training_rows", sa.Integer, nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("feature_names", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
    )
    op.create_index("ix_model_versions_is_active", "model_versions", ["is_active"])

    # --- service accounts for integration with external land records --------
    op.create_table(
        "api_clients",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(16), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("scopes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("state", sa.String(80)),
        sa.Column("district", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
    )

    # --- alert workflow -----------------------------------------------------
    op.add_column("alerts", sa.Column("severity", sa.String(10), nullable=False, server_default="High"))
    op.add_column("alerts", sa.Column("category", sa.String(80), nullable=False, server_default="Risk threshold"))
    op.add_column("alerts", sa.Column("drivers", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("alerts", sa.Column("recommendations", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("alerts", sa.Column("assigned_to", sa.BigInteger, sa.ForeignKey("users.id")))
    op.add_column("alerts", sa.Column("acknowledged_by", sa.BigInteger, sa.ForeignKey("users.id")))
    op.add_column("alerts", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("alerts", sa.Column("resolved_by", sa.BigInteger, sa.ForeignKey("users.id")))
    op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column("alerts", sa.Column("resolution_note", sa.Text))
    op.create_index("ix_alerts_status", "alerts", ["status"])

    # --- permissions --------------------------------------------------------
    bind = op.get_bind()
    for code, description in NEW_PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING"),
            {"code": code, "description": description},
        )
    # Admin keeps every permission.
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code = 'ADMIN' "
        "ON CONFLICT DO NOTHING"
    ))
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN ('models.manage', 'integration.manage') "
        "WHERE r.code = 'POLICY_MAKER' ON CONFLICT DO NOTHING"
    ))
    for role, permissions in GRANTS.items():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = ANY(:codes) "
                "WHERE r.code = :role ON CONFLICT DO NOTHING"
            ),
            {"codes": permissions, "role": role},
        )


def downgrade():
    op.drop_index("ix_alerts_status", table_name="alerts")
    for name in ("resolution_note", "resolved_at", "resolved_by", "acknowledged_at", "acknowledged_by",
                 "assigned_to", "recommendations", "drivers", "category", "severity"):
        op.drop_column("alerts", name)
    op.drop_table("api_clients")
    op.drop_index("ix_model_versions_is_active", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index("ix_project_snapshots_captured_at", table_name="project_snapshots")
    op.drop_index("ix_project_snapshots_project_captured", table_name="project_snapshots")
    op.drop_table("project_snapshots")
    op.drop_index("ix_projects_lifecycle_stage", table_name="projects")
    op.drop_index("ix_projects_delayed", table_name="projects")
    for name in ("updated_at", "created_at", "outcome_notes", "outcome_recorded_at", "delayed",
                 "actual_completion_days", "expected_completion_days"):
        op.drop_column("projects", name)
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE code = ANY(:codes))"
    ), {"codes": [code for code, _ in NEW_PERMISSIONS]})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"), {"codes": [code for code, _ in NEW_PERMISSIONS]})
