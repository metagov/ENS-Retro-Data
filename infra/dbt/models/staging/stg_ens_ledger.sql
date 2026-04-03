-- Staging: ENS Foundation transaction ledger
-- Reads labeled CSV and renames columns to snake_case
-- Amount is already in token units (not wei). Value is USD.

select
    "Transaction Hash" as tx_hash,
    try_cast("Date" as date)  as tx_date,
    "Quarter"                  as quarter,
    "From"                     as source_entity,
    "To"                       as destination,
    "Category"                 as category,
    try_cast("Amount" as double) as amount,
    "Asset"                    as asset,
    try_cast("Value"  as double) as value_usd
from {{ source('bronze_financial', 'ens_ledger') }}
