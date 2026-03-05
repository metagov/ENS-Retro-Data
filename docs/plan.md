# ENS DAO Evaluation: Data Infrastructure Plan

## Design Principles

| Principle | How We Honor It |
|---|---|
| Reproducibility | Everything lives in Git. Raw → Processed is scripted, never manual. |
| Transparency | All transformations are Python scripts in the repo. No black-box steps. |
| Mixed-Methods Fit | Quantitative (Parquet/SQL) and qualitative (coded JSON) share a common tagging taxonomy. |
| Archival Durability | File-based formats (Parquet, JSON, CSV). No server dependency. |
| AI-Augmented Query | DuckDB queries Parquet directly. Clean Gold layer = any AI tool can sit on top later. |
| Interactivity | Deferred. Once data is solid, Quarto/Observable/Hex can plug in trivially. |

---

## 1. Repo Structure

```
ens-retro-data/
│
├── README.md
├── taxonomy.yaml                  # Single source of truth for all tags
│
├── bronze/                        # Raw data, untouched
│   ├── on-chain/                  # Etherscan exports, Dune CSV pulls
│   ├── governance/                # Snapshot, Tally, Agora API dumps
│   ├── forum/                     # Discourse JSON exports
│   ├── financial/                 # enswallets, SafeNotes, Karpatkey
│   ├── docs/                      # ENS Docs, Basics, website copy
│   ├── interviews/                # Transcripts (markdown or text)
│   ├── grants/                    # Grant proposals, reports
│   └── github/                    # ensdomains repo activity
│
├── silver/                        # Cleaned, tagged, entity-resolved
│   ├── quantitative/              # Parquet files, one per domain
│   ├── qualitative/               # Coded JSON, one per source type
│   └── crosswalk/                 # Entity resolution tables
│
├── gold/                          # Analysis-ready views
│   ├── views/                     # Materialized Parquet tables per hypothesis cluster
│   └── indexes/                   # Lookup tables for fast query
│
├── infra/ (Dagster and DBT)
│   ├── ingest/                    # Bronze collection
│   ├── transform/                 # Bronze → Silver
│   ├── materialize/               # Silver → Gold
│   └── validate/                  # Data quality checks
│
├── analysis/                     # Analysis notebooks or Dashboards (Quarto/Marimo/Jupyter)
│
└── docs/
    ├── taxonomy.md                # Human-readable taxonomy docs
    ├── data-dictionary.md         # Field definitions per table
    └── collection-log.md          # What was collected, when, by whom
```

---

## 2. The Taxonomy — One System to Tag Everything

Every piece of data, for example a vote record, a forum post, an interview quote, gets tagged using the same controlled vocabulary so it can be joined, filtered, and queried across sources.

### taxonomy.yaml

```yaml
# -- Entities --
entities:
  stakeholder_types:
    - delegate
    - token_holder
    - steward
    - working_group_member
    - contributor
    - core_team
    - grant_recipient

  working_groups:
    - meta_governance
    - ens_labs
    - public_goods
    - ecosystem
    - providers        # add as discovered

  governance_bodies:
    - dao_wide_vote
    - working_group
    - steward_council
    - veto_multisig    

# -- Hypothesis Tags --
hypothesis_tags:
  - H1.1_visibility_bias
  - H1.2_free_riding
  - H1.3_legacy_distribution
  - H2.1_token_weighted_paradox
  - H2.2_status_quo_coordination
  - H2.3_weak_small_holder
  - H3.1_ux_drives_hubs
  - H3.2_info_asymmetry
  - H3.3_low_redelegation
  - H4.1_cognitive_cost
  - H4.2_weak_feedback
  - H4.3_spectatorship
  - H5.1_narrative_mismatch
  - H5.2_emergency_creep
  - H5.3_complexity_barrier
  - H6.1_onramp_barriers
  - H6.2_reputation_lockin
  - H6.3_lack_experimentation
  - H7.1_treasury_fragmentation
  - H7.2_resourcing
  - H7.3_grant_tracking
  - H8.1_compensation_framework
  - H8.2_insider_advantage
  - H8.3_formalization

# -- Qualitative Codes --
qualitative_codes:
# More to be added 

  participation_barrier:
    - complexity
    - time
    - low_perceived_impact
    - information_overload
    - unspecified
    - information_underload

  sentiment:
    - positive
    - negative
    - neutral
    - concerned
    - resigned

  power_dynamic:
    - supports_decentralization
    - supports_status_quo
    - acknowledges_concentration
    - dismisses_concentration

# -- Data Domains --
data_domains:
  - delegation
  - voting
  - treasury
  - proposals
  - compensation
  - grants
  - governance_structure
  - community_sentiment
```

