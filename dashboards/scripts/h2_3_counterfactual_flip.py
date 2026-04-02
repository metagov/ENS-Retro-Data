"""
H2.3 — Weak small-holder voice
Visual 3: Counterfactual analysis — would removing small-holder votes change outcomes?
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Threshold & paths
# ---------------------------------------------------------------------------

SMALL_HOLDER_PERCENTILE = 0.80

# Raw JSON path — bypasses the broken vote_choice mapping in the silver model
# (clean_tally_votes maps support codes as integers, but the field is a string)
_TALLY_VOTES_JSON = str(
    Path(__file__).parent.parent.parent / "bronze" / "governance" / "tally_votes.json"
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, float]:
    con = get_connection()

    # Use for_votes / against_votes from clean_tally_proposals (authoritative totals
    # from Tally) as the "actual" baseline, and read individual vote weight+direction
    # directly from the raw JSON (the silver model maps support as integer but the
    # field is a string, so vote_choice is always 'unknown' in the silver layer).
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
        actual AS (
            SELECT
                proposal_id,
                SUM(CASE WHEN vote_choice = 'for'     THEN weight ELSE 0 END) AS for_actual,
                SUM(CASE WHEN vote_choice = 'against' THEN weight ELSE 0 END) AS against_actual
            FROM raw_votes
            GROUP BY proposal_id
        ),
        small_contrib AS (
            SELECT
                v.proposal_id,
                SUM(CASE WHEN v.vote_choice = 'for'     THEN v.weight ELSE 0 END) AS for_small,
                SUM(CASE WHEN v.vote_choice = 'against' THEN v.weight ELSE 0 END) AS against_small
            FROM raw_votes v
            CROSS JOIN threshold t
            WHERE v.weight < t.p80
            GROUP BY v.proposal_id
        )
        SELECT
            p.proposal_id,
            LEFT(p.title, 60) AS title,
            p.start_date,
            p.status,
            a.for_actual,
            a.against_actual,
            COALESCE(sc.for_small,     0) AS for_small,
            COALESCE(sc.against_small, 0) AS against_small,
            -- counterfactual totals
            (a.for_actual     - COALESCE(sc.for_small,     0)) AS for_cf,
            (a.against_actual - COALESCE(sc.against_small, 0)) AS against_cf,
            -- actual outcome
            CASE WHEN a.for_actual > a.against_actual THEN 'passed' ELSE 'failed' END
                AS outcome_actual,
            -- counterfactual outcome
            CASE
                WHEN (a.for_actual     - COALESCE(sc.for_small,     0)) >
                     (a.against_actual - COALESCE(sc.against_small, 0))
                THEN 'passed' ELSE 'failed'
            END AS outcome_cf,
            -- did outcome flip?
            CASE
                WHEN (CASE WHEN a.for_actual > a.against_actual THEN 'passed' ELSE 'failed' END)
                  != (CASE
                        WHEN (a.for_actual     - COALESCE(sc.for_small,     0)) >
                             (a.against_actual - COALESCE(sc.against_small, 0))
                        THEN 'passed' ELSE 'failed'
                      END)
                THEN TRUE ELSE FALSE
            END AS outcome_flipped,
            -- margin as % of total (positive = for wins)
            ROUND(
                (a.for_actual - a.against_actual)
                / NULLIF(a.for_actual + a.against_actual, 0) * 100, 1
            ) AS margin_actual_pct,
            ROUND(
                ((a.for_actual     - COALESCE(sc.for_small,     0))
               - (a.against_actual - COALESCE(sc.against_small, 0)))
                / NULLIF(
                    (a.for_actual     - COALESCE(sc.for_small,     0))
                  + (a.against_actual - COALESCE(sc.against_small, 0)), 0
                ) * 100, 1
            ) AS margin_cf_pct,
            t.p80 AS threshold_p80
        FROM main_silver.clean_tally_proposals p
        JOIN actual a ON p.proposal_id = a.proposal_id
        LEFT JOIN small_contrib sc ON p.proposal_id = sc.proposal_id
        CROSS JOIN threshold t
        WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
          AND (a.for_actual + a.against_actual) > 0
        ORDER BY p.start_date DESC
        LIMIT 40
    """).df()

    threshold_p80 = float(df["threshold_p80"].iloc[0]) if len(df) else 0.0
    return df, threshold_p80


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    df = df.copy().reset_index(drop=True)

    # Truncate labels and add date
    df["label"] = df.apply(
        lambda r: f"{r['title'][:55]}… ({str(r['start_date'])[:7]})"
        if len(str(r["title"])) > 55 else f"{r['title']} ({str(r['start_date'])[:7]})",
        axis=1,
    )

    # Color by outcome
    bar_colors_actual = [
        "#3B4EC8" if r["outcome_actual"] == "passed" else "#E05252"
        for _, r in df.iterrows()
    ]

    fig = go.Figure()

    # Actual margins
    fig.add_trace(go.Bar(
        name="Actual margin",
        y=df["label"],
        x=df["margin_actual_pct"],
        orientation="h",
        marker_color=bar_colors_actual,
        opacity=0.85,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Actual margin: %{x:.1f}%<br>"
            "Outcome: %{customdata}<extra></extra>"
        ),
        customdata=df["outcome_actual"],
    ))

    # Counterfactual margins (outline only)
    fig.add_trace(go.Bar(
        name="Counterfactual margin (small holders removed)",
        y=df["label"],
        x=df["margin_cf_pct"],
        orientation="h",
        marker_color="rgba(0,0,0,0)",
        marker_line=dict(color="#E07B54", width=2),
        opacity=1.0,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Counterfactual margin: %{x:.1f}%<br>"
            "CF outcome: %{customdata}<extra></extra>"
        ),
        customdata=df["outcome_cf"],
    ))

    # Pass/fail boundary
    fig.add_vline(
        x=0,
        line=dict(color="#718096", width=1.5),
    )

    # Flip markers
    flipped = df[df["outcome_flipped"]]
    for _, row in flipped.iterrows():
        fig.add_annotation(
            x=row["margin_actual_pct"],
            y=row["label"],
            text="⬤ FLIP",
            showarrow=False,
            font=dict(color="#D97706", size=11, family="sans-serif"),
            xanchor="left" if row["margin_actual_pct"] >= 0 else "right",
            xshift=8 if row["margin_actual_pct"] >= 0 else -8,
        )

    n_proposals = len(df)
    n_flipped   = int(df["outcome_flipped"].sum())

    fig.update_layout(
        barmode="overlay",
        xaxis=dict(
            title=dict(
                text="Vote margin (for − against) as % of total weight cast",
                font=dict(size=13, color="#4A5568"),
            ),
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(size=10, color="#2D3748"),
            autorange="reversed",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=80, b=60, l=420, r=60),
        height=max(420, n_proposals * 22),
    )

    return fig, n_flipped, n_proposals


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


