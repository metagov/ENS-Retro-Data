"""
Bronze layer assets — API ingestion and sentinel checks.

DATA FLOW ARCHITECTURE:
======================
This module defines Dagster assets that form the BRONZE (raw) layer of our
medallion architecture. The flow is:

    External APIs (Snapshot, Tally, Etherscan, Discourse, Safe)
         ↓
    Dagster Assets (this file) — fetch & flatten data
         ↓
    Bronze/ JSON files on disk (immutable raw data)
         ↓
    dbt (reads bronze files, transforms to silver/gold)
         ↓
    DuckDB warehouse (queryable analytics data)

ASSET GROUPS:
=============
- bronze: All data ingestion assets
- Each asset has compute_kind="api" (API calls) or "file" (sentinel checks)
- Dependencies (deps=[]) define execution order

METADATA TRACKING:
==================
Every write to bronze/ updates metadata.json with:
- last_indexed_at: When data was collected
- provenance: source API, collection method, record count
- collection_status: "in_progress" or "complete"

OUTPUT FILES:
=============
- bronze/governance/: Snapshot & Tally proposals, votes, delegates
- bronze/on-chain/: Etherscan events (delegations, transfers, treasury)
- bronze/grants/: Snapshot Small Grants proposals & votes
- bronze/forum/: Discourse topics & posts
- bronze/financial/: Safe wallet balances & transactions
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from dagster import AssetExecutionContext, asset

from infra.ingest.discourse_api import fetch_forum_data
from infra.ingest.etherscan_api import (
    fetch_delegation_events,
    fetch_token_transfers,
    fetch_treasury_transactions,
)
from infra.ingest.safe_api import fetch_all_balances, fetch_all_safe_transactions
from infra.ingest.smallgrants_api import (
    fetch_smallgrants_proposals,
    fetch_smallgrants_votes,
)
from infra.ingest.snapshot_api import fetch_snapshot_proposals, fetch_snapshot_votes
from infra.ingest.tally_api import (
    fetch_organization,
    fetch_tally_delegates,
    fetch_tally_proposals,
    fetch_tally_votes,
    flatten_tally_delegates,
    flatten_tally_proposals,
    flatten_tally_votes,
)
from infra.resources import EtherscanApiConfig, TallyApiConfig

# Root directory for all bronze-layer data files
BRONZE_ROOT = Path(__file__).resolve().parent.parent.parent / "bronze"


def _update_metadata(
    subdir: str,
    filename: str,
    *,
    status: str,
    records: int | None = None,
    file_size: int | None = None,
    source: str = "dagster_pipeline",
    method: str | None = None,
):
    """Update bronze/{subdir}/metadata.json with provenance and freshness info.

    This enables tracking which data was collected when and from where,
    supporting data lineage and freshness monitoring in Dagster.
    """
    meta_path = BRONZE_ROOT / subdir / "metadata.json"
    if not meta_path.exists():
        return
    with open(meta_path) as f:
        meta = json.load(f)

    now = datetime.now(timezone.utc).isoformat()
    meta["last_indexed_at"] = now

    file_entry = meta.get("files", {}).get(filename)
    if file_entry is None:
        return

    file_entry["status"] = status
    if records is not None:
        file_entry["actual_records"] = records
    if file_size is not None:
        file_entry["file_size_bytes"] = file_size

    prov = file_entry.get("provenance") or {}
    prov["collected_by"] = source
    prov["collected_at"] = now
    if records is not None:
        prov["records"] = records
    if method:
        prov["query_or_method"] = method
    file_entry["provenance"] = prov

    # Aggregate collection_status based on how many files are present
    # This helps track overall pipeline health at a glance
    files = meta.get("files", {})
    present = sum(1 for f in files.values() if f.get("status") == "present")
    if present == len(files):
        meta["collection_status"] = "complete"
    elif present > 0:
        meta["collection_status"] = "in_progress"

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def _write_json(
    data: list[dict],
    subdir: str,
    filename: str,
    context: AssetExecutionContext,
    *,
    source: str = "dagster_pipeline",
    method: str | None = None,
):
    """Write API response to bronze/{subdir}/{filename}.json and track metadata.

    This is the main write function used by all API-based assets.
    It:
    1. Creates parent directories if needed
    2. Writes data as formatted JSON (default=str handles datetime, etc.)
    3. Logs record count and file size for observability
    4. Updates metadata.json with provenance info
    """
    path = BRONZE_ROOT / subdir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    file_size = path.stat().st_size
    context.log.info(f"Wrote {len(data)} records to {path} ({file_size:,} bytes)")

    _update_metadata(
        subdir,
        filename,
        status="present",
        records=len(data),
        file_size=file_size,
        source=source,
        method=method,
    )


def _check_file_exists(subdir: str, filename: str, context: AssetExecutionContext):
    """Verify manually-placed files exist and update metadata accordingly.

    Some data sources (votingpower.xyz, ens-ledger.app) are not yet
    automated via API. These sentinel assets:
    1. Check if the file exists on disk
    2. Log a warning if missing
    3. Update metadata to track availability

    Run文化建设 (data culture) to ensure these files are placed before analysis.
    """
    path = BRONZE_ROOT / subdir / filename
    if path.exists():
        file_size = path.stat().st_size
        context.log.info(f"Found {path} ({file_size:,} bytes)")
        _update_metadata(
            subdir,
            filename,
            status="present",
            file_size=file_size,
            source="manual_upload",
            method="sentinel check — file already on disk",
        )
    else:
        context.log.warning(f"Missing {path} — place file manually")
        _update_metadata(subdir, filename, status="missing")


# ============================================================================
# SNAPSHOT.GOV — Off-chain voting data
# Snapshot hosts ENS DAO's off-chain voting (temperature check / discourse)
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def snapshot_proposals(context: AssetExecutionContext) -> None:
    """Fetch all ENS governance proposals from Snapshot.org.

    DATA: Off-chain proposals used for community sentiment before on-chain votes.
    API: Snapshot GraphQL (space: ens.eth)
    OUTPUT: bronze/governance/snapshot_proposals.json

    DEPENDENCIES: None — fetches all proposals directly
    ESTIMATED: ~30s for ~90 proposals
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: snapshot_proposals")
    context.log.info("[BRONZE] Source: snapshot.org (space: ens.eth)")
    context.log.info("[BRONZE] Output: bronze/governance/snapshot_proposals.json")
    context.log.info("[BRONZE] Fetching all ENS governance proposals from Snapshot...")

    proposals = fetch_snapshot_proposals()

    context.log.info(f"[BRONZE] ✓ Received {len(proposals)} proposals from Snapshot")

    # Write to bronze layer — dbt will read this file in the silver/gold transforms
    _write_json(
        proposals,
        "governance",
        "snapshot_proposals.json",
        context,
        source="snapshot.org",
        method="GraphQL paginated query (space=ens.eth)",
    )

    context.log.info(f"[BRONZE] ✓ snapshot_proposals COMPLETE - {len(proposals)} records written")


