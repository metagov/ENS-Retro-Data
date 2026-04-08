# Architecture

## Overview

ENS-Retro-Data implements a **medallion architecture** (bronze → silver → gold) for ENS DAO governance research. The pipeline is orchestrated by **Dagster**, with **dbt** handling SQL transformations and **DuckDB** as the analytical warehouse. A Streamlit dashboard and a FastAPI + MCP server sit on top of the warehouse.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Dagster Orchestrator                        │
│                     (infra/definitions.py)                         │
├────────────┬──────────────────┬──────────────────┬─────────────────┤
│   Bronze   │    Staging       │     Silver       │      Gold       │
│  (Python)  │   (dbt views)    │  (dbt tables)    │  (dbt tables)   │
│            │                  │                  │                 │
│ API fetch  │  read_json_auto  │  clean, type,    │  aggregate,     │
│ → JSON on  │  read_csv_auto   │  deduplicate     │  compute        │
│   disk     │  → bronze schema │  → silver schema │  → gold schema  │
└────────────┴──────────────────┴──────────────────┴─────────────────┘
        ↓              ↓                ↓                 ↓
  bronze/*.json   DuckDB views     DuckDB tables     DuckDB tables
                                                          ↓
                                              warehouse/ens_retro.duckdb
                                                          ↓
                                 ┌────────────────────────┼────────────────────┐
                                 ▼                        ▼                    ▼
                       ┌──────────────────┐   ┌──────────────────┐  ┌─────────────────┐
                       │ Streamlit        │   │ FastAPI + MCP    │  │ Dagster UI      │
                       │ dashboard        │   │ dashboards/api.py│  │ (read-only)     │
                       │ dashboards/app.py│   │                  │  │                 │
                       └──────────────────┘   └──────────────────┘  └─────────────────┘
```

## Technology Stack

| Component       | Technology         | Version  | Purpose                              |
|-----------------|--------------------|----------|--------------------------------------|
| Orchestrator    | Dagster            | >= 1.9   | Pipeline scheduling & asset graph    |
| SQL Transforms  | dbt-core           | >= 1.9   | Staging, silver, gold models         |
| Warehouse       | DuckDB             | >= 1.1   | OLAP database (single file)          |
| dbt Adapter     | dbt-duckdb         | >= 1.9   | dbt ↔ DuckDB connector              |
| Data Quality    | Great Expectations | >= 1.3   | Bronze validation suites             |
| DataFrames      | pandas / polars    | >= 2.2   | Data manipulation                    |
| HTTP Client     | requests / httpx   | >= 2.31  | API calls to data sources            |
| Dashboard       | Streamlit          | latest   | Research frontend                    |
| API server      | FastAPI + FastMCP  | latest   | REST + MCP endpoints for agents      |
| Package Manager | uv                 | latest   | Python dependency management         |
| Python          | CPython            | >= 3.12  | Runtime                              |

## Directory Layout

```
ENS-Retro-Data/
├── bronze/                     Raw data (append-only JSON/CSV, LFS for large files)
│   ├── governance/             Snapshot, Tally, Agora governor events, votingpower
│   ├── on-chain/               Delegations, transfers, treasury (Etherscan)
│   ├── forum/                  Discourse topics + posts
│   ├── financial/              ENS ledger, Safe txs, wallet balances, compensation
│   ├── grants/                 SmallGrants + large-grant disbursements
│   ├── github/                 OSO code metrics + timeseries
│   └── docs/                   ENS governance reference documents
│
├── infra/                      Pipeline infrastructure
│   ├── definitions.py          Central Dagster entry point
│   ├── dbt_project.py          dagster-dbt config + EnsDbtTranslator
│   ├── dbt_assets.py           @dbt_assets function wrapping dbt build
│   ├── resources.py            EtherscanApiConfig, OsoApiConfig
│   ├── sensors.py              vector_store_sync_sensor (post-gold refresh)
│   ├── io_managers.py          Parquet / JSON IO managers (utility)
│   ├── taxonomy.py             Taxonomy loader & validator
│   ├── ingest/                 Bronze layer (8 API clients + assets.py)
│   ├── transform/              (empty stub — dbt handles silver)
│   ├── materialize/            (empty stub — dbt handles gold)
│   ├── validate/               Dagster asset checks + GE suites
│   ├── dbt/                    Full dbt project (staging/silver/gold)
│   └── great_expectations/     GE expectation suites
│
├── dashboards/                 Streamlit + FastAPI + MCP
│   ├── app.py                  Main Streamlit app
│   ├── api.py                  FastAPI REST + MCP server
│   ├── scripts/                Chart renderers (hypothesis modules)
│   ├── static/                 ChatKit iframe pages
│   ├── pages/                  Streamlit sub-pages
│   └── tests/                  106 pytest cases
│
├── warehouse/                  DuckDB database (LFS)
│   └── ens_retro.duckdb        Created/refreshed by dbt
│
├── .dagster/                   Dagster instance state (LFS for run history)
├── docs/                       Project + research documentation
├── scripts/                    Standalone utilities (taxonomy seeds, serve.sh)
├── taxonomy.yaml               Single source of truth for vocabularies
├── pyproject.toml              Python project config
└── .env                        API keys (not committed)
```

## Data Flow

### 1. Bronze Layer (Python — Dagster Assets)

Bronze assets fetch raw data from external APIs (or detect manually-placed files) and write JSON/CSV files to `bronze/`. They return `None` — dbt reads the files directly from disk.

**18 bronze assets across 6 groups:**

| Group | Assets | Source |
|---|---|---|
| `bronze_governance` | `snapshot_proposals`, `snapshot_votes`, `tally_proposals`, `tally_votes`, `tally_delegates`, `votingpower_delegates` | Snapshot GraphQL, Tally GraphQL (frozen), votingpower.xyz CSV |
| `bronze_onchain` | `delegations`, `token_distribution`, `treasury_flows` | Etherscan API |
| `bronze_financial` | `ens_ledger_transactions`, `ens_wallet_balances`, `ens_safe_transactions` | Safe API + ENS financial ledger |
| `bronze_grants` | `smallgrants_proposals`, `smallgrants_votes` | SmallGrants Snapshot space |
| `bronze_forum` | `forum_topics` | Discourse API (discuss.ens.domains) |
| `bronze_github` | 3 OSO-derived assets | Open Source Observer (GitHub metrics) |

**Tally assets are frozen** — Tally.xyz shut down their public API. The existing bronze JSON is checked into the repo as historical record (`compute_kind="file"` sentinels) but no new fetches happen.

### 2. Staging Layer (dbt Views — `bronze` schema)

**18 staging views** use a custom `source()` macro override that resolves `{{ source('bronze_governance', 'snapshot_proposals') }}` to `read_json_auto('../../bronze/governance/snapshot_proposals.json')`.

These views are lightweight schema-on-read wrappers — no data transformation, just column selection and renaming.

### 3. Silver Layer (dbt Tables — `silver` schema)

**16 silver tables** apply cleaning transformations:

- Lowercase Ethereum addresses
- Convert Unix timestamps to `TIMESTAMP`
- Convert wei to ether (18 decimal shift)
- Map vote choice integers to strings (`for`, `against`, `abstain`)
- Normalize proposal statuses against `taxonomy.yaml`
- Build `address_crosswalk` merging all address sources
- Build `snapshot_discourse_crosswalk` + `tally_discourse_crosswalk` linking forum topics to proposals

### 4. Gold Layer (dbt Tables — `gold` schema)

**6 analysis-ready models:**

| Model | Type | Purpose |
|---|---|---|
| `governance_activity` | SQL | Unified Snapshot + Tally proposals with vote percentages |
| `governance_discourse_activity` | SQL | Joins governance activity to forum discussion via discourse crosswalks |
| `delegate_scorecard` | SQL | Per-delegate participation rate and voting power |
| `treasury_summary` | SQL | Monthly treasury flows by category (USD-denominated) |
| `participation_index` | Python | Gini coefficients, participation metrics |
| `decentralization_index` | Python | Nakamoto coefficient, HHI, delegation concentration |

### 5. Validation Layer

**Bronze asset checks** (Dagster):
- 5 row-count checks (fast, always run) on Snapshot and Tally assets
- 5 Great Expectations suite validations (schema + value rules) on the same assets
- Coverage is concentrated on the governance layer; on-chain/financial/grants/forum/github assets currently rely on dbt tests rather than Dagster asset checks

**Silver/Gold checks** (dbt tests):
- `not_null`, `unique`, `accepted_values` constraints declared in `_staging.yml`, `_silver.yml`, `_gold.yml`
- ~45 silver tests + ~21 gold tests
- Some models that depend on unresolved data sources use `severity: warn` to avoid blocking the pipeline

## Key Design Decisions

### Why assets return `None`
Bronze assets write JSON to disk and return `None`. dbt reads files directly using DuckDB's `read_json_auto()`. This avoids passing DataFrames through Dagster's IO system and leverages DuckDB's native file scanning.

### Why a custom `source()` macro
dbt-duckdb doesn't natively support reading JSON/CSV files via `{{ source() }}`. The custom macro overrides dbt's built-in `source()` to emit `read_json_auto()` / `read_csv_auto()` calls against relative paths on disk.

### Why Tally assets are frozen
Tally.xyz shut down their public governance API in early 2026. The existing bronze JSON is retained for historical analysis but the fetcher assets were converted to `compute_kind="file"` sentinels — they detect the presence of the checked-in data but never call the API.

### Why DuckDB
DuckDB is an embedded OLAP engine that reads JSON/CSV/Parquet natively, requires no server, and stores everything in a single file (`warehouse/ens_retro.duckdb`). It supports SQL with analytical functions, making it ideal for a local-first data pipeline.

### Why `.dagster/storage/` is tracked via LFS
Render's free/starter tier doesn't provide persistent disks. To share Dagster's run history across deployments (so the read-only UI can show meaningful run state), the SQLite storage files are committed via Git LFS. This is documented in [`ROADMAP.md`](../ROADMAP.md#a-clone-size-12-gb-via-git-lfs).

### Why `warehouse/` is a separate directory
The `warehouse/` directory holds the DuckDB database file created at runtime. It is separate from `bronze/` (raw inputs) and `infra/` (code) to keep outputs isolated. The directory is auto-created by the `ens_dbt_assets` function before each dbt build.

## Dagster Resources

Declared in `infra/definitions.py`:

| Resource | Type | Purpose |
|---|---|---|
| `dbt` | `DbtCliResource` | Runs `dbt build` from within Dagster |
| `etherscan_config` | `EtherscanApiConfig` | Holds `ETHERSCAN_API_KEY` for on-chain assets |
| `oso_config` | `OsoApiConfig` | Holds `OSO_API_KEY` for GitHub metrics assets |

## Sensors

- **`vector_store_sync_sensor`** (`infra/sensors.py`) — triggers after gold models are materialized; re-exports the gold tables to markdown and uploads them to the OpenAI vector store so the ChatKit agent sees fresh data.

## Dagster-dbt Integration

```
┌─────────────────────┐       ┌──────────────────────────────┐
│  infra/dbt_project.py│       │  infra/dbt_assets.py         │
│                     │       │                              │
│  DbtProject(        │──────▶│  @dbt_assets(                │
│    project_dir=     │       │    manifest=...,             │
│    infra/dbt/       │       │    dagster_dbt_translator=   │
│  )                  │       │    EnsDbtTranslator()        │
│                     │       │  )                           │
│  EnsDbtTranslator   │       │  def ens_dbt_assets():       │
│    maps dbt sources │       │    dbt.cli(["build"]).stream │
│    → bronze keys    │       │                              │
└─────────────────────┘       └──────────────────────────────┘
```

The `EnsDbtTranslator` class in `infra/dbt_project.py` maps dbt sources to upstream Dagster bronze asset keys, creating dependency edges in the Dagster asset graph. When Dagster materializes dbt assets, it runs `dbt build` which executes all staging views, silver tables, gold tables, and dbt tests in topological order.

See [`dagster-dbt-integration.md`](dagster-dbt-integration.md) for the detailed integration mechanics.
