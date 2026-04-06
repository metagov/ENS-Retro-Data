"""DuckDB query tools for the ChatKit agent.

Provides read-only SQL access to the ENS DAO warehouse.
These functions are called by the ChatKit agent backend (via the session
context) to answer data questions from the chat widget.
"""

import re
from pathlib import Path

import duckdb

_DB_PATH = Path(__file__).parent.parent.parent / "warehouse" / "ens_retro.duckdb"

# Allowlist: only SELECT and WITH (CTEs) are permitted entry points.
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# Secondary guard: catch dangerous keywords anywhere in the query, including
# comment-escaped variants like `sel/**/ect` or stacked statements via semicolons.
_UNSAFE_PATTERNS = re.compile(
    r"(;|--|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\bcreate\b"
    r"|\balter\b|\btruncate\b|\breplace\b|\bcopy\b|\battach\b|\bdetach\b"
    r"|\bpragma\b|\bload\b|\binstall\b)",
    re.IGNORECASE,
)


def _get_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(_DB_PATH), read_only=True)
    # Constrain resource usage per query
    conn.execute("SET threads TO 1")
    conn.execute("SET memory_limit='128MB'")
    return conn


def query_duckdb(sql: str) -> str:
    """Run a read-only SQL SELECT query against the ENS DAO warehouse.

    Returns results as a markdown table (max 50 rows).
    Returns an error string if the query fails or is unsafe.
    """
    if not sql or not sql.strip():
        return "Error: Empty query."

    if not _ALLOWED_START.match(sql):
        return "Error: Only SELECT queries are permitted."

    if _UNSAFE_PATTERNS.search(sql):
        return "Error: Query contains disallowed keywords or syntax."

    try:
        conn = _get_conn()
        rel = conn.execute(sql)
        df = rel.fetchdf()
        if df.empty:
            return "Query returned no results."
        if len(df) > 50:
            df = df.head(50)
            note = "\n\n*Results truncated to 50 rows.*"
        else:
            note = ""
        return df.to_markdown(index=False) + note
    except Exception as e:
        return f"Query error: {e}"


def list_tables() -> str:
    """List all available tables and their columns in the ENS DAO warehouse.

    Use this before writing a query to discover the correct table and column names.
    """
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
            table = str(row["table_name"])
            # Use parameterized query — no f-string interpolation into SQL
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

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tables: {e}"
