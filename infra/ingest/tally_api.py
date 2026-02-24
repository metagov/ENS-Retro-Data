"""Tally GraphQL API client for ENS DAO governance data."""

import time

import requests

API_URL = "https://api.tally.xyz/query"
ORG_SLUG = "ens"
ENS_TOKEN_DECIMALS = 18


def run_query(query: str, variables: dict | None, api_key: str) -> dict:
    """Execute a GraphQL query against Tally with rate-limit retry."""
    headers = {"Content-Type": "application/json", "Api-Key": api_key}
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code == 429:
        time.sleep(60)
        return run_query(query, variables, api_key)
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", {})


def fetch_organization(api_key: str) -> dict:
    """Fetch the ENS organization metadata from Tally."""
    query = """
    query GetOrg($slug: String!) {
      organization(input: { slug: $slug }) {
        id
        name
        slug
        governorIds
        tokenIds
        proposalsCount
        delegatesCount
        delegatesVotesCount
        tokenOwnersCount
      }
    }
    """
    data = run_query(query, {"slug": ORG_SLUG}, api_key)
    org = data.get("organization")
    if not org:
        raise RuntimeError(f"Organization '{ORG_SLUG}' not found on Tally.")
    return org


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

PROPOSALS_QUERY = """
query ListProposals($orgId: IntID!, $limit: Int!, $afterCursor: String) {
  proposals(input: {
    filters: { organizationId: $orgId },
    page: { limit: $limit, afterCursor: $afterCursor },
    sort: { sortBy: id, isDescending: true }
  }) {
    nodes {
      ... on Proposal {
        id
        onchainId
        status
        metadata {
          title
          description
          eta
          discourseURL
          snapshotURL
        }
        proposer {
          address
          name
          ens
        }
        governor {
          id
          name
        }
        organization {
          id
          name
          slug
        }
        voteStats {
          type
          votesCount
          votersCount
          percent
        }
        quorum
        start {
          ... on Block { timestamp number }
          ... on BlocklessTimestamp { timestamp }
        }
        end {
          ... on Block { timestamp number }
          ... on BlocklessTimestamp { timestamp }
        }
        block {
          timestamp
          number
        }
      }
    }
    pageInfo {
      firstCursor
      lastCursor
      count
    }
  }
}
"""


