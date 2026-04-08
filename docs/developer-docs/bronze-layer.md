# Bronze Layer

The bronze layer holds raw, append-only data fetched from external APIs or manually placed on disk. Every file has a `metadata.json` provenance entry alongside it.

## Directory Structure

```
bronze/
├── governance/                 Snapshot, Tally, Agora, votingpower
│   ├── metadata.json           Schema hints + provenance
│   ├── snapshot_proposals.json         ~90 proposals from Snapshot GraphQL
│   ├── snapshot_votes.json             ~48k votes from Snapshot GraphQL
│   ├── tally_proposals.json            ~62 proposals (historical — Tally shut down)
│   ├── tally_votes.json                ~9.5k votes (historical)
│   ├── tally_delegates.json            ~38k delegates (historical)
│   ├── votingpower-xyz/                Manual CSV export
│   │   └── ens-delegates-*.csv
│   ├── agora/                          Agora governor contract events (CSV, LFS)
│   │   ├── Governor Contract/
│   │   └── Token Contract/
│   └── scripts/
│       └── export_ens_tally.py         Legacy Tally export script
│
├── on-chain/                   Delegations, transfers, treasury (Etherscan)
│   ├── metadata.json
│   ├── delegations.json                DelegateChanged events
│   ├── token_distribution.json         Transfer events → holder balances
│   ├── treasury_flows.json             DAO treasury wallet movements
│   └── scripts/
│       └── export_ens_onchain.py       Standalone export helper
│
├── forum/                      Discourse (discuss.ens.domains)
│   ├── metadata.json
│   ├── forum_topics.json
│   └── forum_posts.json
│
├── financial/                  ENS treasury ledger + Safe transactions
│   ├── metadata.json
│   ├── ens_ledger_transactions.csv     Maintained ENS financial ledger
│   ├── ens_safe_transactions.json      Safe API history for ENS multisigs
│   ├── ens_wallet_balances.json        Wallet balance snapshots
│   ├── enswallets.json                 ENS working-group wallet directory
│   └── compensation.json               Steward/contributor compensation
│
├── grants/                     SmallGrants + large-grant disbursements
│   ├── metadata.json
│   ├── smallgrants_proposals.json      SmallGrants Snapshot space
│   ├── smallgrants_votes.json
│   └── large_grants.json               Derived from financial ledger
│
├── github/                     GitHub activity via Open Source Observer
│   ├── metadata.json
│   ├── oso_ens_repos.json              ENS ecosystem repo list
│   ├── oso_ens_code_metrics.json       Code metrics aggregates
│   └── oso_ens_timeseries.json         Activity timeseries
│
└── docs/                       Governance reference documents
    └── metadata.json
```

## Data Sources — at a glance

| Source | Layer | Fetcher | Auth | Bronze files |
|---|---|---|---|---|
| **Snapshot** | Governance | `infra/ingest/snapshot_api.py` | None | `snapshot_proposals.json`, `snapshot_votes.json` |
| **Tally** (frozen) | Governance | `infra/ingest/tally_api.py` | `TALLY_API_KEY` | `tally_proposals.json`, `tally_votes.json`, `tally_delegates.json` |
| **votingpower.xyz** | Governance | Manual CSV | — | `votingpower-xyz/*.csv` |
| **Etherscan** | On-chain | `infra/ingest/etherscan_api.py` | `ETHERSCAN_API_KEY` | `delegations.json`, `token_distribution.json`, `treasury_flows.json` |
| **Safe** | Financial | `infra/ingest/safe_api.py` | None | `ens_safe_transactions.json`, `ens_wallet_balances.json` |
| **SmallGrants** | Grants | `infra/ingest/smallgrants_api.py` | None | `smallgrants_proposals.json`, `smallgrants_votes.json` |
| **Discourse** | Forum | `infra/ingest/discourse_api.py` | None | `forum_topics.json`, `forum_posts.json` |
| **OSO** | GitHub | `infra/ingest/oso_api.py` | `OSO_API_KEY` | `oso_ens_repos.json`, `oso_ens_code_metrics.json`, `oso_ens_timeseries.json` |

All eight API clients follow the same pattern: fetch → flatten → write JSON → update `metadata.json` provenance.

## Detailed Sources

### Snapshot (snapshot.org)

- **API:** `https://hub.snapshot.org/graphql`
- **Space:** `ens.eth`
- **Auth:** None (public API)
- **Fetch method:** GraphQL paginated queries. Proposals fetched in batches of 100 ordered by `created` desc; votes fetched per-proposal in batches of 1000. `proposal_id` is injected into each vote record.

### Tally (tally.xyz) — FROZEN

- **Status:** Historical only. Tally.xyz shut down public API access.
- **Assets:** `tally_proposals`, `tally_votes`, `tally_delegates` are all `compute_kind="file"` sentinels that only detect the checked-in JSON; they do **not** call the API.
- **Retained for:** historical comparison with Agora governor contract events and Snapshot votes.

