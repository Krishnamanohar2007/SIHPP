# Architecture

## Components

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Client | React 18, Vite, Tailwind, React Query, Plotly, Leaflet | Dashboards, GIS risk map, project register, alert inbox, admin console |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 | Contracts, RBAC, scoping, analytics aggregation, model orchestration |
| Data | PostgreSQL 16 + PostGIS 3.4 | Project register, metric history, alerts, users, audit trail, model registry |
| ML | scikit-learn pipeline + XGBoost + SHAP | Portfolio and per-stage delay classifiers, explanations |
| Scheduling | APScheduler in-process | Risk scan, snapshot capture, optional scheduled retraining |
| Delivery | Docker Compose, nginx | Local and single-host deployment |

## Client surfaces

| Route | Permission | Purpose |
| --- | --- | --- |
| `/dashboard` | `analytics.read` | Indicators, geography trends (state or district), portfolio timeline, stage exposure, driver prevalence, comparative analysis, intervention queue |
| `/map` | `projects.read` | GIS risk map with a project layer and a district concentration layer, filtered by risk band and delay threshold |
| `/projects` | `projects.read` | Filterable register with server-side sorting; detail shows stage risks, attribution, recorded history and outcome entry |
| `/projects/new` | `projects.write` | Guided entry with a live prediction, stage risks and ranked actions before saving |
| `/alerts` | `alerts.read` | Alert inbox with drivers and recommendations; acknowledge, assign and resolve |
| `/models` | `analytics.read` | Model card, per-stage quality, global importance; retrain, activate and re-score for `models.manage` |
| `/audit` | `audit.read` | Filterable audit trail with before/after diffs |
| `/integration` | `integration.manage` | Issue, inspect and revoke API keys |
| `/admin` | `users.review` | Registration review, roles and project assignment |

Navigation is built from the same permission matrix the server enforces
(`frontend/src/permissions.js`), so a role only sees the pages it can use. The
matrix hides controls; it never grants access, which stays a server decision.

Charts use a categorical palette validated for the lightness band, chroma floor,
all-pairs colour-vision separation and contrast against the paper surface
(`frontend/src/theme.js`). Risk colours are reserved for risk bands and are never
reused as series colours, every chart ships an equivalent table view, and no chart
carries meaning by colour alone.

## Request path

```
browser ──JWT──▶ FastAPI router ──▶ role scope (SQL) ──▶ PostGIS
                      │
                      ├──▶ MLService (active bundle: model + SHAP + model card)
                      └──▶ audit_log (every state change)

external system ──X-API-Key──▶ /integration/v1/* ──▶ key scope (SQL) ──▶ PostGIS
```

## Prediction flow

1. A project is created, updated or synced.
2. `services/scoring.py` calls the active model and writes `risk_score`,
   `delay_probability` and `risk_category` onto the row. A client cannot assert
   these values; they are always derived.
3. The same call appends a `project_snapshots` row, which is what the timeline and
   comparative analytics read.
4. The scheduled scan re-scores the whole register, snapshots it, and raises one
   alert per project above `NOTIFICATION_RISK_THRESHOLD`, carrying its SHAP delay
   drivers and ranked corrective actions.

## Model contract

Serving is driven by `model_card.json` inside the active bundle, never by
hard-coded constants: the feature list, the transparent risk-score rule, the
driver taxonomy and the recorded metrics all live in the card. Retraining changes
behaviour without a code change, and every prediction response carries the
`model_version` that produced it.

Bundle layout under `ml/models/`:

```
ml/models/
  active.json                  # {"version": "...", "path": "..."} - what serving loads
  <version>/
    delay_model.pkl            # portfolio delay classifier
    delay_model_shap.pkl       # SHAP TreeExplainer
    stage_<slug>.pkl           # one classifier per lifecycle stage
    stage_<slug>_shap.pkl
    model_card.json            # feature contract, risk rule, metrics, importance
```

`ML_MODEL_DIR` overrides the whole resolution and pins one bundle.

## Continuous learning

Ground truth arrives through `POST /projects/{id}/outcome`. Retraining merges the
seed history (`data/training_history.csv`) with every database row that has a
recorded outcome, database rows winning on conflict. A new version is registered in
`model_versions` and activated only when its portfolio ROC AUC is at least as good
as the active one, unless activation is forced. `POST /models/{version}/activate`
rolls back to any earlier registered version.

## Role scoping

Scoping is applied in SQL by `services/auth.scoped_projects`, so it holds for
listing, map data, analytics, alerts and single-record reads alike.

| Role | Visible projects |
| --- | --- |
| `ADMIN`, `POLICY_MAKER` | all |
| `STATE_GOVERNMENT` | own state |
| `DISTRICT_ADMINISTRATION` | own district |
| `LAND_ACQUISITION_AUTHORITY`, `PROJECT_IMPLEMENTING_AGENCY` | explicitly assigned projects |

See [rbac.md](rbac.md) for the permission matrix.
