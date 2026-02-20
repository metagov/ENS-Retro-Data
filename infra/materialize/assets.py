"""Gold layer assets — analysis-ready views and composite indexes.

These assets combine cleaned silver-layer data into the final views
used for the retrospective evaluation report.
"""

import pandas as pd
from dagster import AssetExecutionContext, asset


@asset(group_name="gold", compute_kind="pandas")
def governance_activity(
    context: AssetExecutionContext,
    clean_snapshot_proposals: pd.DataFrame,
    clean_snapshot_votes: pd.DataFrame,
    clean_tally_proposals: pd.DataFrame,
    clean_tally_votes: pd.DataFrame,
) -> pd.DataFrame:
    """Unified governance activity view combining Snapshot and Tally data.

    Columns: proposal_id, source, title, category, status, vote_count,
    for_pct, against_pct, abstain_pct, quorum_met, start_date, end_date.
    """
    rows = []

    if not clean_snapshot_proposals.empty:
        for _, p in clean_snapshot_proposals.iterrows():
            rows.append(
                {
                    "proposal_id": p.get("id"),
                    "source": "snapshot",
                    "title": p.get("title"),
                    "category": None,  # TODO: classify from title/body
                    "status": p.get("state"),
                    "vote_count": p.get("votes", 0),
                    "start_date": p.get("start"),
                    "end_date": p.get("end"),
                }
            )

    if not clean_tally_proposals.empty:
        for _, p in clean_tally_proposals.iterrows():
            rows.append(
                {
                    "proposal_id": p.get("id"),
                    "source": "tally",
                    "title": p.get("title"),
                    "category": None,  # TODO: classify from description
                    "status": p.get("status"),
                    "vote_count": None,
                    "start_date": None,
                    "end_date": None,
                }
            )

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    context.log.info(f"Built governance_activity with {len(df)} proposals")
    return df


@asset(group_name="gold", compute_kind="pandas")
def delegate_scorecard(
    context: AssetExecutionContext,
    clean_tally_delegates: pd.DataFrame,
    clean_snapshot_votes: pd.DataFrame,
    clean_tally_votes: pd.DataFrame,
    address_crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Per-delegate scorecard with participation and influence metrics.

    Columns: address, ens_name, voting_power, snapshot_votes_cast,
    tally_votes_cast, participation_rate, delegators_count, role.
    """
    if clean_tally_delegates.empty:
        context.log.warning("No delegate data for scorecard")
        return pd.DataFrame()

    df = clean_tally_delegates.copy()

    # Count votes per address from each source
    if not clean_snapshot_votes.empty and "voter" in clean_snapshot_votes.columns:
        snap_counts = clean_snapshot_votes.groupby("voter").size().rename("snapshot_votes_cast")
        df = df.merge(snap_counts, left_on="address", right_index=True, how="left")
    else:
        df["snapshot_votes_cast"] = 0

    if not clean_tally_votes.empty and "voter" in clean_tally_votes.columns:
        tally_counts = clean_tally_votes.groupby("voter").size().rename("tally_votes_cast")
        df = df.merge(tally_counts, left_on="address", right_index=True, how="left")
    else:
        df["tally_votes_cast"] = 0

    df["snapshot_votes_cast"] = df["snapshot_votes_cast"].fillna(0).astype(int)
    df["tally_votes_cast"] = df["tally_votes_cast"].fillna(0).astype(int)

    # TODO: compute participation_rate, merge ENS names from crosswalk

    context.log.info(f"Built delegate_scorecard with {len(df)} delegates")
    return df


@asset(group_name="gold", compute_kind="pandas")
def treasury_summary(
    context: AssetExecutionContext,
    clean_treasury_flows: pd.DataFrame,
    clean_grants: pd.DataFrame,
    clean_compensation: pd.DataFrame,
) -> pd.DataFrame:
    """Treasury summary with inflows, outflows, and categorization.

    Columns: period, category, inflows, outflows, net, grant_spend,
    compensation_spend, other_spend.
    """
    # TODO: aggregate treasury flows by period and category
    # TODO: join grants and compensation for spend breakdown
    if clean_treasury_flows.empty:
        context.log.warning("No treasury data for summary")
        return pd.DataFrame()

    df = clean_treasury_flows.copy()
    context.log.info(f"Built treasury_summary from {len(df)} transactions")
    return df


@asset(group_name="gold", compute_kind="pandas")
def participation_index(
    context: AssetExecutionContext,
    governance_activity: pd.DataFrame,
    delegate_scorecard: pd.DataFrame,
    clean_token_distribution: pd.DataFrame,
) -> pd.DataFrame:
    """Composite participation index over time.

    Measures: voter turnout, unique voters, voting power concentration,
    proposal activity rate.
    """
    # TODO: compute time-series participation metrics
    # TODO: calculate Gini coefficient for voting power
    rows = []

    if not governance_activity.empty:
        rows.append(
            {
                "metric": "total_proposals",
                "value": len(governance_activity),
            }
        )
    if not delegate_scorecard.empty:
        rows.append(
            {
                "metric": "active_delegates",
                "value": len(
                    delegate_scorecard[
                        (delegate_scorecard.get("snapshot_votes_cast", 0) > 0)
                        | (delegate_scorecard.get("tally_votes_cast", 0) > 0)
                    ]
                )
                if not delegate_scorecard.empty
                else 0,
            }
        )

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    context.log.info(f"Built participation_index with {len(df)} metrics")
    return df


@asset(group_name="gold", compute_kind="pandas")
def decentralization_index(
    context: AssetExecutionContext,
    clean_token_distribution: pd.DataFrame,
    clean_delegations: pd.DataFrame,
    delegate_scorecard: pd.DataFrame,
) -> pd.DataFrame:
    """Decentralization metrics for ENS governance.

    Measures: Nakamoto coefficient, HHI for voting power, delegation
    concentration, unique proposer count.
    """
    # TODO: compute Nakamoto coefficient (min delegates for >50% power)
    # TODO: compute HHI (Herfindahl-Hirschman Index) for voting power
    # TODO: measure delegation concentration
    rows = []

    if not delegate_scorecard.empty and "voting_power" in delegate_scorecard.columns:
        rows.append(
            {
                "metric": "total_delegates",
                "value": len(delegate_scorecard),
            }
        )

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    context.log.info(f"Built decentralization_index with {len(df)} metrics")
    return df
