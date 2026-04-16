"""
H2.3 — Weak small-holder voice
Visual 4: Small-holder vote coherence — do they vote as a bloc?
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Threshold & paths
# ---------------------------------------------------------------------------

SMALL_HOLDER_PERCENTILE = 0.80

# Raw JSON path — bypasses the broken vote_choice mapping in the silver model
_TALLY_VOTES_JSON = str(
    Path(__file__).parent.parent.parent / "bronze" / "governance" / "tally_votes.json"
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, float]:
    con = get_connection()

    df = con.execute(f"""
        WITH raw_votes AS (
            SELECT
                voter,
                proposal_id,
                support                             AS vote_choice,
                CAST(weight AS DOUBLE) / 1e18       AS weight
            FROM read_json(
                '{_TALLY_VOTES_JSON}',
                columns = {{
                    voter:       'VARCHAR',
                    proposal_id: 'VARCHAR',
                    support:     'VARCHAR',
                    weight:      'VARCHAR'
                }}
            )
            WHERE support IN ('for', 'against', 'abstain')
        ),
        threshold AS (
            SELECT PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY weight) AS p80
            FROM raw_votes
        ),
        actual_totals AS (
            SELECT
                proposal_id,
                SUM(CASE WHEN vote_choice = 'for'     THEN weight ELSE 0 END) AS for_votes,
                SUM(CASE WHEN vote_choice = 'against' THEN weight ELSE 0 END) AS against_votes
            FROM raw_votes
            GROUP BY proposal_id
        ),
        proposal_outcomes AS (
            SELECT
                p.proposal_id,
                LEFT(p.title, 55) AS title,
                p.start_date,
                atot.for_votes,
                atot.against_votes,
                CASE WHEN atot.for_votes > atot.against_votes THEN 'for' ELSE 'against' END
                    AS winning_side
            FROM main_silver.clean_tally_proposals p
            JOIN actual_totals atot ON p.proposal_id = atot.proposal_id
            WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
              AND (atot.for_votes + atot.against_votes) > 0
        ),
        small_votes AS (
            SELECT
                v.proposal_id,
                SUM(CASE WHEN v.vote_choice = 'for'     THEN v.weight ELSE 0 END) AS small_for,
                SUM(CASE WHEN v.vote_choice = 'against' THEN v.weight ELSE 0 END) AS small_against
            FROM raw_votes v
            CROSS JOIN threshold t
            WHERE v.weight < t.p80
              AND v.vote_choice IN ('for', 'against')
            GROUP BY v.proposal_id
        )
        SELECT
            po.proposal_id,
            po.title,
            po.start_date,
            po.winning_side,
            po.for_votes,
            po.against_votes,
            COALESCE(sv.small_for,     0) AS small_for,
            COALESCE(sv.small_against, 0) AS small_against,
            -- alignment: fraction of small-holder weight that sided with the winner
            CASE
                WHEN po.winning_side = 'for'
                THEN COALESCE(sv.small_for, 0)
                     / NULLIF(COALESCE(sv.small_for, 0) + COALESCE(sv.small_against, 0), 0)
                ELSE COALESCE(sv.small_against, 0)
                     / NULLIF(COALESCE(sv.small_for, 0) + COALESCE(sv.small_against, 0), 0)
            END AS winner_alignment,
            t.p80 AS threshold_p80
        FROM proposal_outcomes po
        LEFT JOIN small_votes sv ON po.proposal_id = sv.proposal_id
        CROSS JOIN threshold t
        WHERE (COALESCE(sv.small_for, 0) + COALESCE(sv.small_against, 0)) > 0
        ORDER BY po.start_date
    """).df()

    threshold_p80 = float(df["threshold_p80"].iloc[0]) if len(df) else 0.0
    return df, threshold_p80


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    scores = df["winner_alignment"].dropna()

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=scores,
        nbinsx=10,
        marker_color="#3B4EC8",
        opacity=0.80,
        hovertemplate="Alignment %{x:.2f}–%{x:.2f}<br>Proposals: %{y}<extra></extra>",
        name="Proposals",
    ))

    mean_val = float(scores.mean())

    # Mean line
    fig.add_vline(
        x=mean_val,
        line=dict(color="#2D8A6E", dash="dash", width=2),
        annotation_text=f"Mean {mean_val:.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#2D8A6E", size=12),
    )

    # 0.5 reference (perfectly split)
    fig.add_vline(
        x=0.5,
        line=dict(color="#CBD5E0", dash="dot", width=1.5),
        annotation_text="50/50 split",
        annotation_position="top left",
        annotation_font=dict(color="#CBD5E0", size=11),
    )

    fig.update_layout(
        xaxis=dict(
            title=dict(
                text="Fraction of small-holder weight voting with the winning side",
                font=dict(size=13, color="#4A5568"),
            ),
            range=[-0.05, 1.05],
            tickformat=".0%",
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Number of proposals", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
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
        margin=dict(t=80, b=70, l=70, r=40),
        height=420,
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


def _render_cards(df: pd.DataFrame, threshold_p80: float) -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    scores = df["winner_alignment"].dropna()
    mean_val   = round(float(scores.mean()), 2)
    median_val = round(float(scores.median()), 2)
    # Fraction of proposals where small holders voted majority-against-winner
    contrarian_pct = round((scores < 0.5).mean() * 100, 1)
    # Fraction where they aligned strongly with winner (>= 0.75)
    aligned_pct    = round((scores >= 0.75).mean() * 100, 1)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Alignment summary</div>
            <div class="stat-row">Mean alignment with winner:
            <span class="stat-value">{mean_val:.2f}</span></div>
            <div class="stat-row">Median: <span class="stat-value">{median_val:.2f}</span></div>
            <div class="stat-row">Proposals with strong alignment (≥75%):
            <span class="stat-value">{aligned_pct:.0f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Contrarian signal</div>
            <div class="stat-row">Proposals where small holders sided <em>against</em>
            the eventual winner (majority):
            <span class="stat-value-warn">{contrarian_pct:.0f}%</span></div>
            <div class="stat-row">A flat distribution suggests no coordinated bloc —
            small holders fragment across both sides.</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Interpretation</div>
            <div class="stat-row">A distribution concentrated near 0.5 would indicate
            fragmentation (no coalition). Clustering near 1.0 would suggest bloc behavior.
            Even a coherent bloc cannot overcome the weight deficit shown in Visual 1.</div>
            <div class="stat-row">Small holder = &lt;<span class="stat-value">{threshold_p80:.0f} ENS</span>.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_small_holder_alignment() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "For each on-chain proposal, this shows the fraction of small-holder vote weight "
        "that sided with the eventual winning outcome. "
        "1.0 = small holders voted unanimously with the winner; "
        "0.0 = they voted unanimously against the winner; "
        "0.5 = perfectly split. "
        "A distribution scattered around 0.5 indicates fragmentation — no organized coalition.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Computing small-holder alignment…"):
        df, threshold_p80 = _load_data()

    fig = _build_chart(df)
    render_chart(fig, key="dl_h23_small_holder_alignment", filename="small_holder_alignment")

    _render_cards(df, threshold_p80)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "**Sources:** ENS Tally on-chain governance votes and proposals. "
        f"Small holder = bottom {int(SMALL_HOLDER_PERCENTILE * 100)}th percentile "
        f"of voters by ENS token weight cast (< {threshold_p80:.0f} ENS). "
        "Only proposals where at least one small-holder vote was cast are included. "
        "Alignment = fraction of small-holder weight on the winning side."
    )
