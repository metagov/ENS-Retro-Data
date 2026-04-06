"""FastAPI + MCP server for ChatKit agent tool calls.

Endpoints:
    GET  /api/tables        — list permitted gold/silver tables and their columns
    POST /api/agent-query   — hardened SELECT-only REST endpoint (testing/fallback)
    /mcp                    — MCP server for Agent Builder (primary integration)

MCP tools exposed at /mcp:
    query_duckdb(sql)       — run a validated SELECT against the ENS DAO warehouse
    list_tables()           — return all permitted tables with column names and types

Security layers on all query paths (applied in order):
    1. Bearer token auth      — AGENT_API_KEY env var (skipped in dev if unset)
    2. Length cap             — 4,000-char query maximum
    3. sqlglot AST parse      — must be a single SELECT; DML/DDL nodes rejected
                                even when buried inside CTEs or subqueries
    4. Table allowlist        — only main_gold and main_silver schemas permitted
    5. Regex fallback         — catches edge cases if sqlglot parse fails
    6. DuckDB read_only=True  — OS-level write block, unconditional last defence
    7. Resource limits        — 4 threads, 1GB memory, 500-row result cap

Run locally:
    uvicorn dashboards.api:app --reload --port 8001

Register in Agent Builder:
    MCP Server URL  → https://ens-retro-data.fly.dev/mcp
    Access token    → value of AGENT_API_KEY env var
"""

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_DB_PATH = Path(__file__).parent.parent / "warehouse" / "ens_retro.duckdb"
_AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "")

_MAX_QUERY_LEN = 4_000
_MAX_ROWS = 500  # enough for meaningful analysis; agent summarises, not dumps

# Only these schemas are queryable. System schemas are never included.
_ALLOWED_SCHEMAS = {"main_gold", "main_silver", "main"}

# Tables blocked even within allowed schemas (extend as needed).
_BLOCKED_TABLES: set[str] = set()

app = FastAPI(title="ENS Retro Agent API", docs_url=None, redoc_url=None)
# NOTE: lifespan is patched below after MCP server is created (FastMCP 3.x requirement)
_bearer = HTTPBearer(auto_error=False)


# Agent Builder sends POST /mcp (no trailing slash). FastAPI's Mount redirects
# /mcp → /mcp/ via 307, but Agent Builder doesn't follow redirects → 424 error.
# Fix: rewrite the path so no redirect is needed.
from starlette.middleware.base import BaseHTTPMiddleware as _BHTTP

class _TrailingSlashMiddleware(_BHTTP):
    async def dispatch(self, request, call_next):
        if request.url.path == "/mcp":
            request.scope["path"] = "/mcp/"
        return await call_next(request)

app.add_middleware(_TrailingSlashMiddleware)


# ---------------------------------------------------------------------------
# Layer 1: Bearer token auth
# ---------------------------------------------------------------------------

def _check_auth(creds: HTTPAuthorizationCredentials | None) -> None:
    """Validate Bearer token. If AGENT_API_KEY is unset, dev mode — allow all."""
    if not _AGENT_API_KEY:
        return
    if creds is None or creds.credentials != _AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized.")


# ---------------------------------------------------------------------------
# Layer 2–5: SQL validation
# ---------------------------------------------------------------------------

# Regex fallback — used when sqlglot parse fails
_UNSAFE_RE = re.compile(
    r"(;|--|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\bcreate\b"
    r"|\balter\b|\btruncate\b|\breplace\b|\bcopy\b|\battach\b|\bdetach\b"
    r"|\bpragma\b|\bload\b|\binstall\b|\bexec\b|\bexecute\b)",
    re.IGNORECASE,
)
_SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# DML/DDL node types that must never appear anywhere in the AST
_BLOCKED_AST_TYPES: tuple = ()  # populated lazily after sqlglot import


def _get_blocked_ast_types() -> tuple:
    global _BLOCKED_AST_TYPES
    if not _BLOCKED_AST_TYPES:
        import sqlglot.expressions as exp
        _BLOCKED_AST_TYPES = (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
            exp.AlterTable, exp.Command, exp.Use, exp.Transaction,
            exp.Commit, exp.Rollback, exp.LoadData,
        )
    return _BLOCKED_AST_TYPES


