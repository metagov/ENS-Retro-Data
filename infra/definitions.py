"""Central Dagster Definitions — bronze ingest assets only.

dbt transforms (silver/gold) will be re-enabled once bronze data is populated.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dagster import Definitions, load_assets_from_modules

from infra.ingest import assets as ingest_assets
from infra.resources import EtherscanApiConfig, TallyApiConfig

bronze_assets = load_assets_from_modules([ingest_assets])

defs = Definitions(
    assets=[*bronze_assets],
    resources={
        "tally_config": TallyApiConfig(api_key=os.environ.get("TALLY_API_KEY", "")),
        "etherscan_config": EtherscanApiConfig(api_key=os.environ.get("ETHERSCAN_API_KEY", "")),
    },
)
