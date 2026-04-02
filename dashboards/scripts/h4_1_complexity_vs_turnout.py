"""
H4.1 — Complexity vs turnout
Scatter: per-proposal complexity score vs unique voter count.
Tests whether harder-to-parse proposals attract fewer participants.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.complexity import score_proposals
from scripts.db import get_connection

_SNAPSHOT_COLOR = "#3B4EC8"
_TALLY_COLOR    = "#E05252"


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
            p.choices,
            CAST(p.start_date AS DATE)          AS date,
            COUNT(DISTINCT v.voter)              AS unique_voters,
            'Snapshot'                           AS platform
        FROM main_silver.clean_snapshot_proposals p
        LEFT JOIN main_silver.clean_snapshot_votes v ON p.proposal_id = v.proposal_id
        WHERE p.status = 'closed'
        GROUP BY p.proposal_id, p.title, p.body, p.choices, p.start_date
    """).df()

    tally_df = con.execute("""
        SELECT
            p.proposal_id,
            p.title,
            p.body,
            NULL                                AS choices,
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

    # Score via shared utility (same logic used by future silver model)
    df = score_proposals(df)
    return df


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _trend_line(x: np.ndarray, y: np.ndarray):
    """Return (x_line, y_line) for a linear OLS fit."""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3:
        return None, None
    m, b = np.polyfit(x[mask], y[mask], 1)
    x_line = np.linspace(x[mask].min(), x[mask].max(), 100)
    return x_line, m * x_line + b


def _build_scatter(df: pd.DataFrame, x_col: str, x_label: str) -> go.Figure:
    fig = go.Figure()

    for platform, color in [("Snapshot", _SNAPSHOT_COLOR), ("Tally", _TALLY_COLOR)]:
        sub = df[df["platform"] == platform].dropna(subset=[x_col, "unique_voters"])
        if sub.empty:
            continue

        fig.add_trace(go.Scatter(
            x=sub[x_col],
            y=sub["unique_voters"],
            mode="markers",
            name=platform,
            marker=dict(color=color, size=8, opacity=0.65,
                        line=dict(width=0.5, color="white")),
            customdata=sub[["title", "word_count", "link_count", "fk_grade"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Voters: %{y}<br>"
                f"{x_label}: %{{x:.2f}}<br>"
                "Words: %{customdata[1]} · Links: %{customdata[2]} · FK grade: %{customdata[3]:.1f}"
                "<extra></extra>"
            ),
        ))

        # OLS trend line
        x_line, y_line = _trend_line(sub[x_col].to_numpy(float), sub["unique_voters"].to_numpy(float))
        if x_line is not None:
            fig.add_trace(go.Scatter(
                x=x_line,
                y=y_line,
                mode="lines",
                name=f"{platform} trend",
                line=dict(color=color, width=2, dash="dash"),
                hoverinfo="skip",
            ))

    fig.update_layout(
        title=dict(
            text=f"{x_label} vs unique voters per proposal",
            font=dict(size=19, color="#2D3748"),
            x=0, xanchor="left",
        ),
        xaxis=dict(
            title=dict(text=x_label, font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0", zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Unique voters", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0", zeroline=False,
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04,
            xanchor="left", x=0,
            font=dict(size=12, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=90, b=60, l=70, r=40),
        height=420,
    )
    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _corr_label(r: float) -> str:
    a = abs(r)
    direction = "negative" if r < 0 else "positive"
    if a >= 0.4:
        strength = "moderate–strong"
    elif a >= 0.2:
        strength = "weak"
    else:
        strength = "negligible"
    return f"{direction}, {strength} (r = {r:.2f})"


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
    cols = st.columns(4)
    metrics = [
        ("complexity_score", "Composite score"),
        ("word_count",       "Word count"),
        ("link_count",       "Link count"),
        ("fk_grade",         "FK grade"),
    ]

    for col, (metric, label) in zip(cols, metrics):
        with col:
            rows = []
            for platform, color in [("Snapshot", _SNAPSHOT_COLOR), ("Tally", _TALLY_COLOR)]:
                sub = df[df["platform"] == platform].dropna(subset=[metric, "unique_voters"])
                if sub.empty:
                    continue
                r = sub[metric].corr(sub["unique_voters"])
                rows.append(f'<div class="cx-row" style="margin-top:4px;">'
                            f'<span style="color:{color};font-weight:700">{platform}</span><br>'
                            f'<span class="cx-val">{_corr_label(r)}</span></div>')
            st.markdown(f"""
            <div class="cx-card">
                <div class="cx-title">{label}</div>
                {''.join(rows)}
            </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_complexity_vs_turnout() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Each dot is one proposal. The dashed line is a linear trend. "
        "A downward slope means harder proposals attract fewer voters. "
        "Hover for proposal title and raw component scores.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Scoring proposals…"):
        df = _load_data()

    tab1, tab2, tab3, tab4 = st.tabs([
        "Composite score", "Word count", "Link count", "FK grade"
    ])
    with tab1:
        st.plotly_chart(_build_scatter(df, "complexity_score", "Complexity score (0–1)"), use_container_width=True)
    with tab2:
        st.plotly_chart(_build_scatter(df, "word_count", "Word count"), use_container_width=True)
    with tab3:
        st.plotly_chart(_build_scatter(df, "link_count", "Link count"), use_container_width=True)
    with tab4:
        st.plotly_chart(_build_scatter(df, "fk_grade", "Flesch-Kincaid grade level"), use_container_width=True)

    st.markdown("##### Correlation with voter turnout")
    _render_cards(df)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Complexity score: min-max normalised composite of word count, link count, and FK grade. "
        "FK grade computed on markdown-stripped body text via textstat. "
        "Sources: Snapshot · Tally · warehouse/ens_retro.duckdb"
    )
