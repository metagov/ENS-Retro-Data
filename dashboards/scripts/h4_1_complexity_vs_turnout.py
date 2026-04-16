"""
H4.1 — Complexity vs turnout
Box plots: distribution of unique voter count across proposals grouped by
LLM-assessed complexity score (1–5).  Tests whether harder-to-evaluate
proposals attract fewer participants.

Discrete scores (1–5) make box plots more honest than scatter plots:
each box shows the voter-count distribution for all proposals at that
score level, making direction and spread immediately readable.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

from scripts.chart_utils import CHART_CONFIG, WATERMARK
from scripts.db import get_connection
from scripts.proposal_type import classify_proposals

_SNAPSHOT_COLOR = "#3B4EC8"
_TALLY_COLOR    = "#E05252"

_LLM_DIMS = [
    ("cognitive_load",     "Cognitive load"),
    ("technical_depth",    "Technical depth"),
    ("context_dependency", "Context dependency"),
    ("time_to_evaluate",   "Time to evaluate"),
]


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
            p.body,
            CAST(p.start_date AS DATE)          AS date,
            COUNT(DISTINCT v.voter)              AS unique_voters,
            'Snapshot'                           AS platform
        FROM main_silver.clean_snapshot_proposals p
        LEFT JOIN main_silver.clean_snapshot_votes v ON p.proposal_id = v.proposal_id
        WHERE p.status = 'closed'
        GROUP BY p.proposal_id, p.title, p.body, p.start_date
    """).df()

    tally_df = con.execute("""
        SELECT
            p.proposal_id,
            p.title,
            p.body,
            p.start_date                        AS date,
            COUNT(DISTINCT v.voter)             AS unique_voters,
            'Tally'                             AS platform
        FROM main_silver.clean_tally_proposals p
        LEFT JOIN main_silver.clean_tally_votes v ON p.proposal_id = v.proposal_id
        WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued')
        GROUP BY p.proposal_id, p.title, p.body, p.start_date
    """).df()

    df = pd.concat([snapshot_df, tally_df], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])

    # LLM-assessed complexity dimensions (cached per proposal_id)
    df = classify_proposals(df)

    # LLM composite: mean of the four dimensions, rounded to nearest integer
    dim_cols = [c for c, _ in _LLM_DIMS]
    df["llm_composite"] = df[dim_cols].mean(axis=1).round().astype(int).clip(1, 5)

    return df


# ---------------------------------------------------------------------------
# Chart helper
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)  # reproducible jitter


