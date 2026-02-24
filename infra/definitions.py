"""Central Dagster Definitions — bronze assets, dbt assets, checks, and resources."""

from dagster import Definitions, EnvVar, load_assets_from_modules
from dagster_dbt import DbtCliResource

from infra.dbt_assets import ens_dbt_assets
from infra.dbt_project import dbt_project
from infra.ingest import assets as ingest_assets
from infra.resources import TallyApiConfig
from infra.validate.checks import (
    check_ge_snapshot_proposals,
    check_ge_snapshot_votes,
    check_ge_tally_delegates,
    check_ge_tally_proposals,
    check_ge_tally_votes,
    check_snapshot_proposals_count,
    check_snapshot_votes_count,
    check_tally_delegates_count,
    check_tally_proposals_count,
    check_tally_votes_count,
)

bronze_assets = load_assets_from_modules([ingest_assets])

all_checks = [
    # Bronze row counts
    check_snapshot_proposals_count,
    check_snapshot_votes_count,
    check_tally_proposals_count,
    check_tally_votes_count,
    check_tally_delegates_count,
    # Bronze Great Expectations suites
    check_ge_snapshot_proposals,
    check_ge_snapshot_votes,
    check_ge_tally_proposals,
    check_ge_tally_votes,
    check_ge_tally_delegates,
]

defs = Definitions(
    assets=[*bronze_assets, ens_dbt_assets],
    asset_checks=all_checks,
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project.project_dir),
        "tally_config": TallyApiConfig(api_key=EnvVar("TALLY_API_KEY")),
    },
)
