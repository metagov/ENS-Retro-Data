-- Silver: Cleaned OSO ENS code metrics
-- Deduplicates on artifact_id (keep most recent row), casts dates, adds source tag

select distinct on (artifact_id)
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    star_count,
    fork_count,
    cast(contributor_count as integer)                    as contributor_count,
    cast(contributor_count_6_months as integer)           as contributor_count_6_months,
    cast(active_developer_count_6_months as integer)      as active_developer_count_6_months,
    cast(new_contributor_count_6_months as integer)       as new_contributor_count_6_months,
    cast(commit_count_6_months as integer)                as commit_count_6_months,
    cast(merged_pull_request_count_6_months as integer)   as merged_pull_request_count_6_months,
    cast(opened_pull_request_count_6_months as integer)   as opened_pull_request_count_6_months,
    cast(opened_issue_count_6_months as integer)          as opened_issue_count_6_months,
    cast(closed_issue_count_6_months as integer)          as closed_issue_count_6_months,
    round(cast(fulltime_developer_average_6_months as double), 2) as fulltime_developer_average_6_months,
    cast(first_commit_date as timestamp)                  as first_commit_date,
    cast(last_commit_date as timestamp)                   as last_commit_date,
    'oso' as source
from {{ ref('stg_oso_ens_code_metrics') }}
where artifact_id is not null
order by artifact_id, last_commit_date desc nulls last
