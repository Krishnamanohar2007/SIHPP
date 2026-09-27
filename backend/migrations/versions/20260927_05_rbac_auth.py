"""Add role-based access control, registrations, and audit trail."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260927_05"
down_revision = "20260925_04"
branch_labels = None
depends_on = None

ROLE_ROWS = [("ADMIN","Admin"),("LAND_ACQUISITION_AUTHORITY","Land Acquisition Authority"),("DISTRICT_ADMINISTRATION","District Administration"),("STATE_GOVERNMENT","State Government"),("PROJECT_IMPLEMENTING_AGENCY","Project Implementing Agency"),("POLICY_MAKER","Policy Maker")]
PERMISSION_ROWS = [("users.review","Review registrations"),("users.manage","Manage users"),("projects.read","Read projects"),("projects.write","Create or update projects"),("alerts.read","Read alerts"),("analytics.read","Read analytics")]

def upgrade():
    op.create_table("roles",sa.Column("id",sa.Integer,primary_key=True),sa.Column("code",sa.String(50),nullable=False,unique=True),sa.Column("name",sa.String(100),nullable=False))
    op.create_table("permissions",sa.Column("id",sa.Integer,primary_key=True),sa.Column("code",sa.String(100),nullable=False,unique=True),sa.Column("description",sa.String(255),nullable=False))
    op.create_table("role_permissions",sa.Column("role_id",sa.Integer,sa.ForeignKey("roles.id",ondelete="CASCADE"),primary_key=True),sa.Column("permission_id",sa.Integer,sa.ForeignKey("permissions.id",ondelete="CASCADE"),primary_key=True))
    op.create_table("users",sa.Column("id",sa.BigInteger,primary_key=True),sa.Column("official_name",sa.String(255),nullable=False),sa.Column("organization",sa.String(255),nullable=False),sa.Column("designation",sa.String(255),nullable=False),sa.Column("email",sa.String(255),nullable=False,unique=True),sa.Column("employee_id",sa.String(100),nullable=False,unique=True),sa.Column("password_hash",sa.String(255),nullable=False),sa.Column("state",sa.String(80)),sa.Column("district",sa.String(100)),sa.Column("status",sa.String(20),nullable=False,server_default="ACTIVE"),sa.Column("role_id",sa.Integer,sa.ForeignKey("roles.id"),nullable=False))
    op.create_index("ix_users_email","users",["email"])
    op.create_table("user_project_access",sa.Column("user_id",sa.BigInteger,sa.ForeignKey("users.id",ondelete="CASCADE"),primary_key=True),sa.Column("project_id",sa.String(20),sa.ForeignKey("projects.project_id",ondelete="CASCADE"),primary_key=True))
    op.create_table("registration_requests",sa.Column("id",sa.BigInteger,primary_key=True),sa.Column("official_name",sa.String(255),nullable=False),sa.Column("organization",sa.String(255),nullable=False),sa.Column("designation",sa.String(255),nullable=False),sa.Column("email",sa.String(255),nullable=False),sa.Column("employee_id",sa.String(100),nullable=False),sa.Column("state",sa.String(80)),sa.Column("district",sa.String(100)),sa.Column("requested_role",sa.String(50),nullable=False),sa.Column("document_path",sa.String(500),nullable=False),sa.Column("status",sa.String(20),nullable=False,server_default="PENDING"),sa.Column("rejection_reason",sa.Text),sa.Column("reviewed_by",sa.BigInteger,sa.ForeignKey("users.id")),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.Column("reviewed_at",sa.DateTime(timezone=True)))
    op.create_index("ix_registration_requests_email","registration_requests",["email"])
    op.create_table("audit_log",sa.Column("id",sa.BigInteger,primary_key=True),sa.Column("actor_id",sa.BigInteger,sa.ForeignKey("users.id")),sa.Column("action",sa.String(100),nullable=False),sa.Column("target_type",sa.String(80),nullable=False),sa.Column("target_id",sa.String(100),nullable=False),sa.Column("details",postgresql.JSONB,nullable=False,server_default="{}"),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False))
    roles = op.get_bind(); roles.execute(sa.text("INSERT INTO roles (code,name) VALUES " + ",".join(f"('{c}','{n}')" for c,n in ROLE_ROWS)))
    roles.execute(sa.text("INSERT INTO permissions (code,description) VALUES " + ",".join(f"('{c}','{d}')" for c,d in PERMISSION_ROWS)))
    roles.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.code='ADMIN'"))
    roles.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code IN ('projects.read','projects.write','alerts.read') WHERE r.code='LAND_ACQUISITION_AUTHORITY'"))
    roles.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code IN ('projects.read','projects.write','alerts.read') WHERE r.code='DISTRICT_ADMINISTRATION'"))
    roles.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code IN ('projects.read','analytics.read') WHERE r.code IN ('STATE_GOVERNMENT','POLICY_MAKER')"))
    roles.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code IN ('projects.read','alerts.read') WHERE r.code='PROJECT_IMPLEMENTING_AGENCY'"))

def downgrade():
    op.drop_table("audit_log"); op.drop_table("registration_requests"); op.drop_table("user_project_access"); op.drop_index("ix_users_email",table_name="users"); op.drop_table("users"); op.drop_table("role_permissions"); op.drop_table("permissions"); op.drop_table("roles")
