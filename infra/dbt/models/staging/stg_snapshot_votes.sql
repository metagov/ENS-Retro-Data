-- Staging: Snapshot individual votes
-- Reads raw JSON and renames columns to snake_case

select
    id as vote_id,
    voter,
    choice as choice_index,
    vp as voting_power,
    created as created_ts,
    proposal_id
from {{ source('bronze_governance', 'snapshot_votes') }}
