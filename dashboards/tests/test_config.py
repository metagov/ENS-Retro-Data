"""Tests for the config.yaml parser (scripts/config.py).

These tests run against the actual config.yaml file and against synthetic
YAML strings to validate parsing logic and error behaviour.
"""

import textwrap
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers — parse config from a YAML string without hitting the filesystem
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import _parse_config, VisualConfig, HypothesisConfig, ChallengeConfig


def _write_tmp_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Happy-path: real config.yaml
# ---------------------------------------------------------------------------

_REAL_CONFIG = Path(__file__).parent.parent / "config.yaml"


def test_real_config_loads():
    cfg = _parse_config(_REAL_CONFIG)
    assert len(cfg.challenges) > 0


def test_real_config_all_challenges_have_id_and_title():
    cfg = _parse_config(_REAL_CONFIG)
    for c in cfg.challenges:
        assert c.id, f"Challenge missing id: {c}"
        assert c.title, f"Challenge missing title: {c}"


def test_real_config_all_hypotheses_have_id():
    cfg = _parse_config(_REAL_CONFIG)
    for c in cfg.challenges:
        for h in c.hypotheses:
            assert h.id, f"Hypothesis missing id in challenge {c.id}"


def test_real_config_visuals_have_script_and_fn():
    cfg = _parse_config(_REAL_CONFIG)
    for c in cfg.challenges:
        for h in c.hypotheses:
            for v in h.visuals:
                assert v.script, f"Visual missing script in {h.id}"
                assert v.fn, f"Visual missing fn in {h.id}"


# ---------------------------------------------------------------------------
# Empty visuals list → no crash, empty list
# ---------------------------------------------------------------------------

def test_empty_visuals_list(tmp_path):
    cfg_path = _write_tmp_config(tmp_path, """
        challenges:
          - id: "C1"
            title: "Test Challenge"
            short_title: "Test"
            description: "desc"
            hypotheses:
              - id: "H1.1"
                title: "A hypothesis"
                short_title: "A hyp"
                description: "desc"
                visuals: []
    """)
    cfg = _parse_config(cfg_path)
    assert cfg.challenges[0].hypotheses[0].visuals == []


# ---------------------------------------------------------------------------
# Takeaway defaults to empty string when not specified
# ---------------------------------------------------------------------------

def test_visual_takeaway_defaults_to_empty(tmp_path):
    cfg_path = _write_tmp_config(tmp_path, """
        challenges:
          - id: "C1"
            title: "Test Challenge"
            short_title: "Test"
            description: "desc"
            hypotheses:
              - id: "H1.1"
                title: "A hypothesis"
                short_title: "A hyp"
                description: "desc"
                visuals:
                  - script: "my_script"
                    fn: "render_fn"
                    title: "Chart title"
    """)
    cfg = _parse_config(cfg_path)
    assert cfg.challenges[0].hypotheses[0].visuals[0].takeaway == ""


# ---------------------------------------------------------------------------
# Missing required key → raises KeyError (not a silent None)
# ---------------------------------------------------------------------------

def test_missing_visual_script_key_raises(tmp_path):
    cfg_path = _write_tmp_config(tmp_path, """
        challenges:
          - id: "C1"
            title: "Test Challenge"
            short_title: "Test"
            description: "desc"
            hypotheses:
              - id: "H1.1"
                title: "A hypothesis"
                short_title: "A hyp"
                description: "desc"
                visuals:
                  - fn: "render_fn"
                    title: "No script key"
    """)
    with pytest.raises(KeyError):
        _parse_config(cfg_path)


def test_missing_visual_fn_key_raises(tmp_path):
    cfg_path = _write_tmp_config(tmp_path, """
        challenges:
          - id: "C1"
            title: "Test Challenge"
            short_title: "Test"
            description: "desc"
            hypotheses:
              - id: "H1.1"
                title: "A hypothesis"
                short_title: "A hyp"
                description: "desc"
                visuals:
                  - script: "my_script"
                    title: "No fn key"
    """)
    with pytest.raises(KeyError):
        _parse_config(cfg_path)


# ---------------------------------------------------------------------------
# Correct number of challenges and hypotheses parsed from real config
# ---------------------------------------------------------------------------

def test_real_config_challenge_count():
    cfg = _parse_config(_REAL_CONFIG)
    # C1–C4 are defined in config.yaml (C5 is commented out)
    assert len(cfg.challenges) == 4


def test_real_config_hypothesis_ids_are_unique():
    cfg = _parse_config(_REAL_CONFIG)
    ids = [h.id for c in cfg.challenges for h in c.hypotheses]
    assert len(ids) == len(set(ids)), "Duplicate hypothesis IDs found"
