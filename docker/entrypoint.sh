#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running alembic migrations..."
  alembic upgrade head
fi

exec "$@"
