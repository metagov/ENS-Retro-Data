"""Tally GraphQL API client for ENS DAO governance data."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.tally.xyz/query"
ORG_SLUG = "ens"
ENS_TOKEN_DECIMALS = 18

RATE_LIMIT_DELAY = 60
MAX_RETRIES = 10
MIN_REQUEST_INTERVAL = 0.5

_last_request_time = 0.0


def _throttle():
    """Enforce minimum time between API requests to avoid rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def run_query(
    query: str, variables: dict | None, api_key: str, *, _retries: int = MAX_RETRIES
) -> dict:
    """Execute a GraphQL query against Tally with rate-limit retry.

    Uses exponential backoff starting at 60s, doubling each retry up to 10 minutes.
    """
    _throttle()
    logger.debug("[TALLY] Sending GraphQL request to %s", API_URL)
    headers = {"Content-Type": "application/json", "Api-Key": api_key}
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=120)
    except requests.exceptions.Timeout:
        if _retries <= 0:
            raise RuntimeError("[TALLY] Request timed out after max retries")
        logger.warning("[TALLY] Request timed out, retrying in 30s (%d retries left)", _retries)
        time.sleep(30)
        return run_query(query, variables, api_key, _retries=_retries - 1)

    if resp.status_code == 429:
        if _retries <= 0:
            raise RuntimeError("[TALLY] Rate limited after max retries")

        delay = min(RATE_LIMIT_DELAY * (2 ** (MAX_RETRIES - _retries)), 600)
        logger.warning(
            "[TALLY] Rate limited (429), waiting %ds before retry (%d left)...", delay, _retries
        )
        time.sleep(delay)
        return run_query(query, variables, api_key, _retries=_retries - 1)

    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        print(f"[TALLY] HTTP {resp.status_code} error body: {err_body}", flush=True)
        import sys
        print(f"[TALLY] HTTP {resp.status_code} error body: {err_body}", file=sys.stderr, flush=True)
        logger.error("[TALLY] HTTP %d error body: %s", resp.status_code, err_body)
        resp.raise_for_status()
    body = resp.json()
    data = body.get("data", {})
    logger.debug("[TALLY] Received response with keys: %s", list(data.keys()) if data else "empty")
    return data


def fetch_organization(api_key: str) -> dict:
    """Fetch the ENS organization metadata from Tally."""
    logger.info("[TALLY] Fetching organization: %s", ORG_SLUG)
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
    logger.info(
        "[TALLY] ✓ Found org: %s (id=%s, delegates=%s)",
        org.get("name"),
        org.get("id"),
        org.get("delegatesCount"),
    )
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
    logger.info("=" * 60)
    logger.info("[TALLY] Starting: fetch_tally_proposals")
    logger.info("[TALLY] API: %s", API_URL)
    logger.info("[TALLY] Organization ID: %s", org_id)

    all_proposals: list[dict] = []
    cursor: str | None = None
    page_size = 200
    page_num = 0

    while True:
        page_num += 1
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        logger.debug(
            "[TALLY] Fetching proposals page %d (cursor=%s)",
            page_num,
            cursor[:20] if cursor else "none",
        )
        data = run_query(PROPOSALS_QUERY, variables, api_key)
        nodes = data.get("proposals", {}).get("nodes", [])
        page_info = data.get("proposals", {}).get("pageInfo", {})

        if not nodes:
            logger.info("[TALLY] No more proposals (empty page)")
            break

        all_proposals.extend(nodes)
        logger.info(
            "[TALLY] Page %d: got %d proposals (total: %d)",
            page_num,
            len(nodes),
            len(all_proposals),
        )

        cursor = page_info.get("lastCursor")
        if not cursor:
            logger.info("[TALLY] Reached end (no more cursor)")
            break

        time.sleep(1.5)

    logger.info("[TALLY] COMPLETE: Fetched %d total proposals", len(all_proposals))
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


