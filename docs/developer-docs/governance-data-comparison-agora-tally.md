# ENS Governance Data Comparison — Agora vs Tally vs Etherscan

**Date:** 2026-03-24
**Prepared by:** ENS Retro Data team
**Purpose:** Side-by-side comparison of governance data available from Agora, Tally, and Etherscan for the ENS DAO

---

## Summary

We pulled governance data from three sources — **Agora** (on-chain event indexer), **Tally** (governance API), and **Etherscan** (blockchain explorer API). Each source captures different aspects of the same governance activity. This report compares what each source provides, where they overlap, and where each has unique data the others don't.

---

## 1. Data We Have From Each Source

### Agora — On-chain Event Logs

Raw blockchain events indexed from the ENS Governor contract (`0x323a...b7e3`) and ENS Token contract (`0xc183...9d72`).

| Dataset | Records | Fields |
|---------|---------|--------|
| **VoteCast** | 10,092 | block_number, transaction_index, log_index, voter, proposal_id, support, weight, reason |
| **ProposalCreated** | 66* | block_number, transaction_index, log_index, proposal_id, proposer, targets, values, signatures, calldatas, start_block, end_block, description |
| **ProposalExecuted** | 59 | block_number, transaction_index, log_index, proposal_id |
| **ProposalQueued** | 60 | block_number, transaction_index, log_index, proposal_id, eta |
| **ProposalCanceled** | 0 | block_number, transaction_index, log_index, proposal_id |
| **QuorumNumeratorUpdated** | 1 | block_number, transaction_index, log_index, old_quorum_numerator, new_quorum_numerator |
| **DelegateChanged** | 123,121 | block_number, transaction_index, log_index, delegator, from_delegate, to_delegate |
| **DelegateVotesChanged** | 308,871 | block_number, transaction_index, log_index, delegate, previous_balance, new_balance |
| **Transfer** | 1,513,540 | block_number, transaction_index, log_index, from, to, value |
| **Claim** | 102,833 | block_number, transaction_index, log_index, claimant, amount |
| **MerkleRootChanged** | 1 | block_number, transaction_index, log_index, merkle_root |
| **OwnershipTransferred** | 2 | block_number, transaction_index, log_index, previous_owner, new_owner |

*\*ProposalCreated CSV has 4,521 lines due to multi-line description fields; actual proposal count is ~66.*

### Tally — Governance API

Enriched data from the Tally GraphQL API. Provides human-readable names, vote tallies, and delegate profiles.

| Dataset | Records | Fields |
|---------|---------|--------|
| **Proposals** | 66 | id, onchain_id, title, description, status, eta, discourse_url, snapshot_url, proposer, proposer_name, proposer_ens, governor_id, governor_name, organization_id, organization_name, start_block, start_timestamp, end_block, end_timestamp, block_number, block_timestamp, created_block, for_votes, against_votes, abstain_votes, for_voters, against_voters, abstain_voters, for_percent, against_percent, abstain_percent, quorum |
| **Votes** | 9,987 | id, voter, voter_name, voter_ens, support, weight, reason, tx_hash, chain_id, proposal_id, block_timestamp, block_number |
| **Delegates** | 37,891 | id, address, name, ens_name, twitter, bio, picture, account_type, voting_power, delegators_count, is_prioritized, chain_id, token_symbol, token_name, statement, statement_summary, is_seeking_delegation, organization_id, organization_name, participation_rate, voted_proposals_count, proposals_count |

### Etherscan — Blockchain Explorer API

On-chain DelegateChanged events fetched directly from the Etherscan API.

| Dataset | Records | Fields |
|---------|---------|--------|
| **Delegation Events** | 122,974 | delegator, delegate, block_number, timestamp, token_balance |

---

## 2. Vote Data Comparison

Both Agora and Tally capture individual votes cast on ENS governance proposals.

