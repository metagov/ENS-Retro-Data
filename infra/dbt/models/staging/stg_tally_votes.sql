-- Staging: Tally individual votes
-- Reads raw JSON and renames columns to snake_case

select
    id as vote_id,
    voter,
    support as support_code,
    weight as weight_wei,
    proposal_id,
    reason
from {{ source('bronze_governance', 'tally_votes') }}