def fetch_tally_votes(proposals: list[dict], api_key: str, *, progress_callback=None) -> list[dict]:
    """Fetch all votes for the given Tally proposals (raw API objects).

    Args:
        proposals: List of proposal dicts with 'id' field
        api_key: Tally API key
        progress_callback: Optional callable(log_message) for real-time progress updates

    Estimated time: 1-4 HOURS due to Tally rate limiting
    """
    _log = progress_callback or logger.info
    _log("=" * 60)
    _log("[TALLY] Starting: fetch_tally_votes")
    _log("[TALLY] API: %s", API_URL)
    _log("[TALLY] Total proposals to fetch votes for: %d", len(proposals))
    _log("[TALLY] WARNING: With rate limiting, expect 1-4 HOURS runtime")

    all_votes: list[dict] = []
    total_proposals = len(proposals)
    start_time = time.time()
    total_rate_limit_retries = 0

    for i, proposal in enumerate(proposals, 1):
        prop_id = proposal["id"]
        cursor: str | None = None
        page_size = 500
        proposal_votes = 0
        proposal_retries = 0

        while True:
            variables: dict = {"proposalId": prop_id, "limit": page_size}
            if cursor:
                variables["afterCursor"] = cursor

            try:
                data = run_query(VOTES_QUERY, variables, api_key)
            except RuntimeError as e:
                if "Rate limited" in str(e):
                    proposal_retries += 1
                    total_rate_limit_retries += 1
                    _log("[TALLY] ⚠ Rate limit on proposal %d, retry %d", i, proposal_retries)
                    if proposal_retries > 5:
                        _log("[TALLY] ✗ Too many retries for proposal %d, skipping...", i)
                        break
                    continue
                raise

            nodes = data.get("votes", {}).get("nodes", [])
            page_info = data.get("votes", {}).get("pageInfo", {})

            if not nodes:
                break
            all_votes.extend(nodes)
            proposal_votes += len(nodes)

            cursor = page_info.get("lastCursor")
            if not cursor:
                break
            time.sleep(1)

        time.sleep(2)

        if i % 5 == 0 or i == total_proposals:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total_proposals - i) / rate if rate > 0 else 0
            _log(
                "[TALLY] Progress: %d/%d proposals (%d votes, %d rate retries) - %.0fs elapsed, ~%.0fs remaining",
                i,
                total_proposals,
                len(all_votes),
                total_rate_limit_retries,
                elapsed,
                eta,
            )

    _log(
        "[TALLY] COMPLETE: Fetched %d total votes for %d proposals (total rate retries: %d)",
        len(all_votes),
        total_proposals,
        total_rate_limit_retries,
    )
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