---

## 3. Data Formats and Medallion Architecture

### Bronze (Raw) 

| Source Type | Format Stored | Example |
|---|---|---|
| API responses (Snapshot, Agora, Tally) | JSON | `bronze/governance/snapshot_proposals_2024.json` |
| Dune query exports | CSV | `bronze/on-chain/dune_delegation_history.csv` |
| Etherscan exports | CSV | `bronze/on-chain/ens_token_transfers.csv` |
| Forum posts (Discourse) | JSON (API export) | `bronze/forum/delegate_threads_raw.json` |
| Interview transcripts | Markdown | `bronze/interviews/interview_holder_01.md` |
| ENS Docs / website copy | Markdown | `bronze/docs/ens_constitution.md` |
| Grant proposals / reports | PDF → Markdown | `bronze/grants/grant_report_xyz.md` |
| Wallet / treasury data | CSV or JSON | `bronze/financial/enswallets_balances.csv` |

**Rule**: Bronze is append-only. Never edit. Every file gets a `_metadata.json` sidecar:

```json
{
  "source": "Snapshot GraphQL API",
  "collected_by": "metagov",
  "collected_at": "2026-02-18",
  "query_or_method": "scripts/ingest/snapshot_proposals.py",
  "covers_period": "2022-01-01 to 2026-01-31",
  "notes": "All ENS space proposals, off-chain"
}
```

### Silver (Processed) — Where Tagging Happens

**Quantitative → Parquet files** (columnar, compressed, queryable by DuckDB/Pandas/Polars)

| Silver Table | Key Fields | Tagged With | Source(s) |
|---|---|---|---|
| `delegations.parquet` | delegator_addr, delegate_addr, timestamp, token_amount, is_active | H1.x, H3.x, H6.x | Tally, Dune, Etherscan |
| `votes.parquet` | voter_addr, proposal_id, vote_choice, voting_power, timestamp | H1.2, H2.x, H4.1 | Snapshot, Tally |
| `proposals.parquet` | proposal_id, title, body_hash, category, complexity_score, outcome, turnout | H2.x, H4.1, H4.2, H6.3 | Snapshot, Tally, Agora |
| `token_distribution.parquet` | address, balance, snapshot_date, holder_tier (whale/mid/small) | H1.3, H2.1, H2.3 | Etherscan, Dune |
| `treasury_flows.parquet` | tx_hash, from_wg, to_addr, amount_usd, category, date | H7.x | ENS Ledger, enswallets, SafeNotes |
| `grants.parquet` | grant_id, recipient, amount, purpose, has_outcome_report, outcome_summary | H7.3 | Forum, grants data |
| `delegate_profiles.parquet` | delegate_addr, join_date, profile_length, positions_count, vote_rate, delegated_power | H3.2, H6.1, H6.2 | Agora, Boardroom, Tally |
| `compensation.parquet` | contributor_id, role, wg, amount, period, source_doc | H8.x | Forum WG reports |

**Qualitative → Coded JSON** (one record per coded segment)

```json
{
  "segment_id": "int_holder_01_seg_003",
  "source_type": "interview",
  "source_file": "bronze/interviews/interview_holder_01.md",
  "speaker_role": "token_holder",
  "text": "I just picked whoever was at the top of the Agora list, honestly.",
  "codes": {
    "delegation_reason": ["visibility_default"],
    "participation_barrier": [],
    "sentiment": ["neutral"],
    "power_dynamic": []
  },
  "hypothesis_tags": ["H1.1_visibility_bias", "H3.1_ux_drives_hubs"],
  "entities_mentioned": {
    "platforms": ["agora"],
    "working_groups": [],
    "stakeholders": []
  },
  "coded_by": "metagov",
  "coded_at": "2026-03-01"
}
```

All coded segments are collected into files per source type:

| Silver File | Contents |
|---|---|
| `qualitative/coded_interviews.json` | Array of coded interview segments |
| `qualitative/coded_forum_posts.json` | Array of coded forum post segments |
| `qualitative/coded_docs.json` | Array of coded document/website excerpts |
| `qualitative/coded_newsletters.json` | Array of coded newsletter excerpts |

**Crosswalk tables** (entity resolution):

