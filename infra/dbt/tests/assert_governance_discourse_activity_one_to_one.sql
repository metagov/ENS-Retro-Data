-- Asserts governance_discourse_activity has exactly one row per proposal,
-- matching the union of both silver crosswalks (Tally + Snapshot).

with expected as (
    select
        (select count(*) from {{ ref('tally_discourse_crosswalk') }})
      + (select count(*) from {{ ref('snapshot_discourse_crosswalk') }}) as n
),
actual as (
    select count(*) as n from {{ ref('governance_discourse_activity') }}
)
select expected.n as expected_n, actual.n as actual_n
from expected, actual
where expected.n <> actual.n
