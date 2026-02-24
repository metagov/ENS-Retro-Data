# Taxonomy & Controlled Vocabularies

The project uses a single source of truth (`taxonomy.yaml`) for all controlled vocabularies. This ensures consistency across bronze ingestion, dbt transformations, dbt tests, and Great Expectations suites.

## taxonomy.yaml

**Location:** `/taxonomy.yaml` (project root)

### Vocabularies

#### `sources` (9 values)
Data source identifiers used throughout the pipeline.

| Value                  | Description                        |
|------------------------|------------------------------------|
| `snapshot`             | Snapshot.org governance platform   |
| `tally`                | Tally.xyz governance platform      |
| `etherscan`            | Etherscan block explorer           |
| `dune`                 | Dune Analytics                     |
| `ens-governance-forum` | ENS governance forum (Discourse)   |
| `github`               | GitHub repositories                |
| `interviews`           | Stakeholder interviews             |
| `grants-portal`        | ENS grants portal                  |
| `token-contract`       | ENS token contract data            |

#### `governance_categories` (6 values)
Proposal classification categories.

| Value            | Description                          |
|------------------|--------------------------------------|
| `executable`     | On-chain executable proposals        |
| `social`         | Off-chain social signaling           |
| `constitutional` | Constitutional amendments            |
| `metagovernance` | Governance process changes           |
| `funding`        | Funding and budget proposals         |
| `election`       | Working group elections              |

#### `proposal_status` (7 values)
Normalized proposal lifecycle states.

| Value       | Description                  |
|-------------|------------------------------|
| `active`    | Currently open for voting    |
| `closed`    | Voting period ended          |
| `executed`  | Proposal executed on-chain   |
| `defeated`  | Proposal did not pass        |
| `pending`   | Queued but not yet active    |
| `queued`    | Awaiting execution           |
| `cancelled` | Proposal cancelled           |

#### `vote_choices` (3 values)
Standardized vote options.

| Value     | Snapshot Code | Tally Code |
|-----------|---------------|------------|
| `for`     | 1             | 1          |
| `against` | 2             | 0          |
| `abstain` | 3             | 2          |

#### `stakeholder_roles` (8 values)
ENS DAO participant roles.

| Value                | Description                          |
|----------------------|--------------------------------------|
| `delegate`           | Token holder's delegate              |
| `steward`            | Working group steward                |
| `contributor`        | Active contributor                   |
| `token_holder`       | ENS token holder                     |
| `service_provider`   | External service provider            |
| `multisig_signer`    | Treasury multisig signer             |
| `working_group_lead` | Working group leader                 |
| `dao_officer`        | DAO officer role                     |

#### `working_groups` (4 values)
ENS DAO working groups.

| Value              | Description                     |
|--------------------|---------------------------------|
| `meta-governance`  | Governance process & operations |
| `ens-ecosystem`    | ENS protocol development        |
| `public-goods`     | Public goods funding            |
| `providers`        | Infrastructure providers        |

#### `evaluation_dimensions` (7 values)
Retrospective evaluation criteria.

| Value                       | Description                          |
|-----------------------------|--------------------------------------|
| `governance_participation`  | Voting and proposal activity         |
| `proposal_quality`          | Quality of proposals submitted       |
| `financial_stewardship`     | Treasury management effectiveness    |
| `ecosystem_growth`          | Protocol adoption and growth         |
| `decentralization`          | Power distribution metrics           |
| `transparency`              | Information disclosure practices     |
| `community_engagement`      | Community participation depth        |

#### `entity_types` (8 values)
Data entity types across the pipeline.

`address`, `proposal`, `vote`, `delegate`, `transaction`, `grant`, `working_group`, `forum_post`

#### `data_layers` (3 values)
Medallion architecture layers: `bronze`, `silver`, `gold`

#### `bronze_domains` (8 values)
Bronze subdirectory names: `on-chain`, `governance`, `forum`, `financial`, `docs`, `interviews`, `grants`, `github`

#### `silver_domains` (3 values)
Silver data categories: `quantitative`, `qualitative`, `crosswalk`

## Where Taxonomies Are Used

### 1. dbt Tests (`accepted_values`)
Silver model tests in `_silver.yml` validate categorical columns against taxonomy values:

```yaml
- name: status
  tests:
    - accepted_values:
        values: ['active', 'closed', 'executed', 'defeated', 'pending', 'queued', 'cancelled']
```

### 2. dbt Macros
Vote choice mapping macros (`map_vote_choice_snapshot`, `map_vote_choice_tally`) encode the taxonomy-defined vote choices.

### 3. Python Validation
`infra/taxonomy.py::validate_column()` checks pandas/polars Series against taxonomy values at runtime.

### 4. dbt Seeds
`scripts/generate_taxonomy_seeds.py` generates seed CSVs from `taxonomy.yaml` for use as reference tables in DuckDB.

### 5. Great Expectations
GE suites validate that categorical columns contain expected values (e.g., `expect_column_values_to_be_in_set` for proposal states).

## Updating Taxonomies

1. Edit `taxonomy.yaml`
2. Regenerate seed CSVs:
   ```bash
   uv run python scripts/generate_taxonomy_seeds.py
   ```
3. Update dbt tests in `_staging.yml`, `_silver.yml`, `_gold.yml` if accepted_values changed
4. Update GE suites if value_set expectations changed
5. Reload dbt seeds:
   ```bash
   uv run dbt seed --project-dir infra/dbt --profiles-dir infra/dbt
   ```
