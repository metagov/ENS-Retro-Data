# ENS-Retro-Data

Data infrastructure for the ENS DAO retrospective evaluation. Implements a medallion architecture (bronze/silver/gold) orchestrated by Dagster with dbt for SQL transforms.

## Architecture

```
bronze/                Raw data — append-only JSON from each source
  governance/          Snapshot proposals/votes, Tally proposals/votes/delegates
  on-chain/            Delegations, token distribution, treasury flows
  forum/               Governance forum posts
  financial/           Compensation records
  grants/              Grant applications and awards
  interviews/          Stakeholder interviews, delegate profiles
  docs/                Governance documents
  github/              Repository activity

infra/                 All pipeline infrastructure
  ingest/              Bronze layer — API fetchers and sentinel assets
    snapshot_api.py    Snapshot GraphQL client
    tally_api.py       Tally GraphQL client + response flatteners
    assets.py          Dagster bronze asset definitions
  transform/           (Handled by dbt silver models)
  materialize/         (Handled by dbt gold models)
  validate/            Asset checks for bronze data quality
  dbt/                 dbt project — SQL transforms for staging/silver/gold
    models/staging/    Staging views that read bronze JSON/CSV files
    models/silver/     Cleaned, typed, deduplicated tables
    models/gold/       Analysis-ready composite views
    macros/            Custom dbt macros (source override, wei conversion, etc.)
    seeds/             Taxonomy reference CSVs (generated from taxonomy.yaml)
    tests/             Custom dbt data tests
  great_expectations/  (Placeholder for GE integration)
  definitions.py       Central Dagster definitions (assets, checks, resources)
  dbt_project.py       dagster-dbt project config + source-to-asset translator
  dbt_assets.py        @dbt_assets decorator wiring dbt models into Dagster
  resources.py         Dagster resources (TallyApiConfig)

warehouse/             DuckDB database output (created at runtime by dbt)
                       Contains all silver/gold tables after materialization

scripts/               Standalone utility scripts
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Tally API key (set in `.env` as `TALLY_API_KEY`)

## Quick Start

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --extra dev

# Install dbt packages
cd infra/dbt && uv run dbt deps && cd ../..

# Generate taxonomy seed CSVs from taxonomy.yaml
uv run python scripts/generate_taxonomy_seeds.py

# Set your Tally API key
echo 'TALLY_API_KEY=your_key_here' > .env

# Launch Dagster UI (opens at http://localhost:3000)
DAGSTER_HOME=$(pwd)/.dagster uv run dagster dev
```

## Command Reference

### Setup & Dependencies

| Command | Description |
|---|---|
| `uv sync` | Install all Python dependencies from pyproject.toml |
| `uv sync --extra dev` | Install dev dependencies (pytest, ruff) |
| `cd infra/dbt && uv run dbt deps` | Install dbt packages (dbt_utils) |
| `uv run python scripts/generate_taxonomy_seeds.py` | Generate dbt seed CSVs from taxonomy.yaml |

### Dagster (Orchestration)

| Command | Description |
|---|---|
| `uv run dagster dev` | Launch Dagster UI at http://localhost:3000 |
| `uv run dagster asset materialize -m infra.definitions --select snapshot_proposals` | Materialize a single bronze asset (fetches from API) |
| `uv run dagster asset materialize -m infra.definitions --select snapshot_proposals snapshot_votes` | Materialize multiple bronze assets |
| `uv run dagster asset materialize -m infra.definitions --select '*'` | Materialize all assets (bronze + dbt) |
| `uv run dagster asset check -m infra.definitions` | Run all asset checks |

### dbt (SQL Transforms)

All dbt commands must be run from `infra/dbt/`:

| Command | Description |
|---|---|
| `uv run dbt build` | Run all models + tests (staging, silver, gold) |
| `uv run dbt run` | Run all models without tests |
| `uv run dbt test` | Run all dbt tests only |
| `uv run dbt run --select staging` | Run only staging models |
| `uv run dbt run --select silver` | Run only silver models |
| `uv run dbt run --select gold` | Run only gold models |
| `uv run dbt seed` | Load taxonomy seed CSVs into DuckDB |
| `uv run dbt parse` | Parse project and generate manifest.json |
| `uv run dbt deps` | Install dbt packages |
| `uv run dbt compile` | Compile SQL without executing |