| File | Purpose |
|---|---|
| `crosswalk/address_to_identity.parquet` | Maps ETH addresses → known names/roles |
| `crosswalk/proposal_id_map.parquet` | Maps Snapshot ID ↔ Tally ID ↔ Forum thread |
| `crosswalk/wg_budget_periods.parquet` | Maps working group → budget terms → amounts |

### Gold (Analysis-Ready) — Materialized Per Hypothesis Cluster

| Gold View | Serves Hypotheses | What It Contains |
|---|---|---|
| `gold/delegation_concentration.parquet` | H1.1, H1.3, H3.3, H6.2 | Time-series of top-N delegate share, HHI, churn rates |
| `gold/voter_participation.parquet` | H1.2, H2.3, H4.1 | Per-proposal turnout by holder tier, complexity score |
| `gold/power_structure.parquet` | H2.1, H2.2, H5.1 | Voting power distribution, Gini, minimum winning coalition size |
| `gold/treasury_reconstruction.parquet` | H7.1, H7.2, H7.3 | Full-year spending by WG × category, gap flags |
| `gold/delegate_lifecycle.parquet` | H6.1, H6.2, H3.2 | Delegate join cohort × power growth × activity × profile richness |
| `gold/qualitative_code_matrix.parquet` | H4.3, H5.3, H8.2 | Code frequency × role × hypothesis (queryable counts from coded JSON) |

---

## 4. Database Choice

- [ ] Postgresql or Duckdb ?


DuckDB seems like a good choice. It queries Parquet files directly from disk — no database server, no setup, fully reproducible, and works in Python or CLI
Or query qualitative as Parquet too.

Example: The `gold/qualitative_code_matrix.parquet` flattens coded JSON into a tabular format so DuckDB can query it:


---

## 5. Hypothesis to Data Pipeline Map


| Hypothesis Cluster | Bronze Sources to Ingest | Silver Tables to Build | Gold Views |
|---|---|---|---|
| **H1 Delegation concentration** | Tally delegations, Dune delegation history, Agora delegate list, Etherscan holders, Forum delegate threads, Interviews | `delegations`, `token_distribution`, `delegate_profiles`, `coded_interviews`, `coded_forum_posts` | `delegation_concentration`, `delegate_lifecycle` |
| **H2 Token-weighted power** | Dune voting power, ENS Ledger scripts, Snapshot + Tally votes, Forum debates, Token Terminal | `votes`, `token_distribution`, `proposals`, `coded_forum_posts` | `power_structure`, `voter_participation` |
| **H3 UX and information** | Agora/Boardroom UI data, Dune/Tally delegation network, Forum delegate statements, Interviews | `delegate_profiles`, `delegations`, `coded_interviews` | `delegate_lifecycle`, `delegation_concentration` |
| **H4 Participation barriers** | Tally/Agora proposal texts, Forum threads, Interviews, ENS Newsletter, Token Terminal | `proposals` (with complexity_score), `votes`, `coded_interviews`, `coded_forum_posts` | `voter_participation`, `qualitative_code_matrix` |
| **H5 Narrative vs reality** | ENS Docs/Basics/website, Dune/Ledger concentration data, Forum (veto debates), Etherscan/Tally (veto multisig) | `token_distribution`, `coded_docs`, `proposals` | `power_structure`, `qualitative_code_matrix` |
| **H6 Delegate dynamics** | Agora/Boardroom (join dates), Dune (growth), Forum (delegate threads), Interviews, ENS Docs | `delegate_profiles`, `delegations`, `coded_interviews`, `proposals` | `delegate_lifecycle` |
| **H7 Treasury** | enswallets, SafeNotes, Forum WG reports, Karpatkey, ENS Ledger, Grants + threads | `treasury_flows`, `grants`, `compensation` | `treasury_reconstruction` |
| **H8 Compensation** | Forum WG budgets, Grants, Interviews, ENS Docs | `compensation`, `coded_interviews`, `coded_forum_posts` | `qualitative_code_matrix`, `treasury_reconstruction` |

# ENS DAO Evaluation: Data Infrastructure Plan

## Design Principles

| Principle | How We Honor It |
|---|---|
| Reproducibility | Everything lives in Git. Raw → Processed is scripted, never manual. |
| Transparency | All transformations are Python scripts in the repo. No black-box steps. |
| Mixed-Methods Fit | Quantitative (Parquet/SQL) and qualitative (coded JSON) share a common tagging taxonomy. |
| Archival Durability | File-based formats (Parquet, JSON, CSV). No server dependency. |
| AI-Augmented Query | DuckDB queries Parquet directly. Clean Gold layer = any AI tool can sit on top later. |
| Interactivity | Deferred. Once data is solid, Quarto/Observable/Hex can plug in trivially. |

