-- Staging: Tally delegate profiles
-- Reads raw JSON and renames columns to snake_case

select
    id,
    address,
    name,
    ens_name,
    twitter,
    bio,
    picture,
    account_type,
    voting_power as voting_power_wei,
    delegators_count,
    is_prioritized,
    chain_id,
    token_symbol,
    token_name,
    statement,
    statement_summary,
    is_seeking_delegation,
    organization_id,
    organization_name,
    participation_rate,
    voted_proposals_count,
    proposals_count
from {{ source('bronze_governance', 'tally_delegates') }}
