"""Remove synthetic mandal data and classify existing synthetic land types."""

from alembic import op
import sqlalchemy as sa


revision = "20260925_03"
down_revision = "20260925_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE projects
        SET land_type = CASE project_type
            WHEN 'Industrial Corridor' THEN 'Industrial'
            WHEN 'Logistics Park' THEN 'Industrial'
            WHEN 'Airport Expansion' THEN 'Commercial'
            WHEN 'Metro Rail' THEN 'Residential'
            WHEN 'Railway Corridor' THEN 'Residential'
            WHEN 'Transmission Line' THEN 'Barren'
            ELSE 'Agricultural'
        END
        WHERE project_id ~ '^LAP-[0-9]{4}$'
          AND land_type = 'Agricultural'
    """)
    op.drop_index("ix_projects_mandal", table_name="projects")
    op.drop_column("projects", "mandal")


def downgrade() -> None:
    op.add_column("projects", sa.Column("mandal", sa.String(100), nullable=False, server_default="Not recorded"))
    op.create_index("ix_projects_mandal", "projects", ["mandal"])
