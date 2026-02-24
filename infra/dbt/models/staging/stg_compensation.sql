-- Staging: Compensation records
-- Reads raw JSON and renames columns to snake_case

select
    recipient as recipient_address,
    amount,
    token,
    period,
    working_group,
    role
from {{ source('bronze_financial', 'compensation') }}