def _render_cards(df: pd.DataFrame, n_flipped: int, n_proposals: int, threshold_p80: float) -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    avg_margin_shift = round(
        (df["margin_cf_pct"] - df["margin_actual_pct"]).abs().mean(), 2
    )
    median_margin = round(df["margin_actual_pct"].abs().median(), 1)

    col1, col2, col3 = st.columns(3)

    with col1:
        verdict = "zero" if n_flipped == 0 else str(n_flipped)
        color = "stat-value" if n_flipped == 0 else "stat-value-warn"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Outcome flips</div>
            <div class="stat-row">Proposals where removing small-holder votes
            would flip the outcome:</div>
            <div class="stat-row"><span class="{color}">{verdict} of {n_proposals}</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Margin impact</div>
            <div class="stat-row">Average margin shift when removing small holders:
            <span class="stat-value">{avg_margin_shift:.1f} pp</span></div>
            <div class="stat-row">Median actual margin:
            <span class="stat-value">{median_margin:.1f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">What this means</div>
            <div class="stat-row">Small holder = &lt;<span class="stat-value">{threshold_p80:.0f} ENS</span>.
            Even when small holders cast votes, their combined weight is too small to
            reverse outcomes dominated by large-holder blocs.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_counterfactual_flip() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Each row = one on-chain Tally proposal. "
        "Solid bars show the actual vote margin (blue = passed, red = failed). "
        "Outlined orange bars show the counterfactual margin after removing all small-holder votes. "
        "A 'FLIP' label marks any proposal where removing small-holder votes would have changed the outcome.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Running counterfactual analysis…"):
        df, threshold_p80 = _load_data()

    fig, n_flipped, n_proposals = _build_chart(df)
    st.plotly_chart(fig, use_container_width=True)

    _render_cards(df, n_flipped, n_proposals, threshold_p80)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "**Sources:** ENS Tally on-chain governance votes and proposals. "
        f"Small holder defined as bottom {int(SMALL_HOLDER_PERCENTILE * 100)}th percentile "
        f"of voters by ENS token weight cast (< {threshold_p80:.0f} ENS). "
        "Analysis limited to the 40 most recent completed proposals."
    )
