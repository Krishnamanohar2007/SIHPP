"""Single source of truth for the predictive model's feature contract.

The training pipeline writes every value defined here into ``model_card.json``
next to the model artifacts, and the API reads that card back at load time. The
API therefore never hard-codes a feature list or a scoring coefficient: change
this module, retrain, and serving follows automatically.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


# Ordered feature contract. Order matters: it is persisted in the model card and
# used to rebuild a single-row frame at prediction time.
CATEGORICAL_FEATURES = ["project_type", "land_type", "lifecycle_stage"]
NUMERIC_FEATURES = [
    "land_area",
    "number_of_owners",
    "affected_families",
    "approval_timeline_days",
    "documentation_completeness",
    "stakeholder_responsiveness",
    "historical_performance_score",
    "compensation_percentage",
    "legal_disputes",
    "land_possession_percentage",
    "rehabilitation_percentage",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Lifecycle stages that receive their own delay model, in lifecycle order.
STAGES = ["Notification", "Compensation", "Possession", "Rehabilitation", "Legal resolution"]


def stage_slug(stage: str) -> str:
    return stage.lower().replace(" ", "_")


STAGE_LABELS = {stage: f"delayed_{stage_slug(stage)}" for stage in STAGES}
PORTFOLIO_LABEL = "delayed"

# Transparent, auditable risk rule. ``base`` is selected by project type,
# ``deficits`` are scored on the shortfall from 100, and ``levels`` are scored on
# the raw value. Persisted in the model card so the API applies the same numbers.
RISK_RULE: dict[str, Any] = {
    "intercept": 0.0,
    "type_weights": {
        "National Highway": 9, "Railway Corridor": 12, "Irrigation Canal": 7,
        "Industrial Corridor": 16, "Solar Park": 5, "Transmission Line": 8,
        "Metro Rail": 18, "Logistics Park": 11, "Airport Expansion": 15,
    },
    "default_type_weight": 10,
    # coefficient applied to (100 - value)
    "deficits": {
        "compensation_percentage": 0.30,
        "land_possession_percentage": 0.15,
        "rehabilitation_percentage": 0.19,
        "documentation_completeness": 0.11,
        "stakeholder_responsiveness": 0.09,
        "historical_performance_score": 0.08,
    },
    # coefficient applied to the value itself
    "levels": {
        "legal_disputes": 3.8,
        "approval_timeline_days": 0.010,
    },
    # weight applied to the model's delay probability, expressed on a 0-100 scale
    "delay_probability_weight": 12.0,
}

# Maps a raw feature to the delay driver a policymaker acts on. Used to roll SHAP
# contributions up into the driver categories named in the problem statement.
DRIVER_TAXONOMY: dict[str, str] = {
    "approval_timeline_days": "Pending approvals",
    "lifecycle_stage": "Pending approvals",
    "compensation_percentage": "Compensation delays",
    "legal_disputes": "Legal disputes",
    "documentation_completeness": "Incomplete documentation",
    "rehabilitation_percentage": "Rehabilitation status",
    "affected_families": "Rehabilitation status",
    "land_possession_percentage": "Possession bottlenecks",
    "stakeholder_responsiveness": "Administrative bottlenecks",
    "historical_performance_score": "Administrative bottlenecks",
    "land_area": "Project scale",
    "number_of_owners": "Ownership fragmentation",
    "project_type": "Project profile",
    "land_type": "Project profile",
}

# Human-readable labels for explanation output.
FEATURE_LABELS: dict[str, str] = {
    "project_type": "Project type",
    "land_type": "Land type",
    "lifecycle_stage": "Lifecycle stage",
    "land_area": "Land area (acres)",
    "number_of_owners": "Number of owners",
    "affected_families": "Affected families",
    "approval_timeline_days": "Approval timeline (days)",
    "documentation_completeness": "Documentation completeness",
    "stakeholder_responsiveness": "Stakeholder responsiveness",
    "historical_performance_score": "Historical performance",
    "compensation_percentage": "Compensation disbursed",
    "legal_disputes": "Legal disputes",
    "land_possession_percentage": "Land possession",
    "rehabilitation_percentage": "Rehabilitation progress",
}

# Feature defaults so a partially filled payload can still be scored.
FEATURE_DEFAULTS: dict[str, Any] = {
    "project_type": "National Highway",
    "land_type": "Agricultural",
    "lifecycle_stage": "Pre-notification",
    "land_area": 100.0,
    "number_of_owners": 10,
    "affected_families": 0,
    "approval_timeline_days": 0,
    "documentation_completeness": 100.0,
    "stakeholder_responsiveness": 100.0,
    "historical_performance_score": 100.0,
    "compensation_percentage": 0.0,
    "legal_disputes": 0,
    "land_possession_percentage": 0.0,
    "rehabilitation_percentage": 0.0,
}


def feature_frame(values: Mapping[str, Any], features: list[str] | None = None) -> pd.DataFrame:
    """Build a one-row frame in contract order, filling absent fields."""
    names = features or FEATURES
    row = {}
    for name in names:
        value = values.get(name, FEATURE_DEFAULTS.get(name))
        if value is None:
            value = FEATURE_DEFAULTS.get(name)
        row[name] = float(value) if name in NUMERIC_FEATURES else str(value)
    return pd.DataFrame([row], columns=names)


def risk_score(values: Mapping[str, Any], delay_probability: float, rule: Mapping[str, Any] | None = None) -> float:
    """Apply the transparent risk rule to one project."""
    spec = rule or RISK_RULE
    project_type = str(values.get("project_type", ""))
    score = float(spec.get("intercept", 0.0))
    score += float(spec["type_weights"].get(project_type, spec["default_type_weight"]))
    score += float(spec["delay_probability_weight"]) * float(delay_probability)
    for name, weight in spec["deficits"].items():
        current = float(values.get(name, FEATURE_DEFAULTS.get(name, 100)))
        score += float(weight) * (100.0 - current)
    for name, weight in spec["levels"].items():
        score += float(weight) * float(values.get(name, FEATURE_DEFAULTS.get(name, 0)))
    return round(float(np.clip(score, 0, 100)), 2)


def risk_score_frame(frame: pd.DataFrame, delay_probability: np.ndarray, rule: Mapping[str, Any] | None = None) -> np.ndarray:
    """Vectorised risk rule used to report the rule's fit during training."""
    spec = rule or RISK_RULE
    weights = frame["project_type"].map(spec["type_weights"]).fillna(spec["default_type_weight"]).to_numpy(dtype=float)
    score = float(spec.get("intercept", 0.0)) + weights + float(spec["delay_probability_weight"]) * np.asarray(delay_probability, dtype=float)
    for name, weight in spec["deficits"].items():
        score = score + float(weight) * (100.0 - frame[name].to_numpy(dtype=float))
    for name, weight in spec["levels"].items():
        score = score + float(weight) * frame[name].to_numpy(dtype=float)
    return np.clip(score, 0, 100)


def risk_category(score: float) -> str:
    return "Low" if score <= 30 else "Medium" if score <= 60 else "High"
