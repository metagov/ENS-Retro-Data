# ENS-Retro-Data: Schema Report

> For dashboard and chart preparation. Last updated: 2026-04-02 (treasury pipeline rebuilt).

---

## BRONZE LAYER — Raw Ingestion

~315,000+ records across 6 domains. All files live under `bronze/`.

### Governance

| File | Records | Key Fields |
|---|---|---|
| `governance/snapshot_proposals.json` | 90 | id, title, author, state, choices, scores, scores_total, votes, start/end (unix ts) |
| `governance/snapshot_votes.json` | 47,551 | id, voter (address), choice, vp (voting power), created (unix ts), proposal_id |
| `governance/tally_proposals.json` | 66 | id, title, status, proposer, for/against/abstain_votes (wei), start/end_block — **historical snapshot** |
| `governance/tally_votes.json` | 9,987 | id, voter, support, weight (wei), reason, proposal_id — **historical snapshot** |
| `governance/tally_delegates.json` | 37,891 | address, ens_name, voting_power, delegators_count, statement, statement_summary, participation_rate — **historical snapshot** |
| `governance/votingpower-xyz/ens-delegates-2026-02-20.csv` | point-in-time | Rank, Delegate (address/ENS), Voting Power, 30-day change, Delegations count, On-chain Votes |

> Tally.xyz shut down in 2026. Tally files are frozen historical snapshots — no re-indexing possible.

### Financial

| File | Records | Key Fields |
|---|---|---|
| `financial/ens_ledger_transactions.csv` | 2,316 | Transaction Hash, Date (YYYY-MM-DD), Quarter, From (wallet label), To (recipient label), Category (84 types), Amount (token units), Asset (ENS/ETH/USDC), Value (USD) — **primary source for treasury_summary** |
| `financial/compensation.json` | 599 | id, recipient, amount, token, value_usd, period, date, working_group, role, category |
| `financial/enswallets.json` | — | name, address, working_group, type, multisig_config, balances |
| `financial/ens_wallet_balances.json` | 17 | wallet address, ETH/ENS/USDC balances |
| `financial/ens_safe_transactions.json` | ⏳ pending | safe_address, tx_hash, direction, token, amount, category, date |

**compensation.json category breakdown:** Salaries (384), Stream (196), Fellowship (9), Steward Gas Ref. (7), Delegate Gas Ref. (3)

### Grants

| File | Records | Key Fields |
|---|---|---|
| `grants/large_grants.json` | 423 | id, applicant, amount_awarded, token, value_usd, working_group, description (category), date, quarter — **~$3.3M total** |
| `grants/smallgrants_proposals.json` | 24 | id, title, choices, scores, scores_total, votes, author, start/end |
| `grants/smallgrants_votes.json` | 1,562 | id, voter, choice, vp, created (unix ts), proposal_id |

**large_grants categories:** Discretionary Grants, Eco. Grants, Eco. Small Grants, Gitcoin Grants, Grant Platform, Growth Grants, Mini Grants, PG Grants, PG Large Grants, PG Small Grants, Retro Grants

### Forum

| File | Records | Key Fields |
|---|---|---|
| `forum/forum_topics.json` | 2,489 | topic_id, title, category_id, tags, created_at, posts_count, views, like_count |
| `forum/forum_posts.json` | 21,747 | post_id, topic_id, username (author), cooked (HTML body), created_at, like_count, reply_count |

### GitHub (via Open Source Observer)

| File | Records | Key Fields |
|---|---|---|
| `github/oso_ens_repos.json` | 962 | artifact_id, artifact_name, artifact_namespace (GitHub org), artifact_source, project_id, project_name |
| `github/oso_ens_code_metrics.json` | ⏳ not fetched | star_count, fork_count, contributor_count, contributor_count_6m, active_developer_count_6m, commit_count_6m, merged_PR_count_6m, opened_issue_count_6m, first_commit_date, last_commit_date |
| `github/oso_ens_timeseries.json` | ⏳ not fetched | artifact_id, event_type (COMMIT_CODE / PULL_REQUEST_MERGED / ISSUE_OPENED / …), amount (daily count), event_time |

