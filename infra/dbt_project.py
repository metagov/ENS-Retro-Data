"""dagster-dbt project configuration and asset key translator."""

from pathlib import Path

from dagster import AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtProject

PROJECT_DIR = Path(__file__).resolve().parent / "dbt"

dbt_project = DbtProject(project_dir=PROJECT_DIR)
dbt_project.prepare_if_dev()


# Map dbt source names to the Dagster bronze asset keys that produce the files
_SOURCE_TO_ASSET_KEY = {
    ("bronze_governance", "snapshot_proposals"): AssetKey("snapshot_proposals"),
    ("bronze_governance", "snapshot_votes"): AssetKey("snapshot_votes"),
    ("bronze_governance", "tally_proposals"): AssetKey("tally_proposals"),
    ("bronze_governance", "tally_votes"): AssetKey("tally_votes"),
    ("bronze_governance", "tally_delegates"): AssetKey("tally_delegates"),
    ("bronze_governance", "votingpower_delegates"): AssetKey("votingpower_delegates"),
    ("bronze_onchain", "delegations"): AssetKey("delegations"),
    ("bronze_onchain", "token_distribution"): AssetKey("token_distribution"),
    ("bronze_onchain", "treasury_flows"): AssetKey("treasury_flows"),
    ("bronze_financial", "compensation"): AssetKey("compensation"),
    ("bronze_grants", "grants"): AssetKey("grants"),
    ("bronze_interviews", "delegate_profiles"): AssetKey("delegate_profiles"),
    ("bronze_forum", "forum_posts"): AssetKey("forum_posts"),
}


class EnsDbtTranslator(DagsterDbtTranslator):
    """Maps dbt sources to upstream Dagster bronze asset keys."""

    def get_asset_key(self, dbt_resource_props: dict) -> AssetKey:
        resource_type = dbt_resource_props.get("resource_type")
        if resource_type == "source":
            source_name = dbt_resource_props.get("source_name", "")
            table_name = dbt_resource_props.get("name", "")
            key = _SOURCE_TO_ASSET_KEY.get((source_name, table_name))
            if key:
                return key
        return super().get_asset_key(dbt_resource_props)