---

## 1. Repo Structure

```
ens-retro-data/
│
├── README.md
├── taxonomy.yaml                  # Single source of truth for all tags
│
├── bronze/                        # Raw data, untouched
│   ├── on-chain/                  # Etherscan exports, Dune CSV pulls
│   ├── governance/                # Snapshot, Tally, Agora API dumps
│   ├── forum/                     # Discourse JSON exports
│   ├── financial/                 # enswallets, SafeNotes, Karpatkey
│   ├── docs/                      # ENS Docs, Basics, website copy
│   ├── grants/                    # Grant proposals, reports
│   └── github/                    # ensdomains repo activity
│
├── silver/                        # Cleaned, tagged, entity-resolved
│   ├── quantitative/              # Parquet files, one per domain
│   ├── qualitative/               # Coded JSON, one per source type
│   └── crosswalk/                 # Entity resolution tables
│
├── gold/                          # Analysis-ready views
│   ├── views/                     # Materialized Parquet tables per hypothesis cluster
│   └── indexes/                   # Lookup tables for fast query
│
├── infra/ (Dagster and DBT)
│   ├── ingest/                    # Bronze collection
│   ├── transform/                 # Bronze → Silver
│   ├── materialize/               # Silver → Gold
│   └── validate/                  # Data quality checks
│
├── analysis/                     # Analysis notebooks or Dashboards (Quarto/Marimo/Jupyter)
│
└── docs/
    ├── Phase 1                    # Phase 1 Design Docs and Results
    ├── taxonomy.md                # Human-readable taxonomy docs
    ├── data-dictionary.md         # Field definitions per table
    └── collection-log.md          # What was collected, when, by whom
```

---

## 2. The Taxonomy — One System to Tag Everything

Every piece of data, for example a vote record, a forum post, an interview quote, gets tagged using the same controlled vocabulary so it can be joined, filtered, and queried across sources.

### taxonomy.yaml

```yaml
# -- Entities --
entities:
  stakeholder_types:
    - delegate
    - token_holder
    - steward
    - working_group_member
    - contributor
    - core_team
    - grant_recipient

  working_groups:
    - meta_governance
    - ens_labs
    - public_goods
    - ecosystem
    - providers        # add as discovered

  governance_bodies:
    - dao_wide_vote
    - working_group
    - steward_council
    - veto_multisig    

# -- Hypothesis Tags --
hypothesis_tags:
  - H1.1_visibility_bias
  - H1.2_free_riding
  - H1.3_legacy_distribution
  - H2.1_token_weighted_paradox
  - H2.2_status_quo_coordination
  - H2.3_weak_small_holder
  - H3.1_ux_drives_hubs
  - H3.2_info_asymmetry
  - H3.3_low_redelegation
  - H4.1_cognitive_cost
  - H4.2_weak_feedback
  - H4.3_spectatorship
  - H5.1_narrative_mismatch
  - H5.2_emergency_creep
  - H5.3_complexity_barrier
  - H6.1_onramp_barriers
  - H6.2_reputation_lockin
  - H6.3_lack_experimentation
  - H7.1_treasury_fragmentation
  - H7.2_resourcing
  - H7.3_grant_tracking
  - H8.1_compensation_framework
  - H8.2_insider_advantage
  - H8.3_formalization

# -- Qualitative Codes --
qualitative_codes:
# More to be added 

  participation_barrier:
    - complexity
    - time
    - low_perceived_impact
    - information_overload
    - unspecified
    - information_underload

  sentiment:
    - positive
    - negative
    - neutral
    - concerned
    - resigned

  power_dynamic:
    - supports_decentralization
    - supports_status_quo
    - acknowledges_concentration
    - dismisses_concentration

# -- Data Domains --
data_domains:
  - delegation
  - voting
  - treasury
  - proposals
  - compensation
  - grants
  - governance_structure
  - community_sentiment
```

---

## 3. Data Formats and Medallion Architecture

### Bronze (Raw) 

