-- Staging: Compensation records
-- Reads raw JSON and renames columns to snake_case

select
    id,
    recipient as recipient_address,
    amount,
    token,
    value_usd,
    period,
    date,
    working_group,
    role,
    category
from {{ source('bronze_financial', 'compensation') }}
