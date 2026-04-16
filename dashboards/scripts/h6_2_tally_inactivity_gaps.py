"""
H6.2 — Reputation lock-in
Inactivity gaps vs delegation retention: per-delegate activity strip chart.
24-month window Jan 2024 – Dec 2025. Tally (on-chain) only.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

START_DATE  = "2024-01-01"
END_DATE    = "2026-01-01"
N_MONTHS    = 24
N_DELEGATES = 10

# Cell geometry
CELL_WIDTH  = 0.88   # x-width per cell (leaves a small gap)
CELL_HEIGHT = 0.52
CELL_YOFF   = 0.22   # bottom offset within each row

# Colors
COL_ACTIVE   = "#7B89D4"   # purple  — voted in proposals
COL_INACTIVE = "#F0B99B"   # coral   — had proposals, didn't vote
COL_NOPROP   = "#EEEEEE"   # light gray — no proposals that month

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()
    df = con.execute(f"""
        WITH months_series AS (
            SELECT DATE_TRUNC('month', MAKE_DATE(y, m, 1)) AS month
            FROM (VALUES (2024),(2025)) t(y)
            CROSS JOIN (VALUES (1),(2),(3),(4),(5),(6),
                               (7),(8),(9),(10),(11),(12)) s(m)
        ),
        months_with_proposals AS (
            SELECT DISTINCT DATE_TRUNC('month', start_date)::DATE AS month
            FROM main_silver.clean_tally_proposals
            WHERE start_date >= '{START_DATE}'
              AND start_date <  '{END_DATE}'
        ),
        delegate_votes_by_month AS (
            SELECT
                tv.voter                                          AS address,
                DATE_TRUNC('month', tp.start_date)::DATE          AS month,
                COUNT(DISTINCT tv.proposal_id)                    AS votes_cast
            FROM main_silver.clean_tally_votes tv
            JOIN main_silver.clean_tally_proposals tp
                ON tv.proposal_id = tp.proposal_id
            WHERE tp.start_date >= '{START_DATE}'
              AND tp.start_date <  '{END_DATE}'
            GROUP BY tv.voter, DATE_TRUNC('month', tp.start_date)::DATE
        ),
        top_delegates AS (
            SELECT address, ens_name, voting_power
            FROM main_gold.delegate_scorecard
            ORDER BY voting_power DESC
            LIMIT {N_DELEGATES}
        )
        SELECT
            d.address,
            COALESCE(NULLIF(d.ens_name, ''), d.address) AS label,
            d.voting_power,
            ms.month,
            CASE WHEN mwp.month IS NOT NULL THEN 1 ELSE 0 END AS had_proposals,
            COALESCE(v.votes_cast, 0)                          AS votes_cast
        FROM top_delegates d
        CROSS JOIN months_series ms
        LEFT JOIN months_with_proposals mwp ON ms.month = mwp.month
        LEFT JOIN delegate_votes_by_month v
               ON d.address = v.address AND ms.month = v.month
        ORDER BY d.voting_power DESC, ms.month
    """).df()
    df["month"] = pd.to_datetime(df["month"])
    return df


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    delegates = df.groupby("address", sort=False).first().reset_index()
    delegates = delegates.sort_values("voting_power", ascending=False).reset_index(drop=True)

    all_months = sorted(df["month"].unique())
    month_to_j = {m: j for j, m in enumerate(all_months)}
    n = len(delegates)

    fig = go.Figure()

    # Legend proxy traces
    for name, color in [
        ("Voted in proposals", COL_ACTIVE),
        ("Inactive gap",       COL_INACTIVE),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            name=name,
            marker=dict(color=color, symbol="square", size=10, line=dict(width=0)),
            showlegend=True,
        ))

    for i, row in delegates.iterrows():
        address = row["address"]
        del_df  = df[df["address"] == address].sort_values("month")

        y_top = n - i - CELL_YOFF
        y_bot = y_top - CELL_HEIGHT

        for _, mrow in del_df.iterrows():
            j = month_to_j[mrow["month"]]
            if mrow["had_proposals"]:
                color = COL_ACTIVE if mrow["votes_cast"] > 0 else COL_INACTIVE
            else:
                color = COL_NOPROP

            fig.add_shape(
                type="rect",
                x0=j,         x1=j + CELL_WIDTH,
                y0=y_bot,     y1=y_top,
                fillcolor=color,
                line=dict(width=0),
                layer="below",
            )

    # Year boundary
    y_max = n + 0.3
    y_min = -0.3
    fig.add_shape(
        type="line",
        x0=12, x1=12, y0=y_min, y1=y_max,
        line=dict(color="#CCCCCC", width=1),
    )
    fig.add_annotation(x=6,  y=y_max, text="<b>2024</b>",
                       showarrow=False, font=dict(size=12, color="#4A5568"), yanchor="bottom")
    fig.add_annotation(x=18, y=y_max, text="<b>2025</b>",
                       showarrow=False, font=dict(size=12, color="#4A5568"), yanchor="bottom")

    ytick_vals = [n - i - CELL_YOFF - CELL_HEIGHT / 2 for i in range(n)]
    ytick_text = [delegates.iloc[i]["label"] for i in range(n)]

    fig.update_layout(
        xaxis=dict(
            tickvals=list(range(N_MONTHS)),
            ticktext=["J","F","M","A","M","J","J","A","S","O","N","D"] * 2,
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=False,
            zeroline=False,
            range=[-0.5, N_MONTHS - 0.5],
        ),
        yaxis=dict(
            tickvals=ytick_vals,
            ticktext=ytick_text,
            tickfont=dict(size=12, color="#2D3748"),
            showgrid=False,
            zeroline=False,
            range=[y_min, y_max + 0.3],
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
        margin=dict(t=80, b=50, l=120, r=30),
        height=80 + n * 55,
    )

    return fig


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_tally_inactivity_gaps() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Per-delegate strip: active voting months (purple) and inactive gaps (coral). "
        "24-month view, Jan 2024 – Dec 2025. Tally (on-chain) only.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading delegate activity data…"):
        df = _load_data()

    if df.empty:
        st.warning("No Tally data found for the Jan 2024 – Dec 2025 window.")
        return

    fig = _build_chart(df)
    render_chart(fig, key="dl_tally_inactivity", filename="tally_inactivity_gaps", width='stretch')

    proposal_months = df[df["had_proposals"] == 1]
    total_cells     = len(proposal_months)
    inactive_cells  = (proposal_months["votes_cast"] == 0).sum()
    pct_inactive    = round(inactive_cells / total_cells * 100) if total_cells else 0

    st.caption(
        f"Across the top-{N_DELEGATES} delegates and proposal-bearing months in 2024–2025, "
        f"**{inactive_cells} of {total_cells} delegate-month cells ({pct_inactive}%) were inactive gaps** "
        f"(Tally proposals existed but the delegate did not vote). "
        f"Months with no proposals shown in light gray."
    )
    st.caption(
        "**Sources:** ENS Tally on-chain governance data."
    )
