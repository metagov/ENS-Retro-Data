-- Staging: OSO ENS daily GitHub event history
-- One row per (repo, event_type, day). All event types included.
-- Incremental appends in bronze may produce duplicates — deduplicated in silver.

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    event_source_id,
    event_type,
    from_artifact_id,
    to_artifact_id,
    amount,
    cast(time as timestamp) as event_time
from {{ source('bronze_github', 'oso_ens_timeseries') }}
