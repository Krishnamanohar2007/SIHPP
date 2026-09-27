"""Add lifecycle delay drivers without invalidating existing projects."""
from alembic import op
import sqlalchemy as sa

revision = "20260927_06"
down_revision = "20260927_05"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("projects", sa.Column("affected_families", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("projects", sa.Column("approval_timeline_days", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("projects", sa.Column("documentation_completeness", sa.Numeric(5, 2), nullable=False, server_default="100"))
    op.add_column("projects", sa.Column("stakeholder_responsiveness", sa.Numeric(5, 2), nullable=False, server_default="100"))
    op.add_column("projects", sa.Column("historical_performance_score", sa.Numeric(5, 2), nullable=False, server_default="100"))
    op.add_column("projects", sa.Column("lifecycle_stage", sa.String(40), nullable=False, server_default="Pre-notification"))

def downgrade():
    for name in ("lifecycle_stage", "historical_performance_score", "stakeholder_responsiveness", "documentation_completeness", "approval_timeline_days", "affected_families"):
        op.drop_column("projects", name)
