"""Train the land-acquisition delay models and write a versioned model bundle.

One run produces:

* ``delay_model.pkl``            portfolio delay classifier (probability of delay)
* ``delay_model_shap.pkl``       SHAP TreeExplainer for the portfolio model
* ``stage_<slug>.pkl``           one delay classifier per lifecycle stage
* ``stage_<slug>_shap.pkl``      matching SHAP explainer per stage
* ``model_card.json``            feature contract, risk rule, metrics, global importance

Artifacts are written to a versioned directory (``ml/models/<version>/``) and the
bundle is also mirrored into ``ml/models/`` so an existing deployment keeps
working. ``ml/models/active.json`` records which version serving should load.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import (  # noqa: E402  (path bootstrap above is intentional)
    CATEGORICAL_FEATURES,
    DRIVER_TAXONOMY,
    FEATURE_DEFAULTS,
    FEATURE_LABELS,
    FEATURES,
    NUMERIC_FEATURES,
    PORTFOLIO_LABEL,
    RISK_RULE,
    STAGE_LABELS,
    STAGES,
    risk_score_frame,
    stage_slug,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "training_history.csv"
PROJECTS_PATH = ROOT / "data" / "projects.csv"
# ML_MODELS_DIR lets a deployment - or a test run - put bundles somewhere else.
MODEL_ROOT = Path(os.getenv("ML_MODELS_DIR", Path(__file__).resolve().parent / "models"))
ACTIVE_POINTER = MODEL_ROOT / "active.json"
RANDOM_STATE = 26017


class InsufficientLabelsError(RuntimeError):
    """Raised when a target has too few labelled rows to train on."""


def classifier() -> XGBClassifier:
    return XGBClassifier(
        objective="binary:logistic", n_estimators=280, max_depth=4, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85, reg_lambda=1.2, min_child_weight=3,
        eval_metric="logloss", random_state=RANDOM_STATE, n_jobs=1,
    )


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ("numeric", "passthrough", NUMERIC_FEATURES),
    ])
    return Pipeline([("preprocessor", preprocessor), ("model", classifier())])


def classification_metrics(truth: pd.Series, probability: np.ndarray) -> dict[str, Any]:
    prediction = (probability >= 0.5).astype(int)
    single_class = truth.nunique() < 2
    return {
        "rows": int(len(truth)),
        "positive_rate": round(float(truth.mean()), 4),
        "accuracy": round(float(accuracy_score(truth, prediction)), 4),
        "f1": round(float(f1_score(truth, prediction, zero_division=0)), 4),
        "roc_auc": None if single_class else round(float(roc_auc_score(truth, probability)), 4),
        "brier": round(float(brier_score_loss(truth, probability)), 4),
    }


def global_importance(pipeline: Pipeline, limit: int = 15) -> list[dict[str, Any]]:
    """Gain-based importance, mapped back to encoded feature names."""
    names = list(pipeline.named_steps["preprocessor"].get_feature_names_out())
    gains = np.asarray(pipeline.named_steps["model"].feature_importances_, dtype=float)
    ranked = sorted(zip(names, gains), key=lambda item: item[1], reverse=True)[:limit]
    total = float(gains.sum()) or 1.0
    return [{"feature": name, "importance": round(float(value), 6), "share": round(float(value) / total, 4)} for name, value in ranked]


def labelled(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """Rows usable for one target: the label present, and no missing features.

    A recorded project outcome supplies the portfolio label only, so those rows
    carry no stage labels. Dropping them per target is what lets one table train
    every model without inventing labels it does not have.
    """
    usable = frame[frame[label].notna()]
    return usable.dropna(subset=FEATURES)


MIN_TRAINING_ROWS = 40


def train_target(frame: pd.DataFrame, label: str, reference: str | None = None) -> tuple[Pipeline, dict[str, Any], Any]:
    """Fit one delay classifier plus its SHAP explainer."""
    frame = labelled(frame, label)
    if len(frame) < MIN_TRAINING_ROWS:
        raise InsufficientLabelsError(f"only {len(frame)} labelled rows for '{label}', need {MIN_TRAINING_ROWS}")
    target = frame[label].astype(int)
    stratify = target if target.nunique() == 2 else None
    columns = FEATURES + ([reference] if reference and reference in frame.columns else [])
    x_train, x_test, y_train, y_test = train_test_split(
        frame[columns], target, test_size=0.2, random_state=RANDOM_STATE, stratify=stratify,
    )
    pipeline = build_pipeline()
    pipeline.fit(x_train[FEATURES], y_train)
    probability = pipeline.predict_proba(x_test[FEATURES])[:, 1]
    metrics = classification_metrics(y_test, probability)
    if reference and reference in x_test.columns and y_test.nunique() == 2:
        # Outcomes are sampled from a probability, so no model can exceed the AUC
        # of that probability itself. Reporting it stops the score being read as
        # a failure when it is simply close to the achievable ceiling.
        metrics["reference_roc_auc"] = round(float(roc_auc_score(y_test, x_test[reference].astype(float))), 4)
    metrics["importance"] = global_importance(pipeline)
    explainer = shap.TreeExplainer(pipeline.named_steps["model"])
    return pipeline, metrics, explainer


def train_bundle(frame: pd.DataFrame, version: str, source: str, mirror: bool = True) -> dict[str, Any]:
    missing = [name for name in [*FEATURES, PORTFOLIO_LABEL] if name not in frame.columns]
    if missing:
        raise SystemExit(f"Training data is missing columns: {', '.join(missing)}")

    version_dir = MODEL_ROOT / version
    version_dir.mkdir(parents=True, exist_ok=True)

    pipeline, metrics, explainer = train_target(frame, PORTFOLIO_LABEL, reference="delay_probability")
    joblib.dump(pipeline, version_dir / "delay_model.pkl")
    joblib.dump(explainer, version_dir / "delay_model_shap.pkl")

    stage_metrics: dict[str, Any] = {}
    for stage in STAGES:
        label = STAGE_LABELS[stage]
        if label not in frame.columns or labelled(frame, label)[label].nunique() < 2:
            # A stage without both outcomes cannot be learned; serving falls back
            # to the portfolio probability for that stage and says so.
            stage_metrics[stage] = {"trained": False, "reason": "insufficient labelled outcomes"}
            continue
        try:
            stage_pipeline, stage_report, stage_explainer = train_target(frame, label)
        except InsufficientLabelsError as error:
            stage_metrics[stage] = {"trained": False, "reason": str(error)}
            continue
        slug = stage_slug(stage)
        joblib.dump(stage_pipeline, version_dir / f"stage_{slug}.pkl")
        joblib.dump(stage_explainer, version_dir / f"stage_{slug}_shap.pkl")
        stage_report["trained"] = True
        stage_metrics[stage] = stage_report

    # Fit quality of the transparent risk rule against the stored risk scores,
    # reported so reviewers can see the rule is not silently drifting.
    risk_rule_rmse = None
    if "risk_score" in frame.columns:
        complete = frame.dropna(subset=[*FEATURES, "risk_score"])
        if not complete.empty:
            probability = pipeline.predict_proba(complete[FEATURES])[:, 1]
            derived = risk_score_frame(complete[FEATURES], probability)
            risk_rule_rmse = round(float(np.sqrt(mean_squared_error(complete["risk_score"].astype(float), derived))), 4)

    card = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "XGBClassifier",
        "training_source": source,
        "training_rows": int(len(frame)),
        "features": FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "stages": STAGES,
        "stage_files": {stage: f"stage_{stage_slug(stage)}.pkl" for stage in STAGES},
        "risk_rule": RISK_RULE,
        "driver_taxonomy": DRIVER_TAXONOMY,
        "feature_labels": FEATURE_LABELS,
        "feature_defaults": FEATURE_DEFAULTS,
        "metrics": {"portfolio": metrics, "stages": stage_metrics, "risk_rule_rmse": risk_rule_rmse},
    }
    (version_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    if mirror:
        # Mirror into the flat location (kept for deployments that load it
        # directly) and point serving at this version.
        for artifact in version_dir.iterdir():
            if artifact.is_file():
                (MODEL_ROOT / artifact.name).write_bytes(artifact.read_bytes())
        ACTIVE_POINTER.write_text(json.dumps({"version": version, "path": str(version_dir)}, indent=2), encoding="utf-8")
    return card


def load_training_frame() -> tuple[pd.DataFrame, str]:
    """Prefer the labelled history; fall back to deriving labels from the register."""
    if HISTORY_PATH.exists():
        return pd.read_csv(HISTORY_PATH), f"file:{HISTORY_PATH.name}"
    if not PROJECTS_PATH.exists():
        raise SystemExit(f"No training data. Run python data/generate_synthetic_projects.py")
    frame = pd.read_csv(PROJECTS_PATH)
    # Without recorded outcomes, threshold the stored delay probability so a
    # first model can still be produced from the operational register alone.
    frame[PORTFOLIO_LABEL] = (frame["delay_probability"].astype(float) >= 0.5).astype(int)
    return frame, f"file:{PROJECTS_PATH.name} (thresholded)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train land-acquisition delay models")
    parser.add_argument("--version", default=None, help="Version label (default: utc timestamp)")
    args = parser.parse_args()
    version = args.version or datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    frame, source = load_training_frame()
    card = train_bundle(frame, version, source)
    print(json.dumps({"version": card["version"], "rows": card["training_rows"], "metrics": card["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
