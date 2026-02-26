-- Staging: ENS Governance Forum posts
-- Reads raw JSON and renames columns to snake_case

select
    id as post_id,
    topic_id,
    author,
    body,
    created_at,
    likes,
    reply_count
from {{ source('bronze_forum', 'forum_posts') }}
