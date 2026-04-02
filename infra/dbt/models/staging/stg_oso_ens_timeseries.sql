-- Staging: OSO ENS periodic GitHub metric history
-- One row per (repo, metric_type, sample_date).
-- Schema updated 2026-04: OSO retired timeseries_events_by_artifact_v0;
-- data now sourced from timeseries_metrics_by_artifact_v0 + metrics_v0.

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    event_type,
    cast(event_time as timestamp) as event_time,
    amount
from {{ source('bronze_github', 'oso_ens_timeseries') }}
