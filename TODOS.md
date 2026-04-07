# TODOS

Items deferred from engineering review on 2026-03-27 (branch: dashboard-setup-v2).

---

## When `render-deploy` is merged to main

**Render service branch setting:** The 3 Render services (`ens-retro-dashboard`,
`ens-retro-api`, `ens-retro-dagster`) are currently pointed at the `render-deploy`
branch because `Dockerfile.api`, `Dockerfile.dagster`, and `render.yaml` only exist
there. After merging `render-deploy` → `main`:

1. Update `render.yaml` to set `branch: main` on all 3 services
2. Via the Render API or dashboard, switch each service back to `branch: main`:
   ```bash
   export RENDER_API_KEY=<key>
   for id in srv-d7a95bbuibrs73fsq7lg srv-d7a95bbuibrs73fsq7mg srv-d7a95bbuibrs73fsq7m0; do
     curl -X PATCH -H "Authorization: Bearer $RENDER_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{"branch":"main"}' \
       "https://api.render.com/v1/services/$id"
   done
   ```
3. Delete the `render-deploy` branch locally and on origin once main is green
4. Confirm auto-deploy triggers on subsequent pushes to main

**Why:** Blueprint expects `branch: main` per convention, and the split-brain
between render.yaml and service config will drift otherwise.

**Dagster run history (LFS):** Only 4 `.db` files in `.dagster/storage/` survived
the Git LFS migration (originally ~40). Re-materialize Dagster assets locally to
repopulate run history, then commit `.dagster/storage/` to share it via LFS.

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

## Gold: unified governance↔discourse activity table

**What:** Create `gold/governance_discourse_activity.sql` that unions
`tally_discourse_crosswalk` and `snapshot_discourse_crosswalk` and joins
in forum engagement metrics (posts_count, reply_count, like_count, views)
from `stg_forum_topics`.

**Why:** Downstream dashboards and API queries shouldn't need to know
whether a proposal came from Tally or Snapshot to get its forum engagement.
A single gold table with `(source, proposal_id, topic_id, forum_metrics...)`
is the natural join key.

**Pros:** One join for analytics. Makes "most-discussed proposals" and
"proposals with no forum debate" trivial to query. Consistent with existing
gold-layer conventions.

**Cons:** Only valuable once an actual dashboard consumer exists. Premature
if built before a concrete use case.

**Context:** Deferred from /plan-eng-review on 2026-04-07 (branch:
`feat/proposal-discourse-crosswalk`). The silver crosswalks are complete;
this would be a thin gold layer on top. Both silver models expose
`(proposal_id, topic_id, match_source)` with identical schemas.

**Depends on:** `feat/proposal-discourse-crosswalk` merged.
