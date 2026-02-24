-- Gold: Per-delegate scorecard
-- Joins delegates with vote counts from both sources, computes participation rate

with delegates as (
    select
        address,
        ens_name,
        voting_power,
        delegators_count,
        votes_count as tally_votes_available
    from {{ ref('clean_tally_delegates') }}
),

snapshot_counts as (
    select
        voter as address,
        count(*) as snapshot_votes_cast
    from {{ ref('clean_snapshot_votes') }}
    group by voter
),

tally_counts as (
    select
        voter as address,
        count(*) as tally_votes_cast
    from {{ ref('clean_tally_votes') }}
    group by voter
),

total_proposals as (
    select
        count(*) filter (where source = 'snapshot') as snapshot_proposals,
        count(*) filter (where source = 'tally') as tally_proposals
    from {{ ref('governance_activity') }}
),

crosswalk as (
    select address, ens_name
    from {{ ref('address_crosswalk') }}
)

select
    d.address,
    coalesce(d.ens_name, cw.ens_name) as ens_name,
    d.voting_power,
    coalesce(sc.snapshot_votes_cast, 0) as snapshot_votes_cast,
    coalesce(tc.tally_votes_cast, 0) as tally_votes_cast,
    d.delegators_count,
    case
        when tp.snapshot_proposals + tp.tally_proposals > 0
        then round(
            (coalesce(sc.snapshot_votes_cast, 0) + coalesce(tc.tally_votes_cast, 0))::double
            / (tp.snapshot_proposals + tp.tally_proposals) * 100, 2
        )
        else 0
    end as participation_rate
from delegates d
left join snapshot_counts sc on d.address = sc.address
left join tally_counts tc on d.address = tc.address
left join crosswalk cw on d.address = cw.address
cross join total_proposals tp
order by d.voting_power desc
