"""Add hierarchical location and land-value fields to projects."""

from alembic import op
import sqlalchemy as sa


revision = "20260925_02"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("country", sa.String(80), nullable=False, server_default="India"))
    op.add_column("projects", sa.Column("mandal", sa.String(100), nullable=False, server_default="Not recorded"))
    op.add_column("projects", sa.Column("land_type", sa.String(50), nullable=False, server_default="Agricultural"))
    op.add_column("projects", sa.Column("land_price_per_acre", sa.Numeric(14, 2), nullable=False, server_default="2500000"))
    op.create_index("ix_projects_country", "projects", ["country"])
    op.create_index("ix_projects_mandal", "projects", ["mandal"])


def downgrade() -> None:
    op.drop_index("ix_projects_mandal", table_name="projects")
    op.drop_index("ix_projects_country", table_name="projects")
    op.drop_column("projects", "land_price_per_acre")
    op.drop_column("projects", "land_type")
    op.drop_column("projects", "mandal")
    op.drop_column("projects", "country")
