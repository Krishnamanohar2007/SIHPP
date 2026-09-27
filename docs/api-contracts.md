# API Contracts

Every path below is also served under `/api/v1` for external clients that need a
pinned version. Interactive endpoints use `Authorization: Bearer <jwt>`;
`/integration/v1/*` uses `X-API-Key`. Permissions are listed per endpoint and are
enforced on top of role scoping (see [rbac.md](rbac.md)).

## System

`GET /health`

```json
{"status": "ok", "environment": "development", "model_version": "v1"}
```

## Authentication and administration

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/register` | public | Submit a registration request with a supporting document |
| POST | `/auth/login` | public | Exchange credentials for a JWT |
| GET | `/auth/me` | any session | Current identity, role and geographic assignment |
| GET | `/auth/locations` | public | Reference states and districts |
| GET | `/auth/assignable-users` | any session | Officials an alert can be assigned to, within the caller's scope |
| GET | `/auth/admin/registrations` | `users.review` | Pending registration requests |
| GET | `/auth/admin/registrations/{id}/document` | `users.review` | Download the supporting document |
| POST | `/auth/admin/registrations/{id}/approve` | `users.review` | Approve and create the account |
| POST | `/auth/admin/registrations/{id}/reject` | `users.review` | Reject with a reason |
| GET | `/auth/admin/users` | `users.manage` | List accounts |
| POST | `/auth/admin/users/{id}/role` | `users.manage` | Change a role |
| POST | `/auth/admin/users/{id}/projects/{project_id}` | `users.manage` | Grant project-level access |
| GET | `/auth/admin/audit` | `audit.read` | Filterable audit trail |
| GET | `/auth/admin/audit/actions` | `audit.read` | Distinct actions and target types, for filters |

`GET /auth/admin/audit` accepts `action`, `target_type`, `target_id`, `actor_id`,
`limit` and `offset`, and returns `{"total": n, "items": [...]}`. Recorded actions
include `REGISTRATION_*`, `ROLE_CHANGED`, `PROJECT_ACCESS_ASSIGNED`,
`PROJECT_CREATED`, `PROJECT_UPDATED`, `PROJECTS_BULK_IMPORTED`,
`PROJECT_OUTCOME_RECORDED`, `ALERT_ACKNOWLEDGED`, `ALERT_ASSIGNED`,
`ALERT_RESOLVED`, `MODEL_RETRAINED`, `MODEL_ACTIVATED`, `PORTFOLIO_RESCORED`,
`API_KEY_ISSUED`, `API_KEY_REVOKED` and `INTEGRATION_SYNC`.

## Projects

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/projects` | `projects.read` | Paged register with filters and sorting |
| GET | `/projects/geo` | `projects.read` | GeoJSON feature collection for the map |
| GET | `/projects/filter-options` | `projects.read` | Dependent filter values |
| GET | `/projects/{id}` | `projects.read` | One project |
| POST | `/projects` | `projects.write` | Create; the server scores it |
| PUT | `/projects/{id}` | `projects.write` | Replace; the server re-scores it |
| POST | `/projects/bulk-upload` | `projects.write` | CSV import, every row scored |
| POST | `/projects/predict-preview` | `projects.write` | Score an unsaved project |
| POST | `/projects/{id}/predict` | `projects.read` | Portfolio and per-stage probabilities |
| GET | `/projects/{id}/explain` | `projects.read` | SHAP attribution and recommendations |
| GET | `/projects/{id}/timeline` | `projects.read` | Recorded metric history |
| POST | `/projects/{id}/outcome` | `projects.outcome` | Record the realised schedule |
| GET | `/locations/reverse` | public | Reverse geocode to state and district |
| GET | `/stats/summary` | `analytics.read` | Legacy dashboard summary |

`GET /projects` filters: `country`, `state`, `district`, `land_type`,
`risk_category`, `project_type`, `lifecycle_stage`, `min_delay_probability`;
sorting: `sort` in `project_id|project_name|risk_score|delay_probability|state|district|lifecycle_stage`
with `order=asc|desc`.

`risk_score`, `delay_probability` and `risk_category` are **derived**. They are
optional on write and ignored if supplied, so a client cannot assert a risk score
the model does not support. Supplying all three inconsistently is still rejected
(422), which keeps a CSV export round-trip honest.

`POST /projects/{id}/predict`:

```json
{
  "risk_score": 100.0,
  "delay_probability": 0.993,
  "risk_category": "High",
  "lifecycle_risks": {"Notification": 0.91, "Compensation": 0.99, "Possession": 0.97,
                      "Rehabilitation": 0.99, "Legal resolution": 0.89},
  "lifecycle_risk_sources": {"Notification": "modelled", "Compensation": "modelled",
                             "Possession": "modelled", "Rehabilitation": "modelled",
                             "Legal resolution": "modelled"},
  "model_version": "v1"
}
```

A stage whose model could not be trained reports
`"fallback: portfolio model"` in `lifecycle_risk_sources` rather than silently
presenting a guess as a stage prediction.

`GET /projects/{id}/explain?stage=Compensation` (omit `stage` for the portfolio
model):

