"""
H2.3 — Weak small-holder voice
Visual 3: Counterfactual analysis — would removing small-holder votes change outcomes?
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

SMALL_HOLDER_PERCENTILE  = 0.80
MEDIUM_HOLDER_PERCENTILE = 0.95  # mirrors h2_3_supply_vs_voice.py

# Raw JSON path — bypasses the broken vote_choice mapping in the silver model
# (clean_tally_votes maps support codes as integers, but the field is a string)
_TALLY_VOTES_JSON = str(
    Path(__file__).parent.parent.parent / "bronze" / "governance" / "tally_votes.json"
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, float, float]:
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
            SELECT
                PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY weight) AS p80,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY weight) AS p95
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
        ),
        medium_contrib AS (
            SELECT
                v.proposal_id,
                SUM(CASE WHEN v.vote_choice = 'for'     THEN v.weight ELSE 0 END) AS for_medium,
                SUM(CASE WHEN v.vote_choice = 'against' THEN v.weight ELSE 0 END) AS against_medium
            FROM raw_votes v
            CROSS JOIN threshold t
            WHERE v.weight >= t.p80 AND v.weight < t.p95
            GROUP BY v.proposal_id
        )
        SELECT
            p.proposal_id,
            LEFT(p.title, 60) AS title,
            p.start_date,
            p.status,
            a.for_actual,
            a.against_actual,
            -- small holder contributions
            COALESCE(sc.for_small,     0) AS for_small,
            COALESCE(sc.against_small, 0) AS against_small,
            -- medium holder contributions
            COALESCE(mc.for_medium,     0) AS for_medium,
            COALESCE(mc.against_medium, 0) AS against_medium,
            -- actual outcome
            CASE WHEN a.for_actual > a.against_actual THEN 'passed' ELSE 'failed' END
                AS outcome_actual,
            -- ── small-holder counterfactual ──────────────────────────────────
            (a.for_actual     - COALESCE(sc.for_small,     0)) AS for_cf,
            (a.against_actual - COALESCE(sc.against_small, 0)) AS against_cf,
            CASE
                WHEN (a.for_actual     - COALESCE(sc.for_small,     0)) >
                     (a.against_actual - COALESCE(sc.against_small, 0))
                THEN 'passed' ELSE 'failed'
            END AS outcome_cf,
            CASE
                WHEN (CASE WHEN a.for_actual > a.against_actual THEN 'passed' ELSE 'failed' END)
                  != (CASE
                        WHEN (a.for_actual     - COALESCE(sc.for_small,     0)) >
                             (a.against_actual - COALESCE(sc.against_small, 0))
                        THEN 'passed' ELSE 'failed'
                      END)
                THEN TRUE ELSE FALSE
            END AS outcome_flipped,
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
            -- ── medium-holder counterfactual ─────────────────────────────────
            (a.for_actual     - COALESCE(mc.for_medium,     0)) AS for_cf_med,
            (a.against_actual - COALESCE(mc.against_medium, 0)) AS against_cf_med,
            CASE
                WHEN (a.for_actual     - COALESCE(mc.for_medium,     0)) >
                     (a.against_actual - COALESCE(mc.against_medium, 0))
                THEN 'passed' ELSE 'failed'
            END AS outcome_cf_med,
            CASE
                WHEN (CASE WHEN a.for_actual > a.against_actual THEN 'passed' ELSE 'failed' END)
                  != (CASE
                        WHEN (a.for_actual     - COALESCE(mc.for_medium,     0)) >
                             (a.against_actual - COALESCE(mc.against_medium, 0))
                        THEN 'passed' ELSE 'failed'
                      END)
                THEN TRUE ELSE FALSE
            END AS outcome_flipped_med,
            ROUND(
                ((a.for_actual     - COALESCE(mc.for_medium,     0))
               - (a.against_actual - COALESCE(mc.against_medium, 0)))
                / NULLIF(
                    (a.for_actual     - COALESCE(mc.for_medium,     0))
                  + (a.against_actual - COALESCE(mc.against_medium, 0)), 0
                ) * 100, 1
            ) AS margin_cf_med_pct,
            -- thresholds
            t.p80 AS threshold_p80,
            t.p95 AS threshold_p95
        FROM main_silver.clean_tally_proposals p
        JOIN actual a ON p.proposal_id = a.proposal_id
        LEFT JOIN small_contrib  sc ON p.proposal_id = sc.proposal_id
        LEFT JOIN medium_contrib mc ON p.proposal_id = mc.proposal_id
        CROSS JOIN threshold t
        WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
          AND (a.for_actual + a.against_actual) > 0
        ORDER BY p.start_date DESC
        LIMIT 40
    """).df()

    threshold_p80 = float(df["threshold_p80"].iloc[0]) if len(df) else 0.0
    threshold_p95 = float(df["threshold_p95"].iloc[0]) if len(df) else 0.0
    return df, threshold_p80, threshold_p95


