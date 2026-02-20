"""Bronze layer assets — raw data ingestion.

Each asset reads a JSON file from the corresponding bronze/ subdirectory
and yields it as a DataFrame for downstream transforms.
"""

import json
from pathlib import Path

import pandas as pd
from dagster import AssetExecutionContext, asset

BRONZE_ROOT = Path(__file__).resolve().parent.parent.parent / "bronze"


def _load_json(subdir: str, filename: str) -> pd.DataFrame:
    """Load a JSON file from a bronze subdirectory into a DataFrame."""
    path = BRONZE_ROOT / subdir / filename
    if not path.exists():
        return pd.DataFrame()
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict) and "data" in data:
        return pd.DataFrame(data["data"])
    return pd.DataFrame([data])


# ---------------------------------------------------------------------------
# Governance (Snapshot + Tally)
# ---------------------------------------------------------------------------


@asset(group_name="bronze", compute_kind="json")
def snapshot_proposals(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw Snapshot governance proposals."""
    df = _load_json("governance", "snapshot_proposals.json")
    context.log.info(f"Loaded {len(df)} snapshot proposals")
    return df


@asset(group_name="bronze", compute_kind="json")
def snapshot_votes(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw Snapshot votes."""
    df = _load_json("governance", "snapshot_votes.json")
    context.log.info(f"Loaded {len(df)} snapshot votes")
    return df


@asset(group_name="bronze", compute_kind="json")
def tally_proposals(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw Tally on-chain proposals."""
    df = _load_json("governance", "tally_proposals.json")
    context.log.info(f"Loaded {len(df)} tally proposals")
    return df


@asset(group_name="bronze", compute_kind="json")
def tally_votes(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw Tally votes."""
    df = _load_json("governance", "tally_votes.json")
    context.log.info(f"Loaded {len(df)} tally votes")
    return df


@asset(group_name="bronze", compute_kind="json")
def tally_delegates(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw Tally delegate profiles."""
    df = _load_json("governance", "tally_delegates.json")
    context.log.info(f"Loaded {len(df)} tally delegates")
    return df


# ---------------------------------------------------------------------------
# On-chain
# ---------------------------------------------------------------------------


@asset(group_name="bronze", compute_kind="json")
def delegations(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw delegation events."""
    df = _load_json("on-chain", "delegations.json")
    context.log.info(f"Loaded {len(df)} delegation records")
    return df


@asset(group_name="bronze", compute_kind="json")
def token_distribution(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw ENS token distribution snapshot."""
    df = _load_json("on-chain", "token_distribution.json")
    context.log.info(f"Loaded {len(df)} token holders")
    return df


@asset(group_name="bronze", compute_kind="json")
def treasury_flows(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw treasury transaction flows."""
    df = _load_json("on-chain", "treasury_flows.json")
    context.log.info(f"Loaded {len(df)} treasury transactions")
    return df


# ---------------------------------------------------------------------------
# Financial / Grants / Interviews
# ---------------------------------------------------------------------------


@asset(group_name="bronze", compute_kind="json")
def grants(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw grants data."""
    df = _load_json("grants", "grants.json")
    context.log.info(f"Loaded {len(df)} grants")
    return df


@asset(group_name="bronze", compute_kind="json")
def compensation(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw compensation records."""
    df = _load_json("financial", "compensation.json")
    context.log.info(f"Loaded {len(df)} compensation records")
    return df


@asset(group_name="bronze", compute_kind="json")
def delegate_profiles(context: AssetExecutionContext) -> pd.DataFrame:
    """Raw delegate profile data from interviews and public statements."""
    df = _load_json("interviews", "delegate_profiles.json")
    context.log.info(f"Loaded {len(df)} delegate profiles")
    return df
