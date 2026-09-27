# RBAC and approval workflow

Roles: `ADMIN`, `LAND_ACQUISITION_AUTHORITY`, `DISTRICT_ADMINISTRATION`, `STATE_GOVERNMENT`, `PROJECT_IMPLEMENTING_AGENCY`, `POLICY_MAKER`.

New registrations are always `PENDING`. Submit `POST /auth/register` as multipart form data with a government-domain email and PDF/JPG/PNG supporting document. An Admin approves or rejects requests through `/auth/admin/registrations` endpoints. Approval requires a one-time initial password.

Authentication uses expiring JWT bearer tokens. Set a unique `JWT_SECRET` in every environment. Never commit it. Set optional bootstrap credentials only for first deployment, then remove `BOOTSTRAP_ADMIN_PASSWORD`.

Permissions are stored in `roles`, `permissions`, and `role_permissions`. Server-side scopes restrict district users to their district, state users to their state, and implementing agencies to explicitly assigned projects. Read-only roles have no write permission. Approval, rejection, and role changes write to `audit_log`.

After deployment, create an admin from bootstrap variables, log in at `POST /auth/login`, then use its bearer token to review requests. Configure persistent `/app/uploads` storage before production deployment; uploaded documents must not be served publicly without an authenticated admin download endpoint.

## Permission matrix

| Permission | ADMIN | POLICY_MAKER | STATE_GOVERNMENT | DISTRICT_ADMINISTRATION | LAND_ACQUISITION_AUTHORITY | PROJECT_IMPLEMENTING_AGENCY |
| --- | :-: | :-: | :-: | :-: | :-: | :-: |
| `projects.read` | yes | yes | yes | yes | yes | yes |
| `projects.write` | yes | - | - | yes | yes | - |
| `projects.outcome` | yes | - | - | yes | yes | - |
| `analytics.read` | yes | yes | yes | yes | yes | yes |
| `alerts.read` | yes | yes | yes | yes | yes | yes |
| `alerts.write` | yes | - | - | yes | yes | yes |
| `audit.read` | yes | yes | yes | - | - | - |
| `models.manage` | yes | yes | - | - | - | - |
| `integration.manage` | yes | yes | - | - | - | - |
| `users.review` | yes | - | - | - | - | - |
| `users.manage` | yes | - | - | - | - | - |

`ADMIN` passes every permission check unconditionally; the other roles are granted
exactly the rows above through `role_permissions`.

## Project scope

Scoping is applied in SQL by `services/auth.scoped_projects`, so it holds for
listing, map data, analytics, alerts and single-record reads alike. A record
outside the caller's scope returns 403 and never appears in a list.

| Role | Visible projects |
| --- | --- |
| `ADMIN`, `POLICY_MAKER` | all |
| `STATE_GOVERNMENT` | own state |
| `DISTRICT_ADMINISTRATION` | own district |
| `LAND_ACQUISITION_AUTHORITY`, `PROJECT_IMPLEMENTING_AGENCY` | explicitly assigned projects |

A `LAND_ACQUISITION_AUTHORITY` may edit an assigned project but cannot create a
new one. A `DISTRICT_ADMINISTRATION` user cannot create or move a project outside
their own district.

## Audit coverage

Every state change is written to `audit_log` with the actor, the target and a
before/after diff where one applies: account review and role changes, project
creation, update and bulk import, recorded outcomes, alert acknowledge / assign /
resolve, model retraining and activation, portfolio re-scoring, and API-key issue,
revocation and sync. `GET /auth/admin/audit` filters by action, target and actor
and requires `audit.read`.

Integration keys are separate principals: they carry scopes rather than roles, and
their activity is audited against the key prefix. See [integration.md](integration.md).
