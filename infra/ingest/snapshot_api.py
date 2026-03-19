"""Snapshot GraphQL API client for ENS DAO governance data."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

API_URL = "https://hub.snapshot.org/graphql"
SPACE = "ens.eth"


def run_query(query: str, *, _retries: int = 3) -> dict:
    """Execute a GraphQL query with rate-limit retry."""
    logger.debug("[SNAPSHOT] Sending GraphQL request to %s", API_URL)
    resp = requests.post(API_URL, json={"query": query}, timeout=30)
    if resp.status_code == 429:
        logger.warning("[SNAPSHOT] Rate limited (429), waiting 60s before retry...")
        time.sleep(60)
        return run_query(query, _retries=_retries)
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
    logger.info("=" * 60)
    logger.info("[SNAPSHOT] Starting: fetch_snapshot_proposals")
    logger.info("[SNAPSHOT] API: %s", API_URL)
    logger.info("[SNAPSHOT] Space: %s", SPACE)

    all_proposals: list[dict] = []
    skip = 0
    batch = 100
    page_num = 0

    while True:
        page_num += 1
        logger.info(
            "[SNAPSHOT] Fetching proposals batch %d (skip=%d, limit=%d)", page_num, skip, batch
        )

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
            logger.info("[SNAPSHOT] No more proposals (empty response)")
            break

        all_proposals.extend(data)
        logger.info(
            "[SNAPSHOT] ✓ Got %d proposals (total so far: %d)", len(data), len(all_proposals)
        )

        if len(data) < batch:
            logger.info("[SNAPSHOT] Reached end (got %d < %d)", len(data), batch)
            break

        skip += batch
        time.sleep(1)

    logger.info("[SNAPSHOT] COMPLETE: Fetched %d total proposals", len(all_proposals))
    return all_proposals


def fetch_snapshot_votes(proposals: list[dict]) -> list[dict]:
    """Fetch all votes for the given proposals.

    Injects `proposal_id` into each vote record.
    Returns flat list with fields:
    id, voter, choice, vp, created, proposal_id
    """
    logger.info("=" * 60)
    logger.info("[SNAPSHOT] Starting: fetch_snapshot_votes")
    logger.info("[SNAPSHOT] API: %s", API_URL)
    logger.info("[SNAPSHOT] Total proposals to fetch votes for: %d", len(proposals))

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
            logger.info(
                "[SNAPSHOT] Progress: %d/%d proposals (%d votes) - %.0fs elapsed, ~%.0fs remaining",
                i,
                total_proposals,
                len(all_votes),
                elapsed,
                eta,
            )

    logger.info(
        "[SNAPSHOT] COMPLETE: Fetched %d total votes for %d proposals",
        len(all_votes),
        total_proposals,
    )
    return all_votes
