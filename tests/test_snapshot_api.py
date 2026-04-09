"""Tests for infra/ingest/snapshot_api.py.

Snapshot's GraphQL API has no auth and a simple paginated query pattern.
We mock at the run_query() boundary so tests don't depend on the requests
library internals.
"""

from __future__ import annotations

import infra.ingest.snapshot_api as snap


class TestFetchSnapshotProposals:
    def test_single_page_returns_all(self, monkeypatch, sample_snapshot_proposal):
        """One page of results, fewer than batch size → fetch terminates."""
        # Build a mock run_query that returns 3 proposals once, then nothing
        responses = [
            {"data": {"proposals": [sample_snapshot_proposal] * 3}},
        ]
        calls = []

        def fake_run_query(query, **kwargs):
            calls.append(query)
            if responses:
                return responses.pop(0)
            return {"data": {"proposals": []}}

        monkeypatch.setattr(snap, "run_query", fake_run_query)
        monkeypatch.setattr(snap.time, "sleep", lambda *_: None)

        result = snap.fetch_snapshot_proposals()

        assert len(result) == 3
        assert all(p["id"] == sample_snapshot_proposal["id"] for p in result)
        assert len(calls) == 1  # 3 < batch=100, so loop exits after one call

    def test_paginates_until_empty(self, monkeypatch, sample_snapshot_proposal):
        """Two full pages followed by an empty page → fetch terminates."""
        full_page = [sample_snapshot_proposal] * 100
        responses = [
            {"data": {"proposals": full_page}},
            {"data": {"proposals": full_page}},
            {"data": {"proposals": []}},
        ]

        def fake_run_query(query, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(snap, "run_query", fake_run_query)
        monkeypatch.setattr(snap.time, "sleep", lambda *_: None)

        result = snap.fetch_snapshot_proposals()
        assert len(result) == 200

    def test_empty_first_page(self, monkeypatch):
        """Empty first response → empty result, no error."""
        monkeypatch.setattr(snap, "run_query", lambda q, **k: {"data": {"proposals": []}})
        monkeypatch.setattr(snap.time, "sleep", lambda *_: None)
        assert snap.fetch_snapshot_proposals() == []


class TestFetchSnapshotVotes:
    def test_injects_proposal_id_into_each_vote(self, monkeypatch):
        """Every fetched vote should carry the parent proposal_id."""
        proposals = [
            {"id": "prop-A", "title": "Proposal A"},
            {"id": "prop-B", "title": "Proposal B"},
        ]
        # Per-proposal: one page of N votes (N < batch=1000) → loop exits after one call
        responses_by_call = iter([
            {"data": {"votes": [
                {"id": "v1", "voter": "0xa", "vp": 1.0, "created": 1, "choice": 1},
                {"id": "v2", "voter": "0xb", "vp": 2.0, "created": 2, "choice": 1},
            ]}},
            {"data": {"votes": [
                {"id": "v3", "voter": "0xc", "vp": 3.0, "created": 3, "choice": 2},
            ]}},
        ])

        def fake_run_query(query, **kwargs):
            return next(responses_by_call)

        monkeypatch.setattr(snap, "run_query", fake_run_query)
        monkeypatch.setattr(snap.time, "sleep", lambda *_: None)

        votes = snap.fetch_snapshot_votes(proposals)

        # Total: 2 (prop-A) + 1 (prop-B) = 3
        assert len(votes) == 3
        # Every vote has proposal_id injected
        prop_a_votes = [v for v in votes if v["proposal_id"] == "prop-A"]
        prop_b_votes = [v for v in votes if v["proposal_id"] == "prop-B"]
        assert len(prop_a_votes) == 2
        assert len(prop_b_votes) == 1

    def test_no_proposals_returns_empty(self, monkeypatch):
        monkeypatch.setattr(snap, "run_query", lambda q, **k: {"data": {"votes": []}})
        monkeypatch.setattr(snap.time, "sleep", lambda *_: None)
        assert snap.fetch_snapshot_votes([]) == []
