"""
H6.2 — Reputation lock-in
Inactivity gaps vs delegation retention — Snapshot + Tally tabs wrapper.
"""

import streamlit as st

from scripts.h6_2_snapshot_inactivity_gaps import render_snapshot_inactivity_gaps
from scripts.h6_2_tally_inactivity_gaps import render_tally_inactivity_gaps


def render_inactivity_gaps() -> None:
    tab_snap, tab_tally = st.tabs(["Snapshot", "Tally (On-Chain)"])
    with tab_snap:
        render_snapshot_inactivity_gaps()
    with tab_tally:
        render_tally_inactivity_gaps()
