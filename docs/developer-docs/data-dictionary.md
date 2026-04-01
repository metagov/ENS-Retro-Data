# Data Dictionary

Schema definitions for each layer of the medallion architecture.

## Bronze Layer (Raw)

Raw data as ingested from sources. Minimal transformation — only structural parsing from JSON.

### governance/snapshot_proposals
| Column | Type | Description |
|---|---|---|
| id | string | Snapshot proposal ID |
| title | string | Proposal title |
| body | string | Proposal body (markdown) |
| choices | array\<string\> | Available vote choices |
| start | int | Start timestamp (unix) |
| end | int | End timestamp (unix) |
| state | string | Proposal state |
| scores | array\<float\> | Vote scores per choice |
| scores_total | float | Total voting power cast |
| votes | int | Number of votes |
| author | string | Proposer address |

### governance/snapshot_votes
| Column | Type | Description |
|---|---|---|
| id | string | Vote ID |
| voter | string | Voter address |
| choice | int/object | Choice index or weighted choice |
| vp | float | Voting power |
| created | int | Vote timestamp (unix) |
| proposal_id | string | Parent proposal ID |

### governance/tally_proposals
| Column | Type | Description |
|---|---|---|
| id | string | Tally proposal ID |
| title | string | Proposal title |
| description | string | Proposal description |
| status | string | Proposal status |
| proposer | string | Proposer address |
| start_block | int | Start block number |
| end_block | int | End block number |
| for_votes | string | For votes (wei) |
| against_votes | string | Against votes (wei) |
| abstain_votes | string | Abstain votes (wei) |

### governance/tally_votes
| Column | Type | Description |
|---|---|---|
| id | string | Vote ID |
| voter | string | Voter address |
| support | int | 0=against, 1=for, 2=abstain |
| weight | string | Vote weight (wei) |
| proposal_id | string | Parent proposal ID |
| reason | string | Vote reason (optional) |

### governance/tally_delegates
| Column | Type | Description |
|---|---|---|
| address | string | Delegate address |
| ens_name | string | ENS name (optional) |
| voting_power | string | Voting power (wei) |
| delegators_count | int | Number of delegators |
| votes_count | int | Votes cast |
| proposals_count | int | Proposals created |
| statement | string | Delegate statement (optional) |

### on-chain/delegations
| Column | Type | Description |
|---|---|---|
| delegator | string | Delegator address |
| delegate | string | Delegate address |
| block_number | int | Block of delegation |
| timestamp | int | Unix timestamp |
| token_balance | string | Delegator balance (wei) |

### on-chain/token_distribution
| Column | Type | Description |
|---|---|---|
| address | string | Holder address |
| balance | string | Token balance (wei) |
| percentage | float | Share of total supply |
| snapshot_block | int | Block number of snapshot |

### on-chain/treasury_flows
| Column | Type | Description |
|---|---|---|
| tx_hash | string | Transaction hash |
| from | string | Sender address |
| to | string | Recipient address |
| value | string | Transfer amount |
| token | string | Token symbol |
| block_number | int | Block number |
| timestamp | int | Unix timestamp |
| category | string | Transaction category |

## Silver Layer (Cleaned)

Cleaned, typed, and deduplicated versions of bronze data. Key transforms:
- Addresses lowercased
- Wei values converted to float (ETH/token units)
- Timestamps parsed to datetime
- Values validated against taxonomy.yaml
- Duplicates removed

### silver/address_crosswalk
| Column | Type | Description |
|---|---|---|
| address | string | Unique Ethereum address |
| ens_name | string | Resolved ENS name |
| stakeholder_role | string | Role from taxonomy |
| source | string | Primary data source |

## Gold Layer (Analysis Views)

### gold/governance_activity
| Column | Type | Description |
|---|---|---|
| proposal_id | string | Unique proposal ID |
| source | string | snapshot or tally |
| title | string | Proposal title |
| category | string | Governance category |
| status | string | Proposal status |
| vote_count | int | Number of votes |
| start_date | datetime | Voting start |
| end_date | datetime | Voting end |

### gold/delegate_scorecard
| Column | Type | Description |
|---|---|---|
| address | string | Delegate address |
| ens_name | string | ENS name |
| voting_power | float | Current voting power |
| snapshot_votes_cast | int | Snapshot votes |
| tally_votes_cast | int | Tally votes |
| participation_rate | float | Vote participation % |
| delegators_count | int | Number of delegators |

### gold/treasury_summary
Aggregated treasury flows by period and category.

### gold/participation_index
Composite participation metrics over time.

### gold/decentralization_index
Power distribution and decentralization metrics (Nakamoto coefficient, HHI).
