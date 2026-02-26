# dbt Models

All SQL and Python models in the dbt project, organized by layer.

## Configuration

**Project:** `infra/dbt/dbt_project.yml`
**Profile:** `infra/dbt/profiles.yml`
**Warehouse:** DuckDB at `warehouse/ens_retro.duckdb`

```yaml
# Materialization strategy
staging:  views   (schema: bronze)
silver:   tables  (schema: silver)
gold:     tables  (schema: gold)
seeds:    tables  (schema: reference)
```

## Custom Macros

Located in `infra/dbt/macros/`.

### `lowercase_address(column_name)`
Lowercases and trims Ethereum addresses.
```sql
lower(trim({{ column_name }}))
```

### `wei_to_ether(column_name)`
Converts wei values (18 decimals) to ether.
```sql
try_cast({{ column_name }} as double) / 1e18
```

### `unix_ts_to_timestamp(column_name)`
Converts Unix epoch seconds to a timestamp.
```sql
to_timestamp(try_cast({{ column_name }} as bigint))
```

### `map_vote_choice_snapshot(column_name)`
Maps Snapshot integer vote choices to strings.
```
1 → 'for', 2 → 'against', 3 → 'abstain', else → 'unknown'
```

### `map_vote_choice_tally(column_name)`
Maps Tally integer support codes to strings.
```
0 → 'against', 1 → 'for', 2 → 'abstain', else → 'unknown'
```

### `source(source_name, table_name)` (override)
Custom override of dbt's built-in `source()` macro. Maps dbt source references to DuckDB `read_json_auto()` / `read_csv_auto()` calls using a hardcoded lookup dictionary.

## Staging Layer (13 Views)

All staging models are views in the `bronze` schema. They read directly from bronze JSON/CSV files using the custom `source()` macro.

### Active Models (real data)

| Model                        | Source                                    | Description                      |
|------------------------------|-------------------------------------------|----------------------------------|
| `stg_snapshot_proposals`     | `bronze_governance.snapshot_proposals`     | Raw Snapshot proposals           |
| `stg_snapshot_votes`         | `bronze_governance.snapshot_votes`         | Raw Snapshot votes               |
| `stg_tally_proposals`        | `bronze_governance.tally_proposals`        | Raw Tally proposals (flattened)  |
| `stg_tally_votes`            | `bronze_governance.tally_votes`            | Raw Tally votes (flattened)      |
| `stg_tally_delegates`        | `bronze_governance.tally_delegates`        | Raw Tally delegates (flattened)  |
| `stg_votingpower_delegates`  | `bronze_governance.votingpower_delegates`  | votingpower.xyz CSV export       |

### Sentinel Models (placeholder data)

| Model                        | Source                                    | Description                      |
|------------------------------|-------------------------------------------|----------------------------------|
| `stg_delegations`            | `bronze_onchain.delegations`              | On-chain delegation events       |
| `stg_token_distribution`     | `bronze_onchain.token_distribution`       | Token holder balances            |
| `stg_treasury_flows`         | `bronze_onchain.treasury_flows`           | Treasury transactions            |
| `stg_grants`                 | `bronze_grants.grants`                    | Grant applications               |
| `stg_compensation`           | `bronze_financial.compensation`           | Compensation records             |
| `stg_delegate_profiles`      | `bronze_interviews.delegate_profiles`     | Interview-based profiles         |
| `stg_forum_posts`            | `bronze_forum.forum_posts`                | Governance forum posts           |

## Silver Layer (11 Tables)

Silver models apply cleaning transformations: lowercasing addresses, converting timestamps, mapping categorical values, deduplicating records.

### `clean_snapshot_proposals`
**Input:** `stg_snapshot_proposals`
**Key transforms:**
- Renames `id` → `proposal_id`, `state` → `status`
- Lowercases `author` address
- Converts Unix `start`/`end` to timestamps
- Adds `source = 'snapshot'`

**Output columns:** `proposal_id`, `title`, `body`, `status`, `author_address`, `start_date`, `end_date`, `vote_count`, `scores_total`, `quorum`, `proposal_type`, `source`

### `clean_snapshot_votes`
**Input:** `stg_snapshot_votes`
**Key transforms:**
- Renames `id` → `vote_id`, `vp` → `voting_power`
- Lowercases `voter` address
- Maps integer `choice` → `for`/`against`/`abstain` via `map_vote_choice_snapshot()`
- Converts Unix `created` to timestamp
- Adds `source = 'snapshot'`

**Output columns:** `vote_id`, `proposal_id`, `voter`, `vote_choice`, `voting_power`, `created_at`, `source`

### `clean_tally_proposals`
**Input:** `stg_tally_proposals`
**Key transforms:**
- Renames `id` → `proposal_id`
- Lowercases `proposer` address
- Casts `for_votes`, `against_votes`, `abstain_votes` to double
- Adds `source = 'tally'`

**Output columns:** `proposal_id`, `title`, `description`, `status`, `proposer`, `start_block`, `end_block`, `for_votes`, `against_votes`, `abstain_votes`, `source`

### `clean_tally_votes`
**Input:** `stg_tally_votes`
**Key transforms:**
- Renames `id` → `vote_id`
- Lowercases `voter` address
- Maps integer `support` → `for`/`against`/`abstain` via `map_vote_choice_tally()`
- Adds `source = 'tally'`

