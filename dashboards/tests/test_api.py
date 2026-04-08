"""Tests for dashboards/api.py — SQL validation, auth, query execution, serialisation."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Ensure dashboards package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# SQL validation (unit tests — no DB needed)
# ---------------------------------------------------------------------------

class TestValidateSQL:
    """Test _validate_sql() in isolation."""

    @pytest.fixture(autouse=True)
    def _import_validate(self, _reset_ast_cache):
        from api import _validate_sql
        self.validate = _validate_sql

    # -- Valid queries --

    def test_simple_select(self):
        result = self.validate("SELECT 1")
        assert result == "SELECT 1"

    def test_select_from_allowed_schema(self):
        result = self.validate("SELECT * FROM main_gold.proposals")
        assert "proposals" in result

    def test_select_with_cte(self):
        sql = "WITH cte AS (SELECT 1 AS x) SELECT * FROM cte"
        result = self.validate(sql)
        assert "cte" in result

    def test_whitespace_stripped(self):
        result = self.validate("  SELECT 1  ")
        assert result == "SELECT 1"

    # -- Rejected: empty / too long --

    def test_empty_query(self):
        with pytest.raises(HTTPException) as exc_info:
            self.validate("")
        assert exc_info.value.status_code == 400
        assert "Empty" in exc_info.value.detail

    def test_whitespace_only(self):
        with pytest.raises(HTTPException) as exc_info:
            self.validate("   ")
        assert exc_info.value.status_code == 400

    def test_exceeds_length_limit(self):
        sql = "SELECT " + "x" * 4_001
        with pytest.raises(HTTPException) as exc_info:
            self.validate(sql)
        assert exc_info.value.status_code == 400
        assert "4000" in exc_info.value.detail

    # -- Rejected: DML / DDL --

    @pytest.mark.parametrize("sql", [
        "INSERT INTO main_gold.proposals VALUES (1)",
        "UPDATE main_gold.proposals SET id = 1",
        "DELETE FROM main_gold.proposals",
        "DROP TABLE main_gold.proposals",
        "CREATE TABLE main_gold.test (id INT)",
    ])
    def test_dml_ddl_rejected(self, sql):
        with pytest.raises(HTTPException) as exc_info:
            self.validate(sql)
        assert exc_info.value.status_code == 400

    def test_multi_statement_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            self.validate("SELECT 1; DROP TABLE main_gold.proposals")
        assert exc_info.value.status_code == 400

    # -- Rejected: disallowed schema --

    def test_disallowed_schema(self):
        with pytest.raises(HTTPException) as exc_info:
            self.validate("SELECT * FROM pg_catalog.pg_tables")
        assert exc_info.value.status_code == 400
        assert "not permitted" in exc_info.value.detail

    def test_information_schema_blocked(self):
        with pytest.raises(HTTPException) as exc_info:
            self.validate("SELECT * FROM information_schema.tables")
        assert exc_info.value.status_code == 400

    # -- Rejected: sqlglot parse failure → reject (not fallback) --

    def test_sqlglot_parse_failure_rejects(self):
        """If sqlglot can't parse it, the query is rejected (no regex fallback)."""
        with patch("sqlglot.parse", side_effect=RuntimeError("parse boom")):
            with pytest.raises(HTTPException) as exc_info:
                self.validate("SELECT 1")
            assert exc_info.value.status_code == 400
            assert "could not be validated" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Auth (unit tests)
# ---------------------------------------------------------------------------

class TestCheckAuth:

    def test_dev_mode_no_key_set(self):
        """When AGENT_API_KEY is empty, all requests are allowed."""
        from api import _check_auth
        with patch("api._AGENT_API_KEY", ""):
            _check_auth(None)  # should not raise

    def test_valid_bearer_token(self):
        from api import _check_auth
        creds = MagicMock()
        creds.credentials = "test-key-123"
        with patch("api._AGENT_API_KEY", "test-key-123"):
            _check_auth(creds)  # should not raise

    def test_missing_bearer_token(self):
        from api import _check_auth
        with patch("api._AGENT_API_KEY", "test-key-123"):
            with pytest.raises(HTTPException) as exc_info:
                _check_auth(None)
            assert exc_info.value.status_code == 401

    def test_wrong_bearer_token(self):
        from api import _check_auth
        creds = MagicMock()
        creds.credentials = "wrong-key"
        with patch("api._AGENT_API_KEY", "test-key-123"):
            with pytest.raises(HTTPException) as exc_info:
                _check_auth(creds)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# REST endpoint integration tests (using FastAPI TestClient + in-memory DuckDB)
