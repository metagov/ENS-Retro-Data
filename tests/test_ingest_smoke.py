"""Smoke tests for every infra/ingest/*_api.py module.

These tests do nothing more than import each module and verify the public
function names exist with the expected signatures. They catch:

- Syntax errors in any ingest module
- Renamed/removed public functions
- Broken imports (missing dependencies)
- Module-level side effects that crash on import

If a test here fails, it usually means a refactor broke a public API
that downstream code (Dagster assets, dbt translator, scripts) depends on.
"""

from __future__ import annotations

import inspect


class TestImportSmoke:
    def test_snapshot_api_imports(self):
        from infra.ingest import snapshot_api
        assert callable(snapshot_api.run_query)
        assert callable(snapshot_api.fetch_snapshot_proposals)
        assert callable(snapshot_api.fetch_snapshot_votes)

    def test_tally_api_imports(self):
        from infra.ingest import tally_api
        # Frozen but flatteners are still public
        assert callable(tally_api.flatten_tally_proposals)
        assert callable(tally_api.flatten_tally_votes)
        assert callable(tally_api.flatten_tally_delegates)

    def test_etherscan_api_imports(self):
        from infra.ingest import etherscan_api
        assert callable(etherscan_api.fetch_delegation_events)
        assert callable(etherscan_api.fetch_token_transfers)
        assert callable(etherscan_api.fetch_treasury_transactions)

    def test_safe_api_imports(self):
        from infra.ingest import safe_api
        assert callable(safe_api.fetch_all_balances)
        assert callable(safe_api.fetch_all_safe_transactions)

    def test_smallgrants_api_imports(self):
        from infra.ingest import smallgrants_api
        assert callable(smallgrants_api.fetch_smallgrants_proposals)
        assert callable(smallgrants_api.fetch_smallgrants_votes)

    def test_discourse_api_imports(self):
        from infra.ingest import discourse_api
        assert callable(discourse_api.fetch_all_topics)
        assert callable(discourse_api.fetch_topic_posts)
        assert callable(discourse_api.fetch_forum_data)

    def test_oso_api_imports(self):
        from infra.ingest import oso_api
        assert callable(oso_api.fetch_ens_repos)
        assert callable(oso_api.fetch_ens_code_metrics)
        assert callable(oso_api.fetch_ens_timeseries)

    def test_assets_module_imports(self):
        """Importing assets.py loads ALL @asset definitions; catches Dagster wiring breakage."""
        from infra.ingest import assets
        # Helper functions
        assert callable(assets._update_metadata)
        assert callable(assets._write_json)
        assert callable(assets._check_file_exists)


class TestIngestFunctionSignatures:
    """Pin the public signatures so accidental refactors are caught."""

    def test_fetch_delegation_events_takes_api_key(self):
        from infra.ingest.etherscan_api import fetch_delegation_events
        sig = inspect.signature(fetch_delegation_events)
        assert "api_key" in sig.parameters

    def test_fetch_token_transfers_takes_api_key(self):
        from infra.ingest.etherscan_api import fetch_token_transfers
        sig = inspect.signature(fetch_token_transfers)
        assert "api_key" in sig.parameters

    def test_fetch_ens_repos_takes_api_key(self):
        from infra.ingest.oso_api import fetch_ens_repos
        sig = inspect.signature(fetch_ens_repos)
        assert "api_key" in sig.parameters

    def test_fetch_snapshot_votes_takes_proposals_list(self):
        from infra.ingest.snapshot_api import fetch_snapshot_votes
        sig = inspect.signature(fetch_snapshot_votes)
        assert "proposals" in sig.parameters


class TestInfraTopLevelImports:
    """Make sure every public infra module imports cleanly."""

    def test_definitions(self):
        # The Dagster entry point — if this breaks, nothing materializes
        from infra import definitions  # noqa: F401

    def test_dbt_project(self):
        from infra import dbt_project
        assert dbt_project.dbt_project is not None

    def test_dbt_assets(self):
        from infra import dbt_assets
        assert callable(dbt_assets.ens_dbt_assets)

    def test_resources(self):
        from infra.resources import EtherscanApiConfig, OsoApiConfig
        assert EtherscanApiConfig is not None
        assert OsoApiConfig is not None

    def test_validate_checks(self):
        from infra.validate import checks
        assert callable(checks._count_json_records)
        assert callable(checks._load_bronze_df)
        assert callable(checks._run_ge_suite)

    def test_taxonomy(self):
        from infra.taxonomy import load_taxonomy, valid_values, validate_column
        assert callable(load_taxonomy)
        assert callable(valid_values)
        assert callable(validate_column)

    def test_sensors(self):
        from infra import sensors
        assert sensors.vector_store_sync_sensor is not None
