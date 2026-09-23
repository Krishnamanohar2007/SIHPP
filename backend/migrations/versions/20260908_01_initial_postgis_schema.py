"""Create project risk-monitoring schema with PostGIS point geometry."""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql


revision = "20260908_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(20), primary_key=True),
        sa.Column("project_name", sa.String(255), nullable=False),
        sa.Column("project_type", sa.String(80), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("land_area", sa.Numeric(12, 2), nullable=False),
        sa.Column("number_of_owners", sa.Integer(), nullable=False),
        sa.Column("compensation_status", sa.String(30), nullable=False),
        sa.Column("compensation_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("legal_disputes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("land_possession_status", sa.String(30), nullable=False),
        sa.Column("land_possession_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("rehabilitation_status", sa.String(30), nullable=False),
        sa.Column("rehabilitation_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("delay_probability", sa.Numeric(4, 2), nullable=False),
        sa.Column("risk_category", sa.String(10), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326), sa.Computed("ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)", persisted=True)),
        sa.CheckConstraint("compensation_percentage BETWEEN 0 AND 100", name="ck_projects_compensation_percentage"),
        sa.CheckConstraint("land_possession_percentage BETWEEN 0 AND 100", name="ck_projects_possession_percentage"),
        sa.CheckConstraint("rehabilitation_percentage BETWEEN 0 AND 100", name="ck_projects_rehabilitation_percentage"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_projects_risk_score"),
        sa.CheckConstraint("delay_probability BETWEEN 0 AND 1", name="ck_projects_delay_probability"),
        sa.CheckConstraint("risk_category IN ('Low', 'Medium', 'High')", name="ck_projects_risk_category"),
    )
    for column in ("state", "district", "risk_category", "project_type"):
        op.create_index(f"ix_projects_{column}", "projects", [column])
    op.create_index("ix_projects_geom", "projects", ["geom"], postgresql_using="gist")
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.String(20), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_score_at_trigger", sa.Numeric(5, 2), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
    )
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])
    op.create_table(
        "notifications_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.String(20), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_index("ix_notifications_log_project_id", "notifications_log", ["project_id"])


def downgrade() -> None:
    op.drop_table("notifications_log")
    op.drop_table("alerts")
    op.drop_table("projects")
