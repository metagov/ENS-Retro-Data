-- Silver: Cleaned Snapshot votes
-- Lowercases addresses, maps choice integers to taxonomy values

select distinct
    vote_id,
    {{ lowercase_address('voter') }} as voter,
    proposal_id,
    {{ map_vote_choice_snapshot('choice_index') }} as vote_choice,
    voting_power,
    {{ unix_ts_to_timestamp('created_ts') }} as created_at,
    'snapshot' as source
from {{ ref('stg_snapshot_votes') }}
where vote_id is not null
