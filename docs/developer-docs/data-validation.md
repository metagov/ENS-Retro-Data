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
│                   BRONZE (governance only)                  │
├────────────────────────────────────────────────────────────┤
│                      dbt Tests                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  not_null, unique, accepted_values                   │  │
│  │  configured in _staging.yml, _silver.yml, _gold.yml  │  │
│  └──────────────────────────────────────────────────────┘  │
│                    STAGING + SILVER + GOLD                  │
└────────────────────────────────────────────────────────────┘
```

> **Coverage note:** Bronze asset checks currently cover **only** the governance layer (Snapshot + Tally). On-chain, financial, grants, forum, and github assets rely on dbt tests at staging/silver/gold for now. See [`ROADMAP.md` section D](../ROADMAP.md#d-test-coverage-is-inverted-pipeline-has-0-tests-dashboard-has-106) for the expansion plan.

## Layer 1: Bronze Row Count Checks

Fast sanity checks that verify bronze JSON files contain data.

| Check | Asset | Expected Rows |
|---|---|---|
| `check_snapshot_proposals_count` | `snapshot_proposals` | ~90 |
| `check_snapshot_votes_count` | `snapshot_votes` | ~47,551 |
| `check_tally_proposals_count` | `tally_proposals` | ~62 (frozen) |
| `check_tally_votes_count` | `tally_votes` | ~9,550 (frozen) |
| `check_tally_delegates_count` | `tally_delegates` | ~37,876 (frozen) |

**Severity:** WARN (pipeline continues if a check fails — surfaces drift without blocking).

**Implementation:** `infra/validate/checks.py::_count_json_records()` — reads the JSON file and counts array elements.

## Layer 2: Bronze Great Expectations Suites

Schema and value validation using Great Expectations 1.x.

### How it works

1. Suite JSON files live in `infra/great_expectations/expectations/`
2. `_run_ge_suite()` creates an ephemeral GE context
3. Loads the bronze file into a pandas DataFrame via `_load_bronze_df()`
4. Maps expectation type strings to GE 1.x classes
5. Runs the validation definition and collects results
6. Returns a Dagster `AssetCheckResult`

### Supported Expectation Types

| Expectation type | GE class |
|---|---|
| `expect_table_row_count_to_be_between` | `gxe.ExpectTableRowCountToBeBetween` |
| `expect_column_to_exist` | `gxe.ExpectColumnToExist` |
| `expect_column_values_to_not_be_null` | `gxe.ExpectColumnValuesToNotBeNull` |
| `expect_column_values_to_be_unique` | `gxe.ExpectColumnValuesToBeUnique` |
| `expect_column_values_to_be_in_set` | `gxe.ExpectColumnValuesToBeInSet` |
| `expect_column_values_to_match_regex` | `gxe.ExpectColumnValuesToMatchRegex` |

Add more types by extending the dispatch table in `_run_ge_suite()`.

### Suite Files

#### `snapshot_proposals_suite.json`
- Row count between 50 and 500
- Columns exist: `id`, `title`, `state`, `author`
- Not null: `id`, `title`
- Unique: `id`
- `state` in `{active, closed, pending}`

#### `snapshot_votes_suite.json`
- Row count between 1000 and 200000
- Columns exist: `id`, `voter`, `vp`, `proposal_id`
- Not null: `id`, `voter`
- Unique: `id`
- `voter` matches `^0x[a-fA-F0-9]{40}$`

#### `tally_proposals_suite.json`
- Row count between 20 and 500
- Columns exist: `id`, `title`, `status`, `proposer`
- Not null: `id`, `title`
- Unique: `id`
- `proposer` matches `^0x[a-fA-F0-9]{40}$`

#### `tally_votes_suite.json`
- Row count between 1000 and 100000
- Columns exist: `id`, `voter`, `support`, `proposal_id`
- Not null: `id`, `voter`
- Unique: `id`
- `voter` matches `^0x[a-fA-F0-9]{40}$`

#### `tally_delegates_suite.json`
- Row count between 1000 and 100000
- Columns exist: `address`, `voting_power`, `votes_count`
- Not null: `address`
- Unique: `address`
- `address` matches `^0x[a-fA-F0-9]{40}$`

## Layer 3: dbt Tests

Column-level constraints defined in YAML schema files, executed as part of `dbt build`. Totals: **~45 silver tests + ~21 gold tests**, plus staging checks.

### Staging Tests (`_staging.yml`)

Tests on staging views verify the raw data shape. Representative examples:

- `stg_snapshot_proposals`: `proposal_id` not_null + unique, `author_address` not_null, `status` accepted_values
- `stg_snapshot_votes`: `vote_id` not_null + unique, `voter` not_null, `proposal_id` not_null
- `stg_tally_proposals`: `proposal_id` not_null + unique

### Silver Tests (`_silver.yml`)

Tests on cleaned tables verify data quality after transformations:

- `clean_snapshot_proposals`: `proposal_id` not_null + unique, `author_address` not_null, `status` accepted_values, `source = 'snapshot'`
- `clean_snapshot_votes`: `vote_id` not_null + unique, `voter` not_null, `vote_choice` accepted_values, `source = 'snapshot'`
- `clean_tally_proposals`: `proposal_id` not_null + unique, `status` accepted_values, `source = 'tally'`
- `clean_tally_votes`: `vote_id` not_null + unique, `voter` not_null, `vote_choice` accepted_values, `source = 'tally'`
- `clean_tally_delegates`: `address` not_null + unique
- `clean_delegations`: `delegator` not_null, `delegate` not_null
- `clean_token_distribution`: `address` not_null + unique
- `clean_treasury_flows`: `tx_hash` not_null + unique
- `clean_ens_ledger`: `tx_hash`, `tx_date`, `category`, `flow_type`, `asset`, `value_usd` constraints
- `clean_grants`: `grant_id` not_null + unique, `working_group` accepted_values
- `clean_compensation`: `recipient_address` not_null, `working_group` + `role` accepted_values
- `clean_oso_ens_code_metrics`: `artifact_id`, `artifact_name`, `source` constraints
- `clean_oso_ens_timeseries`: `artifact_id`, `event_type`, `event_time`, `source` constraints
- `address_crosswalk`: `address` not_null + unique
- `snapshot_discourse_crosswalk` / `tally_discourse_crosswalk`: `proposal_id`, `topic_id`, `match_source` constraints

### Gold Tests (`_gold.yml`)

- `governance_activity`: `proposal_id` not_null + unique, `source` accepted_values, `title` not_null
- `governance_discourse_activity`: `source`, `proposal_id`, `match_source`, `has_forum_discussion`, `topic_id` constraints
- `delegate_scorecard`: `address` not_null + unique, `voting_power` not_null
- `treasury_summary`: `period`, `category`, `inflows_usd`, `outflows_usd`, `net_usd`, `internal_transfer_usd` constraints
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

3. No manual registration needed — `load_asset_checks_from_modules([check_modules])` in `infra/definitions.py` picks up every `@asset_check` decorated function in the module automatically.
