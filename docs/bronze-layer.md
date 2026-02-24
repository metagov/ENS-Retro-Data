# Bronze Layer

The bronze layer holds raw, append-only data fetched from external APIs or manually placed on disk.

## Directory Structure

```
bronze/
├── governance/
│   ├── metadata.json                           Schema hints + provenance
│   ├── snapshot_proposals.json                 90 records, ~455 KB
│   ├── snapshot_votes.json                     47,551 records, ~14.8 MB
│   ├── tally_proposals.json                    62 records, ~133 KB
│   ├── tally_votes.json                        9,550 records, ~2.1 MB
│   ├── tally_delegates.json                    37,876 records, ~8.8 MB
│   ├── votingpower-xyz/
│   │   └── ens-delegates-2026-02-20.csv        CSV export
│   └── scripts/
│       └── export_ens_tally.py                 Standalone export script
│
├── on-chain/
│   └── metadata.json                           No data yet
│
├── financial/
│   └── metadata.json                           No data yet
│
├── forum/
│   └── metadata.json                           No data yet
│
├── grants/
│   └── metadata.json                           No data yet
│
├── interviews/
│   └── metadata.json                           No data yet
│
├── github/
│   └── metadata.json
│
└── docs/
    └── metadata.json
```

## Data Sources

### Snapshot (snapshot.org)

**API:** `https://hub.snapshot.org/graphql`
**Space:** `ens.eth`

| Dataset              | Records | Schema                                                        |
|----------------------|---------|---------------------------------------------------------------|
| `snapshot_proposals` | 90      | id, title, body, choices, start, end, snapshot, state, author, created, scores, scores_total, votes, quorum, type |
| `snapshot_votes`     | 47,551  | id, voter, choice, vp, created, proposal_id                  |

**Fetch method:** GraphQL paginated queries. Proposals fetched in batches of 100 (ordered by `created` desc). Votes fetched per-proposal in batches of 1000. `proposal_id` is injected into each vote record.

### Tally (tally.xyz)

**API:** `https://api.tally.xyz/query`
**Organization:** `ens` (slug)
**Authentication:** `Api-Key` header (from `TALLY_API_KEY` env var)

| Dataset              | Records | Schema                                                        |
|----------------------|---------|---------------------------------------------------------------|
| `tally_proposals`    | 62      | id, title, description, status, proposer, start_block, end_block, for_votes, against_votes, abstain_votes |
| `tally_votes`        | 9,550   | id, voter, support, weight, proposal_id, reason               |
| `tally_delegates`    | 37,876  | address, ens_name, voting_power, delegators_count, votes_count, proposals_count, statement |

**Fetch method:** GraphQL paginated queries. Proposals and delegates fetched in batches of 50. Votes fetched per-proposal in batches of 100. Raw nested responses are flattened. Vote counts are converted from wei to human-readable strings (18 decimal shift).

### votingpower.xyz (manual)

**Source:** CSV export from `votingpower.xyz`
**File:** `bronze/governance/votingpower-xyz/ens-delegates-2026-02-20.csv`

| Column          | Description                |
|-----------------|----------------------------|
| Rank            | Delegate rank by power     |
| Delegate        | ENS name or address        |
| Voting Power    | Current voting power       |
| 30 Day Change   | Power change over 30 days  |
| Delegations     | Number of delegators       |
| On-chain Votes  | Total on-chain votes cast  |

### Sentinel Sources (Planned)

These sources are not yet automated. No data files exist on disk — the sentinel Dagster assets simply check for their presence and log a warning if missing.

| Source               | Domain       | Expected File                  | Status   |
|----------------------|--------------|--------------------------------|----------|
| On-chain delegations | on-chain     | delegations.json               | Planned  |
| Token distribution   | on-chain     | token_distribution.json        | Planned  |
| Treasury flows       | on-chain     | treasury_flows.json            | Planned  |
| Grants               | grants       | grants.json                    | Planned  |
| Compensation         | financial    | compensation.json              | Planned  |
| Delegate profiles    | interviews   | delegate_profiles.json         | Planned  |
| Forum posts          | forum        | forum_posts.json               | Planned  |

When data is collected for these sources, place the JSON file in the corresponding `bronze/` subdirectory and the sentinel asset will detect it on the next run.

