"""Full-page ChatKit chat interface.

Strips all Streamlit chrome — ChatKit fills the viewport.
A minimal back link overlays top-left for navigation.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.chat_session import is_configured  # noqa: E402
from scripts.chat_widget import _get_cached_secret  # noqa: E402

st.set_page_config(
    page_title="ENS Chat Assistant",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if not is_configured():
    st.error("ChatKit not configured — set `OPENAI_API_KEY` and `WORKFLOW_ID` in `.env`")
    st.stop()

secret = _get_cached_secret()
if not secret:
    st.error("Failed to create ChatKit session — check terminal logs")
    st.stop()

# Hide ALL Streamlit chrome — header, footer, sidebar toggle, block container padding
# so the iframe fills the entire viewport
st.markdown("""
<style>
  header[data-testid="stHeader"] { display: none !important; }
  footer { display: none !important; }
  [data-testid="stSidebarCollapsedControl"] { display: none !important; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  [data-testid="stIFrame"] {
    border: none !important;
    width: 100vw !important;
    height: calc(100vh - 4px) !important;
  }
</style>
""", unsafe_allow_html=True)

st.iframe(f"/app/static/chatpage.html#{secret}", height=800)
