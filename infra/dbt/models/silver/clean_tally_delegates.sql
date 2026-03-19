-- Silver: Cleaned Tally delegates
-- Lowercases addresses, converts voting power from wei, deduplicates

select distinct on ({{ lowercase_address('address') }})
    {{ lowercase_address('address') }} as address,
    id,
    name,
    ens_name,
    twitter,
    bio,
    picture,
    account_type,
    {{ wei_to_ether('voting_power_wei') }} as voting_power,
    delegators_count,
    is_prioritized,
    chain_id,
    token_symbol,
    token_name,
    statement,
    statement_summary,
    is_seeking_delegation,
    'tally' as source
from {{ ref('stg_tally_delegates') }}
where address is not null
order by {{ lowercase_address('address') }}, {{ wei_to_ether('voting_power_wei') }} desc
