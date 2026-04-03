-- Gold: Treasury summary by month and category
-- Primary source: clean_ens_ledger (ENS Foundation labeled ledger, 2316 records, 2022–2025)
-- Amounts in USD for cross-token comparability.
--
-- flow_type breakdown:
--   inflow   = external revenue (Registrar ETH, CoW Swap yield, Endowment)
--   outflow  = working group spending (grants, salaries, contractors, IRL, etc.)
--   internal = DAO Wallet → WG budget allocations (not end-spend, just transfers)

with monthly as (
    select
        date_trunc('month', tx_date)    as period,
        category,
        flow_type,
        sum(value_usd)                  as amount_usd
    from {{ ref('clean_ens_ledger') }}
    group by 1, 2, 3
)

select
    period,
    category,
    sum(case when flow_type = 'inflow'    then amount_usd else 0 end) as inflows_usd,
    sum(case when flow_type = 'outflow'   then amount_usd else 0 end) as outflows_usd,
    sum(case when flow_type = 'inflow'    then amount_usd else 0 end)
  - sum(case when flow_type = 'outflow'  then amount_usd else 0 end) as net_usd,
    sum(case when flow_type = 'internal' then amount_usd else 0 end) as internal_transfer_usd
from monthly
group by 1, 2
order by 1, 2
