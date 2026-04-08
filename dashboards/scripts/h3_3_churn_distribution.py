"""
H3.3 — Low re-delegation churn
Churn count distribution: number of delegate changes per address across the
full study window (Nov 2021 – Mar 2026, ~4.3 years), shown on a log y-axis.
Heavy left-skew confirms low churn. Threshold signal: mean changes/year < 0.3.
Self-delegations (delegator = delegate) excluded.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Study window from data
WINDOW_START  = "2021-11-08"   # first delegation in bronze layer
WINDOW_END    = "2026-03-06"   # data cutoff
WINDOW_YEARS  = 4.33           # approximate span used for mean/yr calculation

BUCKET_MAX    = 5              # "5+" bucket for anything ≥ this
THRESHOLD_YR  = 0.3            # mean changes/year threshold signal

COLOR_BAR     = "#8B93D0"      # blue-purple bars
COLOR_MEAN    = "#C0392B"      # red mean line
COLOR_MEDIAN  = "#27AE60"      # green median line

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, float, float, float]:
    """
    Returns:
        dist_df   — DataFrame with columns: bucket (str), n_addresses (int)
        mean_chg  — mean changes per delegator (all time)
        median_chg — median changes per delegator
        pct_zero  — % of delegators with 0 changes
    """
    con = get_connection()

    dist_df = con.execute(f"""
        WITH excl_self AS (
            SELECT delegator, delegate, delegated_at
            FROM main_silver.clean_delegations
            WHERE delegator != delegate
              AND delegate != '0x0000000000000000000000000000000000000000'
        ),
        with_prev AS (
            SELECT
                delegator,
                delegate,
                delegated_at,
                LAG(delegate) OVER (PARTITION BY delegator ORDER BY delegated_at) AS prev_delegate
            FROM excl_self
        ),
        changes AS (
            SELECT
                delegator,
                SUM(
                    CASE WHEN prev_delegate IS NOT NULL
                              AND delegate != prev_delegate THEN 1 ELSE 0 END
                ) AS n_changes
            FROM with_prev
            GROUP BY delegator
        ),
        bucketed AS (
            SELECT
                CASE WHEN n_changes >= {BUCKET_MAX} THEN {BUCKET_MAX}
                     ELSE CAST(n_changes AS INTEGER) END AS bucket_ord,
                CASE WHEN n_changes >= {BUCKET_MAX} THEN '{BUCKET_MAX}+'
                     ELSE CAST(n_changes AS VARCHAR) END AS bucket,
                delegator
            FROM changes
        )
        SELECT bucket_ord, bucket, COUNT(*) AS n_addresses
        FROM bucketed
        GROUP BY bucket_ord, bucket
        ORDER BY bucket_ord
    """).df()

    stats = con.execute(f"""
        WITH excl_self AS (
            SELECT delegator, delegate, delegated_at
            FROM main_silver.clean_delegations
            WHERE delegator != delegate
              AND delegate != '0x0000000000000000000000000000000000000000'
        ),
        with_prev AS (
            SELECT delegator, delegate, delegated_at,
                   LAG(delegate) OVER (PARTITION BY delegator ORDER BY delegated_at) AS prev_delegate
            FROM excl_self
        ),
        changes AS (
            SELECT delegator,
                   SUM(CASE WHEN prev_delegate IS NOT NULL
                                 AND delegate != prev_delegate THEN 1 ELSE 0 END) AS n_changes
            FROM with_prev
            GROUP BY delegator
        )
        SELECT
            COUNT(*)                                                                    AS total,
            AVG(n_changes)                                                              AS mean_chg,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY n_changes)                     AS median_chg,
            SUM(CASE WHEN n_changes = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)         AS pct_zero
        FROM changes
    """).fetchone()

    total, mean_chg, median_chg, pct_zero = stats
    return dist_df, float(mean_chg), float(median_chg), float(pct_zero)


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _build_chart(
    dist_df: pd.DataFrame,
    mean_chg: float,
    median_chg: float,
) -> go.Figure:
    mean_per_yr = mean_chg / WINDOW_YEARS

    buckets = dist_df["bucket"].tolist()
    counts  = dist_df["n_addresses"].tolist()

    # Plotly needs numeric x for line positions; use index positions
    x_positions = list(range(len(buckets)))

    fig = go.Figure()

    # Bars
    fig.add_trace(go.Bar(
        x=buckets,
        y=counts,
        name=f"# addresses (log scale)",
        marker_color=COLOR_BAR,
        marker_line=dict(width=0),
        width=0.65,
    ))

    # Mean vertical line — expressed as fractional x position
    # mean_chg is the mean number of total changes; map onto x-axis (0-indexed buckets)
    # Clamp to visible range
    mean_x = min(mean_chg, BUCKET_MAX - 0.5)
    fig.add_vline(
        x=mean_x,
        line=dict(color=COLOR_MEAN, width=2),
        annotation_text=f"Mean {mean_per_yr:.3f}/yr",
        annotation_position="top right",
        annotation_font=dict(size=12, color=COLOR_MEAN),
    )

    # Median annotation (always 0 — show as text on bar, not as a line on top of x=0 bar)
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode="lines",
        name=f"Median ({int(median_chg)})",
        line=dict(color=COLOR_MEDIAN, width=2),
        showlegend=True,
    ))

    fig.update_layout(
        xaxis=dict(
            title="Number of delegate changes (full study window, Nov 2021 – Mar 2026)",
            tickfont=dict(size=12, color="#4A5568"),
            title_font=dict(size=12, color="#4A5568"),
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title="Number of addresses (log scale)",
            type="log",
            tickfont=dict(size=11, color="#4A5568"),
            title_font=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#F0F0F0",
            zeroline=False,
            tickformat=",",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=80, b=60, l=80, r=40),
        height=460,
        bargap=0.15,
    )

    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(
    dist_df: pd.DataFrame,
    mean_chg: float,
    pct_zero: float,
) -> None:
    mean_per_yr = mean_chg / WINDOW_YEARS
    total = dist_df["n_addresses"].sum()
    ever_churned = total - int(dist_df.loc[dist_df["bucket"] == "0", "n_addresses"].iloc[0])

    card_css = """
    <style>
    .stat-card {
        background: #F7FAFC; border: 1px solid #E2E8F0;
        border-radius: 8px; padding: 16px 20px; text-align: center;
    }
    .stat-value { font-size: 28px; font-weight: 700; color: #2D3748; margin-bottom: 4px; }
    .stat-label { font-size: 12px; color: #718096; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-value">{pct_zero:.1f}%</div>
          <div class="stat-label">of delegators made <b>zero</b> changes<br>over the full study window</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-value">{mean_per_yr:.4f}</div>
          <div class="stat-label">mean delegate changes per year<br>(threshold signal: &lt;0.3)</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-value">{ever_churned:,}</div>
          <div class="stat-label">delegators ever re-delegated<br>out of {total:,} total</div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_churn_distribution() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Number of delegate changes per address across the full study window "
        "(Nov 2021 – Mar 2026, ~4.3 years), on a log y-axis. "
        "Heavy left-skew confirms low churn. "
        "Threshold signal: mean changes/year &lt;0.3.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading churn distribution…"):
        dist_df, mean_chg, median_chg, pct_zero = _load_data()

    if dist_df.empty:
        st.warning("No delegation data found.")
        return

    fig = _build_chart(dist_df, mean_chg, median_chg)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    _render_cards(dist_df, mean_chg, pct_zero)

    mean_per_yr = mean_chg / WINDOW_YEARS
    st.caption(
        f"{pct_zero:.1f}% of delegators made zero delegate changes over the full study window. "
        f"Mean changes/year = {mean_per_yr:.4f} — far below the 0.3 threshold signal. "
        "Log scale on y-axis is intentional — linear scale would render the 1+ bars nearly invisible "
        "against the 0-change bar."
    )
    st.caption(
        "**Sources:** ENS on-chain DelegateChanged events (bronze layer). "
        "Self-delegations excluded."
    )