def _build_strip_median(
    sub: pd.DataFrame,
    x_col: str,
    x_label: str,
    platform: str,
    color: str,
    fill_color: str,
) -> go.Figure:
    """
    Strip plot + median line with IQR band for a single platform.

    Individual proposals are semi-transparent dots (jittered horizontally so
    overlapping scores don't pile up).  Outliers are just dots — they don't
    compress the rest of the chart.  The median line and IQR band show the
    directional trend clearly.
    """
    fig = go.Figure()
    scores = list(range(1, 6))
    sub = sub.dropna(subset=[x_col, "unique_voters"])

    # ── Strip dots ────────────────────────────────────────────────────────
    for score in scores:
        bucket = sub[sub[x_col] == score]
        if bucket.empty:
            continue
        jitter = _RNG.uniform(-0.18, 0.18, size=len(bucket))
        fig.add_trace(go.Scatter(
            x=score + jitter,
            y=bucket["unique_voters"],
            mode="markers",
            name="Proposals",
            legendgroup="dots",
            showlegend=(score == 1),
            marker=dict(color=color, size=7, opacity=0.45,
                        line=dict(width=0.5, color="white")),
            customdata=bucket[["title"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"{x_label}: {score}<br>"
                "Voters: %{y:,}<extra></extra>"
            ),
        ))

    # ── Median + IQR ─────────────────────────────────────────────────────
    medians, q25s, q75s, xs = [], [], [], []
    for score in scores:
        bucket = sub[sub[x_col] == score]["unique_voters"]
        if len(bucket) < 2:
            continue
        xs.append(score)
        medians.append(bucket.median())
        q25s.append(bucket.quantile(0.25))
        q75s.append(bucket.quantile(0.75))

    if xs:
        fig.add_trace(go.Scatter(
            x=xs + xs[::-1],
            y=q75s + q25s[::-1],
            fill="toself",
            fillcolor=fill_color,
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=xs,
            y=medians,
            mode="lines+markers",
            name="Median",
            legendgroup="median",
            showlegend=True,
            line=dict(color=color, width=2.5),
            marker=dict(color=color, size=9, symbol="diamond",
                        line=dict(width=1.5, color="white")),
            hovertemplate=(
                "Median<br>"
                f"{x_label}: %{{x}}<br>"
                "Median voters: %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text=platform,
            font=dict(size=17, color=color),
            x=0, xanchor="left",
        ),
        xaxis=dict(
            title=dict(text=x_label + "  (1 = easy, 5 = hardest)", font=dict(size=12, color="#4A5568")),
            tickvals=scores,
            ticktext=[str(s) for s in scores],
            tickfont=dict(size=13, color="#4A5568"),
            showgrid=False,
            range=[0.5, 5.5],
        ),
        yaxis=dict(
            title=dict(text="Unique voters", font=dict(size=12, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0", zeroline=False,
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04,
            xanchor="left", x=0,
            font=dict(size=11, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        annotations=[WATERMARK],
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=70, b=60, l=60, r=20),
        height=400,
    )
    return fig


_PLATFORMS = [
    ("Snapshot", _SNAPSHOT_COLOR, "rgba(59,78,200,0.12)"),
    ("Tally",    _TALLY_COLOR,    "rgba(224,82,82,0.12)"),
]


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _spearman_label(r: float, p: float) -> str:
    sig = "✓" if p < 0.05 else "ns"
    direction = "negative" if r < 0 else "positive"
    a = abs(r)
    strength = "strong" if a >= 0.4 else "moderate" if a >= 0.25 else "weak"
    return f"{direction}, {strength} (ρ = {r:.2f}, {sig})"


def _render_cards(df: pd.DataFrame) -> None:
    card_css = """
    <style>
    .cx-card {
        background: #F7F8FC; border-radius: 8px;
        padding: 14px 18px; margin: 4px 0;
    }
    .cx-title { font-size: 13px; font-weight: 700; margin-bottom: 6px; }
    .cx-row   { font-size: 12px; color: #4A5568; line-height: 1.9; }
    .cx-val   { font-weight: 600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    all_dims = [("llm_composite", "LLM Composite")] + list(_LLM_DIMS)
    cols = st.columns(len(all_dims))

    for col, (metric, label) in zip(cols, all_dims):
        with col:
            rows = []
            for platform, color in [("Snapshot", _SNAPSHOT_COLOR), ("Tally", _TALLY_COLOR)]:
                sub = df[df["platform"] == platform].dropna(subset=[metric, "unique_voters"])
                if sub.empty or sub[metric].nunique() < 2:
                    continue
                r, p = stats.spearmanr(sub[metric], sub["unique_voters"])
                rows.append(
                    f'<div class="cx-row" style="margin-top:4px;">'
                    f'<span style="color:{color};font-weight:700">{platform}</span><br>'
                    f'<span class="cx-val">{_spearman_label(r, p)}</span></div>'
                )
            st.markdown(f"""
            <div class="cx-card">
                <div class="cx-title">{label}</div>
                {''.join(rows) if rows else '<div class="cx-row">No data</div>'}
            </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_complexity_vs_turnout() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Each dot is one proposal. The diamond line connects median voter count at each score level "
        "(1 = easy, 5 = hardest); the shaded band spans the IQR (25th–75th percentile). "
        "Scores are rated by Claude Haiku on four dimensions that capture participation barriers "
        "beyond readability: domain expertise required, reliance on off-chain context, and total "
        "evaluation effort. A downward median line from left to right supports H4.1.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading proposals and scoring complexity…"):
        df = _load_data()

    all_dims = [("llm_composite", "LLM Composite")] + list(_LLM_DIMS)
    tab_labels = [label for _, label in all_dims]
    tabs = st.tabs(tab_labels)

    for tab, (col, label) in zip(tabs, all_dims):
        with tab:
            c1, c2 = st.columns(2)
            for st_col, (platform, color, fill_color) in zip([c1, c2], _PLATFORMS):
                sub = df[df["platform"] == platform]
                with st_col:
                    st.plotly_chart(
                        _build_strip_median(sub, col, label, platform, color, fill_color),
                        use_container_width=True,
                        config=CHART_CONFIG,
                    )

    st.markdown("##### Spearman correlation with voter turnout")
    st.markdown(
        "<p style='color:#718096; font-size:12px; margin-bottom:8px;'>"
        "Spearman ρ is used instead of Pearson r because scores are ordinal (1–5). "
        "✓ = significant at p &lt; 0.05; ns = not significant.</p>",
        unsafe_allow_html=True,
    )
    _render_cards(df)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "LLM complexity scored by Claude Haiku per proposal (cached). "
        "LLM Composite = mean of cognitive_load, technical_depth, context_dependency, "
        "time_to_evaluate — rounded to nearest integer. "
        "Sources: Snapshot · Tally · warehouse/ens_retro.duckdb"
    )