| Field | Agora | Tally | Notes |
|-------|:-----:|:-----:|-------|
| block_number | ✅ | ✅ | Same |
| transaction_index | ✅ | ❌ | Agora only — position of tx within a block |
| log_index | ✅ | ❌ | Agora only — position of event within a tx |
| voter (address) | ✅ | ✅ | Same format (0x address) |
| voter_name | ❌ | ✅ | Tally resolves human-readable names |
| voter_ens | ❌ | ✅ | Tally resolves ENS names |
| proposal_id | ✅ (on-chain) | ✅ (Tally internal) | **Different ID formats** — Agora uses the raw on-chain uint256, Tally uses its own internal ID |
| support | ✅ (numeric: 0/1/2) | ✅ (string: for/against/abstain) | Different encoding, same meaning |
| weight | ✅ (raw wei) | ✅ (raw wei) | Same |
| reason | ✅ | ✅ | Same |
| tx_hash | ❌ | ✅ | Tally only |
| block_timestamp | ❌ | ✅ | Tally provides ISO 8601 timestamps; Agora has block numbers only |
| chain_id | ❌ | ✅ | Tally only |

**Record count and indexing window:**

| | Count | Latest block | Approx. date |
|--|------:|-------------:|--------------|
| Agora | 10,092 | 24,723,328 | ~2026-03-23 |
| Tally | 9,987 | 24,695,038 | 2026-03-20 |

The two datasets were indexed at different points in time — Tally ~3 days before Agora. We aligned both datasets to Tally's cutoff block (24,695,038) and compared using the correct unique key `(voter, proposal_id, support)`:

| | Raw count | Within cutoff | Unique votes (deduped) |
|--|----------:|-------------:|-----------------------:|
| Agora | 10,092 | 9,993 | 9,986 |
| Tally | 9,987 | 9,987 | 9,987 |
| **Difference** | **105** | **6** | **-1** |

The 105-record gap breaks down as:
- **41 records** — newer blocks: Agora data covers up to block 24,723,328 (~2026-03-23), Tally stops at block 24,695,038 (~2026-03-20)
- **7 duplicate event rows** in Agora — the same vote appears twice with different `transaction_index` and `log_index` values. These are cases where a voter's delegation changed mid-block causing two `VoteCast` log entries for the same vote. Tally correctly deduplicates these.
- **After removing both:** Agora and Tally are **within 1 record of each other** — effectively identical coverage for the same time window.

---

## 3. Proposal Data Comparison

| Field | Agora | Tally | Notes |
|-------|:-----:|:-----:|-------|
| proposal_id (on-chain) | ✅ | ✅ (as `onchain_id`) | Same underlying ID |
| proposer (address) | ✅ | ✅ | Same |
| proposer_name | ❌ | ✅ | Tally resolves names |
| proposer_ens | ❌ | ✅ | Tally resolves ENS names |
| description | ✅ | ✅ | Same raw text |
| title | ❌ | ✅ | Tally extracts title from the description text |
| status | ❌ | ✅ | Tally tracks lifecycle (active, executed, defeated, etc.) |
| start_block / end_block | ✅ | ✅ | Same |
| start_timestamp / end_timestamp | ❌ | ✅ | Tally provides ISO timestamps; Agora has block numbers only |
| targets (contract addresses) | ✅ | ❌ | Agora only — what contracts the proposal calls |
| values (ETH amounts) | ✅ | ❌ | Agora only — ETH sent with each call |
| signatures (function names) | ✅ | ❌ | Agora only — which functions are called |
| calldatas (encoded params) | ✅ | ❌ | Agora only — exact encoded parameters |
| for/against/abstain votes | ❌ | ✅ | Tally pre-aggregates vote tallies |
| voter counts per choice | ❌ | ✅ | Tally provides for_voters, against_voters, etc. |
| vote percentages | ❌ | ✅ | Tally calculates for_percent, against_percent, etc. |
| quorum | ❌ | ✅ | Tally provides quorum requirement |
| discourse_url | ❌ | ✅ | Tally links to forum discussion |
| snapshot_url | ❌ | ✅ | Tally links to related Snapshot vote |
| eta (execution time) | ❌ | ✅ | Tally provides; Agora has this in ProposalQueued separately |
| transaction_index / log_index | ✅ | ❌ | Agora only — exact on-chain position |

**Key takeaway:** Agora is the only source with the raw execution payload (targets, calldatas, signatures, values). This is the actual code a proposal would execute on-chain. Tally doesn't expose this. Tally provides everything needed for governance reporting (status, tallies, quorum, timestamps, forum links).

---

## 4. Proposal Lifecycle Events

Agora captures separate events for each stage of a proposal's lifecycle. Tally rolls these into a single `status` field.