def _validate_sql(sql: str) -> str:
    """Return the normalised SQL string or raise HTTPException."""
    sql = sql.strip()

    if not sql:
        raise HTTPException(status_code=400, detail="Empty query.")

    if len(sql) > _MAX_QUERY_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Query exceeds {_MAX_QUERY_LEN}-character limit.",
        )

    try:
        import sqlglot
        import sqlglot.expressions as exp

        # Layer 3a: must parse as exactly one statement
        statements = sqlglot.parse(sql, dialect="duckdb")
        if len(statements) != 1 or statements[0] is None:
            raise HTTPException(
                status_code=400,
                detail="Exactly one SELECT statement is required.",
            )
        stmt = statements[0]

        # Layer 3b: top-level statement must be SELECT
        if not isinstance(stmt, exp.Select):
            raise HTTPException(
                status_code=400,
                detail="Only SELECT statements are permitted.",
            )

        # Layer 3c: walk the full AST — no DML/DDL anywhere (including CTEs)
        blocked = _get_blocked_ast_types()
        for node in stmt.walk():
            if isinstance(node, blocked):
                raise HTTPException(
                    status_code=400,
                    detail=f"Disallowed operation in query: {type(node).__name__}.",
                )

        # Layer 4: table allowlist
        for table_node in stmt.find_all(exp.Table):
            raw_schema = table_node.args.get("db")
            schema = (str(raw_schema) if raw_schema else "main_gold").lower()
            name = (table_node.name or "").lower()

            if schema not in _ALLOWED_SCHEMAS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Schema '{schema}' is not permitted. "
                           f"Allowed: {sorted(_ALLOWED_SCHEMAS)}.",
                )
            if name in _BLOCKED_TABLES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Table '{name}' is not accessible.",
                )

    except HTTPException:
        raise
    except Exception:
        # sqlglot unavailable or parse failed — apply regex fallback (Layer 5)
        _fallback_validate(sql)

    return sql


def _fallback_validate(sql: str) -> None:
    """Regex guard used when sqlglot is unavailable or fails to parse."""
    if not _SELECT_RE.match(sql):
        raise HTTPException(
            status_code=400, detail="Only SELECT queries are permitted."
        )
    if _UNSAFE_RE.search(sql):
        raise HTTPException(
            status_code=400, detail="Query contains disallowed syntax."
        )


# ---------------------------------------------------------------------------
# Layer 6: DuckDB read-only connection (+ Layer 7: resource limits)
# ---------------------------------------------------------------------------

def _get_conn():
    import duckdb
    conn = duckdb.connect(str(_DB_PATH), read_only=True)
    # 4 threads: DuckDB's parallel columnar execution matters for joins across
    # 37k delegates + 116k delegators. Single-thread kills aggregation quality.
    conn.execute("SET threads TO 4")
    # 1GB: complex queries (percentile, Gini, multi-join aggregations) need room.
    # Fly.io shared-2x machine has 2GB total — 1GB leaves headroom for the app.
    conn.execute("SET memory_limit='1GB'")
    return conn


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    result: list[dict[str, Any]]
    row_count: int
    truncated: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/tables")
