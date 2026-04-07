-- Silver: Snapshot proposal -> Discourse forum topic crosswalk
--
-- Snapshot proposals (unlike Tally) do not carry a structured discussion URL.
-- The convention in ENS governance is to paste the forum link inside the
-- proposal body. We regex-extract the first discuss.ens.domains/t/.../<id>
-- URL from the body text; rows that don't match fall through to a manual
-- seed override, and anything still unresolved is emitted as 'unmatched'.
--
-- Resolution order (first non-null wins):
--   1. 'body_regex' - parsed out of clean_snapshot_proposals.body
--   2. 'manual'     - override from seeds/manual_snapshot_discourse_map.csv
--   3. 'unmatched'  - no link could be determined
--
-- Invariants (enforced in _silver.yml):
--   * Exactly one row per Snapshot proposal (1:1 with clean_snapshot_proposals)
--   * match_source in {'body_regex','manual','unmatched'}
--   * topic_id, when not null, must exist in stg_forum_topics

with snapshot as (
    select
        proposal_id,
        body
    from {{ ref('clean_snapshot_proposals') }}
),

regex_match as (
    select
        proposal_id,
        {{ extract_discourse_topic_id('body') }} as topic_id
    from snapshot
),

manual as (
    select
        cast(proposal_id as varchar) as proposal_id,
        cast(topic_id as bigint)     as topic_id
    from {{ ref('manual_snapshot_discourse_map') }}
)

select
    s.proposal_id,
    coalesce(r.topic_id, m.topic_id)                as topic_id,
    case
        when r.topic_id is not null then 'body_regex'
        when m.topic_id is not null then 'manual'
        else 'unmatched'
    end                                             as match_source
from snapshot s
left join regex_match r using (proposal_id)
left join manual      m using (proposal_id)
