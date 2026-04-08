# dbt Models

All SQL and Python models in the dbt project, organized by layer. **40 models total** (18 staging + 16 silver + 6 gold).

## Configuration

**Project:** `infra/dbt/dbt_project.yml`
**Profile:** `infra/dbt/profiles.yml`
**Warehouse:** DuckDB at `warehouse/ens_retro.duckdb`

```yaml
# Materialization strategy (infra/dbt/dbt_project.yml)
models:
  ens_retro:
    staging:   { +materialized: view,  +schema: bronze }
    silver:    { +materialized: table, +schema: silver }
    gold:      { +materialized: table, +schema: gold }
seeds:
  ens_retro:  { +schema: reference }
```

When dbt writes these into DuckDB they land in schemas named `main_bronze`, `main_silver`, `main_gold`, `main_reference` (DuckDB prepends the database name). Query with the `main_<layer>` prefix.

## Custom Macros

Located in `infra/dbt/macros/`.

### `lowercase_address(column_name)`
```sql
lower(trim({{ column_name }}))
```

### `wei_to_ether(column_name)`
```sql
try_cast({{ column_name }} as double) / 1e18
```

### `unix_ts_to_timestamp(column_name)`
```sql
to_timestamp(try_cast({{ column_name }} as bigint))
```

### `map_vote_choice_snapshot(column_name)`
Maps Snapshot integer vote choices to strings. `1 → 'for'`, `2 → 'against'`, `3 → 'abstain'`, else → `'unknown'`.

### `map_vote_choice_tally(column_name)`
Maps Tally support codes: `0 → 'against'`, `1 → 'for'`, `2 → 'abstain'`, else → `'unknown'`.

### `source(source_name, table_name)` (override)
Custom override of dbt's built-in `source()`. Maps dbt source references to DuckDB `read_json_auto()` / `read_csv_auto()` calls via a hardcoded lookup dictionary. This is what lets staging models read directly from bronze JSON/CSV files without a separate ingestion table.

## Staging Layer (18 views)

All staging models are views in the `bronze` schema. They read directly from bronze JSON/CSV files using the custom `source()` macro.

| Model | Source file |
|---|---|
| `stg_snapshot_proposals` | `bronze/governance/snapshot_proposals.json` |
| `stg_snapshot_votes` | `bronze/governance/snapshot_votes.json` |
| `stg_tally_proposals` | `bronze/governance/tally_proposals.json` |
| `stg_tally_votes` | `bronze/governance/tally_votes.json` |
| `stg_tally_delegates` | `bronze/governance/tally_delegates.json` |
| `stg_votingpower_delegates` | `bronze/governance/votingpower-xyz/*.csv` |
| `stg_delegations` | `bronze/on-chain/delegations.json` |
| `stg_token_distribution` | `bronze/on-chain/token_distribution.json` |
| `stg_treasury_flows` | `bronze/on-chain/treasury_flows.json` |
| `stg_ens_ledger` | `bronze/financial/ens_ledger_transactions.csv` |
| `stg_compensation` | `bronze/financial/compensation.json` |
| `stg_grants` | `bronze/grants/*.json` |
| `stg_forum_topics` | `bronze/forum/forum_topics.json` |
| `stg_forum_posts` | `bronze/forum/forum_posts.json` |
| `stg_delegate_profiles` | `bronze/interviews/delegate_profiles.json` (if present) |
| `stg_oso_ens_repos` | `bronze/github/oso_ens_repos.json` |
| `stg_oso_ens_code_metrics` | `bronze/github/oso_ens_code_metrics.json` |
| `stg_oso_ens_timeseries` | `bronze/github/oso_ens_timeseries.json` |

## Silver Layer (16 tables)

Silver models apply cleaning transformations: lowercasing addresses, converting timestamps, mapping categorical values, deduplicating records.

### Governance

#### `clean_snapshot_proposals`
- Renames `id → proposal_id`, `state → status`
- Lowercases `author` → `author_address`
- Converts `start` / `end` → `start_date` / `end_date` timestamps
- Adds `source = 'snapshot'`
- **Output:** `proposal_id, title, body, status, author_address, start_date, end_date, vote_count, scores_total, quorum, proposal_type, source`

#### `clean_snapshot_votes`
- Renames `id → vote_id`, `vp → voting_power`
- Lowercases `voter`
- Maps integer `choice` via `map_vote_choice_snapshot()`
- Converts `created → created_at` timestamp
- Adds `source = 'snapshot'`
- **Output:** `vote_id, proposal_id, voter, vote_choice, voting_power, created_at, source`

#### `clean_tally_proposals`, `clean_tally_votes`, `clean_tally_delegates`
Same transform pattern as the Snapshot equivalents, applied to the (frozen) Tally data. Vote weights converted via `wei_to_ether()`.