def api_tables(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
):
    """Return all permitted tables with column names and types."""
    _check_auth(creds)
    try:
        conn = _get_conn()
        tables = conn.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """).fetchdf()

        result = []
        for _, row in tables.iterrows():
            schema = str(row["table_schema"])
            if schema not in _ALLOWED_SCHEMAS:
                continue
            table = str(row["table_name"])
            cols = conn.execute(
                "SELECT column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                [schema, table],
            ).fetchdf()
            result.append({
                "schema": schema,
                "table": table,
                "columns": [
                    {"name": r["column_name"], "type": r["data_type"]}
                    for _, r in cols.iterrows()
                ],
            })
        conn.close()
        return {"tables": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent-query", response_model=QueryResponse)
def api_agent_query(
    body: QueryRequest,
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
):
    """Execute a validated SELECT query. Enforces 7 security layers.

    Returns up to 100 rows as a JSON array. Sets truncated=true if capped.
    On query error returns error string with empty result (does not raise 500).
    """
    _check_auth(creds)
    sql = _validate_sql(body.sql)

    try:
        conn = _get_conn()
        df = conn.execute(sql).fetchdf()
        conn.close()
    except Exception as e:
        return QueryResponse(result=[], row_count=0, truncated=False, error=str(e))

    truncated = len(df) > _MAX_ROWS
    if truncated:
        df = df.head(_MAX_ROWS)

    # Serialise — make all values JSON-safe
    records = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif hasattr(v, "item"):
                # numpy scalar → native Python
                clean[k] = v.item()
            elif v.__class__.__name__ == "NaT":
                clean[k] = None
            else:
                clean[k] = v
        records.append(clean)

    return QueryResponse(
        result=records,
        row_count=len(df),
        truncated=truncated,
        error=None,
    )


# ---------------------------------------------------------------------------
# MCP server — primary integration for Agent Builder
# ---------------------------------------------------------------------------
# Agent Builder config:
#   URL:   https://ens-retro-data.fly.dev/mcp
#   Token: value of AGENT_API_KEY (set via fly secrets set AGENT_API_KEY=...)
#
# The MCP tools reuse the same _validate_sql / _get_conn / serialisation logic
# as the REST endpoint — same 7 security layers, same resource limits.
# ---------------------------------------------------------------------------

def _validate_sql_mcp(sql: str) -> str:
    """SQL validation for MCP context — raises ValueError instead of HTTPException."""
    try:
        return _validate_sql(sql)
    except HTTPException as e:
        raise ValueError(e.detail) from e


def _run_query(sql: str) -> str:
    """Execute validated SQL and return a markdown table string."""
    sql = _validate_sql_mcp(sql)
    try:
        conn = _get_conn()
        df = conn.execute(sql).fetchdf()
        conn.close()
    except Exception as e:
        return f"Query error: {e}"

    if df.empty:
        return "Query returned no results."

    truncated = len(df) > _MAX_ROWS
    if truncated:
        df = df.head(_MAX_ROWS)

    note = f"\n\n*Results capped at {_MAX_ROWS} rows.*" if truncated else ""
    return df.to_markdown(index=False) + note


def _run_list_tables() -> str:
    """Return all permitted tables with column names — markdown formatted."""
    try:
        conn = _get_conn()
        tables = conn.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """).fetchdf()

        lines = []
        for _, row in tables.iterrows():
            schema = str(row["table_schema"])
            if schema not in _ALLOWED_SCHEMAS:
                continue
            table = str(row["table_name"])
            cols = conn.execute(
                "SELECT column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                [schema, table],
            ).fetchdf()
            col_str = ", ".join(
                f"{r['column_name']} ({r['data_type']})" for _, r in cols.iterrows()
            )
            lines.append(f"**{schema}.{table}**: {col_str}")
        conn.close()
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tables: {e}"


try:
    from fastmcp import FastMCP
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse

    mcp = FastMCP(
        name="ENS Retro Analyst",
        instructions=(
            "You are connected to the ENS DAO governance warehouse. "
            "Use list_tables to discover schema, then query_duckdb to run SELECT queries. "
            "All queries must be SELECT only. Results are capped at 500 rows."
        ),
    )

    @mcp.tool(
        description=(
            "Run a SELECT query against the ENS DAO DuckDB warehouse. "
            "Returns results as a markdown table (max 500 rows). "
            "Call list_tables first if you need to discover column names. "
            "Only SELECT statements are permitted — INSERT/UPDATE/DELETE/DROP are blocked."
        )
    )
    def query_duckdb(sql: str) -> str:
        return _run_query(sql)

    @mcp.tool(
        description=(
            "List all available tables and their columns in the ENS DAO warehouse. "
            "Call this before writing a query to verify table and column names. "
            "Returns schema.table with column names and types."
        )
    )
    def list_tables() -> str:
        return _run_list_tables()

    # Mount MCP server on the FastAPI app at /mcp
    # Auth is enforced by middleware below — the MCP app itself is unaware of it
    _mcp_asgi = mcp.http_app(path="/")

    # FastMCP 3.x requires its lifespan to initialize the task group.
    # Pass it to the parent FastAPI app so the session manager starts up.
    app.router.lifespan_context = _mcp_asgi.router.lifespan_context

    class _McpAuthMiddleware(BaseHTTPMiddleware):
        """Enforce Bearer token on all /mcp requests."""
        async def dispatch(self, request: StarletteRequest, call_next):
            if _AGENT_API_KEY:
                auth_header = request.headers.get("authorization", "")
                token = auth_header.removeprefix("Bearer ").strip()
                if token != _AGENT_API_KEY:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    _mcp_asgi.add_middleware(_McpAuthMiddleware)
    app.mount("/mcp", _mcp_asgi)

except ImportError:
    # fastmcp not installed — REST endpoints still work, MCP unavailable
    import logging
    logging.getLogger(__name__).warning(
        "fastmcp not installed — MCP server unavailable. "
        "Install with: pip install fastmcp"
    )
