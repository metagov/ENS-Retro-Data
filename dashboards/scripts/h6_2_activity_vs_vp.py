"""
H6.2 — Reputation lock-in
Activity vs. delegated voting power — Snapshot + Tally tabs wrapper.
"""

import streamlit as st

from scripts.h6_2_snapshot_reputation_lock_in import render_snapshot_activity_vs_vp
from scripts.h6_2_tally_reputation_lock_in import render_tally_activity_vs_vp


def render_activity_vs_vp() -> None:
    tab_snap, tab_tally = st.tabs(["Snapshot", "Tally (On-Chain)"])
    with tab_snap:
        render_snapshot_activity_vs_vp()
    with tab_tally:
        render_tally_activity_vs_vp()
