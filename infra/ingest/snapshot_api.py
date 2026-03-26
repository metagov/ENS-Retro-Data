"""Snapshot GraphQL API client for ENS DAO governance data."""

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

API_URL = "https://hub.snapshot.org/graphql"
SPACE = "ens.eth"


def run_query(query: str, *, _retries: int = 3) -> dict:
    """Execute a GraphQL query with rate-limit retry."""
    logger.debug("[SNAPSHOT] Sending GraphQL request to %s", API_URL)
    resp = requests.post(API_URL, json={"query": query}, timeout=30)
    if resp.status_code == 429:
        _emit("[SNAPSHOT] Rate limited (429), waiting 60s before retry...")
        time.sleep(60)
        return run_query(query, _retries=_retries)
    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        _emit(f"[SNAPSHOT] HTTP {resp.status_code} error: {err_body}")
    resp.raise_for_status()
    data = resp.json()
    logger.debug("[SNAPSHOT] Received response: %s", str(data)[:200])
    return data


def fetch_snapshot_proposals() -> list[dict]:
    """Fetch all ENS Snapshot proposals.

    Returns raw API objects with fields:
    id, title, body, choices, start, end, snapshot, state, author,
    created, scores, scores_total, votes, quorum, type
    """
    _emit("=" * 60)
    _emit("[SNAPSHOT] Starting: fetch_snapshot_proposals")
    _emit(f"[SNAPSHOT] API: {API_URL}")
    _emit(f"[SNAPSHOT] Space: {SPACE}")

    all_proposals: list[dict] = []
    skip = 0
    batch = 100
    page_num = 0

    while True:
        page_num += 1
        _emit(f"[SNAPSHOT] Fetching proposals batch {page_num} (skip={skip}, limit={batch})")

        query = f"""
        {{
          proposals(
            first: {batch},
            skip: {skip},
            where: {{ space_in: ["{SPACE}"] }},
            orderBy: "created",
            orderDirection: desc
          ) {{
            id
            title
            body
            choices
            start
            end
            snapshot
            state
            author
            created
            scores
            scores_total
            votes
            quorum
            type
          }}
        }}
        """
        data = run_query(query)["data"]["proposals"]

        if not data:
            _emit("[SNAPSHOT] No more proposals (empty response)")
            break

        all_proposals.extend(data)
        _emit(f"[SNAPSHOT] ✓ Got {len(data)} proposals (total so far: {len(all_proposals)})")

        if len(data) < batch:
            _emit(f"[SNAPSHOT] Reached end (got {len(data)} < {batch})")
            break

        skip += batch
        time.sleep(1)

    _emit(f"[SNAPSHOT] COMPLETE: Fetched {len(all_proposals)} total proposals")
    return all_proposals


def fetch_snapshot_votes(proposals: list[dict]) -> list[dict]:
    """Fetch all votes for the given proposals.

    Injects `proposal_id` into each vote record.
    Returns flat list with fields:
    id, voter, choice, vp, created, proposal_id
    """
    _emit("=" * 60)
    _emit("[SNAPSHOT] Starting: fetch_snapshot_votes")
    _emit(f"[SNAPSHOT] API: {API_URL}")
    _emit(f"[SNAPSHOT] Total proposals to fetch votes for: {len(proposals)}")

    all_votes: list[dict] = []
    total_proposals = len(proposals)
    start_time = time.time()

    for i, proposal in enumerate(proposals, 1):
        proposal_id = proposal["id"]
        proposal_title = proposal.get("title", "unknown")[:50]
        skip = 0
        batch = 1000
        page_num = 0

        while True:
            page_num += 1
            query = f"""
            {{
              votes(
                first: {batch},
                skip: {skip},
                where: {{ proposal: "{proposal_id}" }},
                orderBy: "created",
                orderDirection: desc
              ) {{
                id
                voter
                vp
                created
                choice
              }}
            }}
            """
            data = run_query(query)["data"]["votes"]

            if not data:
                break

            for vote in data:
                vote["proposal_id"] = proposal_id
            all_votes.extend(data)

            if len(data) < batch:
                break

            skip += batch
            time.sleep(1)

        time.sleep(1)

        # Progress every 10 proposals
        if i % 10 == 0 or i == total_proposals:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total_proposals - i) / rate if rate > 0 else 0
            _emit(f"[SNAPSHOT] Progress: {i}/{total_proposals} proposals ({len(all_votes)} votes) - {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining")

    _emit(f"[SNAPSHOT] COMPLETE: Fetched {len(all_votes)} total votes for {total_proposals} proposals")
    return all_votes