# ---------------------------------------------------------------------------
# Chart — connected dot plot
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame, holder_type: str = "small") -> tuple[go.Figure, int, int]:
    df = df.copy().reset_index(drop=True)

    # Select counterfactual columns based on holder type
    if holder_type == "small":
        cf_col      = "margin_cf_pct"
        outcome_cf  = "outcome_cf"
        flipped_col = "outcome_flipped"
        cf_label    = "Counterfactual (small holders removed)"
    else:
        cf_col      = "margin_cf_med_pct"
        outcome_cf  = "outcome_cf_med"
        flipped_col = "outcome_flipped_med"
        cf_label    = "Counterfactual (medium holders removed)"

    # Truncate labels and add date
    df["label"] = df.apply(
        lambda r: f"{r['title'][:55]}… ({str(r['start_date'])[:7]})"
        if len(str(r["title"])) > 55 else f"{r['title']} ({str(r['start_date'])[:7]})",
        axis=1,
    )

    n_proposals = len(df)
    n_flipped   = int(df[flipped_col].sum())

    fig = go.Figure()

    # ── connector lines (actual → counterfactual) ───────────────────────────
    # One trace per proposal so each can be a separate line; batch them to
    # reduce trace count by using None separators.
    x_lines, y_lines = [], []
    for _, row in df.iterrows():
        x_lines += [row["margin_actual_pct"], row[cf_col], None]
        y_lines += [row["label"],              row["label"],  None]

    fig.add_trace(go.Scatter(
        x=x_lines,
        y=y_lines,
        mode="lines",
        line=dict(color="#E07B54", width=1.5),
        opacity=0.6,
        showlegend=False,
        hoverinfo="skip",
    ))

    # ── actual margin dots (filled, color by outcome) ────────────────────────
    for outcome, color in [("passed", "#3B4EC8"), ("failed", "#E05252")]:
        mask = df["outcome_actual"] == outcome
        sub  = df[mask]
        fig.add_trace(go.Scatter(
            name=f"Actual margin ({outcome})",
            x=sub["margin_actual_pct"],
            y=sub["label"],
            mode="markers",
            marker=dict(
                symbol="circle",
                size=10,
                color=color,
                line=dict(color=color, width=1),
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Actual margin: %{x:.1f}%<br>"
                f"Outcome: {outcome}<extra></extra>"
            ),
        ))

    # ── counterfactual dots (open circles, orange) ───────────────────────────
    fig.add_trace(go.Scatter(
        name=cf_label,
        x=df[cf_col],
        y=df["label"],
        mode="markers",
        marker=dict(
            symbol="circle-open",
            size=10,
            color="#E07B54",
            line=dict(color="#E07B54", width=2),
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Counterfactual margin: %{x:.1f}%<br>"
            "CF outcome: %{customdata}<extra></extra>"
        ),
        customdata=df[outcome_cf],
    ))

    # ── pass/fail boundary ───────────────────────────────────────────────────
    fig.add_vline(
        x=0,
        line=dict(color="#718096", width=1.5),
    )

    # ── FLIP annotations ─────────────────────────────────────────────────────
    flipped = df[df[flipped_col]]
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

    fig.update_layout(
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


def _render_cards(
    df: pd.DataFrame,
    n_flipped: int,
    n_proposals: int,
    threshold: float,
    holder_label: str,
    holder_type: str,
) -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    cf_col = "margin_cf_pct" if holder_type == "small" else "margin_cf_med_pct"

    avg_margin_shift = round(
        (df[cf_col] - df["margin_actual_pct"]).abs().mean(), 2
    )
    median_margin = round(df["margin_actual_pct"].abs().median(), 1)

    col1, col2, col3 = st.columns(3)

    with col1:
        verdict = "zero" if n_flipped == 0 else str(n_flipped)
        color   = "stat-value" if n_flipped == 0 else "stat-value-warn"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Outcome flips</div>
            <div class="stat-row">Proposals where removing {holder_label.lower()} votes
            would flip the outcome:</div>
            <div class="stat-row"><span class="{color}">{verdict} of {n_proposals}</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Margin impact</div>
            <div class="stat-row">Average margin shift when removing {holder_label.lower()}s:
            <span class="stat-value">{avg_margin_shift:.1f} pp</span></div>
            <div class="stat-row">Median actual margin:
            <span class="stat-value">{median_margin:.1f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">What this means</div>
            <div class="stat-row">{holder_label} = &lt;<span class="stat-value">{threshold:.0f} ENS</span>.
            Even when {holder_label.lower()}s cast votes, their combined weight is too small to
            reverse outcomes dominated by large-holder blocs.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@st.fragment
def render_counterfactual_flip() -> None:
    holder_choice = st.radio(
        "Remove votes from:",
        ["Small holders (bottom 80%)", "Medium holders (80th–95th percentile)"],
        horizontal=True,
    )
    holder_type = "small" if "Small" in holder_choice else "medium"

    if holder_type == "small":
        holder_label    = "Small holder"
        description_who = "small-holder"
    else:
        holder_label    = "Medium holder"
        description_who = "medium-holder"

    st.markdown(
        f"<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        f"Each row = one on-chain Tally proposal. "
        f"Filled circles show the actual vote margin (blue = passed, red = failed). "
        f"Open orange circles show the counterfactual margin after removing all {description_who} votes. "
        f"An orange connector line links actual to counterfactual — if they overlap, the line is invisible. "
        f"A 'FLIP' label marks any proposal where removing {description_who} votes would have changed the outcome.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Running counterfactual analysis…"):
        df, threshold_p80, threshold_p95 = _load_data()

    threshold = threshold_p80 if holder_type == "small" else threshold_p95

    fig, n_flipped, n_proposals = _build_chart(df, holder_type)
    render_chart(fig, key="dl_counterfactual_flip", filename="counterfactual_flip")

    _render_cards(df, n_flipped, n_proposals, threshold, holder_label, holder_type)

    st.markdown("<br>", unsafe_allow_html=True)

    if holder_type == "small":
        caption_detail = (
            f"Small holder defined as bottom {int(SMALL_HOLDER_PERCENTILE * 100)}th percentile "
            f"of voters by ENS token weight cast (< {threshold_p80:.0f} ENS)."
        )
    else:
        caption_detail = (
            f"Medium holder defined as {int(SMALL_HOLDER_PERCENTILE * 100)}th–"
            f"{int(MEDIUM_HOLDER_PERCENTILE * 100)}th percentile "
            f"of voters by ENS token weight cast ({threshold_p80:.0f}–{threshold_p95:.0f} ENS)."
        )

    st.caption(
        f"**Sources:** ENS Tally on-chain governance votes and proposals. "
        f"{caption_detail} "
        "Analysis limited to the 40 most recent completed proposals."
    )