### On-chain

| File | Records | Key Fields |
|---|---|---|
| `on-chain/delegations.json` | 123,051 | delegator (address), delegate (address), block_number, timestamp (unix) — `token_balance` is null by design |
| `on-chain/token_distribution.json` | 67,190 | address, balance (wei), percentage, snapshot_block |
| `on-chain/treasury_flows.json` | 622 | tx_hash, from (address), to (address), value (wei), token, block_number, timestamp (unix) |

---

## SILVER LAYER — Cleaned & Normalized (dbt)

Models live in `infra/dbt/models/staging/` and `infra/dbt/models/silver/`.

### Staging models — 1:1 rename/cast from bronze

| Model | Source | Output Columns |
|---|---|---|
| `stg_snapshot_proposals` | bronze_governance.snapshot_proposals | proposal_id, title, body, author_address, status, proposal_type, choices, scores, scores_total, vote_count, start_ts, end_ts, snapshot_block |
| `stg_snapshot_votes` | bronze_governance.snapshot_votes | vote_id, voter, choice_index, voting_power, created_ts, proposal_id |
| `stg_tally_proposals` | bronze_governance.tally_proposals | proposal_id, title, status, proposer_address, for_votes_wei, against_votes_wei, abstain_votes_wei, start_block, end_block, created_timestamp |
| `stg_tally_votes` | bronze_governance.tally_votes | vote_id, voter, support_code, weight_wei, reason, tx_hash, proposal_id, block_timestamp |
| `stg_tally_delegates` | bronze_governance.tally_delegates | address, name, ens_name, twitter, bio, voting_power_wei, delegators_count, statement, statement_summary, is_seeking_delegation, participation_rate, voted_proposals_count |
| `stg_votingpower_delegates` | bronze_governance.votingpower_delegates | rank, delegate_address, voting_power, voting_power_30d_change, delegations_count, onchain_votes_count |
| `stg_delegations` | bronze_onchain.delegations | delegator, delegate, block_number, timestamp_unix, token_balance_wei |
| `stg_token_distribution` | bronze_onchain.token_distribution | address, balance_wei, percentage, snapshot_block |
| `stg_treasury_flows` | bronze_onchain.treasury_flows | tx_hash, from_address, to_address, value_raw, token, block_number, timestamp_unix, category |
| `stg_ens_ledger` | bronze_financial.ens_ledger | tx_hash, tx_date, quarter, source_entity, destination, category, amount, asset, value_usd |
| `stg_compensation` | bronze_financial.compensation | id, recipient_address, amount, token, value_usd, period, date, working_group, role, category |
| `stg_grants` | bronze_grants.grants | grant_id, title, applicant, amount_requested (null), amount_awarded, token, value_usd, status, working_group, description, date, quarter |
| `stg_forum_posts` | bronze_forum.forum_posts | post_id, topic_id, author, body, created_at, likes, reply_count |
| `stg_delegate_profiles` | bronze_governance.tally_delegates | address, name (ens_name or name), role (null), interview_date (null), key_themes (statement_summary), summary (bio) |
| `stg_oso_ens_repos` | bronze_github.oso_ens_repos | artifact_id, artifact_name, artifact_namespace, artifact_source, project_id, project_name |
| `stg_oso_ens_code_metrics` | bronze_github.oso_ens_code_metrics | artifact_id, artifact_name, star_count, fork_count, contributor_count, commit_count_6m, merged_PR_count_6m, opened_issue_count_6m, first_commit_date, last_commit_date |
| `stg_oso_ens_timeseries` | bronze_github.oso_ens_timeseries | artifact_id, artifact_name, event_type, amount, event_time |

### Clean models — deduplicated, normalized

