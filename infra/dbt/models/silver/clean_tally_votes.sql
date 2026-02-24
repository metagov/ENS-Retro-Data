-- Silver: Cleaned Tally votes
-- Maps support codes to taxonomy, converts weight from wei

select distinct
    vote_id,
    {{ lowercase_address('voter') }} as voter,
    proposal_id,
    {{ map_vote_choice_tally('support_code') }} as vote_choice,
    {{ wei_to_ether('weight_wei') }} as weight,
    reason,
    'tally' as source
from {{ ref('stg_tally_votes') }}
where vote_id is not null
