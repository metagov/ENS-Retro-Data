# TODOS

Items deferred from engineering review on 2026-03-27 (branch: dashboard-setup-v2).

---

## Nakamoto / Gini computation — read from gold table instead of computing inline

**What:** Once `main_gold.decentralization_index` is materialized, `h2_1_concentration_curve.py`
should read its `nakamoto_coefficient` and `voting_power_gini` values from the table instead
of recomputing them with inline NumPy math.

**Why:** Eliminates two sources of truth for the same metric. If rounding logic or filters
ever change in the dbt model, the dashboard will automatically reflect the authoritative value.

**Pros:** Single source of truth; dashboard math is auditable via dbt.

**Cons:** Adds a dependency on `decentralization_index` being materialized (it's being built
in this PR, so this unblocks it immediately after merge).

**Context:** `infra/dbt/models/gold/decentralization_index.py` already computes both metrics.
`h2_1_concentration_curve.py:20-37` duplicates the math. The dbt model was not previously
materialized; it will be after this PR. Update the dashboard script to query
`SELECT value FROM main_gold.decentralization_index WHERE metric IN ('nakamoto_coefficient', 'voting_power_gini')`.

**Depends on:** `main_gold.decentralization_index` being materialized (done in this PR).

---

## CRITICAL: Fix MCP server connection from Agent Builder

**What:** Agent Builder cannot connect to the MCP server (`api.py` at `/mcp`). The agent has no
access to the DuckDB warehouse — it can only answer from static vector store snapshots, not live
SQL. This blocks the core data analyst functionality.

**Why:** Without MCP, the agent cannot run `query_duckdb` or `list_tables`. It cannot produce
live counts, rankings, trends, or cross-table joins. It becomes a documentation lookup tool
instead of a data analyst. The entire value proposition of the chat widget depends on MCP.

**Pros:** Enables live SQL queries through the agent — the agent becomes a real data analyst
that can answer "top 10 delegates by voting power" or "participation trend over last 20 proposals"
from actual warehouse data, not stale snapshots.

**Cons:** Requires Fly.io deployment (or a permanent public URL). May require debugging OpenAI's
Agent Builder MCP integration, which has known platform bugs.

**Context:** The MCP server (`dashboards/api.py`) works perfectly when tested with curl — both
locally and through a Cloudflare tunnel. FastMCP 3.x serves Streamable HTTP transport at `/mcp/`.
Agent Builder returns HTTP 424 (Failed Dependency) and never sends a request to the server.

Root causes to investigate:
1. Deploy to Fly.io and test with production URL (`https://ens-retro-data.fly.dev/mcp`)
2. Agent Builder may block temporary tunnel domains (trycloudflare.com)
3. Agent Builder may not handle Streamable HTTP transport correctly (GET probe returns 406)
4. Known Agent Builder platform bug — documented in multiple OpenAI community threads
5. Fallback: replace MCP with REST HTTP tool calls if MCP remains broken

See `DEV/ChatkitSetup.md` → "CRITICAL BUG: Agent Builder cannot connect to MCP server" for
full investigation notes.

**Depends on:** Fly.io deployment (`fly secrets set AGENT_API_KEY=<key> OPENAI_API_KEY=<key>` + `fly deploy`).

---

## Add query concurrency limiter to prevent OOM on Fly.io

**What:** Add an `asyncio.Semaphore` (max 2 concurrent queries) around the DuckDB execution
path in `api.py` to prevent two simultaneous 1GB queries from OOM-killing the 2GB Fly.io machine.

**Why:** Each `_get_conn()` sets `memory_limit=1GB`. Two concurrent queries = 2GB claimed =
machine limit. A third request could trigger OOM kill.

**Pros:** Prevents server crash under concurrent load; requests queue instead of crash.

**Cons:** Adds ~5 lines of async wrapper code. Queued requests may timeout at the client side
if the queue grows.

**Context:** Traffic is expected to be low (internal dashboard, single agent). But a user
refreshing the page while the agent is mid-query creates 2 concurrent requests easily.
Add an `asyncio.Semaphore(2)` wrapping `_get_conn()` + `conn.execute()` in both
`api_agent_query()` and `_run_query()`.

**Depends on:** Nothing — can be done independently.

---
