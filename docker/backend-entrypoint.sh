#!/bin/sh
set -eu

if [ ! -f /ml/models/delay_model.pkl ] || [ ! -f /ml/models/delay_model_shap.pkl ]; then
  python /ml/train_model.py
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ "${SEED_SAMPLE_DATA:-true}" = "true" ]; then
  python scripts/seed_projects.py
fi

exec "$@"