### On-chain

#### `clean_delegations`
Lowercases delegator/delegate addresses, converts timestamp, deduplicates.

#### `clean_token_distribution`
Aggregates `Transfer` events into per-holder balances. Lowercases address, converts wei balance to ETH.

#### `clean_treasury_flows`
Lowercases from/to addresses, converts wei to ETH, deduplicates by `tx_hash`.

### Financial

#### `clean_ens_ledger`
Cleaned view of the maintained financial ledger CSV. Columns: `tx_hash, tx_date, category, flow_type, asset, value_usd`. The USD denomination is intentional (ledger is maintained in USD).

#### `clean_compensation`
Steward/contributor compensation records with working group + role validated against `taxonomy.yaml`.

#### `clean_grants`
Unified SmallGrants + large-grant disbursements. Working group validated.

### Crosswalks

#### `address_crosswalk`
Unified address lookup merging addresses from every silver source. One row per unique address with `ens_name` (if resolvable) and `sources` array.

#### `snapshot_discourse_crosswalk` / `tally_discourse_crosswalk`
Links proposals to their ENS governance forum discussion topics. Matching is done via title heuristics, URL references, and manual overrides. Columns: `proposal_id, topic_id, match_source`.

### GitHub (OSO)

#### `clean_oso_ens_code_metrics`
Per-artifact aggregate code metrics (commits, contributors, stars, etc.).

#### `clean_oso_ens_timeseries`
Time-series activity data per artifact and event type.

## Gold Layer (6 tables)

### `governance_activity` (SQL)
**Inputs:** `clean_snapshot_proposals`, `clean_tally_proposals`, `clean_snapshot_votes`, `clean_tally_votes`
**Purpose:** Unified view of all governance proposals from both platforms, with vote percentages.
**Output columns:** `proposal_id, source, title, status, vote_count, voter_count, for_pct, against_pct, abstain_pct, start_date, end_date`

Combines Snapshot and Tally proposals via `UNION ALL`. For each proposal, joins the vote rows and computes for/against/abstain power percentages.

### `governance_discourse_activity` (SQL)
**Inputs:** `governance_activity`, `snapshot_discourse_crosswalk`, `tally_discourse_crosswalk`
**Purpose:** Join proposals to their forum discussion. Used by hypotheses that compare "did this proposal have forum discussion first?" against voting outcomes.
**Output columns:** `source, proposal_id, has_forum_discussion, match_source, topic_id`

### `delegate_scorecard` (SQL)
**Inputs:** `clean_tally_delegates`, `clean_snapshot_votes`, `clean_tally_votes`, `governance_activity`, `address_crosswalk`
**Purpose:** Per-delegate participation metrics.
**Output columns:** `address, ens_name, voting_power, snapshot_votes_cast, tally_votes_cast, delegators_count, participation_rate`

### `treasury_summary` (SQL)
**Inputs:** `clean_ens_ledger`, `clean_treasury_flows`
**Purpose:** Monthly treasury flows aggregated by category, USD-denominated.
**Output columns:** `period, category, inflows_usd, outflows_usd, net_usd, internal_transfer_usd`

### `participation_index` (Python)
**Inputs:** `governance_activity`, `delegate_scorecard`, `clean_token_distribution`
**Purpose:** Composite participation metrics with Gini coefficients. Uses numpy for statistical computation.
**Output shape:** Long format (`metric`, `value`). Metrics: `total_proposals`, `snapshot_proposals`, `tally_proposals`, `active_delegates`, `total_delegates`, `avg_participation_rate`, `voting_power_gini`, `token_gini`.

### `decentralization_index` (Python)
**Inputs:** `clean_token_distribution`, `clean_delegations`, `delegate_scorecard`
**Purpose:** Power-concentration analysis.
**Output shape:** Long format (`metric`, `value`). Metrics: `nakamoto_coefficient`, `voting_power_hhi`, `token_hhi`, `top_10_delegation_pct`, `unique_delegators`, `unique_delegates_receiving`.

## Seeds

Generated from `taxonomy.yaml` by `scripts/generate_taxonomy_seeds.py`.

| Seed | Schema | Content |
|---|---|---|
| `taxonomy_proposal_status.csv` | `reference` | Accepted status values |
| `taxonomy_vote_choices.csv` | `reference` | Vote choice enum |
| `taxonomy_sources.csv` | `reference` | Data source enum |
| `taxonomy_stakeholder_roles.csv` | `reference` | Stakeholder role enum |
| `taxonomy_working_groups.csv` | `reference` | Working group enum |

Run `uv run dbt seed` from `infra/dbt/` to load them.

## dbt Packages

Declared in `infra/dbt/packages.yml`:

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
```

Install with:
```bash
cd infra/dbt
uv run dbt deps
```
