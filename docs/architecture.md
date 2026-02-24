# Architecture

## Overview

ENS-Retro-Data implements a **medallion architecture** (bronze → silver → gold) for ENS DAO retrospective evaluation. The pipeline is orchestrated by **Dagster**, with **dbt** handling SQL transformations and **DuckDB** as the analytical warehouse.

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
```

## Technology Stack

| Component       | Technology         | Version  | Purpose                        |
|-----------------|--------------------|----------|--------------------------------|
| Orchestrator    | Dagster            | >= 1.9   | Pipeline scheduling & UI       |
| SQL Transforms  | dbt-core           | >= 1.9   | Staging, silver, gold models   |
| Warehouse       | DuckDB             | >= 1.1   | OLAP database (file-based)     |
| dbt Adapter     | dbt-duckdb         | >= 1.9   | dbt ↔ DuckDB connector        |
| Data Quality    | Great Expectations | >= 1.3   | Bronze validation suites       |
| DataFrames      | pandas / polars    | >= 2.2   | Data manipulation              |
| HTTP Client     | requests           | >= 2.31  | API calls to Snapshot/Tally    |
| Package Manager | uv                 | latest   | Python dependency management   |
| Python          | CPython            | >= 3.11  | Runtime                        |

## Directory Layout

```
ENS-Retro-Data/
├── bronze/                     Raw data (append-only JSON/CSV)
│   ├── governance/             Snapshot, Tally, votingpower data
│   ├── on-chain/               metadata.json only (no data yet)
│   ├── financial/              metadata.json only (no data yet)
│   ├── forum/                  metadata.json only (no data yet)
│   ├── grants/                 metadata.json only (no data yet)
│   ├── interviews/             metadata.json only (no data yet)
│   ├── github/                 metadata.json only (no data yet)
│   └── docs/                   Governance documents
│
├── infra/                      Pipeline infrastructure
│   ├── definitions.py          Dagster entry point
│   ├── dbt_project.py          dagster-dbt config + translator
│   ├── dbt_assets.py           @dbt_assets decorator
│   ├── resources.py            Dagster resources
│   ├── io_managers.py          Parquet/JSON IO managers
│   ├── taxonomy.py             Taxonomy loader & validator
│   ├── ingest/                 Bronze layer (API clients + assets)
│   ├── transform/              Silver layer (stub — dbt handles this)
│   ├── materialize/            Gold layer (stub — dbt handles this)
│   ├── validate/               Data quality checks
│   ├── dbt/                    Full dbt project
│   └── great_expectations/     GE expectation suites
│
├── warehouse/                  DuckDB database output
│   └── ens_retro.duckdb        Created at runtime by dbt
│
├── scripts/                    Standalone utility scripts
├── docs/                       Project documentation
├── taxonomy.yaml               Single source of truth for vocabularies
├── pyproject.toml              Python project config
└── .env                        API keys (not committed)
```

## Data Flow

### 1. Bronze Layer (Python — Dagster Assets)

Bronze assets fetch raw data from external APIs and write JSON files to `bronze/`. They return `None` — dbt reads the files directly from disk.

**Active fetchers** (5 assets):
- `snapshot_proposals` → Snapshot GraphQL API → `bronze/governance/snapshot_proposals.json`
- `snapshot_votes` → Snapshot GraphQL API → `bronze/governance/snapshot_votes.json`
- `tally_proposals` → Tally GraphQL API → `bronze/governance/tally_proposals.json`
- `tally_votes` → Tally GraphQL API → `bronze/governance/tally_votes.json`
- `tally_delegates` → Tally GraphQL API → `bronze/governance/tally_delegates.json`

**Sentinel assets** (8 assets):
- Check if manually-placed files exist on disk
- Log warnings if missing, update metadata if present
- `votingpower_delegates`, `delegations`, `token_distribution`, `treasury_flows`, `grants`, `compensation`, `delegate_profiles`, `forum_posts`

### 2. Staging Layer (dbt Views — `bronze` schema)

13 staging views use a custom `source()` macro override that resolves `{{ source('bronze_governance', 'snapshot_proposals') }}` to `read_json_auto('../../bronze/governance/snapshot_proposals.json')`.

These views are lightweight schema-on-read wrappers — no data transformation, just column selection and renaming.

### 3. Silver Layer (dbt Tables — `silver` schema)

11 silver tables apply cleaning transformations:
- Lowercase Ethereum addresses
- Convert Unix timestamps to `TIMESTAMP`
- Convert wei to ether (18 decimal shift)
- Map vote choice integers to strings (`for`, `against`, `abstain`)
- Normalize proposal statuses
- Build `address_crosswalk` merging all address sources

### 4. Gold Layer (dbt Tables — `gold` schema)

5 analysis-ready models:
- `governance_activity` — Unified Snapshot + Tally proposals with vote percentages
- `delegate_scorecard` — Per-delegate participation rate and voting power
- `treasury_summary` — Monthly treasury flows by category (placeholder)
- `participation_index` — Gini coefficients, participation metrics (Python model)
- `decentralization_index` — Nakamoto coefficient, HHI, delegation concentration (Python model)

### 5. Validation Layer

**Bronze checks** (Dagster asset checks):
- 5 row-count checks (fast, always run)
- 5 Great Expectations suite validations (schema + value rules)

**Silver/Gold checks** (dbt tests):
- `not_null`, `unique`, `accepted_values` constraints in `_silver.yml` and `_gold.yml`
- Sentinel model tests use `severity: warn` to avoid blocking the pipeline

## Key Design Decisions

### Why assets return `None`
Bronze assets write JSON to disk and return `None`. dbt reads files directly using DuckDB's `read_json_auto()`. This avoids passing DataFrames through Dagster's IO system and leverages DuckDB's native file scanning.

### Why a custom `source()` macro
dbt-duckdb doesn't natively support reading JSON/CSV files via `{{ source() }}`. The custom macro overrides dbt's built-in `source()` to look up `external_location` metadata and emit `read_json_auto()` / `read_csv_auto()` calls.

### Why sentinel assets exist
Data from on-chain indexers, forums, grants portals, and interviews is not yet collected via automated APIs. Sentinel assets check if files were manually placed on disk and update `metadata.json` provenance accordingly. No placeholder files are committed — sentinel directories contain only `metadata.json` with `"files": {}`. The corresponding dbt staging models will error if the bronze file is absent; run selective dbt builds to skip them.

### Why DuckDB
DuckDB is an embedded OLAP engine that reads JSON/CSV/Parquet natively, requires no server, and stores everything in a single file (`warehouse/ens_retro.duckdb`). It supports SQL with analytical functions, making it ideal for a local-first data pipeline.

### Why `warehouse/` is a separate directory
The `warehouse/` directory holds the DuckDB database file created at runtime. It is separate from `bronze/` (raw inputs) and `infra/` (code) to keep outputs isolated. The directory is auto-created by the `ens_dbt_assets` function before each dbt build.

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

The `EnsDbtTranslator` class maps dbt sources to upstream Dagster bronze asset keys, creating dependency edges in the Dagster asset graph. When Dagster materializes dbt assets, it runs `dbt build` which executes all staging views, silver tables, gold tables, and dbt tests in topological order.
