-- Staging: OSO ENS per-repo code health metrics
-- All-time aggregate snapshot per GitHub repo.
-- Schema updated 2026-04: OSO retired code_metrics_by_artifact_v0;
-- data now sourced from repositories_v0 + key_metrics_by_artifact_v0.

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    star_count,
    fork_count,
    language,
    contributor_count,
    commit_count,
    merged_pull_request_count,
    opened_pull_request_count,
    opened_issue_count,
    closed_issue_count,
    first_commit_date,
    last_commit_date
from {{ source('bronze_github', 'oso_ens_code_metrics') }}
