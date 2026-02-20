"""Custom IO managers for the medallion architecture.

ParquetIOManager: reads/writes Parquet files keyed by asset name.
JsonIOManager:    reads/writes JSON files keyed by asset name.
"""

import json
from pathlib import Path

import pandas as pd
from dagster import ConfigurableIOManager, InputContext, OutputContext


class ParquetIOManager(ConfigurableIOManager):
    """Persist DataFrames as Parquet files under a base directory.

    The file path is derived from the asset key:
        base_dir / key_part_0 / key_part_1 / ... .parquet
    """

    base_dir: str = "."

    def _path_for(self, context) -> Path:
        parts = context.asset_key.path
        return Path(self.base_dir).joinpath(*parts[:-1], f"{parts[-1]}.parquet")

    def handle_output(self, context: OutputContext, obj):
        path = self._path_for(context)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(obj, pd.DataFrame):
            obj.to_parquet(path, index=False)
        else:
            # Assume polars
            obj.write_parquet(path)
        context.log.info(f"Wrote {path} ({path.stat().st_size:,} bytes)")

    def load_input(self, context: InputContext):
        path = self._path_for(context)
        return pd.read_parquet(path)


class JsonIOManager(ConfigurableIOManager):
    """Read/write plain Python objects as JSON files.

    Used for the bronze layer where raw data arrives as JSON.
    """

    base_dir: str = "."

    def _path_for(self, context) -> Path:
        parts = context.asset_key.path
        return Path(self.base_dir).joinpath(*parts[:-1], f"{parts[-1]}.json")

    def handle_output(self, context: OutputContext, obj):
        path = self._path_for(context)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f, indent=2, default=str)
        context.log.info(f"Wrote {path}")

    def load_input(self, context: InputContext):
        path = self._path_for(context)
        with open(path) as f:
            return json.load(f)
