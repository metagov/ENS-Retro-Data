#!/usr/bin/env bash
# Launch the Dagster webserver.
#
# Usage:
#   ./scripts/serve.sh              # full-capacity mode (default)
#   ./scripts/serve.sh --read-only  # read-only UI mode
#
# Environment:
#   PORT  – webserver port (default: 3000)
#   HOST  – bind address  (default: 127.0.0.1)

set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-3000}"
HOST="${HOST:-127.0.0.1}"

MODE_FLAG=""
if [[ "${1:-}" == "--read-only" ]]; then
    MODE_FLAG="--read-only"
    echo "Starting Dagster webserver in READ-ONLY mode on ${HOST}:${PORT}"
else
    echo "Starting Dagster webserver in FULL mode on ${HOST}:${PORT}"
fi

export DAGSTER_HOME="$(pwd)/.dagster"

exec uv run dagster-webserver \
    --workspace workspace.yaml \
    --host "$HOST" \
    --port "$PORT" \
    $MODE_FLAG
