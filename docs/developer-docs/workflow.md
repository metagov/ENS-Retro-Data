# Workflow Guide

Step-by-step instructions for common workflows.

## First-Time Setup

```bash
# 1. Clone the repository
git clone <repo-url> && cd ENS-Retro-Data

# 2. Install dependencies
uv sync

# 3. Install dbt packages
uv run dbt deps --project-dir infra/dbt --profiles-dir infra/dbt

# 4. Create .env with your Tally API key
echo 'TALLY_API_KEY=your_key_here' > .env

# 5. Generate dbt manifest
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt

# 6. Generate taxonomy seeds
uv run python scripts/generate_taxonomy_seeds.py

# 7. Start Dagster
uv run dagster dev
```

Open `http://localhost:3000` in your browser.

## Full Pipeline Run (Dagster UI)

This materializes everything: fetches bronze data from APIs, runs dbt staging/silver/gold models, executes all tests and checks.

1. Open Dagster UI at `http://localhost:3000`
2. Go to **Assets** tab
3. Click **Materialize all** (top right)
4. Watch the run in the **Runs** tab

### What happens in order:

```
1. Bronze fetchers run in parallel:
   ├── snapshot_proposals  (Snapshot API → JSON)
   ├── tally_proposals     (Tally API → JSON)
   ├── tally_delegates     (Tally API → JSON)
   ├── votingpower_delegates (file check)
   ├── delegations         (file check)
   ├── token_distribution  (file check)
   ├── treasury_flows      (file check)
   ├── grants              (file check)
   ├── compensation        (file check)
   ├── delegate_profiles   (file check)
   └── forum_posts         (file check)

2. Dependent bronze fetchers:
   ├── snapshot_votes      (depends on snapshot_proposals)
   └── tally_votes         (depends on tally_proposals)

3. Asset checks run on bronze:
   ├── Row count checks (5)
   └── GE suite validations (5)

4. dbt build runs all models in dependency order:
   ├── Staging views (13 models)
   ├── Silver tables (11 models)
   ├── Gold tables (5 models)
   └── dbt tests (~30 tests)
```

## Bronze-Only Run

If you only want to refresh the raw data without rebuilding the warehouse:

### From Dagster UI:
1. Go to **Assets** tab
2. Select all assets in the `bronze` group
3. Click **Materialize selected**

### From CLI:
```bash
uv run dagster asset materialize --select 'group:bronze'
```

## dbt-Only Run

If bronze data already exists and you only want to rebuild the warehouse:

```bash
uv run dbt build --project-dir infra/dbt --profiles-dir infra/dbt
```

Or selectively:
```bash
# Only silver layer
uv run dbt build --select 'silver.*' --project-dir infra/dbt --profiles-dir infra/dbt

# Only gold layer
uv run dbt build --select 'gold.*' --project-dir infra/dbt --profiles-dir infra/dbt

# Single model + downstream
uv run dbt build --select 'clean_tally_delegates+' --project-dir infra/dbt --profiles-dir infra/dbt
```

## Adding a New Data Source

### 1. Create the API client (if API-based)

Create `infra/ingest/<source>_api.py` with fetch functions:

```python
def fetch_<source>_data() -> list[dict]:
    """Fetch data from the API and return raw records."""
    ...
```

### 2. Add the bronze asset

In `infra/ingest/assets.py`:

```python
@asset(group_name="bronze", compute_kind="api")
def new_source(context: AssetExecutionContext) -> None:
    data = fetch_new_source_data()
    _write_json(data, "<subdomain>", "<filename>.json", context,
                source="<api>", method="description of fetch method")
```

### 3. Add dbt source definition

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
'bronze_<domain>.new_source': "read_json_auto('../../bronze/<domain>/<filename>.json')",
```

### 5. Create staging model

Create `infra/dbt/models/staging/stg_new_source.sql`:

```sql
select * from {{ source('bronze_<domain>', 'new_source') }}
```

### 6. Create silver model

Create `infra/dbt/models/silver/clean_new_source.sql` with transformations.

### 7. Update the translator

In `infra/dbt_project.py`, add to `_SOURCE_TO_ASSET_KEY`:

```python
("bronze_<domain>", "new_source"): AssetKey("new_source"),
```

### 8. Add metadata.json entry

Update `bronze/<domain>/metadata.json` with the new file entry.

### 9. Regenerate manifest

```bash
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt
```

### 10. Add validation (optional)

- Add a GE expectation suite in `infra/great_expectations/expectations/`
- Add asset checks in `infra/validate/checks.py`
- Add dbt tests in `_staging.yml` and `_silver.yml`

## Converting a Sentinel to an Active Fetcher

When you're ready to automate data collection for a currently-sentinel source:

1. Create an API client in `infra/ingest/` (e.g., `forum_api.py`)
2. Replace the sentinel asset in `infra/ingest/assets.py` with an active fetcher (change `compute_kind="file"` to `compute_kind="api"`)
3. Add the file entry to the domain's `metadata.json` (currently `"files": {}`)
4. Remove `severity: warn` from that model's dbt tests in `_staging.yml` and `_silver.yml`
5. Add GE expectations and row-count checks in `infra/validate/checks.py`
6. Register checks in `infra/definitions.py`
7. Run `dbt parse` to regenerate the manifest

## Querying the Warehouse

After a full pipeline run, the DuckDB warehouse contains all data:

```bash
uv run duckdb warehouse/ens_retro.duckdb
```

```sql
-- See what's available
SELECT schema_name FROM information_schema.schemata;
SELECT table_schema, table_name FROM information_schema.tables ORDER BY 1, 2;

-- Gold layer queries
SELECT * FROM gold.governance_activity LIMIT 5;
SELECT * FROM gold.delegate_scorecard ORDER BY voting_power DESC LIMIT 10;
SELECT * FROM gold.participation_index;
SELECT * FROM gold.decentralization_index;
```

## Updating After Code Changes

After modifying dbt models, macros, or Python assets:

```bash
# 1. Regenerate dbt manifest
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt

# 2. If Dagster is running, click "Reload definitions" in the UI
#    Or restart dagster dev

# 3. Re-materialize affected assets
```

## Troubleshooting

### "Manifest not found" error
```bash
uv run dbt parse --project-dir infra/dbt --profiles-dir infra/dbt
```

### "No files found that match the pattern"
A bronze JSON file is missing. Either:
- Run the bronze fetcher for that source
- Place the data file manually in the correct `bronze/` subdirectory
- Use selective dbt builds to skip missing sources: `dbt build --select 'staging.stg_snapshot_*'`

### dbt tests failing with `severity: error`
Check if the failing test is on a sentinel model. If so, change the test severity to `warn` in `_staging.yml` or `_silver.yml`.

### Rate limit errors (429)
The API clients have built-in 60-second backoff. If you hit rate limits, wait and retry. For Tally, ensure your API key is valid.

### DuckDB lock error
Only one process can write to the DuckDB file at a time. Close any other `duckdb` sessions or Dagster runs before building.
