"""Shared pytest fixtures for the infra/ test suite.

Tests live at the repo root (tests/) and import from the infra package
directly. The infra package is installable via pyproject.toml so no
sys.path manipulation is needed when running pytest from the repo root.

Run with:
    uv run pytest tests/ -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture()
def tmp_bronze(tmp_path, monkeypatch) -> Path:
    """Create a temp bronze/ tree and patch infra.validate.checks.BRONZE_ROOT.

    Returns the temp bronze root so tests can write fixture files into it.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()

    # Patch the BRONZE_ROOT constant in checks.py
    import infra.validate.checks as checks_mod
    monkeypatch.setattr(checks_mod, "BRONZE_ROOT", bronze)
    return bronze


@pytest.fixture()
def write_bronze_json(tmp_bronze):
    """Helper that writes a JSON file under tmp_bronze and returns its path."""
    def _write(subdir: str, filename: str, data: list | dict) -> Path:
        sub = tmp_bronze / subdir
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / filename
        with open(path, "w") as f:
            json.dump(data, f)
        return path
    return _write


# ---------------------------------------------------------------------------
# Sample raw API response fixtures (used by ingest tests)
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_tally_proposal() -> dict:
    """One raw Tally proposal in the shape returned by their GraphQL API."""
    return {
        "id": "tally-prop-001",
        "onchainId": "0xabc123",
        "status": "executed",
        "quorum": "1000000",
        "metadata": {
            "title": "EP 1.1: Sample proposal",
            "description": "A test proposal description with **markdown**.",
            "eta": "2026-01-15T00:00:00Z",
            "discourseURL": "https://discuss.ens.domains/t/test/1",
            "snapshotURL": "",
        },
        "proposer": {
            "address": "0x1111111111111111111111111111111111111111",
            "name": "Test Proposer",
            "ens": "test.eth",
        },
        "voteStats": [
            {"type": "for",     "votesCount": "1000000000000000000000000", "votersCount": 50, "percent": 80.0},
            {"type": "against", "votesCount":  "200000000000000000000000", "votersCount": 10, "percent": 16.0},
            {"type": "abstain", "votesCount":   "50000000000000000000000", "votersCount":  5, "percent":  4.0},
        ],
        "start":      {"number": 18000000, "timestamp": "2026-01-01T00:00:00Z"},
        "end":        {"number": 18050000, "timestamp": "2026-01-08T00:00:00Z"},
        "block":      {"number": 18055000, "timestamp": "2026-01-09T00:00:00Z"},
        "governor":     {"id": "gov-1",  "name": "ENS Governor"},
        "organization": {"id": "org-1", "name": "ENS"},
    }


@pytest.fixture()
def sample_tally_vote() -> dict:
    """One raw Tally vote in the shape returned by their GraphQL API."""
    return {
        "id": "tally-vote-001",
        "type": "1",  # 1=for, 2=against, 3=abstain
        "amount": "500000000000000000000000",
        "reason": "I support this proposal.",
        "txHash": "0xdef456",
        "chainId": "eip155:1",
        "voter": {
            "address": "0x2222222222222222222222222222222222222222",
            "name": "Voter A",
            "ens": "voter-a.eth",
        },
        "proposal": {"id": "tally-prop-001"},
        "block": {"number": 18030000, "timestamp": "2026-01-05T00:00:00Z"},
    }


@pytest.fixture()
def sample_tally_delegate() -> dict:
    """One raw Tally delegate in the shape returned by their GraphQL API."""
    return {
        "id": "tally-del-001",
        "votesCount": "5000000000000000000000000",
        "delegatorsCount": 12,
        "isPrioritized": False,
        "chainId": "eip155:1",
        "account": {
            "address": "0x3333333333333333333333333333333333333333",
            "name": "Delegate One",
            "ens": "delegate1.eth",
            "twitter": "delegate1",
            "bio": "I delegate.",
            "picture": "https://example.com/d1.png",
            "type": "EOA",
        },
        "statement": {
            "statement": "My governance philosophy.",
            "statementSummary": "Pragmatic.",
            "isSeekingDelegation": True,
        },
        "token": {"symbol": "ENS", "name": "Ethereum Name Service"},
        "organization": {"id": "org-1", "name": "ENS"},
        "participation": {
            "stats": {
                "voteCount": 40,
                "participationRate": 0.85,
                "proposalCount": 50,
            }
        },
    }


@pytest.fixture()
def sample_snapshot_proposal() -> dict:
    """One raw Snapshot proposal."""
    return {
        "id": "0xabc123def456",
        "title": "[EP 5.1] Test proposal",
        "body": "A markdown body.",
        "choices": ["For", "Against", "Abstain"],
        "start": 1735689600,
        "end": 1736294400,
        "snapshot": "18000000",
        "state": "closed",
        "author": "0x4444444444444444444444444444444444444444",
        "created": 1735689500,
        "scores": [80.0, 15.0, 5.0],
        "scores_total": 100.0,
        "votes": 65,
        "quorum": 1.0,
        "type": "single-choice",
    }
