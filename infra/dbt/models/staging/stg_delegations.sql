-- Staging: ENS token delegation events
-- Reads raw JSON and renames columns to snake_case

select
    delegator,
    delegate,
    block_number,
    timestamp as timestamp_unix,
    token_balance as token_balance_wei
from {{ source('bronze_onchain', 'delegations') }}
