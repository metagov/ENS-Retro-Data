-- Staging: OSO ENS GitHub repository registry
-- One row per ENS GitHub repo registered in Open Source Observer

select
    artifact_id,
    artifact_name,
    artifact_namespace,
    artifact_source,
    artifact_source_id,
    project_id,
    project_name,
    project_namespace,
    project_source
from {{ source('bronze_github', 'oso_ens_repos') }}
