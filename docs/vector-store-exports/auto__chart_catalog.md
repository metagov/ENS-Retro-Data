# ENS Retro — Dashboard Chart Catalog

Machine-readable catalog of every chart on the ENS Retrospective Dashboard (https://ensretro.metagov.org). Each entry includes: public screenshot URL, source warehouse tables, key columns, reproduction SQL, and a live sample of the underlying data. Designed for a ChatKit agent with read-only DuckDB MCP access to cite or reproduce any chart.

**Warehouse connection:** `warehouse/ens_retro.duckdb` (read-only).  
**Query tool:** `query_duckdb(sql)` — SELECT-only, 50-row cap.  
**Vector store:** vs_69d291d5a5fc819194838e0475405ef7  
**Images hosted:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/

---

## C1 — Voting Power Concentration

Voting power concentration refers to the condition where governance authority remains highly  concentrated among initial token recipients with minimal redistribution over time.  In ENS DAO, top delegates hold significant influence while some publicly admit non-participation,  creating a governance system where formal power structures diverge from actual engagement patterns.

### H1.3 — Legacy distribution — early patterns still dominate

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H1_3.png

![Early power frozen?](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H1_3.png)

**Description:** Delegation in ENS DAO concentrates at launch and then becomes structurally locked. Q4 2021 alone accounts for 40% of the top-50 delegates' current voting power — the single largest quarter by a wide margin — and nearly half of all top-50 VP was established before 2023. What followed is near-zero redistribution: once a delegate captures voting power, they rarely lose it. Occasional bursts (Q4'22, Q1'23, Q1'25, Q2'25) add modest increments but never displace the launch cohort's dominance. Token holders do not re-delegate, negative net flows are vanishingly rare among top delegates, and incoming contributors cannot accumulate meaningful delegation through merit alone. The result is a system where governance authority is structurally inherited from the 2021 airdrop moment, not earned through ongoing community participation, creating permanent barriers to entry regardless of contribution or expertise. Community members report that even a single signal from a high-power delegate can dramatically alter individual outcomes, generating animosity within the governance community.

**Source tables:** `main_silver.clean_delegations`, `main_silver.clean_token_distribution`, `main_gold.delegate_scorecard`

**Key columns:** `delegator`, `delegate`, `delegated_at`, `balance`, `voting_power`

**Transformation:** Classifies top-50 delegates' current delegators by the quarter their current delegation was first established, then computes each quarter's share of top-50 VP.

**Reproduction SQL:**

```sql
-- H1.3 — Legacy distribution: VP share by cohort quarter for top-50 delegates
WITH current_delegations AS (
    SELECT delegator, delegate, delegated_at,
           ROW_NUMBER() OVER (PARTITION BY delegator ORDER BY delegated_at DESC) AS rn
    FROM main_silver.clean_delegations
),
active AS (
    SELECT delegator, delegate, delegated_at
    FROM current_delegations
    WHERE rn = 1 AND delegate != '0x0000000000000000000000000000000000000000'
),
active_with_balance AS (
    SELECT a.delegator, a.delegate, a.delegated_at, td.balance AS token_balance
    FROM active a
    JOIN main_silver.clean_token_distribution td ON td.address = a.delegator
    WHERE td.balance > 0
),
delegate_totals AS (
    SELECT delegate, SUM(token_balance) AS total_vp,
           ROW_NUMBER() OVER (ORDER BY SUM(token_balance) DESC) AS rnk
    FROM active_with_balance GROUP BY delegate
),
top50 AS (SELECT delegate FROM delegate_totals WHERE rnk <= 50),
cohorted AS (
    SELECT awb.token_balance,
           date_trunc('quarter', awb.delegated_at)::DATE AS cohort_quarter_start
    FROM active_with_balance awb JOIN top50 t ON t.delegate = awb.delegate
)
SELECT cohort_quarter_start,
       SUM(token_balance) AS vp_in_cohort,
       SUM(token_balance) / SUM(SUM(token_balance)) OVER () * 100 AS pct_of_top50_vp
FROM cohorted GROUP BY cohort_quarter_start ORDER BY cohort_quarter_start
```

**Sample output (top 10 rows, live from warehouse):**

| cohort_quarter_start   |     vp_in_cohort |   pct_of_top50_vp |
|:-----------------------|-----------------:|------------------:|
| 2021-10-01 00:00:00    |      1.20618e+06 |        39.7597    |
| 2022-01-01 00:00:00    | 197474           |         6.5094    |
| 2022-04-01 00:00:00    |  67464.9         |         2.22387   |
| 2022-07-01 00:00:00    |  15834.9         |         0.521972  |
| 2022-10-01 00:00:00    |   6375.36        |         0.210154  |
| 2023-01-01 00:00:00    | 352374           |        11.6155    |
| 2023-04-01 00:00:00    |    801.815       |         0.0264305 |
| 2023-07-01 00:00:00    |    999.593       |         0.03295   |
| 2023-10-01 00:00:00    |   7894.17        |         0.260219  |
| 2024-01-01 00:00:00    |   4239.57        |         0.139751  |

**Chart: When Was Today's Power Established?**

> **Key takeaway:** Today's ENS governance power was established at the 2021 airdrop and has barely moved since. Q4 2021 accounts for 40% of the top-50 delegates' current voting power — the single largest quarter — and nearly half (49.4%) was locked in before 2023. Subsequent quarters add only marginal increments, spread across both the Top 20 and the 21–50 tier. This is genuine legacy lock-in: the delegation relationships formed at launch continue to define who governs ENS today, more than four years later.

**Chart: Net Delegation Flow — Top 20 Delegates**

> **Key takeaway:** Top 20 ENS delegates accumulated their delegator base overwhelmingly at launch and have held it ever since. Q4'21 inflows dwarf every subsequent quarter — most top delegates gained thousands of delegators in that single quarter and single-digits in every quarter since. Red cells (net losses) are vanishingly rare and tiny across 19 quarters. Occasional bursts like Q4'22 and Q1'23 added modest increments for a handful of delegates but did not alter the underlying ranking. This is not organic redistribution — it is a frozen hierarchy, locked in at the moment of the airdrop.

---

### H2.1 — Token-weighted democracy paradox — 1T1V leads to concentration

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H2_1.png

![Few control the vote](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H2_1.png)

**Description:** In a one-token-one-vote system, governance influence mirrors token concentration — not participation breadth. ENS DAO's concentration curve (Gini = 0.9659) shows near-maximum inequality: just 18 delegates hold majority voting power, and the top 1% of delegates control ~84% of total VP. The curve rises almost vertically before flattening far above the 50% threshold, meaning the remaining hundreds of delegates collectively cannot form a majority coalition. This is not a failure of individual engagement — it is a structural consequence of 1T1V when token ownership is concentrated: large holders delegate to a small set of trusted addresses, and that set becomes the effective governing body regardless of how many addresses formally hold tokens. The result is a paradox where a nominally open, democratic system produces oligarchic governance outcomes by design.

**Source tables:** `main_gold.delegate_scorecard`, `main_gold.decentralization_index`

**Key columns:** `voting_power`, `metric`, `value`

**Transformation:** Lorenz curve on voting power distribution. Gini coefficient computed in Python from sorted VP array.

**Reproduction SQL:**

```sql
-- H2.1 — Concentration curve base data
SELECT voting_power FROM main_gold.delegate_scorecard
WHERE voting_power > 0 ORDER BY voting_power DESC
```

**Sample output (top 10 rows, live from warehouse):**

|   voting_power |
|---------------:|
|       253988   |
|       176309   |
|       149723   |
|       146937   |
|       131642   |
|       121283   |
|       114926   |
|       111158   |
|        98996.3 |
|        92543.6 |

**Chart: Concentration Curve — Voting Power vs Delegates**

> **Key takeaway:** ENS governance voting power is distributed with near-maximum inequality — a Gini coefficient of 0.9659, where 1.0 would mean a single delegate holds everything. The concentration curve rises almost vertically from zero: just 18 delegates (the Nakamoto coefficient) collectively control a majority of all active voting power, and the top 1% of delegates hold ~84% of total VP. The curve crosses the 50% threshold so early that the remaining 99% of delegates are effectively spectators. In ENS DAO, governance is formally open to all token holders, but structurally controlled by a group small enough to fit in a conference room.

---

### H3.3 — Low re-delegation churn — delegations rarely change

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H3_3.png

![Delegations never change](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H3_3.png)

**Description:** Token holders in ENS DAO set their delegation once and almost never revisit it. Across 4.3 years of on-chain data, 98.2% of delegators made zero delegate changes — a mean churn rate of 0.0048 changes per year, and only 1,487 out of 82,794 delegators ever re-delegated at all. The survival curve confirms this at every time horizon: retention exceeds 98% at 12 months for both top-20 and smaller-delegate cohorts, barely declining through 50 months. Critically, delegators of top-20 delegates are the least likely to leave — meaning concentration compounds rather than decays over time. This near-zero churn freezes whatever delegation pattern exists at any given moment into a durable power structure. When combined with the Q2 2025 reshuffling seen elsewhere, the pattern becomes clear: governance power shifts in rare, concentrated bursts — and then locks immediately. A direct consequence is that delegates who have publicly acknowledged disengagement retain their voting power indefinitely, because the mechanism that would correct this (re-delegation) is behaviorally near-absent.

**Source tables:** `main_silver.clean_delegations`, `main_gold.delegate_scorecard`

**Key columns:** `delegator`, `delegate`, `delegated_at`

**Transformation:** Per-delegator count of delegate changes (0, 1, 2, 3, 4, 5+) plus Kaplan-Meier survival curves for top-20 vs smaller delegate cohorts.

**Reproduction SQL:**

```sql
-- H3.3 — Churn distribution by number of delegate changes per delegator
WITH excl_self AS (
    SELECT delegator, delegate, delegated_at
    FROM main_silver.clean_delegations
    WHERE delegator != delegate AND delegate != '0x0000000000000000000000000000000000000000'
),
with_prev AS (
    SELECT delegator, delegate,
           LAG(delegate) OVER (PARTITION BY delegator ORDER BY delegated_at) AS prev
    FROM excl_self
),
changes AS (
    SELECT delegator,
           SUM(CASE WHEN prev IS NOT NULL AND delegate != prev THEN 1 ELSE 0 END) AS n_changes
    FROM with_prev GROUP BY delegator
)
SELECT
    CASE WHEN n_changes >= 5 THEN '5+' ELSE CAST(n_changes AS VARCHAR) END AS bucket,
    COUNT(*) AS n_delegators
FROM changes GROUP BY bucket ORDER BY bucket
```

**Sample output (top 10 rows, live from warehouse):**

| bucket   |   n_delegators |
|:---------|---------------:|
| 0        |          81270 |
| 1        |           1334 |
| 2        |            107 |
| 3        |             21 |
| 4        |              3 |
| 5+       |             10 |

**Chart: Delegator retention — survival curve**

> **Key takeaway:** Once a token holder delegates in ENS DAO, they almost never change their choice — and this holds regardless of who they delegated to. At 12 months, 98.7% of top-20 delegate cohort and 98.2% of smaller delegate cohort remain unchanged, and both curves stay nearly flat through 50 months. The counterintuitive finding sharpens the story: delegators of top-20 delegates are less likely to leave than delegators of smaller ones. Concentration is not just self-reinforcing — it is actively stickier at the top. Governance authority doesn't drift; it compounds.

**Chart: Churn count distribution**

> **Key takeaway:** Re-delegation in ENS DAO is not just rare — it is essentially absent as a behaviour. Over 4.3 years (Nov 2021–Mar 2026), 98.2% of delegators made exactly zero delegate changes. The mean churn rate is 0.0048 changes per year — roughly one change per 200 years per address. On a log scale, the "0 changes" bar towers over "1 change" by 60×, and each subsequent bucket drops by another order of magnitude. Of 82,794 delegators, only 1,487 ever re-delegated at all.

---

### H6.2 — Reputation lock-in — early delegates keep power despite low activity

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H6_2.png

![Inactive, still powerful](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C1_H6_2.png)

**Description:** Voting power in ENS governance is highly sticky, and inactivity carries no structural cost. Of the top 30 delegates, 16 fall in the lock-in zone — below 50% Snapshot participation while holding tens to hundreds of thousands of delegated VP. Participation is sharply bimodal: delegates are either highly active or largely absent, with almost no middle ground. Over 24 months, 30% of top-delegate voting months were inactive gaps, with delegates like imtoken.eth showing near-continuous disengagement across 2024–2025 — yet retaining their full delegation. There is no automatic re-delegation trigger, no protocol visibility into inactivity, and no social norm prompting reassignment. Inactivity is a structurally costless choice, meaning governance power reflects the legacy of past delegation moments — not the active stewardship record of the people who hold it today.

**Source tables:** `main_silver.clean_snapshot_votes`, `main_silver.clean_snapshot_proposals`, `main_silver.clean_tally_votes`, `main_silver.clean_tally_proposals`, `main_gold.delegate_scorecard`

**Key columns:** `address`, `ens_name`, `voting_power`, `proposals_voted`

**Transformation:** Top-30 delegates' Snapshot (or Tally) participation rate over last 12 months, with a monthly activity grid for the top 10.

**Reproduction SQL:**

```sql
-- H6.2 — Snapshot activity vs voting power for top-30 delegates (last 12 months)
WITH snapshot_proposals_12m AS (
    SELECT COUNT(DISTINCT proposal_id) AS total_proposals
    FROM main_silver.clean_snapshot_proposals
    WHERE start_date >= CURRENT_DATE - INTERVAL '12 months'
),
delegate_votes_12m AS (
    SELECT sv.voter AS address, COUNT(DISTINCT sv.proposal_id) AS proposals_voted
    FROM main_silver.clean_snapshot_votes sv
    JOIN main_silver.clean_snapshot_proposals sp ON sv.proposal_id = sp.proposal_id
    WHERE sp.start_date >= CURRENT_DATE - INTERVAL '12 months'
    GROUP BY sv.voter
),
top_delegates AS (
    SELECT address, ens_name, voting_power FROM main_gold.delegate_scorecard
    ORDER BY voting_power DESC LIMIT 30
)
SELECT d.ens_name, d.voting_power,
       COALESCE(dv.proposals_voted, 0) AS proposals_voted,
       tp.total_proposals,
       ROUND(COALESCE(dv.proposals_voted, 0)::DOUBLE / NULLIF(tp.total_proposals, 0) * 100, 1) AS participation_rate
FROM top_delegates d LEFT JOIN delegate_votes_12m dv ON d.address = dv.address
CROSS JOIN snapshot_proposals_12m tp ORDER BY d.voting_power DESC
```

**Sample output (top 10 rows, live from warehouse):**

| ens_name           |   voting_power |   proposals_voted |   total_proposals |   participation_rate |
|:-------------------|---------------:|------------------:|------------------:|---------------------:|
| fireeyesdao.eth    |       253988   |                10 |                10 |                  100 |
| scratch.ricmoo.eth |       176309   |                 4 |                10 |                   40 |
| nick.eth           |       149723   |                 6 |                10 |                   60 |
|                    |       146937   |                 0 |                10 |                    0 |
| avsa.eth           |       131642   |                 9 |                10 |                   90 |
| imtoken.eth        |       121283   |                 2 |                10 |                   20 |
| coltron.eth        |       114926   |                 9 |                10 |                   90 |
| slobo.eth          |       111158   |                10 |                10 |                  100 |
| brantly.eth        |        98996.3 |                10 |                10 |                  100 |
| liubenben.eth      |        92543.6 |                 4 |                10 |                   40 |

**Chart: Activity vs. Delegated Voting Power**

> **Key takeaway:** ENS governance has a participation crisis hiding inside its power structure. Of the top 30 delegates by voting power, 16 fall in the lock-in zone — below 50% participation on Snapshot over the past 12 months — several holding 50K–180K delegated VP. The distribution is sharply bimodal: delegates cluster either near 0–40% or near 80–100% participation, with almost no middle ground, suggesting two distinct governance archetypes coexisting in the same system. The two highest-VP delegates (~250K each) are fully active, but they cannot offset the substantial share of total governance weight sitting idle with no accountability mechanism, no automatic re-delegation trigger, and no protocol-level consequence for disengagement.

**Chart: Inactivity Gaps vs Delegation Retention**

> **Key takeaway:** Inactivity is costless in ENS governance. Across the top-10 delegates over 24 months (Jan 2024–Dec 2025), 30% of delegate-month cells with active proposals were inactive gaps — months where a delegate held power but did not vote. The contrast is visible and named: imtoken.eth and one hex address show near-continuous coral (inactive) strips across the full window, while slobo.eth, brantly.eth, and avsa.eth are consistently purple throughout. The critical observation is what doesn't happen: both groups retain their delegation identically. Active stewardship and near-complete disengagement produce the same governance outcome — no loss of delegated VP — confirming that inactivity carries no structural penalty in ENS DAO.

---

## C2 — Low Broad-Based Participation

Low broad-based participation refers to the persistent failure to cultivate widespread governance  engagement despite operating for over three years. Most token holders and delegates remain passive  observers, with a small active minority conducting governance operations while lacking clear  mandate or accountability to the broader community.

### H4.1 — High cognitive/time costs — complexity discourages participation

**Verdict:** `mixed`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C2_H4_1.png

![Complexity blocks entry](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C2_H4_1.png)

**Description:** Proposal complexity suppresses participation at the margins but is not the primary barrier to broad governance engagement in ENS DAO. Across both Snapshot and Tally, LLM-scored complexity shows weak, inconsistent correlations with voter turnout: Snapshot trends negative (context dependency: ρ = -0.21) while Tally trends positive (technical depth: ρ = +0.28) and the wide scatter at every complexity level confirms that readability explains little of who participates. The deeper barriers operate at a structural level that proposal scores cannot capture: sustained governance engagement requires months of unpaid investment before any formal recognition becomes available, navigation of informal influence networks that operate alongside and often in place of formal processes, and the economic flexibility to absorb that speculative time commitment. This creates adverse selection: the barrier is not technical knowledge but economic privilege and schedule availability, selecting for participants with independent wealth or flexible employment over those with relevant expertise or community representation. Complexity is a symptom-level friction; the structural investment required to gain meaningful standing, relationships with stewards, unpaid track record, access to back-channels, is the actual gate.

**Source tables:** `main_silver.clean_snapshot_proposals`, `main_silver.clean_snapshot_votes`, `main_silver.clean_tally_proposals`, `main_silver.clean_tally_votes`

**Key columns:** `proposal_id`, `title`, `body`, `unique_voters`, `complexity_score`

**Transformation:** LLM-scored proposal complexity (cognitive load, technical depth, context dependency, time to evaluate) correlated with voter turnout on Snapshot and Tally. Spearman ρ computed in Python.

**Reproduction SQL:**

```sql
-- H4.1 — Snapshot turnout per proposal (complexity scored in Python via LLM)
SELECT p.proposal_id, LEFT(p.title, 60) AS title,
       CAST(p.start_date AS DATE) AS date,
       COUNT(DISTINCT v.voter) AS unique_voters
FROM main_silver.clean_snapshot_proposals p
LEFT JOIN main_silver.clean_snapshot_votes v ON p.proposal_id = v.proposal_id
WHERE p.status = 'closed'
GROUP BY p.proposal_id, p.title, p.start_date
ORDER BY p.start_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

| proposal_id                                                        | title                                                        | date                |   unique_voters |
|:-------------------------------------------------------------------|:-------------------------------------------------------------|:--------------------|----------------:|
| 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | [6.31] [Temp Check] Delegation Incentives Program            | 2026-02-05 00:00:00 |             105 |
| 0x8d16992852893f05b23b0e26de27c9e6b2a8de1193c991e14f81ef13cd943517 | [6.26] [Social] ENS Retro: An ENS DAO Retrospective & Stakeh | 2025-12-05 00:00:00 |             109 |
| 0xbc44d9714ee818da49c25998cabdbe745f939fef74923255c3571a00e8977e5d | [6.25] [Social] Replace the Working Groups with the ENS Admi | 2025-11-29 00:00:00 |             109 |
| 0x7b603c5ada65cfcdbdfec9a33352edf731615fe96fbcc09daa7aa97b327e15ce | [6.24.3] [Social] Funding Request - ENS Public Goods Working | 2025-11-05 00:00:00 |              88 |
| 0x9b3f5463e52aadc35155e686f8416297b24e6c7e30cb527747e61cf17b42a5f6 | [6.24.2] [Social] Funding Request: ENS Ecosystem Working Gro | 2025-11-05 00:00:00 |              88 |
| 0xc689edd77def6b9f6be6ca7fa1729e597c85ee12ae96e134d995a8b9fd78a21f | [6.24.1] [Social] Funding Request: ENS Meta-Governance Worki | 2025-11-05 00:00:00 |              90 |
| 0xf06f3ad61f9f77c8ed362dd54913cc44d030841eebebfffce4dd6605b1b0e6f3 | [EP6.16] [Social] Enhancing ENS Governance with Tally’s Ente | 2025-07-17 00:00:00 |              95 |
| 0xa9c47b281667a85f80e0cc9be5904438c9205e123352779cbb69b0ecf583307c | [EP 6.14] [Social] Proposal to form the OpenBox Investment C | 2025-06-26 00:00:00 |             104 |
| 0x98c65ac02f738ddb430fcd723ea5852a45168550b3daf20f75d5d508ecf28aa1 | [EP 6.10] [Social] Select providers for Service Provider Pro | 2025-05-08 00:00:00 |             166 |
| 0x2c07add832383dc6900077406b4241a34dc4923ba209e2d07d1a4243a18fcdef | [6.6.2] [Social] April Funding Request - ENS Public Goods Wo | 2025-04-17 00:00:00 |             173 |

**Chart: Proposal Complexity vs Voter Turnout**

> **Key takeaway:** Proposal complexity has a weak, inconsistent, and largely non-significant relationship with voter turnout in ENS governance — and the pattern contradicts itself across platforms. On Snapshot, all complexity dimensions trend negative (more complex = fewer voters), but only context dependency reaches statistical significance (ρ = -0.21). On Tally, the correlations flip entirely: more complex proposals draw marginally more on-chain voters, with technical depth the only significant result (ρ = +0.28). The Snapshot/Tally divergence is itself informative: complexity may filter out casual off-chain participants while leaving the committed on-chain voter base unmoved. Across both platforms, complexity scores explain very little of the variance in turnout — the wide scatter at every score level confirms that something other than proposal readability is driving who participates and who doesn't.

---

## C3 — Communication Fragmentation

Communication fragmentation refers to the condition where ENS DAO stakeholders operate in  isolated communication channels with minimal cross-group coordination. Working groups don't  systematically coordinate with each other, Labs communicates sporadically with the DAO,  service providers lack clear information channels, and critical documentation is scattered,  outdated, or held by specific individuals who can modify interpretations without formal process.

### H2.2 — Coordination on status quo – large actors resist decentralizing reforms

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H2_2.png

![Insiders resist reform](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H2_2.png)

**Description:** By the time decentralizing reform proposals reach a formal vote, their fate has already been determined. Reforms and routine proposals pass at nearly identical rates (77% vs 73%), but their outcome distributions differ structurally: routine proposals scatter continuously across the full range, while reform outcomes are bimodal — either near-unanimous passage (median 99.9% "for") or outright rejection near zero, with almost nothing in between. This binary pattern is the signature of pre-vote coordination: proposals are either pre-negotiated into acceptable forms and ratified overwhelmingly, or killed via coordinated opposition. The delegate heatmap confirms this — when resistance materializes, it clusters: the same large delegates voting "against" the same proposals together. Stakeholders outside the pre-vote coordination network cannot influence which outcome a reform receives.

**Source tables:** `main_silver.clean_snapshot_proposals`, `main_silver.clean_tally_proposals`, `main_gold.governance_activity`, `main_gold.delegate_scorecard`

**Key columns:** `proposal_id`, `title`, `for_pct`, `against_pct`, `vote_choice`

**Transformation:** Reform vs routine outcomes: keyword-classifies reform proposals, then plots 'for%' distribution and a top-30 delegate × reform-proposal heatmap showing who votes for/against/abstains.

**Reproduction SQL:**

```sql
-- H2.2 — Snapshot for/against percentages for outcome-distribution plot
SELECT sp.proposal_id, LEFT(sp.title, 60) AS title, sp.status,
       ga.for_pct, ga.against_pct
FROM main_silver.clean_snapshot_proposals sp
JOIN main_gold.governance_activity ga ON ga.proposal_id = sp.proposal_id
WHERE sp.status = 'closed' AND ga.source = 'snapshot'
ORDER BY sp.start_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

| proposal_id                                                        | title                                                        | status   |   for_pct |   against_pct |
|:-------------------------------------------------------------------|:-------------------------------------------------------------|:---------|----------:|--------------:|
| 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | [6.31] [Temp Check] Delegation Incentives Program            | closed   |     87.49 |          4.52 |
| 0x8d16992852893f05b23b0e26de27c9e6b2a8de1193c991e14f81ef13cd943517 | [6.26] [Social] ENS Retro: An ENS DAO Retrospective & Stakeh | closed   |     59.9  |         39.92 |
| 0xbc44d9714ee818da49c25998cabdbe745f939fef74923255c3571a00e8977e5d | [6.25] [Social] Replace the Working Groups with the ENS Admi | closed   |     28.47 |         71.33 |
| 0x7b603c5ada65cfcdbdfec9a33352edf731615fe96fbcc09daa7aa97b327e15ce | [6.24.3] [Social] Funding Request - ENS Public Goods Working | closed   |     99.52 |          0    |
| 0x9b3f5463e52aadc35155e686f8416297b24e6c7e30cb527747e61cf17b42a5f6 | [6.24.2] [Social] Funding Request: ENS Ecosystem Working Gro | closed   |    100    |          0    |
| 0xc689edd77def6b9f6be6ca7fa1729e597c85ee12ae96e134d995a8b9fd78a21f | [6.24.1] [Social] Funding Request: ENS Meta-Governance Worki | closed   |     91.08 |          8.92 |
| 0xf06f3ad61f9f77c8ed362dd54913cc44d030841eebebfffce4dd6605b1b0e6f3 | [EP6.16] [Social] Enhancing ENS Governance with Tally’s Ente | closed   |      0.05 |         97.4  |
| 0xa9c47b281667a85f80e0cc9be5904438c9205e123352779cbb69b0ecf583307c | [EP 6.14] [Social] Proposal to form the OpenBox Investment C | closed   |     92.32 |          0    |
| 0x98c65ac02f738ddb430fcd723ea5852a45168550b3daf20f75d5d508ecf28aa1 | [EP 6.10] [Social] Select providers for Service Provider Pro | closed   |      0    |          0    |
| 0x2c07add832383dc6900077406b4241a34dc4923ba209e2d07d1a4243a18fcdef | [6.6.2] [Social] April Funding Request - ENS Public Goods Wo | closed   |    100    |          0    |

**Chart: Do Large Actors Resist Decentralizing Reforms?**

> **Key takeaway:** Decentralizing reforms in ENS DAO don't fail more often than routine proposals — they fail differently. The reform pass rate (77%) is nearly identical to routine (73%), but the distribution of outcomes is strikingly different. Routine proposals scatter continuously from 0–100%, reflecting genuine variation in support. Reform proposals are bimodal: most cluster at near-100% "for," while a handful are outright rejected at near-0%, with almost nothing in between. The 99.9% median "for" on passing reforms — versus 91.5% for routine — sharpens this: when reforms pass, they pass near-unanimously; when they fail, they collapse completely. This binary outcome pattern is the signature of pre-vote coordination: proposals either get blessed or killed before the vote, with no messy middle ground.

---

### H3.2 — Information asymmetry — big delegates have richer info than small ones

**Verdict:** `in_development`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H3_2.png

![Information gatekeeping](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H3_2.png)

**Description:** Critical governance information — policies, precedents, past decisions — resides in working group stewards rather than accessible documentation. Official sites go outdated while relevant content is buried in forum threads. The most effective information strategy available is direct communication with stewards, who become the de-facto source of truth. This creates asymmetric access: those with existing relationships get timely, consistent answers while others encounter high transaction costs or inconsistent interpretations. The asymmetry is sharpest in competitive selection processes, where evaluation criteria are opaque, reviewers don't consistently follow stated rubrics, and applicants have no appeals mechanism.

**Transformation:** Hypothesis is in development — no dashboard visualization yet. Information asymmetry between large and small delegates observed qualitatively via stakeholder interviews; quantitative evidence pending.

---

### H6.3 — Lack of experimentation — few structural trials around delegates

**Verdict:** `mixed`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H6_3.png

![No structural trials](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C3_H6_3.png)

**Description:** ENS DAO proposes structural experiments at a modest rate (12.3% of proposals, 79% pass rate), but the experiments that exist address delegation mechanics, security, and anti-concentration — not the communication fragmentation between working groups. The three working groups have operated as independent silos since their creation with no systematic cross-group coordination, and no formal alternatives have been piloted: no shared coordination rituals, no authoritative documentation systems, no cross-working-group briefing structures. The one proposal explicitly restructuring how working groups operate (EP 6.25, Nov 2025) failed. Without experimentation in this specific area, there is no evidence base for whether reforms would reduce duplication or close coordination gaps — and the consistent re-funding of existing structures each budget cycle suggests the default is continuity, not iteration.

**Source tables:** `main_silver.clean_snapshot_proposals`, `main_silver.clean_tally_proposals`

**Key columns:** `proposal_id`, `title`, `body`, `status`, `proposal_date`

**Transformation:** Classifies proposals as 'structural experiment' via keyword matching on title + body. Timeline shows when experiments happen vs routine funding proposals.

**Reproduction SQL:**

```sql
-- H6.3 — Tally proposals classified in Python as experiments vs routine
SELECT proposal_id, LEFT(title, 60) AS title, status, start_date::DATE AS proposal_date
FROM main_silver.clean_tally_proposals
WHERE status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
ORDER BY start_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

|         proposal_id | title                                                        | status   | proposal_date       |
|--------------------:|:-------------------------------------------------------------|:---------|:--------------------|
| 2809688187364967429 | [EP 6.37] [Executable] Transfer 900,000 USDC from Endowment  | executed | 2026-03-11 00:00:00 |
| 2800331310839629175 | [EP 6.36][Executable] Register on.eth to the ENS DAO wallet  | executed | 2026-03-02 00:00:00 |
| 2800133654548841876 | [Executable] Replace DNSSEC oracle algorithms                | executed | 2026-02-25 00:00:00 |
| 2790714538897442592 | [EP 6.34] Register on.eth to the ENS DAO wallet and set the  | queued   | 2026-02-12 00:00:00 |
| 2790047678174594448 | Enable Root and Registrar Security Controllers               | executed | 2026-02-11 00:00:00 |
| 2787172295146210684 | [EP 6.32] [Executable] Transfer $2.5M USDC from Endowment to | executed | 2026-02-07 00:00:00 |
| 2779038904580310743 | # [EP 6.28] ENS Retro: Executable Proposal                   | executed | 2026-01-27 00:00:00 |
| 2729564643990177078 | [Executable] Collective Working Group Funding Request (Oct 2 | executed | 2026-01-22 00:00:00 |
| 2746027444409468820 | Assign Ownership of the .kred TLD to Verified Multisig Contr | executed | 2026-01-13 00:00:00 |
| 2748560757745518030 | [EP 6.27] [Executable] Endowment permissions to karpatkey -  | executed | 2025-12-16 00:00:00 |

**Chart: How Often Does ENS DAO Attempt Structural Experiments?**

> **Key takeaway:** Structural experiments represent 12.3% of ENS DAO proposals (19 of 155) — not trivially rare, and they pass at 79%. But frequency and pass rate obscure what these experiments actually address: delegation incentives, security councils, anti-concentration mechanics, and pilot programs. The one proposal explicitly restructuring working groups — the direct fix for communication fragmentation — failed (EP 6.25, Nov 2025). The timeline confirms the pattern: routine treasury and working group funding proposals recur densely every year, while experiments targeting cross-group coordination, shared documentation, or governance architecture are near-absent across four years. The DAO can pass structural experiments when they reach a vote; the bottleneck is that experiments addressing how the working groups coordinate with each other are rarely proposed at all.

---

## C4 — De-Facto Centralization of Decision Making

De facto centralization refers to the condition where despite DAO structures designed for distributed  decision-making, real decisions concentrate in small informal groups. Power flows through personal relationships,  behind-the-scenes coordination, and informal gatekeeping rather than transparent governance processes.  This creates divergence between nominal decentralization and actual centralized decision-making.

### H2.3 — Weak small-holder voice — small holders' preferences rarely affect outcomes

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_H2_3.png

![Small holders shut out](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_H2_3.png)

**Description:** Small holders in ENS DAO are structurally voiceless by every quantitative measure. They represent 96% of voters by headcount but hold a 19.8× voice deficit — 3.2% of supply exercising only 0.2% of on-chain voting weight. Removing their votes from the 40 most recent proposals flips zero outcomes. And they do not compensate through coordination: small holders vote with the eventual winner at a 0.92 mean alignment, showing conformity rather than independent bloc behavior — ruling out the one mechanism that might let them punch above their weight. The structural cause extends beyond token math: effective voice requires navigating informal power networks that operate alongside formal processes. Contributors face opaque evaluation with no clear pathway from contribution to standing, while insiders face incentives against dissent — proposing bold ideas risks threatening incumbents who control future appointments. The result is conformity at every level, concentrating effective governance voice among a small incumbent group regardless of the underlying token distribution.

**Source tables:** `main_silver.clean_tally_votes`, `main_silver.clean_tally_proposals`, `main_silver.clean_token_distribution`

**Key columns:** `voter`, `weight`, `proposal_id`, `balance`

**Transformation:** Tiers voters by weight percentile (Small <80th, Medium 80-95th, Large ≥95th). Compares supply share to voice share per tier. Runs counterfactual: removes small-holder votes from last 40 proposals, checks if outcomes change.

**Reproduction SQL:**

```sql
-- H2.3 — Supply vs Voice by tier
WITH threshold AS (
    SELECT PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY weight) AS p80,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY weight) AS p95
    FROM main_silver.clean_tally_votes
),
voter_tiers AS (
    SELECT voter, weight,
           CASE WHEN weight < t.p80 THEN 'Small'
                WHEN weight < t.p95 THEN 'Medium' ELSE 'Large' END AS tier
    FROM main_silver.clean_tally_votes v CROSS JOIN threshold t
)
SELECT tier, SUM(weight) AS weight_cast, COUNT(DISTINCT voter) AS voter_count
FROM voter_tiers GROUP BY tier ORDER BY tier
```

**Sample output (top 10 rows, live from warehouse):**

| tier   |      weight_cast |   voter_count |
|:-------|-----------------:|--------------:|
| Large  |      7.63513e+07 |            24 |
| Medium |      3.50955e+07 |           136 |
| Small  | 179244           |          3745 |

**Chart: Supply vs Voice — What Small Holders Hold vs What They Exercise**

> **Key takeaway:** Small holders (bottom 80% of voters, holding <962 ENS each) collectively own 3.2% of ENS supply but cast only 0.2% of on-chain voting weight — a 19.8× voice deficit. They represent 96% of all voters by headcount but are near-silent by governance impact. Large holders (top 5%) hold 89.8% of supply and cast 68.4% of vote weight from just 0.6% of voter addresses. Token ownership and governance voice are structurally decoupled: being numerous does not translate to being heard.

**Chart: Counterfactual Analysis — Would Removing Small-Holder Votes Change Outcomes?**

> **Key takeaway:** Small-holder votes are not just marginal — they are structurally irrelevant to outcomes. Removing all small-holder votes from every one of the 40 most recent on-chain proposals produces zero outcome flips, an average margin shift of 0.0 percentage points, and a median actual margin of 100%. Their combined weight is so far below the threshold needed to challenge large-holder blocs that even full small-holder mobilization cannot reverse a single result. Participation by small holders is expressive, not decisive.

**Chart: Small-Holder Vote Coherence — Do They Vote as a Bloc?**

> **Key takeaway:** Small holders do not vote as an independent bloc — they overwhelmingly follow the winning side. Mean alignment with the eventual winner is 0.92, with a median of 1.00 and 86% of proposals showing strong alignment (≥75% of small-holder weight on the winning side). Only 3% of proposals show contrarian small-holder voting. This is not coordinated coalition behavior, it is conformity. Small holders align with outcomes they cannot influence, ruling out the one mechanism, coordinated bloc voting, that might let them punch above their structural weight deficit.

---

### Hx.1 — Outcome robustness — the choice of voter with highest VP usually sides with outcomes

**Verdict:** `mixed`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_Hx_1.png

![One whale, many outcomes](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_Hx_1.png)

**Description:** The single highest-VP delegate sides with the winning outcome on 90.6% of ENS proposals — but removing them counterfactually flips only 1 of 64 results (1.6%). This combination is the critical finding: top whales are highly aligned with outcomes but rarely decisive, suggesting they track consensus rather than manufacture it. The causal question this raises is whether that consensus is organically formed or pre-coordinated through informal channels before votes occur. The broader C4 evidence points toward the latter: working group stewards coordinate informally before formal votes, Labs receives continuous funding outside the reapproval requirements that apply to all other participants, and most proposals pass by margins that leave no room for genuine contestation. High outcome robustness may therefore reflect not the health of distributed deliberation, but the efficiency of pre-vote coordination where alignment is near-universal because substantive disagreement was resolved, or suppressed, before the vote began.

**Source tables:** `main_silver.clean_tally_proposals`

**Key columns:** `voter`, `weight`, `proposal_id`, `vote_choice`, `winning_choice`

**Transformation:** Top-VP voter agreement rate with winning outcome (VP.1). Counterfactual removes top voter and checks if outcome flips (VP.2UP). Uses raw Tally votes JSON because on-chain vote weights need precise tracking.

**Reproduction SQL:**

```sql
-- Hx.1 — Outcome robustness (simplified: agreement rate per proposal)
SELECT p.proposal_id, LEFT(p.title, 60) AS title, p.status
FROM main_silver.clean_tally_proposals p
WHERE p.status IN ('executed', 'defeated')
ORDER BY p.start_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

