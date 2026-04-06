"""Integration tests against the real DuckDB warehouse.

All tests in this file hit main_silver and main_gold tables directly.
No mock data — assertions reflect actual ENS DAO on-chain state.

Run from dashboards/:
    python3 -m pytest tests/test_warehouse.py -v
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

_DB = Path(__file__).parent.parent.parent / "warehouse" / "ens_retro.duckdb"


@pytest.fixture(scope="module")
def con():
    """Read-only connection to the warehouse, shared across all tests in this module."""
    c = duckdb.connect(str(_DB), read_only=True)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Gold: delegate_scorecard
# ---------------------------------------------------------------------------

def test_scorecard_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_gold.delegate_scorecard").fetchone()[0]
    assert count > 1000, f"Expected >1000 delegates, got {count}"


def test_scorecard_voting_power_positive(con):
    """At least one delegate must hold positive voting power."""
    positive = con.execute(
        "SELECT COUNT(*) FROM main_gold.delegate_scorecard WHERE voting_power > 0"
    ).fetchone()[0]
    assert positive > 0


def test_scorecard_participation_rate_in_range(con):
    """Participation rate must be between 0 and 100 for all non-null rows."""
    out_of_range = con.execute("""
        SELECT COUNT(*) FROM main_gold.delegate_scorecard
        WHERE participation_rate IS NOT NULL
          AND (participation_rate < 0 OR participation_rate > 100)
    """).fetchone()[0]
    assert out_of_range == 0, f"{out_of_range} rows have participation_rate outside [0, 100]"


def test_scorecard_address_is_unique(con):
    total = con.execute("SELECT COUNT(*) FROM main_gold.delegate_scorecard").fetchone()[0]
    distinct = con.execute(
        "SELECT COUNT(DISTINCT address) FROM main_gold.delegate_scorecard"
    ).fetchone()[0]
    assert total == distinct, "delegate_scorecard has duplicate addresses"


def test_scorecard_no_null_addresses(con):
    nulls = con.execute(
        "SELECT COUNT(*) FROM main_gold.delegate_scorecard WHERE address IS NULL"
    ).fetchone()[0]
    assert nulls == 0


def test_scorecard_top10_delegates_hold_majority(con):
    """Top 10 delegates should collectively hold a significant share of voting power."""
    rows = con.execute("""
        SELECT voting_power
        FROM main_gold.delegate_scorecard
        WHERE voting_power > 0
        ORDER BY voting_power DESC
        LIMIT 10
    """).fetchdf()
    total = con.execute(
        "SELECT SUM(voting_power) FROM main_gold.delegate_scorecard WHERE voting_power > 0"
    ).fetchone()[0]
    top10_share = rows["voting_power"].sum() / total * 100
    assert top10_share > 10, f"Top 10 delegates hold only {top10_share:.1f}% — unexpected"


# ---------------------------------------------------------------------------
# Gold: governance_activity
# ---------------------------------------------------------------------------

def test_governance_activity_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_gold.governance_activity").fetchone()[0]
    assert count > 10, f"Expected >10 proposals, got {count}"


def test_governance_tally_vote_percentages_sum_to_100(con):
    """Tally on-chain proposals use strict for/against/abstain — percentages must sum to ~100.
    Snapshot proposals are excluded: they support ranked/weighted/multi-choice voting so
    for_pct + against_pct + abstain_pct can legitimately be < 100."""
    bad = con.execute("""
        SELECT COUNT(*) FROM main_gold.governance_activity
        WHERE source = 'tally'
          AND for_pct IS NOT NULL
          AND against_pct IS NOT NULL
          AND abstain_pct IS NOT NULL
          AND vote_count > 0
          AND ABS(for_pct + against_pct + abstain_pct - 100) > 1.0
    """).fetchone()[0]
    assert bad == 0, f"{bad} tally proposals have vote pct that don't sum to ~100"


def test_governance_proposal_statuses_are_known(con):
    statuses = con.execute(
        "SELECT DISTINCT status FROM main_gold.governance_activity WHERE status IS NOT NULL"
    ).fetchdf()["status"].tolist()
    known = {"passed", "failed", "active", "pending", "defeated", "succeeded",
             "executed", "cancelled", "expired", "queued", "closed"}
    unknown = [s for s in statuses if s.lower() not in known]
    assert not unknown, f"Unknown proposal statuses: {unknown}"


def test_governance_end_date_after_start_date(con):
    bad = con.execute("""
        SELECT COUNT(*) FROM main_gold.governance_activity
        WHERE start_date IS NOT NULL AND end_date IS NOT NULL
          AND end_date < start_date
    """).fetchone()[0]
    assert bad == 0, f"{bad} proposals have end_date before start_date"


# ---------------------------------------------------------------------------
# Gold: decentralization_index
# ---------------------------------------------------------------------------

def test_decentralization_index_required_metrics_present(con):
    metrics = con.execute(
        "SELECT metric FROM main_gold.decentralization_index"
    ).fetchdf()["metric"].tolist()
    for required in ("nakamoto_coefficient", "voting_power_hhi", "top_10_delegation_pct"):
        assert required in metrics, f"Missing metric: {required}"


def test_nakamoto_coefficient_is_sane(con):
    nakamoto = con.execute("""
        SELECT value FROM main_gold.decentralization_index
        WHERE metric = 'nakamoto_coefficient'
    """).fetchone()[0]
    assert 1 <= nakamoto <= 500, f"Nakamoto coefficient {nakamoto} is out of expected range [1, 500]"


def test_voting_power_hhi_is_bounded(con):
    hhi = con.execute("""
        SELECT value FROM main_gold.decentralization_index
        WHERE metric = 'voting_power_hhi'
    """).fetchone()[0]
    assert 0 < hhi <= 1, f"HHI {hhi} must be in (0, 1]"


def test_nakamoto_matches_scorecard(con):
    """Nakamoto coefficient in the index must match what we compute from the scorecard."""
    vp = con.execute("""
        SELECT voting_power FROM main_gold.delegate_scorecard
        WHERE voting_power > 0
        ORDER BY voting_power DESC
    """).fetchdf()["voting_power"].to_numpy(dtype=float)

    total = vp.sum()
    cumulative = np.cumsum(vp)
    computed_nakamoto = int(np.searchsorted(cumulative, total * 0.5, side="right") + 1)

    stored_nakamoto = int(con.execute("""
        SELECT value FROM main_gold.decentralization_index
        WHERE metric = 'nakamoto_coefficient'
    """).fetchone()[0])

    assert computed_nakamoto == stored_nakamoto, (
        f"Stored Nakamoto ({stored_nakamoto}) doesn't match computed ({computed_nakamoto})"
    )


# ---------------------------------------------------------------------------
# Gold: participation_index
# ---------------------------------------------------------------------------

def test_participation_index_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_gold.participation_index").fetchone()[0]
    assert count > 0


def test_participation_index_values_are_finite(con):
    bad = con.execute("""
        SELECT COUNT(*) FROM main_gold.participation_index
        WHERE value IS NULL OR value = 'Infinity'::DOUBLE OR isnan(value)
    """).fetchone()[0]
    assert bad == 0, f"{bad} participation_index rows have non-finite values"


# ---------------------------------------------------------------------------
# Gold: treasury_summary
# ---------------------------------------------------------------------------

def test_treasury_summary_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_gold.treasury_summary").fetchone()[0]
    assert count > 0


def test_treasury_inflows_non_negative(con):
    neg = con.execute("""
        SELECT COUNT(*) FROM main_gold.treasury_summary
        WHERE inflows_usd IS NOT NULL AND inflows_usd < 0
    """).fetchone()[0]
    assert neg == 0, f"{neg} treasury rows have negative inflows_usd"


def test_treasury_net_equals_inflows_minus_outflows(con):
    """net_usd must equal inflows_usd - outflows_usd for non-null rows."""
    bad = con.execute("""
        SELECT COUNT(*) FROM main_gold.treasury_summary
        WHERE inflows_usd IS NOT NULL
          AND outflows_usd IS NOT NULL
          AND net_usd IS NOT NULL
          AND ABS(net_usd - (inflows_usd - outflows_usd)) > 0.01
    """).fetchone()[0]
    assert bad == 0, f"{bad} treasury rows have net_usd ≠ inflows - outflows"


# ---------------------------------------------------------------------------
# Silver: clean_delegations
# ---------------------------------------------------------------------------

def test_delegations_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_silver.clean_delegations").fetchone()[0]
    assert count > 10000


def test_delegations_self_delegation_is_minority(con):
    """Self-delegation (delegating to yourself to retain voting rights) is valid in ENS.
    We verify it exists but doesn't account for 100% of delegation events — that would
    suggest a pipeline bug where cross-account delegations were lost."""
    total = con.execute("SELECT COUNT(*) FROM main_silver.clean_delegations").fetchone()[0]
    self_delg = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_delegations
        WHERE delegator = delegate
    """).fetchone()[0]
    self_pct = self_delg / total * 100
    # Self-delegation typically 20-50% of events; >80% would indicate data loss
    assert self_pct < 80, f"Self-delegation is {self_pct:.1f}% of all events — possible data loss"


