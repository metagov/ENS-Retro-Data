"""Discourse API client for ENS Governance Forum.

Fetches all topics and their posts from https://discuss.ens.domains
using the public JSON API. No authentication required.

Endpoints used:
  GET /latest.json?page=N        — paginate through all topics (30/page)
  GET /t/{slug}/{id}.json        — fetch a topic with its first 20 posts
  GET /t/{id}/posts.json?post_ids[] — fetch remaining posts by ID
"""

import logging
import sys
import time

import requests

logger = logging.getLogger(__name__)


def _emit(msg: str) -> None:
    """Print to stdout, stderr, and logger."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)
    logger.info(msg)

BASE_URL = "https://discuss.ens.domains"
TOPICS_PER_PAGE = 30
REQUEST_DELAY = 0.25  # stay well under any rate limits


def _get_json(path: str, params: dict | None = None) -> dict:
    """GET a Discourse JSON endpoint with retry on rate limit."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        _emit(f"[DISCOURSE] Rate limited (429), waiting {retry_after}s before retry...")
        time.sleep(retry_after)
        return _get_json(path, params)
    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        _emit(f"[DISCOURSE] HTTP {resp.status_code} error for {url}: {err_body}")
    resp.raise_for_status()
    return resp.json()


def fetch_all_topics() -> list[dict]:
    """Fetch all topic metadata from /latest.json, paginated.

    Returns list of topic dicts with keys like:
    id, title, slug, posts_count, reply_count, created_at, views,
    like_count, category_id, tags, etc.

    Estimated time: ~30s (~2,400 topics, 30/page, ~80 pages).
    """
    all_topics: list[dict] = []
    page = 0
    start_time = time.time()

    _emit("[DISCOURSE] Starting: fetch_all_topics (est. ~30s for ~2,400 topics)")

    while True:
        data = _get_json("/latest.json", {"page": page})
        topic_list = data.get("topic_list", {})
        topics = topic_list.get("topics", [])

        if not topics:
            break

        all_topics.extend(topics)
        page += 1

        if page % 20 == 0:
            elapsed = time.time() - start_time
            _emit(f"[DISCOURSE] Topics progress: {len(all_topics)} fetched (page {page}, {elapsed:.0f}s elapsed)")

        more = topic_list.get("more_topics_url")
        if not more:
            break

        time.sleep(REQUEST_DELAY)

    _emit(f"[DISCOURSE] Topics complete: {len(all_topics)} total")
    return all_topics


def fetch_topic_posts(topic_id: int, topic_slug: str) -> list[dict]:
    """Fetch all posts for a single topic.

    The topic endpoint returns the first ~20 posts inline plus a stream
    of all post IDs. We batch-fetch any remaining posts via /t/{id}/posts.json.
    """
    try:
        data = _get_json(f"/t/{topic_slug}/{topic_id}.json")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.warning("Topic %d (%s) not found, skipping", topic_id, topic_slug)
            return []
        raise

    post_stream = data.get("post_stream", {})
    posts = post_stream.get("posts", [])
    all_post_ids = post_stream.get("stream", [])

    # IDs we already have from the inline posts
    fetched_ids = {p["id"] for p in posts}
    remaining_ids = [pid for pid in all_post_ids if pid not in fetched_ids]

    # Fetch remaining posts in batches of 20
    batch_size = 20
    for i in range(0, len(remaining_ids), batch_size):
        batch = remaining_ids[i : i + batch_size]
        params = {"post_ids[]": batch}
        try:
            batch_data = _get_json(f"/t/{topic_id}/posts.json", params)
        except requests.HTTPError:
            logger.warning("Failed to fetch post batch for topic %d, skipping batch", topic_id)
            continue
        batch_posts = batch_data.get("post_stream", {}).get("posts", [])
        posts.extend(batch_posts)
        time.sleep(REQUEST_DELAY)

    return posts


def _slim_post(post: dict) -> dict:
    """Extract the fields we care about from a raw Discourse post."""
    return {
        "post_id": post.get("id"),
        "topic_id": post.get("topic_id"),
        "post_number": post.get("post_number"),
        "username": post.get("username"),
        "name": post.get("name"),
        "created_at": post.get("created_at"),
        "updated_at": post.get("updated_at"),
        "cooked": post.get("cooked"),  # HTML body
        "reply_count": post.get("reply_count"),
        "reply_to_post_number": post.get("reply_to_post_number"),
        "like_count": post.get("actions_summary", [{}])[0].get("count", 0)
        if post.get("actions_summary")
        else 0,
        "reads": post.get("reads", 0),
        "score": post.get("score", 0),
        "user_trust_level": post.get("trust_level"),
        "accepted_answer": post.get("accepted_answer", False),
    }


def _slim_topic(topic: dict) -> dict:
    """Extract the fields we care about from a raw Discourse topic."""
    return {
        "topic_id": topic.get("id"),
        "title": topic.get("title"),
        "slug": topic.get("slug"),
        "category_id": topic.get("category_id"),
        "tags": topic.get("tags", []),
        "created_at": topic.get("created_at"),
        "last_posted_at": topic.get("last_posted_at"),
        "posts_count": topic.get("posts_count"),
        "reply_count": topic.get("reply_count"),
        "views": topic.get("views"),
        "like_count": topic.get("like_count"),
        "closed": topic.get("closed"),
        "archived": topic.get("archived"),
        "pinned": topic.get("pinned"),
        "visible": topic.get("visible"),
        "has_accepted_answer": topic.get("has_accepted_answer", False),
    }


def fetch_forum_data() -> tuple[list[dict], list[dict]]:
    """Fetch all topics and all posts from the ENS governance forum.

    Returns (topics, posts) where both are lists of slimmed-down dicts.

    Estimated time: ~15-25 min (~2,400 topics + all their posts).
    """
    raw_topics = fetch_all_topics()
    topics = [_slim_topic(t) for t in raw_topics]

    all_posts: list[dict] = []
    total = len(raw_topics)
    start_time = time.time()

    _emit(f"[DISCOURSE] Starting: fetch posts for {total} topics (est. ~15-25 min)")

    for i, topic in enumerate(raw_topics, 1):
        topic_id = topic["id"]
        topic_slug = topic.get("slug", "")
        posts = fetch_topic_posts(topic_id, topic_slug)
        all_posts.extend([_slim_post(p) for p in posts])

        if i % 100 == 0:
            elapsed = time.time() - start_time
            est_total = elapsed / i * total
            remaining = est_total - elapsed
            _emit(f"[DISCOURSE] Posts progress: topic {i}/{total}, {len(all_posts)} posts so far (~{remaining:.0f}s remaining)")

        time.sleep(REQUEST_DELAY)

    _emit(f"[DISCOURSE] COMPLETE: {len(all_posts)} posts across {total} topics")
    return topics, all_posts
