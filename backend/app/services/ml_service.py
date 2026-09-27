"""Prediction, stage-wise forecasting and explainability for land-acquisition projects.

The service is driven entirely by ``model_card.json`` inside the active model
bundle: the feature contract, the transparent risk rule, the driver taxonomy and
the recorded metrics all come from the card. Retraining therefore changes serving
behaviour without a code change, and every response carries the model version
that produced it.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd


class ModelUnavailableError(RuntimeError):
    """Raised when no usable model bundle is present on disk."""


def models_root() -> Path:
    """Directory that holds model bundles and the active-version pointer."""
    default = Path(__file__).resolve().parents[3] / "ml" / "models"
    return Path(os.getenv("ML_MODELS_DIR", default))


def active_bundle_dir() -> Path:
    """Resolve the bundle to serve: explicit override, active pointer, or flat dir."""
    override = os.getenv("ML_MODEL_DIR")
    if override:
        return Path(override)
    root = models_root()
    pointer = root / "active.json"
    if pointer.is_file():
        try:
            version = json.loads(pointer.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError):
            version = None
        if version and (root / version / "model_card.json").is_file():
            return root / version
    return root


# Actions the platform can recommend, with the counterfactual improvement used to
# estimate each action's effect on the delay probability.
ACTIONS: tuple[dict[str, Any], ...] = (
    {"feature": "compensation_percentage", "delta": 25.0, "cap": 100.0, "threshold": 90.0,
     "action": "Accelerate compensation disbursement", "detail": "Release pending awards to bring disbursement up by 25 percentage points."},
    {"feature": "land_possession_percentage", "delta": 25.0, "cap": 100.0, "threshold": 90.0,
     "action": "Accelerate possession handover", "detail": "Complete joint measurement and handover for the remaining parcels."},
    {"feature": "rehabilitation_percentage", "delta": 25.0, "cap": 100.0, "threshold": 90.0,
     "action": "Advance rehabilitation and resettlement", "detail": "Close pending R&R entitlements for displaced families."},
    {"feature": "documentation_completeness", "delta": 20.0, "cap": 100.0, "threshold": 95.0,
     "action": "Complete acquisition documentation", "detail": "Resolve missing title records, mutation entries and award files."},
    {"feature": "stakeholder_responsiveness", "delta": 20.0, "cap": 100.0, "threshold": 90.0,
     "action": "Escalate inter-departmental coordination", "detail": "Set a fixed response window for line departments and track it weekly."},
    {"feature": "legal_disputes", "delta": -2.0, "floor": 0.0, "threshold": 1.0, "invert": True,
     "action": "Resolve pending litigation", "detail": "Refer disputes to the authority for time-bound adjudication or settlement."},
    {"feature": "approval_timeline_days", "delta": -90.0, "floor": 0.0, "threshold": 60.0, "invert": True,
     "action": "Clear pending administrative approvals", "detail": "Escalate files that are waiting beyond the sanctioned approval window."},
)


class MLService:
    """Loads one model bundle and serves predictions, stages and explanations."""

    def __init__(self, bundle_dir: Path | None = None) -> None:
        self.directory = Path(bundle_dir or active_bundle_dir())
        card_path = self.directory / "model_card.json"
        model_path = self.directory / "delay_model.pkl"
        if not card_path.is_file() or not model_path.is_file():
            raise ModelUnavailableError(
                f"No model bundle in {self.directory}. Train first: python ml/train_model.py"
            )
        try:
            self.card: dict[str, Any] = json.loads(card_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ModelUnavailableError(f"Corrupt model card in {self.directory}") from error

        self.version: str = self.card.get("version", self.directory.name)
        self.features: list[str] = list(self.card["features"])
        self.numeric_features: set[str] = set(self.card.get("numeric_features", []))
        self.risk_rule: dict[str, Any] = self.card["risk_rule"]
        self.driver_taxonomy: dict[str, str] = self.card.get("driver_taxonomy", {})
        self.feature_labels: dict[str, str] = self.card.get("feature_labels", {})
        self.feature_defaults: dict[str, Any] = self.card.get("feature_defaults", {})
        self.metrics: dict[str, Any] = self.card.get("metrics", {})
        self.stages: list[str] = list(self.card.get("stages", []))

        self.pipeline = joblib.load(model_path)
        explainer_path = self.directory / "delay_model_shap.pkl"
        self.explainer = joblib.load(explainer_path) if explainer_path.is_file() else None

        # Per-stage bundles are optional: a stage without both outcomes in the
        # training data has no model and is reported as untrained.
        self.stage_models: dict[str, Any] = {}
        self.stage_explainers: dict[str, Any] = {}
        for stage, filename in self.card.get("stage_files", {}).items():
            path = self.directory / filename
            if path.is_file():
                self.stage_models[stage] = joblib.load(path)
                shap_path = self.directory / filename.replace(".pkl", "_shap.pkl")
                if shap_path.is_file():
                    self.stage_explainers[stage] = joblib.load(shap_path)

    # ---------------------------------------------------------------- helpers
    def _frame(self, values: Mapping[str, Any]) -> pd.DataFrame:
        row: dict[str, Any] = {}
        for name in self.features:
            value = values.get(name, self.feature_defaults.get(name))
            if value is None:
                value = self.feature_defaults.get(name)
            if value is None:
                raise ValueError(f"Missing prediction feature: {name}")
            row[name] = float(value) if name in self.numeric_features else str(value)
        return pd.DataFrame([row], columns=self.features)

    def _probability(self, pipeline: Any, frame: pd.DataFrame) -> float:
        return float(np.clip(pipeline.predict_proba(frame)[0][1], 0.0, 1.0))

    def risk_score(self, values: Mapping[str, Any], delay_probability: float) -> float:
        """Transparent risk rule, applied with the coefficients in the model card."""
        rule = self.risk_rule
        project_type = str(values.get("project_type", ""))
        score = float(rule.get("intercept", 0.0))
        score += float(rule["type_weights"].get(project_type, rule["default_type_weight"]))
        score += float(rule["delay_probability_weight"]) * float(delay_probability)
        for name, weight in rule["deficits"].items():
            current = float(values.get(name, self.feature_defaults.get(name, 100)) or 0)
            score += float(weight) * (100.0 - current)
        for name, weight in rule["levels"].items():
            score += float(weight) * float(values.get(name, self.feature_defaults.get(name, 0)) or 0)
        return round(float(np.clip(score, 0, 100)), 2)

    @staticmethod
    def risk_category(score: float) -> str:
        return "Low" if score <= 30 else "Medium" if score <= 60 else "High"

    def label(self, feature: str) -> str:
        return self.feature_labels.get(feature, feature.replace("_", " ").capitalize())

    def driver(self, feature: str) -> str:
        return self.driver_taxonomy.get(feature, "Other factors")

    def _base_feature(self, encoded_name: str) -> str:
        """Map an encoded column such as ``categorical__land_type_Barren`` back."""
        name = encoded_name.split("__", 1)[-1]
        if encoded_name.startswith("categorical__"):
            for feature in self.features:
                if name == feature or name.startswith(f"{feature}_"):
                    return feature
        return name

    # ------------------------------------------------------------- prediction
    def predict(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Portfolio delay probability, risk score and per-stage probabilities."""
        frame = self._frame(values)
        delay_probability = round(self._probability(self.pipeline, frame), 4)
        score = self.risk_score(values, delay_probability)
        stage_risks: dict[str, float] = {}
        stage_status: dict[str, str] = {}
        for stage in self.stages:
            model = self.stage_models.get(stage)
            if model is None:
                stage_risks[stage] = delay_probability
                stage_status[stage] = "fallback: portfolio model"
                continue
            stage_risks[stage] = round(self._probability(model, frame), 4)
            stage_status[stage] = "modelled"
        return {
            "risk_score": score,
            "delay_probability": delay_probability,
            "risk_category": self.risk_category(score),
            "lifecycle_risks": stage_risks,
            "lifecycle_risk_sources": stage_status,
            "model_version": self.version,
        }

    # ---------------------------------------------------------- explainability
    def _shap_contributions(self, explainer: Any, frame: pd.DataFrame) -> tuple[list[tuple[str, float]], float]:
        """Return per-encoded-column SHAP values plus the model's base value."""
        transformed = self.pipeline.named_steps["preprocessor"].transform(frame)
        raw = explainer.shap_values(transformed)
        values = np.asarray(raw, dtype=float).reshape(-1)
        names = list(self.pipeline.named_steps["preprocessor"].get_feature_names_out())
        expected = explainer.expected_value
        base = float(np.asarray(expected, dtype=float).reshape(-1)[0]) if expected is not None else 0.0
        return list(zip(names, values[: len(names)])), base

    def _rolled_up(self, contributions: list[tuple[str, float]]) -> dict[str, float]:
        """Sum encoded contributions back onto their source feature."""
        totals: dict[str, float] = {}
        for encoded, value in contributions:
            feature = self._base_feature(encoded)
            totals[feature] = totals.get(feature, 0.0) + float(value)
        return totals

    def recommendations(self, values: Mapping[str, Any], delay_probability: float) -> list[dict[str, Any]]:
        """Rank corrective actions by their simulated effect on delay probability."""
        ranked: list[dict[str, Any]] = []
        for action in ACTIONS:
            feature = action["feature"]
            if feature not in self.features:
                continue
            current = float(values.get(feature, self.feature_defaults.get(feature, 0)) or 0)
            # Skip actions that are already done, or already at the safe level.
            if action.get("invert"):
                if current <= action["threshold"]:
                    continue
                improved = max(action["floor"], current + action["delta"])
            else:
                if current >= action["threshold"]:
                    continue
                improved = min(action["cap"], current + action["delta"])
            candidate = dict(values)
            candidate[feature] = improved
            new_probability = round(self._probability(self.pipeline, self._frame(candidate)), 4)
            reduction = round(delay_probability - new_probability, 4)
            ranked.append({
                "action": action["action"],
                "detail": action["detail"],
                "driver": self.driver(feature),
                "feature": feature,
                "feature_label": self.label(feature),
                "current_value": round(current, 2),
                "target_value": round(float(improved), 2),
                "projected_delay_probability": new_probability,
                "expected_reduction": reduction,
                "priority": ("High" if reduction >= 0.05 else "Medium" if reduction >= 0.015
                             else "Low" if reduction > 0.0 else "No modelled effect"),
            })
        ranked.sort(key=lambda item: item["expected_reduction"], reverse=True)
        if not ranked:
            ranked.append({
                "action": "Maintain periodic acquisition risk review",
                "detail": "No parameter is currently outside its safe operating band.",
                "driver": "Monitoring", "feature": None, "feature_label": None,
                "current_value": None, "target_value": None,
                "projected_delay_probability": delay_probability, "expected_reduction": 0.0,
                "priority": "Low",
            })
        return ranked

    def explain(self, values: Mapping[str, Any], stage: str | None = None) -> dict[str, Any]:
        """Local SHAP attribution, driver rollup, and ranked recommendations."""
        frame = self._frame(values)
        model = self.stage_models.get(stage) if stage else self.pipeline
        explainer = self.stage_explainers.get(stage) if stage else self.explainer
        if stage and model is None:
            raise ValueError(f"No model trained for stage '{stage}'")
        if explainer is None:
            raise ModelUnavailableError("Model bundle has no SHAP explainer; retrain to produce one")

        delay_probability = round(self._probability(model, frame), 4)
        contributions, base_value = self._shap_contributions(explainer, frame)
        totals = self._rolled_up(contributions)
        ordered = sorted(totals.items(), key=lambda item: abs(item[1]), reverse=True)

        factors = [{
            "feature": feature,
            "feature_label": self.label(feature),
            "driver": self.driver(feature),
            "value": values.get(feature),
            "shap_value": round(float(value), 5),
            "impact": "increases delay risk" if value > 0 else "reduces delay risk",
        } for feature, value in ordered[:8]]

        # Driver rollup: only positive contributions, since policymakers act on
        # what is pushing risk up, expressed as a share of the total push.
        driver_totals: dict[str, float] = {}
        for feature, value in totals.items():
            if value > 0:
                driver_totals[self.driver(feature)] = driver_totals.get(self.driver(feature), 0.0) + float(value)
        push = sum(driver_totals.values()) or 1.0
        drivers = sorted(
            ({"driver": name, "contribution": round(value, 5), "share": round(value / push, 4)} for name, value in driver_totals.items()),
            key=lambda item: item["contribution"], reverse=True,
        )

        return {
            "model_version": self.version,
            "stage": stage,
            "delay_probability": delay_probability,
            "base_value": round(base_value, 5),
            "top_contributing_factors": factors,
            "delay_drivers": drivers,
            "waterfall": [{"feature": self.label(feature), "shap_value": round(float(value), 5)} for feature, value in ordered],
            "global_importance": (self.metrics.get("portfolio") or {}).get("importance", []),
            "recommendations": self.recommendations(values, delay_probability),
        }

    def model_info(self) -> dict[str, Any]:
        """Model card view for the transparency panel and the models API."""
        return {
            "version": self.version,
            "algorithm": self.card.get("algorithm"),
            "trained_at": self.card.get("trained_at"),
            "training_rows": self.card.get("training_rows"),
            "training_source": self.card.get("training_source"),
            "features": self.features,
            "stages": self.stages,
            "trained_stages": sorted(self.stage_models),
            "metrics": self.metrics,
            "risk_rule": self.risk_rule,
            "artifact_path": str(self.directory),
        }


_lock = threading.Lock()
_service: MLService | None = None


def get_ml_service() -> MLService:
    """Process-wide cached service. Thread-safe so the scheduler can share it."""
    global _service
    with _lock:
        if _service is None:
            _service = MLService()
        return _service


def reload_ml_service() -> MLService:
    """Drop the cached service so a newly activated model version is picked up."""
    global _service
    with _lock:
        _service = MLService()
        return _service
