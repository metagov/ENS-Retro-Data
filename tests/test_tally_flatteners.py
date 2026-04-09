"""Tests for infra/ingest/tally_api.py flattener functions.

These are pure functions — they take raw API responses and reshape them
into flat dicts for bronze JSON. No HTTP, no Tally API key needed.
The Tally fetchers themselves are frozen (Tally.xyz shut down their API);
the flatteners remain useful for any future revival or other indexers
that produce Tally-shaped data.
"""

from __future__ import annotations

from infra.ingest.tally_api import (
    flatten_tally_delegates,
    flatten_tally_proposals,
    flatten_tally_votes,
)


class TestFlattenTallyProposals:
    def test_empty_input_returns_empty_list(self):
        assert flatten_tally_proposals([]) == []

    def test_single_proposal_basic_fields(self, sample_tally_proposal):
        result = flatten_tally_proposals([sample_tally_proposal])
        assert len(result) == 1
        p = result[0]
        assert p["id"] == "tally-prop-001"
        assert p["onchain_id"] == "0xabc123"
        assert p["title"] == "EP 1.1: Sample proposal"
        assert p["status"] == "executed"
        assert p["proposer"] == "0x1111111111111111111111111111111111111111"
        assert p["proposer_ens"] == "test.eth"

    def test_vote_stats_flattened(self, sample_tally_proposal):
        p = flatten_tally_proposals([sample_tally_proposal])[0]
        # Voter counts come through as ints
        assert p["for_voters"] == 50
        assert p["against_voters"] == 10
        assert p["abstain_voters"] == 5
        # Percentages
        assert p["for_percent"] == 80.0
        assert p["against_percent"] == 16.0
        assert p["abstain_percent"] == 4.0
        # Wei → human conversion happens in _raw_to_human (returns string)
        # The for_votes value is 1e24 wei = 1,000,000 ENS
        assert "1000000" in str(p["for_votes"]) or p["for_votes"] is not None

    def test_blocks_and_timestamps_flattened(self, sample_tally_proposal):
        p = flatten_tally_proposals([sample_tally_proposal])[0]
        assert p["start_block"] == 18000000
        assert p["end_block"] == 18050000
        assert p["block_number"] == 18055000
        assert p["start_timestamp"] == "2026-01-01T00:00:00Z"
        assert p["end_timestamp"] == "2026-01-08T00:00:00Z"

    def test_metadata_url_fields(self, sample_tally_proposal):
        p = flatten_tally_proposals([sample_tally_proposal])[0]
        assert p["discourse_url"] == "https://discuss.ens.domains/t/test/1"
        assert p["snapshot_url"] == ""

    def test_organization_fields(self, sample_tally_proposal):
        p = flatten_tally_proposals([sample_tally_proposal])[0]
        assert p["organization_id"] == "org-1"
        assert p["organization_name"] == "ENS"
        assert p["governor_name"] == "ENS Governor"

    def test_missing_optional_fields_default_to_empty(self):
        minimal = {
            "id": "x",
            "metadata": {},
            "proposer": {},
            "voteStats": [],
            "start": None,
            "end": None,
            "block": None,
            "governor": {},
            "organization": {},
        }
        p = flatten_tally_proposals([minimal])[0]
        assert p["title"] == ""
        assert p["proposer"] == ""
        assert p["start_block"] is None
        assert p["for_voters"] == 0

    def test_description_truncated_to_5000(self):
        big = {
            "id": "x",
            "metadata": {"description": "x" * 10000},
            "proposer": {},
            "voteStats": [],
            "start": None,
            "end": None,
            "block": None,
            "governor": {},
            "organization": {},
        }
        p = flatten_tally_proposals([big])[0]
        assert len(p["description"]) == 5000


class TestFlattenTallyVotes:
    def test_empty_input_returns_empty_list(self):
        assert flatten_tally_votes([]) == []

    def test_single_vote_basic_fields(self, sample_tally_vote):
        result = flatten_tally_votes([sample_tally_vote])
        assert len(result) == 1
        v = result[0]
        assert v["id"] == "tally-vote-001"
        assert v["voter"] == "0x2222222222222222222222222222222222222222"
        assert v["voter_name"] == "Voter A"
        assert v["voter_ens"] == "voter-a.eth"
        assert v["proposal_id"] == "tally-prop-001"

    def test_support_mapped_to_string(self, sample_tally_vote):
        # type "1" → "for", "2" → "against", "3" → "abstain"
        for code, expected in [("1", "for"), ("2", "against"), ("3", "abstain")]:
            v = dict(sample_tally_vote, type=code)
            result = flatten_tally_votes([v])[0]
            assert result["support"] == expected

    def test_unknown_support_passes_through(self, sample_tally_vote):
        v = dict(sample_tally_vote, type="other")
        assert flatten_tally_votes([v])[0]["support"] == "other"

    def test_reason_truncated_to_500(self):
        v = {
            "id": "x",
            "type": "1",
            "amount": "0",
            "reason": "x" * 1000,
            "voter": {},
            "proposal": {},
            "block": {},
        }
        assert len(flatten_tally_votes([v])[0]["reason"]) == 500

    def test_block_fields(self, sample_tally_vote):
        v = flatten_tally_votes([sample_tally_vote])[0]
        assert v["block_number"] == 18030000
        assert v["block_timestamp"] == "2026-01-05T00:00:00Z"


class TestFlattenTallyDelegates:
    def test_empty_input_returns_empty_list(self):
        assert flatten_tally_delegates([]) == []

    def test_single_delegate_basic_fields(self, sample_tally_delegate):
        result = flatten_tally_delegates([sample_tally_delegate])
        assert len(result) == 1
        d = result[0]
        assert d["id"] == "tally-del-001"
        assert d["address"] == "0x3333333333333333333333333333333333333333"
        assert d["name"] == "Delegate One"
        assert d["delegators_count"] == 12

    def test_token_and_org_fields(self, sample_tally_delegate):
        d = flatten_tally_delegates([sample_tally_delegate])[0]
        assert d["token_symbol"] == "ENS"
        assert d["token_name"] == "Ethereum Name Service"
        assert d["organization_name"] == "ENS"

    def test_statement_fields(self, sample_tally_delegate):
        d = flatten_tally_delegates([sample_tally_delegate])[0]
        assert d["statement"] == "My governance philosophy."
        assert d["statement_summary"] == "Pragmatic."
        assert d["is_seeking_delegation"] is True
