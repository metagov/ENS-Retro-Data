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
- bronze/github/: ENS GitHub repo metrics and event history (via OSO)
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
from infra.ingest.oso_api import (
    TIMESERIES_START,
    fetch_ens_code_metrics,
    fetch_ens_repos,
    fetch_ens_timeseries,
)
from infra.resources import EtherscanApiConfig, OsoApiConfig

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


def _log_metadata_warning(subdir: str, message: str, *, source: str = "dagster_pipeline") -> None:
    """Append a warning entry to the top-level warnings list in bronze/{subdir}/metadata.json.

    Warnings capture things like skipped addresses, shutdown APIs, or missing
    files so the provenance record reflects what happened during the run.
    """
    meta_path = BRONZE_ROOT / subdir / "metadata.json"
    if not meta_path.exists():
        return
    with open(meta_path) as f:
        meta = json.load(f)

    warnings = meta.setdefault("warnings", [])
    warnings.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "message": message,
    })

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def _check_file_exists(subdir: str, filename: str, context: AssetExecutionContext):
    """Verify manually-placed files exist and update metadata accordingly.

    Some data sources (votingpower.xyz, ens-ledger.app) are not yet
    automated via API. These sentinel assets:
    1. Check if the file exists on disk
    2. Log a warning if missing
    3. Update metadata to track availability
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
        msg = f"Missing {path.name} — file not on disk, place manually before running dbt"
        context.log.warning(msg)
        _update_metadata(subdir, filename, status="missing")
        _log_metadata_warning(subdir, msg, source=filename)


def _already_on_disk(path: Path, context: AssetExecutionContext) -> bool:
    """Return True if a bronze JSON file already exists, logging its stats.

    When True, the calling asset should skip the API fetch — the data is
    already present from a previous run.  Delete the file to force a re-fetch.
    """
    if not path.exists():
        return False
    stat = path.stat()
    try:
        with open(path) as f:
            records = len(json.load(f))
        context.log.info(
            f"[BRONZE] Already on disk: {path.name} ({records:,} records, {stat.st_size:,} bytes)"
        )
        context.log.info("[BRONZE] Skipping fetch — delete the file to force a re-fetch.")
        context.add_output_metadata(
            {"records": records, "file_size_bytes": stat.st_size, "status": "existing_file"}
        )
    except Exception:
        context.log.info(f"[BRONZE] Already on disk: {path.name} ({stat.st_size:,} bytes)")
        context.add_output_metadata(
            {"file_size_bytes": stat.st_size, "status": "existing_file"}
        )
    return True


# ============================================================================
# SNAPSHOT.GOV — Off-chain voting data
# Snapshot hosts ENS DAO's off-chain voting (temperature check / discourse)
# ============================================================================


@asset(group_name="bronze_governance", compute_kind="api")
def snapshot_proposals(context: AssetExecutionContext) -> None:
    """Fetch all ENS governance proposals from Snapshot.org.

    DATA: Off-chain proposals used for community sentiment before on-chain votes.
    API: Snapshot GraphQL (space: ens.eth)
    OUTPUT: bronze/governance/snapshot_proposals.json

    DEPENDENCIES: None — fetches all proposals directly
    ESTIMATED: ~30s for ~90 proposals
    """
    if _already_on_disk(BRONZE_ROOT / "governance" / "snapshot_proposals.json", context):
        return
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


@asset(group_name="bronze_governance", compute_kind="api", deps=["snapshot_proposals"])
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
    if _already_on_disk(BRONZE_ROOT / "governance" / "snapshot_votes.json", context):
        return
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
# TALLY.XYZ — Historical snapshot (read-only)
# Tally shut down its API in 2025. These assets are now frozen sentinels that
# confirm the previously indexed data is still present on disk. Re-indexing
# is no longer possible.
# ============================================================================

_TALLY_SHUTDOWN_MSG = (
    "Tally.xyz has shut down its API, so this data can no longer be refreshed. "
    "What you see here is a historical snapshot captured before the shutdown. "
    "The underlying JSON file is committed to the repository and serves as the "
    "permanent source of record for all downstream dbt models."
)


@asset(group_name="bronze_governance", compute_kind="file")
def tally_proposals(context: AssetExecutionContext) -> None:
    """Historical snapshot of ENS on-chain governance proposals from Tally.

    SOURCE: Tally GraphQL API (now shut down — data frozen as of last index run)
    PATH: bronze/governance/tally_proposals.json
    RECORDS: 66 proposals

    NOTE: Tally.xyz has shut down its API. This data cannot be re-indexed.
    """
    context.log.warning(_TALLY_SHUTDOWN_MSG)
    _log_metadata_warning("governance", _TALLY_SHUTDOWN_MSG, source="tally_proposals")
    _check_file_exists("governance", "tally_proposals.json", context)


@asset(group_name="bronze_governance", compute_kind="file", deps=["tally_proposals"])
def tally_votes(context: AssetExecutionContext) -> None:
    """Historical snapshot of ENS on-chain votes from Tally.

    SOURCE: Tally GraphQL API (now shut down — data frozen as of last index run)
    PATH: bronze/governance/tally_votes.json
    RECORDS: ~9,987 votes across 66 proposals

    NOTE: Tally.xyz has shut down its API. This data cannot be re-indexed.
    """
    context.log.warning(_TALLY_SHUTDOWN_MSG)
    _log_metadata_warning("governance", _TALLY_SHUTDOWN_MSG, source="tally_votes")
    _check_file_exists("governance", "tally_votes.json", context)


@asset(group_name="bronze_governance", compute_kind="file")
def tally_delegates(context: AssetExecutionContext) -> None:
    """Historical snapshot of ENS delegate profiles from Tally.

    SOURCE: Tally GraphQL API (now shut down — data frozen as of last index run)
    PATH: bronze/governance/tally_delegates.json
    RECORDS: ~37,891 delegate profiles

    NOTE: Tally.xyz has shut down its API. This data cannot be re-indexed.
    """
    context.log.warning(_TALLY_SHUTDOWN_MSG)
    _log_metadata_warning("governance", _TALLY_SHUTDOWN_MSG, source="tally_delegates")
    _check_file_exists("governance", "tally_delegates.json", context)


# ============================================================================
# SENTINEL ASSETS — Manually placed data files
# These check for files that haven't been automated yet
# ============================================================================


@asset(group_name="bronze_governance", compute_kind="file")
def votingpower_delegates(context: AssetExecutionContext) -> None:
    """Sentinel check for votingpower.xyz delegate snapshot.

    SOURCE: Manually downloaded from votingpower.xyz (no public API)
    PATH: bronze/governance/votingpower-xyz/ens-delegates-2026-02-20.csv

    ACTION REQUIRED: Download CSV from votingpower.xyz and place in bronze/
    """
    _check_file_exists("governance", "votingpower-xyz/ens-delegates-2026-02-20.csv", context)


@asset(group_name="bronze_financial", compute_kind="file")
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


@asset(group_name="bronze_onchain", compute_kind="api")
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
    if _already_on_disk(BRONZE_ROOT / "on-chain" / "delegations.json", context):
        return
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


@asset(group_name="bronze_onchain", compute_kind="api")
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
    if _already_on_disk(BRONZE_ROOT / "on-chain" / "token_distribution.json", context):
        return
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


@asset(group_name="bronze_onchain", compute_kind="api")
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
    if _already_on_disk(BRONZE_ROOT / "on-chain" / "treasury_flows.json", context):
        return
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


@asset(group_name="bronze_grants", compute_kind="api")
def smallgrants_proposals(context: AssetExecutionContext) -> None:
    """Fetch ENS Small Grants proposals from Snapshot.

    DATA: Off-chain funding proposals (space: small-grants.eth)
    API: Snapshot GraphQL
    OUTPUT: bronze/grants/smallgrants_proposals.json

    DEPENDENCIES: None
    ESTIMATED: ~30s
    """
    if _already_on_disk(BRONZE_ROOT / "grants" / "smallgrants_proposals.json", context):
        return
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


@asset(group_name="bronze_grants", compute_kind="api", deps=["smallgrants_proposals"])
def smallgrants_votes(context: AssetExecutionContext) -> None:
    """Fetch votes on ENS Small Grants proposals.

    DATA: Community voting on grant funding
    API: Snapshot GraphQL — per proposal
    OUTPUT: bronze/grants/smallgrants_votes.json

    DEPENDENCIES: smallgrants_proposals (reads proposal IDs from disk)
    ESTIMATED: ~2-5 min
    """
    if _already_on_disk(BRONZE_ROOT / "grants" / "smallgrants_votes.json", context):
        return
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


@asset(group_name="bronze_forum", compute_kind="api")
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
    if (
        _already_on_disk(BRONZE_ROOT / "forum" / "forum_topics.json", context)
        and (BRONZE_ROOT / "forum" / "forum_posts.json").exists()
    ):
        return
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


@asset(group_name="bronze_financial", compute_kind="api")
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
    if _already_on_disk(BRONZE_ROOT / "financial" / "ens_wallet_balances.json", context):
        return
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


@asset(group_name="bronze_financial", compute_kind="api")
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
    if _already_on_disk(BRONZE_ROOT / "financial" / "ens_safe_transactions.json", context):
        return
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: ens_safe_transactions")
    context.log.info("[BRONZE] Source: Safe Transaction Service API")
    context.log.info("[BRONZE] Output: bronze/financial/ens_safe_transactions.json")
    context.log.info("[BRONZE] Fetching historical multisig transactions for ENS DAO wallets...")

    fetch_warnings: list[str] = []
    transactions = fetch_all_safe_transactions(warnings=fetch_warnings)
    for w in fetch_warnings:
        context.log.warning(f"[BRONZE] {w}")
        _log_metadata_warning("financial", w, source="ens_safe_transactions")
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


# ============================================================================
# OPEN SOURCE OBSERVER — GitHub activity data for ENS repositories
# OSO indexes GitHub events for open-source projects via SQL data lake.
# ============================================================================


@asset(group_name="bronze_github", compute_kind="api")
def oso_ens_repos(context: AssetExecutionContext, oso_config: OsoApiConfig) -> None:
    """Fetch all ENS GitHub repositories registered in Open Source Observer.

    DATA: Artifact registry — one row per ENS repo with artifact ID, name, project linkage.
    API: OSO data lake via pyoso (artifacts_by_project_v1, artifact_namespace='ensdomains')
    OUTPUT: bronze/github/oso_ens_repos.json

    DEPENDENCIES: None — reference table, fetched independently
    ESTIMATED: ~10s
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: oso_ens_repos")
    context.log.info("[BRONZE] Output: bronze/github/oso_ens_repos.json")

    repos = fetch_ens_repos(oso_config.api_key)
    context.log.info(f"[BRONZE] ✓ Received {len(repos)} ENS repo records from OSO")

    _write_json(
        repos,
        "github",
        "oso_ens_repos.json",
        context,
        source="opensource.observer",
        method="pyoso SQL: artifacts_by_project_v1 WHERE artifact_namespace='ensdomains'",
    )

    context.log.info(f"[BRONZE] ✓ oso_ens_repos COMPLETE — {len(repos)} repos written")