### Etherscan (etherscan.io)

- **API:** Etherscan REST API (v2 event logs endpoint)
- **Auth:** `ETHERSCAN_API_KEY`
- **Fetches:**
  - `DelegateChanged` events → `delegations.json`
  - `Transfer` events → `token_distribution.json`
  - Working-group Safe transactions → `treasury_flows.json`

### Safe (safe.global)

- **API:** Safe Transaction Service
- **Auth:** None
- **Fetches:** Full transaction history + current balances for every ENS working-group Safe address (list lives in `bronze/financial/enswallets.json`).

### SmallGrants

- **API:** Snapshot GraphQL (SmallGrants hosts its grant voting as a Snapshot space)
- **Auth:** None
- **Fetches:** Grant proposals + votes for the SmallGrants space, then flattened per-round.

### Discourse (discuss.ens.domains)

- **API:** Discourse REST API (public forum endpoints)
- **Auth:** None
- **Fetches:** Topic list + per-topic posts. Used for the `*_discourse_crosswalk` silver models that link on-chain proposals to their forum discussion threads.

### OSO (Open Source Observer)

- **API:** `pyoso` Python client hitting OSO's GraphQL data lake
- **Auth:** `OSO_API_KEY`
- **Fetches:** ENS ecosystem repo list + per-repo code metrics + activity timeseries.

### votingpower.xyz (manual)

- CSV export, dropped into `bronze/governance/votingpower-xyz/`.
- No automated fetcher — re-export manually when you want fresh data.

## metadata.json

Every bronze subdomain has a `metadata.json` file tracking provenance and collection status. Entries are auto-updated by the `_write_json()` helper in `infra/ingest/assets.py` whenever a fetcher writes a file.

### Structure

```json
{
  "domain": "governance",
  "description": "On-chain and off-chain governance proposal and voting data",
  "sources": ["snapshot", "tally", "votingpower-xyz"],
  "collection_status": "complete",
  "last_indexed_at": "2026-04-08T09:00:00+00:00",
  "notes": "Human-readable notes",
  "files": {
    "snapshot_proposals.json": {
      "status": "present",
      "description": "Snapshot proposals for ens.eth space",
      "expected_records": 90,
      "actual_records": 90,
      "file_size_bytes": 455031,
      "schema_hints": {
        "id": "string — unique proposal identifier",
        "title": "string — proposal title"
      },
      "provenance": {
        "source": "snapshot.org",
        "api_endpoint": "https://hub.snapshot.org/graphql",
        "query_or_method": "GraphQL paginated query (space=ens.eth, batch=100)",
        "collected_by": "dagster_pipeline (infra.ingest.snapshot_api)",
        "collected_at": "2026-04-08T09:00:00+00:00",
        "covers_period": "all-time (ordered by created desc)",
        "records": 90,
        "notes": "Raw API response objects, no transforms applied"
      }
    }
  }
}
```

### Field descriptions

| Field | Description |
|---|---|
| `domain` | Bronze subdomain name |
| `collection_status` | `complete`, `in_progress`, or `not_started` |
| `last_indexed_at` | ISO 8601 timestamp of last pipeline run that touched this domain |
| `files.<name>.status` | `present` or `missing` |
| `files.<name>.provenance.collected_by` | Pipeline component that wrote the file |
| `files.<name>.provenance.collected_at` | ISO 8601 timestamp when the file was written |
| `files.<name>.provenance.query_or_method` | Description of how data was fetched |

### Auto-stamping helpers

All in `infra/ingest/assets.py`:

- **`_write_json(data, subdir, filename, context, *, source, method)`** — called by active fetchers after writing data. Updates `status`, `actual_records`, `file_size_bytes`, and `provenance`.
- **`_check_file_exists(subdir, filename, context)`** — called by sentinel assets (Tally, votingpower). Updates `status` if the file is present, logs a warning if missing.
- **`_update_metadata(...)`** — low-level helper that writes a single file entry in the subdomain's `metadata.json`.

## Adding a new data source

See [`workflow.md`](workflow.md#adding-a-new-data-source) for the step-by-step recipe. Summary:

1. Write a client in `infra/ingest/<source>_api.py`
2. Add an `@asset` in `infra/ingest/assets.py` that calls the client and `_write_json`
3. Add a staging model in `infra/dbt/models/staging/stg_<source>.sql` using `{{ source(...) }}`
4. Add source entries to `infra/dbt/models/staging/_sources.yml` and the macro in `infra/dbt/macros/source.sql`
5. Map the source to the Dagster asset in `_SOURCE_TO_ASSET_KEY` (`infra/dbt_project.py`)
6. Add a silver model in `infra/dbt/models/silver/clean_<source>.sql`
7. Run `dbt parse` to regenerate `manifest.json`
