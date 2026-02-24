-- Silver: Cleaned Snapshot proposals
-- Normalizes timestamps, lowercases addresses, validates status

select distinct
    proposal_id,
    title,
    body,
    {{ lowercase_address('author_address') }} as author_address,
    lower(status) as status,
    proposal_type,
    choices,
    scores,
    scores_total,
    vote_count,
    {{ unix_ts_to_timestamp('start_ts') }} as start_date,
    {{ unix_ts_to_timestamp('end_ts') }} as end_date,
    snapshot_block,
    'snapshot' as source
from {{ ref('stg_snapshot_proposals') }}
where proposal_id is not null
