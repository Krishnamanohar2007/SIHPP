# Integration Guide

External land-acquisition and government record systems cannot hold an interactive
session, so they authenticate with a long-lived API key instead of a JWT.

## Key model

* A key looks like `lar_ab12cd34.<secret>`. The prefix before the dot is stored in
  clear text for lookup; the secret half is stored only as a bcrypt hash.
* The full key is returned **once**, by `POST /integration/api-keys`. It cannot be
  retrieved later. Issue a new key and revoke the old one if it is lost.
* Each key carries explicit scopes and optional `state` / `district` limits. Those
  limits are applied in SQL, exactly like a user's role scope.
* Revoking sets `status = REVOKED`; the key stops working immediately and the
  action is written to the audit trail.

Scopes: `projects.read`, `projects.write`, `analytics.read`, `alerts.read`.

## Issuing a key

Requires the `integration.manage` permission (`ADMIN` or `POLICY_MAKER`).

```bash
curl -X POST http://localhost:8000/integration/api-keys \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"name": "Odisha Land Records Bridge",
       "scopes": ["projects.read", "projects.write", "analytics.read"],
       "state": "Odisha"}'
```

```json
{"id": 1, "name": "Odisha Land Records Bridge", "key_prefix": "lar_ab12cd34",
 "scopes": ["projects.read", "projects.write", "analytics.read"],
 "state": "Odisha", "district": null, "status": "ACTIVE",
 "created_at": "2026-09-27T11:20:00Z", "last_used_at": null,
 "api_key": "lar_ab12cd34.SHOWN-ONCE"}
```

## Using a key

```bash
export KEY="lar_ab12cd34.SHOWN-ONCE"

# Connectivity and the model version currently scoring your records
curl -H "X-API-Key: $KEY" http://localhost:8000/integration/v1/health

# Push records in. Each one is scored on arrival and snapshotted.
curl -X POST http://localhost:8000/integration/v1/projects/sync \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '[{"project_id": "OD-0001", "project_name": "Sundargarh Feeder Road",
        "project_type": "National Highway", "state": "Odisha", "district": "Sundargarh",
        "land_area": 140.5, "number_of_owners": 62, "affected_families": 55,
        "approval_timeline_days": 210, "documentation_completeness": 72,
        "stakeholder_responsiveness": 68, "historical_performance_score": 74,
        "lifecycle_stage": "Compensation",
        "compensation_status": "In Progress", "compensation_percentage": 44,
        "legal_disputes": 2, "land_possession_status": "Partially Possessed",
        "land_possession_percentage": 51, "rehabilitation_status": "In Progress",
        "rehabilitation_percentage": 38, "latitude": 22.1167, "longitude": 84.0333}]'

# Pull scored records back, incrementally
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/integration/v1/projects?updated_since=2026-09-27T00:00:00Z&limit=100"

# One project's prediction and explanation together
curl -H "X-API-Key: $KEY" http://localhost:8000/integration/v1/projects/OD-0001/prediction
```

`sync` response:

```json
{"received": 1, "created": 1, "updated": 0, "scored": 1, "rejected": []}
```

## Behaviour to rely on

* **Derived fields are ignored on write.** `risk_score`, `delay_probability` and
  `risk_category` are always recomputed by the active model, so a feed cannot
  assert its own risk. Send the operational fields and read the scores back.
* **Partial batches make progress.** A record outside the key's geographic scope
  is listed in `rejected` with a reason; the rest of the batch is still applied.
  Batches are capped at 500 records (413 above that).
* **Upsert semantics.** A known `project_id` is updated, an unknown one created.
  Every affected project gets a fresh metric snapshot, so the timeline analytics
  reflect the feed.
* **Incremental sync.** `updated_since` filters on `projects.updated_at`, which the
  database maintains on every write. Records are returned newest first.
* **Every sync is audited.** An `INTEGRATION_SYNC` entry records the key prefix and
  the created / updated / rejected counts.

## Failure modes

| Status | Cause |
| --- | --- |
| 401 | Missing, malformed, unknown or revoked key |
| 403 | Key lacks the scope the endpoint requires |
| 413 | More than 500 records in one batch |
| 422 | A record fails schema validation, or the batch is empty |
| 503 | No model bundle is loaded, so records cannot be scored |

## Operational notes

* `last_used_at` is updated on every authenticated call, which is the simplest way
  to spot a feed that has gone quiet.
* Issue one key per integrating system rather than sharing one, so revocation
  never takes down more than the intended system.
* Prefer narrow keys: a state-limited `projects.write` key cannot touch another
  state's records even if the feed is misconfigured.