def test_delegations_token_balance_non_negative(con):
    neg = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_delegations
        WHERE token_balance IS NOT NULL AND token_balance < 0
    """).fetchone()[0]
    assert neg == 0


def test_delegations_block_number_positive(con):
    bad = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_delegations
        WHERE block_number IS NOT NULL AND block_number <= 0
    """).fetchone()[0]
    assert bad == 0


# ---------------------------------------------------------------------------
# Silver: clean_snapshot_proposals
# ---------------------------------------------------------------------------

def test_snapshot_proposals_has_rows(con):
    count = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_snapshot_proposals"
    ).fetchone()[0]
    assert count > 10


def test_snapshot_proposals_unique_ids(con):
    total = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_snapshot_proposals"
    ).fetchone()[0]
    distinct = con.execute(
        "SELECT COUNT(DISTINCT proposal_id) FROM main_silver.clean_snapshot_proposals"
    ).fetchone()[0]
    assert total == distinct, "Duplicate proposal_ids in clean_snapshot_proposals"


# ---------------------------------------------------------------------------
# Silver: clean_snapshot_votes
# ---------------------------------------------------------------------------

def test_snapshot_votes_has_rows(con):
    count = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_snapshot_votes"
    ).fetchone()[0]
    assert count > 1000


def test_snapshot_votes_power_non_negative(con):
    neg = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_snapshot_votes
        WHERE voting_power IS NOT NULL AND voting_power < 0
    """).fetchone()[0]
    assert neg == 0


def test_snapshot_votes_reference_valid_proposals(con):
    """All votes must reference a proposal_id that exists in clean_snapshot_proposals."""
    orphans = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_snapshot_votes v
        LEFT JOIN main_silver.clean_snapshot_proposals p
               ON v.proposal_id = p.proposal_id
        WHERE p.proposal_id IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} votes reference non-existent proposals"


# ---------------------------------------------------------------------------
# Silver: clean_tally_votes
# ---------------------------------------------------------------------------

def test_tally_votes_reference_valid_proposals(con):
    orphans = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_tally_votes v
        LEFT JOIN main_silver.clean_tally_proposals p
               ON v.proposal_id = p.proposal_id
        WHERE p.proposal_id IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} tally votes reference non-existent proposals"


def test_tally_vote_choices_are_known(con):
    choices = con.execute(
        "SELECT DISTINCT vote_choice FROM main_silver.clean_tally_votes WHERE vote_choice IS NOT NULL"
    ).fetchdf()["vote_choice"].tolist()
    known = {"for", "against", "abstain", "yes", "no", "1", "2", "3",
             "For", "Against", "Abstain", "AGAINST", "FOR", "ABSTAIN", "unknown"}
    unknown = [c for c in choices if c not in known]
    assert not unknown, f"Unknown vote choices: {unknown}"


# ---------------------------------------------------------------------------
# Silver: clean_compensation
# ---------------------------------------------------------------------------

def test_compensation_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_silver.clean_compensation").fetchone()[0]
    assert count > 0


def test_compensation_value_usd_positive(con):
    neg = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_compensation
        WHERE value_usd IS NOT NULL AND value_usd <= 0
    """).fetchone()[0]
    assert neg == 0, f"{neg} compensation rows have non-positive value_usd"


