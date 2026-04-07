-- Asserts snapshot_discourse_crosswalk has exactly one row per distinct
-- Snapshot proposal. Fails (returns rows) if the crosswalk and source disagree.

with src as (
    select count(distinct proposal_id) as n
    from {{ ref('clean_snapshot_proposals') }}
),
xwalk as (
    select count(*) as n
    from {{ ref('snapshot_discourse_crosswalk') }}
)
select src.n as source_n, xwalk.n as crosswalk_n
from src, xwalk
where src.n <> xwalk.n
