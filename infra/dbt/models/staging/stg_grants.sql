-- Staging: ENS grants program data
-- Reads raw JSON and renames columns to snake_case

select
    id as grant_id,
    title,
    applicant,
    amount_requested,
    amount_awarded,
    token,
    status,
    working_group,
    description
from {{ source('bronze_grants', 'grants') }}
