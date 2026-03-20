#!/usr/bin/env bash
# Show Dagster run history, errors, and asset status.
#
# Usage:
#   ./scripts/runs.sh              # show run summary
#   ./scripts/runs.sh --runs       # show all runs
#   ./scripts/runs.sh --errors    # show errors/failures
#   ./scripts/runs.sh --assets    # show materialized assets
#   ./scripts/runs.sh --logs      # show recent logs

set -eo pipefail
cd "$(dirname "$0")/.."

export DAGSTER_HOME="$(pwd)/.dagster"

show_runs() {
    echo "=== DAGSTER RUNS ==="
    local runs_db=".dagster/storage/runs.db"
    if [ -f "$runs_db" ]; then
        sqlite3 "$runs_db" "SELECT run_id, status FROM runs ORDER BY start_time DESC LIMIT 10;" 2>/dev/null | while IFS='|' read -r id status; do
            echo "  [$status] $id"
        done
    else
        echo "  No run database found"
    fi
}

show_errors() {
    echo "=== ERRORS & FAILURES ==="
    
    # Check for failed runs
    local runs_db=".dagster/storage/runs.db"
    if [ -f "$runs_db" ]; then
        local failed=$(sqlite3 "$runs_db" "SELECT COUNT(*) FROM runs WHERE status='FAILURE';" 2>/dev/null)
        echo "  Failed runs: $failed"
    fi
    
    # Check error files
    echo ""
    echo "=== ERROR LOG FILES ==="
    local error_count=0
    while IFS= read -r errfile; do
        error_count=$((error_count + 1))
        echo "  --- $(basename $(dirname $errfile)) ---"
        grep -iE "(error|failed|exception)" "$errfile" 2>/dev/null | head -3 || echo "  (no errors)"
    done < <(find .dagster/storage -name "*.err" 2>/dev/null)
    
    if [ $error_count -eq 0 ]; then
        echo "  No error files found"
    fi
}

show_assets() {
    echo "=== MATERIALIZED ASSETS ==="
    local index_db=".dagster/storage/index.db"
    if [ -f "$index_db" ]; then
        sqlite3 "$index_db" "SELECT asset_key FROM asset_keys WHERE last_materialization IS NOT NULL ORDER BY last_materialization_timestamp DESC;" 2>/dev/null | sed 's/["\[\]"]//g' | while read -r asset; do
            echo "  ✓ $asset"
        done
        
        local total=$(sqlite3 "$index_db" "SELECT COUNT(*) FROM asset_keys WHERE last_materialization IS NOT NULL;" 2>/dev/null)
        echo ""
        echo "  Total: $total assets materialized"
    else
        echo "  No index database found"
    fi
}

show_logs() {
    echo "=== RECENT LOGS ==="
    find .dagster/storage -name "*.err" -newer .dagster/storage/index.db 2>/dev/null | while read -r log; do
        echo "  --- $(basename $(dirname $log)) ---"
        tail -10 "$log" 2>/dev/null | sed 's/\\n/ /g'
    done | head -50
}

case "${1:-summary}" in
    --runs|-r)
        show_runs
        ;;
    --errors|-e)
        show_errors
        ;;
    --assets|-a)
        show_assets
        ;;
    --logs|-l)
        show_logs
        ;;
    summary|*)
        echo "╔══════════════════════════════════════════╗"
        echo "║     DAGSTER PIPELINE STATUS              ║"
        echo "╚══════════════════════════════════════════╝"
        echo ""
        show_runs
        echo ""
        show_errors
        echo ""
        show_assets
        ;;
esac
