-- Silver: Cleaned token distribution
-- Converts balances from wei, computes percentages

with raw as (
    select
        {{ lowercase_address('address') }} as address,
        {{ wei_to_ether('balance_wei') }} as balance,
        snapshot_block
    from {{ ref('stg_token_distribution') }}
    where address is not null
),

total as (
    select sum(balance) as total_supply from raw
)

select distinct
    r.address,
    r.balance,
    case
        when t.total_supply > 0 then r.balance / t.total_supply * 100
        else 0
    end as percentage,
    r.snapshot_block
from raw r
cross join total t
order by r.balance desc
