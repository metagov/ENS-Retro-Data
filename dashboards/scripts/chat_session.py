"""Server-side ChatKit session token generation.

Generates a short-lived client secret that the ChatKit widget uses
to authenticate with the OpenAI backend — without exposing the raw API key
to the browser.

Usage:
    from scripts.chat_session import create_chatkit_session
    client_secret = create_chatkit_session(page_context="Challenge: C1 | Hypothesis: H1.1")
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Read workflow ID from environment — set WORKFLOW_ID in .env or as a Fly secret.
# Falls back to the OPENAI_WORKFLOWS_API_KEY env var (same value, different name).
WORKFLOW_ID = (
    os.environ.get("WORKFLOW_ID")
    or os.environ.get("OPENAI_WORKFLOWS_API_KEY")
    or ""
)

# Maximum number of ChatKit session tokens minted per Streamlit browser session.
# Prevents a single session from looping and burning tokens in case of a bug.
# Raised from 10 → 50 so a long-lived dashboard session can safely re-mint
# after the 4-hour cache expiry without hitting the cap.
_SESSION_TOKEN_CAP = 50


def _get_session_id() -> str:
    """Return the Streamlit browser session ID for use as the ChatKit user field.

    Falls back to a static string if the runtime context is unavailable
    (e.g., during unit tests). Sanitised to alphanumeric + hyphens only
    since the ChatKit API rejects arbitrary strings.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx:
            raw = ctx.session_id
            # Keep only safe chars — strip anything the API might reject
            import re
            return re.sub(r"[^a-zA-Z0-9\-]", "", raw)[:64] or "ens-dashboard-user"
    except Exception:
        pass
    return "ens-dashboard-user"


def create_chatkit_session(page_context: str = "") -> str | None:
    """Generate a ChatKit client secret for the current user session.

    Args:
        page_context: Current page/tab context string to pass to the agent
                      e.g. "Challenge: Voter Apathy | Hypothesis: H1.1 Low Incentives"

    Returns:
        client_secret string, or None if generation fails.
    """
    import streamlit as st

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    if not WORKFLOW_ID:
        return None

    # Rate-limit: cap token mints per Streamlit session
    mint_count = st.session_state.get("_chatkit_mint_count", 0)
    if mint_count >= _SESSION_TOKEN_CAP:
        return None
    st.session_state["_chatkit_mint_count"] = mint_count + 1

    session_id = _get_session_id()

    try:
        import httpx

        payload: dict = {"workflow": {"id": WORKFLOW_ID}, "user": session_id}
        # Note: 'metadata' is not yet supported by the ChatKit sessions API (returns 400).
        # page_context is baked into the agent system prompt directly for now.

        r = httpx.post(
            "https://api.openai.com/v1/chatkit/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "chatkit_beta=v1",
            },
            json=payload,
            timeout=10,
        )
        if r.status_code != 200:
            import logging
            logging.getLogger(__name__).error(
                "ChatKit session %s: %s", r.status_code, r.text
            )
            return None
        return r.json()["client_secret"]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("ChatKit session error: %s", e, exc_info=True)
        return None


def is_configured() -> bool:
    """Return True if both the API key and workflow ID are set."""
    return bool(os.environ.get("OPENAI_API_KEY")) and bool(WORKFLOW_ID)
