"""SQLAlchemy models for land-acquisition risk monitoring."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Computed, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


role_permissions = Table("role_permissions", Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)
user_project_access = Table("user_project_access", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    official_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    role: Mapped[Role] = relationship()
    projects: Mapped[list["Project"]] = relationship(secondary=user_project_access)


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    official_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(100))
    requested_role: Mapped[str] = mapped_column(String(50), nullable=False)
    document_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("compensation_percentage BETWEEN 0 AND 100", name="ck_projects_compensation_percentage"),
        CheckConstraint("land_possession_percentage BETWEEN 0 AND 100", name="ck_projects_possession_percentage"),
        CheckConstraint("rehabilitation_percentage BETWEEN 0 AND 100", name="ck_projects_rehabilitation_percentage"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_projects_risk_score"),
        CheckConstraint("delay_probability BETWEEN 0 AND 1", name="ck_projects_delay_probability"),
        CheckConstraint("risk_category IN ('Low', 'Medium', 'High')", name="ck_projects_risk_category"),
        Index("ix_projects_state", "state"),
        Index("ix_projects_district", "district"),
        Index("ix_projects_country", "country"),
        Index("ix_projects_risk_category", "risk_category"),
        Index("ix_projects_project_type", "project_type"),
        Index("ix_projects_geom", "geom", postgresql_using="gist"),
    )

    project_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False, server_default="India")
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    land_area: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    land_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="Agricultural")
    land_price_per_acre: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="2500000")
    number_of_owners: Mapped[int] = mapped_column(Integer, nullable=False)
    affected_families: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    approval_timeline_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    documentation_completeness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="100")
    stakeholder_responsiveness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="100")
    historical_performance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="100")
    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False, server_default="Pre-notification")
    compensation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    compensation_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    legal_disputes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    land_possession_status: Mapped[str] = mapped_column(String(30), nullable=False)
    land_possession_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rehabilitation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    rehabilitation_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    delay_probability: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(10), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("POINT", srid=4326),
        Computed("ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)", persisted=True),
    )
    expected_completion_days: Mapped[int | None] = mapped_column(Integer)
    actual_completion_days: Mapped[int | None] = mapped_column(Integer)
    delayed: Mapped[bool | None] = mapped_column(Boolean)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    alerts: Mapped[list[Alert]] = relationship(back_populates="project", cascade="all, delete-orphan")
    notifications: Mapped[list[NotificationLog]] = relationship(back_populates="project", cascade="all, delete-orphan")
    snapshots: Mapped[list[ProjectSnapshot]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score_at_trigger: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending", index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, server_default="High")
    category: Mapped[str] = mapped_column(String(80), nullable=False, server_default="Risk threshold")
    drivers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    recommendations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    project: Mapped[Project] = relationship(back_populates="alerts")


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    project: Mapped[Project] = relationship(back_populates="notifications")


class ProjectSnapshot(Base):
    """Point-in-time project metrics. Feeds timeline analytics and retraining."""

    __tablename__ = "project_snapshots"
    __table_args__ = (
        Index("ix_project_snapshots_project_captured", "project_id", "captured_at"),
        Index("ix_project_snapshots_captured_at", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    delay_probability: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(10), nullable=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    compensation_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    land_possession_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rehabilitation_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    documentation_completeness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    stakeholder_responsiveness: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    legal_disputes: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_risks: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    source: Mapped[str] = mapped_column(String(30), nullable=False, server_default="scheduled")
    project: Mapped[Project] = relationship(back_populates="snapshots")


class ModelVersion(Base):
    """Registry of trained model bundles, one row per training run."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    training_source: Mapped[str] = mapped_column(String(255), nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    feature_names: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ApiClient(Base):
    """Service account for integrating external land-acquisition systems."""

    __tablename__ = "api_clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    state: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
