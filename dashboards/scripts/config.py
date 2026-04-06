"""
Portal configuration loader.

Reads dashboards/config.yaml and exposes typed dataclasses for challenges,
hypotheses, and visuals. Uses importlib for lazy script resolution so that
unused visualization scripts are never imported.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import streamlit as st
import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VisualConfig:
    script: str
    fn: str
    title: str
    takeaway: str


@dataclass
class HypothesisConfig:
    id: str
    title: str
    short_title: str
    description: str
    verdict: str = ""
    visuals: list[VisualConfig] = field(default_factory=list)


@dataclass
class ChallengeConfig:
    id: str
    title: str
    short_title: str
    description: str
    doc_url: str = ""
    hypotheses: list[HypothesisConfig] = field(default_factory=list)


@dataclass
class PortalConfig:
    challenges: list[ChallengeConfig]


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _parse_config(path: Path) -> PortalConfig:
    raw = yaml.safe_load(path.read_text())
    challenges = []
    for c in raw.get("challenges", []):
        hypotheses = []
        for h in c.get("hypotheses", []):
            visuals = [
                VisualConfig(
                    script=v["script"],
                    fn=v["fn"],
                    title=v["title"],
                    takeaway=v.get("takeaway", ""),
                )
                for v in h.get("visuals", [])
            ]
            hypotheses.append(HypothesisConfig(
                id=h["id"],
                title=h["title"],
                short_title=h.get("short_title", h["id"]),
                description=h.get("description", ""),
                verdict=h.get("verdict", ""),
                visuals=visuals,
            ))
        challenges.append(ChallengeConfig(
            id=c["id"],
            title=c["title"],
            short_title=c.get("short_title", c["title"]),
            description=c.get("description", ""),
            doc_url=c.get("doc_url", ""),
            hypotheses=hypotheses,
        ))
    return PortalConfig(challenges=challenges)


_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@st.cache_resource
def load_config() -> PortalConfig:
    return _parse_config(_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Render function resolver
# ---------------------------------------------------------------------------

def resolve_render_fn(visual: VisualConfig) -> Callable[[], None]:
    """Import the script module lazily and return the named render function."""
    mod = importlib.import_module(f"scripts.{visual.script}")
    return getattr(mod, visual.fn)
