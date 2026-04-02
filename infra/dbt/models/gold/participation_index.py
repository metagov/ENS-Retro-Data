"""Gold: Participation index with Gini coefficient for voting power.

dbt Python model — runs inside DuckDB via dbt-duckdb.
"""

import numpy as np


def model(dbt, session):
    dbt.config(materialized="table")

    # Load upstream models
    governance = dbt.ref("governance_activity").df()
    scorecard = dbt.ref("delegate_scorecard").df()
    token_dist = dbt.ref("clean_token_distribution").df()

    metrics = []

    # Total proposals
    if len(governance) > 0:
        total_proposals = len(governance)
        snapshot_proposals = len(governance[governance["source"] == "snapshot"])
        tally_proposals = len(governance[governance["source"] == "tally"])
        metrics.append({"metric": "total_proposals", "value": float(total_proposals)})
        metrics.append({"metric": "snapshot_proposals", "value": float(snapshot_proposals)})
        metrics.append({"metric": "tally_proposals", "value": float(tally_proposals)})

    # Active delegates and participation
    if len(scorecard) > 0:
        active = scorecard[
            (scorecard["snapshot_votes_cast"] > 0) | (scorecard["tally_votes_cast"] > 0)
        ]
        metrics.append({"metric": "active_delegates", "value": float(len(active))})
        metrics.append({"metric": "total_delegates", "value": float(len(scorecard))})

        if len(active) > 0:
            avg_participation = float(active["participation_rate"].mean())
            metrics.append(
                {"metric": "avg_participation_rate", "value": round(avg_participation, 2)}
            )

    # Gini coefficient for voting power
    if len(scorecard) > 0 and "voting_power" in scorecard.columns:
        vp = np.array(scorecard["voting_power"].dropna().astype(float))
        if len(vp) > 0:
            vp_sorted = np.sort(vp)
            n = len(vp_sorted)
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * vp_sorted) - (n + 1) * np.sum(vp_sorted)) / (
                n * np.sum(vp_sorted)
            )
            metrics.append({"metric": "voting_power_gini", "value": round(float(gini), 4)})

    # Token distribution Gini
    if len(token_dist) > 0 and "balance" in token_dist.columns:
        balances = np.array(token_dist["balance"].dropna().astype(float))
        if len(balances) > 0:
            b_sorted = np.sort(balances)
            n = len(b_sorted)
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * b_sorted) - (n + 1) * np.sum(b_sorted)) / (
                n * np.sum(b_sorted)
            )
            metrics.append({"metric": "token_gini", "value": round(float(gini), 4)})

    import pandas as pd

    return pd.DataFrame(metrics) if metrics else pd.DataFrame(columns=["metric", "value"])
