"""
H1.3 — Legacy distribution
Net delegation flow heatmap: inflows and outflows per quarter for top-20 delegates.
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

    # Infer outflows via LAG(): for each delegation event, the previous delegate
    # for that delegator is the one losing a delegator. No token balances needed —
    # this uses raw delegation counts. Top-20 ranking still uses current VP to
    # identify which delegates matter most today.
    df = con.execute("""
        WITH ordered_events AS (
            SELECT
                delegator,
                delegate,
                delegated_at,
                date_trunc('quarter', delegated_at)::DATE AS quarter_start,
                LAG(delegate) OVER (
                    PARTITION BY delegator ORDER BY delegated_at
                ) AS prev_delegate
            FROM main_silver.clean_delegations
            WHERE delegate != '0x0000000000000000000000000000000000000000'
        ),
        active_delegations AS (
            SELECT delegator, delegate,
                   ROW_NUMBER() OVER (
                       PARTITION BY delegator ORDER BY delegated_at DESC
                   ) AS rn
            FROM main_silver.clean_delegations
            WHERE delegate != '0x0000000000000000000000000000000000000000'
        ),
        active AS (
            SELECT delegator, delegate FROM active_delegations WHERE rn = 1
        ),
        active_with_balance AS (
            SELECT a.delegator, a.delegate, td.balance AS token_balance
            FROM active a
            JOIN main_silver.clean_token_distribution td ON td.address = a.delegator
            WHERE td.balance > 0
        ),
        delegate_totals AS (
            SELECT delegate, SUM(token_balance) AS total_vp,
                   ROW_NUMBER() OVER (ORDER BY SUM(token_balance) DESC) AS rnk
            FROM active_with_balance
            GROUP BY delegate
        ),
        top20 AS (
            SELECT delegate, rnk FROM delegate_totals WHERE rnk <= 20
        ),
        inflows AS (
            SELECT oe.delegate, oe.quarter_start, COUNT(*) AS inflow_count
            FROM ordered_events oe
            JOIN top20 ON top20.delegate = oe.delegate
            WHERE oe.prev_delegate IS DISTINCT FROM oe.delegate
            GROUP BY oe.delegate, oe.quarter_start
        ),
        outflows AS (
            SELECT oe.prev_delegate AS delegate, oe.quarter_start,
                   COUNT(*) AS outflow_count
            FROM ordered_events oe
            JOIN top20 ON top20.delegate = oe.prev_delegate
            WHERE oe.prev_delegate IS DISTINCT FROM oe.delegate
            GROUP BY oe.prev_delegate, oe.quarter_start
        ),
        quarters AS (
            SELECT unnest(
                generate_series(DATE '2021-10-01', CURRENT_DATE, INTERVAL '3 months')
            )::DATE AS quarter_start
        ),
        grid AS (
            SELECT
                t.delegate,
                t.rnk,
                q.quarter_start,
                'Q' || date_part('quarter', q.quarter_start)::INTEGER::VARCHAR
                    || '''' || right(date_part('year', q.quarter_start)::INTEGER::VARCHAR, 2)
                    AS quarter_label
            FROM top20 t CROSS JOIN quarters q
        )
        SELECT
            g.delegate,
            g.rnk,
            g.quarter_start,
            g.quarter_label,
            COALESCE(i.inflow_count,  0) AS inflows,
            COALESCE(o.outflow_count, 0) AS outflows,
            COALESCE(i.inflow_count,  0) - COALESCE(o.outflow_count, 0) AS net_change
        FROM grid g
        LEFT JOIN inflows  i ON i.delegate = g.delegate
                             AND i.quarter_start = g.quarter_start
        LEFT JOIN outflows o ON o.delegate = g.delegate
                             AND o.quarter_start = g.quarter_start
        ORDER BY g.rnk, g.quarter_start
    """).df()

    # ENS name labels
    names = con.execute("""
        SELECT address, ens_name
        FROM main_silver.address_crosswalk
        WHERE ens_name IS NOT NULL
    """).df()

    name_map = names.set_index("address")["ens_name"].to_dict()
    df["label"] = df["delegate"].map(
        lambda addr: name_map.get(addr, addr[:10] + "…")
    )

    return df


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _build_chart(df: pd.DataFrame) -> go.Figure:
    # Pivot to matrix: rows = delegates (by rank), columns = quarters
    quarters = df["quarter_label"].unique().tolist()

    # Build ordered delegate list (rank 1 at top → reversed for heatmap y-axis)
    delegate_order = (
        df[["delegate", "rnk", "label"]]
        .drop_duplicates()
        .sort_values("rnk", ascending=False)  # reversed so rank 1 is at top
    )
    labels = delegate_order["label"].tolist()
    delegates = delegate_order["delegate"].tolist()

    # Build z matrix and text matrix
    pivot = df.pivot_table(
        index="delegate", columns="quarter_label", values="net_change", fill_value=0
    ).reindex(index=delegates, columns=quarters, fill_value=0)

    z = pivot.values.tolist()

    # Cap color scale at 90th percentile so moderate changes get visible color
    # without being swamped by Q4'21 outliers. Cells beyond cap clip to extreme color.
    nonzero = df.loc[df["net_change"] != 0, "net_change"].abs()
    abs_max = max(nonzero.quantile(0.90) if not nonzero.empty else 1, 1)

    # Per-cell annotations for text with adaptive color:
    # white text on strongly-colored cells, dark text on near-white cells.
    threshold = abs_max * 0.5
    annotations = []
    for row_i, (label, row) in enumerate(zip(labels, z)):
        for col_i, (quarter, val) in enumerate(zip(quarters, row)):
            if val == 0:
                continue
            text_str = f"+{int(val)}" if val > 0 else str(int(val))
            font_color = "white" if abs(val) >= threshold else "#1A202C"
            annotations.append(dict(
                x=quarter,
                y=label,
                text=text_str,
                showarrow=False,
                font=dict(size=10, color=font_color),
                xref="x",
                yref="y",
            ))

    fig = go.Figure(go.Heatmap(
        z=z,
        x=quarters,
        y=labels,
        colorscale="RdBu",
        zmid=0,
        zmin=-abs_max,
        zmax=abs_max,
        colorbar=dict(
            title=dict(text="Net change", font=dict(size=12, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            thickness=14,
            len=0.8,
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{x}<br>"
            "Net: %{z:+d} delegators"
            "<extra></extra>"
        ),
        xgap=2,
        ygap=2,
    ))

    fig.update_layout(
        title=dict(
            text="Net delegation change per quarter — top 20 delegates",
            font=dict(size=20, color="#2D3748"),
            x=0,
            xanchor="left",
        ),
        xaxis=dict(
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=False,
            side="bottom",
        ),
        yaxis=dict(
            tickfont=dict(size=12, color="#2D3748"),
            showgrid=False,
            autorange=True,
        ),
        annotations=annotations,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=100, b=60, l=150, r=80),
        height=max(400, 30 * 20 + 120),
    )

    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(df: pd.DataFrame) -> None:
    # Largest single-quarter inflow for any top-20 delegate
    max_row = df.loc[df["inflows"].idxmax()]
    max_label = max_row["label"]
    max_quarter = max_row["quarter_label"]
    max_inflow = int(max_row["inflows"])

    # Quarters where net_change == 0 for every top-20 delegate
    by_quarter = df.groupby("quarter_label")["net_change"].apply(lambda s: (s == 0).all())
    frozen_quarters = int(by_quarter.sum())
    total_quarters = int(len(by_quarter))

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
            <div class="stat-card-title">Peak inflow</div>
            <div class="stat-row"><span class="stat-value">{max_label}</span> gained
                <span class="stat-value">+{max_inflow}</span> delegators in {max_quarter}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Frozen quarters</div>
            <div class="stat-row">
                <span class="stat-value">{frozen_quarters}</span> of {total_quarters} quarters
                had zero net change across all top-20 delegates
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-card-title" style="color:#555;">How to read this</div>
            <div class="stat-row">
                <b style="color:#3B4EC8;">Blue</b> = gained delegators that quarter.
                <b style="color:#C0392B;">Red</b> = lost delegators.
                White = no change. Values are raw delegator counts, not VP.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_delegation_flow() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "For each of today's top-20 delegates (by current delegated VP), this chart shows "
        "how many delegators they gained or lost each quarter. Inflows and outflows are inferred "
        "from the on-chain delegation event history — no token balances required. "
        "A predominantly white grid after Q4 2021 is the signature of a frozen power structure.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading delegation flow data…"):
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
        "ENS names from Tally delegate profiles · "
        "Top 20 ranked by current delegated VP."
    )
