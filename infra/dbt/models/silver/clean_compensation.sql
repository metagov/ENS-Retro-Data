-- Silver: Cleaned compensation records
-- Normalizes roles and working groups to taxonomy values

with deduped as (
    select *,
        row_number() over (
            partition by recipient_address, amount, token, period, working_group, role, date
            order by id
        ) as rn
    from {{ ref('stg_compensation') }}
    where recipient_address is not null
)
select
    id,
    {{ lowercase_address('recipient_address') }} as recipient_address,
    amount,
    token,
    value_usd,
    period,
    date,
    lower(working_group) as working_group,
    lower(role) as role,
    lower(category) as category
from deduped
where rn = 1
