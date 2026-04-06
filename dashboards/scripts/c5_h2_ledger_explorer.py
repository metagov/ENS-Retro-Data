"""
C5 — Treasury & Institutional Liability Risk
H5.2 — Ledger Transaction Explorer

  render_ledger_explorer — filterable transaction table with summary bar and stat cards
"""

import pandas as pd
import streamlit as st

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
    color: #4A5568;
    line-height: 1.8;
}
.stat-value {
    color: #2D8A6E;
    font-weight: 600;
}
</style>
"""


@st.cache_data
def _load_ledger() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        SELECT tx_hash, tx_date, quarter, source_entity, destination,
               category, amount, asset, value_usd, flow_type
        FROM main_silver.clean_ens_ledger
        ORDER BY tx_date
    """).df()
    df["tx_date"] = pd.to_datetime(df["tx_date"])
    df["year"] = df["tx_date"].dt.year
    return df


def _fmt_usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:.0f}"


# ---------------------------------------------------------------------------
# render_ledger_explorer
# ---------------------------------------------------------------------------

@st.fragment
def render_ledger_explorer() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Row-level view of 2,316 ENS Foundation treasury transactions from the "
        "Foundation's own labeled bookkeeping ledger. Use the filters to trace "
        "payments by flow type, asset, year, or category. The bar chart and stat "
        "cards reflect your current selection.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading ledger data…"):
        df = _load_ledger()

    if df.empty:
        st.warning("No ledger data available.")
        return

    all_flow_types = sorted(df["flow_type"].dropna().unique().tolist())
    all_assets = sorted(df["asset"].dropna().unique().tolist())
    all_years = sorted(df["year"].unique().tolist())
    all_categories = sorted(df["category"].dropna().unique().tolist())
    all_sources = sorted(df["source_entity"].dropna().unique().tolist())
    all_destinations = sorted(df["destination"].dropna().unique().tolist())

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        flow_opts = ["All"] + sorted(all_flow_types)
        sel_flow = st.radio(
            "Flow type",
            flow_opts,
            index=0,
            horizontal=True,
            key="ledger_flow_type",
        )
    with col_f2:
        sel_asset = st.multiselect(
            "Asset",
            all_assets,
            default=all_assets,
            key="ledger_asset",
        )
    with col_f3:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox("Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="ledger_year")
    with col_f4:
        cat_options = ["All"] + all_categories
        sel_cat = st.selectbox(
            "Category",
            cat_options,
            index=0,
            key="ledger_cats",
        )

    col_f5, col_f6, col_reset = st.columns([2, 2, 1])
    with col_f5:
        src_options = ["All"] + all_sources
        sel_source = st.selectbox(
            "Source",
            src_options,
            index=0,
            key="ledger_source",
        )
    with col_f6:
        dst_options = ["All"] + all_destinations
        sel_dest = st.selectbox(
            "Destination",
            dst_options,
            index=0,
            key="ledger_dest",
        )
    with col_reset:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        if st.button("Reset filters", key="ledger_reset"):
            for k in ("ledger_flow_type", "ledger_asset", "ledger_year",
                      "ledger_cats", "ledger_source", "ledger_dest"):
                st.session_state.pop(k, None)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    filtered = df.copy()
    if sel_flow != "All":
        filtered = filtered[filtered["flow_type"] == sel_flow]
    if sel_asset:
        filtered = filtered[filtered["asset"].isin(sel_asset)]
    if sel_year != "All years":
        filtered = filtered[filtered["year"] == int(sel_year)]
    if sel_cat != "All":
        filtered = filtered[filtered["category"] == sel_cat]
    if sel_source != "All":
        filtered = filtered[filtered["source_entity"] == sel_source]
    if sel_dest != "All":
        filtered = filtered[filtered["destination"] == sel_dest]

    if filtered.empty:
        st.info("No transactions match the current filters.")
        return

    # Stat cards
    total_usd = filtered["value_usd"].sum()
    n_rows = len(filtered)
    n_destinations = filtered["destination"].nunique()

    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Total value</div>
            <div class="stat-row"><span class="stat-value">{_fmt_usd(total_usd)}</span> USD across filtered transactions</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Transactions</div>
            <div class="stat-row"><span class="stat-value">{n_rows:,}</span> rows match current filters</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Unique destinations</div>
            <div class="stat-row"><span class="stat-value">{n_destinations:,}</span> distinct recipients</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Filterable table
    display = (
        filtered[["tx_date", "source_entity", "destination", "category", "asset", "amount", "value_usd", "flow_type"]]
        .rename(columns={
            "tx_date": "Date",
            "source_entity": "Source",
            "destination": "Destination",
            "category": "Category",
            "asset": "Asset",
            "amount": "Amount",
            "value_usd": "Value (USD)",
            "flow_type": "Flow Type",
        })
        .sort_values("Date", ascending=False)
        .reset_index(drop=True)
    )
    display["Date"] = display["Date"].dt.date
    display["Value (USD)"] = display["Value (USD)"].round(2)

    st.dataframe(display, use_container_width=True, height=400)

    st.caption(
        "Source: ENS Foundation ledger (ens_ledger_transactions.csv) · "
        "2,316 total transactions · Mar 2022–Nov 2025"
    )
