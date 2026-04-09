-- Consistency check: verify that the accepted_values used in _silver.yml
-- tests match the canonical taxonomy seed tables in main_reference.
--
-- If this test FAILS, it means taxonomy.yaml was updated but the
-- accepted_values lists in _silver.yml / _gold.yml were not. Fix by
-- running `uv run python scripts/generate_taxonomy_seeds.py` then
-- updating the hardcoded lists to match.
--
-- This test returns rows where a value appears in the seed but NOT in
-- the set of distinct values actually present in the silver tables, or
-- vice versa. An empty result set means everything is consistent.

-- Check 1: proposal_status values in taxonomy match what silver uses
with taxonomy_statuses as (
    select status as value from {{ ref('taxonomy_proposal_status') }}
),
silver_snapshot_statuses as (
    select distinct status as value from {{ ref('clean_snapshot_proposals') }}
),
silver_tally_statuses as (
    select distinct status as value from {{ ref('clean_tally_proposals') }}
),
all_silver_statuses as (
    select value from silver_snapshot_statuses
    union
    select value from silver_tally_statuses
),
-- Find any silver status NOT in the taxonomy (real violations)
status_violations as (
    select s.value as silver_value, 'proposal_status' as taxonomy_field, 'value_not_in_taxonomy' as issue
    from all_silver_statuses s
    left join taxonomy_statuses t on s.value = t.value
    where t.value is null
),

-- Check 2: vote_choices
taxonomy_choices as (
    select choice as value from {{ ref('taxonomy_vote_choices') }}
),
silver_snapshot_choices as (
    select distinct vote_choice as value from {{ ref('clean_snapshot_votes') }}
    where vote_choice != 'unknown'
),
silver_tally_choices as (
    select distinct vote_choice as value from {{ ref('clean_tally_votes') }}
    where vote_choice != 'unknown'
),
all_silver_choices as (
    select value from silver_snapshot_choices
    union
    select value from silver_tally_choices
),
choice_violations as (
    select s.value as silver_value, 'vote_choices' as taxonomy_field, 'value_not_in_taxonomy' as issue
    from all_silver_choices s
    left join taxonomy_choices t on s.value = t.value
    where t.value is null
),

-- Check 3: working_groups
taxonomy_wgs as (
    select working_group as value from {{ ref('taxonomy_working_groups') }}
),
silver_comp_wgs as (
    select distinct working_group as value from {{ ref('clean_compensation') }}
    where working_group is not null
),
silver_grants_wgs as (
    select distinct working_group as value from {{ ref('clean_grants') }}
    where working_group is not null
),
all_silver_wgs as (
    select value from silver_comp_wgs
    union
    select value from silver_grants_wgs
),
wg_violations as (
    select s.value as silver_value, 'working_groups' as taxonomy_field, 'value_not_in_taxonomy' as issue
    from all_silver_wgs s
    left join taxonomy_wgs t on s.value = t.value
    where t.value is null
)

-- Union all violations — if this returns ANY rows, the test fails
select * from status_violations
union all
select * from choice_violations
union all
select * from wg_violations
