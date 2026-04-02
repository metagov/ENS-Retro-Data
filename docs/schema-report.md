# ENS-Retro-Data: Schema Report

> For dashboard and chart preparation. Last updated: 2026-04-02.

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
| `financial/ens_ledger_transactions.csv` | 2,315 | Transaction Hash, Date (YYYY-MM-DD), Quarter, From (wallet label), To (recipient label), Category (84 types), Amount, Asset (ENS/ETH/USDC), Value (USD) |
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
| `stg_compensation` | bronze_financial.compensation | recipient_address, amount, token, period, working_group, role |
| `stg_grants` | bronze_grants.grants | grant_id, title, applicant, amount_requested (null), amount_awarded, token, status, working_group, description |
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
| `clean_tally_proposals` | wei→ether, lowercase proposer, distinct on proposal_id | proposal_id, title, body, proposer_address, status, for_votes, against_votes, abstain_votes, start_block, end_block, source |
| `clean_tally_votes` | support_code→vote_choice, wei→ether, lowercase voter | vote_id, voter, proposal_id, vote_choice, weight, reason, created_at, source |
| `clean_tally_delegates` | wei→ether, dedup by address | address, name, ens_name, twitter, bio, voting_power, delegators_count, statement, statement_summary, is_seeking_delegation, participation_rate, voted_proposals_count, source |
| `clean_delegations` | unix→datetime, wei→ether, lowercase addresses | delegator, delegate, block_number, delegated_at, token_balance |
| `clean_token_distribution` | wei→ether, recalculate %, lowercase address | address, balance, percentage, snapshot_block |
| `clean_treasury_flows` | wei→ether, unix→datetime, lowercase addresses | tx_hash, from_address, to_address, value_ether, token, block_number, transacted_at, category |
| `clean_compensation` | lowercase fields, distinct on full row | recipient_address, amount, token, period, working_group, role |
| `clean_grants` | lowercase status/working_group, distinct on grant_id | grant_id, title, applicant, amount_requested, amount_awarded, token, status, working_group, description |
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
| `treasury_summary` | clean_treasury_flows + clean_grants + clean_compensation | period (monthly), category, inflows, outflows, net, grant_spend, compensation_spend | Spending over time, category breakdowns, treasury balance |
| `participation_index` *(Python model)* | governance_activity + delegate_scorecard | metric (name), value (numeric) | KPI cards, trend lines |
| `decentralization_index` *(Python model)* | clean_tally_delegates + clean_delegations | metric (name), value (numeric) | Nakamoto coefficient, HHI, Gini coefficient |

---

## Notes for Chart Preparation

- **Timestamps:** All gold/clean layer timestamps are ISO 8601 datetimes (not unix)
- **Token amounts:** All gold/clean layer amounts are in ether, not wei
- **Addresses:** Lowercased uniformly across all layers
- **Tally data:** Historical snapshot only — Tally.xyz shut down, no re-indexing
- **Pending data:** `oso_ens_code_metrics`, `oso_ens_timeseries`, `ens_safe_transactions` not yet collected
- **Grants:** `large_grants.json` records actual disbursements only — `amount_requested` is always null
- **Delegations:** `token_balance` is null by design — join with `token_distribution` for balances
- **Period coverage:** Ledger/financial data spans 2022-04-20 to 2025-11-28

---

## treasury_summary — Data Quality Investigation

> Investigation date: 2026-04-02. Scope: full chain from `treasury_flows.json` → `stg_treasury_flows` → `clean_treasury_flows` → `treasury_summary`.

### Summary

`treasury_summary` has **5 structural data quality issues** that cause `grant_spend` and `compensation_spend` to always be 0, inflows/outflows to be double-counted, USDC amounts to be near-zero, and noise from spam tokens. The model is not currently usable for reliable financial analysis without fixes.

---

### Issue 1 — Category mismatch: grant/compensation joins always return 0 (CRITICAL)

**What happens:** `treasury_summary.sql` joins `clean_treasury_flows` with `clean_grants` and `clean_compensation` on `category = working_group`. But ALL 622 records in `treasury_flows.json` have `category = "unknown"`. The lowercased working groups in grants are `ecosystem`, `public goods`; in compensation they are `community wg`, `ecosystem`, `metagov`, `providers`, `public goods`. The intersection with `unknown` is empty — the join **never matches**, so `grant_spend` and `compensation_spend` are always `0` for every row.

**Root cause:** `treasury_flows.json` was ingested without category labels. The category field needs to be populated (e.g. by mapping ENS treasury wallet addresses to known working groups) before this join can produce real results.

**Impact:** `grant_spend` and `compensation_spend` columns in the gold model are always `coalesce(null, 0) = 0`. Charts built on these columns will show no grant or compensation spend.

---

### Issue 2 — Double-counted inflows/outflows (HIGH)

**What happens:** The directional logic in `treasury_summary.sql` is:
```sql
sum(case when to_address is not null then value_ether else 0 end) as outflows,
sum(case when from_address is not null then value_ether else 0 end) as inflows
```
621 of 622 records have **both** `from` and `to` populated (only 1 record has an empty `to`). This means the same transaction value is counted **once as an inflow and once as an outflow** for every normal transfer. Both inflows and outflows are inflated by the same amount, and `net` (inflows − outflows) is near-zero for all rows regardless of actual cash flow.

