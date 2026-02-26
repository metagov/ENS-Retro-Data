-- Silver: Cleaned treasury flows
-- Normalizes addresses, parses amounts, validates categories

select distinct
    tx_hash,
    {{ lowercase_address('from_address') }} as from_address,
    {{ lowercase_address('to_address') }} as to_address,
    {{ wei_to_ether('value_raw') }} as value_ether,
    token,
    block_number,
    {{ unix_ts_to_timestamp('timestamp_unix') }} as transacted_at,
    lower(category) as category
from {{ ref('stg_treasury_flows') }}
where tx_hash is not null
