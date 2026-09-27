"""Model serving behaviour: prediction, stage forecasts and explainability."""
from __future__ import annotations

import pytest


def test_model_card_declares_the_feature_contract(ml_service):
    info = ml_service.model_info()
    assert info["version"]
    assert info["algorithm"] == "XGBClassifier"
    # Every declared feature must be scorable, and every stage accounted for.
    assert set(ml_service.features) >= {"compensation_percentage", "legal_disputes", "lifecycle_stage"}
    assert ml_service.stages, "the bundle must declare lifecycle stages"


def test_prediction_shape_and_bounds(ml_service, high_risk):
    prediction = ml_service.predict(high_risk)
    assert 0.0 <= prediction["delay_probability"] <= 1.0
    assert 0.0 <= prediction["risk_score"] <= 100.0
    assert prediction["risk_category"] in {"Low", "Medium", "High"}
    assert prediction["model_version"] == ml_service.version
    assert set(prediction["lifecycle_risks"]) == set(ml_service.stages)
    for probability in prediction["lifecycle_risks"].values():
        assert 0.0 <= probability <= 1.0


def test_risk_category_follows_the_published_bands(ml_service):
    assert ml_service.risk_category(12.0) == "Low"
    assert ml_service.risk_category(30.0) == "Low"
    assert ml_service.risk_category(30.01) == "Medium"
    assert ml_service.risk_category(60.0) == "Medium"
    assert ml_service.risk_category(60.01) == "High"


def test_worse_project_scores_higher_than_a_healthy_one(ml_service, high_risk, low_risk):
    bad = ml_service.predict(high_risk)
    good = ml_service.predict(low_risk)
    assert bad["risk_score"] > good["risk_score"]
    assert bad["delay_probability"] > good["delay_probability"]


def test_risk_rule_responds_to_each_deficit(ml_service, low_risk):
    """Every deficit coefficient in the rule must actually move the score."""
    baseline = ml_service.risk_score(low_risk, 0.2)
    for feature in ml_service.risk_rule["deficits"]:
        worse = dict(low_risk)
        worse[feature] = max(0.0, float(low_risk[feature]) - 30.0)
        assert ml_service.risk_score(worse, 0.2) > baseline, feature


def test_risk_rule_is_bounded(ml_service, high_risk):
    catastrophic = dict(high_risk, legal_disputes=99, approval_timeline_days=5000,
                        compensation_percentage=0, land_possession_percentage=0,
                        rehabilitation_percentage=0, documentation_completeness=0,
                        stakeholder_responsiveness=0, historical_performance_score=0)
    assert ml_service.risk_score(catastrophic, 1.0) == 100.0


def test_explanation_attributes_risk_to_named_drivers(ml_service, high_risk):
    explanation = ml_service.explain(high_risk)
    assert explanation["model_version"] == ml_service.version
    assert explanation["top_contributing_factors"], "SHAP attribution must not be empty"
    for factor in explanation["top_contributing_factors"]:
        assert factor["feature"] in ml_service.features
        assert factor["impact"] in {"increases delay risk", "reduces delay risk"}
    shares = [driver["share"] for driver in explanation["delay_drivers"]]
    assert shares == sorted(shares, reverse=True), "drivers must be ranked"
    assert pytest.approx(sum(shares), abs=0.01) == 1.0
    assert explanation["global_importance"], "the model card must expose global importance"


def test_stage_explanation_uses_the_stage_model(ml_service, high_risk):
    stage = ml_service.stages[0]
    if stage not in ml_service.stage_explainers:
        pytest.skip(f"stage {stage} has no trained explainer")
    explanation = ml_service.explain(high_risk, stage=stage)
    assert explanation["stage"] == stage
    assert 0.0 <= explanation["delay_probability"] <= 1.0


def test_unknown_stage_is_rejected(ml_service, high_risk):
    with pytest.raises(ValueError):
        ml_service.explain(high_risk, stage="Not a stage")


def test_recommendations_are_ranked_and_actionable(ml_service, high_risk):
    recommendations = ml_service.explain(high_risk)["recommendations"]
    assert recommendations
    reductions = [item["expected_reduction"] for item in recommendations]
    assert reductions == sorted(reductions, reverse=True)
    top = recommendations[0]
    assert top["feature"] in ml_service.features
    assert top["current_value"] != top["target_value"]
    assert top["driver"]


def test_healthy_project_gets_a_monitoring_recommendation(ml_service, low_risk):
    recommendations = ml_service.explain(low_risk)["recommendations"]
    assert len(recommendations) == 1
    assert recommendations[0]["feature"] is None


def test_missing_features_fall_back_to_documented_defaults(ml_service):
    minimal = {"project_type": "National Highway", "compensation_percentage": 10.0}
    prediction = ml_service.predict(minimal)
    assert 0.0 <= prediction["delay_probability"] <= 1.0