# ---------------------------------------------------------------------------

@pytest.fixture()
def _reset_ast_cache():
    """Reset the cached _BLOCKED_AST_TYPES so sqlglot attribute names are re-resolved."""
    import api
    api._BLOCKED_AST_TYPES = ()
    yield
    api._BLOCKED_AST_TYPES = ()


@pytest.fixture()
def client(_reset_ast_cache, tmp_path):
    """TestClient with auth disabled and DuckDB pointed at a temp DB."""
    import duckdb
    from fastapi.testclient import TestClient

    db_path = str(tmp_path / "test.duckdb")
    # Seed the test database
    setup_conn = duckdb.connect(db_path)
    setup_conn.execute("CREATE SCHEMA IF NOT EXISTS main_gold")
    setup_conn.execute(
        "CREATE TABLE main_gold.proposals (id INTEGER, title VARCHAR, created_at TIMESTAMP)"
    )
    setup_conn.execute(
        "INSERT INTO main_gold.proposals VALUES (1, 'Test Proposal', '2026-01-01 00:00:00')"
    )
    setup_conn.close()

    def mock_get_conn():
        return duckdb.connect(db_path, read_only=True)

    with patch("api._AGENT_API_KEY", ""), \
         patch("api._get_conn", mock_get_conn):
        from api import app
        yield TestClient(app, raise_server_exceptions=False)


