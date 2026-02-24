# Data Validation

Three layers of validation ensure data quality across the pipeline.

## Validation Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Dagster Asset Checks                     │
│  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │  Row Count (5)   │  │  Great Expectations Suites (5) │  │
│  │  fast, always    │  │  schema + value validation     │  │
│  └──────────────────┘  └────────────────────────────────┘  │
│                         BRONZE LAYER                        │
├────────────────────────────────────────────────────────────┤
│                      dbt Tests                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  not_null, unique, accepted_values                   │  │
│  │  configured in _staging.yml, _silver.yml, _gold.yml  │  │
│  └──────────────────────────────────────────────────────┘  │
│                    SILVER + GOLD LAYERS                     │
└────────────────────────────────────────────────────────────┘
```

## Layer 1: Bronze Row Count Checks

Fast sanity checks that verify bronze JSON files contain data.

| Check                             | Asset               | Expected Rows |
|-----------------------------------|----------------------|---------------|
| `check_snapshot_proposals_count`  | snapshot_proposals   | ~90           |
| `check_snapshot_votes_count`      | snapshot_votes       | ~47,551       |
| `check_tally_proposals_count`     | tally_proposals      | ~62           |
| `check_tally_votes_count`         | tally_votes          | ~9,550        |
| `check_tally_delegates_count`     | tally_delegates      | ~37,876       |

**Severity:** WARN (pipeline continues if check fails)

**Implementation:** `infra/validate/checks.py::_count_json_records()` — reads the JSON file, counts array elements.

## Layer 2: Bronze Great Expectations Suites

Schema and value validation using Great Expectations 1.x.

### How it works

1. Suite JSON files are stored in `infra/great_expectations/expectations/`
2. `_run_ge_suite()` creates an ephemeral GE context
3. Loads the bronze file into a pandas DataFrame
4. Maps expectation type strings to GE 1.x classes
5. Runs the validation definition and collects results
6. Returns a Dagster `AssetCheckResult`

### Supported Expectation Types

| Expectation Type                        | GE Class                              |
|-----------------------------------------|---------------------------------------|
| `expect_table_row_count_to_be_between`  | `gxe.ExpectTableRowCountToBeBetween`  |
| `expect_column_to_exist`               | `gxe.ExpectColumnToExist`             |
| `expect_column_values_to_not_be_null`  | `gxe.ExpectColumnValuesToNotBeNull`   |
| `expect_column_values_to_be_unique`    | `gxe.ExpectColumnValuesToBeUnique`    |
| `expect_column_values_to_be_in_set`    | `gxe.ExpectColumnValuesToBeInSet`     |
| `expect_column_values_to_match_regex`  | `gxe.ExpectColumnValuesToMatchRegex`  |

### Suite Files

#### `snapshot_proposals_suite.json`
| # | Expectation                         | Parameters                                    |
|---|-------------------------------------|-----------------------------------------------|
| 1 | Row count between                   | min=50, max=500                               |
| 2 | Column exists: `id`                 |                                               |
| 3 | Column exists: `title`              |                                               |
| 4 | Column exists: `state`              |                                               |
| 5 | Column exists: `author`             |                                               |
| 6 | Not null: `id`                      |                                               |
| 7 | Not null: `title`                   |                                               |
| 8 | Unique: `id`                        |                                               |
| 9 | Values in set: `state`              | `[active, closed, pending]`                   |

#### `snapshot_votes_suite.json`
| # | Expectation                         | Parameters                                    |
|---|-------------------------------------|-----------------------------------------------|
| 1 | Row count between                   | min=1000, max=200000                          |
| 2 | Column exists: `id`                 |                                               |
| 3 | Column exists: `voter`              |                                               |
| 4 | Column exists: `vp`                 |                                               |
| 5 | Column exists: `proposal_id`        |                                               |
| 6 | Not null: `id`                      |                                               |
| 7 | Not null: `voter`                   |                                               |
| 8 | Unique: `id`                        |                                               |
| 9 | Regex: `voter`                      | `^0x[a-fA-F0-9]{40}$`                        |

#### `tally_proposals_suite.json`
| # | Expectation                         | Parameters                                    |
|---|-------------------------------------|-----------------------------------------------|
| 1 | Row count between                   | min=20, max=500                               |
| 2 | Column exists: `id`, `title`, `status`, `proposer` |                              |
| 6 | Not null: `id`, `title`             |                                               |
| 8 | Unique: `id`                        |                                               |
| 9 | Regex: `proposer`                   | `^0x[a-fA-F0-9]{40}$`                        |

#### `tally_votes_suite.json`
| # | Expectation                         | Parameters                                    |
|---|-------------------------------------|-----------------------------------------------|
| 1 | Row count between                   | min=1000, max=100000                          |
| 2 | Column exists: `id`, `voter`, `support`, `proposal_id` |                          |
| 6 | Not null: `id`, `voter`             |                                               |
| 8 | Unique: `id`                        |                                               |
| 9 | Regex: `voter`                      | `^0x[a-fA-F0-9]{40}$`                        |

#### `tally_delegates_suite.json`
| # | Expectation                         | Parameters                                    |
|---|-------------------------------------|-----------------------------------------------|
| 1 | Row count between                   | min=1000, max=100000                          |
| 2 | Column exists: `address`, `voting_power`, `votes_count` |                          |
| 5 | Not null: `address`                 |                                               |
| 6 | Unique: `address`                   |                                               |
| 7 | Regex: `address`                    | `^0x[a-fA-F0-9]{40}$`                        |

## Layer 3: dbt Tests

Column-level constraints defined in YAML schema files, executed as part of `dbt build`.

### Staging Tests (`_staging.yml`)

Tests on staging views verify the raw data shape.

**Active models** (real data — severity: error):
- `stg_snapshot_proposals`: `id` not_null + unique
- `stg_snapshot_votes`: `id` not_null + unique
- `stg_tally_proposals`: `id` not_null + unique
- `stg_tally_votes`: `id` not_null + unique
- `stg_tally_delegates`: `address` not_null + unique

**Sentinel models** (placeholder data — severity: warn):
- `stg_delegations`, `stg_token_distribution`, `stg_treasury_flows`
- `stg_grants`, `stg_compensation`, `stg_delegate_profiles`, `stg_forum_posts`

### Silver Tests (`_silver.yml`)

Tests on cleaned tables verify data quality after transformations.

**Active models** (severity: error):
- `clean_snapshot_proposals`: `proposal_id` not_null + unique, `author_address` not_null, `status` accepted_values, `source` = 'snapshot'
- `clean_snapshot_votes`: `vote_id` not_null + unique, `voter` not_null, `vote_choice` accepted_values, `source` = 'snapshot'
- `clean_tally_proposals`: `proposal_id` not_null + unique, `status` accepted_values, `source` = 'tally'
- `clean_tally_votes`: `vote_id` not_null + unique, `voter` not_null, `vote_choice` accepted_values, `source` = 'tally'
- `clean_tally_delegates`: `address` not_null + unique

**Sentinel models** (severity: warn):
- `clean_delegations`: `delegator` not_null, `delegate` not_null
- `clean_token_distribution`: `address` not_null + unique
- `clean_treasury_flows`: `tx_hash` not_null + unique
- `clean_grants`: `grant_id` not_null + unique, `working_group` accepted_values
- `clean_compensation`: `recipient_address` not_null, `working_group` accepted_values, `role` accepted_values

### Gold Tests (`_gold.yml`)

Tests on analysis-ready tables:

- `governance_activity`: `proposal_id` not_null + unique, `source` accepted_values, `title` not_null
- `delegate_scorecard`: `address` not_null + unique, `voting_power` not_null
- `treasury_summary`: `period` not_null (severity: warn — placeholder data)
- `participation_index`: `metric` not_null + unique, `value` not_null
- `decentralization_index`: `metric` not_null + unique, `value` not_null

## Adding a New Expectation Suite

1. Create a JSON file in `infra/great_expectations/expectations/<name>_suite.json`:

```json
{
  "expectation_suite_name": "<name>_suite",
  "expectations": [
    {
      "expectation_type": "expect_table_row_count_to_be_between",
      "kwargs": {"min_value": 10, "max_value": 10000}
    },
    {
      "expectation_type": "expect_column_to_exist",
      "kwargs": {"column": "id"}
    }
  ],
  "meta": {
    "great_expectations_version": "1.12.3"
  }
}
```

2. Add the asset check in `infra/validate/checks.py`:

```python
@asset_check(asset="<asset_name>", description="GE schema & value validation")
def check_ge_<name>():
    return _run_ge_suite("<subdomain>", "<filename>.json", "<name>_suite")
```

3. Register the check in `infra/definitions.py`:

```python
from infra.validate.checks import check_ge_<name>

all_checks = [
    ...
    check_ge_<name>,
]
```
