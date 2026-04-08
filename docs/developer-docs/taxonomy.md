# Taxonomy Reference

This document describes the controlled vocabularies defined in `taxonomy.yaml`.
All pipeline stages validate data against these enumerations.

## Sources

Where data originates:

| Source | Description |
|---|---|
| `snapshot` | Off-chain governance votes (Snapshot.org) |
| `tally` | On-chain governance proposals and votes (Tally — historical, API discontinued) |
| `etherscan` | Blockchain transaction data |
| `dune` | Dune Analytics queries |
| `ens-governance-forum` | Discourse governance forum |
| `github` | GitHub repository activity |
| `interviews` | Stakeholder interviews |
| `grants-portal` | ENS grants program |
| `token-contract` | ENS token contract data |

## Governance Categories

Classification for proposals:

- **executable** — On-chain executable proposals
- **social** — Off-chain signaling / social consensus
- **constitutional** — Changes to ENS constitution or bylaws
- **metagovernance** — Governance process changes
- **funding** — Budget and funding requests
- **election** — Steward and role elections

## Proposal Status

Lifecycle states for proposals:

`active` | `closed` | `executed` | `defeated` | `pending` | `queued` | `cancelled`

## Vote Choices

Standardized vote options: `for` | `against` | `abstain`

## Stakeholder Roles

| Role | Description |
|---|---|
| `delegate` | Token holder who votes on governance |
| `steward` | Elected working group steward |
| `contributor` | Active DAO contributor |
| `token_holder` | ENS token holder (may not vote) |
| `service_provider` | External service provider to the DAO |
| `multisig_signer` | Signer on DAO multisig wallets |
| `working_group_lead` | Lead of a working group |
| `dao_officer` | Official DAO role holder |

## Working Groups

- **meta-governance** — Governance processes and DAO operations
- **ens-ecosystem** — ENS protocol and ecosystem development
- **public-goods** — Public goods funding
- **providers** — Service provider management

## Evaluation Dimensions

Dimensions used in the retrospective evaluation:

1. `governance_participation` — Voter turnout and engagement
2. `proposal_quality` — Proposal outcomes and execution
3. `financial_stewardship` — Treasury management and spending
4. `ecosystem_growth` — Protocol adoption and development
5. `decentralization` — Power distribution metrics
6. `transparency` — Information availability and reporting
7. `community_engagement` — Forum activity and stakeholder input

## Entity Types

Core data entities: `address` | `proposal` | `vote` | `delegate` | `transaction` | `grant` | `working_group` | `forum_post`
