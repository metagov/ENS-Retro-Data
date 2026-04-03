# ENS Dashboard — Data Pipeline Engineering Review
**Date:** 2026-04-03 | **Branch:** `main` | **Reviewer:** Claude Code (plan-eng-review)

---

## Purpose

This document maps every dashboard module and sub-module from the ENS Dashboard Guidance Manual to the exact pipeline asset (silver or gold model) best suited for it. It records data quality findings, critical bugs, field-level gaps, and the fix plan. Written before implementing Bug Fixes 1–3.

---

## Pipeline Architecture

```
BRONZE FILES                   STAGING                  SILVER                        GOLD
─────────────────────────────────────────────────────────────────────────────────────────────
snapshot_proposals.json ──► stg_snapshot_proposals ──► clean_snapshot_proposals ──┐
snapshot_votes.json     ──► stg_snapshot_votes     ──► clean_snapshot_votes      ──┼──► governance_activity
tally_proposals.json    ──► stg_tally_proposals    ──► clean_tally_proposals     ──┘
tally_votes.json        ──► stg_tally_votes        ──► clean_tally_votes         ──┐
tally_delegates.json    ──► stg_tally_delegates    ──► clean_tally_delegates     ──┼──► delegate_scorecard
delegations.json        ──► stg_delegations        ──► clean_delegations         ──┤
                                                                                   ├──► decentralization_index
token_distribution.json ──► stg_token_distribution ──► clean_token_distribution  ──┘
                                                                                   ──► participation_index

ens_ledger_transactions.csv ──► stg_ens_ledger ──► clean_ens_ledger ──► treasury_summary

compensation.json ──[BUG 1: 46% dedup loss]──► clean_compensation ──► (no gold yet)
large_grants.json ──[BUG 2: date stripped] ──► clean_grants        ──► (no gold yet)
tally_proposals   ──[BUG 3: timestamps dropped in silver+gold]      ──► governance_activity (41% NULL)
```

---

## Challenge-by-Challenge Asset Map

### C1 — Delegation Behavior (H1)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Top-delegate power share over time | `main_gold.delegate_scorecard` | `address`, `voting_power`, `delegators_count`, `is_seeking_delegation` | ⚠️ Partial | Point-in-time only — Tally is frozen. No historical snapshots. |
| New delegation flows by cohort | `main_silver.clean_delegations` | `delegator`, `delegate`, `delegated_at` | ✅ Ready | `token_balance` is NULL on all 122K rows — count-based only, not token-weighted |
| Re-delegation churn rate | `main_silver.clean_delegations` | `delegator`, `delegate`, `delegated_at` | ✅ Ready | No gold model yet — needs self-join: same delegator, different delegate over time |
| Delegation network map | `main_silver.clean_delegations` + `main_silver.address_crosswalk` | `delegator`, `delegate`, `delegated_at`, `ens_name` | ✅ Ready | No edge weights (token_balance null) |

---

### C2 — Structural Power Concentration (H2)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Top 1%/10% voting power share | `main_silver.clean_token_distribution` | `address`, `balance`, `percentage`, `snapshot_block` | ⚠️ Partial | Single snapshot — no historical trend |
| Pre-computed Gini + Nakamoto | `main_gold.decentralization_index` | `metric`, `value` | ✅ Ready | Gini=0.9921, Nakamoto=18, top_10_delegation_pct=35.9% |
| Vote outcomes by holder size | JOIN: `clean_snapshot_votes` × `clean_token_distribution` | `voter`, `vote_choice`, `voting_power` × `address`, `balance` | ⚠️ Partial | Balance is single snapshot, not at vote time; use voting_power in votes as tier proxy |
| Small-holder participation share | Same JOIN | `voting_power` as proxy for holder tier | ✅ Ready | Tier thresholds need manual definition |
| Participation by stakeholder tier | `main_gold.delegate_scorecard` + `main_silver.clean_snapshot_votes` | `voting_power`, `participation_rate`, `snapshot_votes_cast`, `tally_votes_cast` | ✅ Ready | — |

