"""Dagster resources for API credentials and external services."""

from dagster import ConfigurableResource


class EtherscanApiConfig(ConfigurableResource):
    """Etherscan API configuration, typically sourced from ETHERSCAN_API_KEY env var."""

    api_key: str
