"""Asset checks for bronze data quality validation.

Combines simple row-count checks with Great Expectations suite validations.
Silver/gold checks are handled by dbt tests.
"""

import json
from pathlib import Path

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd
from dagster import AssetCheckResult, AssetCheckSeverity, asset_check

BRONZE_ROOT = Path(__file__).resolve().parent.parent.parent / "bronze"
GE_EXPECTATIONS_DIR = Path(__file__).resolve().parent.parent / "great_expectations" / "expectations"


def _count_json_records(subdir: str, filename: str) -> int:
    """Count records in a bronze JSON file."""
    path = BRONZE_ROOT / subdir / filename
    if not path.exists():
        return 0
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return len(data)
    return 1


def _load_bronze_df(subdir: str, filename: str) -> pd.DataFrame | None:
    """Load a bronze JSON file into a DataFrame for GE validation."""
    path = BRONZE_ROOT / subdir / filename
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) > 0:
        return pd.DataFrame(data)
    return None


# Map expectation type strings from suite JSON to GE 1.x expectation classes
_GXE_MAP = {
    "expect_table_row_count_to_be_between": gxe.ExpectTableRowCountToBeBetween,
    "expect_column_to_exist": gxe.ExpectColumnToExist,
    "expect_column_values_to_not_be_null": gxe.ExpectColumnValuesToNotBeNull,
    "expect_column_values_to_be_unique": gxe.ExpectColumnValuesToBeUnique,
    "expect_column_values_to_be_in_set": gxe.ExpectColumnValuesToBeInSet,
    "expect_column_values_to_match_regex": gxe.ExpectColumnValuesToMatchRegex,
}


def _run_ge_suite(subdir: str, filename: str, suite_name: str) -> AssetCheckResult:
    """Run a Great Expectations suite against a bronze JSON file."""
    suite_path = GE_EXPECTATIONS_DIR / f"{suite_name}.json"
    if not suite_path.exists():
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"GE suite not found: {suite_path}",
        )

    df = _load_bronze_df(subdir, filename)
    if df is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            metadata={"file": f"{subdir}/{filename}"},
            description=f"File not found or empty: {subdir}/{filename}",
        )

    with open(suite_path) as f:
        suite_dict = json.load(f)

    # Build GE context, datasource, and suite
    ctx = gx.get_context()
    ds = ctx.data_sources.add_pandas(f"ds_{suite_name}")
    asset = ds.add_dataframe_asset(f"asset_{suite_name}")
    batch_def = asset.add_batch_definition_whole_dataframe(f"batch_{suite_name}")

    suite = ctx.suites.add(gx.ExpectationSuite(name=suite_name))
    for exp in suite_dict.get("expectations", []):
        exp_type = exp["expectation_type"]
        kwargs = exp.get("kwargs", {})
        exp_class = _GXE_MAP.get(exp_type)
        if exp_class:
            suite.add_expectation(exp_class(**kwargs))

    vd = ctx.validation_definitions.add(
        gx.ValidationDefinition(name=f"vd_{suite_name}", data=batch_def, suite=suite)
    )
    result = vd.run(batch_parameters={"dataframe": df})

    failed = []
    for r in result.results:
        if not r.success:
            failed.append(r.expectation_config.type)

    total = len(result.results)
    passed_count = total - len(failed)
    all_passed = result.success

    return AssetCheckResult(
        passed=all_passed,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "suite": suite_name,
            "expectations_total": total,
            "expectations_passed": passed_count,
            "expectations_failed": len(failed),
            "failed_expectations": failed[:10],
            "rows_validated": len(df),
        },
        description=(
            f"GE: {passed_count}/{total} expectations passed ({len(df)} rows)"
            if all_passed
            else f"GE: {len(failed)} failed — {', '.join(failed[:3])}"
        ),
    )


# ---------------------------------------------------------------------------
# Bronze — row count checks (fast, always run)
# ---------------------------------------------------------------------------


@asset_check(asset="snapshot_proposals", description="Snapshot proposals row count")
def check_snapshot_proposals_count():
    expected = 90
    actual = _count_json_records("governance", "snapshot_proposals.json")
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="snapshot_votes", description="Snapshot votes row count")
def check_snapshot_votes_count():
    expected = 47551
    actual = _count_json_records("governance", "snapshot_votes.json")
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_proposals", description="Tally proposals row count")
def check_tally_proposals_count():
    expected = 62
    actual = _count_json_records("governance", "tally_proposals.json")
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_votes", description="Tally votes row count")
def check_tally_votes_count():
    expected = 9550
    actual = _count_json_records("governance", "tally_votes.json")
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_delegates", description="Tally delegates row count")
def check_tally_delegates_count():
    expected = 37876
    actual = _count_json_records("governance", "tally_delegates.json")
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


# ---------------------------------------------------------------------------
# Bronze — Great Expectations suite validations (schema + values)
# ---------------------------------------------------------------------------


@asset_check(asset="snapshot_proposals", description="GE schema & value validation")
def check_ge_snapshot_proposals():
    return _run_ge_suite("governance", "snapshot_proposals.json", "snapshot_proposals_suite")


@asset_check(asset="snapshot_votes", description="GE schema & value validation")
def check_ge_snapshot_votes():
    return _run_ge_suite("governance", "snapshot_votes.json", "snapshot_votes_suite")


@asset_check(asset="tally_proposals", description="GE schema & value validation")
def check_ge_tally_proposals():
    return _run_ge_suite("governance", "tally_proposals.json", "tally_proposals_suite")


@asset_check(asset="tally_votes", description="GE schema & value validation")
def check_ge_tally_votes():
    return _run_ge_suite("governance", "tally_votes.json", "tally_votes_suite")


@asset_check(asset="tally_delegates", description="GE schema & value validation")
def check_ge_tally_delegates():
    return _run_ge_suite("governance", "tally_delegates.json", "tally_delegates_suite")
