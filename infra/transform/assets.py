"""Silver layer assets — cleaning, typing, and deduplication.

Each silver asset takes a bronze DataFrame, applies transforms,
and outputs a cleaned DataFrame. Transform logic is stubbed with TODOs
to be implemented once raw data schemas are confirmed.
"""

import pandas as pd
from dagster import AssetExecutionContext, asset

# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


@asset(group_name="silver", compute_kind="pandas")
def clean_snapshot_proposals(
    context: AssetExecutionContext, snapshot_proposals: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned Snapshot proposals with normalized columns."""
    if snapshot_proposals.empty:
        context.log.warning("No snapshot proposals to clean")
        return snapshot_proposals
    df = snapshot_proposals.copy()
    # TODO: parse timestamps, normalize column names, validate against taxonomy
    # TODO: extract governance_category from title/body
    context.log.info(f"Cleaned {len(df)} snapshot proposals")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_snapshot_votes(
    context: AssetExecutionContext, snapshot_votes: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned Snapshot votes with normalized addresses."""
    if snapshot_votes.empty:
        context.log.warning("No snapshot votes to clean")
        return snapshot_votes
    df = snapshot_votes.copy()
    # TODO: lowercase addresses, parse timestamps, deduplicate
    # TODO: map choice integers to vote_choices taxonomy values
    context.log.info(f"Cleaned {len(df)} snapshot votes")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_tally_proposals(
    context: AssetExecutionContext, tally_proposals: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned Tally proposals with normalized columns."""
    if tally_proposals.empty:
        context.log.warning("No tally proposals to clean")
        return tally_proposals
    df = tally_proposals.copy()
    # TODO: convert wei strings to float, normalize status to proposal_status taxonomy
    context.log.info(f"Cleaned {len(df)} tally proposals")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_tally_votes(
    context: AssetExecutionContext, tally_votes: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned Tally votes with normalized support values."""
    if tally_votes.empty:
        context.log.warning("No tally votes to clean")
        return tally_votes
    df = tally_votes.copy()
    # TODO: map support integers to vote_choices, convert weight from wei
    context.log.info(f"Cleaned {len(df)} tally votes")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_tally_delegates(
    context: AssetExecutionContext, tally_delegates: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned delegate data with normalized addresses and voting power."""
    if tally_delegates.empty:
        context.log.warning("No tally delegates to clean")
        return tally_delegates
    df = tally_delegates.copy()
    # TODO: lowercase addresses, convert voting_power from wei, deduplicate
    context.log.info(f"Cleaned {len(df)} tally delegates")
    return df


# ---------------------------------------------------------------------------
# On-chain
# ---------------------------------------------------------------------------


@asset(group_name="silver", compute_kind="pandas")
def clean_delegations(
    context: AssetExecutionContext, delegations: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned delegation records."""
    if delegations.empty:
        context.log.warning("No delegations to clean")
        return delegations
    df = delegations.copy()
    # TODO: lowercase addresses, convert balances, sort by block
    context.log.info(f"Cleaned {len(df)} delegation records")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_token_distribution(
    context: AssetExecutionContext, token_distribution: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned token distribution snapshot."""
    if token_distribution.empty:
        context.log.warning("No token distribution to clean")
        return token_distribution
    df = token_distribution.copy()
    # TODO: convert balances from wei, compute percentages
    context.log.info(f"Cleaned {len(df)} token holders")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_treasury_flows(
    context: AssetExecutionContext, treasury_flows: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned treasury flows with categorized transactions."""
    if treasury_flows.empty:
        context.log.warning("No treasury flows to clean")
        return treasury_flows
    df = treasury_flows.copy()
    # TODO: normalize addresses, parse amounts, validate categories
    context.log.info(f"Cleaned {len(df)} treasury transactions")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_grants(context: AssetExecutionContext, grants: pd.DataFrame) -> pd.DataFrame:
    """Cleaned grants data."""
    if grants.empty:
        context.log.warning("No grants to clean")
        return grants
    df = grants.copy()
    # TODO: normalize working_group to taxonomy, validate amounts
    context.log.info(f"Cleaned {len(df)} grants")
    return df


@asset(group_name="silver", compute_kind="pandas")
def clean_compensation(
    context: AssetExecutionContext, compensation: pd.DataFrame
) -> pd.DataFrame:
    """Cleaned compensation records."""
    if compensation.empty:
        context.log.warning("No compensation to clean")
        return compensation
    df = compensation.copy()
    # TODO: normalize roles to stakeholder_roles taxonomy, validate working_group
    context.log.info(f"Cleaned {len(df)} compensation records")
    return df


# ---------------------------------------------------------------------------
# Crosswalk
# ---------------------------------------------------------------------------


@asset(group_name="silver", compute_kind="pandas")
def address_crosswalk(
    context: AssetExecutionContext,
    clean_tally_delegates: pd.DataFrame,
    clean_snapshot_votes: pd.DataFrame,
    clean_delegations: pd.DataFrame,
) -> pd.DataFrame:
    """Unified address crosswalk linking identities across data sources.

    Merges addresses from Tally delegates, Snapshot voters, and delegation
    records into a single lookup table with ENS names where available.
    """
    addresses = set()

    if not clean_tally_delegates.empty and "address" in clean_tally_delegates.columns:
        addresses.update(clean_tally_delegates["address"].dropna().unique())

    if not clean_snapshot_votes.empty and "voter" in clean_snapshot_votes.columns:
        addresses.update(clean_snapshot_votes["voter"].dropna().unique())

    if not clean_delegations.empty:
        for col in ["delegator", "delegate"]:
            if col in clean_delegations.columns:
                addresses.update(clean_delegations[col].dropna().unique())

    df = pd.DataFrame({"address": sorted(addresses)})
    # TODO: resolve ENS names, merge delegate metadata, assign stakeholder_roles
    df["ens_name"] = None
    df["stakeholder_role"] = None
    df["source"] = None

    context.log.info(f"Built address crosswalk with {len(df)} unique addresses")
    return df