**Root cause:** Direction should be determined by whether the treasury address appears in `from` (outflow) or `to` (inflow), not by null-checking both fields. The known ENS DAO treasury addresses (e.g. from `financial/enswallets.json`) need to be used as the reference set.

---

### Issue 3 — USDC decimal mismatch: USDC amounts near-zero (HIGH)

**What happens:** The `wei_to_ether` macro divides all `value_raw` by `1e18`:
```sql
try_cast(value_raw as double) / 1e18
```
ETH and ENS use 18 decimal places, so this is correct for them. USDC uses **6 decimal places**. Dividing a USDC raw value by `1e18` instead of `1e6` underestimates every USDC amount by a factor of `1e12`.

**Example:** Raw USDC value `10318098311236` → correct: `$10,318,098 USDC` → actual output: `~0.00001 ETH`.

**Impact:** All 104 non-zero USDC treasury flow records are effectively zeroed out in the silver/gold layers. Any financial totals that include USDC are massively understated.

**Affected records:** 104 non-zero USDC records in `treasury_flows.json`. Fix requires a token-aware conversion macro.

---

### Issue 4 — Spam/dust token contamination (MEDIUM)

**What happens:** `treasury_flows.json` contains 87 records (14%) with token names that are phishing URLs or dust tokens. Examples:
- `'$ USDCNotice.com <- Visit to secure your wallet'`
- `'Visit https://atuni.site'`
- `'LOFE'` (14 records)

These appear because ENS treasury addresses receive unsolicited token transfers. The `clean_treasury_flows` silver model has no filter on recognized tokens — it passes all records through. In `treasury_summary`, these inflate row counts and distort aggregations.

**Legitimate tokens:** `ETH` (110 records), `ENS` (319 records), `USDC` (104 records), `USDT` (1), `WETH` (1) = 535 legitimate records. The remaining 87 (14%) are noise.

**Fix:** Add a `token IN ('ETH', 'ENS', 'USDC', 'USDT', 'WETH')` filter in `clean_treasury_flows`.

---

### Issue 5 — Richer source unused: `ens_ledger_transactions.csv` not wired in (MEDIUM)

**What happens:** `bronze/financial/ens_ledger_transactions.csv` has **2,316 records** with labeled `From`/`To` (e.g. "DAO Wallet", "Ecosystem WG"), 84 distinct `Category` values (Salaries, DAO Wallet, Stream, $ENS Distribution, Support, Eco. Small Grants, IRL, PG Small Grants, Eco. Grants, Hackathons, …), amounts, and USD values. This file has the category labels that `treasury_flows.json` lacks.

The ledger CSV is documented in the schema report (Bronze → Financial) but is **not sourced** into any dbt staging model. Currently, `treasury_summary` uses only the raw address-level `treasury_flows.json` (all `category='unknown'`). The labeled ledger data would directly resolve Issue 1 (category joins).

**Date range:** 2022-03-31 to 2025-11-28 (approximately 15 quarters of data).

---

### Issue 6 — Minimal dbt tests on treasury_summary (LOW)

`_gold.yml` defines only 1 test for `treasury_summary` (`not_null:warn` on `period`) compared to 5+ tests for `governance_activity` and `delegate_scorecard`. The description still reads "placeholder until on-chain data collected" even though the data is collected. No tests exist for `inflows`, `outflows`, `net`, `grant_spend`, or `compensation_spend`.

---

### Data Completeness by Column

| Column | Source | Issue | Status |
|---|---|---|---|
| `period` | treasury_flows.timestamp | Correct — 50 months Nov 2021–Mar 2026 | ✅ OK |
| `category` | treasury_flows.category | All rows are `"unknown"` | ❌ Broken |
| `inflows` | treasury_flows.value (wei→ether) | Double-counted with outflows; USDC decimals wrong | ❌ Broken |
| `outflows` | treasury_flows.value (wei→ether) | Double-counted with inflows; USDC decimals wrong | ❌ Broken |
| `net` | inflows − outflows | Near-zero due to double-counting | ❌ Broken |
| `grant_spend` | clean_grants.amount_awarded | Always 0 due to category mismatch | ❌ Broken |
| `compensation_spend` | clean_compensation.amount | Always 0 due to category mismatch | ❌ Broken |

### Recommended Fixes (priority order)

1. **Wire `ens_ledger_transactions.csv` into a `stg_ens_ledger` model** — it has real categories and labeled addresses, resolves Issues 1 and 2.
2. **Fix directional logic** — determine flow direction by matching treasury wallet addresses (from `enswallets.json`) against `from_address`/`to_address`.
3. **Fix USDC decimal conversion** — use a token-aware macro: divide USDC by `1e6`, ETH/ENS by `1e18`.
4. **Filter spam tokens** in `clean_treasury_flows` — whitelist `ETH`, `ENS`, `USDC`, `USDT`, `WETH`.
5. **Update `_gold.yml`** — fix stale description, add `not_null`/`accepted_values` tests on key columns.
