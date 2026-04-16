"""
H2.1 — Token-weighted paradox
Concentration curve: voting power vs delegates (ENS DAO only)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import CHART_CONFIG, WATERMARK
from scripts.db import get_connection


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, int, float]:
    con = get_connection()

    vp_df = con.execute("""
        SELECT voting_power
        FROM main_gold.delegate_scorecard
        WHERE voting_power > 0
        ORDER BY voting_power DESC
    """).df()

    # Read Nakamoto coefficient from the pre-computed decentralization index.
    # voting_power_gini is not stored in the index table, so compute it inline
    # from the already-loaded vp_df (same data, no extra query needed).
    idx = con.execute("""
        SELECT metric, value
        FROM main_gold.decentralization_index
        WHERE metric = 'nakamoto_coefficient'
    """).df().set_index("metric")["value"]

    nakamoto = int(idx["nakamoto_coefficient"])

    vp = np.sort(vp_df["voting_power"].dropna().astype(float).to_numpy())
    n = len(vp)
    gini = round(
        float((2 * np.sum(np.arange(1, n + 1) * vp) - (n + 1) * vp.sum()) / (n * vp.sum())),
        4,
    ) if n > 0 and vp.sum() > 0 else 0.0

    return vp_df, nakamoto, gini


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _compute_curve(vp_df: pd.DataFrame) -> pd.DataFrame:
    df = vp_df.copy().reset_index(drop=True)
    total = len(df)
    total_vp = df["voting_power"].sum()

    df["pct_delegates"] = (df.index + 1) / total * 100
    df["cumulative_vp_pct"] = df["voting_power"].cumsum() / total_vp * 100

    return df


def _top1_share(curve_df: pd.DataFrame) -> float:
    mask = curve_df["pct_delegates"] <= 1.0
    if mask.any():
        return round(curve_df.loc[mask, "cumulative_vp_pct"].iloc[-1], 0)
    return round(curve_df["cumulative_vp_pct"].iloc[0], 0)


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(curve_df: pd.DataFrame, nakamoto: int, gini: float) -> go.Figure:
    x = curve_df["pct_delegates"].values
    y = curve_df["cumulative_vp_pct"].values

    # Perfect equality reference
    eq_x = np.linspace(0, 100, 500)
    eq_y = eq_x

    fig = go.Figure()

    # Perfect equality
    fig.add_trace(go.Scatter(
        x=eq_x,
        y=eq_y,
        mode="lines",
        line=dict(color="#888888", dash="dash", width=2),
        name="Perfect equality",
        hoverinfo="skip",
    ))

    # 50% VP threshold
    fig.add_hline(
        y=50,
        line=dict(color="#D97706", dash="dash", width=1.5),
        annotation_text="50% VP threshold",
        annotation_position="top right",
        annotation_font=dict(color="#D97706", size=13, family="sans-serif"),
    )

    # ENS concentration curve
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="lines",
        line=dict(color="#3B4EC8", width=2.5),
        name=f"ENS (Gini ~{gini}, N={nakamoto})",
        fill="tozeroy",
        fillcolor="rgba(59, 78, 200, 0.08)",
        hovertemplate="Delegates: %{x:.2f}%<br>Cumulative VP: %{y:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="Concentration curve — voting power vs delegates",
            font=dict(size=20, color="#2D3748"),
            x=0,
            xanchor="left",
        ),
        xaxis=dict(
            title=dict(text="Cumulative % of delegates (largest VP first)", font=dict(size=13, color="#4A5568")),
            range=[0, 20],
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Cumulative % of voting power", font=dict(size=13, color="#4A5568")),
            range=[0, 100],
            tickformat=".0f",
            ticksuffix="%",
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
            font=dict(size=13, color="#2D3748"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=100, b=70, l=70, r=40),
        height=480,
        annotations=[WATERMARK],
    )

    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(top1: float, nakamoto: int, gini: float) -> None:
    card_css = """
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
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">ENS DAO</div>
            <div class="stat-row">Top 1% hold <span class="stat-value">~{int(top1)}%</span> VP</div>
            <div class="stat-row">Nakamoto coeff. <span class="stat-value">{nakamoto}</span></div>
            <div class="stat-row">Gini (active VP) <span class="stat-value">{gini}</span></div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-card-title" style="color:#555;">What is the Nakamoto coefficient?</div>
            <div class="stat-row">Minimum number of delegates needed to control 50% of voting power.
            A higher value means power is more distributed.</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-card-title" style="color:#555;">What is the Gini coefficient?</div>
            <div class="stat-row">Measures inequality in voting power (0 = perfect equality,
            1 = one delegate holds all power). Computed on active VP only.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_concentration_curve() -> None:
    # Subtitle
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Largest delegates first (descending). Curve shows cumulative VP captured as you add the "
        "next biggest delegate. X-axis zoomed to 0–20% where all meaningful action occurs.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading governance data…"):
        vp_df, nakamoto, gini = _load_data()

    curve_df = _compute_curve(vp_df)
    top1 = _top1_share(curve_df)

    fig = _build_chart(curve_df, nakamoto, gini)
    st.plotly_chart(fig, width='stretch', config=CHART_CONFIG)

    _render_cards(top1, nakamoto, gini)

    # Source notes
    st.markdown("<br>", unsafe_allow_html=True)
