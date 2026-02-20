# ENS-Retro-Data

Data infrastructure for the ENS DAO retrospective evaluation. Implements a medallion architecture (bronze/silver/gold) orchestrated by Dagster.

## Architecture

```
bronze/          Raw data — append-only JSON from each source
  governance/    Snapshot proposals/votes, Tally proposals/votes/delegates
  on-chain/      Delegations, token distribution, treasury flows
  forum/         Governance forum posts
  financial/     Compensation records
  grants/        Grant applications and awards
  interviews/    Stakeholder interviews, delegate profiles
  docs/          Governance documents
  github/        Repository activity

silver/          Cleaned, typed, deduplicated data
  quantitative/  Numeric/structured data
  qualitative/   Text and interview data
  crosswalk/     Address-to-identity mappings

gold/            Analysis-ready views
  views/         Composite views (governance_activity, delegate_scorecard, etc.)
  indexes/       Composite indexes (participation, decentralization)

infra/           Dagster pipeline code
  ingest/        Bronze layer asset definitions
  transform/     Silver layer transforms
  materialize/   Gold layer view construction
  validate/      Asset checks and data quality
```

## Quick Start

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --extra dev

# Launch Dagster UI
uv run dagster dev

# Run linter
uv run ruff check .
```

## Data Sources

| Source | Platform | Records | Status |
|---|---|---|---|
| Snapshot proposals | Snapshot.org | ~90 | Awaiting upload |
| Snapshot votes | Snapshot.org | ~47,551 | Awaiting upload |
| Tally proposals | Tally | ~62 | Awaiting upload |
| Tally votes | Tally | ~9,550 | Awaiting upload |
| Tally delegates | Tally | ~37,876 | Awaiting upload |
| Delegations | On-chain | TBD | Not started |
| Token distribution | On-chain | TBD | Not started |
| Treasury flows | On-chain | TBD | Not started |
| Grants | Grants portal | TBD | Not started |
| Compensation | Forum/On-chain | TBD | Not started |
| Delegate profiles | Interviews | TBD | Not started |

## Pipeline Assets

- **27 assets** across three layers (11 bronze, 11 silver, 5 gold)
- **8 asset checks** for row counts, taxonomy conformance, and completeness
- All assets visible in Dagster UI with dependency graph

## Key Files

- `taxonomy.yaml` — Controlled vocabularies (single source of truth)
- `bronze/*/metadata.json` — Schema hints and expected record counts
- `docs/taxonomy.md` — Human-readable taxonomy reference
- `docs/data-dictionary.md` — Full schema definitions
- `docs/collection-log.md` — Dataset provenance tracking