| Model | Key Transformations | Output Columns |
|---|---|---|
| `clean_snapshot_proposals` | unix→datetime, lowercase address, distinct on proposal_id | proposal_id, title, body, author_address, status, proposal_type, choices, scores, scores_total, vote_count, start_date, end_date, source |
| `clean_snapshot_votes` | choice_index→for/against/abstain/unknown, lowercase voter | vote_id, voter, proposal_id, vote_choice, voting_power, created_at, source |
| `clean_tally_proposals` | wei→ether, lowercase proposer, distinct on proposal_id, ISO 8601 timestamps cast to datetime | proposal_id, title, body, proposer_address, status, for_votes, against_votes, abstain_votes, start_block, end_block, start_date, end_date, voter_count, source |
| `clean_tally_votes` | support_code→vote_choice, wei→ether, lowercase voter | vote_id, voter, proposal_id, vote_choice, weight, reason, created_at, source |
| `clean_tally_delegates` | wei→ether, dedup by address | address, name, ens_name, twitter, bio, voting_power, delegators_count, statement, statement_summary, is_seeking_delegation, participation_rate, voted_proposals_count, source |
| `clean_delegations` | unix→datetime, wei→ether, lowercase addresses | delegator, delegate, block_number, delegated_at, token_balance |
| `clean_token_distribution` | wei→ether, recalculate %, lowercase address | address, balance, percentage, snapshot_block |
| `clean_ens_ledger` | lowercase entities, add flow_type (inflow/outflow/internal), filter null value_usd | tx_hash, tx_date, quarter, source_entity, destination, category, amount, asset, value_usd, flow_type |
| `clean_treasury_flows` | token-aware decimal conversion (USDC/USDT÷1e6, others÷1e18), unix→datetime, lowercase addresses, **whitelist ETH/ENS/USDC/USDT/WETH only** | tx_hash, from_address, to_address, value_ether, token, block_number, transacted_at, category |
| `clean_compensation` | lowercase fields, dedup on (recipient, amount, token, period, wg, role, date) | id, recipient_address, amount, token, value_usd, period, date, working_group, role, category |
| `clean_grants` | lowercase status/working_group, SELECT DISTINCT on all columns | grant_id, title, applicant, amount_requested, amount_awarded, token, value_usd, status, working_group, description, date, quarter |
| `clean_oso_ens_code_metrics` | dedup by last_commit_date, cast counts to int | artifact_id, artifact_name, artifact_namespace, star_count, fork_count, contributor_count, commit_count_6m, merged_PR_count_6m, opened_issue_count_6m, first_commit_date, last_commit_date, source |
| `clean_oso_ens_timeseries` | dedup on (artifact_id, event_type, event_time) | artifact_id, artifact_name, event_type, amount, event_time, source |
| `address_crosswalk` | Union of tally/snapshot/delegation addresses | address, ens_name, primary_source |

---

## GOLD LAYER — Analytics & Aggregations (dbt)

Models live in `infra/dbt/models/gold/`.

| Model | Source Tables | Output Columns | Useful for |
|---|---|---|---|
| `governance_activity` | clean_snapshot_proposals + clean_snapshot_votes, clean_tally_proposals | proposal_id, source (snapshot/tally), title, status, vote_count, voter_count, for_pct, against_pct, abstain_pct, start_date, end_date | Vote outcomes over time, participation trends |
| `delegate_scorecard` | clean_tally_delegates + clean_snapshot_votes + clean_tally_votes + governance_activity + address_crosswalk | address, ens_name, voting_power, snapshot_votes_cast, tally_votes_cast, delegators_count, is_seeking_delegation, statement_summary, participation_rate | Delegate rankings, activity heatmaps, leaderboards |
| `treasury_summary` | clean_ens_ledger | period (monthly), category, inflows_usd, outflows_usd, net_usd, internal_transfer_usd | Spending over time, 84-category breakdowns, treasury balance — **amounts in USD** |
| `participation_index` *(Python model)* | governance_activity + delegate_scorecard | metric (name), value (numeric) | KPI cards, trend lines |
| `decentralization_index` *(Python model)* | clean_tally_delegates + clean_delegations | metric (name), value (numeric) | Nakamoto coefficient, HHI, Gini coefficient |

