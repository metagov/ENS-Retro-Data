from pathlib import Path

import duckdb
import streamlit as st

_DB_PATH = Path(__file__).parent.parent.parent / "warehouse" / "ens_retro.duckdb"


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(_DB_PATH), read_only=True)
