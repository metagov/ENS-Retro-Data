import sys
from pathlib import Path

import duckdb
import streamlit as st

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from scripts.config import load_config, resolve_render_fn  # noqa: E402
from scripts.db import get_connection  # noqa: E402
from scripts.chat_widget import render_chat_widget  # noqa: E402

st.set_page_config(
    page_title="ENS DAO Governance Retrospective",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="collapsed",
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

st.markdown("# ENS DAO Governance Retrospective")
st.caption(f"Data as of {_data_as_of()}")
st.markdown(
    """
This dashboard presents quantitative findings from the **ENS DAO Governance Retrospective**,
a structured evaluation of structural challenges in ENS governance commissioned by the ENS DAO
([Snapshot proposal](https://snapshot.org/#/s:ens.eth/proposal/0x8d16992852893f05b23b0e26de27c9e6b2a8de1193c991e14f81ef13cd943517)).
The research is conducted by the [Metagov Research](https://metagov.org) team and combines approximately 23 qualitative
stakeholder interviews with on-chain and forum data analysis.

**Research updates:**
- [Retrospective Research Update: Phase 1 Complete](https://discuss.ens.domains/t/retrospective-research-update-phase-1-complete/21935) — interviews, data infrastructure, and analysis plan complete
- [ENS Retro Eval Preliminary Results](https://discuss.ens.domains/t/ens-retro-eval-preliminary-results/21976) — preliminary findings and recommendations available for community feedback
"""
)

with st.expander("How this dashboard is organized"):
    st.markdown(
        """
The tabs below map directly to the **governance challenges** surfaced during the retrospective.
For each challenge, the research team formulated one or more **hypotheses** — plausible explanations
for why that challenge exists. Each hypothesis is evaluated against quantitative evidence drawn from
on-chain activity, forum participation, and delegate behavior data.

| Level | What it represents |
|---|---|
| **Tab** | A distinct governance challenge identified in the retro |
| **Sub-tab** | A hypothesis under investigation for that challenge |
| **Charts & metrics** | Supporting data that tests the hypothesis |

Use the tabs to navigate challenges and the sub-tabs to explore the hypotheses and evidence underneath each one.
"""
    )

# ---------------------------------------------------------------------------
# Challenge tabs
# ---------------------------------------------------------------------------

challenge_tabs = st.tabs([c.short_title for c in config.challenges])

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

# ---------------------------------------------------------------------------
# Chat widget
# ---------------------------------------------------------------------------

render_chat_widget()
