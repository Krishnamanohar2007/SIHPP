"""Train delay model and persist matching SHAP TreeExplainer artifacts."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "projects.csv"
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "delay_model.pkl"
EXPLAINER_PATH = MODEL_DIR / "delay_model_shap.pkl"
FEATURES = ["project_type", "land_area", "number_of_owners", "compensation_percentage", "legal_disputes", "land_possession_percentage", "rehabilitation_percentage"]
CATEGORICAL_FEATURES = ["project_type"]
NUMERIC_FEATURES = [feature for feature in FEATURES if feature not in CATEGORICAL_FEATURES]


def derive_risk_score(features: pd.DataFrame, delay_probability: np.ndarray) -> np.ndarray:
    """Transparent risk rule; higher acquisition gaps and delay increase risk."""
    type_weight = {"Metro Rail": 12, "Industrial Corridor": 11, "Airport Expansion": 10, "Railway Corridor": 8, "Logistics Park": 7}
    project_weight = features["project_type"].map(type_weight).fillna(5).to_numpy()
    score = (project_weight + 15 * delay_probability + 0.34 * (100 - features["compensation_percentage"].to_numpy()) + 4.2 * features["legal_disputes"].to_numpy() + 0.17 * (100 - features["land_possession_percentage"].to_numpy()) + 0.22 * (100 - features["rehabilitation_percentage"].to_numpy()))
    return np.clip(score, 0, 100)


def main() -> None:
    frame = pd.read_csv(DATA_PATH)
    x_train, x_test, y_train, y_test = train_test_split(frame[FEATURES], frame["delay_probability"], test_size=0.2, random_state=26017)
    preprocessor = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ("numeric", "passthrough", NUMERIC_FEATURES),
    ])
    regressor = XGBRegressor(objective="reg:squarederror", n_estimators=250, max_depth=4, learning_rate=0.04, subsample=0.85, colsample_bytree=0.85, random_state=26017, n_jobs=1)
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", regressor)])
    pipeline.fit(x_train, y_train)
    prediction = np.clip(pipeline.predict(x_test), 0, 1)
    rmse = float(np.sqrt(mean_squared_error(y_test, prediction)))
    high_delay = y_test >= 0.5
    auc = float(roc_auc_score(high_delay, prediction)) if high_delay.nunique() == 2 else None
    risk_prediction = derive_risk_score(x_test, prediction)
    risk_rmse = float(np.sqrt(mean_squared_error(frame.loc[x_test.index, "risk_score"], risk_prediction)))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    explainer = shap.TreeExplainer(pipeline.named_steps["model"])
    joblib.dump(explainer, EXPLAINER_PATH)
    print({"delay_rmse": round(rmse, 4), "delay_auc": None if auc is None else round(auc, 4), "risk_rule_rmse": round(risk_rmse, 4), "model": str(MODEL_PATH), "explainer": str(EXPLAINER_PATH)})


if __name__ == "__main__":
    main()
