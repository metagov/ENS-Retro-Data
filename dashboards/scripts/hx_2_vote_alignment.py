"""
Hx.2 — Factional politics
Delegate vote-alignment clustering — surfacing informal coalitions among top-50 delegates.

Approach: Build a delegate × proposal vote matrix, compute pairwise cosine similarity
(for=+1, against=−1; abstain/no-vote excluded), then apply hierarchical clustering
to reveal which delegates consistently vote together — a quantitative proxy for
informal factional coordination.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform

from scripts.chart_utils import CHART_CONFIG, WATERMARK
from scripts.db import get_connection

TOP_N = 50
MIN_SHARED = 3   # min shared contested votes between a delegate pair to compute similarity
MIN_VOTERS = 5   # min top-50 voters per proposal (filters sparse / low-interest proposals)

# Cluster color palette — largest cluster gets index 0 (most prominent color)
_CLUSTER_COLORS = [
    "#4C72B0",  # blue
    "#DD8452",  # orange
    "#55A868",  # green
    "#C44E52",  # red
    "#8172B3",  # purple
    "#937860",  # brown
    "#DA8BC3",  # pink
    "#64B5CD",  # teal
]

# Discrete vote colorscale: for=green, against=red, no-vote/abstain=gray
# Encoded values: for=0, against=1, no-vote=2  →  normalized to [0, 1] within zmin=0, zmax=2
_VOTE_COLORSCALE = [
    [0.000, "#48BB78"], [0.333, "#48BB78"],
    [0.333, "#E07B54"], [0.666, "#E07B54"],
    [0.666, "#CBD5E0"], [1.000, "#CBD5E0"],
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def _load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = get_connection()

    top_del = con.execute(f"""
        SELECT address,
               COALESCE(NULLIF(ens_name, ''), LEFT(address, 10) || '…') AS label,
               voting_power
        FROM main_gold.delegate_scorecard
        ORDER BY voting_power DESC
        LIMIT {TOP_N}
    """).df()

    votes = con.execute(f"""
        WITH top50 AS (
            SELECT address
            FROM main_gold.delegate_scorecard
            ORDER BY voting_power DESC
            LIMIT {TOP_N}
        ),
        snap AS (
            SELECT
                sv.voter,
                sv.proposal_id,
                sv.vote_choice,
                sp.start_date::DATE AS proposal_date,
                LEFT(COALESCE(sp.title, sv.proposal_id), 60) AS proposal_title,
                0 AS src_priority
            FROM main_silver.clean_snapshot_votes sv
            JOIN top50 ON sv.voter = top50.address
            JOIN main_silver.clean_snapshot_proposals sp
                ON sv.proposal_id = sp.proposal_id
        ),
        tally AS (
            SELECT
                tv.voter,
                tv.proposal_id,
                tv.vote_choice,
                tp.start_date::DATE AS proposal_date,
                LEFT(COALESCE(tp.title, tv.proposal_id), 60) AS proposal_title,
                1 AS src_priority
            FROM main_silver.clean_tally_votes tv
            JOIN top50 ON tv.voter = top50.address
            JOIN main_silver.clean_tally_proposals tp
                ON tv.proposal_id = tp.proposal_id
        ),
        combined AS (SELECT * FROM snap UNION ALL SELECT * FROM tally),
        deduped AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY voter, proposal_id
                       ORDER BY src_priority DESC   -- tally wins if both exist
                   ) AS rn
            FROM combined
        )
        SELECT voter, proposal_id, vote_choice, proposal_date, proposal_title
        FROM deduped
        WHERE rn = 1
    """).df()

    return top_del, votes


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def _prepare(
    top_del: pd.DataFrame,
    votes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Encode votes to ±1, filter sparse proposals, pivot to matrix."""
    v = votes.copy()
    # for=+1, against=−1; abstain/unknown → NaN (excluded from cosine similarity)
    v["score"] = v["vote_choice"].map({"for": 1.0, "against": -1.0})

    valid_pids = (
        v[v["score"].notna()]
        .groupby("proposal_id")["voter"]
        .nunique()
        .pipe(lambda s: s[s >= MIN_VOTERS])
        .index
    )
    v = v[v["proposal_id"].isin(valid_pids)]

    prop_meta = (
        v[["proposal_id", "proposal_date", "proposal_title"]]
        .drop_duplicates("proposal_id")
        .sort_values("proposal_date")
        .reset_index(drop=True)
    )

    pivot = v.pivot_table(
        index="voter",
        columns="proposal_id",
        values="score",
        aggfunc="first",
    ).reindex(index=top_del["address"], columns=prop_meta["proposal_id"])

    return pivot, prop_meta


