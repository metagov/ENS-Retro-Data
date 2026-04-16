"""
C2 / H4.1 — Participation variance diagnostic
Before testing whether complexity discourages participation, confirm that
participation varies meaningfully across proposals on both Snapshot and Tally.
High coefficient of variation (CV > 0.5) justifies deeper attribution analysis.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

_SNAPSHOT_PRE  = "#3B4EC8"
_SNAPSHOT_POST = "#9BA8E8"
_TALLY_PRE     = "#E05252"
_TALLY_POST    = "#F0A8A8"

_CUTOFF = pd.Timestamp("2024-01-01")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()

    snapshot_df = con.execute("""
        SELECT
            p.proposal_id,
            p.title,
            CAST(p.start_date AS DATE) AS date,
            COUNT(DISTINCT v.voter) AS unique_voters,
            'Snapshot' AS platform
        FROM main_silver.clean_snapshot_proposals p
        LEFT JOIN main_silver.clean_snapshot_votes v ON p.proposal_id = v.proposal_id
        WHERE p.status = 'closed'
        GROUP BY p.proposal_id, p.title, p.start_date
    """).df()

    tally_df = con.execute("""
        SELECT
            p.proposal_id,
            p.title,
            p.start_date AS date,
            COUNT(DISTINCT v.voter) AS unique_voters,
            'Tally' AS platform
        FROM main_silver.clean_tally_proposals p
        LEFT JOIN main_silver.clean_tally_votes v ON p.proposal_id = v.proposal_id
        WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued')
        GROUP BY p.proposal_id, p.title, p.start_date
    """).df()

    df = pd.concat([snapshot_df, tally_df], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["period"] = df["date"].apply(lambda d: "Pre-2024" if d < _CUTOFF else "Post-2024")
    df = df.sort_values("date")
    return df


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _build_box_chart(platform_df: pd.DataFrame, platform: str, color_pre: str, color_post: str) -> go.Figure:
    fig = go.Figure()

    for period, color in [("Pre-2024", color_pre), ("Post-2024", color_post)]:
        sub = platform_df[platform_df["period"] == period]
        if sub.empty:
            continue
        fig.add_trace(go.Box(
            y=sub["unique_voters"],
            name=period,
            marker=dict(color=color, opacity=0.65, size=6),
            line=dict(color=color),
            boxpoints="all",
            jitter=0.4,
            pointpos=0,
            customdata=sub[["title"]],
            hovertemplate="<b>%{customdata[0]}</b><br>Voters: %{y}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text=platform,
            font=dict(size=17, color="#2D3748"),
            x=0,
            xanchor="left",
        ),
        yaxis=dict(
            title=dict(text="Unique voters", font=dict(size=12, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        xaxis=dict(tickfont=dict(size=12, color="#2D3748")),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=80, b=50, l=60, r=20),
        height=400,
    )
    return fig


def _build_scatter_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    for platform, color in [("Snapshot", _SNAPSHOT_PRE), ("Tally", _TALLY_PRE)]:
        sub = df[df["platform"] == platform].copy().sort_values("date").reset_index(drop=True)
        sub["smooth"] = sub["unique_voters"].rolling(3, min_periods=1).mean()

        fig.add_trace(go.Scatter(
            x=sub["date"],
            y=sub["unique_voters"],
            mode="markers",
            name=platform,
            marker=dict(color=color, size=7, opacity=0.5),
            customdata=sub[["title"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{x|%b %Y}<br>Voters: %{y}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=sub["date"],
            y=sub["smooth"],
            mode="lines",
            name=f"{platform} (3-proposal avg)",
            line=dict(color=color, width=2),
            hoverinfo="skip",
        ))

    # 2024 divider
    fig.add_vline(
        x=_CUTOFF.timestamp() * 1000,
        line=dict(color="#999", dash="dash", width=1.5),
        annotation_text="2024",
        annotation_position="top",
        annotation_font=dict(size=12, color="#718096"),
    )

    fig.update_layout(
        title=dict(
            text="Voter turnout over time (per proposal)",
            font=dict(size=20, color="#2D3748"),
            x=0,
            xanchor="left",
        ),
        xaxis=dict(
            title=dict(text="Proposal date", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Unique voters", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=100, b=60, l=70, r=40),
        height=400,
    )
    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(df: pd.DataFrame) -> None:
    card_css = """
    <style>
    .pv-card {
        background: #F7F8FC;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 4px 0;
    }
    .pv-card-title { font-size: 13px; font-weight: 700; margin-bottom: 6px; }
    .pv-row { font-size: 12px; color: #4A5568; line-height: 1.85; }
    .pv-value { font-weight: 600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    cols = st.columns(4)
    specs = [
        ("Snapshot", "Pre-2024",  _SNAPSHOT_PRE),
        ("Snapshot", "Post-2024", _SNAPSHOT_POST),
        ("Tally",    "Pre-2024",  _TALLY_PRE),
        ("Tally",    "Post-2024", _TALLY_POST),
    ]

    for col, (platform, period, color) in zip(cols, specs):
        sub = df[(df["platform"] == platform) & (df["period"] == period)]["unique_voters"]
        if sub.empty:
            with col:
                st.markdown(f"""
                <div class="pv-card">
                    <div class="pv-card-title" style="color:{color};">{platform} · {period}</div>
                    <div class="pv-row">No data</div>
                </div>""", unsafe_allow_html=True)
            continue
        median = int(sub.median())
        std = int(sub.std()) if len(sub) > 1 else 0
        cv = round(sub.std() / sub.mean(), 2) if sub.mean() > 0 and len(sub) > 1 else 0
        cv_label = "high" if cv >= 0.5 else "low"
        with col:
            st.markdown(f"""
            <div class="pv-card">
                <div class="pv-card-title" style="color:{color};">{platform} · {period}</div>
                <div class="pv-row">Proposals: <span class="pv-value">{len(sub)}</span></div>
                <div class="pv-row">Median: <span class="pv-value">{median:,}</span></div>
                <div class="pv-row">Std dev: <span class="pv-value">{std:,}</span></div>
                <div class="pv-row">CV: <span class="pv-value">{cv} ({cv_label})</span></div>
            </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_participation_variance() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Prerequisite check for H4.1: does turnout differ meaningfully across proposals? "
        "Each platform is split at 2024 to surface whether participation patterns shifted. "
        "CV &ge; 0.5 confirms variation is real and worth attributing to drivers like proposal complexity.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading participation data…"):
        df = _load_data()

    snapshot_df = df[df["platform"] == "Snapshot"]
    tally_df    = df[df["platform"] == "Tally"]

    col1, col2 = st.columns(2)
    with col1:
        fig_snap = _build_box_chart(snapshot_df, "Snapshot", _SNAPSHOT_PRE, _SNAPSHOT_POST)
        render_chart(fig_snap, key="dl_c2_box_snapshot", filename="participation_box_snapshot")
    with col2:
        fig_tally = _build_box_chart(tally_df, "Tally", _TALLY_PRE, _TALLY_POST)
        render_chart(fig_tally, key="dl_c2_box_tally", filename="participation_box_tally")

    _render_cards(df)

    st.markdown("<br>", unsafe_allow_html=True)

    fig_scatter = _build_scatter_chart(df)
    render_chart(fig_scatter, key="dl_c2_turnout_scatter", filename="participation_turnout_scatter")

    st.caption("Sources: Snapshot GraphQL API (snapshot_votes, snapshot_proposals) · Tally GraphQL API (tally_votes, tally_proposals) · warehouse/ens_retro.duckdb")
