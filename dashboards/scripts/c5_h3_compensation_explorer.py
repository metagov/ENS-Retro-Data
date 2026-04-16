"""
C5 — Treasury & Institutional Liability Risk
H5.3 — Compensation & Roles Explorer

Two visuals:
  render_compensation_by_wg  — grouped bar by working group × role with filters
  render_compensation_table  — filterable table of individual compensation records
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import CHART_CONFIG, WATERMARK
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

# Consistent color palette for roles
_ROLE_COLORS = [
    "#3B4EC8", "#2D8A6E", "#E07B54", "#D97706",
    "#7C3AED", "#0891B2", "#BE185D", "#A0AEC0",
]


@st.cache_data
def _load_compensation() -> pd.DataFrame:
    con = get_connection()
    df = con.execute("""
        SELECT id, recipient_address, amount, token, value_usd,
               period, date, working_group, role, category
        FROM main_silver.clean_compensation
        ORDER BY date
    """).df()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    # Capitalize display values
    df["working_group"] = df["working_group"].str.title()
    df["role"] = df["role"].str.title()
    df["category"] = df["category"].str.title()
    df["token"] = df["token"].str.upper()
    return df


def _fmt_usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:.0f}"


# ---------------------------------------------------------------------------
# render_compensation_by_wg
# ---------------------------------------------------------------------------

@st.fragment
def render_compensation_by_wg() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Total compensation in USD grouped by working group and role. "
        "Filter by payment category (Salaries, Stream, Fellowship), working group, "
        "and year to compare how compensation is distributed across the DAO.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading compensation data…"):
        df = _load_compensation()

    if df.empty:
        st.warning("No compensation data available.")
        return

    all_categories = sorted(df["category"].dropna().unique().tolist())
    all_wgs = sorted(df["working_group"].dropna().unique().tolist())
    all_years = sorted(df["year"].unique().tolist())

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        sel_cats = st.multiselect(
            "Payment category",
            all_categories,
            default=all_categories,
            key="compwg_cats",
        )
    with col_f2:
        sel_wgs = st.multiselect(
            "Working group",
            all_wgs,
            default=all_wgs,
            key="compwg_wgs",
        )
    with col_f3:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox("Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="compwg_year")

    filtered = df.copy()
    if sel_cats:
        filtered = filtered[filtered["category"].isin(sel_cats)]
    if sel_wgs:
        filtered = filtered[filtered["working_group"].isin(sel_wgs)]
    if sel_year != "All years":
        filtered = filtered[filtered["year"] == int(sel_year)]

    if filtered.empty:
        st.info("No records match the current filters.")
        return

    grouped = (
        filtered.groupby(["working_group", "role"])["value_usd"]
        .sum()
        .reset_index()
        .sort_values(["working_group", "value_usd"], ascending=[True, False])
    )

    all_roles = sorted(grouped["role"].unique().tolist())
    color_map = {role: _ROLE_COLORS[i % len(_ROLE_COLORS)] for i, role in enumerate(all_roles)}

    wgs = sorted(grouped["working_group"].unique().tolist())

    fig = go.Figure()
    for role in all_roles:
        role_df = grouped[grouped["role"] == role].set_index("working_group")
        fig.add_trace(go.Bar(
            name=role,
            x=wgs,
            y=[role_df.loc[wg, "value_usd"] if wg in role_df.index else 0 for wg in wgs],
            marker_color=color_map[role],
            hovertemplate=f"{role}<br>%{{x}}: $%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(
            title=None,
            tickfont=dict(size=12, color="#4A5568"),
            showgrid=False,
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
        margin=dict(t=80, b=60, l=90, r=40),
        height=420,
        bargap=0.2,
        annotations=[WATERMARK],
    )

    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    # Stat cards
    total_usd = filtered["value_usd"].sum()
    n_recipients = filtered["recipient_address"].nunique()
    n_payments = len(filtered)

    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Total compensation</div>
            <div class="stat-row"><span class="stat-value">{_fmt_usd(total_usd)}</span> USD for selected filters</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Unique recipients</div>
            <div class="stat-row"><span class="stat-value">{n_recipients:,}</span> distinct wallet addresses</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Payment records</div>
            <div class="stat-row"><span class="stat-value">{n_payments:,}</span> individual payment entries</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Source: ENS compensation records · 598 total records · 2022–2025")


# ---------------------------------------------------------------------------
# render_compensation_table
# ---------------------------------------------------------------------------

@st.fragment
def render_compensation_table() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Browse individual compensation records with full filter controls. "
        "The running total reflects your current selection.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading compensation data…"):
        df = _load_compensation()

    if df.empty:
        st.warning("No compensation data available.")
        return

    all_wgs = sorted(df["working_group"].dropna().unique().tolist())
    all_roles = sorted(df["role"].dropna().unique().tolist())
    all_categories = sorted(df["category"].dropna().unique().tolist())
    all_years = sorted(df["year"].unique().tolist())

    def _reset_comptable_filters():
        st.session_state["comptable_wgs"] = all_wgs
        st.session_state["comptable_roles"] = all_roles
        st.session_state["comptable_cats"] = all_categories
        year_options_reset = ["All years"] + [str(y) for y in all_years]
        st.session_state["comptable_year"] = (
            "2025" if "2025" in year_options_reset else year_options_reset[0]
        )

    col_f1, col_f2, col_f3, col_f4, col_reset = st.columns([2, 2, 2, 2, 1])
    with col_f1:
        sel_wgs = st.multiselect(
            "Working group",
            all_wgs,
            default=all_wgs,
            key="comptable_wgs",
        )
    with col_f2:
        sel_roles = st.multiselect(
            "Role",
            all_roles,
            default=all_roles,
            key="comptable_roles",
        )
    with col_f3:
        sel_cats = st.multiselect(
            "Category",
            all_categories,
            default=all_categories,
            key="comptable_cats",
        )
    with col_f4:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox("Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="comptable_year")
    with col_reset:
        st.markdown("<div style='margin-top:24px;'>", unsafe_allow_html=True)
        st.button("Reset", on_click=_reset_comptable_filters, key="comptable_reset")
        st.markdown("</div>", unsafe_allow_html=True)

    filtered = df.copy()
    if sel_wgs:
        filtered = filtered[filtered["working_group"].isin(sel_wgs)]
    if sel_roles:
        filtered = filtered[filtered["role"].isin(sel_roles)]
    if sel_cats:
        filtered = filtered[filtered["category"].isin(sel_cats)]
    if sel_year != "All years":
        filtered = filtered[filtered["year"] == int(sel_year)]

    if filtered.empty:
        st.info("No records match the current filters.")
        return

    total_usd = filtered["value_usd"].sum()
    n_rows = len(filtered)
    st.markdown(
        f"<p style='font-size:14px; color:#2D3748; margin-bottom:8px;'>"
        f"<strong>{n_rows:,} records</strong> · Running total: "
        f"<strong style='color:#2D8A6E;'>{_fmt_usd(total_usd)}</strong> USD</p>",
        unsafe_allow_html=True,
    )

    display = (
        filtered[["date", "working_group", "role", "category", "token", "amount", "value_usd", "period"]]
        .rename(columns={
            "date": "Date",
            "working_group": "Working Group",
            "role": "Role",
            "category": "Category",
            "token": "Token",
            "amount": "Amount",
            "value_usd": "Value (USD)",
            "period": "Period",
        })
        .sort_values("Date", ascending=False)
        .reset_index(drop=True)
    )
    display["Date"] = display["Date"].dt.date
    display["Value (USD)"] = display["Value (USD)"].round(2)

    st.dataframe(display, use_container_width=True, height=420)

    st.caption(
        "Source: ENS compensation records · "
        "Categories: Salaries (384), Stream (196), Fellowship (9), "
        "Steward Gas Ref. (7), Delegate Gas Ref. (3)"
    )
