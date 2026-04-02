-- Staging: Delegate profiles from Tally (historical snapshot — Tally.xyz shut down)
-- Maps Tally delegate fields to a common profile schema

select
    address,
    coalesce(ens_name, name)             as name,
    null::varchar                         as role,
    null::date                            as interview_date,
    statement_summary                     as key_themes,
    bio                                   as summary
from {{ source('bronze_governance', 'tally_delegates') }}