def fetch_tally_proposals(org_id: str, api_key: str) -> list[dict]:
    """Fetch all Tally proposals (raw API objects)."""
    all_proposals: list[dict] = []
    cursor: str | None = None
    page_size = 50

    while True:
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        data = run_query(PROPOSALS_QUERY, variables, api_key)
        nodes = data.get("proposals", {}).get("nodes", [])
        page_info = data.get("proposals", {}).get("pageInfo", {})

        if not nodes:
            break
        all_proposals.extend(nodes)

        cursor = page_info.get("lastCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_proposals


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------

VOTES_QUERY = """
query ListVotes($proposalId: IntID!, $limit: Int!, $afterCursor: String) {
  votes(input: {
    filters: { proposalId: $proposalId },
    page: { limit: $limit, afterCursor: $afterCursor },
    sort: { sortBy: id, isDescending: true }
  }) {
    nodes {
      ... on OnchainVote {
        id
        type
        amount
        reason
        txHash
        chainId
        voter {
          address
          name
          ens
        }
        block {
          timestamp
          number
        }
        proposal {
          id
        }
      }
    }
    pageInfo {
      firstCursor
      lastCursor
      count
    }
  }
}
"""


def fetch_tally_votes(proposals: list[dict], api_key: str) -> list[dict]:
    """Fetch all votes for the given Tally proposals (raw API objects)."""
    all_votes: list[dict] = []

    for proposal in proposals:
        prop_id = proposal["id"]
        cursor: str | None = None
        page_size = 100

        while True:
            variables: dict = {"proposalId": prop_id, "limit": page_size}
            if cursor:
                variables["afterCursor"] = cursor

            data = run_query(VOTES_QUERY, variables, api_key)
            nodes = data.get("votes", {}).get("nodes", [])
            page_info = data.get("votes", {}).get("pageInfo", {})

            if not nodes:
                break
            all_votes.extend(nodes)

            cursor = page_info.get("lastCursor")
            if not cursor:
                break
            time.sleep(1)

        time.sleep(1)

    return all_votes


# ---------------------------------------------------------------------------
# Delegates
# ---------------------------------------------------------------------------

DELEGATES_QUERY = """
query ListDelegates($orgId: IntID!, $limit: Int!, $afterCursor: String) {
  delegates(input: {
    filters: { organizationId: $orgId },
    page: { limit: $limit, afterCursor: $afterCursor },
    sort: { sortBy: votes, isDescending: true }
  }) {
    nodes {
      ... on Delegate {
        id
        delegatorsCount
        votesCount
        isPrioritized
        chainId
        account {
          address
          name
          ens
          twitter
          bio
          picture
          type
        }
        statement {
          statement
          statementSummary
          isSeekingDelegation
        }
        organization {
          id
          name
          slug
        }
        token {
          id
          symbol
          name
          decimals
        }
      }
    }
    pageInfo {
      firstCursor
      lastCursor
      count
    }
  }
}
"""


def fetch_tally_delegates(org_id: str, api_key: str) -> list[dict]:
    """Fetch all Tally delegates (raw API objects)."""
    all_delegates: list[dict] = []
    cursor: str | None = None
    page_size = 50

    while True:
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        data = run_query(DELEGATES_QUERY, variables, api_key)
        nodes = data.get("delegates", {}).get("nodes", [])
        page_info = data.get("delegates", {}).get("pageInfo", {})

        if not nodes:
            break
        all_delegates.extend(nodes)

        cursor = page_info.get("lastCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_delegates


# ---------------------------------------------------------------------------
# Flatteners — convert nested API responses to flat dicts for dbt staging
# ---------------------------------------------------------------------------

def _raw_to_human(raw_value: str | int | None, decimals: int = ENS_TOKEN_DECIMALS) -> str:
    """Convert raw token units to human-readable float string."""
    if raw_value is None:
        return "0"
    try:
        return f"{int(raw_value) / 10 ** decimals:.4f}"
    except (ValueError, TypeError):
        return str(raw_value)


def flatten_tally_proposals(raw_proposals: list[dict]) -> list[dict]:
    """Flatten nested Tally proposal responses for bronze JSON.

    Output fields: id, title, description, status, proposer,
    start_block, end_block, for_votes, against_votes, abstain_votes
    """
    result = []
    for p in raw_proposals:
        meta = p.get("metadata") or {}
        proposer = p.get("proposer") or {}
        vs = {s["type"]: s for s in (p.get("voteStats") or [])}
        start = p.get("start") or {}
        end = p.get("end") or {}

        result.append({
            "id": p.get("id"),
            "title": meta.get("title", ""),
            "description": (meta.get("description") or "")[:2000],
            "status": p.get("status", ""),
            "proposer": proposer.get("address", ""),
            "start_block": start.get("number"),
            "end_block": end.get("number"),
            "for_votes": _raw_to_human(vs.get("for", {}).get("votesCount")),
            "against_votes": _raw_to_human(vs.get("against", {}).get("votesCount")),
            "abstain_votes": _raw_to_human(vs.get("abstain", {}).get("votesCount")),
        })
    return result


def flatten_tally_votes(raw_votes: list[dict]) -> list[dict]:
    """Flatten nested Tally vote responses for bronze JSON.

    Output fields: id, voter, support, weight, proposal_id, reason
    """
    result = []
    for v in raw_votes:
        voter = v.get("voter") or {}
        proposal = v.get("proposal") or {}
        result.append({
            "id": v.get("id"),
            "voter": voter.get("address", ""),
            "support": v.get("type", ""),
            "weight": v.get("amount", "0"),
            "proposal_id": proposal.get("id", ""),
            "reason": v.get("reason", ""),
        })
    return result


def flatten_tally_delegates(raw_delegates: list[dict]) -> list[dict]:
    """Flatten nested Tally delegate responses for bronze JSON.

    Output fields: address, ens_name, voting_power, delegators_count,
    votes_count, proposals_count, statement
    """
    result = []
    for d in raw_delegates:
        acct = d.get("account") or {}
        stmt = d.get("statement") or {}
        result.append({
            "address": acct.get("address", ""),
            "ens_name": acct.get("ens", ""),
            "voting_power": d.get("votesCount", "0"),
            "delegators_count": d.get("delegatorsCount", 0),
            "votes_count": d.get("votesCount", 0),
            "proposals_count": 0,
            "statement": (stmt.get("statementSummary") or "")[:1000],
        })
    return result
