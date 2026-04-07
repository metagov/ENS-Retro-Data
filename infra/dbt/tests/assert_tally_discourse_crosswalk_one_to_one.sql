-- Asserts tally_discourse_crosswalk has exactly one row per distinct Tally
-- proposal. Fails (returns rows) if the crosswalk and source disagree.

with src as (
    select count(distinct proposal_id) as n
    from {{ ref('stg_tally_proposals') }}
    where proposal_id is not null
),
xwalk as (
    select count(*) as n
    from {{ ref('tally_discourse_crosswalk') }}
)
select src.n as source_n, xwalk.n as crosswalk_n
from src, xwalk
where src.n <> xwalk.n
