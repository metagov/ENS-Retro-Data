import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the dashboards/ directory (no-op if file is absent, e.g. on Fly)
load_dotenv(Path(__file__).parent / ".env")

import duckdb
import streamlit as st

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from scripts.config import load_config, resolve_render_fn  # noqa: E402
from scripts.db import get_connection  # noqa: E402

st.set_page_config(
    page_title="ENS DAO Governance Research",
    page_icon="🔵",
    layout="wide",
)

config = load_config()

_DB_PATH = Path(__file__).parent.parent / "warehouse" / "ens_retro.duckdb"


def _data_as_of() -> str:
    """Return a 'data as of' string from the warehouse file mtime."""
    try:
        mtime = _DB_PATH.stat().st_mtime
        from datetime import datetime, timezone
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_wip(label: str = "") -> None:
    suffix = f" — {label}" if label else ""
    st.markdown(
        f"""
<div style="background:#FFFBEB; border-left:3px solid #D69E2E;
            padding:12px 16px; border-radius:0 6px 6px 0;
            color:#744210; font-size:14px; margin:12px 0 24px 0;">
<strong>Work in progress{suffix}</strong><br>
Analysis for this view is under development.
</div>
""",
        unsafe_allow_html=True,
    )


def _get_finding(hyp) -> str | None:
    """Return a one-sentence finding for a hypothesis, or None if WIP."""
    if not hyp.visuals:
        return None
    for visual in hyp.visuals:
        if visual.takeaway:
            text = visual.takeaway.strip().replace("\n", " ")
            end = text.find(". ")
            return text[: end + 1] if end > 0 else text
    desc = (hyp.description or "").strip().replace("\n", " ")
    end = desc.find(". ")
    return desc[: end + 1] if end > 0 else desc


