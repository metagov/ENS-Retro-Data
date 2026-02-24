-- Staging: Snapshot governance proposals
-- Reads raw JSON and renames columns to snake_case

select
    id as proposal_id,
    title,
    body,
    author as author_address,
    state as status,
    type as proposal_type,
    choices,
    scores,
    scores_total,
    votes as vote_count,
    start as start_ts,
    "end" as end_ts,
    snapshot as snapshot_block
from {{ source('bronze_governance', 'snapshot_proposals') }}
