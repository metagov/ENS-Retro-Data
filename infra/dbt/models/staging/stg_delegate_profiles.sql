-- Staging: Delegate profiles from interviews
-- Reads raw JSON and renames columns to snake_case

select
    address,
    name,
    role,
    interview_date,
    key_themes,
    summary
from {{ source('bronze_interviews', 'delegate_profiles') }}
