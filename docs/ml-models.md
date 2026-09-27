# Prediction Models

## What is predicted

| Target | Model | Output |
| --- | --- | --- |
| Portfolio delay | `XGBClassifier` on `delayed` | `delay_probability` = P(project is delayed) |
| Notification delay | `XGBClassifier` on `delayed_notification` | stage probability |
| Compensation delay | `XGBClassifier` on `delayed_compensation` | stage probability |
| Possession delay | `XGBClassifier` on `delayed_possession` | stage probability |
| Rehabilitation delay | `XGBClassifier` on `delayed_rehabilitation` | stage probability |
| Legal resolution delay | `XGBClassifier` on `delayed_legal_resolution` | stage probability |

Stage probabilities come from six independent models, not from one model with
offsets applied. A stage with too few labelled outcomes is not trained, and the
API reports `"fallback: portfolio model"` for it instead of presenting a guess as
a stage prediction.

`risk_score` is deliberately **not** a model output. It is a published linear rule
whose coefficients live in `ml/features.py` and are copied into every model card,
so a score can always be recomputed by hand from the project's own fields:

```
risk_score = clip(
    type_weight[project_type]
  + 12.0 × delay_probability
  + 0.30 × (100 − compensation_percentage)
  + 0.15 × (100 − land_possession_percentage)
  + 0.19 × (100 − rehabilitation_percentage)
  + 0.11 × (100 − documentation_completeness)
  + 0.09 × (100 − stakeholder_responsiveness)
  + 0.08 × (100 − historical_performance_score)
  + 3.80 × legal_disputes
  + 0.010 × approval_timeline_days,
    0, 100)
```

Bands: `≤30` Low, `≤60` Medium, otherwise High. Keeping the score rule-based means
an official can be told exactly why a project scores what it scores, while the
probability carries the learned signal.

## Features

Fourteen features, all of them fields officials already maintain.

Categorical: `project_type`, `land_type`, `lifecycle_stage`.

Numeric: `land_area`, `number_of_owners`, `affected_families`,
`approval_timeline_days`, `documentation_completeness`,
`stakeholder_responsiveness`, `historical_performance_score`,
`compensation_percentage`, `legal_disputes`, `land_possession_percentage`,
`rehabilitation_percentage`.

Each feature maps to a delay driver a policymaker can act on, and SHAP
contributions are rolled up onto those drivers:

| Driver | Features |
| --- | --- |
| Pending approvals | `approval_timeline_days`, `lifecycle_stage` |
| Compensation delays | `compensation_percentage` |
| Legal disputes | `legal_disputes` |
| Incomplete documentation | `documentation_completeness` |
| Rehabilitation status | `rehabilitation_percentage`, `affected_families` |
| Possession bottlenecks | `land_possession_percentage` |
| Administrative bottlenecks | `stakeholder_responsiveness`, `historical_performance_score` |
| Project scale / Ownership fragmentation / Project profile | `land_area`, `number_of_owners`, `project_type`, `land_type` |

## Explainability

* **Local**: SHAP `TreeExplainer` per model. Encoded one-hot columns are summed
  back onto their source feature, so `land_type` appears once rather than as five
  fragments. The response includes the model's `base_value` and the full ordered
  waterfall, which is enough to reconstruct the additive explanation.
* **Driver rollup**: only positive contributions, normalised to shares, because
  the operational question is what is pushing risk up.
* **Global**: gain-based importance is computed at training time and stored in the
  model card, so it is served without recomputation.
* **Recommendations**: each candidate action is scored as a counterfactual. The
  action's target value is pushed back through the same model and
  `expected_reduction` is the resulting drop in delay probability. Actions are
  ranked by it, so the ordering is the model's own estimate rather than a fixed
  priority list. A project already inside every safe band gets a single
  monitoring recommendation instead of invented advice.

## Training

```bash
python data/generate_synthetic_projects.py   # writes projects.csv + training_history.csv + seed.sql
python ml/train_model.py --version v1        # writes ml/models/v1/ and points active.json at it
```

`data/training_history.csv` holds every operational column plus the labels:
`delayed`, one `delayed_<stage>` per stage, and the realised schedule
(`expected_completion_days`, `actual_completion_days`, `is_closed`) for projects
that have closed.

Metrics recorded per target: rows, positive rate, accuracy, F1, ROC AUC and Brier
score. The portfolio model also records `reference_roc_auc`: outcomes are sampled
from a probability, so no model can beat the AUC of that probability itself, and
reporting the ceiling stops a fair score being read as a failure.

Measured on the shipped seed data (150-row held-out split):

| Target | ROC AUC | Accuracy | Brier |
| --- | --- | --- | --- |
| Portfolio delay | 0.813 (ceiling 0.828) | 0.740 | 0.183 |
| Notification | 0.688 | 0.627 | 0.226 |
| Compensation | 0.803 | 0.767 | 0.161 |
| Possession | 0.681 | 0.620 | 0.237 |
| Rehabilitation | 0.879 | 0.860 | 0.109 |
| Legal resolution | 0.701 | 0.707 | 0.214 |

The risk rule's RMSE against the stored scores is also recorded, so drift between
the rule and the register is visible rather than silent.

> The shipped data is synthetic. It exercises the full pipeline and must not be
> read as evidence about real districts or real projects.

## Continuous learning

1. An official records a realised schedule: `POST /projects/{id}/outcome`.
2. `POST /models/retrain` merges the seed history with every database row that has
   a recorded outcome. Database rows win on conflict, so a real outcome replaces
   the synthetic row for the same project.
3. A recorded outcome supplies the portfolio label only. Stage labels stay absent
   and those rows are simply excluded from the per-stage models rather than given
   an invented label.
4. The new bundle is registered in `model_versions` with its metrics and activated
   only when its portfolio ROC AUC is at least as good as the active one.
5. `POST /models/{version}/activate` rolls back to any registered version, and
   `POST /models/rescore` refreshes stored risk fields across the register.

Set `RETRAIN_INTERVAL_HOURS` above `0` to run step 2 on a schedule. Retraining
needs at least 40 labelled rows per target and returns 503 with the shortfall
named when it does not have them.

Offline retraining, for a machine with the model directory but no database:

```bash
python ml/retrain.py --extra-csv recorded_outcomes.csv --activate
```

## Serving

`ML_MODELS_DIR` relocates the bundle directory, `ML_MODEL_DIR` pins one exact
bundle, and `active.json` selects the version otherwise. `MLService` is cached per
process and `POST /models/reload` re-reads the bundle without a restart.
