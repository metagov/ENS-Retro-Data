-- Silver: Cleaned ENS Foundation ledger
-- Adds flow_type (inflow / outflow / internal) based on source_entity.
--   inflow   = external revenue entering the treasury (Registrar, CoW Swap, etc.)
--   internal = DAO Wallet budget allocations to working groups
--   outflow  = working group spending to individuals, grants, and contractors

select distinct
    tx_hash,
    tx_date,
    quarter,
    lower(source_entity) as source_entity,
    lower(destination)   as destination,
    lower(category)      as category,
    amount,
    upper(asset)         as asset,
    value_usd,
    case
        when lower(source_entity) in ('registrar', 'cow swap', 'uniswap', 'endowment')
            then 'inflow'
        when lower(source_entity) = 'dao wallet'
            then 'internal'
        else 'outflow'
    end as flow_type
from {{ ref('stg_ens_ledger') }}
where tx_hash is not null
  and value_usd is not null
