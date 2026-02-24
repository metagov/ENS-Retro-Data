"""Dagster assets generated from dbt models (staging, silver, gold)."""

from dagster_dbt import DbtCliResource, dbt_assets

from infra.dbt_project import EnsDbtTranslator, dbt_project


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=EnsDbtTranslator(),
)
def ens_dbt_assets(context, dbt: DbtCliResource):
    """Run dbt build for all staging, silver, and gold models."""
    # Ensure warehouse directory exists for DuckDB
    (dbt_project.project_dir.parent.parent / "warehouse").mkdir(exist_ok=True)
    yield from dbt.cli(["build"], context=context).stream()