@asset(group_name="bronze", compute_kind="api", deps=["snapshot_proposals"])
def snapshot_votes(context: AssetExecutionContext) -> None:
    """Fetch all votes cast on Snapshot ENS proposals.

    DATA: Individual vote records (voter, choice, vp, timestamp)
    API: Snapshot GraphQL — queries each proposal by ID
    OUTPUT: bronze/governance/snapshot_votes.json

    DEPENDENCIES: snapshot_proposals (reads proposal IDs from disk)
    ESTIMATED: ~3-5 min for ~47k votes across ~90 proposals

    FLOW: Reads proposal IDs from bronze/governance/snapshot_proposals.json
          → loops through each, fetching votes via GraphQL
          → writes combined vote records to disk
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: snapshot_votes (depends on snapshot_proposals)")
    context.log.info("[BRONZE] Source: snapshot.org GraphQL API")
    context.log.info("[BRONZE] Output: bronze/governance/snapshot_votes.json")

    # DAGSTER PATTERN: Reading output from a dependent asset
    # The deps=["snapshot_proposals"] ensures this runs AFTER snapshot_proposals
    # We read from disk because the output was already written as JSON
    proposals_path = BRONZE_ROOT / "governance" / "snapshot_proposals.json"
    with open(proposals_path) as f:
        proposals = json.load(f)

    context.log.info(f"[BRONZE] Found {len(proposals)} proposals from previous asset")
    context.log.info(
        "[BRONZE] Now fetching votes for each proposal (this may take a few minutes)..."
    )

    votes = fetch_snapshot_votes(proposals)

    context.log.info(f"[BRONZE] ✓ Received {len(votes)} total votes from Snapshot")

    _write_json(
        votes,
        "governance",
        "snapshot_votes.json",
        context,
        source="snapshot.org",
        method="GraphQL paginated query per proposal",
    )

    context.log.info(f"[BRONZE] ✓ snapshot_votes COMPLETE - {len(votes)} records written")


# ============================================================================
# TALLY.XYZ — On-chain governance data
# Tally indexes ENS Governor contract events and provides enriched data
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def tally_proposals(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch ENS governance proposals from Tally (on-chain).

    DATA: On-chain proposals with vote stats, quorum, proposer info
    API: Tally GraphQL (organization: ens)
    OUTPUT: bronze/governance/tally_proposals.json

    DEPENDENCIES: None — fetches all proposals directly
    ESTIMATED: ~15s for ~62 proposals

    NOTE: We first fetch the org ID (required for GraphQL queries),
          then use it to paginate through all proposals.
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: tally_proposals")
    context.log.info("[BRONZE] Source: tally.xyz GraphQL API")
    context.log.info("[BRONZE] Output: bronze/governance/tally_proposals.json")

    # Tally requires org_id from the organization query before listing proposals
    context.log.info("[BRONZE] Fetching ENS organization from Tally...")
    org = fetch_organization(tally_config.api_key)
    org_id = org["id"]
    context.log.info(f"[BRONZE] ✓ Connected to Tally org: {org['name']} (id={org_id})")

    # Fetch raw proposals from Tally (nested GraphQL response)
    context.log.info("[BRONZE] Fetching proposals with vote stats, quorum, proposer info...")
    raw = fetch_tally_proposals(org_id, tally_config.api_key)

    # Flatten nested structure for easier dbt processing
    # Transforms: {proposal { voteStats { type, votesCount } }}
    # Into: { for_votes, against_votes, abstain_votes, for_percent, etc. }
    context.log.info("[BRONZE] Flattening nested GraphQL response...")
    proposals = flatten_tally_proposals(raw)
    context.log.info(f"[BRONZE] ✓ Flattened {len(proposals)} tally proposals")

    _write_json(
        proposals,
        "governance",
        "tally_proposals.json",
        context,
        source="tally.xyz",
        method="GraphQL paginated query (org=ens), flattened",
    )

    context.log.info(f"[BRONZE] ✓ tally_proposals COMPLETE - {len(proposals)} records written")


@asset(group_name="bronze", compute_kind="api", deps=["tally_proposals"])
def tally_votes(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch all on-chain votes cast on Tally/ENS proposals.

    DATA: Individual vote records (voter, support, weight, tx_hash)
    API: Tally GraphQL — queries each proposal by ID
    OUTPUT: bronze/governance/tally_votes.json

    DEPENDENCIES: tally_proposals (reads proposal IDs from disk)
    ESTIMATED: ~2-4 min for ~9.5k votes across ~62 proposals

    FLOW: Reads proposal IDs from bronze/governance/tally_proposals.json
          → loops through each, fetching paginated votes
          → flattens nested voter/proposal/block data
          → writes combined vote records to disk
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: tally_votes (depends on tally_proposals)")
    context.log.info("[BRONZE] Source: tally.xyz GraphQL API")
    context.log.info("[BRONZE] Output: bronze/governance/tally_votes.json")

    proposals_path = BRONZE_ROOT / "governance" / "tally_proposals.json"
    with open(proposals_path) as f:
        flat_proposals = json.load(f)

    context.log.info(f"[BRONZE] Found {len(flat_proposals)} proposals from previous asset")
    context.log.info(f"[BRONZE] Fetching on-chain votes for {len(flat_proposals)} proposals...")
    context.log.info(
        "[BRONZE] WARNING: With Tally rate limiting (429 errors), this may take 1-4 HOURS"
    )
    context.log.info(
        "[BRONZE] Rate limiting is handled with exponential backoff (60s-10min delays)"
    )
    context.log.info("[BRONZE] Progress will be logged every 5 proposals")

    # Fetch raw votes with progress callback for Dagster console
    raw_votes = fetch_tally_votes(
        flat_proposals, tally_config.api_key, progress_callback=context.log.info
    )
    context.log.info(f"[BRONZE] ✓ Received {len(raw_votes)} raw vote records")

    # Flatten: { voter { address, name, ens }, block { timestamp, number } }
    # Into: { voter, voter_name, voter_ens, block_timestamp, block_number }
    context.log.info("[BRONZE] Flattening nested voter/proposal/block data...")
    votes = flatten_tally_votes(raw_votes)
    context.log.info(f"[BRONZE] ✓ Flattened to {len(votes)} vote records")

    _write_json(
        votes,
        "governance",
        "tally_votes.json",
        context,
        source="tally.xyz",
        method="GraphQL paginated query per proposal, flattened",
    )

    context.log.info(f"[BRONZE] ✓ tally_votes COMPLETE - {len(votes)} records written")


@asset(group_name="bronze", compute_kind="api")
def tally_delegates(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch all ENS token delegates from Tally.

    DATA: Delegate profiles with voting power, delegators, statements
    API: Tally GraphQL (sorted by votes descending)
    OUTPUT: bronze/governance/tally_delegates.json

    DEPENDENCIES: None — fetches all delegates directly
    ESTIMATED: ~2-3 min for ~38k delegates (500/page, ~76 pages)

    NOTE: Results are sorted by voting power (highest first), useful for
          identifying top delegates in the gold layer scorecard.
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: tally_delegates")
    context.log.info("[BRONZE] Source: tally.xyz GraphQL API")
    context.log.info("[BRONZE] Output: bronze/governance/tally_delegates.json")

    context.log.info("[BRONZE] Fetching ENS organization from Tally...")
    org = fetch_organization(tally_config.api_key)
    org_id = org["id"]
    context.log.info(f"[BRONZE] ✓ Connected to Tally org: {org['name']} (id={org_id})")

    # Fetch all delegates — paginates through 500 at a time
    # Sort by voting power to surface top delegates first
    context.log.info("[BRONZE] Fetching all ENS delegates (sorted by voting power)...")
    context.log.info(
        "[BRONZE] WARNING: With Tally rate limiting (429 errors), this may take 2-6 HOURS"
    )
    context.log.info("[BRONZE] ~38k delegates at 500/page with rate limiting delays")
    context.log.info("[BRONZE] Progress will be logged every 5 pages")

    # Fetch delegates with progress callback for Dagster console
    raw = fetch_tally_delegates(org_id, tally_config.api_key, progress_callback=context.log.info)
    context.log.info(f"[BRONZE] ✓ Received {len(raw)} raw delegate records")

    # Flatten nested account/statement/token objects
    # Extracts: twitter, bio, picture, statement, token info, org info
    context.log.info("[BRONZE] Flattening nested account/statement/token data...")
    delegates = flatten_tally_delegates(raw)
    context.log.info(f"[BRONZE] ✓ Flattened to {len(delegates)} delegate profiles")

    _write_json(
        delegates,
        "governance",
        "tally_delegates.json",
        context,
        source="tally.xyz",
        method="GraphQL paginated query (org=ens, sorted by votes), flattened",
    )

    context.log.info(f"[BRONZE] ✓ tally_delegates COMPLETE - {len(delegates)} records written")


# ============================================================================
# SENTINEL ASSETS — Manually placed data files
# These check for files that haven't been automated yet
# ============================================================================


@asset(group_name="bronze", compute_kind="file")
def votingpower_delegates(context: AssetExecutionContext) -> None:
    """Sentinel check for votingpower.xyz delegate snapshot.

    SOURCE: Manually downloaded from votingpower.xyz (no public API)
    PATH: bronze/governance/votingpower-xyz/ens-delegates-2026-02-20.csv

    ACTION REQUIRED: Download CSV from votingpower.xyz and place in bronze/
    """
    _check_file_exists("governance", "votingpower-xyz/ens-delegates-2026-02-20.csv", context)


@asset(group_name="bronze", compute_kind="file")
def ens_ledger_transactions(context: AssetExecutionContext) -> None:
    """Sentinel check for ENS DAO ledger transactions.

    SOURCE: ENS Foundation via 0xLighthouse (ens-ledger.app)
    PATH: bronze/financial/ens_ledger_transactions.csv

    ACTION REQUIRED: Request access to ens-ledger.app and download CSV
    """
    _check_file_exists("financial", "ens_ledger_transactions.csv", context)


# ============================================================================
# ETHERSCAN — On-chain ENS token events
# Raw event logs from the ENS token contract on Ethereum mainnet
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def delegations(
    context: AssetExecutionContext,
    etherscan_config: EtherscanApiConfig,
) -> None:
    """Fetch all DelegateChanged events from the ENS token contract.

    DATA: Historical record of every token delegation change
    API: Etherscan Logs API (module=logs, action=getLogs)
    OUTPUT: bronze/on-chain/delegations.json

    DEPENDENCIES: None — fetches all events directly
    ESTIMATED: ~5-10 min (860k+ events, uses checkpointing for resume)

    USE CASE: Track delegation history over time, identify delegate changes,
              compute time-weighted voting power for retrospectives.

    NOTE: Uses checkpointing — if interrupted, resumes from last block.
          Checkpoint file: .cache/delegations_checkpoint.json
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: delegations (ON-CHAIN)")
    context.log.info("[BRONZE] Source: Etherscan Logs API")
    context.log.info("[BRONZE] Output: bronze/on-chain/delegations.json")
    context.log.info("[BRONZE] Contract: ENS Token (0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72)")
    context.log.info("[BRONZE] Fetching DelegateChanged events...")
    context.log.info("[BRONZE] This may take 5-10 minutes (860k+ events)")
    context.log.info("[BRONZE] Using checkpointing for resume capability")

    events = fetch_delegation_events(etherscan_config.api_key)
    context.log.info(f"[BRONZE] ✓ Received {len(events)} delegation change events")

    _write_json(
        events,
        "on-chain",
        "delegations.json",
        context,
        source="etherscan.io",
        method="Event logs API (DelegateChanged on ENS token contract)",
    )

    context.log.info(f"[BRONZE] ✓ delegations COMPLETE - {len(events)} records written")