def fetch_tally_delegates(org_id: str, api_key: str, *, progress_callback=None) -> list[dict]:
    """Fetch all Tally delegates (raw API objects).

    Args:
        org_id: Tally organization ID
        api_key: Tally API key
        progress_callback: Optional callable(log_message) for real-time progress updates

    Estimated time: 2-6 HOURS due to Tally rate limiting (~38k delegates)
    """
    import sys

    def _log(msg, *args):
        formatted = msg % args if args else msg
        if progress_callback:
            progress_callback(formatted)
        else:
            logger.info(formatted)
        print(formatted, flush=True)
        print(formatted, file=sys.stderr, flush=True)

    _log("=" * 60)
    _log("[TALLY] Starting: fetch_tally_delegates")
    _log("[TALLY] API: %s", API_URL)
    _log("[TALLY] Organization ID: %s", org_id)
    _log("[TALLY] WARNING: With rate limiting, expect 2-6 HOURS runtime (~38k delegates)")

    all_delegates: list[dict] = []
    cursor: str | None = None
    page_size = 500
    page_num = 0
    start_time = time.time()
    total_rate_limit_retries = 0

    while True:
        page_num += 1
        variables: dict = {"orgId": org_id, "limit": page_size}
        if cursor:
            variables["afterCursor"] = cursor

        try:
            data = run_query(DELEGATES_QUERY, variables, api_key)
        except RuntimeError as e:
            if "Rate limited" in str(e):
                total_rate_limit_retries += 1
                _log(
                    "[TALLY] ⚠ Rate limit on page %d, retry (total: %d)",
                    page_num,
                    total_rate_limit_retries,
                )
                time.sleep(5)  # Small delay before retry
                continue
            raise

        nodes = data.get("delegates", {}).get("nodes", [])
        page_info = data.get("delegates", {}).get("pageInfo", {})

        if not nodes:
            _log("[TALLY] No more delegates (empty page)")
            break

        all_delegates.extend(nodes)

        if page_num % 5 == 0 or page_num == 1:
            elapsed = time.time() - start_time
            rate = len(all_delegates) / elapsed if elapsed > 0 else 0
            eta = (38000 - len(all_delegates)) / rate if rate > 0 else 0
            _log(
                "[TALLY] Page %d: %d delegates fetched (%.0f/sec, rate_retries=%d, ~%.0fs remaining)",
                page_num,
                len(all_delegates),
                rate,
                total_rate_limit_retries,
                eta,
            )

        cursor = page_info.get("lastCursor")
        if not cursor:
            _log("[TALLY] Reached end (no more cursor)")
            break

        time.sleep(1.5)

    elapsed = time.time() - start_time
    _log(
        "[TALLY] COMPLETE: Fetched %d delegates in %.0fs (total rate retries: %d)",
        len(all_delegates),
        elapsed,
        total_rate_limit_retries,
    )
    return all_delegates


# ---------------------------------------------------------------------------
# Flatteners — convert nested API responses to flat dicts for dbt staging
# ---------------------------------------------------------------------------


def _raw_to_human(raw_value: str | int | None, decimals: int = ENS_TOKEN_DECIMALS) -> str:
    """Convert raw token units to human-readable float string."""
    if raw_value is None:
        return "0"
    try:
        return f"{int(raw_value) / 10**decimals:.4f}"
    except (ValueError, TypeError):
        return str(raw_value)


def flatten_tally_proposals(raw_proposals: list[dict]) -> list[dict]:
    """Flatten nested Tally proposal responses for bronze JSON.

    Output fields: id, onchain_id, title, description, status, eta,
    discourse_url, snapshot_url, proposer, proposer_name, proposer_ens,
    governor_id, governor_name, organization_id, organization_name,
    start_block, start_timestamp, end_block, end_timestamp,
    block_number, block_timestamp, created_block,
    for_votes, against_votes, abstain_votes,
    for_voters, against_voters, abstain_voters,
    for_percent, against_percent, abstain_percent,
    quorum
    """
    result = []
    for p in raw_proposals:
        meta = p.get("metadata") or {}
        proposer = p.get("proposer") or {}
        vs = {s["type"]: s for s in (p.get("voteStats") or [])}
        start = p.get("start") or {}
        end = p.get("end") or {}
        block = p.get("block") or {}

        def get_ts(obj):
            return obj.get("timestamp") if isinstance(obj, dict) else None

        def get_num(obj):
            return obj.get("number") if isinstance(obj, dict) else None

        result.append(
            {
                "id": p.get("id"),
                "onchain_id": p.get("onchainId", ""),
                "title": meta.get("title", ""),
                "description": (meta.get("description") or "")[:5000],
                "status": p.get("status", ""),
                "eta": meta.get("eta", ""),
                "discourse_url": meta.get("discourseURL", ""),
                "snapshot_url": meta.get("snapshotURL", ""),
                "proposer": proposer.get("address", ""),
                "proposer_name": proposer.get("name", ""),
                "proposer_ens": proposer.get("ens", ""),
                "governor_id": p.get("governor", {}).get("id", ""),
                "governor_name": p.get("governor", {}).get("name", ""),
                "organization_id": p.get("organization", {}).get("id", ""),
                "organization_name": p.get("organization", {}).get("name", ""),
                "start_block": get_num(start),
                "start_timestamp": get_ts(start),
                "end_block": get_num(end),
                "end_timestamp": get_ts(end),
                "block_number": get_num(block),
                "block_timestamp": get_ts(block),
                "created_block": get_num(block),
                "for_votes": _raw_to_human(vs.get("for", {}).get("votesCount")),
                "against_votes": _raw_to_human(vs.get("against", {}).get("votesCount")),
                "abstain_votes": _raw_to_human(vs.get("abstain", {}).get("votesCount")),
                "for_voters": vs.get("for", {}).get("votersCount", 0),
                "against_voters": vs.get("against", {}).get("votersCount", 0),
                "abstain_voters": vs.get("abstain", {}).get("votersCount", 0),
                "for_percent": vs.get("for", {}).get("percent"),
                "against_percent": vs.get("against", {}).get("percent"),
                "abstain_percent": vs.get("abstain", {}).get("percent"),
                "quorum": p.get("quorum"),
            }
        )
    return result


