-- Gold: Unified governance activity view
-- Combines Snapshot and Tally proposals with vote percentages

with snapshot as (
    select
        proposal_id,
        'snapshot' as source,
        title,
        status,
        vote_count,
        scores_total,
        start_date,
        end_date
    from {{ ref('clean_snapshot_proposals') }}
),

tally as (
    select
        proposal_id,
        'tally' as source,
        title,
        status,
        (for_votes + against_votes + abstain_votes) as vote_total,
        for_votes,
        against_votes,
        abstain_votes,
        voter_count,
        start_date,
        end_date
    from {{ ref('clean_tally_proposals') }}
),

-- Count votes per Snapshot proposal
snapshot_vote_counts as (
    select
        proposal_id,
        count(*) as voter_count,
        sum(case when vote_choice = 'for' then voting_power else 0 end) as for_power,
        sum(case when vote_choice = 'against' then voting_power else 0 end) as against_power,
        sum(case when vote_choice = 'abstain' then voting_power else 0 end) as abstain_power,
        sum(voting_power) as total_power
    from {{ ref('clean_snapshot_votes') }}
    group by proposal_id
)

select
    s.proposal_id,
    s.source,
    s.title,
    s.status,
    s.vote_count,
    svc.voter_count,
    case when svc.total_power > 0 then round(svc.for_power / svc.total_power * 100, 2) else null end as for_pct,
    case when svc.total_power > 0 then round(svc.against_power / svc.total_power * 100, 2) else null end as against_pct,
    case when svc.total_power > 0 then round(svc.abstain_power / svc.total_power * 100, 2) else null end as abstain_pct,
    s.start_date,
    s.end_date
from snapshot s
left join snapshot_vote_counts svc on s.proposal_id = svc.proposal_id

union all

select
    t.proposal_id,
    t.source,
    t.title,
    t.status,
    null as vote_count,
    t.voter_count,
    case when t.vote_total > 0 then round(t.for_votes / t.vote_total * 100, 2) else null end as for_pct,
    case when t.vote_total > 0 then round(t.against_votes / t.vote_total * 100, 2) else null end as against_pct,
    case when t.vote_total > 0 then round(t.abstain_votes / t.vote_total * 100, 2) else null end as abstain_pct,
    t.start_date,
    t.end_date
from tally t
