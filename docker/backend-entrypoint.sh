#!/bin/sh
set -eu

# Train a first model bundle when none is present. The API refuses to score
# without one, so this must succeed before migrations and seeding.
if [ ! -f /ml/models/active.json ] && [ ! -f /ml/models/model_card.json ]; then
  python /ml/train_model.py
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ "${SEED_SAMPLE_DATA:-true}" = "true" ]; then
  python scripts/seed_projects.py
fi

exec "$@"
