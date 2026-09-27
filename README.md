# SIH PS 26017 — Land Acquisition Risk Monitor

AI-enabled decision support for land-acquisition delay risk: it predicts which
projects are likely to slip, explains why, ranks corrective actions, and learns
from recorded outcomes.

## What it does

- **Predicts delay** for the whole project and for each lifecycle stage
  (notification, compensation, possession, rehabilitation, legal resolution) using
  six independent gradient-boosted classifiers.
- **Scores and prioritises** every project with a published, hand-checkable risk
  rule, and ranks an intervention queue by exposure times likelihood.
- **Explains every prediction** with SHAP, rolled up onto the delay drivers a
  policymaker acts on: pending approvals, compensation, litigation, documentation,
  rehabilitation and administrative bottlenecks.
- **Recommends corrective actions** ranked by their modelled effect: each action's
  target value is scored back through the model, so the ordering is an estimate,
  not a fixed list.
- **Monitors continuously**: a scheduled scan re-scores the register, records a
  metric snapshot and raises alerts with an acknowledge / assign / resolve
  workflow.
- **Serves dashboards**: portfolio indicators, state and district trends, timeline
  analysis, comparative analytics, stage exposure and a GIS risk map.
- **Learns**: officials record realised schedules, retraining merges them with the
  seed history, and a new version activates only when it scores at least as well.
- **Integrates**: scoped API keys let external government systems push records in
  and read scored records back under `/integration/v1`.
- **Controls access**: six roles, SQL-enforced geographic scoping, and an audit
  trail over every state change.

## Structure

- `backend/` — FastAPI service, RBAC, analytics, model registry, integration API.
- `frontend/` — Vite React client with Tailwind CSS.
- `ml/` — feature contract, training pipeline, offline retraining, model bundles.
- `data/` — synthetic generator, operational register, labelled training history.
- `docker/` — local backend, frontend and PostGIS containers.
- `docs/` — architecture, API contracts, RBAC, models, integration, deployment.

## Run application with Docker

1. From repository root, copy Docker environment defaults and replace the development password:

   ```sh
   cp docker/.env.example docker/.env
   ```

2. Start services:

   ```sh
   docker compose -f docker/docker-compose.yml --env-file docker/.env up --build
   ```

3. Open `http://localhost:8080` for the frontend. Swagger UI: `http://localhost:8000/docs`. Health endpoint: `http://localhost:8000/health`.

The local backend applies migrations and loads sample data at startup. Disable `SEED_SAMPLE_DATA` outside development. See `docs/deployment.md` for managed-cloud deployment guidance and one-off migration steps.

The database listens on `localhost:5432`. Development defaults live in `docker/.env.example`.

## Run backend without Docker

Requires Python 3.11 and a reachable PostgreSQL instance.

```sh
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Set `DATABASE_URL` in `backend/.env` for local PostgreSQL.

## Run frontend

```sh
cd frontend
npm install
npm run dev
```

## Generate data and train models

```sh
python data/generate_synthetic_projects.py   # projects.csv + training_history.csv + seed.sql
python ml/train_model.py --version v1        # ml/models/v1/ and active.json
```

The API refuses to score without a model bundle, and the Docker entrypoint trains
one automatically on first start. `data/generate_synthetic_data.py` separately
regenerates `data/generated/land_parcels.csv`.

> The shipped dataset is synthetic. It exercises the full pipeline and must not be
> read as evidence about real districts or real projects.

## Tests

```sh
cd backend
python -m pytest tests -q
```

Unit tests need no services. The end-to-end API tests need a PostGIS database and
are skipped without one:

```sh
docker run -d --name la-test-db -e POSTGRES_DB=risk_monitor_test   -e POSTGRES_USER=risk_user -e POSTGRES_PASSWORD=risk_password   -p 55432:5432 postgis/postgis:16-3.4-alpine

TEST_DATABASE_URL=postgresql+psycopg2://risk_user:risk_password@localhost:55432/risk_monitor_test   python -m pytest tests -q
```

The suite recreates the schema by running the project's own migrations, so it also
proves the migration chain applies from zero. It copies the active model bundle to
a temporary directory, so retraining tests never touch `ml/models`.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Components, request path, prediction flow, model bundle layout |
| [docs/api-contracts.md](docs/api-contracts.md) | Every endpoint, permissions, payloads, error codes |
| [docs/ml-models.md](docs/ml-models.md) | Targets, features, risk rule, metrics, continuous learning |
| [docs/integration.md](docs/integration.md) | API-key lifecycle and a worked integration example |
| [docs/rbac.md](docs/rbac.md) | Permission matrix, project scoping, audit coverage |
| [docs/deployment.md](docs/deployment.md) | Managed-cloud deployment and migration steps |

## Data files

`data/projects.csv` is the portable register and the input to seeding. The API
exports it again whenever a project is written, but the export is refused when it
would shrink the file, so a partially seeded or test database cannot destroy the
dataset. Set `ALLOW_CSV_SHRINK=true` for the deliberate case.