| Source Type | Format Stored | Example |
|---|---|---|
| API responses (Snapshot, Agora, Tally) | JSON | `bronze/governance/snapshot_proposals_2024.json` |
| Dune query exports | CSV | `bronze/on-chain/dune_delegation_history.csv` |
| Etherscan exports | CSV | `bronze/on-chain/ens_token_transfers.csv` |
| Forum posts (Discourse) | JSON (API export) | `bronze/forum/delegate_threads_raw.json` |
| Interview transcripts | Markdown | `bronze/interviews/interview_holder_01.md` |
| ENS Docs / website copy | Markdown | `bronze/docs/ens_constitution.md` |
| Grant proposals / reports | PDF → Markdown | `bronze/grants/grant_report_xyz.md` |
| Wallet / treasury data | CSV or JSON | `bronze/financial/enswallets_balances.csv` |

**Rule**: Bronze is append-only. Never edit. Every file gets a `_metadata.json` sidecar:

```json
{
  "source": "Snapshot GraphQL API",
  "collected_by": "metagov",
  "collected_at": "2026-02-18",
  "query_or_method": "scripts/ingest/snapshot_proposals.py",
  "covers_period": "2022-01-01 to 2026-01-31",
  "notes": "All ENS space proposals, off-chain"
}
```

### Silver (Processed) — Where Tagging Happens

**Quantitative → Parquet files** (columnar, compressed, queryable by DuckDB/Pandas/Polars)

| Silver Table | Key Fields | Tagged With | Source(s) |
|---|---|---|---|
| `delegations.parquet` | delegator_addr, delegate_addr, timestamp, token_amount, is_active | H1.x, H3.x, H6.x | Tally, Dune, Etherscan |
| `votes.parquet` | voter_addr, proposal_id, vote_choice, voting_power, timestamp | H1.2, H2.x, H4.1 | Snapshot, Tally |
| `proposals.parquet` | proposal_id, title, body_hash, category, complexity_score, outcome, turnout | H2.x, H4.1, H4.2, H6.3 | Snapshot, Tally, Agora |
| `token_distribution.parquet` | address, balance, snapshot_date, holder_tier (whale/mid/small) | H1.3, H2.1, H2.3 | Etherscan, Dune |
| `treasury_flows.parquet` | tx_hash, from_wg, to_addr, amount_usd, category, date | H7.x | ENS Ledger, enswallets, SafeNotes |
| `grants.parquet` | grant_id, recipient, amount, purpose, has_outcome_report, outcome_summary | H7.3 | Forum, grants data |
| `delegate_profiles.parquet` | delegate_addr, join_date, profile_length, positions_count, vote_rate, delegated_power | H3.2, H6.1, H6.2 | Agora, Boardroom, Tally |
| `compensation.parquet` | contributor_id, role, wg, amount, period, source_doc | H8.x | Forum WG reports |

**Qualitative → Coded JSON** (one record per coded segment)

```json
{
  "segment_id": "int_holder_01_seg_003",
  "source_type": "interview",
  "source_file": "bronze/interviews/interview_holder_01.md",
  "speaker_role": "token_holder",
  "text": "I just picked whoever was at the top of the Agora list, honestly.",
  "codes": {
    "delegation_reason": ["visibility_default"],
    "participation_barrier": [],
    "sentiment": ["neutral"],
    "power_dynamic": []
  },
  "hypothesis_tags": ["H1.1_visibility_bias", "H3.1_ux_drives_hubs"],
  "entities_mentioned": {
    "platforms": ["agora"],
    "working_groups": [],
    "stakeholders": []
  },
  "coded_by": "metagov",
  "coded_at": "2026-03-01"
}
```

All coded segments are collected into files per source type:

| Silver File | Contents |
|---|---|
| `qualitative/coded_interviews.json` | Array of coded interview segments |
| `qualitative/coded_forum_posts.json` | Array of coded forum post segments |
| `qualitative/coded_docs.json` | Array of coded document/website excerpts |
| `qualitative/coded_newsletters.json` | Array of coded newsletter excerpts |

**Crosswalk tables** (entity resolution):

| File | Purpose |
|---|---|
| `crosswalk/address_to_identity.parquet` | Maps ETH addresses → known names/roles |
| `crosswalk/proposal_id_map.parquet` | Maps Snapshot ID ↔ Tally ID ↔ Forum thread |
| `crosswalk/wg_budget_periods.parquet` | Maps working group → budget terms → amounts |

### Gold (Analysis-Ready) — Materialized Per Hypothesis Cluster