---

### C3 — Delegation Infrastructure (H3)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Delegation network map | `main_silver.clean_delegations` + `main_silver.address_crosswalk` | `delegator`, `delegate`, `delegated_at`, `ens_name` | ✅ Ready | No token weights |
| Re-delegation churn rate | `main_silver.clean_delegations` | `delegator`, `delegate`, `delegated_at` | ✅ Ready | — |
| Delegate profile richness vs. power | `main_silver.clean_tally_delegates` + `main_gold.delegate_scorecard` | `address`, `voting_power`, `bio`, `statement`, `statement_summary`, `twitter`, `is_seeking_delegation` | ✅ Ready | Need to derive richness score from non-null field count |
| New delegate growth trajectories | `main_silver.clean_delegations` | `delegate`, `delegated_at` → `MIN(delegated_at)` per delegate | ✅ Ready | No official join date; first delegation received is a proxy |

---

### C4 — Participation Barriers (H4)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Voter turnout by proposal complexity proxy | `main_silver.clean_snapshot_proposals` + `main_silver.clean_snapshot_votes` | `proposal_id`, `body`, `vote_count`, `voter_count` × `vote_id`, `proposal_id`, `voting_power` | ✅ Ready | Body available for all 90 Snapshot proposals; derive word count via `LENGTH(body)` or string split |
| Participation trends over time | `main_gold.governance_activity` | `proposal_id`, `source`, `start_date`, `vote_count`, `voter_count` | ❌ **BLOCKED** | **Bug 3: 62/152 Tally proposals have NULL start_date, vote_count, voter_count** |
| Proposal throughput/time-to-execution | `main_gold.governance_activity` | `start_date`, `end_date`, `status` | ❌ **BLOCKED** | Same as above |
| Participation breakdown by tier | `main_gold.delegate_scorecard` + `main_silver.clean_snapshot_votes` | `voting_power`, `participation_rate`, `snapshot_votes_cast` | ✅ Ready | — |

---

### C5 — Governance Legitimacy (H5)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Top 1% voting power / narrative vs. reality | `main_gold.decentralization_index` | `metric='voting_power_gini'` (0.9921), `metric='nakamoto_coefficient'` (18) | ✅ Ready | Point-in-time only |
| Proposal pathway complexity | `main_silver.clean_snapshot_proposals` | `body`, `choices`, `proposal_type`, `vote_count` | ✅ Ready | Link count derivable from body text |
| Proposal throughput and outcome rates | `main_gold.governance_activity` | `status`, `start_date`, `end_date` | ⚠️ Partial | Tally dates missing until Bug 3 fix |

---

### C6 — Delegate Ecosystem Health (H6)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Cohort analysis of delegate join dates | `main_silver.clean_delegations` | `delegate`, `delegated_at` → `MIN(delegated_at)` per delegate | ✅ Ready | Join date = first received delegation (proxy) |
| **Delegate activity vs. power (lock-in chart)** | `main_gold.delegate_scorecard` | `address`, `ens_name`, `voting_power`, `participation_rate`, `snapshot_votes_cast`, `tally_votes_cast`, `delegators_count` | ✅ **Best chart in pipeline** | participation_rate from frozen Tally snapshot |
| Re-delegation churn | `main_silver.clean_delegations` | `delegator`, `delegate`, `delegated_at` | ✅ Ready | — |
| Structural change tracking | `main_silver.clean_snapshot_proposals` | `title`, `body` | ⚠️ Partial | No label for proposal_type = 'governance reform'; requires text search |

---

