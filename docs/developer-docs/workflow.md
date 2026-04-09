# Workflow Guide

Step-by-step instructions for common workflows.

## First-Time Setup

```bash
# 1. Install git-lfs and clone (the warehouse + bronze data live in LFS)
git lfs install
git clone https://github.com/metagov/ENS-Retro-Data.git
cd ENS-Retro-Data

# 2. Install dependencies
uv sync --extra dev

# 3. Install dbt packages
cd infra/dbt && uv run dbt deps && cd ../..

# 4. Set up your .env
cp .env.example .env
# then edit to fill in ETHERSCAN_API_KEY, OSO_API_KEY, OPENAI_API_KEY, etc.

# 5. Generate dbt manifest
cd infra/dbt && uv run dbt parse && cd ../..

# 6. Generate taxonomy seeds
uv run python scripts/generate_taxonomy_seeds.py

# 7. Start Dagster
DAGSTER_HOME=$(pwd)/.dagster uv run dagster dev
```

Open `http://localhost:3000` in your browser.

## Full Pipeline Run (Dagster UI)

This materializes everything: fetches bronze data from APIs, runs dbt staging/silver/gold models, executes tests and checks.

1. Open Dagster UI at `http://localhost:3000`
2. Go to **Assets** tab
3. Click **Materialize all** (top right)
4. Watch the run in the **Runs** tab

### What happens in order

```
1. Bronze fetchers run in parallel (per-group concurrency):

   bronze_governance:
     ├── snapshot_proposals  (Snapshot API → JSON)
     ├── snapshot_votes      (depends on snapshot_proposals)
     ├── tally_proposals     (file sentinel — frozen)
     ├── tally_votes         (file sentinel, depends on tally_proposals)
     ├── tally_delegates     (file sentinel)
     └── votingpower_delegates (file sentinel — manual CSV drop)

   bronze_onchain:
     ├── delegations           (Etherscan → JSON)
     ├── token_distribution    (Etherscan → JSON)
     └── treasury_flows        (Etherscan → JSON)

   bronze_financial:
     ├── ens_ledger_transactions (file sentinel — maintained CSV)
     ├── ens_wallet_balances     (Safe API)
     └── ens_safe_transactions   (Safe API)

   bronze_grants:
     ├── smallgrants_proposals (SmallGrants Snapshot space)
     └── smallgrants_votes     (depends on smallgrants_proposals)

   bronze_forum:
     └── forum_topics          (Discourse API)

   bronze_github:
     └── 3 OSO assets          (OSO GraphQL)

2. Bronze asset checks (governance only):
   ├── Row count checks (5)
   └── GE suite validations (5)

3. dbt build runs all models in dependency order:
   ├── 18 staging views
   ├── 16 silver tables
   ├── 6 gold tables
   └── ~66 dbt tests

4. vector_store_sync_sensor fires after gold materialization,
   re-exporting gold tables to docs/vector-store-exports/ and
   syncing 22 files (gold exports + docs/ + config) to the
   OpenAI vector store (if OPENAI_API_KEY is set).
```

## Bronze-Only Run

To refresh the raw data without rebuilding the warehouse:

### From Dagster UI

1. Go to **Assets** tab
2. Select all assets in the bronze groups (`bronze_governance`, `bronze_onchain`, etc.)
3. Click **Materialize selected**

### From CLI

```bash
uv run dagster asset materialize -m infra.definitions --select 'group:bronze_governance'
uv run dagster asset materialize -m infra.definitions --select 'group:bronze_onchain'
```

Or everything bronze at once:

```bash
uv run dagster asset materialize -m infra.definitions \
    --select 'group:bronze_governance,group:bronze_onchain,group:bronze_financial,group:bronze_grants,group:bronze_forum,group:bronze_github'
```

## dbt-Only Run

If bronze data already exists and you only want to rebuild the warehouse:

```bash
cd infra/dbt
uv run dbt build
```

Or selectively:

```bash
# Only silver layer
uv run dbt build --select 'silver.*'

# Only gold layer
uv run dbt build --select 'gold.*'

# Single model + downstream
uv run dbt build --select 'clean_tally_delegates+'
```

## Adding a New Data Source

### 1. Create the API client

Create `infra/ingest/<source>_api.py` with fetch functions:

```python
def fetch_<source>_data() -> list[dict]:
    """Fetch data from the API and return raw records."""
    ...
```

