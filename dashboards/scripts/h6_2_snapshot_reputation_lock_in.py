"""
H6.2 — Reputation lock-in
Activity vs. delegated voting power scatter plot (Snapshot only, past 12 months)
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import CHART_CONFIG, WATERMARK
from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

PARTICIPATION_THRESHOLD = 50  # percent

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        WITH snapshot_proposals_12m AS (
            SELECT COUNT(DISTINCT proposal_id) AS total_proposals
            FROM main_silver.clean_snapshot_proposals
            WHERE start_date >= CURRENT_DATE - INTERVAL '12 months'
        ),
        delegate_votes_12m AS (
            SELECT
                sv.voter AS address,
                COUNT(DISTINCT sv.proposal_id) AS proposals_voted
            FROM main_silver.clean_snapshot_votes sv
            JOIN main_silver.clean_snapshot_proposals sp
                ON sv.proposal_id = sp.proposal_id
            WHERE sp.start_date >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY sv.voter
        ),
        top_delegates AS (
            SELECT address, ens_name, voting_power
            FROM main_gold.delegate_scorecard
            ORDER BY voting_power DESC
            LIMIT 30
        )
        SELECT
            d.address,
            COALESCE(NULLIF(d.ens_name, ''), d.address) AS label,
            d.voting_power,
            d.voting_power / 1000.0                      AS vp_k,
            COALESCE(dv.proposals_voted, 0)              AS proposals_voted,
            tp.total_proposals,
            ROUND(
                COALESCE(dv.proposals_voted, 0)::DOUBLE
                / NULLIF(tp.total_proposals, 0) * 100, 1
            ) AS participation_rate
        FROM top_delegates d
        LEFT JOIN delegate_votes_12m dv ON d.address = dv.address
        CROSS JOIN snapshot_proposals_12m tp
        ORDER BY d.voting_power DESC
    """).df()
    return df


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify(row: pd.Series) -> str:
    if row["participation_rate"] >= PARTICIPATION_THRESHOLD:
        return "Active (>50% participation)"
    else:
        return "Lock-in zone (<50% participation)"


_COLOR_MAP = {
    "Active (>50% participation)": "#5B6AD6",
    "Lock-in zone (<50% participation)": "#E07B54",
}

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["category"] = df.apply(_classify, axis=1)
    df["color"] = df["category"].map(_COLOR_MAP)

    # Normalise dot sizes — largest dot ≈ 60px diameter
    max_vp = df["vp_k"].max()
    sizeref = 2.0 * max_vp / (60 ** 2)

    fig = go.Figure()

    # Lock-in zone background rectangle
    fig.add_shape(
        type="rect",
        x0=0, x1=PARTICIPATION_THRESHOLD,
        y0=0, y1=max_vp * 1.15,
        fillcolor="rgba(224, 123, 84, 0.08)",
        line=dict(width=0),
        layer="below",
    )

    # One trace per category so legend entries are correct
    for cat, color in _COLOR_MAP.items():
        mask = df["category"] == cat
        sub = df[mask]
        fig.add_trace(go.Scatter(
            x=sub["participation_rate"],
            y=sub["vp_k"],
            mode="markers",
            name=cat,
            marker=dict(
                color=color,
                size=sub["vp_k"],
                sizemode="area",
                sizeref=sizeref,
                sizemin=6,
                opacity=0.85,
                line=dict(width=0.5, color="white"),
            ),
            customdata=sub[["label", "vp_k", "proposals_voted", "total_proposals"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "VP: %{customdata[1]:.0f}K<br>"
                "Participation: %{x:.0f}%"
                " (%{customdata[2]:.0f} / %{customdata[3]:.0f} proposals)"
                "<extra></extra>"
            ),
        ))

    # Vertical threshold line at 50%
    fig.add_vline(
        x=PARTICIPATION_THRESHOLD,
        line=dict(color="#888888", dash="dash", width=1.5),
    )

    # "Lock-in zone" annotation
    fig.add_annotation(
        x=2, y=max_vp * 1.08,
        text="Lock-in zone",
        showarrow=False,
        font=dict(color="#E07B54", size=12),
        xanchor="left",
    )

    fig.update_layout(
        xaxis=dict(
            title=dict(text="Vote participation rate — past 12 months", font=dict(size=13, color="#4A5568")),
            range=[-2, 102],
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Delegated VP (thousands)", font=dict(size=13, color="#4A5568")),
            range=[0, max_vp * 1.2],
            tickfont=dict(size=12, color="#4A5568"),
            tickformat=".0f",
            ticksuffix="K",
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
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
        margin=dict(t=80, b=70, l=70, r=40),
        height=500,
    )
    fig.add_annotation(**WATERMARK)

    return fig, df


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_snapshot_activity_vs_vp() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Each dot = one of the top-30 delegates by voting power. "
        "X-axis: Snapshot vote participation rate over the past 12 months. "
        "Y-axis: current delegated VP (thousands). "
        "Dot size proportional to VP. "
        "Orange quadrant (high VP, low activity) = lock-in candidates.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading delegate activity data…"):
        df = _load_data()

    fig, df_classified = _build_chart(df)

    lock_in_count = (df_classified["category"] == "Lock-in zone (<50% participation)").sum()
    total_count = len(df_classified)

    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    st.caption(
        f"**{lock_in_count} of {total_count} top delegates** fall in the lock-in zone "
        f"(<{PARTICIPATION_THRESHOLD}% participation). "
        f"Dot size proportional to delegated VP. "
        f"Participation threshold: ≥{PARTICIPATION_THRESHOLD}% of Snapshot proposals."
    )
    st.caption(
        "**Sources:** ENS Snapshot governance data. Participation rate computed over "
        "Snapshot proposals with start date in the past 12 months. "
        "Voting power from Tally delegate registry."
    )
