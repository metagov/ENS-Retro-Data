# ChatKit Integration — Implementation Todo

**Approach:** OpenAI ChatKit widget (CDN embed via `st.components.v1.html`) + OpenAI API key directly.
No Agent Builder workflow — just drop in the `workflow_id` once you have it.

**Stack:** ChatKit CDN → Streamlit `components.html` → Python session token → OpenAI API

---

## Step 1 — Environment & Dependencies ✅

- [x] Add `openai>=1.0` to `dashboards/requirements.txt`
- [x] Add `python-dotenv>=1.0` to `dashboards/requirements.txt`
- [x] Add `tabulate>=0.9` to `dashboards/requirements.txt` (for markdown table output)
- [x] Install locally: `pip install openai tabulate`
- [x] Confirm `OPENAI_API_KEY` is in `.env` at repo root
- [ ] Add `OPENAI_API_KEY=` to `.env.example` (without value)

---

## Step 2 — DuckDB Query Tool ✅

**File:** `dashboards/scripts/chat_tools.py`

- [x] Implement `query_duckdb(sql: str) -> str`
  - [x] Read-only connection to `warehouse/ens_retro.duckdb`
  - [x] Returns results as markdown table (max 50 rows)
  - [x] Catches and returns errors as strings
  - [x] SQL injection guard — blocks INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE
- [x] Implement `list_tables() -> str`
  - [x] Returns all table names + column names + data types
- [x] Tested against live warehouse — delegate_scorecard query returns correct data ✅

---

## Step 3 — ChatKit Session Token ✅

**File:** `dashboards/scripts/chat_session.py`

- [x] Implement `create_chatkit_session(page_context) -> str | None`
  - [x] Loads `OPENAI_API_KEY` from `.env`
  - [x] Calls `openai.chatkit.sessions.create()` with workflow ID + page context metadata
  - [x] Returns `client_secret` for the ChatKit widget
  - [x] Returns `None` gracefully if key or workflow ID is missing
- [x] Implement `is_configured() -> bool`
  - [x] Returns False if either API key or workflow ID is missing
- [ ] **TODO: Insert workflow ID** — open `dashboards/scripts/chat_session.py`
      and replace `TODO_INSERT_WORKFLOW_ID_HERE` with your actual workflow ID
      from platform.openai.com/agents

---

## Step 4 — Page Context Detection ✅

**File:** `dashboards/app.py` (tab render loop)

- [x] `st.session_state["current_challenge"]` written on each challenge tab render
- [x] `st.session_state["current_hypothesis"]` written on each hypothesis sub-tab render
- [x] `get_page_context()` in `chat_widget.py` reads session state and formats context string
  - e.g. `"Challenge: Voter Apathy | Hypothesis: H1.1 Low Incentives"`
  - Falls back to `"ENS DAO Governance Dashboard"` if not set

---

## Step 5 — Floating Widget UI ✅

**File:** `dashboards/scripts/chat_widget.py`

- [x] ChatKit CDN script tag injected (`cdn.platform.openai.com/deployments/chatkit/chatkit.js`)
- [x] Floating bubble button — `position: fixed; bottom: 24px; right: 24px`
  - [x] ENS blue (`#3B4EC8`) background, white chat icon
  - [x] Hover effect (scale + darker blue)
  - [x] Toggles between 💬 and × on open/close
- [x] Chat panel — `position: fixed; bottom: 88px; right: 24px; 380×540px`
  - [x] ENS blue header with "ENS Data Assistant" title
  - [x] Context badge in header (current challenge/hypothesis)
  - [x] Close button (×)
  - [x] ChatKit mounts into panel on first open
  - [x] Retry logic if ChatKit CDN script hasn't loaded yet
- [x] Widget renders as `height=0` component — takes no page space
- [x] Widget silently skips render if not configured (no broken UI)

---

## Step 6 — Wire into app.py ✅

**File:** `dashboards/app.py`

- [x] Import `render_chat_widget` from `chat_widget.py`
- [x] Context writes added to challenge + hypothesis tab loops
- [x] `render_chat_widget()` called at bottom of `app.py` (after all tabs)

---

## Step 7 — One Remaining Step ⏳

- [ ] **Get workflow ID from Agent Builder** (user is doing this)
  1. Go to platform.openai.com/agents
  2. Create a new agent — give it the system prompt below
  3. Add two tools: `query_duckdb` and `list_tables` (define as function tools)
  4. Copy the workflow ID
  5. Paste into `dashboards/scripts/chat_session.py` → `WORKFLOW_ID = "..."`

**Suggested Agent Builder system prompt:**
```
You are an ENS DAO data assistant embedded in a governance dashboard.
You help researchers and community members explore ENS DAO governance data.

You have access to two tools:
- list_tables: discover what data is available in the warehouse
- query_duckdb: run SQL SELECT queries to answer data questions

Key tables:
- main_gold.delegate_scorecard — delegate rankings, voting power, participation rate
- main_gold.governance_activity — proposal outcomes, vote counts, pass/fail rates
- main_gold.treasury_summary — monthly treasury spending by category
- main_silver.clean_token_distribution — ENS token holder distribution
- main_silver.clean_delegations — delegation events over time
- main_silver.clean_compensation — DAO compensation payments

Rules:
- Always call list_tables first if you're unsure of column names
- Only use SELECT queries — never modify data
- Be concise and cite specific numbers
- When context mentions a specific challenge or hypothesis, focus your answers there
```

---

## Step 8 — Testing (after workflow ID inserted)

- [ ] Open dashboard — confirm 💬 bubble appears bottom-right
- [ ] Click bubble — confirm panel opens with ENS blue header
- [ ] Check context badge matches current tab
- [ ] Ask: "Who are the top 5 delegates by voting power?" — confirm data answer
- [ ] Ask: "How many proposals passed vs failed?" — confirm query runs
- [ ] Ask: "Drop all tables" — confirm agent refuses
- [ ] Switch challenge tabs — confirm context badge updates
- [ ] Run test suite: `python3 -m pytest tests/ -v` — confirm 0 regressions

---

## Step 9 — Deployment

- [ ] Add `OPENAI_API_KEY` as Fly.io secret: `fly secrets set OPENAI_API_KEY=<key>`
- [ ] Deploy: `fly deploy`
- [ ] Smoke test widget on live URL

---

## File Map

```
dashboards/
├── app.py                          ← UPDATED: context tracking + render_chat_widget()
├── requirements.txt                ← UPDATED: openai, python-dotenv, tabulate
├── addChatKit.md                   ← this file
├── scripts/
│   ├── chat_tools.py               ← NEW ✅: query_duckdb(), list_tables()
│   ├── chat_session.py             ← NEW ✅: create_chatkit_session() — needs workflow_id
│   └── chat_widget.py              ← NEW ✅: render_chat_widget(), ChatKit CDN embed
```

---

## Blocking: Workflow ID

Everything is built. The only thing needed to make the widget live is:

```python
# dashboards/scripts/chat_session.py — line 17
WORKFLOW_ID = "TODO_INSERT_WORKFLOW_ID_HERE"  # ← replace this
```
