"""
Hx.1 — Outcome robustness
Do the highest-VP delegates reflect consensus, or drive it?

Methodology (after Goldberg & Schär, JBR 2023):
  VP.ALL  — the actual winning choice, weighted by all VP cast
  VP.1    — the single highest-VP voter's choice on each proposal
  VP.2UP  — the counterfactual outcome if the highest-VP voter had not voted

High VP.1/VP.ALL agreement alongside frequent VP.2UP flips is evidence of de facto
authority rather than consensus-reflection — the whale does not merely predict the
outcome, they materially determine it.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

# Academic benchmark from Goldberg & Schär (2023): VP.1 matched VP.ALL in 94.8% of proposals
PAPER_BENCHMARK = 94.8


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    """Load per-proposal outcome robustness metrics for Tally on-chain proposals."""
    con = get_connection()

    sql = """
        WITH votes AS (
            SELECT voter, proposal_id, vote_choice, weight
            FROM main_silver.clean_tally_votes
            WHERE vote_choice IN ('for', 'against', 'abstain')
        ),
        proposal_vp AS (
            SELECT
                proposal_id,
                SUM(CASE WHEN vote_choice = 'for'     THEN weight ELSE 0 END) AS for_vp,
                SUM(CASE WHEN vote_choice = 'against'  THEN weight ELSE 0 END) AS against_vp,
                SUM(CASE WHEN vote_choice = 'abstain'  THEN weight ELSE 0 END) AS abstain_vp,
                SUM(weight) AS total_vp,
                COUNT(DISTINCT voter) AS n_voters
            FROM votes
            GROUP BY proposal_id
        ),
        vp_all AS (
            SELECT
                proposal_id, for_vp, against_vp, abstain_vp, total_vp, n_voters,
                CASE
                    WHEN for_vp >= against_vp AND for_vp >= abstain_vp THEN 'for'
                    WHEN against_vp > for_vp AND against_vp >= abstain_vp THEN 'against'
                    ELSE 'abstain'
                END AS winning_choice
            FROM proposal_vp
            WHERE total_vp > 0
        ),
        ranked_votes AS (
            SELECT proposal_id, voter, vote_choice, weight,
                ROW_NUMBER() OVER (PARTITION BY proposal_id ORDER BY weight DESC) AS rn
            FROM votes
        ),
        top_voter AS (
            SELECT proposal_id, voter AS top_voter, vote_choice AS top_choice, weight AS top_vp
            FROM ranked_votes WHERE rn = 1
        ),
        cf_vp AS (
            SELECT
                v.proposal_id,
                SUM(CASE WHEN v.vote_choice = 'for'    AND v.voter != t.top_voter THEN v.weight ELSE 0 END) AS cf_for,
                SUM(CASE WHEN v.vote_choice = 'against' AND v.voter != t.top_voter THEN v.weight ELSE 0 END) AS cf_against,
                SUM(CASE WHEN v.vote_choice = 'abstain' AND v.voter != t.top_voter THEN v.weight ELSE 0 END) AS cf_abstain
            FROM votes v
            JOIN top_voter t USING (proposal_id)
            GROUP BY v.proposal_id
        ),
        cf_outcome AS (
            SELECT
                proposal_id,
                CASE
                    WHEN (cf_for + cf_against + cf_abstain) = 0 THEN NULL  -- only 1 voter total
                    WHEN cf_for >= cf_against AND cf_for >= cf_abstain THEN 'for'
                    WHEN cf_against > cf_for AND cf_against >= cf_abstain THEN 'against'
                    ELSE 'abstain'
                END AS vp2up_outcome
            FROM cf_vp
        )
        SELECT
            p.proposal_id,
            tp.title,
            t.top_voter,
            COALESCE(NULLIF(cw.ens_name, ''), LEFT(LOWER(t.top_voter), 10) || '…') AS top_voter_label,
            t.top_choice,
            t.top_vp,
            p.total_vp,
            p.for_vp,
            p.against_vp,
            p.abstain_vp,
            p.n_voters,
            p.winning_choice,
            (t.top_choice = p.winning_choice) AS vp1_matched,
            c.vp2up_outcome,
            (c.vp2up_outcome IS NOT NULL AND c.vp2up_outcome != p.winning_choice) AS vp2up_flipped
        FROM vp_all p
        JOIN top_voter t USING (proposal_id)
        JOIN cf_outcome c USING (proposal_id)
        JOIN main_silver.clean_tally_proposals tp USING (proposal_id)
        LEFT JOIN main_silver.address_crosswalk cw ON LOWER(t.top_voter) = cw.address
        WHERE tp.status IN ('executed', 'defeated')
    """

    df = con.execute(sql).df()

    # Compute per-row margin and top-voter share
    def _runner_up(row):
        choices = {"for": row.for_vp, "against": row.against_vp, "abstain": row.abstain_vp}
        others = {k: v for k, v in choices.items() if k != row.winning_choice}
        return max(others.values()) if others else 0.0

    df["winner_vp"] = df.apply(
        lambda r: {"for": r.for_vp, "against": r.against_vp, "abstain": r.abstain_vp}.get(r.winning_choice, 0.0),
        axis=1,
    )
    df["runner_up_vp"] = df.apply(_runner_up, axis=1)
    df["margin_pct"] = (df.winner_vp - df.runner_up_vp) / df.total_vp * 100
    df["top_vp_share_pct"] = df.top_vp / df.total_vp * 100
    df["vp1_matched"] = df["vp1_matched"].astype(bool)
    df["vp2up_flipped"] = df["vp2up_flipped"].astype(bool)

    return df


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def _compute_stats(df: pd.DataFrame) -> dict:
    """Aggregate outcome robustness metrics."""
    n = len(df)
    if n == 0:
        return {"n": 0, "agreement_pct": None, "flip_pct": None, "flip_n": 0}
    agreement = df.vp1_matched.sum() / n * 100
    flip_n    = df.vp2up_flipped.sum()
    flip_pct  = flip_n / n * 100
    return {
        "n": n,
        "agreement_pct": round(agreement, 1),
        "flip_n": int(flip_n),
        "flip_pct": round(flip_pct, 1),
    }


def _top_whales(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Delegates most frequently appearing as the highest-VP voter."""
    grp = (
        df.groupby(["top_voter", "top_voter_label"])
        .agg(
            proposals=("proposal_id", "count"),
            matched=("vp1_matched", "sum"),
        )
        .reset_index()
    )
    grp["alignment_pct"] = grp.matched / grp.proposals * 100
    return grp.sort_values("proposals", ascending=False).head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _chart_agreement_rate(stats: dict) -> go.Figure:
    """Bar chart: VP.1 agreement rate and VP.2UP flip rate for Tally on-chain proposals."""
    metrics = ["VP.1 agreement with outcome", "VP.2UP counterfactual flip rate"]
    values  = [stats["agreement_pct"] or 0, stats["flip_pct"] or 0]
    colors  = ["#3B4EC8", "#E07B54"]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="VP.1 agreement with outcome (VP.ALL)",
        x=["VP.1 Agreement"],
        y=[stats["agreement_pct"] or 0],
        marker_color="#3B4EC8",
        text=[f"{stats['agreement_pct']:.1f}%"],
        textposition="outside",
        textfont=dict(size=13, color="#2D3748"),
        width=0.3,
        offsetgroup=0,
    ))

    fig.add_trace(go.Bar(
        name="VP.2UP counterfactual flip rate",
        x=["VP.2UP Flip Rate"],
        y=[stats["flip_pct"] or 0],
        marker_color="#E07B54",
        text=[f"{stats['flip_pct']:.1f}%"],
        textposition="outside",
        textfont=dict(size=13, color="#2D3748"),
        width=0.3,
        offsetgroup=1,
    ))

    # Academic benchmark reference line
    fig.add_hline(
        y=PAPER_BENCHMARK,
        line_dash="dash",
        line_color="#718096",
        line_width=1.5,
        annotation_text=f"Paper benchmark: {PAPER_BENCHMARK}% (Goldberg & Schär 2023)",
        annotation_position="top right",
        annotation_font=dict(size=11, color="#718096"),
    )

    fig.update_layout(
        title=dict(
            text="Outcome robustness: how often does the top whale side with the winning outcome?",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        barmode="group",
        xaxis=dict(
            tickfont=dict(size=13, color="#4A5568"),
            gridcolor="#E2E8F0",
        ),
        yaxis=dict(
            title=dict(text="% of proposals", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            gridcolor="#E2E8F0", range=[0, 108],
        ),
        legend=dict(
            orientation="h", x=0, y=-0.18, bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color="#4A5568"),
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=80, b=100, l=70, r=40),
        height=440,
    )
    return fig


def _chart_per_proposal(df: pd.DataFrame) -> go.Figure:
    """Scatter: per-proposal top-voter VP share vs winning margin, colored by VP.1 match."""
    fig = go.Figure()

    for matched, color, label in [
        (True,  "#3B4EC8", "Sided with outcome"),
        (False, "#E07B54", "Opposed outcome"),
    ]:
        grp = df[df.vp1_matched == matched]
        if grp.empty:
            continue

        short_title = grp.title.apply(lambda t: (t[:50] + "…") if len(str(t)) > 50 else str(t))
        fig.add_trace(go.Scatter(
            x=grp.top_vp_share_pct,
            y=grp.margin_pct,
            mode="markers",
            name=label,
            marker=dict(
                color=color,
                symbol="circle",
                size=9,
                opacity=0.75,
                line=dict(color="white", width=0.8),
            ),
            customdata=list(zip(short_title, grp.top_voter_label, grp.top_choice, grp.winning_choice)),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Top voter: %{customdata[1]}<br>"
                "Their vote: %{customdata[2]} | Outcome: %{customdata[3]}<br>"
                "VP share: %{x:.1f}% | Margin: %{y:.1f}%"
                "<extra></extra>"
            ),
        ))

    # Quadrant annotation: decisive whale zone
    fig.add_annotation(
        x=70, y=8,
        text="<b>High VP share<br>+ narrow margin</b><br><span style='color:#718096;'>decisive whale zone</span>",
        showarrow=False,
        font=dict(size=10, color="#4A5568"),
        align="center",
        bgcolor="rgba(247,248,252,0.85)",
        bordercolor="#CBD5E0",
        borderwidth=1,
        borderpad=6,
    )

    # Light shading for decisive whale zone (high share, low margin)
    fig.add_shape(
        type="rect",
        x0=50, x1=102,
        y0=0, y1=20,
        fillcolor="rgba(224,123,84,0.06)",
        line=dict(color="rgba(224,123,84,0.3)", width=1, dash="dot"),
    )

    fig.update_layout(
        title=dict(
            text="Per-proposal: top voter's VP share vs. winning margin",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        xaxis=dict(
            title=dict(text="Top voter's share of total VP cast (%)", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            gridcolor="#E2E8F0", range=[-2, 105],
        ),
        yaxis=dict(
            title=dict(text="Winning margin (winner VP − runner-up VP) / total VP (%)", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            gridcolor="#E2E8F0",
        ),
        legend=dict(
            orientation="h", x=0, y=-0.22, bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color="#4A5568"),
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=80, b=120, l=90, r=40),
        height=500,
    )
    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(stats: dict, whales: pd.DataFrame) -> None:
    card_css = """
    <style>
    .sc { background:#F7F8FC; border-radius:8px; padding:16px 20px; margin:4px 0; }
    .sc-t { font-size:14px; font-weight:700; color:#3B4EC8; margin-bottom:8px; }
    .sc-r { font-size:13px; color:#4A5568; line-height:1.9; }
    .sc-v { font-weight:600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    flip_n  = stats["flip_n"]
    total_n = stats["n"]

    whale_lines = "".join(
        f"<span class='sc-v' style='color:#2D8A6E;'>{row.top_voter_label}</span>"
        f" &nbsp;·&nbsp; {int(row.proposals)} proposals &nbsp;·&nbsp; {row.alignment_pct:.0f}% aligned<br>"
        for _, row in whales.iterrows()
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        val   = stats["agreement_pct"]
        color = "#2D8A6E" if (val or 0) >= PAPER_BENCHMARK else "#C44E52"
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">VP.1 / VP.ALL Agreement Rate</div>
            <div class="sc-r">
                <span class="sc-v" style="color:{color}; font-size:22px;">{val:.1f}%</span>
                of proposals matched by the top voter<br>
                <span style="color:#718096;">Paper benchmark: {PAPER_BENCHMARK}% (Goldberg &amp; Schär 2023)</span>
            </div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">VP.2UP Counterfactual Flips</div>
            <div class="sc-r">
                <span class="sc-v" style="color:#E07B54; font-size:22px;">{flip_n}</span>
                of {total_n} proposals would have a different outcome
                if the top voter had not voted<br>
                <span style="color:#718096;">({stats["flip_pct"]:.1f}% flip rate)</span>
            </div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">Most Frequent Top Whales</div>
            <div class="sc-r">
                {whale_lines}
            </div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_outcome_robustness() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Applies the outcome robustness framework of Goldberg &amp; Schär (2023) to ENS on-chain governance. "
        "VP.1 agreement measures how often the single highest-VP voter sides with the final outcome. "
        "VP.2UP counterfactuals recompute each proposal's outcome after removing the top voter's weight — "
        "if the result flips, that voter was decisive. High agreement plus frequent flips signals de facto "
        "centralized authority rather than consensus-reflection.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading vote data…"):
        df = _load_data()

    if df.empty:
        st.warning("No governance vote data found.")
        return

    stats  = _compute_stats(df)
    whales = _top_whales(df)

    _render_cards(stats, whales)

    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Agreement Rate", "Per-Proposal Scatter"])
    with tab1:
        fig_agree = _chart_agreement_rate(stats)
        render_chart(fig_agree, key="dl_hx1_agreement_rate", filename="outcome_robustness_agreement")
    with tab2:
        fig_scatter = _chart_per_proposal(df)
        render_chart(fig_scatter, key="dl_hx1_per_proposal", filename="outcome_robustness_per_proposal")

    st.caption(
        f"Sources: ENS Tally on-chain governance ({stats['n']} finalized proposals: executed or defeated). "
        f"VP.ALL = winning choice by total VP-weighted votes. VP.1 = top voter's choice per proposal. "
        f"VP.2UP = recomputed outcome excluding top voter's weight. "
        f"Vote weights read from raw Tally JSON; vote_choice standardized to for/against/abstain. "
        f"Methodology after Goldberg &amp; Schär, Journal of Business Research 160 (2023) 113764."
    )