**Output columns:** `vote_id`, `proposal_id`, `voter`, `vote_choice`, `weight`, `reason`, `source`

### `clean_tally_delegates`
**Input:** `stg_tally_delegates`
**Key transforms:**
- Lowercases `address`
- Converts `voting_power` via `wei_to_ether()`
- Casts count columns to integers

**Output columns:** `address`, `ens_name`, `voting_power`, `delegators_count`, `votes_count`, `proposals_count`, `statement`

### `clean_delegations` (sentinel)
**Input:** `stg_delegations`
**Transforms:** Lowercases delegator/delegate addresses, converts timestamp.

### `clean_token_distribution` (sentinel)
**Input:** `stg_token_distribution`
**Transforms:** Lowercases address, computes ownership percentage.

### `clean_treasury_flows` (sentinel)
**Input:** `stg_treasury_flows`
**Transforms:** Lowercases addresses, converts wei to ether, categorizes flows.

### `clean_grants` (sentinel)
**Input:** `stg_grants`
**Transforms:** Lowercases working group, casts amounts.

### `clean_compensation` (sentinel)
**Input:** `stg_compensation`
**Transforms:** Lowercases addresses and roles.

### `address_crosswalk`
**Input:** Multiple silver tables
**Purpose:** Unified address lookup merging addresses from all sources.
**Output columns:** `address`, `ens_name`, `sources` (array of source names)

## Gold Layer (5 Tables)

### `governance_activity` (SQL)
**Input:** `clean_snapshot_proposals`, `clean_tally_proposals`, `clean_snapshot_votes`
**Purpose:** Unified view of all governance proposals from both platforms.

Combines Snapshot and Tally proposals via `UNION ALL`. For Snapshot proposals, joins vote counts and computes for/against/abstain power percentages.

**Output columns:** `proposal_id`, `source`, `title`, `status`, `vote_count`, `voter_count`, `for_pct`, `against_pct`, `abstain_pct`, `start_date`, `end_date`

### `delegate_scorecard` (SQL)
**Input:** `clean_tally_delegates`, `clean_snapshot_votes`, `clean_tally_votes`, `governance_activity`, `address_crosswalk`
**Purpose:** Per-delegate participation metrics.

Joins delegates with vote counts from both platforms. Computes participation rate as `(snapshot_votes + tally_votes) / (snapshot_proposals + tally_proposals) * 100`.

**Output columns:** `address`, `ens_name`, `voting_power`, `snapshot_votes_cast`, `tally_votes_cast`, `delegators_count`, `participation_rate`

### `treasury_summary` (SQL, placeholder)
**Input:** `clean_treasury_flows`, `clean_grants`, `clean_compensation`
**Purpose:** Monthly treasury flows aggregated by category.

Currently returns no data (all inputs are sentinel placeholders).

**Output columns:** `period`, `category`, `inflows`, `outflows`, `net`, `grant_spend`, `compensation_spend`

### `participation_index` (Python)
**Input:** `governance_activity`, `delegate_scorecard`, `clean_token_distribution`
**Purpose:** Composite participation metrics with Gini coefficients.

Python dbt model using numpy to compute statistical metrics.

**Metrics produced:**
| Metric                    | Description                                      |
|---------------------------|--------------------------------------------------|
| `total_proposals`         | Total proposals across both platforms             |
| `snapshot_proposals`      | Snapshot-only proposal count                      |
| `tally_proposals`         | Tally-only proposal count                         |
| `active_delegates`        | Delegates with at least one vote                  |
| `total_delegates`         | All registered delegates                          |
| `avg_participation_rate`  | Mean participation rate of active delegates       |
| `voting_power_gini`       | Gini coefficient for delegate voting power        |
| `token_gini`              | Gini coefficient for token distribution           |

### `decentralization_index` (Python)
**Input:** `clean_token_distribution`, `clean_delegations`, `delegate_scorecard`
**Purpose:** Power distribution analysis metrics.

Python dbt model using numpy for concentration analysis.

**Metrics produced:**
| Metric                      | Description                                     |
|-----------------------------|-------------------------------------------------|
| `nakamoto_coefficient`      | Min delegates needed for >50% voting power      |
| `voting_power_hhi`          | Herfindahl-Hirschman Index for voting power     |
| `token_hhi`                 | HHI for token distribution                      |
| `top_10_delegation_pct`     | % of voting power held by top 10 delegates      |
| `unique_delegators`         | Distinct delegator addresses                     |
| `unique_delegates_receiving`| Distinct delegate addresses receiving delegation|

## Seeds

Generated from `taxonomy.yaml` by `scripts/generate_taxonomy_seeds.py`.

| Seed                              | Schema      | Content                        |
|-----------------------------------|-------------|--------------------------------|
| `taxonomy_proposal_status.csv`    | reference   | 7 status values                |
| `taxonomy_vote_choices.csv`       | reference   | 3 vote choices                 |
| `taxonomy_sources.csv`            | reference   | 9 data sources                 |
| `taxonomy_stakeholder_roles.csv`  | reference   | 8 stakeholder roles            |
| `taxonomy_working_groups.csv`     | reference   | 4 working groups               |

## dbt Packages

Declared in `infra/dbt/packages.yml`:

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
```

Install with:
```bash
uv run dbt deps --project-dir infra/dbt --profiles-dir infra/dbt
```