class TestAgentQueryEndpoint:

    def test_valid_select(self, client):
        resp = client.post("/api/agent-query", json={"sql": "SELECT * FROM main_gold.proposals"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["row_count"] == 1
        assert data["truncated"] is False
        assert data["error"] is None
        assert data["result"][0]["title"] == "Test Proposal"

    def test_insert_rejected(self, client):
        resp = client.post(
            "/api/agent-query",
            json={"sql": "INSERT INTO main_gold.proposals VALUES (2, 'X', '2026-01-01')"},
        )
        assert resp.status_code == 400

    def test_empty_query_rejected(self, client):
        resp = client.post("/api/agent-query", json={"sql": ""})
        assert resp.status_code == 400

    def test_truncation(self, tmp_path, _reset_ast_cache):
        """Results exceeding _MAX_ROWS are truncated."""
        import duckdb
        from fastapi.testclient import TestClient

        db_path = str(tmp_path / "big.duckdb")
        setup = duckdb.connect(db_path)
        setup.execute("CREATE SCHEMA IF NOT EXISTS main_gold")
        setup.execute("CREATE TABLE main_gold.big (id INTEGER)")
        setup.execute("INSERT INTO main_gold.big SELECT * FROM generate_series(1, 600)")
        setup.close()

        def mock_get_conn():
            return duckdb.connect(db_path, read_only=True)

        with patch("api._AGENT_API_KEY", ""), \
             patch("api._get_conn", mock_get_conn):
            from api import app
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.post("/api/agent-query", json={"sql": "SELECT * FROM main_gold.big"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is True
        assert data["row_count"] == 500


class TestTablesEndpoint:

    def test_returns_tables(self, client):
        resp = client.get("/api/tables")
        assert resp.status_code == 200
        tables = resp.json()["tables"]
        names = [t["table"] for t in tables]
        assert "proposals" in names

    def test_columns_included(self, client):
        resp = client.get("/api/tables")
        tables = resp.json()["tables"]
        proposals = [t for t in tables if t["table"] == "proposals"][0]
        col_names = [c["name"] for c in proposals["columns"]]
        assert "id" in col_names
        assert "title" in col_names


class TestAuthEndpoint:

    def test_auth_required_when_key_set(self):
        """When AGENT_API_KEY is set, requests without a bearer token get 401."""
        from fastapi.testclient import TestClient
        with patch("api._AGENT_API_KEY", "secret-key"):
            from api import app
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get("/api/tables")
            assert resp.status_code == 401

    def test_auth_passes_with_correct_key(self, tmp_path):
        """Correct bearer token is accepted."""
        import duckdb
        from fastapi.testclient import TestClient

        db_path = str(tmp_path / "auth.duckdb")
        setup = duckdb.connect(db_path)
        setup.close()

        def mock_get_conn():
            return duckdb.connect(db_path, read_only=True)

        with patch("api._AGENT_API_KEY", "secret-key"), \
             patch("api._get_conn", mock_get_conn):
            from api import app
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get(
                "/api/tables",
                headers={"Authorization": "Bearer secret-key"},
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialisation:

    def test_datetime_serialised(self, client):
        resp = client.post(
            "/api/agent-query",
            json={"sql": "SELECT created_at FROM main_gold.proposals"},
        )
        assert resp.status_code == 200
        val = resp.json()["result"][0]["created_at"]
        # Should be an ISO string, not a raw datetime object
        assert isinstance(val, str)
        assert "2026" in val

    def test_numpy_scalar_serialised(self, client):
        resp = client.post(
            "/api/agent-query",
            json={"sql": "SELECT COUNT(*) AS cnt FROM main_gold.proposals"},
        )
        assert resp.status_code == 200
        val = resp.json()["result"][0]["cnt"]
        assert isinstance(val, (int, float))


# ---------------------------------------------------------------------------
# MCP validation wrapper
# ---------------------------------------------------------------------------

class TestValidateSqlMcp:

    def test_raises_value_error(self):
        from api import _validate_sql_mcp
        with pytest.raises(ValueError, match="Empty"):
            _validate_sql_mcp("")

    def test_valid_passes_through(self):
        from api import _validate_sql_mcp
        result = _validate_sql_mcp("SELECT 1")
        assert result == "SELECT 1"


# ---------------------------------------------------------------------------
# chat_session / chat_widget (unit tests)
# ---------------------------------------------------------------------------

class TestChatSessionIsConfigured:

    def test_configured_when_both_set(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "WORKFLOW_ID": "wf-123"}):
            # Need to reload since module reads env at import
            from scripts import chat_session
            from importlib import reload
            reload(chat_session)
            assert chat_session.is_configured() is True

    def test_not_configured_when_key_missing(self):
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("WORKFLOW_ID", None)
        with patch.dict(os.environ, env, clear=True):
            from scripts import chat_session
            from importlib import reload
            reload(chat_session)
            # After reload, WORKFLOW_ID is re-read from env (now empty)
            # Also patch the module-level variable to ensure it's empty
            with patch.object(chat_session, "WORKFLOW_ID", ""):
                assert chat_session.is_configured() is False


class TestGetCachedSecret:

    def test_caches_within_ttl(self):
        """Secret is reused within the TTL window."""
        import time
        from scripts.chat_widget import _get_cached_secret

        mock_st = MagicMock()
        mock_st.session_state = {
            "_chatkit_secret": "ek_cached",
            "_chatkit_secret_ts": time.monotonic(),  # fresh
        }

        with patch("scripts.chat_widget.st", mock_st), \
             patch("scripts.chat_widget.is_configured", return_value=True):
            result = _get_cached_secret()
            assert result == "ek_cached"

    def test_refreshes_after_ttl(self):
        """Secret is re-minted when TTL expires."""
        import time
        from scripts.chat_widget import _get_cached_secret

        mock_st = MagicMock()
        mock_st.session_state = {
            "_chatkit_secret": "ek_stale",
            "_chatkit_secret_ts": time.monotonic() - 3600,  # expired (TTL is 1800s)
        }

        with patch("scripts.chat_widget.st", mock_st), \
             patch("scripts.chat_widget.create_chatkit_session", return_value="ek_new"):
            result = _get_cached_secret()
            assert result == "ek_new"
