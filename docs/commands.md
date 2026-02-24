# Command Reference

Every command in this project, organized by category.

## Setup & Installation

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install all dependencies
uv sync

# Install dev dependencies (pytest, ruff)
uv sync --extra dev

# Install dbt packages (dbt_utils)
uv run dbt deps --project-dir infra/dbt --profiles-dir infra/dbt

# Generate dbt manifest (required before first Dagster run)
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt

# Generate dbt seed CSVs from taxonomy.yaml
uv run python scripts/generate_taxonomy_seeds.py

# Create .env file with API keys
echo 'TALLY_API_KEY=your_key_here' > .env
```

## Dagster (Orchestration)

### Start Dagster UI

```bash
# Start the Dagster webserver (default: http://localhost:3000)
uv run dagster dev
```

This loads the Dagster definitions from `infra/definitions.py` (configured via `[tool.dagster]` in `pyproject.toml`).

### Dagster UI Operations

Once the UI is running at `http://localhost:3000`:

| Action                        | How                                                              |
|-------------------------------|------------------------------------------------------------------|
| View all assets               | Go to **Assets** tab                                             |
| Materialize everything        | Click **Materialize all** button                                 |
| Materialize specific asset    | Click asset → **Materialize**                                    |
| Run bronze fetchers only      | Select bronze assets → **Materialize selected**                  |
| View asset checks             | Click asset → **Checks** tab                                     |
| View run logs                 | Go to **Runs** tab → click a run                                 |
| View asset lineage graph      | Go to **Assets** → **Global asset lineage**                      |
| Reload definitions            | Click **Reload definitions** in the top bar after code changes   |

### Dagster CLI Commands

```bash
# Materialize all assets (bronze fetch + dbt build + checks)
uv run dagster asset materialize --select '*'

# Materialize only bronze assets
uv run dagster asset materialize --select 'group:bronze'

# Materialize a single asset
uv run dagster asset materialize --select 'snapshot_proposals'

# Run all asset checks
uv run dagster asset check --select '*'

# List all registered assets
uv run dagster asset list
```

## dbt (SQL Transformations)

All dbt commands require `--project-dir infra/dbt --profiles-dir infra/dbt`.

### Build Commands

```bash
# Build everything (run models + run tests + load seeds)
uv run dbt build --project-dir infra/dbt --profiles-dir infra/dbt

# Run only models (no tests)
uv run dbt run --project-dir infra/dbt --profiles-dir infra/dbt

# Run only tests
uv run dbt test --project-dir infra/dbt --profiles-dir infra/dbt

# Load seed data
uv run dbt seed --project-dir infra/dbt --profiles-dir infra/dbt
```

### Selective Builds

```bash
# Build only staging models
uv run dbt build --select 'staging.*' --project-dir infra/dbt --profiles-dir infra/dbt

# Build only silver models
uv run dbt build --select 'silver.*' --project-dir infra/dbt --profiles-dir infra/dbt

# Build only gold models
uv run dbt build --select 'gold.*' --project-dir infra/dbt --profiles-dir infra/dbt

# Build a specific model and its downstream dependents
uv run dbt build --select 'clean_snapshot_proposals+' --project-dir infra/dbt --profiles-dir infra/dbt

# Build a specific model and its upstream dependencies
uv run dbt build --select '+governance_activity' --project-dir infra/dbt --profiles-dir infra/dbt
```

### Introspection

```bash
# Parse project and generate manifest.json (no build)
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt

# List all models
uv run dbt ls --resource-type model --project-dir infra/dbt --profiles-dir infra/dbt

# List all sources
uv run dbt ls --resource-type source --project-dir infra/dbt --profiles-dir infra/dbt

# List all tests
uv run dbt ls --resource-type test --project-dir infra/dbt --profiles-dir infra/dbt

# Show compiled SQL for a model
uv run dbt show --select 'governance_activity' --project-dir infra/dbt --profiles-dir infra/dbt

# Generate dbt docs
uv run dbt docs generate --project-dir infra/dbt --profiles-dir infra/dbt

# Serve dbt docs locally
uv run dbt docs serve --project-dir infra/dbt --profiles-dir infra/dbt
```