def _render_takeaway(text: str) -> None:
    st.markdown(
        f"""
<div style="background:#F0F4FF; border-left:3px solid #3B4EC8;
            padding:12px 16px; border-radius:0 6px 6px 0;
            color:#2D3748; font-size:14px; margin:12px 0 24px 0;">
<strong>Key takeaway:</strong> {text}
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown("# ENS DAO Governance Research")
st.caption(f"Data as of {_data_as_of()}")
st.markdown(
    """
This dashboard presents quantitative findings from the **ENS DAO Governance Research**,
a structured evaluation of structural challenges in ENS governance commissioned by the ENS DAO
([Snapshot proposal](https://snapshot.org/#/s:ens.eth/proposal/0x8d16992852893f05b23b0e26de27c9e6b2a8de1193c991e14f81ef13cd943517)).
The research is conducted by the [Metagov Research](https://metagov.org) team and combines approximately 23 qualitative
stakeholder interviews with on-chain and forum data analysis.

**Research updates:**
- [Research Update: Phase 1 Complete](https://discuss.ens.domains/t/retrospective-research-update-phase-1-complete/21935) — interviews, data infrastructure, and analysis plan complete
- [ENS Retro Eval Preliminary Results](https://discuss.ens.domains/t/ens-retro-eval-preliminary-results/21976) — preliminary findings and recommendations available for community feedback
"""
)

# ---------------------------------------------------------------------------
# Tabs: Start Here + Challenges
# ---------------------------------------------------------------------------

_CHALLENGE_SUMMARIES = {
    "C1": "Early token allocation still shapes who controls today's votes.",
    "C2": "Most token holders never engage, leaving a small group to govern alone.",
    "C3": "Stakeholders operate in silos with no consistent way to coordinate.",
    "C4": "Real decisions happen through informal networks, not on-chain votes.",
    "C5": "Treasury assets lack adequate accountability mechanisms and financial controls.",
}

_VERDICT_STYLES = {
    "supported":      ("✅ Supported",       "#276749", "#C6F6D5"),
    "mixed":          ("⚠️ Mixed Evidence",   "#744210", "#FEFCBF"),
    "rejected":       ("❌ Not Supported",    "#742A2A", "#FED7D7"),
    "in_development": ("🔄 In Development",  "#4A5568", "#EDF2F7"),
    "explorer":       ("📊 Data Explorer",   "#2B6CB0", "#BEE3F8"),
}


def _verdict_badge(verdict: str) -> str:
    label, color, bg = _VERDICT_STYLES.get(verdict, ("", "#4A5568", "#EDF2F7"))
    if not label:
        return ""
    return (
        f'<span style="background:{bg}; color:{color}; font-size:11px; font-weight:600; '
        f'padding:3px 9px; border-radius:12px; white-space:nowrap;">{label}</span>'
    )

all_tabs = st.tabs(["Start Here"] + [c.short_title for c in config.challenges])
start_tab = all_tabs[0]
challenge_tabs = all_tabs[1:]

with start_tab:
    

    st.markdown("### What this dashboard covers")
    cols = st.columns(5)
    for col, challenge in zip(cols, config.challenges):
        summary = _CHALLENGE_SUMMARIES.get(challenge.id, challenge.description[:80] + "…")
        n = len(challenge.hypotheses)
        col.markdown(
            f"""
<div style="background:#F7FAFC; border:1px solid #E2E8F0; border-radius:8px;
            padding:16px; height:100%;">
<p style="font-weight:700; font-size:15px; color:#2D3748; margin:0 0 8px 0;">
{challenge.short_title}</p>
<p style="font-size:13px; color:#4A5568; margin:0 0 12px 0;">{summary}</p>
<p style="font-size:12px; color:#718096; margin:0;">{n} {"analyses" if n != 1 else "analysis"}</p>
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("### Findings at a glance")
    for challenge in config.challenges:
        summary = _CHALLENGE_SUMMARIES.get(challenge.id, "")
        st.markdown(
            f"""
<div style="border-left:4px solid #3B4EC8; padding:10px 14px; margin:28px 0 12px 0;
            background:#F7FAFC; border-radius:0 6px 6px 0;">
  <span style="font-weight:700; font-size:15px; color:#2D3748;">{challenge.short_title}</span>
  {"<br><span style='font-size:13px; color:#4A5568; font-style:italic;'>" + summary + "</span>" if summary else ""}
</div>
""",
            unsafe_allow_html=True,
        )
        for hyp in challenge.hypotheses:
            finding = _get_finding(hyp)
            desc = (hyp.description or "").strip().replace("\n", " ")
            desc_excerpt = (desc[:220] + "…") if len(desc) > 220 else desc
            badge = _verdict_badge(hyp.verdict)

            finding_html = ""
            if finding:
                finding_html = (
                    f"<div style='margin-top:6px; font-size:13px; color:#2D3748;'>"
                    f"<strong>Finding:</strong> {finding}</div>"
                )
            elif hyp.verdict not in ("explorer", "in_development"):
                finding_html = (
                    "<div style='margin-top:6px; font-size:13px; color:#A0AEC0; font-style:italic;'>"
                    "Analysis in development</div>"
                )

            st.markdown(
                f"""
<div style="border:1px solid #E2E8F0; border-radius:8px; padding:14px 16px;
            margin:6px 0; background:#FFFFFF;">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
    <span style="font-size:13px; font-weight:700; color:#2D3748; flex:1;">
      <span style="background:#E2E8F0; color:#4A5568; font-size:11px; font-weight:600;
                   padding:2px 7px; border-radius:10px; margin-right:6px;">{hyp.id}</span>
      {hyp.title}
    </span>
    {badge}
  </div>
  <div style="font-size:12px; color:#718096; margin-top:6px; line-height:1.5;">{desc_excerpt}</div>
  {finding_html}
</div>
""",
                unsafe_allow_html=True,
            )

for c_tab, challenge in zip(challenge_tabs, config.challenges):
    with c_tab:
        st.markdown(f"## {challenge.title}")
        st.markdown(
            f"<p style='color:#718096; font-size:15px; margin-bottom:16px;'>"
            f"{challenge.description}</p>",
            unsafe_allow_html=True,
        )
        if challenge.doc_url:
            st.markdown(f"[Read the full interview findings →]({challenge.doc_url})")
        st.markdown("---")

        # Hypothesis sub-tabs
        hyp_tabs = st.tabs([h.short_title for h in challenge.hypotheses])

        for h_tab, hyp in zip(hyp_tabs, challenge.hypotheses):
            with h_tab:
                # Hypothesis badge + title
                st.markdown(
                    f"""
<span style="background:#E2E8F0; color:#4A5568; font-size:12px; font-weight:600;
             padding:4px 10px; border-radius:20px; letter-spacing:0.5px;">
    {hyp.id}
</span>
""",
                    unsafe_allow_html=True,
                )
                st.markdown(f"### {hyp.title}")
                st.markdown(
                    f"<p style='color:#718096; font-size:14px; margin-bottom:8px;'>"
                    f"{hyp.description}</p>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")

                # Visuals
                if not hyp.visuals:
                    _render_wip()
                else:
                    for visual in hyp.visuals:
                        st.markdown(f"#### {visual.title}")
                        try:
                            render_fn = resolve_render_fn(visual)
                            render_fn()
                        except (ModuleNotFoundError, AttributeError, duckdb.Error):
                            _render_wip(label=visual.title)
                        else:
                            if visual.takeaway:
                                _render_takeaway(visual.takeaway)
