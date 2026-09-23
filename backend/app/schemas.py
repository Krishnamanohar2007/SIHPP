from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskCategory = Literal["Low", "Medium", "High"]


class ProjectFields(BaseModel):
    project_id: str = Field(min_length=1, max_length=20)
    project_name: str = Field(min_length=1, max_length=255)
    project_type: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=100)
    land_area: float = Field(gt=0)
    number_of_owners: int = Field(ge=1)
    compensation_status: str = Field(min_length=1, max_length=30)
    compensation_percentage: float = Field(ge=0, le=100)
    legal_disputes: int = Field(ge=0)
    land_possession_status: str = Field(min_length=1, max_length=30)
    land_possession_percentage: float = Field(ge=0, le=100)
    rehabilitation_status: str = Field(min_length=1, max_length=30)
    rehabilitation_percentage: float = Field(ge=0, le=100)
    risk_score: float = Field(ge=0, le=100)
    delay_probability: float = Field(ge=0, le=1)
    risk_category: RiskCategory
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def category_matches_score(self):
        expected = "Low" if self.risk_score <= 30 else "Medium" if self.risk_score <= 60 else "High"
        if self.risk_category != expected:
            raise ValueError(f"risk_category must be {expected} for risk_score {self.risk_score}")
        return self


class ProjectCreate(ProjectFields):
    pass


class ProjectPreviewCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=20)
    project_name: str = Field(min_length=1, max_length=255)
    project_type: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=100)
    land_area: float = Field(gt=0)
    number_of_owners: int = Field(ge=1)
    compensation_status: str = Field(min_length=1, max_length=30)
    compensation_percentage: float = Field(ge=0, le=100)
    legal_disputes: int = Field(ge=0)
    land_possession_status: str = Field(min_length=1, max_length=30)
    land_possession_percentage: float = Field(ge=0, le=100)
    rehabilitation_status: str = Field(min_length=1, max_length=30)
    rehabilitation_percentage: float = Field(ge=0, le=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ProjectPreview(BaseModel):
    risk_score: float
    delay_probability: float
    risk_category: RiskCategory
    shap_factors: list[dict]
    recommendations: list[str]


class ProjectRead(ProjectFields):
    model_config = ConfigDict(from_attributes=True)


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    offset: int
    limit: int


class BulkUploadResult(BaseModel):
    inserted: int


class RiskCategoryCount(BaseModel):
    risk_category: RiskCategory
    count: int


class StateDelayAverage(BaseModel):
    state: str
    average_delay_probability: float


class SummaryStats(BaseModel):
    total_projects: int
    risk_category_counts: list[RiskCategoryCount]
    average_delay_probability_by_state: list[StateDelayAverage]


class AlertRead(BaseModel):
    id: int
    project_id: str
    risk_score_at_trigger: float
    message: str
    created_at: datetime
    channel: str
    status: str
    model_config = ConfigDict(from_attributes=True)
