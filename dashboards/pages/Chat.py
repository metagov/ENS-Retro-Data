"""Full-page ChatKit chat interface.

Accessible from the sidebar or via the expand button in the floating widget.
Uses the same static file approach — loads chat.html from a real URL
so chatkit.js has a valid window.location.href.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.chat_session import is_configured, create_chatkit_session  # noqa: E402
from scripts.chat_widget import _get_cached_secret  # noqa: E402

st.set_page_config(
    page_title="ENS Chat Assistant",
    page_icon="💬",
    layout="wide",
)

st.title("ENS Data Assistant")
st.caption("Ask questions about ENS DAO governance data, delegates, proposals, and the retrospective findings.")

if not is_configured():
    st.error("ChatKit not configured — set `OPENAI_API_KEY` and `WORKFLOW_ID` in `.env`")
    st.stop()

secret = _get_cached_secret()
if not secret:
    st.error("Failed to create ChatKit session — check terminal logs")
    st.stop()

# Full-page chat — use the same static file but rendered large
st.iframe(f"/app/static/chatpage.html#{secret}", height=700)
