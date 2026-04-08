# Data Dictionary

Schema definitions for each layer of the medallion architecture. All tables live in `warehouse/ens_retro.duckdb`.

> **Schema naming:** dbt writes into DuckDB schemas prefixed with `main_` (DuckDB's default database). When querying, use `main_silver.<table>` or `main_gold.<table>`. For brevity this document uses the short `silver.<table>` / `gold.<table>` form that matches dbt's internal model references.

## Bronze Layer (raw JSON/CSV)

Bronze is not a DuckDB schema — it's raw files on disk that dbt staging views read directly via `read_json_auto()` / `read_csv_auto()`. The columns below describe the shape of each raw file.

### `bronze/governance/snapshot_proposals.json`
| Column | Type | Description |
|---|---|---|
| id | string | Snapshot proposal ID |
| title | string | Proposal title |
| body | string | Proposal body (markdown) |
| choices | array\<string\> | Available vote choices |
| start | int | Start timestamp (unix) |
| end | int | End timestamp (unix) |
| state | string | Proposal state |
| scores | array\<float\> | Vote scores per choice |
| scores_total | float | Total voting power cast |
| votes | int | Number of votes |
| author | string | Proposer address |
| type | string | Voting system (single-choice, weighted, etc.) |

### `bronze/governance/snapshot_votes.json`
| Column | Type | Description |
|---|---|---|
| id | string | Vote ID |
| voter | string | Voter address |
| choice | int / object | Choice index or weighted choice |
| vp | float | Voting power |
| created | int | Vote timestamp (unix) |
| proposal_id | string | Parent proposal ID (injected at fetch time) |

### `bronze/governance/tally_*.json` (historical — frozen)
See `docs/developer-docs/bronze-layer.md` for the frozen-source note. Schemas retained for historical research.

### `bronze/on-chain/delegations.json`
| Column | Type | Description |
|---|---|---|
| delegator | string | Address changing its delegation |
| delegate | string | Delegate address |
| block_number | int | Block of the event |
| timestamp | int | Unix timestamp |
| tx_hash | string | Transaction hash |

### `bronze/on-chain/token_distribution.json`
Token transfer events. Aggregated into holder balances during silver transformation.

### `bronze/on-chain/treasury_flows.json`
Raw treasury transaction events for all ENS working-group Safes.

### `bronze/financial/ens_ledger_transactions.csv`
Maintained financial ledger with category tagging. Columns include `tx_hash`, `tx_date`, `category`, `flow_type`, `asset`, `value_usd`.

### `bronze/financial/ens_safe_transactions.json`
Safe API transaction history per wallet. Flattened into the ledger during silver.

### `bronze/forum/forum_topics.json`
Discourse topic metadata (id, title, category, created_at, posts_count).

### `bronze/forum/forum_posts.json`
Per-topic posts with author, created_at, raw markdown.

### `bronze/grants/smallgrants_proposals.json` + `smallgrants_votes.json`
SmallGrants Snapshot space dumps with per-round metadata.

### `bronze/github/oso_*.json`
OSO code metrics: repo list, aggregate code metrics, activity timeseries.

## Silver Layer (cleaned, typed)

16 tables in the `silver` schema. Key transforms applied uniformly:

- Addresses lowercased and trimmed
- Wei values converted to float ETH (18-decimal shift)
- Timestamps parsed to `TIMESTAMP`
- Categorical values validated against `taxonomy.yaml`
- Duplicates removed on primary keys

### `silver.clean_snapshot_proposals`
| Column | Type | Description |
|---|---|---|
| proposal_id | string | Renamed from `id` |
| title | string | |
| body | string | |
| status | string | Renamed from `state`, normalized |
| author_address | string | Lowercased |
| start_date | timestamp | Converted from unix |
| end_date | timestamp | Converted from unix |
| vote_count | int | |
| scores_total | float | |
| quorum | float | |
| proposal_type | string | Heuristic category from title prefix |
| source | string | Always `'snapshot'` |

### `silver.clean_snapshot_votes`
| Column | Type | Description |
|---|---|---|
| vote_id | string | Renamed from `id` |
| proposal_id | string | |
| voter | string | Lowercased |
| vote_choice | string | Mapped via `map_vote_choice_snapshot()` |
| voting_power | float | Renamed from `vp` |
| created_at | timestamp | Converted from unix |
| source | string | Always `'snapshot'` |

### `silver.clean_tally_proposals` / `clean_tally_votes` / `clean_tally_delegates`
Same transform pattern as the Snapshot equivalents. Vote weights converted from wei via `wei_to_ether()`.

### `silver.clean_delegations`
| Column | Type | Description |
|---|---|---|
| delegator | string | |
| delegate | string | |
| block_number | int | |
| timestamp | timestamp | |
| tx_hash | string | |

### `silver.clean_token_distribution`
| Column | Type | Description |
|---|---|---|
| address | string | Primary key |
| balance_eth | float | |
| percentage | float | Share of total supply |
| snapshot_block | int | |

### `silver.clean_treasury_flows`
| Column | Type | Description |
|---|---|---|
| tx_hash | string | Primary key |
| from_address | string | |
| to_address | string | |
| value_eth | float | |
| token | string | |
| block_number | int | |
| timestamp | timestamp | |

### `silver.clean_ens_ledger`
| Column | Type | Description |
|---|---|---|
| tx_hash | string | |
| tx_date | date | |
| category | string | From `taxonomy.yaml` category enum |
| flow_type | string | inflow / outflow / internal_transfer |
| asset | string | ENS / ETH / USDC |
| value_usd | float | |

### `silver.clean_grants` / `clean_compensation`
Silver wrappers for grants + compensation records, with working group + role validated against taxonomy.

### `silver.clean_oso_ens_code_metrics` / `clean_oso_ens_timeseries`
OSO GitHub activity metrics cleaned and typed.

### `silver.address_crosswalk`
Unified address lookup merging addresses from every silver source.

| Column | Type | Description |
|---|---|---|
| address | string | Primary key |
| ens_name | string | Resolved ENS name if available |
| sources | array\<string\> | List of sources that reference this address |

### `silver.snapshot_discourse_crosswalk` / `tally_discourse_crosswalk`
Links proposals to their discussion topics on the ENS governance forum.

| Column | Type | Description |
|---|---|---|
| proposal_id | string | Proposal in the governance source |
| topic_id | int | Discourse topic ID |
| match_source | string | How the link was established (title match, URL reference, manual) |

## Gold Layer (analysis-ready)

6 tables in the `gold` schema.

### `gold.governance_activity` (SQL)
Unified view of all governance proposals from Snapshot + Tally with vote percentages.

| Column | Type | Description |
|---|---|---|
| proposal_id | string | Unique proposal ID |
| source | string | `snapshot` or `tally` |
| title | string | Proposal title |
| status | string | Normalized status |
| vote_count | int | Number of votes cast |
| voter_count | int | Distinct voters |
| for_pct | float | % voting power for |
| against_pct | float | % voting power against |
| abstain_pct | float | % voting power abstain |
| start_date | timestamp | |
| end_date | timestamp | |

### `gold.governance_discourse_activity` (SQL)
Joins `governance_activity` to Discourse topic discussion via the silver crosswalks.

| Column | Type | Description |
|---|---|---|
| source | string | `snapshot` or `tally` |
| proposal_id | string | |
| has_forum_discussion | bool | True if a matching topic exists |
| match_source | string | From the crosswalk |
| topic_id | int | Discourse topic ID (nullable) |

### `gold.delegate_scorecard` (SQL)
Per-delegate participation metrics.

| Column | Type | Description |
|---|---|---|
| address | string | Delegate address |
| ens_name | string | |
| voting_power | float | Current voting power |
| snapshot_votes_cast | int | |
| tally_votes_cast | int | |
| delegators_count | int | |
| participation_rate | float | % of proposals voted on |

### `gold.treasury_summary` (SQL)
Monthly treasury flows by category, USD-denominated.

| Column | Type | Description |
|---|---|---|
| period | string | YYYY-MM |
| category | string | From taxonomy |
| inflows_usd | float | |
| outflows_usd | float | |
| net_usd | float | |
| internal_transfer_usd | float | |

### `gold.participation_index` (Python)
Composite participation metrics computed via numpy in a Python dbt model.

| Metric | Description |
|---|---|
| `total_proposals` | Total proposals across both platforms |
| `snapshot_proposals` | Snapshot-only proposal count |
| `tally_proposals` | Tally-only proposal count |
| `active_delegates` | Delegates with at least one vote |
| `total_delegates` | All registered delegates |
| `avg_participation_rate` | Mean participation rate |
| `voting_power_gini` | Gini coefficient for delegate voting power |
| `token_gini` | Gini coefficient for token distribution |

Returned as long format (`metric`, `value`).

### `gold.decentralization_index` (Python)
Power-concentration analysis metrics.

| Metric | Description |
|---|---|
| `nakamoto_coefficient` | Min delegates needed for > 50% voting power |
| `voting_power_hhi` | Herfindahl-Hirschman Index for voting power |
| `token_hhi` | HHI for token distribution |
| `top_10_delegation_pct` | % of voting power held by top 10 delegates |
| `unique_delegators` | Distinct delegator addresses |
| `unique_delegates_receiving` | Distinct delegate addresses receiving delegation |

Returned as long format (`metric`, `value`).

## Conventions

- **Timestamps:** All silver/gold timestamps are `TIMESTAMP` (ISO 8601 in text form), never unix epochs. Unix conversion happens in silver.
- **Token amounts:** Silver values are in ETH (float), not wei. `treasury_summary` is the exception — it uses USD because the underlying ledger is USD-denominated.
- **Addresses:** All addresses are lowercase 42-char hex strings starting with `0x`. Mixed-case → lowercase in silver.
- **Status enums:** Every status / category / role string is validated against `taxonomy.yaml`. Dbt tests enforce this via `accepted_values`.
