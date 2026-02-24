-- Gold: Treasury summary by month and category
-- Aggregates treasury flows with grants and compensation breakdowns

with monthly_flows as (
    select
        date_trunc('month', transacted_at) as period,
        category,
        sum(case when to_address is not null then value_ether else 0 end) as outflows,
        sum(case when from_address is not null then value_ether else 0 end) as inflows
    from {{ ref('clean_treasury_flows') }}
    group by 1, 2
),

grant_spend as (
    select
        lower(working_group) as category,
        sum(amount_awarded) as grant_spend
    from {{ ref('clean_grants') }}
    where amount_awarded is not null
    group by 1
),

compensation_spend as (
    select
        lower(working_group) as category,
        sum(amount) as compensation_spend
    from {{ ref('clean_compensation') }}
    where amount is not null
    group by 1
)

select
    mf.period,
    mf.category,
    mf.inflows,
    mf.outflows,
    mf.inflows - mf.outflows as net,
    coalesce(gs.grant_spend, 0) as grant_spend,
    coalesce(cs.compensation_spend, 0) as compensation_spend
from monthly_flows mf
left join grant_spend gs on mf.category = gs.category
left join compensation_spend cs on mf.category = cs.category
order by mf.period, mf.category
