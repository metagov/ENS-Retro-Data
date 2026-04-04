"""ChatKit floating widget for the ENS DAO dashboard.

Renders a fixed bottom-right chat bubble that opens a ChatKit panel.
The widget is embedded via st.components.v1.html() using the OpenAI
ChatKit CDN — no iframe for the full page, just the chat bubble itself.

Page context (current challenge + hypothesis) is injected into the
ChatKit session so the agent knows what the user is looking at.
"""

import html
import re
import time

import streamlit as st
import streamlit.components.v1 as components

from scripts.chat_session import create_chatkit_session, is_configured

# Prompt injection guard: strip control characters and common injection patterns
# from the page context before it is sent to the model as metadata.
_CTX_STRIP = re.compile(r"[\x00-\x1f\x7f]|(\bignore\b.*\binstructions?\b)", re.IGNORECASE)
_MAX_CTX_LEN = 200

# TTL for the cached client_secret (seconds). ChatKit sessions are short-lived;
# re-use within 5 minutes to avoid hammering the sessions API on every Streamlit rerun.
_SECRET_TTL = 300


def _sanitize_context(raw: str) -> str:
    """Strip control characters and potential prompt-injection text."""
    cleaned = _CTX_STRIP.sub("", raw)
    return cleaned[:_MAX_CTX_LEN]


def get_page_context() -> str:
    """Read current challenge/hypothesis from session state."""
    challenge = st.session_state.get("current_challenge", "")
    hypothesis = st.session_state.get("current_hypothesis", "")
    if challenge and hypothesis:
        raw = f"Challenge: {challenge} | Hypothesis: {hypothesis}"
    elif challenge:
        raw = f"Challenge: {challenge}"
    else:
        raw = "ENS DAO Governance Dashboard"
    return _sanitize_context(raw)


def _get_cached_secret(page_context: str) -> str | None:
    """Return a cached client_secret if still within TTL, else mint a fresh one."""
    now = time.monotonic()
    cached = st.session_state.get("_chatkit_secret")
    cached_at = st.session_state.get("_chatkit_secret_ts", 0.0)
    if cached and (now - cached_at) < _SECRET_TTL:
        return cached
    secret = create_chatkit_session(page_context=page_context)
    if secret:
        st.session_state["_chatkit_secret"] = secret
        st.session_state["_chatkit_secret_ts"] = now
    return secret


def render_chat_widget() -> None:
    """Render the floating ChatKit widget at the bottom-right of every page.

    If the workflow ID or API key is not configured, renders nothing.
    """
    if not is_configured():
        # Silently skip — don't show a broken widget
        # Uncomment below to show a dev warning:
        # st.sidebar.warning("ChatKit: set OPENAI_API_KEY and WORKFLOW_ID in chat_session.py")
        return

    page_context = get_page_context()
    client_secret = _get_cached_secret(page_context=page_context)

    if not client_secret:
        return

    # ENS brand colours
    ENS_BLUE = "#3B4EC8"
    ENS_BLUE_HOVER = "#2D3DAF"
    ENS_LIGHT = "#F0F4FF"  # noqa: F841

    # Escape values that appear in HTML/JS context to prevent XSS.
    # page_context goes into an HTML text node; client_secret goes into a JS string literal.
    safe_context = html.escape(page_context)
    # JSON-encode the secret so any special chars are safely escaped in the JS string
    import json as _json
    safe_secret = _json.dumps(client_secret)  # produces a quoted JS string literal

    html_doc = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdn.platform.openai.com/deployments/chatkit/chatkit.js" async></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: transparent; overflow: hidden; }}

  /* Floating bubble button */
  #chat-bubble {{
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: {ENS_BLUE};
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 16px rgba(59,78,200,0.35);
    z-index: 9999;
    transition: background 0.2s, transform 0.15s;
    font-size: 22px;
  }}
  #chat-bubble:hover {{
    background: {ENS_BLUE_HOVER};
    transform: scale(1.07);
  }}

  /* Chat panel */
  #chat-panel {{
    position: fixed;
    bottom: 88px;
    right: 24px;
    width: 380px;
    height: 540px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.18);
    z-index: 9998;
    display: none;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid #E2E8F0;
  }}
  #chat-panel.open {{
    display: flex;
  }}

  /* Panel header */
  #chat-header {{
    background: {ENS_BLUE};
    color: white;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }}
  #chat-header-left {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  #chat-title {{
    font-weight: 600;
    font-size: 14px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  #chat-context {{
    font-size: 11px;
    opacity: 0.8;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    max-width: 280px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  #close-btn {{
    background: none;
    border: none;
    color: white;
    cursor: pointer;
    font-size: 20px;
    opacity: 0.8;
    padding: 0 4px;
    line-height: 1;
  }}
  #close-btn:hover {{ opacity: 1; }}

  /* ChatKit container */
  #chatkit-container {{
    flex: 1;
    overflow: hidden;
  }}
</style>
</head>
<body>

<!-- Floating bubble -->
<button id="chat-bubble" onclick="toggleChat()" title="Ask ENS Data">
  💬
</button>

<!-- Chat panel -->
<div id="chat-panel">
  <div id="chat-header">
    <div id="chat-header-left">
      <span id="chat-title">ENS Data Assistant</span>
      <span id="chat-context">{safe_context}</span>
    </div>
    <button id="close-btn" onclick="toggleChat()">×</button>
  </div>
  <div id="chatkit-container"></div>
</div>

<script>
  let chatInitialized = false;

  function toggleChat() {{
    const panel = document.getElementById('chat-panel');
    const isOpen = panel.classList.contains('open');

    if (!isOpen) {{
      panel.classList.add('open');
      document.getElementById('chat-bubble').innerHTML = '×';
      document.getElementById('chat-bubble').style.fontSize = '24px';
      if (!chatInitialized) {{
        initChatKit();
        chatInitialized = true;
      }}
    }} else {{
      panel.classList.remove('open');
      document.getElementById('chat-bubble').innerHTML = '💬';
      document.getElementById('chat-bubble').style.fontSize = '22px';
    }}
  }}

  function initChatKit() {{
    const container = document.getElementById('chatkit-container');
    if (window.ChatKit) {{
      window.ChatKit.mount(container, {{
        getClientSecret: async () => {safe_secret},
        style: {{
          height: '100%',
          borderRadius: '0',
        }}
      }});
    }} else {{
      // ChatKit script still loading — retry after short delay
      setTimeout(initChatKit, 500);
    }}
  }}
</script>
</body>
</html>
"""

    # Render as a fixed-position overlay — height 0 so it takes no page space
    components.html(html_doc, height=0, scrolling=False)