### Cleanup

```bash
# Remove dbt artifacts (target/, dbt_packages/)
uv run dbt clean --project-dir infra/dbt --profiles-dir infra/dbt
```

## DuckDB (Warehouse)

```bash
# Open interactive DuckDB shell on the warehouse
uv run duckdb warehouse/ens_retro.duckdb

# Run a query directly
uv run duckdb warehouse/ens_retro.duckdb -c "SELECT count(*) FROM gold.governance_activity;"

# List all schemas
uv run duckdb warehouse/ens_retro.duckdb -c "SELECT schema_name FROM information_schema.schemata;"

# List all tables in a schema
uv run duckdb warehouse/ens_retro.duckdb -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold';"

# Preview a gold table
uv run duckdb warehouse/ens_retro.duckdb -c "SELECT * FROM gold.delegate_scorecard LIMIT 10;"

# Export a table to CSV
uv run duckdb warehouse/ens_retro.duckdb -c "COPY gold.governance_activity TO 'output.csv' (HEADER, DELIMITER ',');"

# Export a table to Parquet
uv run duckdb warehouse/ens_retro.duckdb -c "COPY gold.delegate_scorecard TO 'scorecard.parquet' (FORMAT PARQUET);"

# Read a bronze JSON file directly (no dbt needed)
uv run duckdb -c "SELECT count(*) FROM read_json_auto('bronze/governance/snapshot_proposals.json');"
```

### Useful Queries

```sql
-- Count records in all gold tables
SELECT 'governance_activity' as tbl, count(*) as rows FROM gold.governance_activity
UNION ALL SELECT 'delegate_scorecard', count(*) FROM gold.delegate_scorecard
UNION ALL SELECT 'treasury_summary', count(*) FROM gold.treasury_summary
UNION ALL SELECT 'participation_index', count(*) FROM gold.participation_index
UNION ALL SELECT 'decentralization_index', count(*) FROM gold.decentralization_index;

-- Top 10 delegates by voting power
SELECT address, ens_name, voting_power, participation_rate
FROM gold.delegate_scorecard
ORDER BY voting_power DESC LIMIT 10;

-- Governance activity summary
SELECT source, count(*) as proposals, avg(for_pct) as avg_for_pct
FROM gold.governance_activity
GROUP BY source;

-- Decentralization metrics
SELECT * FROM gold.decentralization_index;

-- Participation metrics
SELECT * FROM gold.participation_index;
```

## Bronze Data Fetching (Standalone Scripts)

```bash
# Fetch Snapshot proposals and votes (standalone, outside Dagster)
uv run python bronze/governance/scripts/export_ens_tally.py

# Generate taxonomy seed CSVs from taxonomy.yaml
uv run python scripts/generate_taxonomy_seeds.py
```

## Code Quality

```bash
# Lint with ruff
uv run ruff check infra/

# Lint and auto-fix
uv run ruff check --fix infra/

# Format with ruff
uv run ruff format infra/

# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Type check (if mypy/pyright installed)
uv run mypy infra/
```

## Git

```bash
# Check status (see what's changed)
git status

# Stage specific files
git add infra/ingest/assets.py infra/validate/checks.py

# Commit
git commit -m "description of changes"

# Push current branch
git push origin governance-scripts
```

## Environment Variables

| Variable        | Required | Description                              |
|-----------------|----------|------------------------------------------|
| `TALLY_API_KEY` | Yes      | API key for Tally GraphQL API            |
| `DAGSTER_HOME`  | No       | Override Dagster's home directory         |

The `.env` file is loaded automatically by Dagster via `python-dotenv`. For standalone scripts, load it manually or export the variables.
