-- Silver: Cleaned OSO ENS timeseries events
-- Deduplicates on (artifact_id, event_type, event_time) — guards against
-- incremental append overlaps in the bronze layer.

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    event_source,
    event_type,
    cast(amount as double) as amount,
    event_time,
    'oso' as source
from (
    select
        *,
        row_number() over (
            partition by artifact_id, event_type, event_time
            order by event_time desc
        ) as rn
    from {{ ref('stg_oso_ens_timeseries') }}
    where artifact_id is not null
      and event_type is not null
      and event_time is not null
) deduped
where rn = 1
