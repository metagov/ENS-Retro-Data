-- Silver: Tally proposal -> Discourse forum topic crosswalk
--
-- Resolution order (first non-null wins):
--   1. 'field'    - discourse_url populated directly on the Tally proposal
--   2. 'manual'   - override from seeds/manual_tally_discourse_map.csv
--   3. 'unmatched'- no link could be determined
--
-- Invariants (enforced in _silver.yml):
--   * Exactly one row per Tally proposal (1:1 with clean_tally_proposals)
--   * match_source in {'field','manual','unmatched'}
--   * topic_id, when not null, must exist in stg_forum_topics
--
--   clean_tally_proposals ──► field match (regex discourse_url)
--                              │
--                              ├─ miss ──► manual seed override
--                              │            │
--                              │            └─ miss ──► unmatched (NULL topic_id)
--                              ▼
--                         COALESCE

-- Note: sourced from stg_tally_proposals (not clean_tally_proposals) because
-- the silver clean model drops the discourse_url column. Tally data is a
-- frozen sentinel, so reading from staging is safe and keeps the diff minimal.
with tally as (
    select distinct
        proposal_id,
        discourse_url
    from {{ ref('stg_tally_proposals') }}
    where proposal_id is not null
),

field_match as (
    select
        proposal_id,
        {{ extract_discourse_topic_id('discourse_url') }} as topic_id
    from tally
),

manual as (
    select
        cast(proposal_id as varchar) as proposal_id,
        cast(topic_id as bigint)     as topic_id
    from {{ ref('manual_tally_discourse_map') }}
)

select
    t.proposal_id,
    coalesce(f.topic_id, m.topic_id)                as topic_id,
    case
        when f.topic_id is not null then 'field'
        when m.topic_id is not null then 'manual'
        else 'unmatched'
    end                                             as match_source
from tally t
left join field_match f using (proposal_id)
left join manual      m using (proposal_id)
