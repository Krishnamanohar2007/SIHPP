"""Replace placeholder land prices with deterministic varied values."""

from alembic import op


revision = "20260925_04"
down_revision = "20260925_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only replace migration-created placeholder values. User-entered prices stay intact.
    op.execute("""
        UPDATE projects
        SET land_price_per_acre = ROUND(
            (CASE land_type
                WHEN 'Commercial' THEN 7000000
                WHEN 'Residential' THEN 5000000
                WHEN 'Industrial' THEN 3500000
                WHEN 'Barren' THEN 800000
                ELSE 1500000
            END) *
            (CASE state
                WHEN 'Maharashtra' THEN 1.65 WHEN 'Delhi' THEN 1.90
                WHEN 'Karnataka' THEN 1.45 WHEN 'Tamil Nadu' THEN 1.35
                WHEN 'Telangana' THEN 1.30 WHEN 'Gujarat' THEN 1.25
                WHEN 'Kerala' THEN 1.35 WHEN 'Uttar Pradesh' THEN 1.05
                WHEN 'Rajasthan' THEN 0.85 WHEN 'Madhya Pradesh' THEN 0.80
                WHEN 'Bihar' THEN 0.70 WHEN 'Odisha' THEN 0.75
                ELSE 1.00
            END) *
            (0.80 + (ABS(hashtext(project_id)) % 41)::numeric / 100), 2)
        WHERE land_price_per_acre = 2500000
    """)


def downgrade() -> None:
    # Restore only rows that this migration could have changed.
    op.execute("""
        UPDATE projects
        SET land_price_per_acre = 2500000
        WHERE project_id ~ '^LAP-[0-9]{4}$'
    """)
