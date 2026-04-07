-- Silver: Tally proposal -> Discourse forum topic crosswalk
--
-- Resolution order (first non-null wins):
--   1. 'field'      - discourse_url populated directly on the Tally proposal
--   2. 'body_regex' - forum URL embedded in proposal body text
--   3. 'manual'     - override from seeds/manual_tally_discourse_map.csv
--   4. 'unmatched'  - no link could be determined
--
-- Invariants (enforced in _silver.yml):
--   * Exactly one row per Tally proposal (1:1 with stg_tally_proposals)
--   * match_source in {'field','body_regex','manual','unmatched'}
--   * topic_id, when not null, must exist in stg_forum_topics

-- Note: sourced from stg_tally_proposals (not clean_tally_proposals) because
-- the silver clean model drops the discourse_url column. Tally data is a
-- frozen sentinel, so reading from staging is safe and keeps the diff minimal.
with tally as (
    select distinct
        proposal_id,
        discourse_url,
        body
    from {{ ref('stg_tally_proposals') }}
    where proposal_id is not null
),

field_match as (
    select
        proposal_id,
        {{ extract_discourse_topic_id('discourse_url') }} as topic_id
    from tally
),

body_match as (
    select
        proposal_id,
        {{ extract_discourse_topic_id('body') }} as topic_id
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
    coalesce(f.topic_id, b.topic_id, m.topic_id)    as topic_id,
    case
        when f.topic_id is not null then 'field'
        when b.topic_id is not null then 'body_regex'
        when m.topic_id is not null then 'manual'
        else 'unmatched'
    end                                             as match_source
from tally t
left join field_match f using (proposal_id)
left join body_match  b using (proposal_id)
left join manual      m using (proposal_id)
