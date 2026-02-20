import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.tally.xyz/query"
API_KEY = os.getenv("TALLY_API_KEY", "")
ORG_SLUG = "ens"
ENS_TOKEN_DECIMALS = 18

if not API_KEY:
    sys.exit("TALLY_API_KEY not set. Copy .env.example to .env and add your key.")

HEADERS = {
    "Content-Type": "application/json",
    "Api-Key": API_KEY,
}


# ---------------------------------------------------------------------------
# GraphQL helpers
# ---------------------------------------------------------------------------

def _dbg(msg, data=None, hyp="", loc=""):
    # #region agent log
    import pathlib; pathlib.Path("/Users/rohitmalekar/work/ens/.cursor").mkdir(parents=True, exist_ok=True)
    with open("/Users/rohitmalekar/work/ens/.cursor/debug.log", "a") as _f:
        _f.write(json.dumps({"timestamp": int(time.time()*1000), "location": loc, "message": msg, "data": data or {}, "hypothesisId": hyp}) + "\n")
    # #endregion

def run_query(query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=60)
    if resp.status_code == 429:
        print("  Rate limited – waiting 60 s …")
        time.sleep(60)
        return run_query(query, variables)
    # #region agent log
    if resp.status_code != 200:
        _dbg("HTTP error response", {"status": resp.status_code, "body": resp.text[:2000], "variables": variables}, hyp="H1,H2,H3", loc="run_query:http_error")
    # #endregion
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        # #region agent log
        _dbg("GraphQL errors in 200 response", {"errors": body["errors"], "variables": variables}, hyp="H1,H2,H3", loc="run_query:gql_errors")
        # #endregion
        print(f"  GraphQL errors: {json.dumps(body['errors'], indent=2)}")
    return body.get("data", {})


def raw_to_human(raw_value: str | int | None, decimals: int = ENS_TOKEN_DECIMALS) -> str:
    """Convert raw token units to human-readable float string."""
    if raw_value is None:
        return "0"
    try:
        return f"{int(raw_value) / 10 ** decimals:.4f}"
    except (ValueError, TypeError):
        return str(raw_value)


# ---------------------------------------------------------------------------
# 1. Resolve ENS organization
# ---------------------------------------------------------------------------

def fetch_organization() -> dict:
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
    data = run_query(query, {"slug": ORG_SLUG})
    org = data.get("organization")
    if not org:
        sys.exit(f"Organization '{ORG_SLUG}' not found on Tally.")
    return org


# ---------------------------------------------------------------------------
# 2. Proposals
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