def _cosine_similarity(pivot: pd.DataFrame) -> np.ndarray:
    """Pairwise cosine similarity between delegate vote vectors, skipping NaN positions."""
    arr = pivot.values.astype(float)
    n = arr.shape[0]
    sim = np.zeros((n, n))

    for i in range(n):
        for j in range(i, n):
            mask = ~(np.isnan(arr[i]) | np.isnan(arr[j]))
            if mask.sum() < MIN_SHARED:
                sim[i, j] = sim[j, i] = 0.0
                continue
            vi, vj = arr[i][mask], arr[j][mask]
            ni, nj = np.linalg.norm(vi), np.linalg.norm(vj)
            val = float(np.dot(vi, vj) / (ni * nj)) if (ni > 0 and nj > 0) else 0.0
            sim[i, j] = sim[j, i] = round(val, 4)

    np.fill_diagonal(sim, 1.0)
    return sim


def _filter_isolated(
    top_del: pd.DataFrame,
    pivot: pd.DataFrame,
    sim: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Remove delegates with zero alignment with all others (not enough shared votes)."""
    off_diag = sim.copy()
    np.fill_diagonal(off_diag, 0.0)
    active = off_diag.max(axis=1) > 0
    if active.all():
        return top_del, pivot, sim
    idx = np.where(active)[0]
    return (
        top_del.iloc[idx].reset_index(drop=True),
        pivot.iloc[idx],
        sim[np.ix_(idx, idx)],
    )


def _cluster(sim: np.ndarray, threshold: float) -> tuple[list[int], np.ndarray]:
    """Ward hierarchical clustering; return leaf order + cluster IDs."""
    dist = np.clip(1.0 - sim, 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    Z = linkage(squareform(dist, checks=False), method="ward")
    leaf_order = dendrogram(Z, no_plot=True)["leaves"]
    cluster_ids = fcluster(Z, t=threshold, criterion="distance")
    return leaf_order, cluster_ids


def _assign_cluster_colors(cluster_ids: np.ndarray) -> dict[int, str]:
    """Map cluster IDs to colors; largest cluster gets the first (most prominent) color."""
    unique, counts = np.unique(cluster_ids, return_counts=True)
    sorted_cls = unique[np.argsort(-counts)]
    return {int(cid): _CLUSTER_COLORS[i % len(_CLUSTER_COLORS)] for i, cid in enumerate(sorted_cls)}


def _cluster_runs(s_cls: np.ndarray) -> list[tuple[int, int, int]]:
    """Return contiguous runs as (start_pos, end_pos, cluster_id)."""
    runs = []
    start = 0
    for k in range(1, len(s_cls)):
        if s_cls[k] != s_cls[k - 1]:
            runs.append((start, k - 1, int(s_cls[k - 1])))
            start = k
    runs.append((start, len(s_cls) - 1, int(s_cls[-1])))
    return runs


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _sim_heatmap(
    sim: np.ndarray,
    labels: list[str],
    order: list[int],
    cluster_ids: np.ndarray,
    cluster_color_map: dict[int, str],
) -> go.Figure:
    """50×N pairwise vote-alignment matrix, sorted by cluster with colored labels."""
    s_labels = [labels[i] for i in order]
    s_sim = sim[np.ix_(order, order)]
    s_cls = cluster_ids[order]
    n = len(s_labels)
    runs = _cluster_runs(s_cls)

    fig = go.Figure(go.Heatmap(
        z=s_sim.tolist(),
        x=list(range(n)),
        y=list(range(n)),
        colorscale="RdBu",
        zmid=0, zmin=-1, zmax=1,
        colorbar=dict(
            title=dict(text="Alignment", font=dict(size=12, color="#4A5568")),
            tickfont=dict(size=11, color="#4A5568"),
            thickness=14, len=0.7,
        ),
        customdata=[[s_labels[j] for j in range(n)] for _ in range(n)],
        hovertemplate=(
            "<b>%{text}</b> × <b>%{customdata}</b><br>"
            "Cosine similarity: %{z:.2f}"
            "<extra></extra>"
        ),
        text=[[s_labels[i]] * n for i in range(n)],
        xgap=1, ygap=1,
    ))

    # Colored rectangle borders around each diagonal cluster block
    for start, end, cid in runs:
        color = cluster_color_map[cid]
        fig.add_shape(
            type="rect",
            x0=start - 0.5, y0=start - 0.5,
            x1=end + 0.5,   y1=end + 0.5,
            line=dict(color=color, width=3),
            fillcolor="rgba(0,0,0,0)",
        )

    # Colored y-axis labels via annotations (hide default ticks)
    fig.update_layout(
        yaxis=dict(showticklabels=False, tickvals=list(range(n))),
        xaxis=dict(showticklabels=False, tickvals=list(range(n))),
    )
    for pos, (label, cid) in enumerate(zip(s_labels, s_cls)):
        color = cluster_color_map[cid]
        # Y-axis (left side)
        fig.add_annotation(
            x=-0.005, y=pos,
            xref="paper", yref="y",
            text=label,
            showarrow=False,
            font=dict(size=9, color=color),
            xanchor="right",
            align="right",
        )
        # X-axis (bottom, angled)
        fig.add_annotation(
            x=pos, y=-0.005,
            xref="x", yref="paper",
            text=label,
            showarrow=False,
            font=dict(size=8, color=color),
            textangle=-45,
            xanchor="right",
            yanchor="top",
        )

    fig.update_layout(
        title=dict(
            text="Vote-alignment similarity — top delegates (colored by faction)",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=80, b=160, l=160, r=60),
        height=700,
    )
    fig.add_annotation(**WATERMARK)
    return fig


def _vote_pattern_heatmap(
    pivot: pd.DataFrame,
    prop_meta: pd.DataFrame,
    labels: list[str],
    order: list[int],
    cluster_ids: np.ndarray,
    cluster_color_map: dict[int, str],
) -> go.Figure:
    """Vote pattern grid: delegates (rows sorted by cluster) × proposals (columns by date)."""
    s_addrs  = [pivot.index[i] for i in order]
    s_labels = [labels[i] for i in order]
    s_cls    = cluster_ids[order]
    n        = len(s_labels)
    runs     = _cluster_runs(s_cls)

    arr = pivot.reindex(s_addrs).values.astype(float)
    # Encode: for=0, against=1, abstain/no-vote=2
    encoded = np.where(
        np.isnan(arr), 2.0,
        np.where(arr == 1.0, 0.0, np.where(arr == -1.0, 1.0, 2.0))
    )
    text_arr = np.where(
        np.isnan(arr), "no vote",
        np.where(arr == 1.0, "for", np.where(arr == -1.0, "against", "abstain"))
    )

    prop_labels  = prop_meta["proposal_title"].tolist()
    short_labels = [t[:28] + "…" if len(t) > 28 else t for t in prop_labels]
    n_props      = len(prop_labels)

    fig = go.Figure(go.Heatmap(
        z=encoded.tolist(),
        x=list(range(n_props)),
        y=list(range(n)),
        colorscale=_VOTE_COLORSCALE,
        zmin=0, zmax=2,
        showscale=False,
        customdata=text_arr.tolist(),
        text=[[short_labels[j] for j in range(n_props)] for _ in range(n)],
        hovertemplate="<b>%{yaxis.ticktext[y]}</b><br>%{text}<br>%{customdata}<extra></extra>",
        xgap=1, ygap=1,
    ))

    # Colored horizontal boundary lines + cluster labels on right
    for start, end, cid in runs:
        color = cluster_color_map[cid]
        if start > 0:
            fig.add_shape(
                type="line", line=dict(color=color, width=2),
                x0=-0.5, x1=n_props - 0.5,
                y0=start - 0.5, y1=start - 0.5,
            )

    # Colored y-axis labels via annotations
    fig.update_layout(
        yaxis=dict(showticklabels=False, tickvals=list(range(n))),
        xaxis=dict(showticklabels=False, tickvals=list(range(n_props))),
    )
    for pos, (label, cid) in enumerate(zip(s_labels, s_cls)):
        fig.add_annotation(
            x=-0.005, y=pos,
            xref="paper", yref="y",
            text=label,
            showarrow=False,
            font=dict(size=9, color=cluster_color_map[cid]),
            xanchor="right",
            align="right",
        )

    # X-axis proposal labels (angled, small)
    for pos, label in enumerate(short_labels):
        fig.add_annotation(
            x=pos, y=-0.005,
            xref="x", yref="paper",
            text=label,
            showarrow=False,
            font=dict(size=7, color="#718096"),
            textangle=-60,
            xanchor="right",
            yanchor="top",
        )

    # Vote legend
    for text, color, xpos in [
        ("For", "#48BB78", 0.00),
        ("Against", "#E07B54", 0.10),
        ("No vote / Abstain", "#CBD5E0", 0.22),
    ]:
        fig.add_annotation(
            x=xpos, y=1.04, xref="paper", yref="paper",
            text=f"<span style='color:{color};font-weight:700;'>■</span> {text}",
            showarrow=False,
            font=dict(size=11, color="#4A5568"),
            xanchor="left",
        )

    fig.update_layout(
        title=dict(
            text="Vote pattern by faction — proposals sorted by date",
            font=dict(size=18, color="#2D3748"), x=0, xanchor="left",
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=100, b=200, l=160, r=40),
        height=max(500, 14 * n + 260),
    )
    fig.add_annotation(**WATERMARK)
    return fig


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def _render_cards(
    sim: np.ndarray,
    labels: list[str],
    cluster_ids: np.ndarray,
    cluster_color_map: dict[int, str],
    pivot: pd.DataFrame,
    prop_meta: pd.DataFrame,
) -> None:
    unique_cls, cls_counts = np.unique(cluster_ids, return_counts=True)
    n_factions = len(unique_cls)
    largest_idx = int(cls_counts.argmax())
    largest_cid = int(unique_cls[largest_idx])
    largest_size = int(cls_counts[largest_idx])

    # Most prominent cluster: members + avg within-cluster alignment
    member_indices = np.where(cluster_ids == largest_cid)[0]
    member_labels = [labels[i] for i in member_indices]
    within_pairs = [
        sim[i, j]
        for idx_i, i in enumerate(member_indices)
        for j in member_indices[idx_i + 1:]
    ]
    avg_within = float(np.mean(within_pairs)) if within_pairs else 0.0

    display = ", ".join(member_labels[:4])
    if len(member_labels) > 4:
        display += f" +{len(member_labels) - 4} more"

    largest_color = cluster_color_map[largest_cid]

    # Most divisive proposal (highest std of non-NaN votes among included delegates)
    arr = pivot.values.astype(float)
    stds = np.nanstd(arr, axis=0)
    div_title = "N/A"
    if len(stds) > 0 and np.any(~np.isnan(stds)):
        idx = int(np.nanargmax(stds))
        raw = prop_meta.iloc[idx]["proposal_title"]
        div_title = (raw[:48] + "…") if len(raw) > 48 else raw

    card_css = """
    <style>
    .sc { background:#F7F8FC; border-radius:8px; padding:16px 20px; margin:4px 0; }
    .sc-t { font-size:14px; font-weight:700; color:#3B4EC8; margin-bottom:8px; }
    .sc-r { font-size:13px; color:#4A5568; line-height:1.8; }
    .sc-v { font-weight:600; }
    </style>
    """
    st.markdown(card_css, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">Faction structure</div>
            <div class="sc-r">
                <span class="sc-v" style="color:#2D8A6E;">{n_factions}</span> voting clusters
                detected among <span class="sc-v" style="color:#2D8A6E;">{len(labels)}</span>
                delegates with sufficient shared votes
            </div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">Most prominent cluster</div>
            <div class="sc-r">
                <span class="sc-v" style="color:{largest_color};">{largest_size} delegates</span>
                · avg alignment <span class="sc-v" style="color:{largest_color};">{avg_within:.2f}</span><br>
                <span style="color:{largest_color};">{display}</span>
            </div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="sc">
            <div class="sc-t">Most divisive proposal</div>
            <div class="sc-r">
                <span class="sc-v" style="color:#2D8A6E;">"{div_title}"</span><br>
                highest vote divergence among top delegates
            </div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_vote_alignment() -> None:
    st.markdown(
        "<p style='color:#718096; font-size:14px; margin-bottom:16px;'>"
        "Clusters top delegates (by current delegated VP) by vote co-alignment across all "
        "governance proposals. Delegates who consistently vote together appear in the same "
        "faction — a quantitative proxy for informal coordination outside formal channels. "
        "Label and border colors indicate cluster membership. Delegates with insufficient "
        "shared votes (no faction signal) are excluded. Similarity = cosine distance on "
        "for/against votes; abstentions excluded.</p>",
        unsafe_allow_html=True,
    )

    threshold = st.slider(
        "Cluster distance threshold  (lower = tighter factions)",
        min_value=0.10, max_value=1.50, value=0.50, step=0.05,
        help=(
            "Distance = 1 − cosine similarity. "
            "0.0 = identical voting record. "
            "1.0 = completely orthogonal. "
            "Lower → more, smaller clusters."
        ),
    )

    with st.spinner("Loading vote data…"):
        top_del, votes = _load_data()

    if votes.empty:
        st.warning("No vote data found for top delegates.")
        return

    pivot, prop_meta = _prepare(top_del, votes)

    if pivot.empty or prop_meta.empty:
        st.warning("Insufficient vote data after filtering.")
        return

    sim_full = _cosine_similarity(pivot)
    top_del, pivot, sim = _filter_isolated(top_del, pivot, sim_full)
    n_removed = len(sim_full) - len(sim)

    labels_list = top_del["label"].tolist()
    order, cluster_ids = _cluster(sim, threshold)
    cluster_color_map = _assign_cluster_colors(cluster_ids)

    if n_removed:
        st.caption(
            f"ℹ️ {n_removed} delegate(s) excluded — fewer than {MIN_SHARED} shared "
            f"contested votes with any other top delegate."
        )

    _render_cards(sim, labels_list, cluster_ids, cluster_color_map, pivot, prop_meta)

    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Similarity Matrix", "Vote Pattern Grid"])
    with tab1:
        st.plotly_chart(
            _sim_heatmap(sim, labels_list, order, cluster_ids, cluster_color_map),
            use_container_width=True,
            config=CHART_CONFIG,
        )
    with tab2:
        st.plotly_chart(
            _vote_pattern_heatmap(pivot, prop_meta, labels_list, order, cluster_ids, cluster_color_map),
            use_container_width=True,
            config=CHART_CONFIG,
        )

    n_proposals = len(prop_meta)
    st.caption(
        f"Sources: ENS Snapshot + Tally on-chain governance data. "
        f"Top {TOP_N} delegates by delegated VP, isolated delegates removed. "
        f"{n_proposals} proposals with ≥{MIN_VOTERS} top-delegate voters. "
        f"Similarity = cosine similarity on for/against votes (abstain excluded). "
        f"Min {MIN_SHARED} shared contested votes per pair. Ward hierarchical linkage."
    )
