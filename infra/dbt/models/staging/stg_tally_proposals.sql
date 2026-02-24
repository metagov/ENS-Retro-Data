-- Staging: Tally on-chain governance proposals
-- Reads raw JSON and renames columns to snake_case

select
    id as proposal_id,
    title,
    description as body,
    status,
    proposer as proposer_address,
    start_block,
    end_block,
    for_votes as for_votes_wei,
    against_votes as against_votes_wei,
    abstain_votes as abstain_votes_wei
from {{ source('bronze_governance', 'tally_proposals') }}
