-- Staging: ENS grants program data
-- Reads raw JSON and renames columns to snake_case

select
    id as grant_id,
    title,
    applicant,
    amount_requested,
    amount_awarded,
    token,
    value_usd,
    status,
    working_group,
    description,
    date,
    quarter
from {{ source('bronze_grants', 'grants') }}
