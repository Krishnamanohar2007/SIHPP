#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

if [ "${SEED_SAMPLE_DATA:-true}" = "true" ]; then
  python scripts/seed_projects.py
fi

exec "$@"
