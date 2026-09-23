"""Prediction and SHAP explanation service for land-acquisition projects."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd


FEATURES = ["project_type", "land_area", "number_of_owners", "compensation_percentage", "legal_disputes", "land_possession_percentage", "rehabilitation_percentage"]


class ModelUnavailableError(RuntimeError):
    pass


def model_path(name: str) -> Path:
    default = Path(__file__).resolve().parents[3] / "ml" / "models" / name
    return Path(os.getenv(f"ML_{name.upper().replace('.', '_')}_PATH", default))


class MLService:
    def __init__(self) -> None:
        delay_path = model_path("delay_model.pkl")
        explainer_path = model_path("delay_model_shap.pkl")
        if not delay_path.exists() or not explainer_path.exists():
            raise ModelUnavailableError("Train model first: run python ml/train_model.py")
        self.pipeline = joblib.load(delay_path)
        self.explainer = joblib.load(explainer_path)

    @staticmethod
    def _frame(project_features: Mapping[str, Any]) -> pd.DataFrame:
        missing = [name for name in FEATURES if name not in project_features]
        if missing:
            raise ValueError(f"Missing prediction features: {', '.join(missing)}")
        return pd.DataFrame([{name: project_features[name] for name in FEATURES}])

    @staticmethod
    def _risk_score(frame: pd.DataFrame, delay_probability: float) -> float:
        type_weight = {"Metro Rail": 12, "Industrial Corridor": 11, "Airport Expansion": 10, "Railway Corridor": 8, "Logistics Park": 7}
        row = frame.iloc[0]
        compensation = float(row.compensation_percentage)
        legal_disputes = float(row.legal_disputes)
        possession = float(row.land_possession_percentage)
        rehabilitation = float(row.rehabilitation_percentage)
        score = type_weight.get(row.project_type, 5) + 15 * delay_probability + 0.34 * (100 - compensation) + 4.2 * legal_disputes + 0.17 * (100 - possession) + 0.22 * (100 - rehabilitation)
        return round(float(np.clip(score, 0, 100)), 2)

    def predict(self, project_features: Mapping[str, Any]) -> dict[str, Any]:
        frame = self._frame(project_features)
        delay_probability = round(float(np.clip(self.pipeline.predict(frame)[0], 0, 1)), 4)
        risk_score = self._risk_score(frame, delay_probability)
        risk_category = "Low" if risk_score <= 30 else "Medium" if risk_score <= 60 else "High"
        return {"risk_score": risk_score, "delay_probability": delay_probability, "risk_category": risk_category}

    def explain(self, project_features: Mapping[str, Any]) -> dict[str, Any]:
        frame = self._frame(project_features)
        transformed = self.pipeline.named_steps["preprocessor"].transform(frame)
        values = np.asarray(self.explainer.shap_values(transformed)).reshape(-1)
        names = self.pipeline.named_steps["preprocessor"].get_feature_names_out()
        ranked = sorted(zip(names, values), key=lambda item: abs(item[1]), reverse=True)[:5]
        factors = [{"feature": name.replace("categorical__", "").replace("numeric__", ""), "shap_value": round(float(value), 5), "impact": "increases delay risk" if value > 0 else "reduces delay risk"} for name, value in ranked]
        recommendations = []
        row = frame.iloc[0]
        if row.compensation_percentage < 60:
            recommendations.append("Prioritize compensation disbursement")
        if row.legal_disputes >= 3:
            recommendations.append("Escalate legal dispute resolution")
        if row.land_possession_percentage < 60:
            recommendations.append("Accelerate land-possession coordination")
        if row.rehabilitation_percentage < 60:
            recommendations.append("Strengthen rehabilitation delivery")
        if not recommendations:
            recommendations.append("Maintain periodic acquisition risk review")
        return {"top_contributing_factors": factors, "recommendations": recommendations}


@lru_cache
def get_ml_service() -> MLService:
    return MLService()
