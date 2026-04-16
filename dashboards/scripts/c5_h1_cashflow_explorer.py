"""
C5 — Treasury & Institutional Liability Risk
H5.1 — Treasury Cashflow Explorer

Two visuals:
  render_cashflow_overview  — monthly inflows vs outflows with year filter
  render_category_breakdown — spending by category with year and flow-type filter
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

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
    color: #1A202C;
    font-weight: 500;
    line-height: 1.8;
}
.stat-value {
    color: #2D8A6E;
    font-weight: 600;
}
.stat-value-warn {
    color: #D97706;
    font-weight: 600;
}
</style>
"""


@st.cache_data
def _load_treasury_summary() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        SELECT period, category, inflows_usd, outflows_usd, net_usd, internal_transfer_usd
        FROM main_gold.treasury_summary
        ORDER BY period
    """).df()
    df["period"] = pd.to_datetime(df["period"])
    df["year"] = df["period"].dt.year
    return df


def _fmt_usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:.0f}"


# ---------------------------------------------------------------------------
# render_cashflow_overview
# ---------------------------------------------------------------------------

@st.fragment
def render_cashflow_overview() -> None:
    st.markdown(
        "<p style='color:#2D3748; font-size:14px; font-weight:600; margin-bottom:16px;'>"
        "Monthly treasury inflows (external revenue), outflows (working group spending), "
        "and internal transfers (DAO Wallet → WG budget allocations) from Mar 2022 to "
        "Nov 2025. Use the year filter to focus on a specific period.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading treasury data…"):
        df = _load_treasury_summary()

    if df.empty:
        st.warning("No treasury data available.")
        return

    all_years = sorted(df["year"].unique().tolist())
    year_options = ["All years"] + [str(y) for y in all_years]

    col_f1, _ = st.columns([1, 3])
    with col_f1:
        selected_year = st.selectbox(
            "Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="cashflow_year"
        )

    df_f = df[df["year"] == int(selected_year)] if selected_year != "All years" else df

    monthly = (
        df_f.groupby("period")[["inflows_usd", "outflows_usd", "internal_transfer_usd"]]
        .sum()
        .reset_index()
        .sort_values("period")
    )
    monthly["period_label"] = monthly["period"].dt.strftime("%b %Y")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["period_label"],
        y=monthly["inflows_usd"],
        name="Inflows",
        marker_color="#2D8A6E",
        hovertemplate="%{x}<br>Inflows: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=monthly["period_label"],
        y=monthly["outflows_usd"],
        name="Outflows",
        marker_color="#E07B54",
        hovertemplate="%{x}<br>Outflows: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=monthly["period_label"],
        y=monthly["internal_transfer_usd"],
        name="Internal transfers",
        marker_color="#A0AEC0",
        hovertemplate="%{x}<br>Internal: $%{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(
            title=None,
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=False,
            tickangle=-45,
        ),
        yaxis=dict(
            title=dict(text="USD", font=dict(size=13, color="#4A5568")),
            tickformat="$,.0f",
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True,
            gridcolor="#E2E8F0",
            zeroline=False,
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
        margin=dict(t=80, b=100, l=90, r=40),
        height=460,
        bargap=0.15,
    )

    render_chart(fig, key="dl_c5h1_cashflow_overview", filename="cashflow_overview")

    total_in = monthly["inflows_usd"].sum()
    total_out = monthly["outflows_usd"].sum()
    total_int = monthly["internal_transfer_usd"].sum()
    net = total_in - total_out

    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Inflows</div>
            <div class="stat-row">Total: <span class="stat-value">{_fmt_usd(total_in)}</span></div>
            <div class="stat-row">External revenue — Registrar, CoW Swap, Endowment</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Outflows</div>
            <div class="stat-row">Total: <span class="stat-value-warn">{_fmt_usd(total_out)}</span></div>
            <div class="stat-row">Working group end-spend — grants, salaries, contractors</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        net_cls = "stat-value" if net >= 0 else "stat-value-warn"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Net &amp; Internal</div>
            <div class="stat-row">Net (inflow − outflow): <span class="{net_cls}">{_fmt_usd(net)}</span></div>
            <div class="stat-row">Internal transfers: <span class="stat-value">{_fmt_usd(total_int)}</span></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Source: ENS Foundation ledger (ens_ledger_transactions.csv) · "
        "Amounts in USD · Period: Mar 2022–Nov 2025"
    )


# ---------------------------------------------------------------------------
# Sankey helpers
# ---------------------------------------------------------------------------

_SANKEY_PALETTE = [
    "rgba(59,78,200,0.55)",
    "rgba(45,138,110,0.55)",
    "rgba(224,123,84,0.55)",
    "rgba(153,102,204,0.55)",
    "rgba(220,53,69,0.55)",
    "rgba(23,162,184,0.55)",
    "rgba(255,193,7,0.55)",
    "rgba(102,16,242,0.55)",
    "rgba(32,201,151,0.55)",
    "rgba(232,62,140,0.55)",
]
_SANKEY_OTHER_COLOR = "rgba(160,174,192,0.4)"
_SANKEY_TOP_N = 10


@st.cache_data
def _load_ledger_flows() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        SELECT source_entity, destination, category, value_usd,
               YEAR(tx_date) AS year
        FROM main_silver.clean_ens_ledger
        WHERE value_usd IS NOT NULL
    """).df()
    return df


