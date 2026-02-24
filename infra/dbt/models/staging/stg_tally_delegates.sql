-- Staging: Tally delegate profiles
-- Reads raw JSON and renames columns to snake_case

select
    address,
    ens_name,
    voting_power as voting_power_wei,
    delegators_count,
    votes_count,
    proposals_count,
    statement
from {{ source('bronze_governance', 'tally_delegates') }}
