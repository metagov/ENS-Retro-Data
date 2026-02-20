"""Utility to load and validate against taxonomy.yaml."""

from pathlib import Path

import yaml

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "taxonomy.yaml"

_cache: dict | None = None


def load_taxonomy() -> dict:
    """Load taxonomy.yaml and cache it for the process lifetime."""
    global _cache
    if _cache is None:
        with open(TAXONOMY_PATH) as f:
            _cache = yaml.safe_load(f)
    return _cache


def valid_values(field: str) -> list[str]:
    """Return the allowed values for a taxonomy field."""
    tax = load_taxonomy()
    if field not in tax:
        raise KeyError(f"Unknown taxonomy field: {field}")
    return tax[field]


def validate_column(series, field: str) -> list[str]:
    """Check that every non-null value in *series* is in the taxonomy.

    Returns a list of invalid values (empty means all valid).
    Works with both pandas Series and polars Series.
    """
    allowed = set(valid_values(field))
    # Convert to plain Python set of unique values
    try:
        # pandas
        unique_vals = set(series.dropna().unique())
    except AttributeError:
        # polars
        unique_vals = set(series.drop_nulls().unique().to_list())
    return sorted(unique_vals - allowed)
