-- Silver: Cleaned OSO ENS code metrics
-- Deduplicates on artifact_id (keep most recent row), casts dates, adds source tag
-- Schema updated 2026-04: OSO retired 6-month window columns; now all-time aggregates only

select distinct on (artifact_id)
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    language,
    cast(star_count as integer)                     as star_count,
    cast(fork_count as integer)                     as fork_count,
    cast(contributor_count as integer)              as contributor_count,
    cast(commit_count as integer)                   as commit_count,
    cast(merged_pull_request_count as integer)      as merged_pull_request_count,
    cast(opened_pull_request_count as integer)      as opened_pull_request_count,
    cast(opened_issue_count as integer)             as opened_issue_count,
    cast(closed_issue_count as integer)             as closed_issue_count,
    cast(first_commit_date as timestamp)            as first_commit_date,
    cast(last_commit_date as timestamp)             as last_commit_date,
    'oso' as source
from {{ ref('stg_oso_ens_code_metrics') }}
where artifact_id is not null
order by artifact_id, last_commit_date desc nulls last
