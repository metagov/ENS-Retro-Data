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
set -a
source .env
set +a

# Start the daemon in the background (dequeues and launches runs)
uv run dagster-daemon run &
DAEMON_PID=$!
echo "Started dagster-daemon (PID: $DAEMON_PID)"

# Ensure daemon is killed when the script exits
trap "kill $DAEMON_PID 2>/dev/null" EXIT

exec uv run dagster-webserver \
    --workspace workspace.yaml \
    --host "$HOST" \
    --port "$PORT" \
    $MODE_FLAG
