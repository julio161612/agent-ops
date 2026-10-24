#!/bin/sh
# Optionally apply DB migrations before starting the app. Locally this stays
# on (RUN_MIGRATIONS_ON_START=true, the default). In Azure it is set to false
# and migrations run as a separate Container Apps Job (see infra/terraform), so
# several replicas never race to migrate and a failed migration never takes a
# running revision down.
set -e

if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
    echo "entrypoint: running alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
