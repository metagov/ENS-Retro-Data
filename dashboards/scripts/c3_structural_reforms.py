"""
C3 — H2.2 and H6.3: Structural Reform Resistance and Experimentation Scarcity

H2.2: Do large actors resist decentralizing reforms?
       Identifies proposals that would reduce governance concentration and tracks
       how the top-30 power-holders vote on them vs. routine proposals.

H6.3: Lack of experimentation — few structural trials around delegates.
       Maps all proposals that attempted to change delegate or working-group
       structures; shows which passed and how often such experiments occurred.

Shared data layer:
  _load_proposals()       — all proposals + classification via proposal_type.py
  _load_delegate_votes()  — top-30 VP-holder votes (Snapshot only; Tally
                            vote_choice = 'unknown' in silver)

Entry points:
  render_h2_2_resistance()
  render_h6_3_experimentation()
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.db import get_connection
from scripts.proposal_type import classify_proposals

TOP_N = 30

# Category display order and colors for the timeline (DAOIP-4 type strings)
_CAT_ORDER = [
    "metagov/delegate-governance",
    "treasury/budget",
    "treasury/grant",
    "treasury/investment",
    "protocol/major-change",
    "protocol/small-change",
    "metagov/major-change",
    "metagov/small-change",
    "protocol/other",
    "treasury/other",
    "metagov/other",
]

_CAT_COLORS = {
    "metagov/delegate-governance": "#8172B3",
    "treasury/budget":             "#64B5CD",
    "treasury/grant":              "#4C72B0",
    "treasury/investment":         "#937860",
    "protocol/major-change":       "#55A868",
    "metagov/major-change":        "#C44E52",
    "metagov/small-change":        "#DA8BC3",
    "protocol/small-change":       "#CBD5E0",
    "protocol/other":              "#CBD5E0",
    "treasury/other":              "#B5B867",
    "metagov/other":               "#A8A8A8",
}

# Vote encoding for heatmap: for=0, against=1, abstain=2, no-vote=3
_VOTE_COLORSCALE = [
    [0.000, "#48BB78"], [0.249, "#48BB78"],   # for   → green
    [0.250, "#E07B54"], [0.499, "#E07B54"],   # against → orange-red
    [0.500, "#ECC94B"], [0.749, "#ECC94B"],   # abstain → amber
    [0.750, "#CBD5E0"], [1.000, "#CBD5E0"],   # no-vote → light gray
]

_VOTE_ENCODE = {"for": 0, "against": 1, "abstain": 2}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_proposals() -> pd.DataFrame:
    """Load all closed/executed proposals with body; classify via proposal_type."""
    con = get_connection()

    snap = con.execute("""
        SELECT
            p.proposal_id,
            'Snapshot'              AS platform,
            p.title,
            p.body,
            p.status,
            p.start_date::DATE      AS proposal_date
        FROM main_silver.clean_snapshot_proposals p
        WHERE p.status = 'closed'
    """).df()

    tally = con.execute("""
        SELECT
            p.proposal_id,
            'Tally'                 AS platform,
            p.title,
            p.body,
            p.status,
            p.start_date::DATE      AS proposal_date
        FROM main_silver.clean_tally_proposals p
        WHERE p.status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
    """).df()

    # Add Snapshot for_pct from governance_activity (pre-computed)
    snap_pct = con.execute("""
        SELECT proposal_id, for_pct, against_pct
        FROM main_gold.governance_activity
        WHERE source = 'snapshot'
    """).df()
    snap = snap.merge(snap_pct, on="proposal_id", how="left")

    # Tally: compute for_pct inline
    tally_pct = con.execute("""
        SELECT
            proposal_id,
            CASE
                WHEN (for_votes + against_votes + abstain_votes) > 0
                THEN ROUND(for_votes / (for_votes + against_votes + abstain_votes) * 100, 2)
            END AS for_pct,
            CASE
                WHEN (for_votes + against_votes + abstain_votes) > 0
                THEN ROUND(against_votes / (for_votes + against_votes + abstain_votes) * 100, 2)
            END AS against_pct
        FROM main_silver.clean_tally_proposals
    """).df()
    tally = tally.merge(tally_pct, on="proposal_id", how="left")

    df = pd.concat([snap, tally], ignore_index=True)
    df["proposal_date"] = pd.to_datetime(df["proposal_date"], errors="coerce")

    # "passed" flag
    df["passed"] = (
        ((df["platform"] == "Snapshot") & (df["for_pct"].fillna(0) > df["against_pct"].fillna(0)))
        | (df["platform"] == "Tally") & (df["status"].isin(["executed", "queued", "succeeded"]))
    )

    df = classify_proposals(df)
    return df.sort_values("proposal_date").reset_index(drop=True)


@st.cache_data
def _load_delegate_votes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Top-30 delegate profiles + their Snapshot votes (Tally excluded:
    vote_choice = 'unknown' in clean_tally_votes).
    """
    con = get_connection()

    delegates = con.execute(f"""
        SELECT
            address,
            COALESCE(NULLIF(ens_name, ''), LEFT(address, 10) || '…') AS label,
            voting_power
        FROM main_gold.delegate_scorecard
        ORDER BY voting_power DESC
        LIMIT {TOP_N}
    """).df()

    votes = con.execute(f"""
        WITH top10 AS (
            SELECT address
            FROM main_gold.delegate_scorecard
            ORDER BY voting_power DESC
            LIMIT {TOP_N}
        )
        SELECT
            sv.voter,
            sv.proposal_id,
            sv.vote_choice,
            sp.start_date::DATE          AS proposal_date,
            LEFT(COALESCE(sp.title, sv.proposal_id), 60) AS proposal_title
        FROM main_silver.clean_snapshot_votes sv
        JOIN top10                  ON sv.voter      = top10.address
        JOIN main_silver.clean_snapshot_proposals sp ON sv.proposal_id = sp.proposal_id
    """).df()

    return delegates, votes


