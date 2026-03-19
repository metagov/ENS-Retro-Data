-- Staging: Tally individual votes
-- Reads raw JSON and renames columns to snake_case

select
    id as vote_id,
    voter,
    voter_name,
    voter_ens,
    support as support_code,
    weight as weight_wei,
    reason,
    tx_hash,
    chain_id,
    proposal_id,
    block_timestamp,
    block_number
from {{ source('bronze_governance', 'tally_votes') }}
