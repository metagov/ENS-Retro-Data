"""Central Dagster Definitions — bronze ingest assets + validation checks.

dbt transforms (silver/gold) will be re-enabled once bronze data is populated.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dagster import Definitions, load_asset_checks_from_modules, load_assets_from_modules

from infra.ingest import assets as ingest_assets
from infra.resources import EtherscanApiConfig, OsoApiConfig, TallyApiConfig
from infra.validate import checks as check_modules

bronze_assets = load_assets_from_modules([ingest_assets])
asset_checks = load_asset_checks_from_modules([check_modules])

defs = Definitions(
    assets=[*bronze_assets],
    asset_checks=[*asset_checks],
    resources={
        "tally_config": TallyApiConfig(api_key=os.environ.get("TALLY_API_KEY", "")),
        "etherscan_config": EtherscanApiConfig(api_key=os.environ.get("ETHERSCAN_API_KEY", "")),
        "oso_config": OsoApiConfig(api_key=os.environ.get("OSO_API_KEY", "")),
    },
)
