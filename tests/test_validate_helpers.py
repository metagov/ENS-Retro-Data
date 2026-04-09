"""Tests for infra/validate/checks.py helper functions.

The full asset checks can't be unit-tested without a Dagster context, but
the helpers (_count_json_records, _load_bronze_df) are pure file-system
utilities that we can verify with a tmp_bronze fixture.
"""

from __future__ import annotations

import pandas as pd

from infra.validate import checks as checks_mod


class TestCountJsonRecords:
    def test_missing_file_returns_zero(self, tmp_bronze):
        assert checks_mod._count_json_records("nonexistent", "missing.json") == 0

    def test_list_returns_length(self, write_bronze_json):
        write_bronze_json("governance", "items.json", [{"a": 1}, {"a": 2}, {"a": 3}])
        assert checks_mod._count_json_records("governance", "items.json") == 3

    def test_empty_list_returns_zero(self, write_bronze_json):
        write_bronze_json("governance", "empty.json", [])
        assert checks_mod._count_json_records("governance", "empty.json") == 0

    def test_dict_returns_one(self, write_bronze_json):
        write_bronze_json("governance", "single.json", {"a": 1, "b": 2})
        assert checks_mod._count_json_records("governance", "single.json") == 1


class TestLoadBronzeDf:
    def test_missing_file_returns_none(self, tmp_bronze):
        assert checks_mod._load_bronze_df("nonexistent", "missing.json") is None

    def test_empty_list_returns_none(self, write_bronze_json):
        write_bronze_json("governance", "empty.json", [])
        assert checks_mod._load_bronze_df("governance", "empty.json") is None

    def test_list_of_dicts_returns_dataframe(self, write_bronze_json):
        write_bronze_json("governance", "items.json", [
            {"id": "a", "value": 1},
            {"id": "b", "value": 2},
        ])
        df = checks_mod._load_bronze_df("governance", "items.json")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["id", "value"]
        assert df.iloc[0]["id"] == "a"

    def test_single_dict_returns_none(self, write_bronze_json):
        # _load_bronze_df expects a list — single dicts are not loaded
        write_bronze_json("governance", "single.json", {"id": "a"})
        assert checks_mod._load_bronze_df("governance", "single.json") is None
