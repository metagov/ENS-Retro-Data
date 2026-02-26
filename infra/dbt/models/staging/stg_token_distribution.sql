-- Staging: ENS token distribution snapshot
-- Reads raw JSON and renames columns to snake_case

select
    address,
    balance as balance_wei,
    percentage,
    snapshot_block
from {{ source('bronze_onchain', 'token_distribution') }}