@asset(group_name="bronze", compute_kind="api")
def token_distribution(
    context: AssetExecutionContext,
    etherscan_config: EtherscanApiConfig,
) -> None:
    """Compute ENS token holder distribution from Transfer events.

    DATA: Current ENS token balances for all addresses
    API: Etherscan Logs API (Transfer events) + client-side balance computation
    OUTPUT: bronze/on-chain/token_distribution.json

    DEPENDENCIES: None — replays all Transfer events
    ESTIMATED: ~10-20 min (millions of Transfer events, checkpointed)

    ALGORITHM:
    1. Fetch all Transfer event logs from ENS token contract
    2. For each transfer: subtract from "from", add to "to"
    3. Final balances = current holder distribution
    4. Filter to only addresses with positive balance

    NOTE: This is computationally expensive — uses checkpointing to resume.
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: token_distribution (ON-CHAIN)")
    context.log.info("[BRONZE] Source: Etherscan Logs API")
    context.log.info("[BRONZE] Output: bronze/on-chain/token_distribution.json")
    context.log.info("[BRONZE] Computing ENS token distribution...")
    context.log.info("[BRONZE] Algorithm: Replay all Transfer events to compute balances")
    context.log.info("[BRONZE] This may take 10-20 minutes (millions of events)")
    context.log.info("[BRONZE] Using checkpointing for resume capability")

    distribution = fetch_token_transfers(etherscan_config.api_key)
    context.log.info(
        f"[BRONZE] ✓ Computed balances for {len(distribution)} holders with positive balance"
    )

    _write_json(
        distribution,
        "on-chain",
        "token_distribution.json",
        context,
        source="etherscan.io",
        method="Event logs API (Transfer events, client-side balance computation)",
    )

    context.log.info(
        f"[BRONZE] ✓ token_distribution COMPLETE - {len(distribution)} records written"
    )


@asset(group_name="bronze", compute_kind="api")
def treasury_flows(
    context: AssetExecutionContext,
    etherscan_config: EtherscanApiConfig,
) -> None:
    """Fetch all transactions for ENS DAO treasury wallets.

    DATA: ETH and ERC-20 transfers involving ENS DAO wallets
    API: Etherscan Account APIs (txlist, tokentx for known wallets)
    OUTPUT: bronze/on-chain/treasury_flows.json

    DEPENDENCIES: None — queries configured wallet addresses
    ESTIMATED: ~3-5 min

    DAO WALLETS TRACKED:
    - ENS DAO Multisig (Safe)
    - ENS Grants Multisig
    - ENS.eth (ENS main treasury)
    See: infra/ingest/etherscan_api.py for full list
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: treasury_flows (ON-CHAIN)")
    context.log.info("[BRONZE] Source: Etherscan Account APIs")
    context.log.info("[BRONZE] Output: bronze/on-chain/treasury_flows.json")
    context.log.info("[BRONZE] Fetching ETH + ERC-20 transactions for ENS DAO wallets...")

    flows = fetch_treasury_transactions(etherscan_config.api_key)
    context.log.info(f"[BRONZE] ✓ Received {len(flows)} treasury transaction records")

    _write_json(
        flows,
        "on-chain",
        "treasury_flows.json",
        context,
        source="etherscan.io",
        method="Account txlist + tokentx APIs for ENS DAO wallets",
    )

    context.log.info(f"[BRONZE] ✓ treasury_flows COMPLETE - {len(flows)} records written")


