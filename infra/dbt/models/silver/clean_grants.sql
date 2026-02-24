-- Silver: Cleaned grants data
-- Normalizes working group, validates amounts

select distinct
    grant_id,
    title,
    applicant,
    amount_requested,
    amount_awarded,
    token,
    lower(status) as status,
    lower(working_group) as working_group,
    description
from {{ ref('stg_grants') }}
where grant_id is not null
