"""Gold: Decentralization index — Nakamoto coefficient, HHI, delegation concentration.

dbt Python model — runs inside DuckDB via dbt-duckdb.
"""

import numpy as np


def model(dbt, session):
    dbt.config(materialized="table")

    token_dist = dbt.ref("clean_token_distribution").df()
    delegations = dbt.ref("clean_delegations").df()
    scorecard = dbt.ref("delegate_scorecard").df()

    metrics = []

    # Nakamoto coefficient: min delegates needed for >50% voting power
    if len(scorecard) > 0 and "voting_power" in scorecard.columns:
        vp = np.array(
            scorecard.sort_values("voting_power", ascending=False)["voting_power"]
            .dropna()
            .astype(float)
        )
        if len(vp) > 0 and np.sum(vp) > 0:
            total = np.sum(vp)
            cumulative = np.cumsum(vp)
            nakamoto = int(np.searchsorted(cumulative, total * 0.5) + 1)
            metrics.append({"metric": "nakamoto_coefficient", "value": float(nakamoto)})

    # HHI (Herfindahl-Hirschman Index) for voting power
    if len(scorecard) > 0 and "voting_power" in scorecard.columns:
        vp = np.array(scorecard["voting_power"].dropna().astype(float))
        if len(vp) > 0 and np.sum(vp) > 0:
            shares = vp / np.sum(vp)
            hhi = float(np.sum(shares**2))
            metrics.append({"metric": "voting_power_hhi", "value": round(hhi, 6)})

    # Token distribution HHI
    if len(token_dist) > 0 and "balance" in token_dist.columns:
        balances = np.array(token_dist["balance"].dropna().astype(float))
        if len(balances) > 0 and np.sum(balances) > 0:
            shares = balances / np.sum(balances)
            hhi = float(np.sum(shares**2))
            metrics.append({"metric": "token_hhi", "value": round(hhi, 6)})

    # Delegation concentration: % of voting power held by top 10 delegates
    if len(scorecard) > 0 and "voting_power" in scorecard.columns:
        vp = np.array(
            scorecard.sort_values("voting_power", ascending=False)["voting_power"]
            .dropna()
            .astype(float)
        )
        if len(vp) > 0 and np.sum(vp) > 0:
            top_10_share = float(np.sum(vp[:10]) / np.sum(vp) * 100)
            metrics.append(
                {"metric": "top_10_delegation_pct", "value": round(top_10_share, 2)}
            )

    # Unique delegators count
    if len(delegations) > 0 and "delegator" in delegations.columns:
        unique_delegators = int(delegations["delegator"].nunique())
        metrics.append({"metric": "unique_delegators", "value": float(unique_delegators)})

    # Unique delegates receiving delegation
    if len(delegations) > 0 and "delegate" in delegations.columns:
        unique_delegates = int(delegations["delegate"].nunique())
        metrics.append(
            {"metric": "unique_delegates_receiving", "value": float(unique_delegates)}
        )

    import pandas as pd

    return pd.DataFrame(metrics) if metrics else pd.DataFrame(columns=["metric", "value"])
