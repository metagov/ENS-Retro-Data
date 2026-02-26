-- Staging: votingpower.xyz delegate export
-- Reads the existing CSV file and renames columns to snake_case

select
    "Rank" as rank,
    "Delegate" as delegate_address,
    "Voting Power" as voting_power,
    "30 Day Change" as voting_power_30d_change,
    "Delegations" as delegations_count,
    "On-chain Votes" as onchain_votes_count
from {{ source('bronze_governance', 'votingpower_delegates') }}
