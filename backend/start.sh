#!/bin/sh
# Starts the API. Two switches for small hosting plans (both off by default):
#   RUN_MIGRATIONS=true      apply database migrations first (safe to repeat)
#   RUN_WORKER_IN_API=true   also run the background worker in this container,
#                            restarted if it ever stops
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    python -m atlas.migrate
fi

if [ "${RUN_WORKER_IN_API:-false}" = "true" ]; then
    (while true; do python -m atlas.worker || true; sleep 5; done) &
fi

exec uvicorn atlas.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-server-header
