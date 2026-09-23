"""SQLAlchemy models for land-acquisition risk monitoring."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
        Index("ix_projects_risk_category", "risk_category"),
        Index("ix_projects_project_type", "project_type"),
        Index("ix_projects_geom", "geom", postgresql_using="gist"),
    )

    project_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    land_area: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    number_of_owners: Mapped[int] = mapped_column(Integer, nullable=False)
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
    alerts: Mapped[list[Alert]] = relationship(back_populates="project", cascade="all, delete-orphan")
    notifications: Mapped[list[NotificationLog]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score_at_trigger: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending")
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
