-- Silver: Cleaned compensation records
-- Normalizes roles and working groups to taxonomy values

select distinct
    {{ lowercase_address('recipient_address') }} as recipient_address,
    amount,
    token,
    period,
    lower(working_group) as working_group,
    lower(role) as role
from {{ ref('stg_compensation') }}
where recipient_address is not null