# ---------------------------------------------------------------------------
# Chart helpers — shared
# ---------------------------------------------------------------------------

def _short_title(t: str, n: int = 45) -> str:
    return (t[:n] + "…") if len(t) > n else t


# ---------------------------------------------------------------------------
# H6.3 Charts
# ---------------------------------------------------------------------------

def _category_timeline(proposals: pd.DataFrame) -> go.Figure:
    """Scatter: all proposals by date, colored by category, star = structural."""
    fig = go.Figure()

    for cat in _CAT_ORDER:
        sub = proposals[proposals["proposal_category"] == cat]
        if sub.empty:
            continue

        # Structural experiments get a star marker
        for is_struct, symbol, size, name_suffix in [
            (True,  "star",   14, " ★ structural"),
            (False, "circle",  8, ""),
        ]:
            s = sub[sub["is_structural_experiment"] == is_struct]
            if s.empty:
                continue

            fig.add_trace(go.Scatter(
                x=s["proposal_date"],
                y=s["proposal_category"],
                mode="markers",
                name=cat.replace("_", " ").title() + name_suffix,
                marker=dict(
                    color=_CAT_COLORS.get(cat, "#A8A8A8"),
                    symbol=symbol,
                    size=size,
                    opacity=0.85,
                    line=dict(width=0.5, color="white"),
                ),
                customdata=list(zip(
                    s["title"],
                    s["platform"],
                    s["passed"].map({True: "Passed", False: "Did not pass"}),
                    s["reform_tags"].apply(lambda x: ", ".join(x) if x else "—"),
                )),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Platform: %{customdata[1]} · %{customdata[2]}<br>"
                    "Tags: %{customdata[3]}"
                    "<extra></extra>"
                ),
                showlegend=True,
            ))

    fig.update_layout(
        title=dict(
            text="Governance proposal landscape by category and date",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        xaxis=dict(
            title=dict(text="Proposal date", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True, gridcolor="#E2E8F0",
        ),
        yaxis=dict(
            title=dict(text="Category", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            showgrid=True, gridcolor="#F0F0F0",
            categoryorder="array",
            categoryarray=list(reversed(_CAT_ORDER)),
        ),
        legend=dict(
            orientation="v", x=1.01, xanchor="left",
            font=dict(size=10, color="#4A5568"),
            bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=80, b=60, l=200, r=20),
        height=480,
    )
    return fig


def _structural_inventory_table(proposals: pd.DataFrame) -> pd.DataFrame:
    """Return styled display DataFrame for structural experiment proposals."""
    struct = proposals[proposals["is_structural_experiment"]].copy()
    struct = struct.sort_values("proposal_date", ascending=False)

    struct["Date"]     = struct["proposal_date"].dt.strftime("%Y-%m-%d")
    struct["Title"]    = struct["title"].apply(lambda t: _short_title(t, 70))
    struct["Platform"] = struct["platform"]
    struct["Category"] = struct["proposal_category"].str.replace("_", " ").str.title()
    struct["Result"]   = struct["passed"].map({True: "✓ Passed", False: "✗ Did not pass"})
    struct["Tags"]     = struct["reform_tags"].apply(lambda x: ", ".join(x) if x else "—")

    return struct[["Date", "Platform", "Title", "Category", "Result", "Tags"]].reset_index(drop=True)


def _h6_3_cards(proposals: pd.DataFrame) -> None:
    struct = proposals[proposals["is_structural_experiment"]]
    total  = len(proposals)
    n_struct = len(struct)
    n_passed = struct["passed"].sum()

    last = struct.dropna(subset=["proposal_date"]).sort_values("proposal_date")
    last_title = _short_title(last.iloc[-1]["title"], 40) if not last.empty else "N/A"
    last_date  = last.iloc[-1]["proposal_date"].strftime("%b %Y") if not last.empty else "N/A"

    card_css = """
    <style>
    .sr-card { background:#F7F8FC; border-radius:8px; padding:16px 20px; margin:4px 0; }
    .sr-t    { font-size:14px; font-weight:700; color:#3B4EC8; margin-bottom:8px; }
    .sr-r    { font-size:13px; color:#4A5568; line-height:1.8; }
    .sr-v    { font-weight:600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="sr-card">
            <div class="sr-t">Structural experiments</div>
            <div class="sr-r">
                <span class="sr-v" style="color:#C44E52;">{n_struct}</span> of
                <span class="sr-v">{total}</span> total proposals
                attempted structural change
                (<span class="sr-v">{n_struct / total * 100:.1f}%</span>)
            </div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="sr-card">
            <div class="sr-t">Pass rate</div>
            <div class="sr-r">
                <span class="sr-v" style="color:#2D8A6E;">{n_passed}</span> passed /
                <span class="sr-v" style="color:#C44E52;">{n_struct - n_passed}</span> did not pass<br>
                Pass rate: <span class="sr-v">{n_passed / n_struct * 100:.0f}%</span>
            </div>
        </div>""" if n_struct else """<div class="sr-card"><div class="sr-t">Pass rate</div>
        <div class="sr-r">No structural proposals found.</div></div>""",
                    unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="sr-card">
            <div class="sr-t">Most recent experiment</div>
            <div class="sr-r">
                <span class="sr-v">{last_title}</span><br>
                <span style="color:#718096;">{last_date}</span>
            </div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# H2.2 Charts
# ---------------------------------------------------------------------------

def _outcome_strip(proposals: pd.DataFrame) -> go.Figure:
    """
    Jittered strip plot of for_pct by reform type.
    Small N makes a box-plot misleading; individual dots show the full picture.
    """
    fig = go.Figure()
    valid = proposals[proposals["for_pct"].notna()].copy()

    groups = [
        (valid[valid["is_decentralizing_reform"]],  "Decentralizing reform", "#C44E52"),
        (valid[~valid["is_decentralizing_reform"]], "Routine proposal",      "#4C72B0"),
    ]

    rng = np.random.default_rng(42)

    for sub, label, color in groups:
        if sub.empty:
            continue
        jitter = rng.uniform(-0.15, 0.15, size=len(sub))
        x_pos  = (1.0 if "reform" in label.lower() else 0.0) + jitter

        fig.add_trace(go.Scatter(
            x=x_pos,
            y=sub["for_pct"],
            mode="markers",
            name=label,
            marker=dict(
                color=color, size=9, opacity=0.70,
                line=dict(width=0.5, color="white"),
            ),
            customdata=list(zip(
                sub["title"],
                sub["platform"],
                sub["passed"].map({True: "Passed", False: "Did not pass"}),
            )),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Platform: %{customdata[1]} · %{customdata[2]}<br>"
                "For %%: %{y:.1f}"
                "<extra></extra>"
            ),
        ))

    # 50% line
    fig.add_hline(y=50, line_dash="dash", line_color="#718096",
                  annotation_text="50 %", annotation_position="right")

    fig.update_layout(
        title=dict(
            text="Vote outcome (for %) — decentralizing reforms vs. routine proposals",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        xaxis=dict(
            tickvals=[0, 1],
            ticktext=["Routine proposals", "Decentralizing reforms"],
            tickfont=dict(size=12, color="#4A5568"),
            range=[-0.5, 1.5],
        ),
        yaxis=dict(
            title=dict(text="For % of total voting power", font=dict(size=13, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            range=[0, 105],
            showgrid=True, gridcolor="#E2E8F0",
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0,
            font=dict(size=12, color="#2D3748"), bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=90, b=60, l=80, r=40),
        height=420,
    )
    return fig


def _delegate_reform_heatmap(
    proposals: pd.DataFrame,
    delegates: pd.DataFrame,
    votes: pd.DataFrame,
) -> go.Figure | None:
    """
    Top-10 delegate × reform-proposal vote grid (Snapshot only).
    Returns None if no reform proposals have delegate votes.
    """
    reform_pids = set(proposals[proposals["is_decentralizing_reform"]]["proposal_id"])
    snap_reform  = votes[votes["proposal_id"].isin(reform_pids)].copy()

    if snap_reform.empty:
        return None

    pid_meta = (
        snap_reform[["proposal_id", "proposal_date", "proposal_title"]]
        .drop_duplicates("proposal_id")
        .sort_values("proposal_date")
    )
    pids   = pid_meta["proposal_id"].tolist()
    labels = pid_meta["proposal_title"].tolist()
    addrs  = delegates["address"].tolist()
    del_labels = delegates["label"].tolist()

    n_del  = len(addrs)
    n_prop = len(pids)

    # Build encoded matrix: 3 = no-vote (default)
    matrix = np.full((n_del, n_prop), 3.0)
    for _, row in snap_reform.iterrows():
        if row["voter"] in addrs and row["proposal_id"] in pids:
            i = addrs.index(row["voter"])
            j = pids.index(row["proposal_id"])
            matrix[i, j] = float(_VOTE_ENCODE.get(row["vote_choice"], 3))

    short_labels = [_short_title(l, 38) for l in labels]

    fig = go.Figure(go.Heatmap(
        z=matrix.tolist(),
        x=list(range(n_prop)),
        y=list(range(n_del)),
        colorscale=_VOTE_COLORSCALE,
        zmin=0, zmax=3,
        showscale=False,
        xgap=2, ygap=2,
        customdata=[[short_labels[j] for j in range(n_prop)] for _ in range(n_del)],
        text=[[del_labels[i]] * n_prop for i in range(n_del)],
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Proposal: %{customdata}<br>"
            "<extra></extra>"
        ),
    ))

    # Y-axis delegate labels as annotations (colored by VP rank)
    fig.update_layout(yaxis=dict(showticklabels=False, tickvals=list(range(n_del))))
    for pos, lbl in enumerate(del_labels):
        fig.add_annotation(
            x=-0.01, y=pos,
            xref="paper", yref="y",
            text=lbl,
            showarrow=False,
            font=dict(size=10, color="#2D3748"),
            xanchor="right", yanchor="middle",
        )

    # X-axis proposal labels (angled)
    fig.update_layout(xaxis=dict(showticklabels=False, tickvals=list(range(n_prop))))
    for pos, lbl in enumerate(short_labels):
        fig.add_annotation(
            x=pos, y=-0.01,
            xref="x", yref="paper",
            text=lbl,
            showarrow=False,
            font=dict(size=8, color="#718096"),
            textangle=-50,
            xanchor="right", yanchor="top",
        )

    # Legend
    for text, color, xpos in [
        ("For", "#48BB78", 0.00),
        ("Against", "#E07B54", 0.10),
        ("Abstain", "#ECC94B", 0.22),
        ("No vote", "#CBD5E0", 0.32),
    ]:
        fig.add_annotation(
            x=xpos, y=1.06, xref="paper", yref="paper",
            text=f"<span style='color:{color};font-weight:700;'>■</span> {text}",
            showarrow=False,
            font=dict(size=11, color="#4A5568"),
            xanchor="left",
        )

    fig.update_layout(
        title=dict(
            text="Top-30 delegate votes on decentralizing reform proposals (Snapshot)",
            font=dict(size=17, color="#2D3748"), x=0, xanchor="left",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=110, b=220, l=180, r=40),
        height=max(420, 28 * n_del + 280),
    )
    return fig


def _h2_2_cards(proposals: pd.DataFrame) -> None:
    reform  = proposals[proposals["is_decentralizing_reform"]]
    routine = proposals[~proposals["is_decentralizing_reform"]]

    n_reform = len(reform)
    n_total  = len(proposals)

    ref_pass = reform["passed"].mean() * 100 if n_reform else 0
    rtn_pass = routine["passed"].mean() * 100 if len(routine) else 0

    ref_med  = reform["for_pct"].dropna().median() if n_reform else 0
    rtn_med  = routine["for_pct"].dropna().median() if len(routine) else 0

    card_css = """
    <style>
    .h22-card { background:#F7F8FC; border-radius:8px; padding:16px 20px; margin:4px 0; }
    .h22-t    { font-size:14px; font-weight:700; color:#3B4EC8; margin-bottom:8px; }
    .h22-r    { font-size:13px; color:#4A5568; line-height:1.8; }
    .h22-v    { font-weight:600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="h22-card">
            <div class="h22-t">Reform proposals identified</div>
            <div class="h22-r">
                <span class="h22-v" style="color:#C44E52;">{n_reform}</span> of
                <span class="h22-v">{n_total}</span> proposals flagged as
                decentralizing reforms ({n_reform / n_total * 100:.1f}%)
            </div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="h22-card">
            <div class="h22-t">Pass rate comparison</div>
            <div class="h22-r">
                Reform: <span class="h22-v" style="color:#C44E52;">{ref_pass:.0f}%</span><br>
                Routine: <span class="h22-v" style="color:#4C72B0;">{rtn_pass:.0f}%</span>
            </div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="h22-card">
            <div class="h22-t">Median for% (voting power)</div>
            <div class="h22-r">
                Reform: <span class="h22-v" style="color:#C44E52;">{ref_med:.1f}%</span><br>
                Routine: <span class="h22-v" style="color:#4C72B0;">{rtn_med:.1f}%</span>
            </div>
        </div>""", unsafe_allow_html=True)


def _vote_reasons(proposals: pd.DataFrame) -> None:
    """Show on-chain Tally vote reasons for reform proposals (proxy for forum arguments)."""
    reform_pids = set(proposals[proposals["is_decentralizing_reform"]]["proposal_id"])
    if not reform_pids:
        return

    con = get_connection()
    reasons_df = con.execute("""
        SELECT
            tv.voter,
            ds.ens_name,
            tp.title                             AS proposal_title,
            tv.vote_choice,
            tv.reason
        FROM main_silver.clean_tally_votes tv
        JOIN main_silver.clean_tally_proposals tp ON tv.proposal_id = tp.proposal_id
        LEFT JOIN main_silver.clean_tally_delegates ds ON tv.voter = ds.address
        WHERE tv.reason IS NOT NULL
          AND tv.reason <> ''
    """).df()

    reasons_df = reasons_df[reasons_df["proposal_title"].notna()]
    reform_titles = set(
        proposals[proposals["is_decentralizing_reform"]]["title"].str[:60]
    )
    # Match on truncated title prefix (Tally proposals may not share IDs with Snapshot)
    reasons_df["title_key"] = reasons_df["proposal_title"].str[:60]
    reasons_df = reasons_df[reasons_df["title_key"].isin(reform_titles)]

    if reasons_df.empty:
        return

    with st.expander("On-chain vote reasons (Tally) — reform proposals", expanded=False):
        st.caption(
            "Vote reasons are submitted on-chain by delegates during Tally votes. "
            "Shown as a proxy for public forum arguments; forum text is not yet linked "
            "to proposals in this warehouse."
        )
        for _, row in reasons_df.iterrows():
            name = row["ens_name"] or row["voter"][:14] + "…"
            color = "#48BB78" if row["vote_choice"] == "for" else (
                "#E07B54" if row["vote_choice"] == "against" else "#ECC94B"
            )
            st.markdown(
                f"**{name}** "
                f"<span style='color:{color};font-size:12px;'>[{row['vote_choice']}]</span>"
                f" — *{row['proposal_title'][:60]}*<br>"
                f"<span style='font-size:13px;color:#4A5568;'>{row['reason']}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("---")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_h6_3_experimentation() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Structural experiments — proposals that would create, dissolve, or restructure "
        "working groups, change delegate roles, or pilot new governance mechanics — are "
        "flagged with ★ in the timeline below. The inventory shows every such proposal "
        "and its vote outcome.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading proposals…"):
        proposals = _load_proposals()

    _h6_3_cards(proposals)
    st.markdown("<br>", unsafe_allow_html=True)

    st.plotly_chart(_category_timeline(proposals), use_container_width=True)

    st.markdown("##### Structural experiment inventory")
    inv = _structural_inventory_table(proposals)
    st.dataframe(inv, use_container_width=True, hide_index=True)

    st.caption(
        "★ markers = structural experiments (is_structural_experiment flag). "
        "Classification via keyword matching on title + body (proposal_type.py). "
        "Implementation status beyond vote outcome is not tracked in this warehouse. "
        "Sources: Snapshot · Tally · warehouse/ens_retro.duckdb"
    )


def render_h2_2_resistance() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Decentralizing reforms — proposals that cap voting power, introduce alternative "
        "voting mechanisms, or reduce governance concentration — are compared to routine "
        "proposals. The delegate heatmap shows how the top-30 VP-holders voted on each "
        "reform proposal (Snapshot only; Tally individual vote choices are not available "
        "in the current data).</p>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading proposals and delegate votes…"):
        proposals             = _load_proposals()
        delegates, all_votes  = _load_delegate_votes()

    _h2_2_cards(proposals)
    st.markdown("<br>", unsafe_allow_html=True)

    st.plotly_chart(_outcome_strip(proposals), use_container_width=True)

    heatmap = _delegate_reform_heatmap(proposals, delegates, all_votes)
    if heatmap is not None:
        st.plotly_chart(heatmap, use_container_width=True)
    else:
        st.info(
            "No reform proposals with top-30 delegate votes found on Snapshot. "
            "This may indicate that identified reform proposals were primarily on Tally, "
            "where individual vote choices are not available."
        )

    _vote_reasons(proposals)

    st.caption(
        "Decentralizing reform flag: keyword matching on title + body (proposal_type.py). "
        "Top-30 delegates ranked by current voting power from delegate_scorecard. "
        "Delegate heatmap: Snapshot proposals only. "
        "Tally aggregate outcomes included in pass-rate cards. "
        "Sources: Snapshot · Tally · warehouse/ens_retro.duckdb"
    )
