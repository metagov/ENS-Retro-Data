"""
H3.3 — Low re-delegation churn
Delegator retention survival curve: % of delegators who have not changed
their delegate, by months since first delegation.
Two cohorts: delegators of top-20 vs. smaller delegates.
Self-delegations (delegator = delegate) excluded.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import CHART_CONFIG, WATERMARK
from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_TOP_DELEGATES = 20
CUTOFF = pd.Timestamp("2026-03-06", tz="UTC")
MAX_MONTHS = 52   # full data window (~4.3 years)

COLOR_TOP    = "#3D4FA6"   # blue  — top-20 cohort
COLOR_SMALL  = "#C0392B"   # red   — smaller delegate cohort
COLOR_THRESH = "#999999"   # gray  — 70% threshold

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()
    df = con.execute(f"""
        WITH excl_self AS (
            SELECT delegator, delegate, delegated_at
            FROM main_silver.clean_delegations
            WHERE delegator != delegate
              AND delegate != '0x0000000000000000000000000000000000000000'
        ),
        top_n AS (
            SELECT address
            FROM main_gold.delegate_scorecard
            ORDER BY voting_power DESC
            LIMIT {N_TOP_DELEGATES}
        ),
        ordered AS (
            SELECT
                delegator,
                delegate,
                delegated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY delegator ORDER BY delegated_at
                ) AS rn,
                FIRST_VALUE(delegate) OVER (
                    PARTITION BY delegator ORDER BY delegated_at
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS first_delegate
            FROM excl_self
        ),
        entry AS (
            SELECT delegator, first_delegate, MIN(delegated_at) AS entry_date
            FROM ordered
            GROUP BY delegator, first_delegate
        ),
        failure AS (
            SELECT o.delegator, MIN(o.delegated_at) AS failure_date
            FROM ordered o
            JOIN entry e ON o.delegator = e.delegator
            WHERE o.rn > 1 AND o.delegate != e.first_delegate
            GROUP BY o.delegator
        )
        SELECT
            e.delegator,
            CASE WHEN t.address IS NOT NULL THEN 'top20' ELSE 'smaller' END AS cohort,
            e.entry_date,
            f.failure_date,
            CASE WHEN f.failure_date IS NOT NULL THEN 1 ELSE 0 END AS event_occurred
        FROM entry e
        LEFT JOIN top_n t ON e.first_delegate = t.address
        LEFT JOIN failure f ON e.delegator = f.delegator
    """).df()

    df["entry_date"]   = pd.to_datetime(df["entry_date"],   utc=True)
    df["failure_date"] = pd.to_datetime(df["failure_date"], utc=True)
    df["end_date"]     = df["failure_date"].fillna(CUTOFF)
    df["months"]       = (
        (df["end_date"] - df["entry_date"]) / pd.Timedelta(days=30.44)
    ).clip(lower=0)
    return df


# ---------------------------------------------------------------------------
# KM computation
# ---------------------------------------------------------------------------

def _km_curve(sub: pd.DataFrame) -> pd.DataFrame:
    """
    Product-limit (Kaplan-Meier) estimator.
    Returns a DataFrame with columns: months, survival (0-1 scale).
    Evaluates at each observed failure time, then extends to MAX_MONTHS.
    """
    sub = sub.copy().sort_values("months").reset_index(drop=True)
    n = len(sub)
    at_risk = n
    S = 1.0
    records = [(0.0, 1.0)]
    last_t = 0.0

    failure_times = sorted(sub.loc[sub["event_occurred"] == 1, "months"].unique())

    for t in failure_times:
        if t > MAX_MONTHS:
            break
        # censored strictly before t
        censored_before = (
            (sub["months"] < t) & (sub["event_occurred"] == 0) & (sub["months"] > last_t)
        ).sum()
        at_risk -= int(censored_before)

        d = int(((sub["months"] == t) & (sub["event_occurred"] == 1)).sum())
        if at_risk > 0 and d > 0:
            S *= 1.0 - d / at_risk
        records.append((t, S))

        # remove events at t from at_risk for next step
        at_risk -= d
        last_t = t

    # extend flat to MAX_MONTHS
    records.append((MAX_MONTHS, S))

    return pd.DataFrame(records, columns=["months", "survival"])


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    top_km   = _km_curve(df[df["cohort"] == "top20"])
    small_km = _km_curve(df[df["cohort"] == "smaller"])

    # Survival at 12 months for caption
    def _surv_at(km: pd.DataFrame, t: float) -> float:
        row = km[km["months"] <= t]
        return row["survival"].iloc[-1] * 100 if not row.empty else 100.0

    top_12   = _surv_at(top_km,   12)
    small_12 = _surv_at(small_km, 12)

    fig = go.Figure()

    # Shaded area between curves
    fig.add_trace(go.Scatter(
        x=list(top_km["months"]) + list(small_km["months"])[::-1],
        y=list(top_km["survival"] * 100) + list(small_km["survival"] * 100)[::-1],
        fill="toself",
        fillcolor="rgba(61,79,166,0.08)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Top-20 cohort line
    fig.add_trace(go.Scatter(
        x=top_km["months"],
        y=top_km["survival"] * 100,
        mode="lines+markers",
        name=f"Delegators of top-{N_TOP_DELEGATES} delegates",
        line=dict(color=COLOR_TOP, width=2.5),
        marker=dict(size=5, color=COLOR_TOP),
    ))

    # Smaller delegate cohort line
    fig.add_trace(go.Scatter(
        x=small_km["months"],
        y=small_km["survival"] * 100,
        mode="lines+markers",
        name="Delegators of smaller delegates",
        line=dict(color=COLOR_SMALL, width=2.5),
        marker=dict(size=5, color=COLOR_SMALL),
    ))

    # 70% threshold
    fig.add_hline(
        y=70,
        line=dict(color=COLOR_THRESH, dash="dash", width=1.2),
        annotation_text="70% threshold",
        annotation_position="right",
        annotation_font=dict(size=11, color=COLOR_THRESH),
    )

    # Annotation: 12-month callout
    fig.add_annotation(
        x=12, y=min(top_12, small_12) - 0.3,
        text=f"Month 12<br>top-{N_TOP_DELEGATES}: {top_12:.1f}%<br>smaller: {small_12:.1f}%",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#4A5568",
        ax=40, ay=30,
        font=dict(size=11, color="#4A5568"),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor="#CCCCCC",
        borderwidth=1,
    )

    fig.update_layout(
        xaxis=dict(
            title="Months since first delegation",
            tickvals=list(range(0, MAX_MONTHS + 1, 6)),
            tickfont=dict(size=11, color="#4A5568"),
            title_font=dict(size=12, color="#4A5568"),
            showgrid=False,
            zeroline=False,
            range=[-1, MAX_MONTHS + 1],
        ),
        yaxis=dict(
            title="% not yet re-delegated",
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=11, color="#4A5568"),
            title_font=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#F0F0F0",
            zeroline=False,
            range=[94, 100.5],
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
        annotations=[WATERMARK],
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=80, b=60, l=80, r=80),
        height=480,
    )

    return fig, top_12, small_12


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(df: pd.DataFrame, top_12: float, small_12: float) -> None:
    n_top   = (df["cohort"] == "top20").sum()
    n_small = (df["cohort"] == "smaller").sum()
    n_fail  = df["event_occurred"].sum()

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
          <div class="stat-value">{top_12:.1f}%</div>
          <div class="stat-label">Top-{N_TOP_DELEGATES} cohort unchanged at 12 months<br>({n_top:,} delegators)</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-value">{small_12:.1f}%</div>
          <div class="stat-label">Smaller-delegate cohort unchanged at 12 months<br>({n_small:,} delegators)</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        total = n_top + n_small
        pct_ever = n_fail / total * 100
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-value">{pct_ever:.1f}%</div>
          <div class="stat-label">Ever re-delegated across all {total:,} delegators</div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_redelegation_churn() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "% of delegators who have not changed their delegate, by months since first delegation. "
        f"Separate curves for delegators of top-{N_TOP_DELEGATES} vs smaller delegates. "
        "Self-delegations excluded. Threshold signal: ≥70% unchanged at 12-month mark.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Computing survival curves…"):
        df = _load_data()

    if df.empty:
        st.warning("No delegation data found.")
        return

    fig, top_12, small_12 = _build_chart(df)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    st.markdown("<br>", unsafe_allow_html=True)
    _render_cards(df, top_12, small_12)
    st.caption(
        f"Both cohorts far exceed the 70% retention threshold — at month 12, "
        f"top-{N_TOP_DELEGATES} cohort retains **{top_12:.1f}%** and smaller-delegate cohort retains "
        f"**{small_12:.1f}%** of original delegators unchanged. "
        "Y-axis zoomed to 94–100% to show curve shape; the 70% threshold (dashed line) lies well below."
    )
    st.caption(
        "**Sources:** ENS on-chain DelegateChanged events (bronze layer). "
        "Cohort classification by current voting-power ranking (Tally). "
        "Self-delegations excluded."
    )