## metadata.json

Each bronze subdomain has a `metadata.json` file tracking provenance and collection status.

### Structure

```json
{
  "domain": "governance",
  "description": "On-chain and off-chain governance proposal and voting data",
  "sources": ["snapshot", "tally", "votingpower-xyz"],
  "collection_status": "complete",
  "last_indexed_at": "2026-02-24T09:38:25+00:00",
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
        "title": "string — proposal title",
        ...
      },
      "provenance": {
        "source": "snapshot.org",
        "api_endpoint": "https://hub.snapshot.org/graphql",
        "query_or_method": "GraphQL paginated query (space=ens.eth, batch=100)",
        "collected_by": "dagster_pipeline (infra.ingest.snapshot_api)",
        "collected_at": "2026-02-24T08:28:19+00:00",
        "covers_period": "all-time (ordered by created desc)",
        "records": 90,
        "notes": "Raw API response objects, no transforms applied"
      }
    }
  }
}
```

### Field Descriptions

| Field                | Description                                                |
|----------------------|------------------------------------------------------------|
| `domain`             | Bronze subdomain name                                      |
| `collection_status`  | `complete`, `in_progress`, or `not_started`                |
| `last_indexed_at`    | ISO 8601 timestamp of last pipeline run                    |
| `files.<name>.status`| `present`, `missing`, or `planned`                         |
| `files.<name>.provenance.collected_by` | Pipeline component that wrote the file      |
| `files.<name>.provenance.collected_at` | ISO 8601 timestamp of when file was written |
| `files.<name>.provenance.query_or_method` | Description of how data was fetched      |

### Sentinel Metadata

Domains without collected data have minimal metadata:

```json
{
  "domain": "on-chain",
  "description": "Blockchain data: token distribution, delegations, and treasury transactions",
  "sources": ["etherscan", "dune", "token-contract"],
  "collection_status": "not_started",
  "notes": "No data files present; requires Dune queries or direct RPC calls to collect",
  "files": {}
}
```

File entries are only added to `files` when data is actually collected. There are no "planned" entries.

### Auto-Stamping

Metadata is automatically updated during pipeline runs:

- **`_write_json()`** — called by active fetchers after writing data. Updates `status`, `actual_records`, `file_size_bytes`, and `provenance`.
- **`_check_file_exists()`** — called by sentinel assets. Updates `status` and `provenance` if file is present, or marks `status: missing`.
- **`_update_metadata()`** — helper that updates `collection_status` based on the ratio of present files to total files.

## API Clients

### `infra/ingest/snapshot_api.py`

```python
# Public API
fetch_snapshot_proposals() -> list[dict]     # All ENS proposals (paginated)
fetch_snapshot_votes(proposals) -> list[dict] # Votes for given proposals
```

- No authentication required
- Rate limit handling: 60s backoff on HTTP 429
- Request timeout: 30s

### `infra/ingest/tally_api.py`

```python
# Public API
fetch_organization(api_key) -> dict                     # Org metadata
fetch_tally_proposals(org_id, api_key) -> list[dict]    # Raw proposals
fetch_tally_votes(proposals, api_key) -> list[dict]     # Raw votes
fetch_tally_delegates(org_id, api_key) -> list[dict]    # Raw delegates

# Flatteners (nested API response → flat dicts)
flatten_tally_proposals(raw) -> list[dict]
flatten_tally_votes(raw) -> list[dict]
flatten_tally_delegates(raw) -> list[dict]
```

- Authentication: `Api-Key` header
- Rate limit handling: 60s backoff on HTTP 429
- Wei-to-ether conversion for vote counts (18 decimal shift)
- Statement text truncated to 1000 characters

## Sentinel Data Files

Sentinel data sources have no files on disk. The sentinel Dagster assets check for file presence and log a warning if missing. The corresponding dbt staging models will error during `dbt build` if the file is absent — this is expected behavior. Run selective dbt builds (e.g., `--select 'staging.stg_snapshot_*'`) to skip missing sources, or place data files manually to enable those models.

When real data is collected for a sentinel source, place the JSON file in the appropriate `bronze/` subdirectory and convert the sentinel asset to an active fetcher.
