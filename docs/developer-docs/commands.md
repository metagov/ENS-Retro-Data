# Command Reference

Every command in this project, organized by category. For the minimal set needed to get started, see the README Quick Start instead.

## Setup & Installation

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# No Git LFS needed — all data is regular git.
# Large files (warehouse, dagster storage) are also hosted on DO Spaces
# for deployed services. See scripts/spaces_sync.py.

# Create virtual environment and install all dependencies
uv sync

# Install dev dependencies (pytest, ruff)
uv sync --extra dev

# Install dbt packages (dbt_utils)
cd infra/dbt && uv run dbt deps && cd ../..

# Generate dbt manifest (required before first Dagster run)
cd infra/dbt && uv run dbt parse && cd ../..

# Generate dbt seed CSVs from taxonomy.yaml
uv run python scripts/generate_taxonomy_seeds.py

# Create .env file with the keys you need
cp .env.example .env
# then edit .env to fill in ETHERSCAN_API_KEY, OSO_API_KEY, OPENAI_API_KEY, AGENT_API_KEY, etc.
```

## Dagster (Orchestration)

### Start Dagster UI

```bash
# Start the Dagster webserver (default: http://localhost:3000)
DAGSTER_HOME=$(pwd)/.dagster uv run dagster dev
```

Or use the helper script:

```bash
./scripts/serve.sh              # full edit mode
./scripts/serve.sh --read-only  # read-only mode (matches the Render deployment)
```

Dagster discovers the pipeline via `[tool.dagster] module_name = "infra.definitions"` in `pyproject.toml`.

### Dagster UI Operations

Once the UI is running at `http://localhost:3000`:

| Action | How |
|---|---|
| View all assets | **Assets** tab |
| Materialize everything | **Materialize all** button |
| Materialize specific asset | Click asset → **Materialize** |
| Run bronze fetchers only | Select bronze assets → **Materialize selected** |
| View asset checks | Click asset → **Checks** tab |
| View run logs | **Runs** tab → click a run |
| View asset lineage | **Assets** → **Global asset lineage** |
| Reload definitions | **Reload definitions** (top bar) after code changes |

### Dagster CLI

```bash
# Materialize all assets (bronze fetch + dbt build + checks)
uv run dagster asset materialize -m infra.definitions --select '*'

# Materialize only bronze assets
uv run dagster asset materialize -m infra.definitions --select 'group:bronze_governance'

# Materialize a single asset
uv run dagster asset materialize -m infra.definitions --select 'snapshot_proposals'

# Run all asset checks
uv run dagster asset check -m infra.definitions --select '*'

# List all registered assets
uv run dagster asset list -m infra.definitions
```

## dbt (SQL Transforms)

All dbt commands must be run from `infra/dbt/` (the project directory). `profiles.yml` is colocated there.

```bash
cd infra/dbt
```

### Build Commands

```bash
# Build everything (run models + run tests + load seeds)
uv run dbt build

# Run only models (no tests)
uv run dbt run

# Run only tests
uv run dbt test

# Load seed data (taxonomy CSVs)
uv run dbt seed
```

### Selective Builds

```bash
# Build only staging models
uv run dbt build --select 'staging.*'

# Build only silver models
uv run dbt build --select 'silver.*'

# Build only gold models
uv run dbt build --select 'gold.*'

# Build a specific model and its downstream dependents
uv run dbt build --select 'clean_snapshot_proposals+'

# Build a specific model and its upstream dependencies
uv run dbt build --select '+governance_activity'
```

### Introspection

```bash
# Parse project and regenerate manifest.json (no build)
uv run dbt parse

# List all models
uv run dbt ls --resource-type model

# List all sources
uv run dbt ls --resource-type source

# List all tests
uv run dbt ls --resource-type test

# Show compiled SQL for a model
uv run dbt show --select 'governance_activity'

# Generate dbt docs
uv run dbt docs generate

# Serve dbt docs locally
uv run dbt docs serve
```

### Cleanup

```bash
# Remove dbt artifacts (target/, dbt_packages/)
uv run dbt clean
```

## DuckDB (Warehouse)

> **Schema naming:** dbt writes tables with DuckDB's `main_` database prefix. When you query from outside dbt, use `main_silver.<table>` or `main_gold.<table>`.