| Lifecycle Event | Agora | Tally | Notes |
|----------------|:-----:|:-----:|-------|
| Proposal created | ✅ (66 events) | ✅ (status field) | Agora has the raw event with full calldata |
| Proposal queued | ✅ (60 events, with `eta`) | ⚠️ Partial (eta field only) | Agora gives the exact block this happened |
| Proposal executed | ✅ (59 events) | ⚠️ Partial (status = "executed") | Agora gives the exact execution block |
| Proposal canceled | ✅ (0 events*) | ⚠️ Partial (status = "cancelled") | *No ENS proposals have been canceled |
| Quorum changed | ✅ (1 event) | ❌ | Only Agora tracks governance parameter changes |

**Key takeaway:** Agora gives you the exact block and transaction where each lifecycle transition happened. Tally only tells you the current status. If you need to know *when* a proposal was executed or queued (at block-level precision), Agora is the only source.

---

## 5. Delegation Data Comparison

Three different views of ENS token delegation.

| Field | Agora | Etherscan | Tally | Notes |
|-------|:-----:|:---------:|:-----:|-------|
| **Data type** | Event log (time-series) | Event log (time-series) | **Snapshot** (current state) | Fundamentally different |
| delegator | ✅ | ✅ | ❌ | Who delegated |
| to_delegate / delegate | ✅ (`to_delegate`) | ✅ (`delegate`) | ❌ | Who received delegation |
| from_delegate | ✅ | ❌ | ❌ | **Only Agora** — who the delegator was previously delegated to |
| block_number | ✅ | ✅ | ❌ | When it happened |
| transaction_index | ✅ | ❌ | ❌ | Exact position in block |
| log_index | ✅ | ❌ | ❌ | Exact position in transaction |
| timestamp | ❌ | ✅ | ❌ | Etherscan provides unix timestamps |
| token_balance | ❌ | ⚠️ Present but empty | ❌ | Not populated in any source |
| address | ❌ | ❌ | ✅ | Delegate's address |
| voting_power | ❌ | ❌ | ✅ | Current voting power (snapshot) |
| name / ens_name | ❌ | ❌ | ✅ | Delegate identity |
| bio / statement | ❌ | ❌ | ✅ | Delegate profile information |
| delegators_count | ❌ | ❌ | ✅ | Current number of delegators |
| twitter / picture | ❌ | ❌ | ✅ | Social links and avatar |

**Record counts:**
- Agora: 123,121 delegation change events
- Etherscan: 122,974 delegation change events (~147 fewer)
- Tally: 37,891 delegate profiles (not comparable — different data type)

**Key takeaway:** Tally does NOT provide historical delegation events. It only gives a snapshot of current delegate profiles (who they are, how much voting power they have today). For delegation history (who delegated to whom, when), you need Agora or Etherscan. Agora is the most complete — it has ~147 more events than Etherscan and uniquely provides `from_delegate`, which lets you track re-delegations (when someone switches their delegate from A to B).

---

## 6. Voting Power Changes Over Time

| Dataset | Agora | Tally | Etherscan |
|---------|:-----:|:-----:|:---------:|
| DelegateVotesChanged (308,871 events) | ✅ | ❌ | ❌ |

Agora's `DelegateVotesChanged` tracks every time a delegate's voting power changes, with the `previous_balance` and `new_balance`. This enables reconstructing a full voting power time-series for any delegate. Neither Tally nor Etherscan provides this.

---

## 7. Token Transfer and Claim Data

| Dataset | Agora | Tally | Etherscan |
|---------|:-----:|:-----:|:---------:|
| ENS Token Transfers (1,513,540 events) | ✅ | ❌ | ❌* |
| ENS Token Claims / Airdrop (102,833 events) | ✅ | ❌ | ❌ |

*\*Etherscan can provide transfer data but we haven't indexed it separately. Agora provides the complete ERC-20 transfer history for the ENS token.*

---

## 8. Data Each Source Uniquely Provides

### Only Agora has:
- Raw proposal execution payloads (targets, calldatas, signatures, values)
- Exact on-chain event ordering (transaction_index, log_index)
- `from_delegate` on delegation changes (re-delegation tracking)
- Voting power change history (DelegateVotesChanged — 308,871 events)
- Complete ENS token transfer history (1.5M events)
- ENS token airdrop claim records (102,833 events)
- Governance parameter changes (QuorumNumeratorUpdated)
- Exact block numbers for proposal lifecycle transitions (queued, executed, canceled)