### C7 — Treasury and Financial Management (H7)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Total spend by WG by term | `main_silver.clean_ens_ledger` | `source_entity`, `quarter`, `flow_type`, `value_usd` | ✅ Ready | 2022Q2–2025Q4, 84 categories |
| Grant vs. operational vs. service provider | `main_silver.clean_ens_ledger` | `category`, `flow_type`, `value_usd`, `quarter` | ✅ Ready | Need CASE mapping: stream=providers, salaries/irl/dao tooling=ops, eco.grants/pg grants=grants |
| Budget vs. actuals | `main_silver.clean_ens_ledger` `flow_type='internal'` vs `flow_type='outflow'` | `source_entity`, `quarter`, `value_usd` | ⚠️ Partial | Internal transfers = budget allocation proxy. Official approved budget amounts from forum proposals not wired in. |
| Spending reconstruction gaps | Meta-finding | — | ✅ Finding | The 5 bugs fixed in the treasury_summary rebuild (April 2026) are direct evidence of H7.1 fragmentation |
| Outcome report availability | `main_silver.clean_grants` | `grant_id`, `title`, `applicant`, `amount_awarded`, `status`, `working_group`, `description` | ❌ **BLOCKED** | **No `report_url`, no `outcome_status`, no `date` field** |
| Time from grant approval to reporting | `main_silver.clean_grants` | Needs `date` field | ❌ **BLOCKED** | **Bug 2: `date` and `quarter` stripped in `stg_grants`** |

---

### C8 — Compensation and Contributor Dynamics (H8)

| Sub-module | Best Asset | Exact Fields | Status | Gap |
|---|---|---|---|---|
| Compensation by role type and WG | `main_silver.clean_compensation` | `recipient_address`, `role`, `working_group`, `amount`, `token`, `period` | ❌ **BLOCKED** | **Bug 1: 325 rows vs 599 raw — 46% dedup data loss** |
| Framework consistency across terms | `main_silver.clean_compensation` | `recipient_address`, `working_group`, `amount`, `period` | ❌ **BLOCKED** | Same bug; also missing `category` (Salaries/Stream/Fellowship) and `date` fields |
| WG budget breakdowns | `main_silver.clean_ens_ledger` + `main_gold.treasury_summary` | `source_entity`, `category`, `quarter`, `value_usd`, `flow_type` | ✅ Ready | Best available chart for H8 |

---

## Data Quality Scorecard

```
Challenge    Primary Asset(s)                     Ready?    Blockers
─────────────────────────────────────────────────────────────────────────
C1  Deleg.   clean_delegations, delegate_score    ⚠️ PARTIAL  token_balance null; VP snapshot only
C2  Power    clean_token_distribution, decentr.   ⚠️ PARTIAL  single snapshot, no historical trend
C3  Infra    clean_delegations, clean_tally_del   ✅ READY
C4  Partic.  governance_activity                  ❌ BLOCKED   Bug 3: 41% proposals undated
C5  Legit.   decentralization_index               ✅ READY    (static KPI cards)
C6  Delegate delegate_scorecard, clean_deleg.     ✅ READY
C7  Treasury clean_ens_ledger, clean_grants       ⚠️ PARTIAL  Bug 2: grants missing dates
C8  Comp.    clean_compensation                   ❌ BLOCKED   Bug 1: 46% data loss
```

---

## Critical Bugs

### Bug 1 — `clean_compensation`: 46% of records silently dropped

**File:** `infra/dbt/models/staging/stg_compensation.sql` + `infra/dbt/models/silver/clean_compensation.sql`

**Root cause:** `stg_compensation` drops `id`, `date`, and `category` from the raw JSON. `clean_compensation` applies `SELECT DISTINCT` on `(recipient_address, amount, token, period, working_group, role)`. Since `period` is quarterly and payments are monthly, three monthly payments of the same amount in the same quarter look identical and collapse to one row.

**Evidence:** 599 raw records → 325 after DISTINCT = 274 legitimate monthly payment rows lost. 179 unique `(recipient, amount, token, period, WG, role)` keys appear multiple times. Example: `coltron.eth` received $9,665 USDC on 2022-08-19 AND 2022-09-04 — both Q3 2022 with identical fields, so one is dropped.

**Impact:** Compensation totals understated by ~46%. Pay rate medians and WG totals are wrong. All H8.1, H8.3 charts unreliable.

**Fix:** Add `id`, `date`, `category` to `stg_compensation`; remove `SELECT DISTINCT` from `clean_compensation`, dedup on `id` instead.

