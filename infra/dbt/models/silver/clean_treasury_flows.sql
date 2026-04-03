-- Silver: Cleaned treasury flows
-- Normalizes addresses, applies token-aware decimal conversion, filters spam tokens.
-- USDC/USDT use 6 decimals; all others (ETH, ENS, WETH) use 18 decimals.
-- Spam/dust tokens (phishing URLs, unsolicited airdrops) are excluded.

select distinct
    tx_hash,
    {{ lowercase_address('from_address') }} as from_address,
    {{ lowercase_address('to_address') }} as to_address,
    {{ token_to_value('value_raw', 'token') }} as value_ether,
    token,
    block_number,
    {{ unix_ts_to_timestamp('timestamp_unix') }} as transacted_at,
    lower(category) as category
from {{ ref('stg_treasury_flows') }}
where tx_hash is not null
  and token in ('ETH', 'ENS', 'USDC', 'USDT', 'WETH')