```json
{
  "model_version": "v1",
  "stage": null,
  "delay_probability": 0.993,
  "base_value": 0.12934,
  "top_contributing_factors": [
    {"feature": "land_possession_percentage", "feature_label": "Land possession",
     "driver": "Possession bottlenecks", "value": 38.0, "shap_value": 1.09715,
     "impact": "increases delay risk"}
  ],
  "delay_drivers": [{"driver": "Possession bottlenecks", "contribution": 1.09715, "share": 0.2251}],
  "waterfall": [{"feature": "Land possession", "shap_value": 1.09715}],
  "global_importance": [{"feature": "numeric__legal_disputes", "importance": 0.138393, "share": 0.1384}],
  "recommendations": [
    {"action": "Accelerate possession handover",
     "detail": "Complete joint measurement and handover for the remaining parcels.",
     "driver": "Possession bottlenecks", "feature": "land_possession_percentage",
     "feature_label": "Land possession", "current_value": 38.0, "target_value": 63.0,
     "projected_delay_probability": 0.9653, "expected_reduction": 0.0277, "priority": "Medium"}
  ]
}
```

`expected_reduction` is a counterfactual: the action's target value is scored
through the same model, so the number is the model's own estimate of the benefit,
not a fixed rule. Recommendations are sorted by it.

`POST /projects/{id}/outcome`:

```json
{"expected_completion_days": 500, "actual_completion_days": 900, "notes": "Litigation"}
```

`delayed` defaults to actual exceeding expected by more than 10% and can be
overridden explicitly. This is the label retraining consumes.

## Analytics

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/analytics/kpis` | Headline indicators, including outcome agreement |
| GET | `/analytics/trends?level=state\|district` | Delay exposure by geography, worst first |
| GET | `/analytics/timeline?days=90&bucket=day\|week\|month` | Portfolio risk over time |
| GET | `/analytics/comparative?dimension=project_type` | Comparison across a dimension |
| GET | `/analytics/drivers` | Prevalence of each delay driver |
| GET | `/analytics/priority?limit=20` | Ranked intervention queue |
| GET | `/analytics/stage-exposure` | Average probability per lifecycle stage |

All require `analytics.read` and accept `state`, `district` and, where relevant,
`project_type`. `dimension` accepts `project_type`, `land_type`,
`lifecycle_stage`, `risk_category`, `state`, `compensation_status`,
`land_possession_status` and `rehabilitation_status`.

`priority_index` is `delay_probability × (land value in crore + affected_families / 100)`,
so ranking reflects exposure and not only likelihood.

## Alerts

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/alerts` | `alerts.read` | Alert list, filter by `status`, `severity`, `assigned_to_me` |
| GET | `/alerts/inbox` | `alerts.read` | Unresolved alerts, most severe first |
| POST | `/alerts/scan-now` | `alerts.read` | Re-score, snapshot and raise alerts immediately |
| POST | `/alerts/{id}/acknowledge` | `alerts.write` | Take ownership |
| POST | `/alerts/{id}/assign` | `alerts.write` | Assign to an official |
| POST | `/alerts/{id}/resolve` | `alerts.write` | Close with a required note |

Each alert carries `severity`, `category`, its `drivers` and its
`recommendations`, so it is actionable without a second call. An alert is
deduplicated while `open` or `acknowledged`; once resolved, a still-risky project
raises a fresh alert on the next scan. Resolving twice returns 409.

## Model registry

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/models/active` | `analytics.read` | Model card of the serving bundle |
| GET | `/models` | `analytics.read` | Registered versions with metrics |
| POST | `/models/retrain` | `models.manage` | Train from seed history plus recorded outcomes |
| POST | `/models/{version}/activate` | `models.manage` | Switch or roll back |
| POST | `/models/reload` | `models.manage` | Reload from disk without a restart |
| POST | `/models/rescore` | `models.manage` | Re-score the whole register |

`POST /models/retrain` body: `{"force_activate": false, "notes": "..."}`. Without
`force_activate`, the new version is activated only when its portfolio ROC AUC is
at least as good as the active one; the response reports both scores.

## Integration

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/integration/scopes` | `integration.manage` | Available key scopes |
| GET | `/integration/api-keys` | `integration.manage` | Issued keys, secrets excluded |
| POST | `/integration/api-keys` | `integration.manage` | Issue a key, returned once |
| DELETE | `/integration/api-keys/{id}` | `integration.manage` | Revoke a key |
| GET | `/integration/v1/health` | `projects.read` scope | Probe, with model version |
| GET | `/integration/v1/projects` | `projects.read` scope | Records, `updated_since` for incremental sync |
| GET | `/integration/v1/projects/{id}` | `projects.read` scope | One record |
| GET | `/integration/v1/projects/{id}/prediction` | `projects.read` scope | Prediction plus explanation |
| POST | `/integration/v1/projects/sync` | `projects.write` scope | Upsert up to 500 records, each scored |
| GET | `/integration/v1/analytics/kpis` | `analytics.read` scope | Indicators within the key's scope |
| GET | `/integration/v1/analytics/trends` | `analytics.read` scope | Geographic trends |

See [integration.md](integration.md) for the key lifecycle and a worked example.

## Errors

| Status | Meaning |
| --- | --- |
| 401 | Missing or invalid credentials or API key |
| 403 | Authenticated but lacking the permission or scope, or the record is outside scope |
| 404 | Record absent |
| 409 | Conflicting state: duplicate ID, already-resolved alert, missing bundle on activate |
| 413 | Payload too large: CSV over 10 MB, document over 5 MB, batch over 500 records |
| 422 | Contract violation: failed validation, unknown dimension or stage |
| 503 | No usable model bundle, or not enough labelled data to retrain |

A record outside the caller's scope returns 403, not 404, and is never returned by
a list endpoint.