def _filter_by_graph(
    agg: pd.DataFrame,
    sel_source: str,
    sel_dest: str,
) -> pd.DataFrame:
    """Return edges relevant to the source/dest selection using graph traversal."""
    if sel_source == "All" and sel_dest == "All":
        return agg

    fwd: dict[str, set[str]] = {}
    bwd: dict[str, set[str]] = {}
    for _, row in agg.iterrows():
        fwd.setdefault(row["source_entity"], set()).add(row["destination"])
        bwd.setdefault(row["destination"], set()).add(row["source_entity"])

    def _reachable_fwd(start: str) -> set[str]:
        visited, queue = {start}, [start]
        while queue:
            node = queue.pop()
            for nxt in fwd.get(node, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return visited

    def _reachable_bwd(start: str) -> set[str]:
        visited, queue = {start}, [start]
        while queue:
            node = queue.pop()
            for prv in bwd.get(node, []):
                if prv not in visited:
                    visited.add(prv)
                    queue.append(prv)
        return visited

    if sel_source != "All" and sel_dest == "All":
        keep_nodes = _reachable_fwd(sel_source)
    elif sel_dest != "All" and sel_source == "All":
        keep_nodes = _reachable_bwd(sel_dest)
    else:
        keep_nodes = _reachable_fwd(sel_source) & _reachable_bwd(sel_dest)

    return agg[
        agg["source_entity"].isin(keep_nodes) & agg["destination"].isin(keep_nodes)
    ]


# ---------------------------------------------------------------------------
# render_category_breakdown  (Sankey: source_entity → destination)
# ---------------------------------------------------------------------------

@st.fragment
def render_category_breakdown() -> None:
    st.markdown(
        "<p style='color:#2D3748; font-size:14px; font-weight:600; margin-bottom:16px;'>"
        "Follow the money: external revenue flows into the DAO Wallet, which allocates "
        "budgets to working groups, which spend on recipients and grantees. "
        "Destinations receiving less than $10K in the period are grouped into "
        "<em>Other</em>. Links are color-coded by ledger category.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading ledger data…"):
        df = _load_ledger_flows()

    if df.empty:
        st.warning("No ledger data available.")
        return

    all_years = sorted(df["year"].unique().tolist())
    year_options = ["All years"] + [str(y) for y in all_years]

    _FILTER_KEYS = ["catbreak_year", "catbreak_category", "catbreak_source", "catbreak_dest"]
    if st.button("Reset filters", key="catbreak_reset"):
        for k in _FILTER_KEYS:
            st.session_state.pop(k, None)
        st.rerun()

    # --- Row 1: Year + Category ---
    col_f1, col_f2, _ = st.columns([1, 1, 2])
    with col_f1:
        selected_year = st.selectbox(
            "Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="catbreak_year",
        )

    df_f = df[df["year"] == int(selected_year)] if selected_year != "All years" else df

    all_categories = sorted(df_f["category"].dropna().unique().tolist())
    with col_f2:
        sel_category = st.selectbox(
            "Category",
            ["All"] + all_categories,
            index=0,
            key="catbreak_category",
        )

    if sel_category != "All":
        df_f = df_f[df_f["category"] == sel_category]

    if df_f.empty:
        st.info("No data for this selection.")
        return

    # Aggregate by (source, destination, category) then apply $10K threshold
    agg = (
        df_f.groupby(["source_entity", "destination", "category"])["value_usd"]
        .sum()
        .reset_index()
    )

    pair_totals = (
        agg.groupby(["source_entity", "destination"])["value_usd"]
        .sum()
        .reset_index()
    )
    small_pairs = set(
        zip(
            pair_totals.loc[pair_totals["value_usd"] < 10_000, "source_entity"],
            pair_totals.loc[pair_totals["value_usd"] < 10_000, "destination"],
        )
    )
    n_grouped = len(small_pairs)
    agg["destination"] = agg.apply(
        lambda r: "Other"
        if (r["source_entity"], r["destination"]) in small_pairs
        else r["destination"],
        axis=1,
    )
    agg = (
        agg.groupby(["source_entity", "destination", "category"])["value_usd"]
        .sum()
        .reset_index()
    )

    # --- Row 2: Source + Destination (built from grouped data so "Other" is selectable) ---
    all_sources = sorted(agg["source_entity"].dropna().unique().tolist())
    all_dests = sorted(agg["destination"].dropna().unique().tolist())

    col_f3, col_f4 = st.columns(2)
    with col_f3:
        sel_source = st.selectbox(
            "Source",
            ["All"] + all_sources,
            index=0,
            key="catbreak_source",
        )
    with col_f4:
        sel_dest = st.selectbox(
            "Destination",
            ["All"] + all_dests,
            index=0,
            key="catbreak_dest",
        )

    agg = _filter_by_graph(agg, sel_source, sel_dest)

    if agg.empty:
        st.info("No data for this selection.")
        return

    # Color mapping: top N categories by total value in this selection
    cat_totals = agg.groupby("category")["value_usd"].sum().sort_values(ascending=False)
    top_cats = cat_totals.head(_SANKEY_TOP_N).index.tolist()
    cat_color_map = {cat: _SANKEY_PALETTE[i] for i, cat in enumerate(top_cats)}

    # Category color legend (above chart)
    legend_html = " &nbsp; ".join(
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'background:{_SANKEY_PALETTE[i]};border-radius:2px;margin-right:4px;vertical-align:middle;">'
        f'</span>{cat}'
        for i, cat in enumerate(top_cats)
    )
    legend_html += (
        f' &nbsp; <span style="display:inline-block;width:12px;height:12px;'
        f'background:{_SANKEY_OTHER_COLOR};border-radius:2px;margin-right:4px;vertical-align:middle;">'
        f'</span>Other categories'
    )
    st.markdown(
        f'<div style="font-size:12px;color:#4A5568;margin:12px 0 6px 0;">{legend_html}</div>',
        unsafe_allow_html=True,
    )

    # Build node list (sources first, then destinations)
    node_labels: list[str] = []
    seen: set[str] = set()
    for val in list(agg["source_entity"].unique()) + list(agg["destination"].unique()):
        if val not in seen:
            node_labels.append(val)
            seen.add(val)
    node_index = {lbl: i for i, lbl in enumerate(node_labels)}

    # Build Sankey link arrays
    link_sources, link_targets, link_values, link_colors, link_labels = [], [], [], [], []
    for _, row in agg.iterrows():
        link_sources.append(node_index[row["source_entity"]])
        link_targets.append(node_index[row["destination"]])
        link_values.append(row["value_usd"])
        link_colors.append(cat_color_map.get(row["category"], _SANKEY_OTHER_COLOR))
        link_labels.append(row["category"])

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=node_labels,
            color="#A0AEC0",
            pad=18,
            thickness=20,
            line=dict(color="#2D3748", width=0.5),
            hovertemplate="%{label}<extra></extra>",
        ),
        link=dict(
            source=link_sources,
            target=link_targets,
            value=link_values,
            color=link_colors,
            label=link_labels,
            hovertemplate=(
                "%{source.label} → %{target.label}<br>"
                "Category: %{label}<br>"
                "Amount: $%{value:,.0f}<extra></extra>"
            ),
        ),
        textfont=dict(
            family="Inter, -apple-system, Helvetica, sans-serif",
            size=14,
            color="#1A202C",
        ),
    ))

    fig.update_layout(
        paper_bgcolor="white",
        margin=dict(t=10, b=10, l=10, r=10),
        height=max(500, len(node_labels) * 28),
        font=dict(
            family="Inter, -apple-system, Helvetica, sans-serif",
            size=14,
            color="#1A202C",
        ),
    )

    render_chart(fig, key="dl_c5h1_sankey", filename="cashflow_sankey")

    # Stat cards
    total_flow = agg["value_usd"].sum()
    n_named = len([d for d in agg["destination"].unique() if d != "Other"])
    period_label = f"{selected_year}" if selected_year != "All years" else "Mar 2022–Nov 2025"

    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Total Flow</div>
            <div class="stat-row">Period: <span class="stat-value">{period_label}</span></div>
            <div class="stat-row">Volume: <span class="stat-value">{_fmt_usd(total_flow)}</span></div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Named Destinations</div>
            <div class="stat-row">Above $10K threshold: <span class="stat-value">{n_named}</span></div>
            <div class="stat-row">Entities receiving significant funds</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Grouped into Other</div>
            <div class="stat-row">Below $10K threshold: <span class="stat-value-warn">{n_grouped}</span></div>
            <div class="stat-row">Smaller recipients aggregated</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Source: ENS Foundation ledger · Amounts in USD · "
        "Destinations < $10K per period grouped into Other"
    )
