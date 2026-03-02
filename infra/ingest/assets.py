"""Bronze layer assets — API ingestion and sentinel checks.

Active fetchers call external APIs and write JSON to bronze/.
Sentinel assets verify that manually-placed files exist on disk.
All assets return None — dbt reads the files directly from disk.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from dagster import AssetExecutionContext, asset

from infra.ingest.etherscan_api import (
    fetch_delegation_events,
    fetch_token_transfers,
    fetch_treasury_transactions,
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
    """Update a file entry in metadata.json with provenance and timestamps."""
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

    # Update collection_status based on how many files are present
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
    """Write a JSON array to a bronze file and update metadata.json provenance."""
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
    """Check that a manually-placed file exists and log its status."""
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


# ---------------------------------------------------------------------------
# Active governance fetchers (call APIs, write JSON to disk)
# ---------------------------------------------------------------------------


@asset(group_name="bronze", compute_kind="api")
def snapshot_proposals(context: AssetExecutionContext) -> None:
    """Fetch Snapshot proposals from API and write to bronze/governance/."""
    proposals = fetch_snapshot_proposals()
    context.log.info(f"Fetched {len(proposals)} snapshot proposals")
    _write_json(
        proposals, "governance", "snapshot_proposals.json", context,
        source="snapshot.org", method="GraphQL paginated query (space=ens.eth)",
    )


@asset(group_name="bronze", compute_kind="api", deps=["snapshot_proposals"])
def snapshot_votes(context: AssetExecutionContext) -> None:
    """Fetch Snapshot votes for all proposals and write to bronze/governance/."""
    # Read proposal IDs from the file written by snapshot_proposals
    proposals_path = BRONZE_ROOT / "governance" / "snapshot_proposals.json"
    with open(proposals_path) as f:
        proposals = json.load(f)
    context.log.info(f"Fetching votes for {len(proposals)} proposals")
    votes = fetch_snapshot_votes(proposals)
    context.log.info(f"Fetched {len(votes)} snapshot votes")
    _write_json(
        votes, "governance", "snapshot_votes.json", context,
        source="snapshot.org", method="GraphQL paginated query per proposal",
    )


@asset(group_name="bronze", compute_kind="api")
def tally_proposals(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch Tally proposals from API and write to bronze/governance/."""
    org = fetch_organization(tally_config.api_key)
    org_id = org["id"]
    context.log.info(f"Tally org: {org['name']} (id={org_id})")
    raw = fetch_tally_proposals(org_id, tally_config.api_key)
    proposals = flatten_tally_proposals(raw)
    context.log.info(f"Fetched {len(proposals)} tally proposals")
    _write_json(
        proposals, "governance", "tally_proposals.json", context,
        source="tally.xyz", method="GraphQL paginated query (org=ens), flattened",
    )


@asset(group_name="bronze", compute_kind="api", deps=["tally_proposals"])
def tally_votes(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch Tally votes for all proposals and write to bronze/governance/."""
    # Read proposal IDs from the flattened file
    proposals_path = BRONZE_ROOT / "governance" / "tally_proposals.json"
    with open(proposals_path) as f:
        _flat_proposals = json.load(f)  # noqa: F841 — read to confirm file exists
    # Re-fetch raw proposals to get IDs for the votes query
    org = fetch_organization(tally_config.api_key)
    raw_proposals = fetch_tally_proposals(org["id"], tally_config.api_key)
    context.log.info(f"Fetching votes for {len(raw_proposals)} tally proposals")
    raw_votes = fetch_tally_votes(raw_proposals, tally_config.api_key)
    votes = flatten_tally_votes(raw_votes)
    context.log.info(f"Fetched {len(votes)} tally votes")
    _write_json(
        votes, "governance", "tally_votes.json", context,
        source="tally.xyz", method="GraphQL paginated query per proposal, flattened",
    )


@asset(group_name="bronze", compute_kind="api")
def tally_delegates(context: AssetExecutionContext, tally_config: TallyApiConfig) -> None:
    """Fetch Tally delegates from API and write to bronze/governance/."""
    org = fetch_organization(tally_config.api_key)
    org_id = org["id"]
    raw = fetch_tally_delegates(org_id, tally_config.api_key)
    delegates = flatten_tally_delegates(raw)
    context.log.info(f"Fetched {len(delegates)} tally delegates")
    _write_json(
        delegates, "governance", "tally_delegates.json", context,
        source="tally.xyz", method="GraphQL paginated query (org=ens, sorted by votes), flattened",
    )


# ---------------------------------------------------------------------------
# Sentinel assets (manually-placed data, check file existence)
# ---------------------------------------------------------------------------


@asset(group_name="bronze", compute_kind="file")
def votingpower_delegates(context: AssetExecutionContext) -> None:
    """Sentinel for votingpower.xyz delegate CSV (manually placed)."""
    _check_file_exists(
        "governance", "votingpower-xyz/ens-delegates-2026-02-20.csv", context
    )


@asset(group_name="bronze", compute_kind="api")
def delegations(
    context: AssetExecutionContext, etherscan_config: EtherscanApiConfig,
) -> None:
    """Fetch DelegateChanged events from Etherscan for the ENS token."""
    events = fetch_delegation_events(etherscan_config.api_key)
    context.log.info(f"Fetched {len(events)} delegation events")
    _write_json(
        events, "on-chain", "delegations.json", context,
        source="etherscan.io",
        method="Event logs API (DelegateChanged on ENS token contract)",
    )


@asset(group_name="bronze", compute_kind="api")
def token_distribution(
    context: AssetExecutionContext, etherscan_config: EtherscanApiConfig,
) -> None:
    """Compute ENS token distribution from Transfer events via Etherscan."""
    distribution = fetch_token_transfers(etherscan_config.api_key)
    context.log.info(f"Computed distribution for {len(distribution)} holders")
    _write_json(
        distribution, "on-chain", "token_distribution.json", context,
        source="etherscan.io",
        method="Event logs API (Transfer events, client-side balance computation)",
    )


@asset(group_name="bronze", compute_kind="api")
def treasury_flows(
    context: AssetExecutionContext, etherscan_config: EtherscanApiConfig,
) -> None:
    """Fetch treasury transactions (ETH + ERC-20) for ENS DAO wallets."""
    flows = fetch_treasury_transactions(etherscan_config.api_key)
    context.log.info(f"Fetched {len(flows)} treasury transactions")
    _write_json(
        flows, "on-chain", "treasury_flows.json", context,
        source="etherscan.io",
        method="Account txlist + tokentx APIs for ENS DAO wallets",
    )


@asset(group_name="bronze", compute_kind="file")
def grants(context: AssetExecutionContext) -> None:
    """Sentinel for grants data (manually placed)."""
    _check_file_exists("grants", "grants.json", context)


@asset(group_name="bronze", compute_kind="file")
def compensation(context: AssetExecutionContext) -> None:
    """Sentinel for compensation records (manually placed)."""
    _check_file_exists("financial", "compensation.json", context)


@asset(group_name="bronze", compute_kind="file")
def delegate_profiles(context: AssetExecutionContext) -> None:
    """Sentinel for delegate profiles (manually placed)."""
    _check_file_exists("interviews", "delegate_profiles.json", context)


@asset(group_name="bronze", compute_kind="file")
def forum_posts(context: AssetExecutionContext) -> None:
    """Sentinel for forum posts (manually placed)."""
    _check_file_exists("forum", "forum_posts.json", context)