# ============================================================================
# SNAPSHOT SMALL GRANTS — ENS community funding proposals
# Separate space for micro-grants (< $5k)
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def smallgrants_proposals(context: AssetExecutionContext) -> None:
    """Fetch ENS Small Grants proposals from Snapshot.

    DATA: Off-chain funding proposals (space: small-grants.eth)
    API: Snapshot GraphQL
    OUTPUT: bronze/grants/smallgrants_proposals.json

    DEPENDENCIES: None
    ESTIMATED: ~30s
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: smallgrants_proposals")
    context.log.info("[BRONZE] Source: snapshot.org (space: small-grants.eth)")
    context.log.info("[BRONZE] Output: bronze/grants/smallgrants_proposals.json")
    context.log.info("[BRONZE] Fetching ENS Small Grants proposals...")

    proposals = fetch_smallgrants_proposals()
    context.log.info(f"[BRONZE] ✓ Received {len(proposals)} small grants proposals")

    _write_json(
        proposals,
        "grants",
        "smallgrants_proposals.json",
        context,
        source="snapshot.org",
        method="GraphQL paginated query (space=small-grants.eth)",
    )

    context.log.info(
        f"[BRONZE] ✓ smallgrants_proposals COMPLETE - {len(proposals)} records written"
    )


@asset(group_name="bronze", compute_kind="api", deps=["smallgrants_proposals"])
def smallgrants_votes(context: AssetExecutionContext) -> None:
    """Fetch votes on ENS Small Grants proposals.

    DATA: Community voting on grant funding
    API: Snapshot GraphQL — per proposal
    OUTPUT: bronze/grants/smallgrants_votes.json

    DEPENDENCIES: smallgrants_proposals (reads proposal IDs from disk)
    ESTIMATED: ~2-5 min
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: smallgrants_votes (depends on smallgrants_proposals)")
    context.log.info("[BRONZE] Source: snapshot.org GraphQL API")
    context.log.info("[BRONZE] Output: bronze/grants/smallgrants_votes.json")

    proposals_path = BRONZE_ROOT / "grants" / "smallgrants_proposals.json"
    with open(proposals_path) as f:
        proposals = json.load(f)

    context.log.info(f"[BRONZE] Found {len(proposals)} proposals from previous asset")
    context.log.info(f"[BRONZE] Fetching votes for {len(proposals)} Small Grants proposals...")

    votes = fetch_smallgrants_votes(proposals)
    context.log.info(f"[BRONZE] ✓ Received {len(votes)} Small Grants votes")

    _write_json(
        votes,
        "grants",
        "smallgrants_votes.json",
        context,
        source="snapshot.org",
        method="GraphQL paginated query per proposal",
    )

    context.log.info(f"[BRONZE] ✓ smallgrants_votes COMPLETE - {len(votes)} records written")


