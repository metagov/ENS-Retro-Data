# API Reference

Public functions and classes in the `infra` Python package.

## infra.definitions

**File:** `infra/definitions.py`

The central Dagster entry point. Loaded via `[tool.dagster] module_name = "infra.definitions"` in `pyproject.toml`.

### `defs: Definitions`
The Dagster `Definitions` object combining all assets, checks, and resources.

**Contains:**
- `assets`: 13 bronze Python assets + 1 dbt asset group (29 models)
- `asset_checks`: 10 checks (5 row-count + 5 GE suites)
- `resources`: `dbt` (DbtCliResource), `tally_config` (TallyApiConfig)

---

## infra.resources

**File:** `infra/resources.py`

### `class TallyApiConfig(ConfigurableResource)`
Dagster resource holding the Tally API key.

**Fields:**
| Field     | Type | Description                |
|-----------|------|----------------------------|
| `api_key` | str  | Tally GraphQL API key      |

**Usage in asset:**
```python
@asset
def tally_proposals(context, tally_config: TallyApiConfig) -> None:
    org = fetch_organization(tally_config.api_key)
```

---

## infra.dbt_project

**File:** `infra/dbt_project.py`

### `dbt_project: DbtProject`
Configured dbt project instance pointing to `infra/dbt/`. Calls `prepare_if_dev()` at import time to generate the manifest.

### `class EnsDbtTranslator(DagsterDbtTranslator)`
Maps dbt sources to upstream Dagster bronze asset keys.

**Method:**
```python
def get_asset_key(self, dbt_resource_props: dict) -> AssetKey
```
- For `resource_type == "source"`: looks up `(source_name, table_name)` in `_SOURCE_TO_ASSET_KEY`
- Otherwise: delegates to `super().get_asset_key()`

---

## infra.dbt_assets

**File:** `infra/dbt_assets.py`

### `ens_dbt_assets(context, dbt: DbtCliResource)`
The `@dbt_assets` decorated function that runs `dbt build` for all models.

- Creates `warehouse/` directory before running dbt
- Uses `EnsDbtTranslator` for source-to-asset mapping
- Streams dbt CLI output back to Dagster

---

## infra.ingest.snapshot_api

**File:** `infra/ingest/snapshot_api.py`

### `run_query(query: str) -> dict`
Execute a GraphQL query against the Snapshot API.

| Parameter | Type | Description           |
|-----------|------|-----------------------|
| `query`   | str  | GraphQL query string  |

**Returns:** Parsed JSON response dict.
**Raises:** `requests.HTTPError` on non-429 errors.
**Retry:** Waits 60s on HTTP 429.

### `fetch_snapshot_proposals() -> list[dict]`
Fetch all ENS Snapshot proposals.

**Returns:** List of raw proposal dicts (paginated, batch=100, ordered by `created` desc).

**Schema per record:**
```
id, title, body, choices, start, end, snapshot, state,
author, created, scores, scores_total, votes, quorum, type
```

### `fetch_snapshot_votes(proposals: list[dict]) -> list[dict]`
Fetch votes for the given proposals.

| Parameter   | Type        | Description                    |
|-------------|-------------|--------------------------------|
| `proposals` | list[dict]  | Proposals (must have `id` key) |

**Returns:** List of vote dicts with injected `proposal_id`.

**Schema per record:**
```
id, voter, choice, vp, created, proposal_id
```

---

## infra.ingest.tally_api

**File:** `infra/ingest/tally_api.py`

### `run_query(query: str, variables: dict | None, api_key: str) -> dict`
Execute a GraphQL query against the Tally API.

| Parameter   | Type            | Description               |
|-------------|-----------------|---------------------------|
| `query`     | str             | GraphQL query string      |
| `variables` | dict or None    | GraphQL variables         |
| `api_key`   | str             | Tally API key             |

### `fetch_organization(api_key: str) -> dict`
Fetch ENS organization metadata from Tally.

**Returns:** Dict with `id`, `name`, `slug`, `governorIds`, `tokenIds`, `proposalsCount`, `delegatesCount`, `delegatesVotesCount`, `tokenOwnersCount`.

### `fetch_tally_proposals(org_id: str, api_key: str) -> list[dict]`
Fetch all raw proposals for the organization (paginated, batch=50).

### `fetch_tally_votes(proposals: list[dict], api_key: str) -> list[dict]`
Fetch raw votes for given proposals (per-proposal, batch=100).

### `fetch_tally_delegates(org_id: str, api_key: str) -> list[dict]`
Fetch all raw delegates for the organization (paginated, batch=50, sorted by votes desc).

### `flatten_tally_proposals(raw_proposals: list[dict]) -> list[dict]`
Flatten nested API response into flat dicts.

**Output schema:** `id`, `title`, `description`, `status`, `proposer`, `start_block`, `end_block`, `for_votes`, `against_votes`, `abstain_votes`

### `flatten_tally_votes(raw_votes: list[dict]) -> list[dict]`
Flatten nested vote response.

**Output schema:** `id`, `voter`, `support`, `weight`, `proposal_id`, `reason`

### `flatten_tally_delegates(raw_delegates: list[dict]) -> list[dict]`
Flatten nested delegate response.

**Output schema:** `address`, `ens_name`, `voting_power`, `delegators_count`, `votes_count`, `proposals_count`, `statement`

---

## infra.ingest.assets

**File:** `infra/ingest/assets.py`

### Helper Functions

