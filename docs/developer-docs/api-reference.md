# API Reference

Public functions, classes, and assets in the `infra` Python package.

> This is the Python API. For the FastAPI / MCP HTTP API, see `dashboards/api.py` source or run `curl https://mcp.ensretro.metagov.org/` for the endpoint landing page.

## `infra.definitions`

**File:** `infra/definitions.py`

The central Dagster entry point. Loaded via `[tool.dagster] module_name = "infra.definitions"` in `pyproject.toml`.

### `defs: Definitions`
The Dagster `Definitions` object combining all assets, checks, resources, and sensors.

**Contains:**
- `assets`: 18 bronze Python assets + 1 dbt asset group (40 models)
- `asset_checks`: 10 checks (5 row-count + 5 GE suites, all on governance assets)
- `resources`: `dbt` (`DbtCliResource`), `etherscan_config` (`EtherscanApiConfig`), `oso_config` (`OsoApiConfig`)
- `sensors`: `vector_store_sync_sensor` (triggers vector store refresh after gold materializations)

---

## `infra.resources`

**File:** `infra/resources.py`

### `class EtherscanApiConfig(ConfigurableResource)`
Dagster resource holding the Etherscan API key. Consumed by `delegations`, `token_distribution`, and `treasury_flows` bronze assets.

| Field | Type | Description |
|---|---|---|
| `api_key` | str | Etherscan API key (from `ETHERSCAN_API_KEY` env var) |

### `class OsoApiConfig(ConfigurableResource)`
Dagster resource holding the Open Source Observer API key. Consumed by the `bronze_github` assets.

| Field | Type | Description |
|---|---|---|
| `api_key` | str | OSO API key (from `OSO_API_KEY` env var) |

> **Removed:** `TallyApiConfig` no longer exists. Tally assets were converted to file sentinels when Tally.xyz shut down their public API.

---

## `infra.dbt_project`

**File:** `infra/dbt_project.py`

### `dbt_project: DbtProject`
Configured dbt project instance pointing to `infra/dbt/`. Calls `prepare_if_dev()` at import time to generate the manifest.

### `class EnsDbtTranslator(DagsterDbtTranslator)`
Maps dbt sources to upstream Dagster bronze asset keys and assigns UI group names based on the dbt folder layout.

**Methods:**
- `get_asset_key(dbt_resource_props)` — for `resource_type == "source"`, looks up `(source_name, table_name)` in `_SOURCE_TO_ASSET_KEY`. Otherwise delegates to `super().get_asset_key()`.
- `get_group_name(dbt_resource_props)` — reads the model's folder (staging/silver/gold) from the `fqn` list and returns it as the group name, so the Dagster UI shows models grouped by layer.

### `_SOURCE_TO_ASSET_KEY: dict`
Static mapping from `(source_name, table_name)` to `AssetKey`. Updated whenever a new ingest asset is added that a dbt model consumes via `{{ source(...) }}`.

---

## `infra.dbt_assets`

**File:** `infra/dbt_assets.py`

### `ens_dbt_assets(context, dbt: DbtCliResource)`
The `@dbt_assets` decorated function that runs `dbt build` for all models.

- Creates `warehouse/` directory before running dbt
- Uses `EnsDbtTranslator` for source-to-asset mapping
- Streams dbt CLI output back to Dagster for real-time logging

---

## `infra.ingest` — API clients

All ingest modules follow the same shape: a handful of `fetch_*` functions that hit the API, optional `flatten_*` helpers that reshape nested responses into flat dicts, and errors that re-raise as `requests.HTTPError` / `httpx.HTTPStatusError` with 60-second backoff on HTTP 429.

### `infra.ingest.snapshot_api` (177 lines)
```python
fetch_snapshot_proposals() -> list[dict]
fetch_snapshot_votes(proposals: list[dict]) -> list[dict]
```
No authentication. Hits `https://hub.snapshot.org/graphql` with paginated queries against the `ens.eth` space.

### `infra.ingest.tally_api` (661 lines — frozen)
```python
fetch_organization(api_key) -> dict
fetch_tally_proposals(org_id, api_key) -> list[dict]
fetch_tally_votes(proposals, api_key) -> list[dict]
fetch_tally_delegates(org_id, api_key) -> list[dict]

flatten_tally_proposals(raw) -> list[dict]
flatten_tally_votes(raw) -> list[dict]
flatten_tally_delegates(raw) -> list[dict]
```
**Frozen:** Tally.xyz no longer exposes a public API. The assets that depend on this module are `compute_kind="file"` sentinels. The code is retained for historical reference and for the case where a new API becomes available.

### `infra.ingest.etherscan_api` (585 lines)
```python
fetch_delegate_changed_events(api_key) -> list[dict]
fetch_transfer_events(api_key) -> list[dict]
fetch_treasury_transactions(safe_addresses, api_key) -> list[dict]
```
Paginates Etherscan's v2 event logs endpoint for the ENS token contract. Handles checkpointing via `bronze/on-chain/.checkpoints/` to resume interrupted fetches.

### `infra.ingest.safe_api` (434 lines)
```python
fetch_safe_transactions(safe_address) -> list[dict]
fetch_safe_balances(safe_address) -> list[dict]
```
Safe Transaction Service REST client. No auth required. Used for every ENS working-group Safe.

### `infra.ingest.smallgrants_api` (145 lines)
```python
fetch_smallgrants_proposals() -> list[dict]
fetch_smallgrants_votes(proposals) -> list[dict]
```
Uses Snapshot GraphQL under the hood — SmallGrants hosts its grant voting as a Snapshot space.