# ============================================================================
# DISCOURSE — ENS Governance Forum
# Community discussion threads (not captured by on-chain voting)
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def forum_topics(context: AssetExecutionContext) -> None:
    """Fetch ENS Governance Forum topics and posts from Discourse.

    DATA: Community discussion, sentiment, proposal debates
    API: Discourse JSON API (public endpoints)
    OUTPUT: bronze/forum/forum_topics.json & forum_posts.json

    DEPENDENCIES: None
    ESTIMATED: ~15-25 min (~2,400 topics + all posts)

    TWO OUTPUTS:
    1. forum_topics.json: Topic metadata (title, author, timestamps, stats)
    2. forum_posts.json: Individual posts with content

    USE CASE: Sentiment analysis, participation metrics, governance discussions
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: forum_topics")
    context.log.info("[BRONZE] Source: discuss.ens.domains Discourse API")
    context.log.info("[BRONZE] Output: bronze/forum/forum_topics.json & forum_posts.json")
    context.log.info("[BRONZE] Fetching ENS Governance Forum topics and posts...")
    context.log.info("[BRONZE] This may take 15-25 minutes (~2,400 topics + all posts)")

    topics, posts = fetch_forum_data()
    context.log.info(f"[BRONZE] ✓ Received {len(topics)} topics and {len(posts)} posts")

    # Write topics and posts as separate files (different schemas)
    _write_json(
        topics,
        "forum",
        "forum_topics.json",
        context,
        source="discuss.ens.domains",
        method="Discourse JSON API (/latest.json paginated topics)",
    )
    _write_json(
        posts,
        "forum",
        "forum_posts.json",
        context,
        source="discuss.ens.domains",
        method="Discourse JSON API (/t/{slug}/{id}.json per topic)",
    )

    context.log.info(
        f"[BRONZE] ✓ forum_topics COMPLETE - {len(topics)} topics, {len(posts)} posts written"
    )


# ============================================================================
# SAFE — ENS DAO Multisig & Treasury
# On-chain transactions from ENS's Gnosis Safe wallets
# ============================================================================


@asset(group_name="bronze", compute_kind="api")
def ens_wallet_balances(context: AssetExecutionContext) -> None:
    """Fetch current balances for all ENS DAO Safe wallets.

    DATA: ETH, ENS, USDC, and other token balances
    API: Safe Transaction Service (/balances/usd/)
    OUTPUT: bronze/financial/ens_wallet_balances.json

    DEPENDENCIES: None
    ESTIMATED: ~1-2 min

    WALLETS: ENS DAO Multisig, Grants Multisig, ENS.eth, etc.
    REFRESH: Run before treasury analysis to get current state
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: ens_wallet_balances")
    context.log.info("[BRONZE] Source: Safe Transaction Service API")
    context.log.info("[BRONZE] Output: bronze/financial/ens_wallet_balances.json")
    context.log.info("[BRONZE] Fetching current balances for all ENS DAO Safe wallets...")

    balances = fetch_all_balances()
    context.log.info(f"[BRONZE] ✓ Fetched balances for {len(balances)} wallet/token combinations")

    _write_json(
        balances,
        "financial",
        "ens_wallet_balances.json",
        context,
        source="safe.global",
        method="Safe Transaction Service /balances/usd/ per wallet",
    )

    context.log.info(f"[BRONZE] ✓ ens_wallet_balances COMPLETE - {len(balances)} records written")


