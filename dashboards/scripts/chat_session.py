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

# ---------------------------------------------------------------------------
# TODO: Insert your Agent Builder workflow ID here once you have it.
# Get it from: platform.openai.com/agents → your agent → copy workflow ID
# ---------------------------------------------------------------------------
WORKFLOW_ID = "TODO_INSERT_WORKFLOW_ID_HERE"


def create_chatkit_session(page_context: str = "") -> str | None:
    """Generate a ChatKit client secret for the current user session.

    Args:
        page_context: Current page/tab context string to pass to the agent
                      e.g. "Challenge: Voter Apathy | Hypothesis: H1.1 Low Incentives"

    Returns:
        client_secret string, or None if generation fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    if WORKFLOW_ID == "TODO_INSERT_WORKFLOW_ID_HERE":
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        session = client.chatkit.sessions.create({
            "workflow": {"id": WORKFLOW_ID},
            "user": "ens-dashboard-user",
            **({"metadata": {"page_context": page_context}} if page_context else {}),
        })
        return session.client_secret
    except Exception:
        return None


def is_configured() -> bool:
    """Return True if both the API key and workflow ID are set."""
    return (
        bool(os.environ.get("OPENAI_API_KEY"))
        and WORKFLOW_ID != "TODO_INSERT_WORKFLOW_ID_HERE"
    )
