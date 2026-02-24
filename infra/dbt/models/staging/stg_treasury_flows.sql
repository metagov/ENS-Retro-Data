-- Staging: ENS DAO treasury flows
-- Reads raw JSON and renames columns to snake_case

select
    tx_hash,
    "from" as from_address,
    "to" as to_address,
    value as value_raw,
    token,
    block_number,
    timestamp as timestamp_unix,
    category
from {{ source('bronze_onchain', 'treasury_flows') }}
