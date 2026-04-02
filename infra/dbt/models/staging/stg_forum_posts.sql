-- Staging: ENS Governance Forum posts
-- Reads raw JSON and renames columns to snake_case

select
    post_id,
    topic_id,
    username as author,
    cooked as body,
    created_at,
    like_count as likes,
    reply_count
from {{ source('bronze_forum', 'forum_posts') }}
