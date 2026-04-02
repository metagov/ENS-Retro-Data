"""
H2.3 — Weak small-holder voice
Visual 1: Supply vs Voice — what small holders hold vs what they exercise on-chain
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------

SMALL_HOLDER_PERCENTILE = 0.80
MEDIUM_HOLDER_PERCENTILE = 0.95

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        WITH threshold AS (
            SELECT
                PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY weight) AS p80,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY weight) AS p95
            FROM main_silver.clean_tally_votes
        ),
        voter_tiers AS (
            SELECT
                v.voter,
                v.weight,
                CASE
                    WHEN v.weight < t.p80 THEN 'Small'
                    WHEN v.weight < t.p95 THEN 'Medium'
                    ELSE 'Large'
                END AS tier
            FROM main_silver.clean_tally_votes v
            CROSS JOIN threshold t
        ),
        voice AS (
            SELECT
                tier,
                SUM(weight)          AS weight_cast,
                COUNT(DISTINCT voter) AS voter_count
            FROM voter_tiers
            GROUP BY tier
        ),
        supply AS (
            SELECT
                CASE
                    WHEN td.balance < t.p80 THEN 'Small'
                    WHEN td.balance < t.p95 THEN 'Medium'
                    ELSE 'Large'
                END AS tier,
                SUM(td.balance) AS total_balance
            FROM main_silver.clean_token_distribution td
            CROSS JOIN threshold t
            GROUP BY 1
        ),
        totals AS (
            SELECT
                SUM(weight_cast)   AS total_voice,
                SUM(voter_count)   AS total_voters
            FROM voice
        )
        SELECT
            v.tier,
            v.weight_cast,
            v.voter_count,
            s.total_balance,
            ROUND(v.weight_cast    / SUM(v.weight_cast) OVER () * 100, 2) AS pct_voice,
            ROUND(s.total_balance  / SUM(s.total_balance) OVER () * 100, 2) AS pct_supply,
            ROUND(v.voter_count    / SUM(v.voter_count) OVER () * 100, 1) AS pct_voters,
            t.p80 AS threshold_p80
        FROM voice v
        JOIN supply s USING (tier)
        CROSS JOIN threshold t
        ORDER BY
            CASE v.tier
                WHEN 'Small'  THEN 1
                WHEN 'Medium' THEN 2
                ELSE 3
            END
    """).df()
    return df


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    tiers = df["tier"].tolist()
    pct_supply = df["pct_supply"].tolist()
    pct_voice  = df["pct_voice"].tolist()

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Share of ENS supply held",
        y=tiers,
        x=pct_supply,
        orientation="h",
        marker_color="#3B4EC8",
        opacity=0.85,
        hovertemplate="%{y}: %{x:.1f}% of total supply<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        name="Share of on-chain voting weight cast",
        y=tiers,
        x=pct_voice,
        orientation="h",
        marker_color="#E07B54",
        opacity=0.85,
        hovertemplate="%{y}: %{x:.1f}% of total vote weight<extra></extra>",
    ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(
            title=dict(text="Share of total (%)", font=dict(size=13, color="#4A5568")),
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(size=13, color="#2D3748"),
            autorange="reversed",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            font=dict(size=12, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=80, b=60, l=80, r=40),
        height=340,
    )

    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

_CARD_CSS = """
<style>
.stat-card {
    background: #F7F8FC;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 4px 0;
}
.stat-card-title {
    font-size: 14px;
    font-weight: 700;
    color: #3B4EC8;
    margin-bottom: 8px;
}
.stat-row {
    font-size: 13px;
    color: #4A5568;
    line-height: 1.8;
}
.stat-value {
    color: #2D8A6E;
    font-weight: 600;
}
.stat-value-warn {
    color: #E07B54;
    font-weight: 600;
}
</style>
"""


def _render_cards(df: pd.DataFrame) -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    small = df[df["tier"] == "Small"].iloc[0]
    large = df[df["tier"] == "Large"].iloc[0]
    threshold_ens = round(small["threshold_p80"], 1)

    # Supply-to-voice ratio for small holders
    ratio = round(small["pct_supply"] / small["pct_voice"], 1) if small["pct_voice"] > 0 else float("inf")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Small holders (bottom 80% of voters)</div>
            <div class="stat-row">Threshold: &lt;<span class="stat-value">{threshold_ens:.0f} ENS</span></div>
            <div class="stat-row">Share of supply: <span class="stat-value">{small['pct_supply']:.1f}%</span></div>
            <div class="stat-row">Share of vote weight: <span class="stat-value-warn">{small['pct_voice']:.1f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Large holders (top 5% of voters)</div>
            <div class="stat-row">Share of supply: <span class="stat-value">{large['pct_supply']:.1f}%</span></div>
            <div class="stat-row">Share of vote weight: <span class="stat-value">{large['pct_voice']:.1f}%</span></div>
            <div class="stat-row">Voter headcount: <span class="stat-value">{large['pct_voters']:.1f}%</span> of all voters</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Voice deficit</div>
            <div class="stat-row">Small holders hold
            <span class="stat-value">{ratio:.1f}×</span> more supply share than
            they exercise in on-chain votes.</div>
            <div class="stat-row">They are numerous by headcount
            (<span class="stat-value">{small['pct_voters']:.0f}%</span> of all voters)
            but near-silent by weight.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_supply_vs_voice() -> None:
    threshold_note = (
        "<b>Small</b> = bottom 80th percentile of on-chain voters by ENS tokens cast "
        "(weight in Tally votes, which records actual token amount). "
        "<b>Medium</b> = 80th–95th percentile. "
        "<b>Large</b> = top 5%."
    )
    with st.expander("How is 'small holder' defined?"):
        st.markdown(
            f"<p style='font-size:13px; color:#4A5568;'>{threshold_note}</p>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Blue bars show each tier's share of total ENS token supply. "
        "Orange bars show each tier's share of total on-chain voting weight actually exercised. "
        "The gap between these two numbers measures the structural voice deficit.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading token and vote data…"):
        df = _load_data()

    fig = _build_chart(df)
    st.plotly_chart(fig, use_container_width=True)

    _render_cards(df)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "**Sources:** ENS on-chain token distribution (Etherscan); "
        "ENS Tally on-chain governance votes. "
        "Tier thresholds derived from the distribution of vote weights in Tally data. "
        "Snapshot votes excluded here because their `voting_power` field reflects delegated power, "
        "not raw token holdings."
    )
