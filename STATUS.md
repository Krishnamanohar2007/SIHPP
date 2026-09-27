# Project Status

Last updated: 2026-09-27. Branch `main`, commit `a6624095`.

---

## Requirement coverage

Against the eleven items in the problem statement's expected solution.

| # | Requirement | State | Where |
| --- | --- | --- | --- |
| 1 | AI/ML models forecasting project delays | Done | Six XGBoost classifiers; [ml/train_model.py](ml/train_model.py) |
| 2 | Automated identification of high-probability projects | Done | Scheduled scan plus ranked queue; `GET /analytics/priority` |
| 3 | Project-wise risk scoring and prioritisation | Done | Published risk rule; exposure-weighted priority index |
| 4 | Identification of key delay drivers | Done | SHAP rolled up onto seven named drivers; `GET /projects/{id}/explain` |
| 5 | Explainable AI for transparency | Done | Local SHAP with base value and waterfall, driver shares, global importance |
| 6 | Interactive dashboards | Done | Delay probability, risk bands, state and district trends, timeline, indicators, comparative analytics |
| 7 | GIS visualisation of high-risk projects | Done | Leaflet map, project and district concentration layers |
| 8 | Automated alerts and notifications | Partial | In-app alerting with full workflow; email/SMS/push transports are logging stubs |
| 9 | Predictive recommendations | Done | Counterfactual actions ranked by modelled effect |
| 10 | Continuous model learning | Done | Outcome capture, merge, retrain, registry, rollback |
| 11 | APIs for integration | Done | Scoped API keys under `/integration/v1` |
| 12 | Secure role-based access with audit trails | Done | Six roles, SQL-enforced scoping, 18 audited action types |

---

## Measured model quality

Held-out split of the shipped seed data (150 rows). Regenerate with
`python ml/train_model.py`; exact figures move with the seed.

| Target | ROC AUC | Accuracy | Brier |
| --- | --- | --- | --- |
| Portfolio delay | 0.813 (ceiling 0.828) | 0.740 | 0.183 |
| Notification | 0.688 | 0.627 | 0.226 |
| Compensation | 0.803 | 0.767 | 0.161 |
| Possession | 0.681 | 0.620 | 0.237 |
| Rehabilitation | 0.879 | 0.860 | 0.109 |
| Legal resolution | 0.701 | 0.707 | 0.214 |

The ceiling matters: outcomes are sampled from a probability, so no model can
beat the AUC of that probability itself. 0.813 against 0.828 means the portfolio
model recovers nearly all the learnable signal in this dataset.

**The shipped data is synthetic.** These numbers demonstrate that the pipeline
works. They say nothing about real districts, and the model must be retrained on
recorded outcomes before any operational use.

---

## Verified end to end

Exercised against a running stack, not only in tests.

- Create, update and bulk import, each scored by the server on write.
- Preview, prediction and explanation, including per-stage explanations.
- Outcome capture, retraining and activation: 60 recorded outcomes moved
  portfolio ROC AUC from 0.8129 to 0.8429, and the new version auto-activated.
- Rollback to an earlier registered version.
- Alert scan, acknowledge and resolve, with audit entries for each.
- Integration key issue, scoped sync with per-record rejection, revoke.
- Role scoping: a state official could not read another state's project.
- Every client route, driven in a browser. No console errors. No horizontal
  overflow at 375px width.

Test suite: 54 tests. 20 unit (model service, contracts, CSV guard) and 34
end-to-end against PostGIS, rebuilding the schema from migration zero.

---

## Known limitations

**Notification transports are stubs.** Only the `console` channel writes
anything real; `email`, `sms` and `push` log what they would have sent. The
in-app inbox is the working delivery path. Wiring SMTP or an SMS gateway means
implementing `NotificationChannel` in
[channels.py](backend/app/services/notifications/channels.py).

**Scheduling assumes a single replica.** The risk scan and optional retraining
run in-process via APScheduler, so N replicas means N concurrent scans. Either
run one API replica or disable the in-process jobs and drive
`POST /alerts/scan-now` and `POST /models/retrain` from an external scheduler.

**The model bundle needs shared storage across replicas.** Replicas load from
disk and retraining writes a new bundle; with per-replica local disks they drift
onto different versions.

**Stage labels come only from the seed data.** A recorded outcome supplies the
portfolio label alone, so the per-stage models continue to learn from synthetic
labels until stage-level outcomes are captured. Those rows are excluded from
stage training rather than given an invented label.

**No password reset.** Administrators set an initial password at approval time.
There is no self-service reset or change-password endpoint.

**Registration documents are stored on the container filesystem** at
`/app/uploads`. Mount persistent storage before any real deployment.

**Retraining is synchronous.** `POST /models/retrain` holds the request until
training finishes - acceptable at this data size, not at a much larger one.

---

## Suggested next steps

Ordered by value, not effort.

1. **Capture stage-level outcomes** so the per-stage models learn from reality
   rather than synthetic labels. Largest single gain in prediction quality.
2. **Implement a real notification transport.** The dispatcher, workflow and
   audit trail are already in place; only the channel is missing.
3. **Password reset and change-password**, needed before any real user base.
4. **Move scheduling out of process** (a dedicated worker or external cron) to
   make the API horizontally scalable.
5. **Frontend tests.** The backend is covered; the client is verified by hand.
6. **Code-split the client bundle.** It is 5.2 MB raw, 1.6 MB gzipped, dominated
   by Plotly.

---

## Reference

| Document | Contents |
| --- | --- |
| [README.md](README.md) | What the system does, quick start |
| [SETUP.md](SETUP.md) | Full setup, configuration reference, troubleshooting |
| [docs/architecture.md](docs/architecture.md) | Components, request path, prediction flow, client surfaces |
| [docs/api-contracts.md](docs/api-contracts.md) | Every endpoint, permissions, payloads, error codes |
| [docs/ml-models.md](docs/ml-models.md) | Targets, features, risk rule, metrics, continuous learning |
| [docs/integration.md](docs/integration.md) | API-key lifecycle and a worked example |
| [docs/rbac.md](docs/rbac.md) | Permission matrix, scoping, audit coverage |
| [docs/deployment.md](docs/deployment.md) | Managed-cloud deployment and release checks |