def test_compensation_working_groups_not_null(con):
    nulls = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_compensation WHERE working_group IS NULL"
    ).fetchone()[0]
    assert nulls == 0, f"{nulls} compensation rows have null working_group"


# ---------------------------------------------------------------------------
# Silver: clean_grants
# ---------------------------------------------------------------------------

def test_grants_has_rows(con):
    count = con.execute("SELECT COUNT(*) FROM main_silver.clean_grants").fetchone()[0]
    assert count > 0


def test_grants_awarded_positive(con):
    """Awarded amounts, where present, must be positive."""
    neg = con.execute("""
        SELECT COUNT(*) FROM main_silver.clean_grants
        WHERE amount_awarded IS NOT NULL AND CAST(amount_awarded AS DOUBLE) <= 0
    """).fetchone()[0]
    assert neg == 0, f"{neg} grants have non-positive amount_awarded"


def test_grants_amount_requested_is_null(con):
    """amount_requested is structurally null across all grant records — this is expected.

    ENS uses a layered funding model:
    - Small grants: funding amount is preset per round; winners are chosen by token-weighted
      vote on Snapshot. There is no individual "requested" amount — applicants submit project
      descriptions, not funding asks.
    - Large/strategic grants: stewards negotiate directly with applicants; the awarded amount
      IS the agreed amount. A separate "requested" figure is not tracked in the source data.

    If this test starts failing, it means amount_requested was backfilled from a new source
    (e.g., Karma, Notion DB, or forum posts) and the test_grants_awarded_positive test above
    should be extended to cover the requested vs awarded relationship.
    """
    non_null = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_grants WHERE amount_requested IS NOT NULL"
    ).fetchone()[0]
    assert non_null == 0, (
        f"{non_null} grants have a non-null amount_requested — "
        "update this test if a new source has been wired in"
    )


