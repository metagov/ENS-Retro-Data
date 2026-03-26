-- Staging: OSO ENS per-repo code health metrics
-- Current snapshot of dev activity per GitHub repo (6-month windows for activity counts)

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    star_count,
    fork_count,
    contributor_count,
    contributor_count_6_months,
    active_developer_count_6_months,
    fulltime_developer_average_6_months,
    new_contributor_count_6_months,
    commit_count_6_months,
    merged_pull_request_count_6_months,
    opened_pull_request_count_6_months,
    opened_issue_count_6_months,
    closed_issue_count_6_months,
    first_commit_date,
    last_commit_date
from {{ source('bronze_github', 'oso_ens_code_metrics') }}
