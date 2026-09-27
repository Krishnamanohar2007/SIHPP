"""Request and response contracts for the predictive land-acquisition API."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskCategory = Literal["Low", "Medium", "High"]
GeographyLevel = Literal["state", "district"]
TimelineBucket = Literal["day", "week", "month"]
ComparativeDimension = Literal[
    "project_type", "land_type", "lifecycle_stage", "risk_category", "state",
    "compensation_status", "land_possession_status", "rehabilitation_status",
]


class ProjectBase(BaseModel):
    """Operational project attributes. Risk fields are derived, so they are not here."""

    project_id: str = Field(min_length=1, max_length=20)
    project_name: str = Field(min_length=1, max_length=255)
    project_type: str = Field(min_length=1, max_length=80)
    country: str = Field(default="India", min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=100)
    land_area: float = Field(gt=0)
    land_type: str = Field(default="Agricultural", min_length=1, max_length=50)
    land_price_per_acre: float = Field(default=2_500_000, gt=0)
    number_of_owners: int = Field(ge=1)
    affected_families: int = Field(default=0, ge=0)
    approval_timeline_days: int = Field(default=0, ge=0)
    documentation_completeness: float = Field(default=100, ge=0, le=100)
    stakeholder_responsiveness: float = Field(default=100, ge=0, le=100)
    historical_performance_score: float = Field(default=100, ge=0, le=100)
    lifecycle_stage: str = Field(default="Pre-notification", min_length=1, max_length=40)
    compensation_status: str = Field(min_length=1, max_length=30)
    compensation_percentage: float = Field(ge=0, le=100)
    legal_disputes: int = Field(ge=0)
    land_possession_status: str = Field(min_length=1, max_length=30)
    land_possession_percentage: float = Field(ge=0, le=100)
    rehabilitation_status: str = Field(min_length=1, max_length=30)
    rehabilitation_percentage: float = Field(ge=0, le=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ProjectCreate(ProjectBase):
    """Create or replace a project.

    Risk fields are optional: when they are omitted the server scores the project
    with the active model. When all three are supplied - as in a CSV export
    round-trip - they must be internally consistent.
    """

    risk_score: float | None = Field(default=None, ge=0, le=100)
    delay_probability: float | None = Field(default=None, ge=0, le=1)
    risk_category: RiskCategory | None = None

    @model_validator(mode="after")
    def category_matches_score(self):
        if self.risk_score is None or self.risk_category is None:
            return self
        expected = "Low" if self.risk_score <= 30 else "Medium" if self.risk_score <= 60 else "High"
        if self.risk_category != expected:
            raise ValueError(f"risk_category must be {expected} for risk_score {self.risk_score}")
        return self


class ProjectPreviewCreate(ProjectBase):
    """Score a project that has not been saved yet."""


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    risk_score: float
    delay_probability: float
    risk_category: RiskCategory
    expected_completion_days: int | None = None
    actual_completion_days: int | None = None
    delayed: bool | None = None
    outcome_recorded_at: datetime | None = None
    outcome_notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    offset: int
    limit: int


class BulkUploadResult(BaseModel):
    inserted: int
    scored: int = 0


# ----------------------------------------------------------------- predictions
class ContributingFactor(BaseModel):
    feature: str
    feature_label: str
    driver: str
    value: Any = None
    shap_value: float
    impact: str


class DelayDriver(BaseModel):
    driver: str
    contribution: float
    share: float


class Recommendation(BaseModel):
    action: str
    detail: str
    driver: str
    feature: str | None = None
    feature_label: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    projected_delay_probability: float
    expected_reduction: float
    priority: str


class Prediction(BaseModel):
    risk_score: float
    delay_probability: float
    risk_category: RiskCategory
    lifecycle_risks: dict[str, float] = Field(default_factory=dict)
    lifecycle_risk_sources: dict[str, str] = Field(default_factory=dict)
    model_version: str


class Explanation(BaseModel):
    model_version: str
    stage: str | None = None
    delay_probability: float
    base_value: float
    top_contributing_factors: list[ContributingFactor]
    delay_drivers: list[DelayDriver]
    waterfall: list[dict]
    global_importance: list[dict]
    recommendations: list[Recommendation]


class ProjectPreview(Prediction):
    top_contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    delay_drivers: list[DelayDriver] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class OutcomeCreate(BaseModel):
    """Realised schedule recorded by an official. Ground truth for retraining."""

    expected_completion_days: int = Field(gt=0, le=10_000)
    actual_completion_days: int = Field(gt=0, le=10_000)
    delayed: bool | None = Field(default=None, description="Defaults to actual exceeding expected by more than 10%")
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def derive_delayed(self):
        if self.delayed is None:
            self.delayed = self.actual_completion_days > self.expected_completion_days * 1.1
        return self


# ------------------------------------------------------------------- analytics
class KpiSummary(BaseModel):
    total_projects: int
    high_risk_projects: int
    medium_risk_projects: int
    low_risk_projects: int
    high_risk_share: float
    average_delay_probability: float
    average_risk_score: float
    average_compensation_percentage: float
    average_possession_percentage: float
    average_rehabilitation_percentage: float
    average_documentation_completeness: float
    average_stakeholder_responsiveness: float
    average_approval_timeline_days: float
    total_legal_disputes: int
    total_affected_families: int
    total_land_area: float
    open_alerts: int
    projects_with_outcome: int
    outcome_agreement: float
    observed_delay_rate: float
    average_actual_completion_days: float
    average_expected_completion_days: float


class GeographyTrend(BaseModel):
    state: str
    district: str | None = None
    projects: int
    average_delay_probability: float
    average_risk_score: float
    high_risk_projects: int
    high_risk_share: float
    average_compensation_percentage: float
    legal_disputes: int
    affected_families: int


class TimelinePoint(BaseModel):
    period: str | None
    snapshots: int
    average_delay_probability: float
    average_risk_score: float
    high_risk_projects: int
    average_compensation_percentage: float
    average_possession_percentage: float
    average_rehabilitation_percentage: float


class ComparativeRow(BaseModel):
    dimension: str
    value: str | None
    projects: int
    average_delay_probability: float
    average_risk_score: float
    high_risk_projects: int
    average_land_area: float
    affected_families: int


class DriverPrevalence(BaseModel):
    driver: str
    criterion: str
    affected_projects: int
    share: float
    average_delay_probability: float


class PriorityRow(BaseModel):
    rank: int
    project_id: str
    project_name: str
    project_type: str
    state: str
    district: str
    lifecycle_stage: str
    risk_score: float
    risk_category: RiskCategory
    delay_probability: float
    affected_families: int
    legal_disputes: int
    exposure_crore: float
    priority_index: float


class StageExposure(BaseModel):
    stage: str
    projects: int
    average_delay_probability: float
    high_risk_projects: int


class SnapshotPoint(BaseModel):
    captured_at: str
    risk_score: float
    delay_probability: float
    risk_category: RiskCategory
    lifecycle_stage: str
    compensation_percentage: float
    land_possession_percentage: float
    rehabilitation_percentage: float
    stage_risks: dict[str, float] = Field(default_factory=dict)
    source: str


class RiskCategoryCount(BaseModel):
    risk_category: RiskCategory
    count: int


class StateDelayAverage(BaseModel):
    state: str
    average_delay_probability: float


class SummaryStats(BaseModel):
    """Legacy dashboard summary, retained so existing clients keep working."""

    total_projects: int
    risk_category_counts: list[RiskCategoryCount]
    average_delay_probability_by_state: list[StateDelayAverage]


# ---------------------------------------------------------------------- alerts
class AlertDelivery(BaseModel):
    channel: str
    status: str
    sent_at: datetime | None = None


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    project_name: str | None = None
    state: str | None = None
    district: str | None = None
    risk_score_at_trigger: float
    message: str
    created_at: datetime
    channel: str
    status: str
    severity: str
    category: str
    drivers: list[dict] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
    assigned_to: int | None = None
    acknowledged_by: int | None = None
    acknowledged_at: datetime | None = None
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    deliveries: list[AlertDelivery] = Field(default_factory=list)


class AlertAcknowledge(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AlertResolve(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=2000)


class AlertAssign(BaseModel):
    user_id: int


class ScanResult(BaseModel):
    triggered: int
    scored: int = 0
    snapshots: int = 0
    skipped: str | None = None


# ------------------------------------------------------------- model registry
class ModelVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    version: str
    algorithm: str
    training_source: str
    training_rows: int
    artifact_path: str
    feature_names: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    is_active: bool
    notes: str | None = None
    trained_at: datetime
    created_by: int | None = None


class RetrainRequest(BaseModel):
    force_activate: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class RetrainResult(BaseModel):
    version: str
    activated: bool
    training_rows: int
    training_source: str
    roc_auc: float | None = None
    previous_roc_auc: float | None = None
    metrics: dict = Field(default_factory=dict)


class RescoreResult(BaseModel):
    scored: int
    changed: int
    snapshots: int
    skipped: str | None = None


# --------------------------------------------------------------- integration
class ApiClientCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    scopes: list[str] = Field(min_length=1)
    state: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=100)


class ApiClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    state: str | None = None
    district: str | None = None
    status: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiClientCreated(ApiClientRead):
    api_key: str = Field(description="Shown once. Store it now; it cannot be retrieved again.")


class IngestResult(BaseModel):
    received: int
    created: int
    updated: int
    scored: int
    rejected: list[dict] = Field(default_factory=list)