def fetch_proposals(org_id: str) -> list[dict]:
    all_proposals: list[dict] = []
    cursor: str | None = None
    page_size = 50

    while True:
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        data = run_query(PROPOSALS_QUERY, variables)
        nodes = data.get("proposals", {}).get("nodes", [])
        page_info = data.get("proposals", {}).get("pageInfo", {})

        # #region agent log
        _dbg("proposals page", {"nodes_count": len(nodes), "page_info": page_info, "cursor_sent": cursor, "page_size": page_size}, hyp="H4", loc="fetch_proposals:page")
        # #endregion
        if not nodes:
            break
        all_proposals.extend(nodes)
        print(f"  Fetched {len(all_proposals)} proposals …")

        cursor = page_info.get("lastCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_proposals


# ---------------------------------------------------------------------------
# 3. Votes (per proposal)
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


def fetch_votes(proposal_id: str) -> list[dict]:
    all_votes: list[dict] = []
    cursor: str | None = None
    page_size = 100

    while True:
        variables: dict = {"proposalId": proposal_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        data = run_query(VOTES_QUERY, variables)
        nodes = data.get("votes", {}).get("nodes", [])
        page_info = data.get("votes", {}).get("pageInfo", {})

        if not nodes:
            break
        all_votes.extend(nodes)

        cursor = page_info.get("lastCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_votes


# ---------------------------------------------------------------------------
# 4. Delegates
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


def fetch_delegates(org_id: str) -> list[dict]:
    all_delegates: list[dict] = []
    cursor: str | None = None
    page_size = 50

    while True:
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        data = run_query(DELEGATES_QUERY, variables)
        nodes = data.get("delegates", {}).get("nodes", [])
        page_info = data.get("delegates", {}).get("pageInfo", {})

        if not nodes:
            break
        all_delegates.extend(nodes)
        print(f"  Fetched {len(all_delegates)} delegates …")

        cursor = page_info.get("lastCursor")
        if not cursor:
            break
        time.sleep(1)

    return all_delegates


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def ts_to_iso(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return str(ts)


def write_proposals_csv(proposals: list[dict], path: str = "tally_ens_proposals.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "proposal_id", "onchain_id", "title", "status",
            "proposer_address", "proposer_name", "proposer_ens",
            "governor_id", "governor_name",
            "for_votes", "for_voters", "for_pct",
            "against_votes", "against_voters", "against_pct",
            "abstain_votes", "abstain_voters", "abstain_pct",
            "quorum", "start_time", "end_time",
            "created_block", "created_time",
            "discourse_url", "snapshot_url",
            "description",
        ])
        for p in proposals:
            vs = {s["type"]: s for s in (p.get("voteStats") or [])}
            for_s = vs.get("for", {})
            against_s = vs.get("against", {})
            abstain_s = vs.get("abstain", {})
            proposer = p.get("proposer") or {}
            meta = p.get("metadata") or {}
            gov = p.get("governor") or {}
            block = p.get("block") or {}

            w.writerow([
                p.get("id", ""),
                p.get("onchainId", ""),
                meta.get("title", ""),
                p.get("status", ""),
                proposer.get("address", ""),
                proposer.get("name", ""),
                proposer.get("ens", ""),
                gov.get("id", ""),
                gov.get("name", ""),
                raw_to_human(for_s.get("votesCount")),
                for_s.get("votersCount", ""),
                for_s.get("percent", ""),
                raw_to_human(against_s.get("votesCount")),
                against_s.get("votersCount", ""),
                against_s.get("percent", ""),
                raw_to_human(abstain_s.get("votesCount")),
                abstain_s.get("votersCount", ""),
                abstain_s.get("percent", ""),
                raw_to_human(p.get("quorum")),
                ts_to_iso((p.get("start") or {}).get("timestamp")),
                ts_to_iso((p.get("end") or {}).get("timestamp")),
                block.get("number", ""),
                ts_to_iso(block.get("timestamp")),
                meta.get("discourseURL", ""),
                meta.get("snapshotURL", ""),
                (meta.get("description") or "")[:1000],
            ])
    print(f"Saved {path}")


def write_votes_csv(
    proposals: list[dict],
    all_votes: dict[str, list[dict]],
    path: str = "tally_ens_votes.csv",
):
    title_map = {p["id"]: (p.get("metadata") or {}).get("title", "") for p in proposals}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "proposal_id", "proposal_title",
            "voter_address", "voter_name", "voter_ens",
            "vote_type", "weight", "weight_human",
            "reason", "block_number", "block_time",
        ])
        for prop_id, votes in all_votes.items():
            title = title_map.get(prop_id, "")
            for v in votes:
                voter = v.get("voter") or {}
                block = v.get("block") or {}
                w.writerow([
                    prop_id,
                    title,
                    voter.get("address", ""),
                    voter.get("name", ""),
                    voter.get("ens", ""),
                    v.get("type", ""),
                    v.get("amount", ""),
                    raw_to_human(v.get("amount")),
                    v.get("reason", ""),
                    block.get("number", ""),
                    ts_to_iso(block.get("timestamp")),
                ])
    print(f"Saved {path}")


def write_delegates_csv(delegates: list[dict], path: str = "tally_ens_delegates.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "delegate_id", "address", "name", "ens", "twitter",
            "account_type", "delegators_count",
            "votes_count_raw", "votes_count_human",
            "is_prioritized", "chain_id",
            "is_seeking_delegation", "statement_summary",
            "bio",
        ])
        for d in delegates:
            acct = d.get("account") or {}
            stmt = d.get("statement") or {}
            token = d.get("token") or {}
            decimals = token.get("decimals") or ENS_TOKEN_DECIMALS

            w.writerow([
                d.get("id", ""),
                acct.get("address", ""),
                acct.get("name", ""),
                acct.get("ens", ""),
                acct.get("twitter", ""),
                acct.get("type", ""),
                d.get("delegatorsCount", ""),
                d.get("votesCount", ""),
                raw_to_human(d.get("votesCount"), decimals),
                d.get("isPrioritized", ""),
                d.get("chainId", ""),
                stmt.get("isSeekingDelegation", ""),
                (stmt.get("statementSummary") or "")[:500],
                (acct.get("bio") or "")[:500],
            ])
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Resolving ENS organization on Tally …")
    org = fetch_organization()
    org_id = org["id"]
    print(f"  Organization: {org['name']} (id={org_id})")
    print(f"  Proposals: {org.get('proposalsCount')}, Delegates: {org.get('delegatesCount')}\n")

    # -- Proposals --
    print("Fetching proposals …")
    proposals = fetch_proposals(org_id)
    print(f"  Total proposals: {len(proposals)}\n")
    write_proposals_csv(proposals)

    # -- Votes --
    print("Fetching votes per proposal …")
    all_votes: dict[str, list[dict]] = {}
    total_vote_count = 0
    for i, p in enumerate(proposals, 1):
        title = (p.get("metadata") or {}).get("title", "")[:70]
        print(f"  [{i}/{len(proposals)}] {title}")
        votes = fetch_votes(p["id"])
        all_votes[p["id"]] = votes
        total_vote_count += len(votes)
        time.sleep(1)
    print(f"  Total votes: {total_vote_count}\n")
    write_votes_csv(proposals, all_votes)

    # -- Delegates --
    print("Fetching delegates …")
    delegates = fetch_delegates(org_id)
    print(f"  Total delegates: {len(delegates)}\n")
    write_delegates_csv(delegates)

    print("Done!")


if __name__ == "__main__":
    main()
