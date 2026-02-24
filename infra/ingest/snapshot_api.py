"""Snapshot GraphQL API client for ENS DAO governance data."""

import time

import requests

API_URL = "https://hub.snapshot.org/graphql"
SPACE = "ens.eth"


def run_query(query: str) -> dict:
    """Execute a GraphQL query with rate-limit retry."""
    resp = requests.post(API_URL, json={"query": query}, timeout=30)
    if resp.status_code == 429:
        time.sleep(60)
        return run_query(query)
    resp.raise_for_status()
    return resp.json()


def fetch_snapshot_proposals() -> list[dict]:
    """Fetch all ENS Snapshot proposals.

    Returns raw API objects with fields:
    id, title, body, choices, start, end, snapshot, state, author,
    created, scores, scores_total, votes, quorum, type
    """
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
        if len(data) < batch:
            break
        skip += batch
        time.sleep(1)

    return all_proposals


def fetch_snapshot_votes(proposals: list[dict]) -> list[dict]:
    """Fetch all votes for the given proposals.

    Injects `proposal_id` into each vote record.
    Returns flat list with fields:
    id, voter, choice, vp, created, proposal_id
    """
    all_votes: list[dict] = []

    for proposal in proposals:
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

        time.sleep(1)

    return all_votes
