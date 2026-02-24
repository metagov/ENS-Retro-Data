-- Silver: Unified address crosswalk
-- Merges addresses from all sources, preferring tally_delegates for ENS names

with tally_addresses as (
    select
        address,
        ens_name,
        'tally' as primary_source
    from {{ ref('clean_tally_delegates') }}
),

snapshot_voter_addresses as (
    select distinct
        voter as address,
        null as ens_name,
        'snapshot' as primary_source
    from {{ ref('clean_snapshot_votes') }}
),

delegation_addresses as (
    select distinct address, null as ens_name, source as primary_source
    from (
        select delegator as address, 'delegation' as source
        from {{ ref('clean_delegations') }}
        union all
        select delegate as address, 'delegation' as source
        from {{ ref('clean_delegations') }}
    )
),

all_addresses as (
    select * from tally_addresses
    union all
    select * from snapshot_voter_addresses
    union all
    select * from delegation_addresses
),

-- Deduplicate, preferring tally (has ens_name) over other sources
ranked as (
    select
        address,
        ens_name,
        primary_source,
        row_number() over (
            partition by address
            order by case primary_source
                when 'tally' then 1
                when 'snapshot' then 2
                when 'delegation' then 3
                else 4
            end
        ) as rn
    from all_addresses
    where address is not null
)

select
    address,
    ens_name,
    primary_source
from ranked
where rn = 1
order by address
