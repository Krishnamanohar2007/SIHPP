# Architecture Notes

- React client presents parcel and risk-monitoring workflows.
- FastAPI owns API contracts, validation, and persistence access.
- PostgreSQL stores operational land and risk records.
- ML workflows train offline and publish versioned models.

Initial scaffold includes no domain schema or prediction endpoint. Add these after risk fields and source contracts are agreed.
