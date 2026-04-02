"""Central Dagster Definitions — bronze ingest + dbt silver/gold transforms + validation."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dagster import Definitions, load_asset_checks_from_modules, load_assets_from_modules
from dagster_dbt import DbtCliResource

from infra.dbt_assets import ens_dbt_assets
from infra.dbt_project import dbt_project
from infra.ingest import assets as ingest_assets
from infra.resources import EtherscanApiConfig, OsoApiConfig
from infra.validate import checks as check_modules

bronze_assets = load_assets_from_modules([ingest_assets])
asset_checks = load_asset_checks_from_modules([check_modules])

defs = Definitions(
    assets=[*bronze_assets, ens_dbt_assets],
    asset_checks=[*asset_checks],
    resources={
        "dbt": DbtCliResource(project_dir=os.fspath(dbt_project.project_dir)),
        "etherscan_config": EtherscanApiConfig(api_key=os.environ.get("ETHERSCAN_API_KEY", "")),
        "oso_config": OsoApiConfig(api_key=os.environ.get("OSO_API_KEY", "")),
    },
)