```bash
# Open interactive DuckDB shell
duckdb warehouse/ens_retro.duckdb

# Run a query directly
duckdb warehouse/ens_retro.duckdb -c "SELECT count(*) FROM main_gold.governance_activity;"

# List all schemas
duckdb warehouse/ens_retro.duckdb -c "SELECT schema_name FROM information_schema.schemata;"

# List all tables in the gold schema
duckdb warehouse/ens_retro.duckdb -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main_gold';"

# Preview the delegate scorecard
duckdb warehouse/ens_retro.duckdb -c "SELECT * FROM main_gold.delegate_scorecard LIMIT 10;"

# Export a table to CSV
duckdb warehouse/ens_retro.duckdb -c "COPY main_gold.governance_activity TO 'output.csv' (HEADER, DELIMITER ',');"

# Export to Parquet
duckdb warehouse/ens_retro.duckdb -c "COPY main_gold.delegate_scorecard TO 'scorecard.parquet' (FORMAT PARQUET);"

# Read a bronze JSON file directly (no dbt needed)
duckdb -c "SELECT count(*) FROM read_json_auto('bronze/governance/snapshot_proposals.json');"
```

### Useful Queries

```sql
-- Count records in all gold tables
SELECT 'governance_activity' AS tbl, count(*) AS rows FROM main_gold.governance_activity
UNION ALL SELECT 'governance_discourse_activity', count(*) FROM main_gold.governance_discourse_activity
UNION ALL SELECT 'delegate_scorecard', count(*) FROM main_gold.delegate_scorecard
UNION ALL SELECT 'treasury_summary', count(*) FROM main_gold.treasury_summary
UNION ALL SELECT 'participation_index', count(*) FROM main_gold.participation_index
UNION ALL SELECT 'decentralization_index', count(*) FROM main_gold.decentralization_index;

-- Top 10 delegates by voting power
SELECT address, ens_name, voting_power, participation_rate
FROM main_gold.delegate_scorecard
ORDER BY voting_power DESC
LIMIT 10;

-- Governance activity summary by source
SELECT source, count(*) AS proposals, avg(for_pct) AS avg_for_pct
FROM main_gold.governance_activity
GROUP BY source;

-- Decentralization metrics (long format)
SELECT metric, value FROM main_gold.decentralization_index;

-- Participation metrics (long format)
SELECT metric, value FROM main_gold.participation_index;
```

## Dashboard (Streamlit)

```bash
# Run the full dashboard locally
uv run streamlit run dashboards/app.py

# Run the /Chat sub-page only
uv run streamlit run dashboards/pages/Chat.py
```

## MCP API server (FastAPI + MCP)

```bash
# Generate a secret key and run the API locally
export AGENT_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
cd dashboards
uv run uvicorn api:app --host 0.0.0.0 --port 8001 --reload

# Smoke test the endpoints (in another shell)
curl http://localhost:8001/                                # HTML landing page

curl -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

curl -X GET http://localhost:8001/api/tables \
  -H "Authorization: Bearer $AGENT_API_KEY"
```

## Code Quality

```bash
# Lint everything with ruff
uv run ruff check .

# Lint and auto-fix
uv run ruff check . --fix

# Format
uv run ruff format .

# Check format without modifying
uv run ruff format --check .

# Run all dashboard + API tests (106 cases)
cd dashboards && uv run pytest tests/ -v
```

## Environment Variables

See `.env.example` for the full list. Quick reference:

| Variable | Needed by | Purpose |
|---|---|---|
| `DAGSTER_HOME` | Dagster | Absolute path to repo's `.dagster/` dir |
| `ETHERSCAN_API_KEY` | `etherscan_api.py` | On-chain event fetching |
| `OSO_API_KEY` | `oso_api.py` | GitHub activity metrics |
| `TALLY_API_KEY` | Legacy only | Tally is frozen; only needed if you try to re-run the (now file-sentinel) tally assets |
| `OPENAI_API_KEY` | Dashboard + ChatKit | Mint ChatKit session tokens, sync vector store |
| `OPENAI_WORKFLOWS_API_KEY` | Dashboard ChatKit | Agent Builder workflow calls |
| `WORKFLOW_ID` | Dashboard ChatKit | Agent Builder workflow ID |
| `AGENT_API_KEY` | MCP API (`api.py`) | Bearer token protecting `/api/*` and `/mcp` |

The `.env` file is loaded automatically by Dagster, Streamlit, and the API via `python-dotenv`. For standalone scripts, either source the file manually or rely on the `load_dotenv()` calls already embedded in most entry points.
