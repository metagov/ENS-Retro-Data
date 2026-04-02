{% macro source(source_name, table_name) %}
  {%- set external_locations = {
    'bronze_governance.snapshot_proposals': "read_json_auto('../../bronze/governance/snapshot_proposals.json')",
    'bronze_governance.snapshot_votes': "read_json_auto('../../bronze/governance/snapshot_votes.json')",
    'bronze_governance.tally_proposals': "read_json_auto('../../bronze/governance/tally_proposals.json')",
    'bronze_governance.tally_votes': "read_json_auto('../../bronze/governance/tally_votes.json')",
    'bronze_governance.tally_delegates': "read_json_auto('../../bronze/governance/tally_delegates.json')",
    'bronze_governance.votingpower_delegates': "read_csv_auto('../../bronze/governance/votingpower-xyz/ens-delegates-2026-02-20.csv')",
    'bronze_onchain.delegations': "read_json_auto('../../bronze/on-chain/delegations.json')",
    'bronze_onchain.token_distribution': "read_json_auto('../../bronze/on-chain/token_distribution.json')",
    'bronze_onchain.treasury_flows': "read_json_auto('../../bronze/on-chain/treasury_flows.json')",
    'bronze_financial.compensation': "read_json_auto('../../bronze/financial/compensation.json')",
    'bronze_grants.grants': "read_json_auto('../../bronze/grants/large_grants.json')",
    'bronze_interviews.delegate_profiles': "read_json_auto('../../bronze/interviews/delegate_profiles.json')",
    'bronze_forum.forum_posts': "read_json_auto('../../bronze/forum/forum_posts.json')"
  } -%}
  {%- set key = source_name ~ '.' ~ table_name -%}
  {%- if key in external_locations -%}
    {{ external_locations[key] }}
  {%- else -%}
    {{ builtins.source(source_name, table_name) }}
  {%- endif -%}
{% endmacro %}
