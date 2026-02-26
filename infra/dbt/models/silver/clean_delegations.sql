-- Silver: Cleaned delegation events
-- Lowercases addresses, converts balances, sorts by block

select distinct
    {{ lowercase_address('delegator') }} as delegator,
    {{ lowercase_address('delegate') }} as delegate,
    block_number,
    {{ unix_ts_to_timestamp('timestamp_unix') }} as delegated_at,
    {{ wei_to_ether('token_balance_wei') }} as token_balance
from {{ ref('stg_delegations') }}
where delegator is not null and delegate is not null
order by block_number
