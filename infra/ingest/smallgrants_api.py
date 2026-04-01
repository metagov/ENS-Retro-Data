"""Snapshot GraphQL API client for ENS Small Grants data.

Fetches proposals and votes from the small-grants.eth Snapshot space.
"""

import logging
import sys
import time

import requests

logger = logging.getLogger(__name__)

API_URL = "https://hub.snapshot.org/graphql"
SPACE = "small-grants.eth"


def _emit(msg: str) -> None:
    """Print to stdout, stderr, and logger."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)
    logger.info(msg)


def run_query(query: str) -> dict:
    """Execute a GraphQL query with rate-limit retry."""
    resp = requests.post(API_URL, json={"query": query}, timeout=30)
    if resp.status_code == 429:
        _emit("[SMALLGRANTS] Rate limited (429), waiting 60s before retry...")
        time.sleep(60)
        return run_query(query)
    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        _emit(f"[SMALLGRANTS] HTTP {resp.status_code} error: {err_body}")
    resp.raise_for_status()
    return resp.json()


def fetch_smallgrants_proposals() -> list[dict]:
    """Fetch all ENS Small Grants proposals from Snapshot.

    Returns raw API objects with fields:
    id, title, body, choices, start, end, snapshot, state, author,
    created, scores, scores_total, votes, quorum, type
    """
    _emit(f"[SMALLGRANTS] Starting: fetch_smallgrants_proposals (space={SPACE})")
    all_proposals: list[dict] = []
    skip = 0
    batch = 100

    while True:
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
            break
        all_proposals.extend(data)
        _emit(f"[SMALLGRANTS] Fetched batch (skip={skip}): {len(data)} proposals (total: {len(all_proposals)})")
        if len(data) < batch:
            break
        skip += batch
        time.sleep(1)

    _emit(f"[SMALLGRANTS] COMPLETE: {len(all_proposals)} proposals fetched")
    return all_proposals


def fetch_smallgrants_votes(proposals: list[dict]) -> list[dict]:
    """Fetch all votes for the given small grants proposals.

    Injects `proposal_id` into each vote record.
    Returns flat list with fields:
    id, voter, choice, vp, created, proposal_id
    """
    _emit(f"[SMALLGRANTS] Starting: fetch_smallgrants_votes ({len(proposals)} proposals)")
    all_votes: list[dict] = []

    for i, proposal in enumerate(proposals, 1):
        proposal_id = proposal["id"]
        skip = 0
        batch = 1000

        while True:
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

        if i % 10 == 0 or i == len(proposals):
            _emit(f"[SMALLGRANTS] Votes progress: {i}/{len(proposals)} proposals, {len(all_votes)} votes total")
        time.sleep(1)

    _emit(f"[SMALLGRANTS] COMPLETE: {len(all_votes)} votes fetched")
    return all_votes
