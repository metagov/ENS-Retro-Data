-- Silver: Cleaned grants data
-- Normalizes working group, validates amounts

select distinct
    grant_id,
    title,
    applicant,
    amount_requested,
    amount_awarded,
    token,
    value_usd,
    lower(status) as status,
    case lower(working_group)
        when 'metagov'      then 'meta-governance'
        when 'ecosystem'    then 'ens-ecosystem'
        when 'public goods' then 'public-goods'
        when 'community wg' then 'ens-ecosystem'
        else lower(working_group)
    end as working_group,
    description,
    try_cast(date as date) as date,
    quarter
from {{ ref('stg_grants') }}
where grant_id is not null