| Gold View | Serves Hypotheses | What It Contains |
|---|---|---|
| `gold/delegation_concentration.parquet` | H1.1, H1.3, H3.3, H6.2 | Time-series of top-N delegate share, HHI, churn rates |
| `gold/voter_participation.parquet` | H1.2, H2.3, H4.1 | Per-proposal turnout by holder tier, complexity score |
| `gold/power_structure.parquet` | H2.1, H2.2, H5.1 | Voting power distribution, Gini, minimum winning coalition size |
| `gold/treasury_reconstruction.parquet` | H7.1, H7.2, H7.3 | Full-year spending by WG × category, gap flags |
| `gold/delegate_lifecycle.parquet` | H6.1, H6.2, H3.2 | Delegate join cohort × power growth × activity × profile richness |
| `gold/qualitative_code_matrix.parquet` | H4.3, H5.3, H8.2 | Code frequency × role × hypothesis (queryable counts from coded JSON) |

---

## 4. Database Choice

- [ ] Postgresql or Duckdb ?


DuckDB seems like a good choice. It queries Parquet files directly from disk — no database server, no setup, fully reproducible, and works in Python or CLI
Or query qualitative as Parquet too.

Example: The `gold/qualitative_code_matrix.parquet` flattens coded JSON into a tabular format so DuckDB can query it:


---

## 5. Hypothesis to Data Pipeline Map


| Hypothesis Cluster | Bronze Sources to Ingest | Silver Tables to Build | Gold Views |
|---|---|---|---|
| **H1 Delegation concentration** | Tally delegations, Dune delegation history, Agora delegate list, Etherscan holders, Forum delegate threads, Interviews | `delegations`, `token_distribution`, `delegate_profiles`, `coded_interviews`, `coded_forum_posts` | `delegation_concentration`, `delegate_lifecycle` |
| **H2 Token-weighted power** | Dune voting power, ENS Ledger scripts, Snapshot + Tally votes, Forum debates, Token Terminal | `votes`, `token_distribution`, `proposals`, `coded_forum_posts` | `power_structure`, `voter_participation` |
| **H3 UX and information** | Agora/Boardroom UI data, Dune/Tally delegation network, Forum delegate statements, Interviews | `delegate_profiles`, `delegations`, `coded_interviews` | `delegate_lifecycle`, `delegation_concentration` |
| **H4 Participation barriers** | Tally/Agora proposal texts, Forum threads, Interviews, ENS Newsletter, Token Terminal | `proposals` (with complexity_score), `votes`, `coded_interviews`, `coded_forum_posts` | `voter_participation`, `qualitative_code_matrix` |
| **H5 Narrative vs reality** | ENS Docs/Basics/website, Dune/Ledger concentration data, Forum (veto debates), Etherscan/Tally (veto multisig) | `token_distribution`, `coded_docs`, `proposals` | `power_structure`, `qualitative_code_matrix` |
| **H6 Delegate dynamics** | Agora/Boardroom (join dates), Dune (growth), Forum (delegate threads), Interviews, ENS Docs | `delegate_profiles`, `delegations`, `coded_interviews`, `proposals` | `delegate_lifecycle` |
| **H7 Treasury** | enswallets, SafeNotes, Forum WG reports, Karpatkey, ENS Ledger, Grants + threads | `treasury_flows`, `grants`, `compensation` | `treasury_reconstruction` |
| **H8 Compensation** | Forum WG budgets, Grants, Interviews, ENS Docs | `compensation`, `coded_interviews`, `coded_forum_posts` | `qualitative_code_matrix`, `treasury_reconstruction` |

---

## 6. Draft ToDo List for two week sprints


Week 1-2: Foundation
- [ ] Finalize taxonomy.yaml (team review)
- [ ] Set up repo structure
- [ ] Write first ingest scripts (Snapshot, Tally, Dune — biggest bang for buck)
- [ ] Establish metadata sidecar convention

Week 3-4: Bronze Sprint  
- [ ] Ingest all quantitative sources into bronze/
- [ ] Begin forum export + interview transcript collection
- [ ] Build crosswalk/address_to_identity (manual + ENS reverse resolution)
- [ ] Document everything in collection-log.md

Week 5-6: Silver Sprint
- [ ] Transform quantitative bronze → silver Parquet tables
- [ ] Begin qualitative coding (interviews first, then forum posts)
- [ ] Build complexity_score for proposals (H4.1)
- [ ] Entity resolution across sources
- [ ] Validate: run data quality scripts
- [ ] Data Quality Assessment Plan

Week 7-8: Gold Sprint + Analysis Start
- [ ] Choose analysis/viz tool (Quarto, Hex, Observable)
- [ ] Materialize gold views per hypothesis cluster
- [ ] Flatten qualitative codes into queryable Parquet
- [ ] Begin hypothesis testing for reports