def flatten_tally_votes(raw_votes: list[dict]) -> list[dict]:
    """Flatten nested Tally vote responses for bronze JSON.

    Output fields: id, voter, voter_name, voter_ens, support, weight, reason,
    tx_hash, chain_id, proposal_id, block_timestamp, block_number
    """
    result = []
    for v in raw_votes:
        voter = v.get("voter") or {}
        proposal = v.get("proposal") or {}
        block = v.get("block") or {}
        support_map = {"1": "for", "2": "against", "3": "abstain"}
        support = v.get("type", "")
        result.append(
            {
                "id": v.get("id"),
                "voter": voter.get("address", ""),
                "voter_name": voter.get("name", ""),
                "voter_ens": voter.get("ens", ""),
                "support": support_map.get(support, support),
                "weight": v.get("amount", "0"),
                "reason": (v.get("reason") or "")[:500],
                "tx_hash": v.get("txHash", ""),
                "chain_id": v.get("chainId", ""),
                "proposal_id": proposal.get("id", ""),
                "block_timestamp": block.get("timestamp", ""),
                "block_number": block.get("number", ""),
            }
        )
    return result


def flatten_tally_delegates(raw_delegates: list[dict]) -> list[dict]:
    """Flatten nested Tally delegate responses for bronze JSON.

    Output fields: id, address, ens_name, name, twitter, bio, picture, account_type,
    voting_power, delegators_count, is_prioritized, chain_id,
    token_symbol, token_name, statement, statement_summary, is_seeking_delegation,
    organization_id, organization_name,
    participation_rate, voted_proposals_count, proposals_count
    """
    result = []
    for d in raw_delegates:
        acct = d.get("account") or {}
        stmt = d.get("statement") or {}
        token = d.get("token") or {}
        org = d.get("organization") or {}
        part = d.get("participation") or {}
        result.append(
            {
                "id": d.get("id", ""),
                "address": acct.get("address", ""),
                "name": acct.get("name", ""),
                "ens_name": acct.get("ens", ""),
                "twitter": acct.get("twitter", ""),
                "bio": (acct.get("bio") or "")[:500],
                "picture": acct.get("picture", ""),
                "account_type": acct.get("type", ""),
                "voting_power": d.get("votesCount", "0"),
                "delegators_count": d.get("delegatorsCount", 0),
                "is_prioritized": d.get("isPrioritized", False),
                "chain_id": d.get("chainId", ""),
                "token_symbol": token.get("symbol", ""),
                "token_name": token.get("name", ""),
                "statement": (stmt.get("statement") or "")[:2000],
                "statement_summary": (stmt.get("statementSummary") or "")[:1000],
                "is_seeking_delegation": stmt.get("isSeekingDelegation", False),
                "organization_id": org.get("id", ""),
                "organization_name": org.get("name", ""),
                "participation_rate": part.get("participationRate"),
                "voted_proposals_count": part.get("votedProposalsCount"),
                "proposals_count": part.get("proposalsCount"),
            }
        )
    return result