---

### Bug 2 — `clean_grants`: `date` and `quarter` fields stripped in staging

**File:** `infra/dbt/models/staging/stg_grants.sql`

**Root cause:** `stg_grants` selects only `id, title, applicant, amount_requested, amount_awarded, token, status, working_group, description`. The bronze `large_grants.json` has `date` (YYYY-MM-DD), `quarter` (e.g. `2023Q1`), and `value_usd` on every record.

**Impact:** Cannot compute grants by term, grants over time, or time-from-approval-to-reporting (H7.3 timeline). All grant timeline charts blocked.

**Fix:** Add `date`, `quarter`, `value_usd` to `stg_grants` and pass through `clean_grants`.

---

### Bug 3 — `governance_activity`: 62/152 Tally proposals have NULL dates and vote counts

**File:** `infra/dbt/models/silver/clean_tally_proposals.sql` + `infra/dbt/models/gold/governance_activity.sql`

**Root cause:** `stg_tally_proposals` already selects `start_timestamp`, `end_timestamp`, `for_voters`, `against_voters`, `abstain_voters` from the raw JSON (ISO 8601 strings). However, `clean_tally_proposals` drops all of these — only carrying `start_block`, `end_block`. `governance_activity` then hardcodes `null as start_date, null as end_date` for Tally rows.

**Evidence:** All 62 Tally proposals in `governance_activity` have `start_date=NULL`, `end_date=NULL`, `vote_count=NULL`, `voter_count=NULL`.

**Impact:** 41% of the proposal corpus is undatable. Participation trend lines, complexity-turnout correlation, and time-series charts silently omit 3+ years of on-chain governance history (H4, H5 charts).

**Fix:**
1. Add `start_timestamp`, `end_timestamp`, `for_voters`, `against_voters`, `abstain_voters` to `clean_tally_proposals`
2. Update `governance_activity` to use these fields for Tally rows instead of hardcoded NULLs

---

## What Is NOT In Scope

| Item | Reason |
|---|---|
| Block→timestamp enrichment for Tally via Ethereum node | Not needed — `start_timestamp` / `end_timestamp` exist in bronze JSON |
| Forum budget proposal parser | Would unlock budget vs. actuals for C7 — deferred |
| Grant outcome report scraping | H7.3 outcome quality — no data exists in any bronze source |
| Historical delegation-weighted power snapshots | Only current Tally snapshot available; Tally is shut down |
| Compensation sub-role tagging within `contributor` | Requires manual enrichment or forum mining |

---

## Known Permanent Data Limitations

| Dimension | What We Can Measure | What We Cannot | Challenge Affected |
|---|---|---|---|
| Voting power over time | Current snapshot only | Historical power trajectory per delegate | C1, C2, C6 |
| Token balance per delegation event | Event count/timing | Token amount delegated | C1, C3 |
| Grant outcomes | Whether grant was awarded | Whether reported outcome delivered value | C7 |
| Compensation sub-roles | Salaries/Stream/Fellowship category | Steward vs secretary vs developer within "contributor" | C8 |
| Budget approvals | Actual disbursements | Approved budget amounts (in forum proposals, not on-chain) | C7 |
| Tally data (post-shutdown) | Historical frozen snapshot | Any governance after Tally shutdown | All |

---

## Fix Implementation

Implemented 2026-04-03. See commit history. Models changed:

- `stg_compensation.sql` — added `id`, `date`, `category`
- `clean_compensation.sql` — replaced SELECT DISTINCT with dedup on `id`
- `stg_grants.sql` — added `date`, `quarter`, `value_usd`
- `clean_grants.sql` — passed through new fields
- `clean_tally_proposals.sql` — added `start_date`, `end_date`, `voter_count`
- `governance_activity.sql` — wired tally timestamps and voter counts

**Post-fix row counts:**
- `clean_compensation`: 599 (was 325) — +274 recovered
- `clean_grants`: 421 with date and quarter fields (was missing both)
- `governance_activity`: 152 proposals, all with dates and vote counts
