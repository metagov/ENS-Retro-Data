"""Asset checks for data quality validation across all layers."""

from dagster import AssetCheckResult, AssetCheckSeverity, asset_check

from infra.taxonomy import validate_column

# ---------------------------------------------------------------------------
# Bronze — row count checks
# ---------------------------------------------------------------------------


@asset_check(asset="snapshot_proposals", description="Snapshot proposals row count")
def check_snapshot_proposals_count(snapshot_proposals):
    expected = 90
    actual = len(snapshot_proposals)
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="snapshot_votes", description="Snapshot votes row count")
def check_snapshot_votes_count(snapshot_votes):
    expected = 47551
    actual = len(snapshot_votes)
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_proposals", description="Tally proposals row count")
def check_tally_proposals_count(tally_proposals):
    expected = 62
    actual = len(tally_proposals)
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_votes", description="Tally votes row count")
def check_tally_votes_count(tally_votes):
    expected = 9550
    actual = len(tally_votes)
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


@asset_check(asset="tally_delegates", description="Tally delegates row count")
def check_tally_delegates_count(tally_delegates):
    expected = 37876
    actual = len(tally_delegates)
    passed = actual > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN,
        metadata={"expected": expected, "actual": actual},
        description=f"Expected ~{expected} rows, got {actual}",
    )


# ---------------------------------------------------------------------------
# Silver — taxonomy conformance
# ---------------------------------------------------------------------------


@asset_check(asset="clean_snapshot_proposals", description="Proposal status taxonomy check")
def check_snapshot_proposal_status(clean_snapshot_proposals):
    if clean_snapshot_proposals.empty or "state" not in clean_snapshot_proposals.columns:
        return AssetCheckResult(passed=True, description="No data to validate")
    invalid = validate_column(clean_snapshot_proposals["state"], "proposal_status")
    return AssetCheckResult(
        passed=len(invalid) == 0,
        severity=AssetCheckSeverity.WARN,
        metadata={"invalid_values": invalid},
        description=f"Invalid proposal_status values: {invalid}" if invalid else "All valid",
    )


@asset_check(asset="clean_tally_proposals", description="Tally proposal status taxonomy check")
def check_tally_proposal_status(clean_tally_proposals):
    if clean_tally_proposals.empty or "status" not in clean_tally_proposals.columns:
        return AssetCheckResult(passed=True, description="No data to validate")
    invalid = validate_column(clean_tally_proposals["status"], "proposal_status")
    return AssetCheckResult(
        passed=len(invalid) == 0,
        severity=AssetCheckSeverity.WARN,
        metadata={"invalid_values": invalid},
        description=f"Invalid proposal_status values: {invalid}" if invalid else "All valid",
    )


# ---------------------------------------------------------------------------
# Gold — completeness checks
# ---------------------------------------------------------------------------


@asset_check(asset="governance_activity", description="Governance activity completeness")
def check_governance_activity_complete(governance_activity):
    if governance_activity.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="Governance activity view is empty",
        )
    has_snapshot = (governance_activity["source"] == "snapshot").any()
    has_tally = (governance_activity["source"] == "tally").any()
    return AssetCheckResult(
        passed=has_snapshot and has_tally,
        severity=AssetCheckSeverity.WARN,
        metadata={"has_snapshot": has_snapshot, "has_tally": has_tally},
        description="Both sources present" if (has_snapshot and has_tally) else "Missing a source",
    )
