"""ChatKit widget for the ENS DAO dashboard.

Embeds the OpenAI ChatKit hosted UI via a static HTML file served by
Streamlit's built-in static file server (server.enableStaticServing=true).

Why static file instead of srcdoc iframe:
  chatkit.js calls  new URL(path, window.location.href)  to build API
  endpoints. Inside a srcdoc iframe, location.href is "about:srcdoc" —
  not a valid URL base — which crashes the custom element constructor.
  Loading via a real URL (/app/static/chat.html) gives chatkit.js a
  valid location.href and everything works.

The client_secret is passed via URL fragment (#ek_...) which is never
sent to the server — it stays client-side only.
"""

import time

import streamlit as st

from scripts.chat_session import create_chatkit_session, is_configured

_SECRET_TTL = 1800  # reuse session token for 30 min — avoids re-minting on every dashboard rerun


def _get_cached_secret() -> str | None:
    """Mint a new session token or return the cached one if still fresh."""
    now = time.monotonic()
    cached = st.session_state.get("_chatkit_secret")
    cached_at = st.session_state.get("_chatkit_secret_ts", 0.0)
    if cached and (now - cached_at) < _SECRET_TTL:
        return cached
    secret = create_chatkit_session()
    if secret:
        st.session_state["_chatkit_secret"] = secret
        st.session_state["_chatkit_secret_ts"] = now
    return secret


def render_chat_widget() -> None:
    """Embed the ChatKit hosted UI at the bottom of the page."""
    if not is_configured():
        return

    secret = _get_cached_secret()
    if not secret:
        return

    # Load the static HTML via URL (not srcdoc) — gives chatkit.js a real
    # window.location.href so its URL constructor doesn't crash.
    # Secret passed via fragment — never hits the server.
    # height=1: the iframe takes no page space. chat.html uses
    # window.frameElement to position itself fixed at bottom-right.
    st.iframe(f"/app/static/chat.html#{secret}", height=1)
