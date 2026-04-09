"""Tests for infra/taxonomy.py — load and validate against taxonomy.yaml."""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from infra.taxonomy import load_taxonomy, validate_column, valid_values


class TestLoadTaxonomy:
    def test_returns_dict(self):
        tax = load_taxonomy()
        assert isinstance(tax, dict)

    def test_contains_expected_top_level_fields(self):
        tax = load_taxonomy()
        for field in [
            "sources",
            "governance_categories",
            "proposal_status",
            "vote_choices",
            "stakeholder_roles",
            "working_groups",
            "evaluation_dimensions",
            "entity_types",
            "data_layers",
            "bronze_domains",
        ]:
            assert field in tax, f"missing taxonomy field: {field}"

    def test_caches_across_calls(self):
        a = load_taxonomy()
        b = load_taxonomy()
        # Same object — proves the module-level cache is used
        assert a is b


class TestValidValues:
    def test_returns_list(self):
        v = valid_values("vote_choices")
        assert isinstance(v, list)

    def test_vote_choices_content(self):
        choices = valid_values("vote_choices")
        assert "for" in choices
        assert "against" in choices
        assert "abstain" in choices

    def test_unknown_field_raises_keyerror(self):
        with pytest.raises(KeyError) as exc_info:
            valid_values("not_a_real_taxonomy_field")
        assert "not_a_real_taxonomy_field" in str(exc_info.value)

    def test_working_groups_match_yaml(self):
        groups = valid_values("working_groups")
        assert "meta-governance" in groups
        assert "ens-ecosystem" in groups
        assert "public-goods" in groups
        assert "providers" in groups


class TestValidateColumn:
    def test_pandas_all_valid(self):
        s = pd.Series(["for", "against", "abstain", None, "for"])
        invalid = validate_column(s, "vote_choices")
        assert invalid == []

    def test_pandas_some_invalid(self):
        s = pd.Series(["for", "yes", "no", "abstain"])
        invalid = validate_column(s, "vote_choices")
        assert sorted(invalid) == ["no", "yes"]

    def test_pandas_all_null(self):
        s = pd.Series([None, None, None])
        invalid = validate_column(s, "vote_choices")
        assert invalid == []

    def test_polars_all_valid(self):
        s = pl.Series(["for", "against", "abstain"])
        invalid = validate_column(s, "vote_choices")
        assert invalid == []

    def test_polars_some_invalid(self):
        s = pl.Series(["for", "MAYBE", "against"])
        invalid = validate_column(s, "vote_choices")
        assert invalid == ["MAYBE"]

    def test_unknown_field_raises_keyerror(self):
        s = pd.Series(["a", "b"])
        with pytest.raises(KeyError):
            validate_column(s, "not_a_field")
