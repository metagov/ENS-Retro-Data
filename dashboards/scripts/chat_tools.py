"""DuckDB query tools for the ChatKit agent.

Provides read-only SQL access to the ENS DAO warehouse.
These functions are called by the ChatKit agent backend (via the session
context) to answer data questions from the chat widget.
"""

from pathlib import Path

import duckdb

_DB_PATH = Path(__file__).parent.parent.parent / "warehouse" / "ens_retro.duckdb"

_BLOCKED = ("insert", "update", "delete", "drop", "create", "alter", "truncate", "replace")


def _get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(_DB_PATH), read_only=True)


def query_duckdb(sql: str) -> str:
    """Run a read-only SQL SELECT query against the ENS DAO warehouse.

    Returns results as a markdown table (max 50 rows).
    Returns an error string if the query fails or is unsafe.
    """
    sql_lower = sql.strip().lower()
    for blocked in _BLOCKED:
        if sql_lower.startswith(blocked) or f" {blocked} " in sql_lower:
            return f"Error: {blocked.upper()} statements are not allowed. Only SELECT queries are permitted."

    try:
        conn = _get_conn()
        rel = conn.execute(sql)
        df = rel.fetchdf()
        if df.empty:
            return "Query returned no results."
        if len(df) > 50:
            df = df.head(50)
            note = f"\n\n*Results truncated to 50 rows.*"
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
            schema = row["table_schema"]
            table = row["table_name"]
            cols = conn.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
            """).fetchdf()
            col_str = ", ".join(
                f"{r['column_name']} ({r['data_type']})" for _, r in cols.iterrows()
            )
            lines.append(f"**{schema}.{table}**: {col_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tables: {e}"
