-- Silver: Cleaned Tally delegates
-- Lowercases addresses, converts voting power from wei, deduplicates

select distinct on ({{ lowercase_address('address') }})
    {{ lowercase_address('address') }} as address,
    ens_name,
    {{ wei_to_ether('voting_power_wei') }} as voting_power,
    delegators_count,
    votes_count,
    proposals_count,
    statement,
    'tally' as source
from {{ ref('stg_tally_delegates') }}
where address is not null
order by {{ lowercase_address('address') }}, {{ wei_to_ether('voting_power_wei') }} desc
