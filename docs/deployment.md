# Deployment guide

## Container contract

The local Compose stack contains three services:

- `db`: PostGIS 16 for local development only.
- `backend`: FastAPI on port 8000. Its startup entrypoint can run Alembic migrations and load sample data.
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
- TLS, API routing, health checks, logs, and alerts work from the deployed endpoint.
