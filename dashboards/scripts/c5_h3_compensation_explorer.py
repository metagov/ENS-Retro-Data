"""
C5 — Treasury & Institutional Liability Risk
H5.3 — Compensation & Roles Explorer

Three visuals:
  render_contributor_comp_by_wg   — WG x role bar (Metagov / Ecosystem / Public Goods)
  render_service_provider_streams — per-team streams for the Service Provider Program
  render_compensation_table       — filterable table of individual records (all sources)
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.chart_utils import render_chart
from scripts.db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Raw silver labels → display labels
WG_DISPLAY = {
    "meta-governance": "Metagov",
    "ens-ecosystem":   "Ecosystem",
    "public-goods":    "Public Goods",
    "providers":       "Service Providers",
}

# Working groups with contributor-style comp (salaries, fellowships, gas refs).
# The Service Provider Program is tracked separately — it's vendor contracts, not WG payroll.
_CONTRIBUTOR_WGS = ["meta-governance", "ens-ecosystem", "public-goods"]
_SP_WG = "providers"

_ROLE_COLORS = [
    "#3B4EC8", "#2D8A6E", "#E07B54", "#D97706",
    "#7C3AED", "#0891B2", "#BE185D", "#A0AEC0",
]

_PROVIDER_COLOR = "#3B4EC8"

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


# ---------------------------------------------------------------------------
# Shared loader
# ---------------------------------------------------------------------------

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
    df["wg_display"] = df["working_group"].map(WG_DISPLAY).fillna(df["working_group"].str.title())
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
# render_contributor_comp_by_wg  (A+B: WGs only, labels cleaned)
# ---------------------------------------------------------------------------

@st.fragment
def render_contributor_comp_by_wg() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Contributor compensation (salaries, fellowships, steward/delegate gas refunds) "
        "for the three ENS working groups. Vendor streams from the Service Provider "
        "Program are shown separately in the next chart.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading compensation data…"):
        df = _load_compensation()

    df = df[df["working_group"].isin(_CONTRIBUTOR_WGS)].copy()
    if df.empty:
        st.warning("No contributor compensation data available.")
        return

    all_categories = sorted(df["category"].dropna().unique().tolist())
    all_wgs = [WG_DISPLAY[w] for w in _CONTRIBUTOR_WGS if w in df["working_group"].unique()]
    all_years = sorted(df["year"].unique().tolist())

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        sel_cats = st.multiselect(
            "Payment category", all_categories, default=all_categories, key="compwg_cats",
        )
    with col_f2:
        sel_wgs = st.multiselect(
            "Working group", all_wgs, default=all_wgs, key="compwg_wgs",
        )
    with col_f3:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox(
            "Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="compwg_year",
        )

    filtered = df.copy()
    if sel_cats:
        filtered = filtered[filtered["category"].isin(sel_cats)]
    if sel_wgs:
        filtered = filtered[filtered["wg_display"].isin(sel_wgs)]
    if sel_year != "All years":
        filtered = filtered[filtered["year"] == int(sel_year)]

    if filtered.empty:
        st.info("No records match the current filters.")
        return

    grouped = (
        filtered.groupby(["wg_display", "role"])["value_usd"]
        .sum().reset_index()
        .sort_values(["wg_display", "value_usd"], ascending=[True, False])
    )

    all_roles = sorted(grouped["role"].unique().tolist())
    color_map = {role: _ROLE_COLORS[i % len(_ROLE_COLORS)] for i, role in enumerate(all_roles)}
    wgs = sorted(grouped["wg_display"].unique().tolist())

    fig = go.Figure()
    for role in all_roles:
        role_df = grouped[grouped["role"] == role].set_index("wg_display")
        fig.add_trace(go.Bar(
            name=role,
            x=wgs,
            y=[role_df.loc[wg, "value_usd"] if wg in role_df.index else 0 for wg in wgs],
            marker_color=color_map[role],
            hovertemplate=f"{role}<br>%{{x}}: $%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(title=None, tickfont=dict(size=12, color="#4A5568"), showgrid=False),
        yaxis=dict(
            title=dict(text="USD", font=dict(size=13, color="#4A5568")),
            tickformat="$,.0f",
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0", zeroline=False,
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=12, color="#2D3748"), bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=80, b=60, l=90, r=40), height=420, bargap=0.2,
    )

    render_chart(fig, key="dl_c5h3_contributor_by_wg", filename="contributor_comp_by_wg")

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

    # Public Goods gap note — be transparent
    if "Public Goods" in sel_wgs:
        pg_n = int((filtered["wg_display"] == "Public Goods").sum())
        if pg_n <= 1:
            st.info(
                "**Note on Public Goods:** the compensation dataset contains only "
                f"{pg_n} Public Goods record{'s' if pg_n != 1 else ''}. The PG working "
                "group primarily disburses funds via *grants* rather than recurring "
                "contributor payroll — see the grants breakdown in H5.2 for the full PG picture."
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Source: ENS compensation ledger · contributor records only "
        "(Service Provider streams shown separately)"
    )


# ---------------------------------------------------------------------------
# render_service_provider_streams  (B: separate chart for the SP program)
# ---------------------------------------------------------------------------

@st.fragment
def render_service_provider_streams() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "The <strong>Service Provider Program</strong> pays external teams via monthly USDC "
        "streams. These are vendor contracts awarded through a competitive process — "
        "not contributor payroll — and are tracked here separately to avoid conflating "
        "them with working-group compensation.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading Service Provider data…"):
        df = _load_compensation()

    df = df[df["working_group"] == _SP_WG].copy()
    if df.empty:
        st.warning("No Service Provider stream data available.")
        return

    # The "id" column in source is "Stream" for every SP record, and the recipient field
    # got lowercased into recipient_address (e.g. 'namehash', 'ethlimo'). Title-case for display.
    df["provider"] = df["recipient_address"].str.replace(".eth", "", regex=False).str.title()

    all_years = sorted(df["year"].unique().tolist())
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox(
            "Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="spstream_year",
        )
    with col_f2:
        all_providers = sorted(df["provider"].unique().tolist())
        sel_providers = st.multiselect(
            "Provider team", all_providers, default=all_providers, key="spstream_providers",
        )

    filtered = df.copy()
    if sel_year != "All years":
        filtered = filtered[filtered["year"] == int(sel_year)]
    if sel_providers:
        filtered = filtered[filtered["provider"].isin(sel_providers)]

    if filtered.empty:
        st.info("No records match the current filters.")
        return

    by_provider = (
        filtered.groupby("provider")["value_usd"].sum()
        .reset_index().sort_values("value_usd", ascending=True)
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        orientation="h",
        x=by_provider["value_usd"],
        y=by_provider["provider"],
        marker_color=_PROVIDER_COLOR,
        hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(
            title=dict(text="USD paid", font=dict(size=13, color="#4A5568")),
            tickformat="$,.0f",
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0", zeroline=False,
        ),
        yaxis=dict(title=None, tickfont=dict(size=12, color="#2D3748"), showgrid=False),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=40, b=60, l=140, r=40),
        height=max(320, 24 * len(by_provider) + 120),
        showlegend=False,
    )
    render_chart(fig, key="dl_c5h3_sp_streams", filename="service_provider_streams")

    total_usd = filtered["value_usd"].sum()
    n_providers = filtered["provider"].nunique()
    n_months = len(filtered)

    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Total paid</div>
            <div class="stat-row"><span class="stat-value">{_fmt_usd(total_usd)}</span> USD for selected filters</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Provider teams</div>
            <div class="stat-row"><span class="stat-value">{n_providers}</span> distinct teams funded</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-card-title">Monthly stream payments</div>
            <div class="stat-row"><span class="stat-value">{n_months:,}</span> monthly disbursements</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Source: ENS Service Provider Program monthly streams · "
        "external vendor contracts, not contributor payroll."
    )


# ---------------------------------------------------------------------------
# render_compensation_table  (A: cleaned labels + live counts)
# ---------------------------------------------------------------------------

@st.fragment
def render_compensation_table() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Browse every compensation record — contributor payroll and Service Provider "
        "streams combined. The running total reflects your current selection.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading compensation data…"):
        df = _load_compensation()

    if df.empty:
        st.warning("No compensation data available.")
        return

    all_wgs = sorted(df["wg_display"].dropna().unique().tolist())
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
        sel_wgs = st.multiselect("Working group", all_wgs, default=all_wgs, key="comptable_wgs")
    with col_f2:
        sel_roles = st.multiselect("Role", all_roles, default=all_roles, key="comptable_roles")
    with col_f3:
        sel_cats = st.multiselect("Category", all_categories, default=all_categories, key="comptable_cats")
    with col_f4:
        year_options = ["All years"] + [str(y) for y in all_years]
        sel_year = st.selectbox(
            "Year", year_options,
            index=year_options.index("2025") if "2025" in year_options else 0,
            key="comptable_year",
        )
    with col_reset:
        st.markdown("<div style='margin-top:24px;'>", unsafe_allow_html=True)
        st.button("Reset", on_click=_reset_comptable_filters, key="comptable_reset")
        st.markdown("</div>", unsafe_allow_html=True)

    filtered = df.copy()
    if sel_wgs:
        filtered = filtered[filtered["wg_display"].isin(sel_wgs)]
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
        filtered[["date", "wg_display", "role", "category", "token", "amount", "value_usd", "period"]]
        .rename(columns={
            "date": "Date",
            "wg_display": "Working Group",
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

    st.dataframe(display, width="stretch", height=420)

    # Live category counts so this never drifts again
    cat_counts = df["category"].value_counts().to_dict()
    cat_str = " · ".join(f"{k} ({v})" for k, v in sorted(cat_counts.items(), key=lambda x: -x[1]))
    st.caption(f"Source: ENS compensation records · {cat_str}")