@asset(group_name="bronze", compute_kind="api")
def ens_safe_transactions(context: AssetExecutionContext) -> None:
    """Fetch historical transactions for ENS DAO Safe wallets.

    DATA: All executed multisig transactions (signers, amounts, destinations)
    API: Safe Transaction Service (/multisig-transactions/)
    OUTPUT: bronze/financial/ens_safe_transactions.json

    DEPENDENCIES: None
    ESTIMATED: ~5-10 min

    USE CASE: Treasury spending analysis, governance fund flows,
              contributor compensation tracking
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: ens_safe_transactions")
    context.log.info("[BRONZE] Source: Safe Transaction Service API")
    context.log.info("[BRONZE] Output: bronze/financial/ens_safe_transactions.json")
    context.log.info("[BRONZE] Fetching historical multisig transactions for ENS DAO wallets...")

    transactions = fetch_all_safe_transactions()
    context.log.info(f"[BRONZE] ✓ Received {len(transactions)} multisig transaction records")

    _write_json(
        transactions,
        "financial",
        "ens_safe_transactions.json",
        context,
        source="safe.global",
        method="Safe Transaction Service /multisig-transactions/ per wallet",
    )

    context.log.info(
        f"[BRONZE] ✓ ens_safe_transactions COMPLETE - {len(transactions)} records written"
    )
