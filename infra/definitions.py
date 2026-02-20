"""Central Dagster Definitions — all assets, checks, and resources."""

from dagster import Definitions, load_assets_from_modules

from infra.ingest import assets as ingest_assets
from infra.io_managers import JsonIOManager, ParquetIOManager
from infra.materialize import assets as materialize_assets
from infra.transform import assets as transform_assets
from infra.validate.checks import (
    check_governance_activity_complete,
    check_snapshot_proposal_status,
    check_snapshot_proposals_count,
    check_snapshot_votes_count,
    check_tally_delegates_count,
    check_tally_proposal_status,
    check_tally_proposals_count,
    check_tally_votes_count,
)

bronze_assets = load_assets_from_modules([ingest_assets])
silver_assets = load_assets_from_modules([transform_assets])
gold_assets = load_assets_from_modules([materialize_assets])

all_checks = [
    # Bronze row counts
    check_snapshot_proposals_count,
    check_snapshot_votes_count,
    check_tally_proposals_count,
    check_tally_votes_count,
    check_tally_delegates_count,
    # Silver taxonomy
    check_snapshot_proposal_status,
    check_tally_proposal_status,
    # Gold completeness
    check_governance_activity_complete,
]

defs = Definitions(
    assets=[*bronze_assets, *silver_assets, *gold_assets],
    asset_checks=all_checks,
    resources={
        "io_manager": ParquetIOManager(base_dir="silver"),
        "json_io_manager": JsonIOManager(base_dir="bronze"),
    },
)
