# Deployment guide

## Container contract

The local Compose stack contains three services:

- `db`: PostGIS 16 for local development only.
- `backend`: FastAPI on port 8000. Its startup entrypoint trains a first model bundle when none exists, can run Alembic migrations, and can load sample data.
- `frontend`: the Vite production build served by Nginx on port 80. Nginx proxies `/api/` to the backend, so browser clients can use a same-origin API path.

For local use, copy `docker/.env.example` to `docker/.env`, set a non-default password, then run:

```sh
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build
```

Open `http://localhost:8080`, API health at `http://localhost:8000/health`, and API docs at `http://localhost:8000/docs`.

`SEED_SAMPLE_DATA=true` is for development. It is idempotent, but set it to `false` for every non-development environment. In production, also set `RUN_MIGRATIONS=false` on web replicas and run `alembic upgrade head` once as a release job before deploying replicas.

## Runtime configuration

Store secrets in the platform secret manager, not in images, source control, Vite variables, or Compose files. Required backend setting:

```text
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Use the managed database hostname outside Compose; `db` is only the local container hostname. Set `ENVIRONMENT`, notification settings, and database credentials as runtime environment variables. `VITE_*` values are public build-time values and must never contain credentials.

### Model and analytics settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `ML_MODELS_DIR` | `<repo>/ml/models` | Directory holding versioned model bundles and `active.json` |
| `ML_MODEL_DIR` | unset | Pin one exact bundle, overriding `active.json` |
| `ML_PACKAGE_DIR` | `<repo>/ml` | Location of the training code, needed for in-process retraining |
| `TRAINING_HISTORY_PATH` | `<repo>/data/training_history.csv` | Seed labels merged with recorded outcomes at retraining |
| `NOTIFICATION_SCAN_INTERVAL_MINUTES` | `15` | Risk scan cadence; each scan also records metric snapshots |
| `NOTIFICATION_RISK_THRESHOLD` | `60` | Risk score above which an alert is raised |
| `RETRAIN_INTERVAL_HOURS` | `0` | Scheduled continuous learning; `0` disables it |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Comma-separated browser origins allowed to call the API |

The model bundle must be on **shared, persistent storage** when more than one
backend replica runs. Replicas load the bundle from disk and `POST /models/retrain`
writes a new one, so with per-replica local disks the replicas will drift onto
different model versions. Mount one shared volume, or bake a fixed bundle into the
image and pin it with `ML_MODEL_DIR` while retraining on a separate job.

For the same reason, run the scheduled jobs on exactly one replica. Both the risk
scan and scheduled retraining run in-process through APScheduler, so N replicas
means N concurrent scans. Either keep the API at one replica, or set
`NOTIFICATION_SCAN_INTERVAL_MINUTES` high and `RETRAIN_INTERVAL_HOURS=0` on the
web replicas and drive both from a dedicated scheduled job that calls
`POST /alerts/scan-now` and `POST /models/retrain`.

Set `CORS_ORIGINS` to the exact production frontend origin. The bundled Nginx
config proxies `/api/` same-origin, so no cross-origin allowance is needed for that
path.

### Integration keys

API keys are stored as bcrypt hashes and returned once at creation. There is no
recovery path: to rotate, issue a new key, move the integrating system over, then
revoke the old one. Issue one key per system and prefer state or district limited
keys. Key issue, revocation and every sync are written to `audit_log`.

The production database role needs enough rights for the Alembic release job to create the PostGIS extension, tables, and indexes. Runtime API roles should use least privilege. Enable backups, point-in-time recovery where available, TLS in transit, encryption at rest, private network access, and audit logs. Do not expose PostgreSQL to the public internet.

Deploy the frontend and backend behind TLS. Route `/` to the frontend and `/api/` to the backend through one ingress, load balancer, or reverse proxy. The included Nginx configuration removes cross-origin browser traffic for this path. If the API must be served from another origin, add an explicit production origin to FastAPI CORS settings before release.

The application uses standard PostgreSQL/PostGIS, HTTP, and environment variables. It contains no cloud-vendor SDK or provider-specific application dependency.

## NIC Cloud (MeghRaj)

Use standard virtual machines when managed containers are unavailable:

1. Build the backend and frontend images in a controlled CI environment and publish them to an approved private registry, or transfer signed images to the VM environment.
2. Run the frontend and backend containers with a supported container runtime. Put a NIC-approved load balancer or Nginx in front for TLS and `/api/` routing.
3. Use a managed PostgreSQL service with PostGIS if offered. Otherwise run a dedicated, private PostgreSQL/PostGIS VM with persistent encrypted storage, automated backups, replication or a tested restore plan, and monitoring.
4. Run `alembic upgrade head` as a one-off release action from the backend image. Set `RUN_MIGRATIONS=false` and `SEED_SAMPLE_DATA=false` on long-running services.
5. Restrict security groups/firewall rules: public HTTPS only to the load balancer; application-to-database traffic only on PostgreSQL TLS port.

If an approved NIC registry, secrets service, or monitoring system is required, configure it at deployment time. Keep those integrations outside application code.

## AWS

Use ECS/Fargate for containers and Amazon RDS for PostgreSQL with the PostGIS extension:

1. Publish versioned backend and frontend images to Amazon ECR.
2. Define separate ECS task definitions. Send frontend traffic through an Application Load Balancer; route `/api/*` to the backend target group. Put backend tasks in private subnets.
3. Create RDS for PostgreSQL in private subnets. Enable PostGIS, Multi-AZ when required, automated backups, encryption, and TLS. Store the RDS connection string or password in Secrets Manager and inject it into the backend task.
4. Run an ECS one-off task for `alembic upgrade head` before rolling out backend tasks. Do not run migration or sample seed logic in every Fargate replica.
5. Use IAM task roles only for deployment infrastructure needs. The application remains provider-neutral and does not import AWS SDKs.

Configure ECS health checks against `/health`, autoscale backend tasks by CPU, memory, or request metrics, and retain application logs in the approved logging destination.

## Azure Government Cloud

Use Azure Container Apps for a simpler managed deployment, or AKS when network, policy, or workload controls require Kubernetes:

1. Publish images to an Azure Government-compatible Azure Container Registry.
2. In Container Apps, create separate frontend and backend apps; in AKS, create separate Deployments and Services. Use an ingress controller or front door/load balancer that routes `/api/` to the backend.
3. Use Azure Database for PostgreSQL Flexible Server where the target region supports it and enable PostGIS. Use private access, TLS, backups, high availability where required, and Azure Key Vault for credentials.
4. Run migrations as a Container Apps Job or Kubernetes Job before updating backend replicas. Set `RUN_MIGRATIONS=false` and `SEED_SAMPLE_DATA=false` on the deployed API.
5. Apply Government Cloud identity, network, logging, and compliance controls through Azure configuration rather than application SDKs.

For AKS, use readiness and liveness probes on `/health`, a persistent external database, and a rolling-update strategy. For Container Apps, configure revision traffic and minimum replicas according to availability requirements.

## Release checks

Before each release, confirm:

- Image build uses a locked dependency set and has passed vulnerability scanning.
- Database migration has been tested against a restored production-like copy.
- Database backup restore is tested.
- `DATABASE_URL` points to the intended private, TLS-protected database.
- Sample seeding is disabled outside development.
- A model bundle is present on shared storage and `GET /health` reports its `model_version`.
- `scikit-learn` matches the version that produced the bundle; a mismatch warns on unpickle and can change results.
- Scheduled scanning and retraining run on exactly one replica.
- `CORS_ORIGINS` lists only the intended production origins.
- TLS, API routing, health checks, logs, and alerts work from the deployed endpoint.