Follow the error-handling pattern used by existing clients (60s backoff on HTTP 429, structured logging).

### 2. Add the bronze asset

In `infra/ingest/assets.py`:

```python
@asset(group_name="bronze_<domain>", compute_kind="api")
def new_source(context: AssetExecutionContext) -> None:
    data = fetch_new_source_data()
    _write_json(data, "<subdomain>", "<filename>.json", context,
                source="<api>", method="description of fetch method")
```

If the asset needs an API key, add a resource to `infra/resources.py` and inject it:

```python
@asset(group_name="bronze_<domain>", compute_kind="api")
def new_source(context, my_config: MyApiConfig) -> None:
    data = fetch_new_source_data(api_key=my_config.api_key)
    ...
```

Register the resource in `infra/definitions.py`.

### 3. Add dbt source entry

In `infra/dbt/models/staging/_sources.yml`, add the source table:

```yaml
- name: bronze_<domain>
  tables:
    - name: new_source
      meta:
        external_location: "../../bronze/<domain>/<filename>.json"
```

### 4. Update the source macro

In `infra/dbt/macros/source.sql`, add the mapping:

```sql
'bronze_<domain>.new_source':
    "read_json_auto('../../bronze/<domain>/<filename>.json')",
```

### 5. Create staging model

Create `infra/dbt/models/staging/stg_new_source.sql`:

```sql
select * from {{ source('bronze_<domain>', 'new_source') }}
```

### 6. Create silver model

Create `infra/dbt/models/silver/clean_new_source.sql` with transformations (lowercase addresses, cast types, etc.).

### 7. Update the Dagster translator

In `infra/dbt_project.py`, add to `_SOURCE_TO_ASSET_KEY`:

```python
("bronze_<domain>", "new_source"): AssetKey("new_source"),
```

This tells Dagster that dbt's `{{ source() }}` reference depends on your new Python asset.

### 8. Add metadata.json entry

Update `bronze/<domain>/metadata.json` with the new file entry.

### 9. Regenerate the dbt manifest

```bash
cd infra/dbt && uv run dbt parse
```

### 10. Add validation (optional but recommended)

- Add a GE expectation suite in `infra/great_expectations/expectations/`
- Add asset checks in `infra/validate/checks.py` (decorator auto-registers)
- Add dbt tests in `_staging.yml` and `_silver.yml`

## Querying the Warehouse

After a full pipeline run, the DuckDB warehouse contains all data:

```bash
duckdb warehouse/ens_retro.duckdb
```

```sql
-- See what's available
SELECT schema_name FROM information_schema.schemata;
SELECT table_schema, table_name FROM information_schema.tables ORDER BY 1, 2;

-- Gold layer queries (note the main_ prefix)
SELECT * FROM main_gold.governance_activity LIMIT 5;
SELECT * FROM main_gold.delegate_scorecard ORDER BY voting_power DESC LIMIT 10;
SELECT * FROM main_gold.participation_index;
SELECT * FROM main_gold.decentralization_index;
```

## Updating After Code Changes

After modifying dbt models, macros, or Python assets:

```bash
# 1. Regenerate dbt manifest
cd infra/dbt && uv run dbt parse && cd ../..

# 2. If Dagster is running, click "Reload definitions" in the UI
#    Or restart: DAGSTER_HOME=$(pwd)/.dagster uv run dagster dev

# 3. Re-materialize affected assets via the UI or CLI
```

## Troubleshooting

### "Manifest not found" error
```bash
cd infra/dbt && uv run dbt parse
```

### "No files found that match the pattern"
A bronze JSON file is missing. Either:
- Run the bronze fetcher for that source
- Place the data file manually in the correct `bronze/` subdirectory
- Use selective dbt builds to skip missing sources: `dbt build --select 'staging.stg_snapshot_*'`

### LFS pointer files instead of real data
You cloned without `git lfs install`. Fix:
```bash
git lfs install
git lfs pull
```

### Rate limit errors (429)
The API clients have built-in 60-second backoff. If you hit rate limits, wait and retry. Check that your API key env vars are set.

### DuckDB lock error
Only one process can write to the DuckDB file at a time. Close any other `duckdb` sessions or Dagster runs before building.

### `main_gold.foo does not exist`
dbt writes into schemas named `main_<layer>` under DuckDB's default database. Make sure you're using the full prefix (`main_gold.governance_activity`, not `gold.governance_activity`) when querying from outside dbt.
