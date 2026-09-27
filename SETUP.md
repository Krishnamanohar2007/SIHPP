# Setup

From a fresh clone to a running system. Two paths: Docker (recommended) or a
local toolchain.

Prerequisites: Docker Desktop, or Python 3.11 + Node 20 + PostgreSQL 16 with
PostGIS 3.4.

---

## 1. Docker (recommended)

### 1.1 Create the environment file

The repository ships `docker/.env.example`. It is a template with placeholder
values and is **not** usable as-is.

```bash
cp docker/.env.example docker/.env
```

Now edit `docker/.env` and set two values before anything else:

| Variable | What to put |
| --- | --- |
| `JWT_SECRET` | A unique random string of at least 32 characters. Sessions are signed with it. |
| `POSTGRES_PASSWORD` | Any local password. It is the database password for the container. |

Generate a secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Optionally set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` to create a
first administrator on startup. The password must be at least 12 characters. If
you leave them blank, no account is created and you will have no way to sign in,
so set them for a first run.

### 1.2 Start

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build
```

First start does four things in order, and the first is slow:

1. Trains a model bundle if `ml/models` has none (roughly one minute).
2. Applies Alembic migrations.
3. Seeds 750 synthetic projects from `data/projects.csv`.
4. Starts the API, then runs the first risk scan a few seconds later in the
   background.

### 1.3 Open

| Service | URL |
| --- | --- |
| Application | http://localhost:8080 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Database | `localhost:5432` |

Sign in with the bootstrap credentials you set. `GET /health` reports the serving
model version; if `model_version` is `null`, no bundle loaded - see
Troubleshooting.

### 1.4 Stop

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env down
```

Add `-v` to also delete the database volume and start clean next time.

---

## 2. Local toolchain

### 2.1 Database

You need PostgreSQL with the PostGIS extension. The simplest route is a
container even when the rest runs locally:

```bash
docker run -d --name la-db -e POSTGRES_DB=risk_monitor \
  -e POSTGRES_USER=risk_user -e POSTGRES_PASSWORD=risk_password \
  -p 5432:5432 postgis/postgis:16-3.4-alpine
```

### 2.2 Data and model

The API refuses to score without a model bundle, so train one before starting it.

```bash
python -m venv venv
# Windows PowerShell: venv\Scripts\Activate.ps1
# macOS/Linux:        source venv/bin/activate
pip install -r ml/requirements.txt

python data/generate_synthetic_projects.py   # projects.csv, training_history.csv, seed.sql
python ml/train_model.py --version v1        # ml/models/v1/ and active.json
```

### 2.3 Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # then set DATABASE_URL and JWT_SECRET
alembic upgrade head
python scripts/seed_projects.py
uvicorn app.main:app --reload
```

`DATABASE_URL` for the container above:

```
postgresql+psycopg2://risk_user:risk_password@localhost:5432/risk_monitor
```

### 2.4 Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves on `http://localhost:5173` and calls the API at
`http://localhost:8000` by default. Set `VITE_API_BASE_URL` in `frontend/.env` to
point elsewhere. The API already allows `localhost:5173` through CORS.

---

## 3. Configuration reference

Set these in `docker/.env` for Docker, or `backend/.env` for a local run.

### Required

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | Set automatically by Compose; set by hand for a local run. |
| `JWT_SECRET` | Unique per environment. Never commit it. |

### First administrator

| Variable | Default | Notes |
| --- | --- | --- |
| `BOOTSTRAP_ADMIN_EMAIL` | unset | Created on startup only if the email does not already exist. |
| `BOOTSTRAP_ADMIN_PASSWORD` | unset | Minimum 12 characters. Remove after first deployment. |

### Risk monitoring

| Variable | Default | Notes |
| --- | --- | --- |
| `NOTIFICATION_RISK_THRESHOLD` | `60` | Risk score above which an alert is raised. |
| `NOTIFICATION_SCAN_INTERVAL_MINUTES` | `15` | Each scan re-scores the register and records snapshots. |
| `NOTIFICATION_CHANNELS` | `console` | Comma-separated: `console`, `email`, `sms`, `push`. All but `console` are logging stubs. |
| `NOTIFICATION_RECIPIENT` | example address | Where alerts are addressed. |

### Models

| Variable | Default | Notes |
| --- | --- | --- |
| `ML_MODELS_DIR` | `<repo>/ml/models` | Bundle directory and `active.json`. |
| `ML_MODEL_DIR` | unset | Pin one exact bundle, overriding `active.json`. |
| `ML_PACKAGE_DIR` | `<repo>/ml` | Training code, needed for in-process retraining. |
| `TRAINING_HISTORY_PATH` | `<repo>/data/training_history.csv` | Seed labels merged with recorded outcomes. |
| `RETRAIN_INTERVAL_HOURS` | `0` | Scheduled retraining. `0` disables it. |

### Other

| Variable | Default | Notes |
| --- | --- | --- |
| `CORS_ORIGINS` | `localhost:5173,localhost:8080` | Comma-separated browser origins. |
| `RUN_MIGRATIONS` | `true` | Set `false` on web replicas; run migrations as a release job. |
| `SEED_SAMPLE_DATA` | `true` | Set `false` outside development. |
| `PROJECTS_CSV_PATH` | `<repo>/data/projects.csv` | Where the register is exported. |
| `ALLOW_CSV_SHRINK` | `false` | Allow an export that would remove rows from the CSV. |

---

## 4. Tests

```bash
cd backend
python -m pytest tests -q
```

Unit tests need no services. The end-to-end API tests need PostGIS and are
skipped without it:

```bash
docker run -d --name la-test-db -e POSTGRES_DB=risk_monitor_test \
  -e POSTGRES_USER=risk_user -e POSTGRES_PASSWORD=risk_password \
  -p 55432:5432 postgis/postgis:16-3.4-alpine

TEST_DATABASE_URL=postgresql+psycopg2://risk_user:risk_password@localhost:55432/risk_monitor_test \
  python -m pytest tests -q
```

The suite drops and rebuilds the schema from migration zero, so point it at a
scratch database, never a working one. It writes the CSV export and model
bundles to temporary directories, so a run never touches `data/` or `ml/models`.

---

## 5. Troubleshooting

**`GET /health` reports `"model_version": null`, and scoring returns 503.**
No model bundle loaded. Run `python ml/train_model.py --version v1`, or check
that `ml/models` is mounted into the container.

**Container is `unhealthy` on first start.**
The entrypoint trains a model before serving, which can exceed the healthcheck
window on a slow machine. Wait and check `docker compose logs backend`; it
becomes healthy once training finishes.

**`InconsistentVersionWarning` on model load.**
The bundle was pickled by a different scikit-learn than the one loading it.
Retrain with the pinned version (`scikit-learn==1.9.0` in both
`backend/requirements.txt` and `ml/requirements.txt`).

**Signed in, but everything returns "Permission denied".**
Your account's role lacks the permission. Check `GET /auth/me` for the live role
and compare against the matrix in `docs/rbac.md`. A role change takes effect on
the next request, but the browser refreshes its copy on page load - reload once.

**No projects visible although the database has rows.**
Project visibility is scoped by role. A state user sees one state, a district
user one district, and an authority only assigned projects. Confirm the role and
the assigned area on `GET /auth/me`.

**`data/projects.csv` shrank unexpectedly.**
It should not: the export refuses to shrink the file. Regenerate with
`python data/generate_synthetic_projects.py` if it did, and check whether
`ALLOW_CSV_SHRINK` was set.

**Port already in use.**
Change `BACKEND_PORT`, `FRONTEND_PORT` or `POSTGRES_PORT` in `docker/.env`.