### `infra.ingest.discourse_api` (206 lines)
```python
fetch_forum_topics(category_id) -> list[dict]
fetch_forum_posts_for_topic(topic_id) -> list[dict]
```
Discourse REST client for `discuss.ens.domains`. No auth.

### `infra.ingest.oso_api` (244 lines)
```python
fetch_ens_repos(api_key) -> list[dict]
fetch_ens_code_metrics(api_key) -> list[dict]
fetch_ens_timeseries(api_key) -> list[dict]
```
Wraps the `pyoso` client for Open Source Observer's GraphQL data lake.

---

## `infra.ingest.assets`

**File:** `infra/ingest/assets.py` (~930 lines)

Hosts all 18 `@asset` definitions plus shared helpers.

### Helper functions

#### `_update_metadata(subdir, filename, *, status, records, file_size, source, method)`
Update a file entry in the subdomain's `metadata.json`.

#### `_write_json(data, subdir, filename, context, *, source, method)`
Write a JSON array to a bronze file and update metadata provenance.

#### `_check_file_exists(subdir, filename, context)`
Check if a manually-placed file exists. Logs a warning via `context.log` if missing.

### Bronze assets by group

| Group | Asset | Kind | Upstream dep |
|---|---|---|---|
| `bronze_governance` | `snapshot_proposals` | api | — |
| `bronze_governance` | `snapshot_votes` | api | `snapshot_proposals` |
| `bronze_governance` | `tally_proposals` | file | — |
| `bronze_governance` | `tally_votes` | file | `tally_proposals` |
| `bronze_governance` | `tally_delegates` | file | — |
| `bronze_governance` | `votingpower_delegates` | file | — |
| `bronze_financial` | `ens_ledger_transactions` | file | — |
| `bronze_financial` | `ens_wallet_balances` | api | — |
| `bronze_financial` | `ens_safe_transactions` | api | — |
| `bronze_onchain` | `delegations` | api | — |
| `bronze_onchain` | `token_distribution` | api | — |
| `bronze_onchain` | `treasury_flows` | api | — |
| `bronze_grants` | `smallgrants_proposals` | api | — |
| `bronze_grants` | `smallgrants_votes` | api | `smallgrants_proposals` |
| `bronze_forum` | `forum_topics` | api | — |
| `bronze_github` | OSO repos, code metrics, timeseries | api | — (3 assets) |

---

## `infra.validate.checks`

**File:** `infra/validate/checks.py`

### Helper functions

#### `_count_json_records(subdir: str, filename: str) -> int`
Count records in a bronze JSON array file. Returns 0 if file missing.

#### `_load_bronze_df(subdir: str, filename: str) -> pd.DataFrame | None`
Load a bronze JSON file into a pandas DataFrame. Returns `None` if missing/empty.

#### `_run_ge_suite(subdir, filename, suite_name) -> AssetCheckResult`
Run a Great Expectations suite against a bronze file. Uses an ephemeral GE context with a pandas datasource.

### Asset checks (10 total)

| Check | Asset | Type | Description |
|---|---|---|---|
| `check_snapshot_proposals_count` | `snapshot_proposals` | row count | Expected ~90 rows |
| `check_snapshot_votes_count` | `snapshot_votes` | row count | Expected ~47,551 rows |
| `check_tally_proposals_count` | `tally_proposals` | row count | Expected ~62 rows |
| `check_tally_votes_count` | `tally_votes` | row count | Expected ~9,550 rows |
| `check_tally_delegates_count` | `tally_delegates` | row count | Expected ~37,876 rows |
| `check_ge_snapshot_proposals` | `snapshot_proposals` | GE suite | Schema + value validation |
| `check_ge_snapshot_votes` | `snapshot_votes` | GE suite | Schema + value validation |
| `check_ge_tally_proposals` | `tally_proposals` | GE suite | Schema + value validation |
| `check_ge_tally_votes` | `tally_votes` | GE suite | Schema + value validation |
| `check_ge_tally_delegates` | `tally_delegates` | GE suite | Schema + value validation |

Coverage is concentrated on the governance layer (Snapshot + Tally). On-chain, financial, grants, forum, and github assets currently rely on dbt tests (`_staging.yml`, `_silver.yml`, `_gold.yml`) rather than Dagster asset checks. See [ROADMAP section D](../ROADMAP.md#d-test-coverage-is-inverted-pipeline-has-0-tests-dashboard-has-106) for the plan to extend coverage.

---

## `infra.taxonomy`

**File:** `infra/taxonomy.py`

### `load_taxonomy() -> dict`
Load and cache `taxonomy.yaml`. Returns the full taxonomy dict.

### `valid_values(field: str) -> list[str]`
Return the allowed values for a taxonomy field.

**Raises:** `KeyError` if field not found.

### `validate_column(series, field: str) -> list[str]`
Validate that non-null values in a pandas/polars Series are in the taxonomy.

**Returns:** List of invalid values (empty list means all valid).

---

## `infra.sensors`

**File:** `infra/sensors.py`

### `vector_store_sync_sensor`
Asset sensor that watches the gold asset group. After any gold model is materialized, it triggers a re-export of gold tables to markdown (via `scripts/sync_vector_store.py`) and uploads the fresh files to the OpenAI vector store so the ChatKit agent sees current data.

---

## `infra.io_managers`

**File:** `infra/io_managers.py`

Utility IO managers (not currently mounted on assets — left in place for downstream users who want DataFrame-based asset flows).

### `class ParquetIOManager(ConfigurableIOManager)`
Read/write DataFrames as Parquet files.

### `class JsonIOManager(ConfigurableIOManager)`
Read/write objects as JSON files.
