-- Silver: Cleaned Tally proposals
-- Converts wei to ether, normalizes status

select distinct
    proposal_id,
    title,
    body,
    {{ lowercase_address('proposer_address') }} as proposer_address,
    lower(status) as status,
    start_block,
    end_block,
    try_cast(start_timestamp as timestamp) as start_date,
    try_cast(end_timestamp as timestamp) as end_date,
    {{ wei_to_ether('for_votes_wei') }} as for_votes,
    {{ wei_to_ether('against_votes_wei') }} as against_votes,
    {{ wei_to_ether('abstain_votes_wei') }} as abstain_votes,
    try_cast(start_timestamp as date) as start_date,
    (for_voters + against_voters + abstain_voters) as voter_count,
    'tally' as source
from {{ ref('stg_tally_proposals') }}
where proposal_id is not null