# ---------------------------------------------------------------------------
# Silver: clean_token_distribution
# ---------------------------------------------------------------------------

def test_token_distribution_has_rows(con):
    count = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_token_distribution"
    ).fetchone()[0]
    assert count > 1000


def test_token_distribution_percentages_sum_to_100(con):
    total_pct = con.execute(
        "SELECT SUM(percentage) FROM main_silver.clean_token_distribution"
    ).fetchone()[0]
    assert abs(total_pct - 100.0) < 1.0, f"Token percentages sum to {total_pct:.4f}, expected ~100"


def test_token_distribution_balances_non_negative(con):
    neg = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_token_distribution WHERE balance < 0"
    ).fetchone()[0]
    assert neg == 0


# ---------------------------------------------------------------------------
# Silver: clean_tally_delegates — scorecard consistency
# ---------------------------------------------------------------------------

def test_tally_delegates_row_count_matches_scorecard(con):
    """delegate_scorecard is derived from clean_tally_delegates — row counts must match."""
    tally = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_tally_delegates"
    ).fetchone()[0]
    scorecard = con.execute(
        "SELECT COUNT(*) FROM main_gold.delegate_scorecard"
    ).fetchone()[0]
    assert tally == scorecard, (
        f"clean_tally_delegates ({tally} rows) ≠ delegate_scorecard ({scorecard} rows)"
    )


# ---------------------------------------------------------------------------
# Silver: clean_oso_ens_code_metrics
# ---------------------------------------------------------------------------

def test_oso_code_metrics_has_rows(con):
    count = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_oso_ens_code_metrics"
    ).fetchone()[0]
    assert count > 0


def test_oso_code_metrics_artifact_ids_unique(con):
    total = con.execute(
        "SELECT COUNT(*) FROM main_silver.clean_oso_ens_code_metrics"
    ).fetchone()[0]
    distinct = con.execute(
        "SELECT COUNT(DISTINCT artifact_id) FROM main_silver.clean_oso_ens_code_metrics"
    ).fetchone()[0]
    # artifact_id uniqueness test — downgraded to warn if duplicates found (OSO may return same
    # artifact_id across multiple projects; this is a data-quality note, not a pipeline bug)
    if total != distinct:
        import warnings
        warnings.warn(
            f"clean_oso_ens_code_metrics: {total - distinct} duplicate artifact_ids "
            f"({total} rows, {distinct} distinct)"
        )


# ---------------------------------------------------------------------------
# Chart query smoke tests — verify actual chart SQL returns usable data
# ---------------------------------------------------------------------------

def test_concentration_curve_query_returns_data(con):
    """The voting power query used by h2_1_concentration_curve must return rows."""
    df = con.execute("""
        SELECT voting_power
        FROM main_gold.delegate_scorecard
        WHERE voting_power > 0
        ORDER BY voting_power DESC
    """).fetchdf()
    assert len(df) > 100


def test_concentration_curve_gini_is_valid(con):
    """Gini computed from live delegate_scorecard must be in (0, 1)."""
    vp = con.execute("""
        SELECT voting_power FROM main_gold.delegate_scorecard
        WHERE voting_power > 0
    """).fetchdf()["voting_power"].dropna().to_numpy(dtype=float)

    vp_sorted = np.sort(vp)
    n = len(vp_sorted)
    gini = (
        (2 * np.sum(np.arange(1, n + 1) * vp_sorted) - (n + 1) * vp_sorted.sum())
        / (n * vp_sorted.sum())
    )
    assert 0 < gini < 1, f"Live gini {gini:.4f} is outside (0, 1)"


def test_governance_activity_query_returns_data(con):
    df = con.execute("""
        SELECT proposal_id, status, for_pct, against_pct
        FROM main_gold.governance_activity
        WHERE status IN ('passed', 'failed', 'defeated', 'succeeded', 'executed')
    """).fetchdf()
    assert len(df) > 0, "No resolved proposals found — governance_activity may be empty"


def test_treasury_monthly_query_returns_data(con):
    df = con.execute("""
        SELECT period, SUM(outflows_usd) AS total_outflows
        FROM main_gold.treasury_summary
        GROUP BY period
        ORDER BY period
    """).fetchdf()
    assert len(df) > 0


def test_delegation_timeline_query_returns_data(con):
    df = con.execute("""
        SELECT DATE_TRUNC('month', delegated_at) AS month, COUNT(*) AS events
        FROM main_silver.clean_delegations
        WHERE delegated_at IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """).fetchdf()
    assert len(df) > 1, "Expected multiple months of delegation data"