|         proposal_id | title                                                        | status   |
|--------------------:|:-------------------------------------------------------------|:---------|
| 2809688187364967429 | [EP 6.37] [Executable] Transfer 900,000 USDC from Endowment  | executed |
| 2800331310839629175 | [EP 6.36][Executable] Register on.eth to the ENS DAO wallet  | executed |
| 2800133654548841876 | [Executable] Replace DNSSEC oracle algorithms                | executed |
| 2790047678174594448 | Enable Root and Registrar Security Controllers               | executed |
| 2787172295146210684 | [EP 6.32] [Executable] Transfer $2.5M USDC from Endowment to | executed |
| 2779038904580310743 | # [EP 6.28] ENS Retro: Executable Proposal                   | executed |
| 2729564643990177078 | [Executable] Collective Working Group Funding Request (Oct 2 | executed |
| 2746027444409468820 | Assign Ownership of the .kred TLD to Verified Multisig Contr | executed |
| 2748560757745518030 | [EP 6.27] [Executable] Endowment permissions to karpatkey -  | executed |
| 2708179808130434396 | [EP 6.23] [Executable] Endowment permissions to karpatkey -  | executed |

**Chart: Outcome Robustness — Does the Top Whale Drive the Vote?**

> **Key takeaway:** The single highest-VP delegate sides with the winning outcome on 90.6% of ENS on-chain proposals — just below the 94.8% benchmark from Goldberg & Schär (2023). But the counterfactual tells the more important story: removing the top voter flips only 1 of 64 proposals (1.6% flip rate). These two numbers together reframe the finding: top whales are highly aligned with outcomes, but rarely decisive — the winning coalition holds even without them. fireeyesdao.eth is the dominant top whale (41 proposals, 95% aligned), with brantly.eth a distant second (15 proposals, 80% aligned). High agreement with near-zero decisive influence is more consistent with a delegate tracking pre-formed consensus than one driving it.

---

### Hx.2 — Factional politics — informal aligned groups increase centralization of decision making

**Verdict:** `supported`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_Hx_2.png

![Informal blocs coordinate](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C4_Hx_2.png)

**Description:** ENS DAO's top delegates organize into 9 persistent voting clusters — a quantitative signature of informal coordination outside formal channels. The most prominent cluster of 10 delegates shows 0.92 average internal alignment, and within-cluster cohesion holds across proposal types, including on genuinely contested votes like EP 5.15. This is not coincidental agreement; it is durable factional structure. The governance consequence extends beyond bloc voting: when decision-making authority concentrates in informal coalitions, operational continuity becomes dependent on the health of interpersonal relationships within those groups. Interview data documents multi-month periods of significantly reduced working group output during internal tensions, with no formal conflict resolution mechanism available to restore function. Experienced stewards describe their final periods as contentious — external actors providing prescriptive direction without operational context, leading to exits that took institutional knowledge with them. Factionalism produces a governance system that functions when relationships are healthy and degrades in ways the formal structure cannot diagnose or repair.

**Source tables:** `main_silver.clean_snapshot_votes`, `main_silver.clean_snapshot_proposals`, `main_silver.clean_tally_votes`, `main_silver.clean_tally_proposals`, `main_gold.delegate_scorecard`

**Key columns:** `voter`, `proposal_id`, `vote_choice`

**Transformation:** Combines top-50 delegates' Snapshot + Tally votes into a voter × proposal matrix. Computes cosine similarity, applies Ward hierarchical clustering to detect factions.

**Reproduction SQL:**

```sql
-- Hx.2 — Top-50 delegate vote history (combined Snapshot + Tally)
WITH top50 AS (
    SELECT address FROM main_gold.delegate_scorecard
    ORDER BY voting_power DESC LIMIT 50
)
SELECT sv.voter, sv.proposal_id, sv.vote_choice,
       sp.start_date::DATE AS proposal_date,
       LEFT(COALESCE(sp.title, sv.proposal_id), 60) AS proposal_title
FROM main_silver.clean_snapshot_votes sv
JOIN top50 ON sv.voter = top50.address
JOIN main_silver.clean_snapshot_proposals sp ON sv.proposal_id = sp.proposal_id
ORDER BY proposal_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

| voter                                      | proposal_id                                                        | vote_choice   | proposal_date       | proposal_title                                    |
|:-------------------------------------------|:-------------------------------------------------------------------|:--------------|:--------------------|:--------------------------------------------------|
| 0x1d5460f896521ad685ea4c3f2c679ec0b6806359 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0x2d7d6ec6198adfd5850d00bd601958f6e316b05e | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0xac50ce326de14ddf9b7e9611cd2f33a1af8ac039 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | against       | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0xd5d171a9aa125af13216c3213b5a9fc793fccf2c | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0x7f7720bdb2cb5c13dd30a0c8ab8d0dd553b31caa | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | against       | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0x8787fc2de4de95c53e5e3a4e5459247d9773ea52 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0xb8c2c29ee19d8307cb7255e1cd9cbde883a267d5 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0x983110309620d911731ac0932219af06091b6744 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0xa8b4756959e1192042fc2a8a103dfe2bddf128e8 | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |
| 0xb352bb4e2a4f27683435f153a259f1b207218b1b | 0xf0ad5ad5a1ee353a65424a83e74f2b8846b16885a4be99af26b5162bfa78c644 | for           | 2026-02-05 00:00:00 | [6.31] [Temp Check] Delegation Incentives Program |

**Chart: Delegate Vote Alignment — Faction Detection**

> **Key takeaway:** ENS's top delegates do not vote as a undifferentiated bloc — they organize into 9 distinct voting clusters among 38 delegates with sufficient shared votes. The most prominent cluster (10 delegates including nick.eth, slobo.eth, liubenben.eth, limes.eth) shows average internal alignment of 0.92. The similarity matrix reveals large dark-blue blocks along the diagonal — tight within-cluster agreement — with meaningful cross-cluster divergence visible on contested proposals, most sharply on EP 5.15 (ENS Governor Improvement Proposal). Factions are not random: they persist across proposal types, suggesting durable coordination relationships rather than ad hoc agreement. Twelve delegates were excluded for insufficient shared contested votes — a further signal that governance participation is concentrated in a smaller active core than the delegate registry suggests.

---

## C5 — Treasury and Institutional Liability Risk

ENS DAO manages substantial multi-year treasury assets while operating with inadequate accountability mechanisms and unclear liability frameworks. The combination of weak financial controls, limited performance evaluation, and demonstrated legal exposure creates sustainability vulnerabilities. Use these explorers to profile treasury flows, spending by category, and contributor compensation patterns across all working groups.

### H5.1 — Treasury Cashflow Overview

**Verdict:** `explorer`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_1.png

![Cashflow](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_1.png)

**Description:** Monthly inflows and outflows across the full financial history (Mar 2022–Nov 2025). Inflows represent external revenue from the Registrar, CoW Swap yield, and the Endowment. Outflows represent end-spend by working groups on grants, salaries, contractors, and events. Internal transfers show budget allocations from the DAO Wallet to working groups. Filter by year and flow type to examine treasury trajectory and burn rate.

**Source tables:** `main_gold.treasury_summary`, `main_silver.clean_ens_ledger`

**Key columns:** `period`, `category`, `inflows_usd`, `outflows_usd`, `net_usd`, `internal_transfer_usd`, `source_entity`, `destination`, `value_usd`

**Transformation:** Monthly treasury cashflow (inflows/outflows/internal transfers) plus Sankey of source→destination ledger flows with $10K threshold for 'Other' bucket.

**Reproduction SQL:**

```sql
-- H5.1 — Monthly treasury cashflow overview
SELECT period, category, inflows_usd, outflows_usd, net_usd, internal_transfer_usd
FROM main_gold.treasury_summary ORDER BY period DESC LIMIT 12
```

**Sample output (top 10 rows, live from warehouse):**

| period              | category      |   inflows_usd |   outflows_usd |   net_usd |   internal_transfer_usd |
|:--------------------|:--------------|--------------:|---------------:|----------:|------------------------:|
| 2025-11-01 00:00:00 | 5pence.eth    |             0 |           4000 |     -4000 |             0           |
| 2025-11-01 00:00:00 | coltron.eth   |             0 |           8000 |     -8000 |             0           |
| 2025-11-01 00:00:00 | daemon.eth    |             0 |           4000 |     -4000 |             0           |
| 2025-11-01 00:00:00 | danch.eth     |             0 |           7500 |     -7500 |             0           |
| 2025-11-01 00:00:00 | dao wallet    |        225699 |              0 |    225699 |             0           |
| 2025-11-01 00:00:00 | daostrat.eth  |             0 |           4000 |     -4000 |             0           |
| 2025-11-01 00:00:00 | ens labs      |             0 |              0 |         0 |             1.35446e+06 |
| 2025-11-01 00:00:00 | estmcmxci.eth |             0 |            560 |      -560 |             0           |
| 2025-11-01 00:00:00 | hackathons    |             0 |           5040 |     -5040 |             0           |
| 2025-11-01 00:00:00 | icann         |             0 |           4485 |     -4485 |             0           |

**Chart: Monthly Treasury Cashflow**

> **Key takeaway:** Filter by year to compare inflows, outflows, and internal transfers month by month. Stat cards update to show totals and net position for the selected period.

**Chart: Cashflow Breakdown**

> **Key takeaway:** Follow the money: external revenue flows into the DAO Wallet, which allocates budgets to working groups, which spend on recipients and grants. Destinations below $25K are grouped into "Other". Links are color-coded by ledger category.

---

### H5.2 — Ledger Transaction Explorer

**Verdict:** `explorer`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_2.png

![Ledger](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_2.png)

**Description:** Row-level view of ENS Foundation treasury transactions sourced from the Foundation's own labeled bookkeeping ledger. Each row is a payment with a source entity, destination, category, asset, and USD value. Filter by flow type, asset, year, and category to trace individual payments. The summary bar shows which entities account for the most treasury activity under the current filters.

**Source tables:** `main_silver.clean_ens_ledger`

**Key columns:** `tx_hash`, `tx_date`, `source_entity`, `destination`, `category`, `amount`, `asset`, `value_usd`, `flow_type`

**Transformation:** Row-level ledger explorer — 2,316 transactions with multi-filter controls. No aggregation, pure filtering.

**Reproduction SQL:**

```sql
-- H5.2 — Ledger transactions (row-level)
SELECT tx_date::DATE AS date, source_entity, destination, category,
       asset, amount, value_usd, flow_type
FROM main_silver.clean_ens_ledger
ORDER BY tx_date DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

| date                | source_entity   | destination   | category   | asset   |      amount |   value_usd | flow_type   |
|:--------------------|:----------------|:--------------|:-----------|:--------|------------:|------------:|:------------|
| 2025-11-28 00:00:00 | providers       | efp           | stream     | USDC    | 38356.2     |     38356.2 | outflow     |
| 2025-11-28 00:00:00 | providers       | zkemail       | stream     | USDC    | 30684.9     |     30684.9 | outflow     |
| 2025-11-28 00:00:00 | providers       | justaname     | stream     | USDC    | 23013.7     |     23013.7 | outflow     |
| 2025-11-28 00:00:00 | providers       | namehash      | stream     | USDC    | 84383.6     |     84383.6 | outflow     |
| 2025-11-28 00:00:00 | providers       | ethlimo       | stream     | USDC    | 53698.6     |     53698.6 | outflow     |
| 2025-11-28 00:00:00 | providers       | namespace     | stream     | USDC    | 30684.9     |     30684.9 | outflow     |
| 2025-11-28 00:00:00 | providers       | unruggable    | stream     | USDC    | 30684.9     |     30684.9 | outflow     |
| 2025-11-28 00:00:00 | providers       | blockful.eth  | stream     | USDC    | 53698.6     |     53698.6 | outflow     |
| 2025-11-25 00:00:00 | registrar       | dao wallet    | dao wallet | ETH     |     7.33149 |     21523.8 | inflow      |
| 2025-11-23 00:00:00 | ecosystem       | 0xa33240      | irl        | USDC    |  4000       |      4000   | outflow     |

**Chart: Transaction Ledger**

> **Key takeaway:** Use the four filter controls to narrow by flow type, asset, year, and category. The bar chart and stat cards reflect the filtered selection; the table below shows individual transactions.

---

### H5.3 — Compensation and Roles Explorer

**Verdict:** `explorer`

**Screenshot:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_3.png

![Compensation](https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/C5_H5_3.png)

**Description:** Contributor compensation records (salaries, streams, fellowships) across all working groups from 2022 to 2025. Records include recipient wallet, working group, role, payment category, token, and USD value. Filter by working group, role, category, and year to compare compensation patterns and identify concentration across budget lines.

**Source tables:** `main_silver.clean_compensation`

**Key columns:** `recipient_address`, `amount`, `token`, `value_usd`, `working_group`, `role`, `category`, `date`

**Transformation:** Contributor compensation records (salaries, streams, fellowships, gas reimbursements) grouped by working group × role.

**Reproduction SQL:**

```sql
-- H5.3 — Compensation by working group × role
SELECT working_group, role, category,
       COUNT(*) AS n_payments,
       SUM(value_usd) AS total_usd,
       COUNT(DISTINCT recipient_address) AS unique_recipients
FROM main_silver.clean_compensation
GROUP BY working_group, role, category
ORDER BY total_usd DESC LIMIT 20
```

**Sample output (top 10 rows, live from warehouse):**

| working_group   | role        | category          |   n_payments |        total_usd |   unique_recipients |
|:----------------|:------------|:------------------|-------------:|-----------------:|--------------------:|
| providers       | contributor | stream            |          196 |      7.70301e+06 |                  11 |
| meta-governance | contributor | salaries          |          356 |      1.58319e+06 |                  19 |
| ens-ecosystem   | fellow      | fellowship        |            8 | 149979           |                   3 |
| ens-ecosystem   | contributor | salaries          |           27 |  58155.4         |                   8 |
| meta-governance | delegate    | delegate gas ref. |            3 |  16580.1         |                   1 |
| public-goods    | contributor | salaries          |            1 |   5000           |                   1 |
| meta-governance | steward     | steward gas ref.  |            7 |   3229.1         |                   7 |

**Chart: Compensation by Working Group**

> **Key takeaway:** Select payment categories and year to compare total compensation across working groups, broken down by role. Stat cards show total USD, unique recipients, and payment count for the selection.

**Chart: Compensation Records**

> **Key takeaway:** Browse individual compensation records with full filter controls. The running total above the table reflects the current selection.

---
