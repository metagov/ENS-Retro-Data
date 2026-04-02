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
    {{ wei_to_ether('for_votes_wei') }} as for_votes,
    {{ wei_to_ether('against_votes_wei') }} as against_votes,
    {{ wei_to_ether('abstain_votes_wei') }} as abstain_votes,
    try_cast(start_timestamp as date) as start_date,
    'tally' as source
from {{ ref('stg_tally_proposals') }}
where proposal_id is not null