### DuckDB (Query the Warehouse)

| Command | Description |
|---|---|
| `duckdb warehouse/ens_retro.duckdb` | Open interactive DuckDB shell |
| `duckdb warehouse/ens_retro.duckdb "SELECT count(*) FROM gold.governance_activity"` | Query gold layer |
| `duckdb warehouse/ens_retro.duckdb "SHOW ALL TABLES"` | List all tables/views |
| `duckdb warehouse/ens_retro.duckdb "SELECT * FROM gold.delegate_scorecard LIMIT 10"` | Preview delegate scorecard |

### Code Quality

| Command | Description |
|---|---|
| `uv run ruff check .` | Run Python linter |
| `uv run ruff check . --fix` | Auto-fix lint issues |
| `uv run ruff format .` | Format Python code |
| `uv run pytest` | Run Python tests |

## Running the Bronze Indexers from Dagster UI

1. **Start Dagster:**
   ```bash
   DAGSTER_HOME=$(pwd)/.dagster uv run dagster dev
   ```

2. **Open the UI:** Navigate to http://localhost:3000

3. **View the asset graph:** Click "Assets" in the top nav. You'll see the full pipeline:
   ```
   bronze (API fetchers) → staging (dbt views) → silver (dbt tables) → gold (dbt tables)
   ```

4. **Materialize bronze assets:**
   - Click on any bronze asset (e.g., `snapshot_proposals`)
   - Click "Materialize" in the top-right
   - The asset will call the Snapshot/Tally API and write JSON to `bronze/`

5. **Materialize downstream:**
   - Select a bronze asset, then click "Materialize all" to run it + all downstream dbt models
   - Or select specific dbt assets to materialize individually

6. **Run checks:**
   - After materializing bronze assets, the row-count checks auto-run
   - View check results in the asset detail panel under "Checks"

7. **Recommended materialization order:**
   - `snapshot_proposals` → `snapshot_votes` (votes depend on proposals)
   - `tally_proposals` → `tally_votes` (votes depend on proposals)
   - `tally_delegates` (independent)
   - Then materialize any dbt staging/silver/gold assets downstream

## Data Sources

| Source | Platform | Expected Records | Bronze File |
|---|---|---|---|
| Snapshot proposals | Snapshot.org | ~90 | `bronze/governance/snapshot_proposals.json` |
| Snapshot votes | Snapshot.org | ~47,551 | `bronze/governance/snapshot_votes.json` |
| Tally proposals | Tally | ~62 | `bronze/governance/tally_proposals.json` |
| Tally votes | Tally | ~9,550 | `bronze/governance/tally_votes.json` |
| Tally delegates | Tally | ~37,876 | `bronze/governance/tally_delegates.json` |
| Votingpower.xyz | CSV export | varies | `bronze/governance/votingpower-xyz/*.csv` |
| Delegations | On-chain | TBD | `bronze/on-chain/delegations.json` |
| Token distribution | On-chain | TBD | `bronze/on-chain/token_distribution.json` |
| Treasury flows | On-chain | TBD | `bronze/on-chain/treasury_flows.json` |
| Grants | Grants portal | TBD | `bronze/grants/grants.json` |
| Compensation | Forum/On-chain | TBD | `bronze/financial/compensation.json` |
| Delegate profiles | Interviews | TBD | `bronze/interviews/delegate_profiles.json` |
| Forum posts | Discourse | TBD | `bronze/forum/forum_posts.json` |

## Pipeline Assets

- **42 assets** across four layers (14 bronze, 13 staging, 11 silver, 5 gold)
- **5 asset checks** for bronze row counts
- dbt tests for silver taxonomy conformance and gold completeness
- Full dependency graph visible in Dagster UI

## Key Files

- `taxonomy.yaml` — Controlled vocabularies (single source of truth)
- `bronze/*/metadata.json` — Schema hints, expected record counts, provenance
- `infra/definitions.py` — Central Dagster definitions entry point
- `infra/dbt/dbt_project.yml` — dbt project configuration
- `.env` — API keys (not committed)
