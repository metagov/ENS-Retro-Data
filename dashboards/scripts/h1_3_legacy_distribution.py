"""
H1.3 — Legacy distribution
When was the top 50 delegates' voting power established?
VP origin by era: fraction of top-50 VP locked in by each delegation cohort quarter.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.db import get_connection


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> pd.DataFrame:
    con = get_connection()

    # Approach:
    #   1. Find each delegator's current active delegation (latest delegated_at).
    #   2. Join with current token balances from clean_token_distribution.
    #   3. Restrict to delegators of the top 50 delegates by total current VP
    #      (ENS Nakamoto = 18, so top 50 captures the governing bloc with margin).
    #   4. Tag each delegator by the quarter their current delegation was set.
    #   5. Compute what share of the top-50's combined VP each era accounts for.
    #
    # This answers "when were today's power relationships established?" without
    # requiring historical balance rankings (which are unknowable from available data).
    df = con.execute("""
        WITH current_delegations AS (
            SELECT
                delegator,
                delegate,
                delegated_at,
                ROW_NUMBER() OVER (PARTITION BY delegator ORDER BY delegated_at DESC) AS rn
            FROM main_silver.clean_delegations
        ),
        active AS (
            SELECT delegator, delegate, delegated_at
            FROM current_delegations
            WHERE rn = 1
              AND delegate != '0x0000000000000000000000000000000000000000'
        ),
        active_with_balance AS (
            SELECT
                a.delegator,
                a.delegate,
                a.delegated_at,
                td.balance AS token_balance
            FROM active a
            JOIN main_silver.clean_token_distribution td ON td.address = a.delegator
            WHERE td.balance > 0
        ),
        delegate_totals AS (
            SELECT
                delegate,
                SUM(token_balance) AS total_vp,
                ROW_NUMBER() OVER (ORDER BY SUM(token_balance) DESC) AS rnk
            FROM active_with_balance
            GROUP BY delegate
        ),
        top30 AS (
            SELECT delegate,
                   CASE WHEN rnk <= 20 THEN 'Top 20' ELSE 'Next 30' END AS tier
            FROM delegate_totals WHERE rnk <= 50
        ),
        cohorted AS (
            SELECT
                awb.token_balance,
                t.tier,
                'Q' || date_part('quarter', awb.delegated_at)::INTEGER::VARCHAR
                    || '''' || right(date_part('year', awb.delegated_at)::INTEGER::VARCHAR, 2)
                    AS cohort_quarter,
                date_trunc('quarter', awb.delegated_at)::DATE AS cohort_quarter_start
            FROM active_with_balance awb
            JOIN top30 t ON t.delegate = awb.delegate
        ),
        total AS (
            SELECT SUM(token_balance) AS total_vp FROM cohorted
        )
        SELECT
            c.cohort_quarter,
            c.cohort_quarter_start,
            c.tier,
            SUM(c.token_balance)                    AS vp_in_cohort,
            SUM(c.token_balance) / t.total_vp * 100 AS pct_of_top30_vp
        FROM cohorted c, total t
        GROUP BY c.cohort_quarter, c.cohort_quarter_start, c.tier, t.total_vp
        ORDER BY c.cohort_quarter_start, c.tier
    """).df()

    return df


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    quarters = df["cohort_quarter"].unique().tolist()

    top20_df = df[df["tier"] == "Top 20"].set_index("cohort_quarter")["pct_of_top30_vp"]
    next10_df = df[df["tier"] == "Next 30"].set_index("cohort_quarter")["pct_of_top30_vp"]

    top20_vals = [top20_df.get(q, 0.0) for q in quarters]
    next10_vals = [next10_df.get(q, 0.0) for q in quarters]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=quarters,
        y=top20_vals,
        name="Top 20 delegates",
        marker_color="#3B4EC8",
        hovertemplate="%{x} · Top 20: %{y:.1f}%<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        x=quarters,
        y=next10_vals,
        name="Delegates 21–50",
        marker_color="#2D8A6E",
        hovertemplate="%{x} · Delegates 21–50: %{y:.1f}%<extra></extra>",
    ))

    # Annotate Q4'21 total bar height
    launch_quarters = [q for q in quarters if str(q).startswith("Q4'21")]
    if launch_quarters:
        lq = launch_quarters[0]
        launch_total = top20_df.get(lq, 0.0) + next10_df.get(lq, 0.0)
        fig.add_annotation(
            x=lq,
            y=launch_total,
            text=f"<b>{launch_total:.0f}%</b>",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#3B4EC8",
            ax=0,
            ay=-36,
            font=dict(size=13, color="#3B4EC8"),
        )

    fig.update_layout(
        title=dict(
            text="When was the top 50 delegates' voting power established?",
            font=dict(size=20, color="#2D3748"),
            x=0,
            xanchor="left",
        ),
        xaxis=dict(
            title=None,
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Share of top-50 VP (%)", font=dict(size=13, color="#4A5568")),
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
        ),
        barmode="stack",
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
        margin=dict(t=100, b=60, l=70, r=40),
        height=440,
        bargap=0.25,
    )

    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(df: pd.DataFrame) -> None:
    by_quarter = df.groupby("cohort_quarter_start")["pct_of_top30_vp"].sum()
    launch_pct = round(by_quarter[by_quarter.index < pd.Timestamp("2022-01-01")].sum(), 1)
    pre2023_pct = round(by_quarter[by_quarter.index < pd.Timestamp("2023-01-01")].sum(), 1)

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
            <div class="stat-card-title">Legacy lock-in</div>
            <div class="stat-row">Q4 2021 delegations account for
                <span class="stat-value">{launch_pct}%</span> of top-50 VP
            </div>
            <div class="stat-row">Pre-2023 delegations account for
                <span class="stat-value">{pre2023_pct}%</span> of top-50 VP
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-card-title" style="color:#555;">Why top 20 + 21–50?</div>
            <div class="stat-row">ENS Nakamoto coefficient is 18 — meaning 18 delegates
            can form a blocking majority. Top 20 is the core governing bloc;
            delegates 21–50 show whether legacy patterns extend into the broader tier.</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-card-title" style="color:#555;">What this measures</div>
            <div class="stat-row">Each bar shows the share of the top-50 delegates'
            combined VP that comes from delegation relationships established in that
            quarter and never updated since.</div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_legacy_distribution() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "For each delegator to the top 50 ENS delegates today, this chart shows <em>when</em> "
        "that delegation was originally set. Each bar is the share of the top-50's combined VP "
        "that was locked in during that quarter — and has not been reassigned since. "
        "A dominant Q4 2021 bar is the signature of legacy power.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading delegation data…"):
        df = _load_data()

    if df.empty:
        st.warning("No delegation data available.")
        return

    fig = _build_chart(df)
    st.plotly_chart(fig, use_container_width=True)

    _render_cards(df)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Sources: on-chain DelegateChanged events (Etherscan) · "
        "ENS token Transfer events (current balances) · "
        "Top 50 defined by total current delegated VP."
    )
