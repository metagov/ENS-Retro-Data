-- Staging: ENS Governance Forum topics
-- Reads raw JSON and renames columns to snake_case

select
    topic_id,
    title,
    slug,
    category_id,
    created_at,
    last_posted_at,
    posts_count,
    reply_count,
    views,
    like_count,
    closed,
    archived,
    pinned,
    visible,
    has_accepted_answer
from {{ source('bronze_forum', 'forum_topics') }}
