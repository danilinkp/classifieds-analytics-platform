#!/usr/bin/env bash
set -euo pipefail

superset db upgrade
superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname BI \
    --email admin@example.com \
    --password "${SUPERSET_ADMIN_PASSWORD}" || true
superset init

exec /usr/bin/run-server.sh