---

## Notes for Chart Preparation

- **Timestamps:** All gold/clean layer timestamps are ISO 8601 datetimes (not unix)
- **Token amounts:** All gold/clean layer amounts are in ether (not wei), **except `treasury_summary` which uses USD**
- **treasury_summary amounts:** `inflows_usd`, `outflows_usd`, `net_usd`, `internal_transfer_usd` are all in USD
- **Addresses:** Lowercased uniformly across all layers
- **Tally data:** Historical snapshot only — Tally.xyz shut down, no re-indexing
- **Pending data:** `oso_ens_code_metrics`, `oso_ens_timeseries`, `ens_safe_transactions` not yet collected
- **Grants:** `large_grants.json` records actual disbursements only — `amount_requested` is always null. `grant_id` is not unique (one grant can have multiple payment rows). 421 rows post-dedup.
- **Compensation:** 598 rows (599 bronze - 1 true duplicate). Monthly payments correctly preserved via date-inclusive dedup key. `category` field added (Salaries/Stream/Fellowship).
- **Delegations:** `token_balance` is null by design — join with `token_distribution` for balances
- **Period coverage:** Ledger/financial data spans 2022-03-31 to 2025-11-28
- **Tally governance timestamps:** All 66 Tally proposals in `governance_activity` now have `start_date` / `end_date` / `voter_count` wired from bronze ISO 8601 timestamps (fixed 2026-04-03).

---

## treasury_summary — Schema & Data Notes

> Pipeline rebuilt 2026-04-02. Source switched from `treasury_flows.json` to `ens_ledger_transactions.csv`.

### Current state (post-fix)

| Column | Source | Notes |
|---|---|---|
| `period` | ens_ledger.tx_date | Monthly buckets, Mar 2022–Nov 2025 (45 months) |
| `category` | ens_ledger.category | 84 real labels (Salaries, Eco. Grants, IRL, DAO Wallet, etc.) |
| `inflows_usd` | flow_type = 'inflow' | External revenue: Registrar ETH, CoW Swap yield, Endowment |
| `outflows_usd` | flow_type = 'outflow' | WG spending: grants, salaries, contractors, IRL, etc. |
| `net_usd` | inflows − outflows | Per-month, per-category net position in USD |
| `internal_transfer_usd` | flow_type = 'internal' | DAO Wallet → WG budget allocations (not end-spend) |

**Output:** 577 rows · 45 months · 84 categories · $121.6M inflows · $25.5M outflows · 21/21 dbt tests pass

### flow_type classification (in `clean_ens_ledger`)

| flow_type | source_entity values | What it represents |
|---|---|---|
| `inflow` | Registrar, CoW Swap, UniSwap, Endowment | External revenue entering the treasury |
| `internal` | DAO Wallet | Budget allocations from treasury to working groups |
| `outflow` | Ecosystem, Metagov, Public Goods, Community WG, Providers, etc. | End-spend to individuals, grantees, contractors |

### Macros updated

| Macro | File | Change |
|---|---|---|
| `wei_to_ether` | `macros/wei_to_ether.sql` | Unchanged — still used for on-chain vote/delegation amounts |
| `token_to_value` *(new)* | `macros/token_to_value.sql` | Token-aware: USDC/USDT ÷ 1e6, all others ÷ 1e18. Used in `clean_treasury_flows`. |

### Why `treasury_flows.json` is no longer the primary treasury source

`bronze/on-chain/treasury_flows.json` (622 raw on-chain records) has three unresolvable problems for financial analysis:
1. All 622 records have `category = "unknown"` — no spend labels
2. 621/622 records have both `from` and `to` populated, making inflow/outflow direction indeterminate without a treasury address whitelist
3. 87 records (14%) are spam/phishing token transfers to treasury addresses

`ens_ledger_transactions.csv` is the ENS Foundation's own labeled bookkeeping ledger and resolves all three. `clean_treasury_flows` is still built and tested for other potential uses (address-level on-chain analysis).
