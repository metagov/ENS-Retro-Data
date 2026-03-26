"""Dagster resources for API credentials and external services."""

from dagster import ConfigurableResource


class TallyApiConfig(ConfigurableResource):
    """Tally API configuration, typically sourced from TALLY_API_KEY env var."""

    api_key: str


class EtherscanApiConfig(ConfigurableResource):
    """Etherscan API configuration, typically sourced from ETHERSCAN_API_KEY env var."""

    api_key: str


class OsoApiConfig(ConfigurableResource):
    """Open Source Observer API configuration, sourced from OSO_API_KEY env var."""

    api_key: str