@asset(group_name="bronze_github", compute_kind="api")
def oso_ens_code_metrics(context: AssetExecutionContext, oso_config: OsoApiConfig) -> None:
    """Fetch per-repo code health metrics for ENS GitHub repositories from OSO.

    DATA: Current snapshot of stars, forks, contributors, commits, PRs, issues
          per repo (6-month windows for activity metrics).
    API: OSO data lake via pyoso (code_metrics_by_artifact_v0)
    OUTPUT: bronze/github/oso_ens_code_metrics.json

    DEPENDENCIES: None — fetched independently, full refresh on every run
    ESTIMATED: ~15s
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: oso_ens_code_metrics")
    context.log.info("[BRONZE] Output: bronze/github/oso_ens_code_metrics.json")

    metrics = fetch_ens_code_metrics(oso_config.api_key)
    context.log.info(f"[BRONZE] ✓ Received code metrics for {len(metrics)} repos from OSO")

    _write_json(
        metrics,
        "github",
        "oso_ens_code_metrics.json",
        context,
        source="opensource.observer",
        method="pyoso SQL: code_metrics_by_artifact_v0 WHERE artifact_namespace='ensdomains'",
    )

    context.log.info(
        f"[BRONZE] ✓ oso_ens_code_metrics COMPLETE — {len(metrics)} repo metric rows written"
    )


@asset(group_name="bronze_github", compute_kind="api")
def oso_ens_timeseries(context: AssetExecutionContext, oso_config: OsoApiConfig) -> None:
    """Fetch daily GitHub event history for ENS repos from OSO (incremental append).

    DATA: All GitHub event types (COMMIT_CODE, PULL_REQUEST_MERGED, ISSUE_OPENED, etc.)
          one row per (repo, event_type, day). Incrementally appended on reruns.
    API: OSO data lake via pyoso (timeseries_metrics_by_artifact_v0 + metrics_v0)
    OUTPUT: bronze/github/oso_ens_timeseries.json

    STRATEGY: Incremental append — reads existing JSON to find max(time), fetches
              only newer events from OSO, merges and writes the combined dataset.
              On first run (no existing file), fetches from TIMESERIES_START (2019-01-01).

    DEPENDENCIES: None
    ESTIMATED: ~30s first run (full history), ~5s on reruns
    """
    context.log.info("=" * 60)
    context.log.info("[BRONZE] Starting: oso_ens_timeseries (incremental)")
    context.log.info("[BRONZE] Output: bronze/github/oso_ens_timeseries.json")

    path = BRONZE_ROOT / "github" / "oso_ens_timeseries.json"

    # Determine incremental cutoff from max event time in existing data
    existing: list[dict] = []
    since = TIMESERIES_START
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
        if existing:
            since = max(str(r.get("event_time", "")) for r in existing if r.get("event_time"))
            context.log.info(
                f"[BRONZE] Found {len(existing)} existing rows — fetching since {since}"
            )
        else:
            context.log.info("[BRONZE] Existing file is empty — fetching full history")
    else:
        context.log.info(f"[BRONZE] No existing file — fetching full history since {since}")

    new_rows = fetch_ens_timeseries(oso_config.api_key, since=since)
    context.log.info(f"[BRONZE] ✓ Received {len(new_rows)} new event rows from OSO")

    merged = existing + new_rows
    context.log.info(
        f"[BRONZE] Merged: {len(existing)} existing + {len(new_rows)} new = {len(merged)} total"
    )

    _write_json(
        merged,
        "github",
        "oso_ens_timeseries.json",
        context,
        source="opensource.observer",
        method=(
            f"pyoso SQL: timeseries_metrics_by_artifact_v0 + metrics_v0 "
            f"WHERE artifact_namespace='ensdomains' AND sample_date >= '{since}'"
        ),
    )

    context.log.info(
        f"[BRONZE] ✓ oso_ens_timeseries COMPLETE — {len(merged)} total rows written"
    )