#### `_update_metadata(subdir, filename, *, status, records, file_size, source, method)`
Update a file entry in the subdomain's `metadata.json`.

| Parameter   | Type       | Description                              |
|-------------|------------|------------------------------------------|
| `subdir`    | str        | Bronze subdomain (e.g., `"governance"`)  |
| `filename`  | str        | File name within the subdomain           |
| `status`    | str        | `"present"`, `"missing"`, or `"planned"` |
| `records`   | int / None | Record count (optional)                  |
| `file_size` | int / None | File size in bytes (optional)            |
| `source`    | str        | Source identifier (default: `"dagster_pipeline"`) |
| `method`    | str / None | Description of fetch method              |

#### `_write_json(data, subdir, filename, context, *, source, method)`
Write a JSON array to a bronze file and update metadata provenance.

#### `_check_file_exists(subdir, filename, context)`
Check if a manually-placed file exists. Logs warning if missing.

### Active Fetcher Assets

| Asset                | Dependencies         | API              | Output File                              |
|----------------------|----------------------|------------------|------------------------------------------|
| `snapshot_proposals` | —                    | Snapshot GraphQL | `bronze/governance/snapshot_proposals.json` |
| `snapshot_votes`     | `snapshot_proposals` | Snapshot GraphQL | `bronze/governance/snapshot_votes.json`    |
| `tally_proposals`    | —                    | Tally GraphQL    | `bronze/governance/tally_proposals.json`   |
| `tally_votes`        | `tally_proposals`    | Tally GraphQL    | `bronze/governance/tally_votes.json`       |
| `tally_delegates`    | —                    | Tally GraphQL    | `bronze/governance/tally_delegates.json`   |

### Sentinel Assets

| Asset                    | Checked File                                              |
|--------------------------|-----------------------------------------------------------|
| `votingpower_delegates`  | `bronze/governance/votingpower-xyz/ens-delegates-*.csv`   |
| `delegations`            | `bronze/on-chain/delegations.json`                        |
| `token_distribution`     | `bronze/on-chain/token_distribution.json`                 |
| `treasury_flows`         | `bronze/on-chain/treasury_flows.json`                     |
| `grants`                 | `bronze/grants/grants.json`                               |
| `compensation`           | `bronze/financial/compensation.json`                      |
| `delegate_profiles`      | `bronze/interviews/delegate_profiles.json`                |
| `forum_posts`            | `bronze/forum/forum_posts.json`                           |

---

## infra.validate.checks

**File:** `infra/validate/checks.py`

### Helper Functions

#### `_count_json_records(subdir: str, filename: str) -> int`
Count records in a bronze JSON array file. Returns 0 if file missing.

#### `_load_bronze_df(subdir: str, filename: str) -> pd.DataFrame | None`
Load a bronze JSON file into a pandas DataFrame. Returns None if missing/empty.

#### `_run_ge_suite(subdir: str, filename: str, suite_name: str) -> AssetCheckResult`
Run a Great Expectations suite against a bronze file. Uses ephemeral GE context with pandas datasource.

### Asset Checks

| Check Function                     | Asset               | Type       | Description                    |
|------------------------------------|-----------------------|------------|--------------------------------|
| `check_snapshot_proposals_count`   | snapshot_proposals    | Row count  | Expected ~90 rows              |
| `check_snapshot_votes_count`       | snapshot_votes        | Row count  | Expected ~47,551 rows          |
| `check_tally_proposals_count`      | tally_proposals       | Row count  | Expected ~62 rows              |
| `check_tally_votes_count`          | tally_votes           | Row count  | Expected ~9,550 rows           |
| `check_tally_delegates_count`      | tally_delegates       | Row count  | Expected ~37,876 rows          |
| `check_ge_snapshot_proposals`      | snapshot_proposals    | GE suite   | Schema + value validation      |
| `check_ge_snapshot_votes`          | snapshot_votes        | GE suite   | Schema + value validation      |
| `check_ge_tally_proposals`         | tally_proposals       | GE suite   | Schema + value validation      |
| `check_ge_tally_votes`             | tally_votes           | GE suite   | Schema + value validation      |
| `check_ge_tally_delegates`         | tally_delegates       | GE suite   | Schema + value validation      |

---

## infra.taxonomy

**File:** `infra/taxonomy.py`

### `load_taxonomy() -> dict`
Load and cache `taxonomy.yaml`. Returns the full taxonomy dict.

### `valid_values(field: str) -> list[str]`
Return the allowed values for a taxonomy field.

| Parameter | Type | Description                           |
|-----------|------|---------------------------------------|
| `field`   | str  | Taxonomy field name (e.g., `"sources"`) |

**Raises:** `KeyError` if field not found.

### `validate_column(series, field: str) -> list[str]`
Validate that non-null values in a pandas/polars Series are in the taxonomy.

**Returns:** List of invalid values (empty list means all valid).

---

## infra.io_managers

**File:** `infra/io_managers.py`

### `class ParquetIOManager(ConfigurableIOManager)`
Read/write DataFrames as Parquet files.

| Field      | Type | Default | Description            |
|------------|------|---------|------------------------|
| `base_dir` | str  | `"."`   | Base directory for files |

### `class JsonIOManager(ConfigurableIOManager)`
Read/write objects as JSON files.

| Field      | Type | Default | Description            |
|------------|------|---------|------------------------|
| `base_dir` | str  | `"."`   | Base directory for files |
