"""Tests for pure computation functions in dashboard scripts.

No database or Streamlit required — all functions under test are
pure Python/NumPy/Pandas transformations.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# H2.1 — _compute_curve and _top1_share
# ---------------------------------------------------------------------------

from scripts.h2_1_concentration_curve import _compute_curve, _top1_share


def test_compute_curve_cumulative_sums_to_100():
    vp_df = pd.DataFrame({"voting_power": [100.0, 50.0, 25.0, 25.0]})
    curve = _compute_curve(vp_df)
    assert abs(curve["cumulative_vp_pct"].iloc[-1] - 100.0) < 0.01


def test_compute_curve_pct_delegates_ends_at_100():
    vp_df = pd.DataFrame({"voting_power": [10.0, 20.0, 30.0]})
    curve = _compute_curve(vp_df)
    assert abs(curve["pct_delegates"].iloc[-1] - 100.0) < 0.01


def test_compute_curve_is_monotonically_increasing():
    vp_df = pd.DataFrame({"voting_power": [100.0, 50.0, 25.0, 10.0, 5.0]})
    curve = _compute_curve(vp_df)
    assert (curve["cumulative_vp_pct"].diff().dropna() >= 0).all()


def test_top1_share_single_dominant_delegate():
    """If the top delegate holds all VP, top-1% share should be 100%."""
    vp_df = pd.DataFrame({"voting_power": [1000.0] + [1.0] * 99})
    curve = _compute_curve(vp_df)
    top1 = _top1_share(curve)
    assert top1 > 90  # dominant holder


def test_top1_share_perfect_equality():
    """If all delegates hold equal VP, top-1% share ≈ 1%."""
    vp_df = pd.DataFrame({"voting_power": [100.0] * 100})
    curve = _compute_curve(vp_df)
    top1 = _top1_share(curve)
    assert abs(top1 - 1.0) < 1.0  # ~1%, within 1 percentage point


# ---------------------------------------------------------------------------
# H6.2 reputation lock-in — _classify
# ---------------------------------------------------------------------------

from scripts.h6_2_reputation_lock_in import _classify, VP_THRESHOLD, PARTICIPATION_THRESHOLD


def _make_row(vp_k: float, participation_rate: float) -> pd.Series:
    return pd.Series({"vp_k": vp_k, "participation_rate": participation_rate})


def test_classify_lock_in_zone():
    row = _make_row(vp_k=VP_THRESHOLD + 100, participation_rate=PARTICIPATION_THRESHOLD - 10)
    assert _classify(row) == "Lock-in zone (high VP, <50% participation)"


def test_classify_active():
    row = _make_row(vp_k=VP_THRESHOLD + 100, participation_rate=PARTICIPATION_THRESHOLD + 10)
    assert _classify(row) == "Active (>50% participation)"


def test_classify_low_vp_low_activity():
    row = _make_row(vp_k=VP_THRESHOLD - 50, participation_rate=PARTICIPATION_THRESHOLD - 10)
    assert _classify(row) == "Low VP + low activity"


def test_classify_at_exact_participation_threshold_is_active():
    """At exactly the threshold, should be active (>= check)."""
    row = _make_row(vp_k=VP_THRESHOLD + 100, participation_rate=PARTICIPATION_THRESHOLD)
    assert _classify(row) == "Active (>50% participation)"


def test_classify_at_exact_vp_threshold_below_participation_is_lock_in():
    """At exactly VP threshold (>= check) with low participation → lock-in zone."""
    row = _make_row(vp_k=VP_THRESHOLD, participation_rate=PARTICIPATION_THRESHOLD - 10)
    assert _classify(row) == "Lock-in zone (high VP, <50% participation)"


# ---------------------------------------------------------------------------
# Nakamoto coefficient — verified against known distributions
# ---------------------------------------------------------------------------

def _nakamoto(voting_powers: list) -> int:
    """Compute Nakamoto coefficient directly (without the gold table)."""
    vp = np.sort(np.array(voting_powers, dtype=float))[::-1]
    total = np.sum(vp)
    cumulative = np.cumsum(vp)
    return int(np.searchsorted(cumulative, total * 0.5, side="right") + 1)


def test_nakamoto_one_dominant_delegate():
    """One delegate holds >50% → Nakamoto = 1."""
    assert _nakamoto([600, 100, 100, 100, 100]) == 1


def test_nakamoto_two_needed():
    """Two delegates needed for >50%."""
    assert _nakamoto([300, 250, 100, 100, 100, 100, 50]) == 2


def test_nakamoto_perfect_equality_ten():
    """10 equal delegates each hold 10% → need 6 to pass 50%."""
    assert _nakamoto([100] * 10) == 6


def test_nakamoto_single_delegate():
    """Single delegate always has Nakamoto = 1."""
    assert _nakamoto([100]) == 1


# ---------------------------------------------------------------------------
# Gini coefficient — edge cases
# ---------------------------------------------------------------------------

def _gini(values: list) -> float:
    vp = np.sort(np.array(values, dtype=float))
    n = len(vp)
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * vp) - (n + 1) * np.sum(vp)) / (n * np.sum(vp)))


def test_gini_perfect_equality():
    """All equal shares → Gini = 0."""
    assert abs(_gini([100, 100, 100, 100])) < 1e-9


def test_gini_perfect_inequality():
    """One holder, many zeros (approximated) → Gini close to 1."""
    values = [1000] + [0.001] * 999
    assert _gini(values) > 0.99


def test_gini_bounded():
    """Gini must be in [0, 1] for any non-negative distribution."""
    import random
    random.seed(42)
    values = [random.uniform(0.1, 1000) for _ in range(200)]
    g = _gini(values)
    assert 0.0 <= g <= 1.0
