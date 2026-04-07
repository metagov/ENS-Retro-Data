-- Gold: Unified governance <-> discourse activity
--
-- One row per governance proposal (Tally or Snapshot) joined to its
-- corresponding Discourse forum topic (when a match exists) and to that
-- topic's engagement metrics. Downstream consumers can answer questions
-- like "most-discussed proposals" or "proposals that shipped with no
-- forum debate" without caring which platform the proposal came from.
--
--   tally_discourse_crosswalk   ─┐
--   snapshot_discourse_crosswalk ─┤
--                                 ├──► governance_discourse_activity
--   governance_activity          ─┤     (proposal meta + forum engagement)
--   stg_forum_topics             ─┘
--
-- Grain: (source, proposal_id) — unique. 1:1 with the union of the two
-- crosswalks (156 rows total = 66 Tally + 90 Snapshot).

with crosswalk as (
    select
        'tally' as source,
        proposal_id,
        topic_id,
        match_source
    from {{ ref('tally_discourse_crosswalk') }}

    union all

    select
        'snapshot' as source,
        proposal_id,
        topic_id,
        match_source
    from {{ ref('snapshot_discourse_crosswalk') }}
),

proposal_meta as (
    select
        source,
        proposal_id,
        title           as proposal_title,
        status          as proposal_status,
        start_date      as proposal_start_date,
        end_date        as proposal_end_date
    from {{ ref('governance_activity') }}
),

topics as (
    select
        topic_id,
        title            as topic_title,
        slug             as topic_slug,
        created_at       as topic_created_at,
        posts_count,
        reply_count,
        like_count,
        views
    from {{ ref('stg_forum_topics') }}
)

select
    c.source,
    c.proposal_id,
    p.proposal_title,
    p.proposal_status,
    p.proposal_start_date,
    p.proposal_end_date,
    c.topic_id,
    c.match_source,
    (c.topic_id is not null)                                        as has_forum_discussion,
    t.topic_title,
    t.topic_slug,
    case
        when t.topic_id is not null
            then 'https://discuss.ens.domains/t/' || t.topic_slug || '/' || t.topic_id
    end                                                             as topic_url,
    t.topic_created_at,
    coalesce(t.posts_count, 0)                                      as forum_posts_count,
    coalesce(t.reply_count, 0)                                      as forum_reply_count,
    coalesce(t.like_count, 0)                                       as forum_like_count,
    coalesce(t.views,       0)                                      as forum_views
from crosswalk c
left join proposal_meta p on p.source = c.source and p.proposal_id = c.proposal_id
left join topics        t on t.topic_id = c.topic_id