### Only Tally has:
- Human-readable identity resolution (names, ENS names, twitter handles)
- Delegate profiles with bios, statements, and avatars
- Pre-aggregated vote tallies and percentages per proposal
- Proposal status tracking (active, executed, defeated, etc.)
- Quorum requirements per proposal
- Links to forum discussions and Snapshot votes
- ISO 8601 timestamps (Agora only provides block numbers)
- Transaction hashes for votes

### Only Etherscan has:
- Unix timestamps on delegation events (Agora has block numbers, Tally has nothing)

---

## 9. What Tally API Offers That We Haven't Indexed Yet

Our current Tally integration uses four GraphQL queries: `organization`, `proposals`, `votes` (per proposal), and `delegates`. We verified this by reading the export code directly — there are **no deliberately skipped fields or commented-out queries**. The script was scoped to the core governance data needed for retrospective analysis and simply hasn't explored the full API surface yet.

The following are additional Tally API capabilities we are aware of but have not yet queried:

| Available Data | Indexed? | Notes |
|---------------|:--------:|-------|
| Proposals (with metadata) | ✅ | Full coverage |
| Individual votes | ✅ | Full coverage — `... on OnchainVote` fragment only; other vote types (if any) not confirmed |
| Delegate profiles | ✅ | Full coverage |
| Organization metadata | ✅ | Used for org resolution |
| Governor contract details (voting delay, voting period, proposal threshold, timelock address) | ❌ | Not yet queried — `governors` query exists in Tally API |
| Delegation relationships (who delegated to whom) | ❌ | Not yet queried — `delegations` query may be available; currently covered by Agora + Etherscan |
| Token balances / supply info | ❌ | Not yet queried — `tokens` / `tokenBalances` queries may be available |
| Per-address governance activity history | ❌ | Not yet queried — `account` query may provide this |
| Executable call details on proposals | ❌ | Not yet queried — `executableCalls` field may be available on proposals; currently covered by Agora |
| Participation rate per delegate | ✅ | Now indexed — `participation_rate`, `voted_proposals_count`, `proposals_count` added to delegates |

None of the above are deliberately excluded. We'd welcome confirmation from Agora/Tally on which of these are actually available for ENS.

---

## 10. Record Count Summary

| Data Type | Agora | Tally | Etherscan | Delta |
|-----------|------:|------:|----------:|-------|
| Votes | 10,092 | 9,987 | — | Agora +105 (41 newer blocks + 7 dedup rows; aligned = ~match) |
| Proposals | 66 | 66 | — | Match |
| Delegation events | 123,121 | — | 122,974 | Agora +147 |
| Delegate profiles | — | 37,891 | — | Tally only |
| Voting power changes | 308,871 | — | — | Agora only |
| Token transfers | 1,513,540 | — | — | Agora only |
| Token claims | 102,833 | — | — | Agora only |
| Proposal lifecycle events | 120 | — | — | Agora only |

---

## 11. Recommended Source Strategy

| Data Need | Best Source | Reason |
|-----------|-----------|--------|
| Governance reporting (proposals, status, tallies) | **Tally** | Pre-aggregated, human-readable, has status + timestamps |
| On-chain execution analysis (what proposals actually do) | **Agora** | Only source with targets, calldatas, signatures |
| Individual vote records | **Both** | Agora for ordering precision, Tally for identity |
| Delegation history (who delegated when) | **Agora** | Most events + unique `from_delegate` field |
| Delegate identity and profiles | **Tally** | Names, ENS, bios, statements, social links |
| Voting power time-series | **Agora** | Only source with DelegateVotesChanged events |
| Token transfer analysis | **Agora** | Only source with complete transfer history |
| Timestamps | **Tally** (ISO) or **Etherscan** (unix) | Agora provides block numbers only |

---

*This comparison is based on data indexed as of March 2026. Agora data was indexed on 2026-03-23 (up to block 24,723,328). Tally data was indexed on 2026-03-20 (up to block 24,695,038). Record counts reflect these different indexing windows — see Section 2 for the vote count alignment analysis.*
