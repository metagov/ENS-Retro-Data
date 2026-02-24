-- Singular test: governance_activity must contain data from both sources
-- Returns rows if the assertion fails (i.e., a source is missing)

with source_counts as (
    select
        count(*) filter (where source = 'snapshot') as snapshot_count,
        count(*) filter (where source = 'tally') as tally_count
    from {{ ref('governance_activity') }}
)

select *
from source_counts
where snapshot_count = 0 or tally_count = 0
