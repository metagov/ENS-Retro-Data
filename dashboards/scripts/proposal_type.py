"""
Proposal type classification utility — DAOIP-4 aligned, LLM-powered.

This module is intentionally free of Streamlit and database dependencies so
that the same logic can be imported by:

  - Dashboard scripts (current use)
  - dbt Python models (future: infra/dbt/models/silver/proposal_categories.py)
  - Unit tests

Column contract
---------------
Input DataFrame must contain:
  - proposal_id  : str
  - platform     : str  ("Snapshot" | "Tally")
  - title        : str
  - body         : str  (raw markdown proposal text; may be None / NaN)

Output adds these columns (names are stable — future silver model will match):
  - proposal_category       : str       — DAOIP-4 type string (see DAOIP4_TYPES)
  - is_decentralizing_reform: bool      — H2.2 flag; proposal caps voting power,
                                          introduces alt voting, or reduces concentration
  - is_structural_experiment: bool      — H6.3 flag; proposal creates/modifies/
                                          dissolves delegate or working-group structures
  - reform_tags             : list[str] — all matched signal tag names (for drill-down)
  - cognitive_load          : int       — H4.1: overall reading/parsing effort, 1 (easy) – 5 (very hard)
  - technical_depth         : int       — H4.1: domain expertise required, 1 (none) – 5 (deep)
  - context_dependency      : int       — H4.1: prior knowledge needed beyond this text, 1 (none) – 5 (heavy)
  - time_to_evaluate        : int       — H4.1: effort to form a well-informed opinion, 1 (<5 min) – 5 (hours)

Notes on complexity columns
---------------------------
LLM-sourced when available; falls back to rule-based derivation from word count
and keyword patterns when the anthropic package is unavailable or an API call fails.
Fallback values are NOT cached — the next run will retry the LLM.
Cache entries without all four complexity fields are treated as stale and trigger
LLM re-classification.

DAOIP-4 Category Schema
-----------------------
  treasury/grant            — one-off ecosystem / project funding
  treasury/budget           — quarterly WG budgets, service provider streams
  treasury/investment       — endowment ops, ETH/USDC conversions, karpatkey
  treasury/other            — airdrops, retroactive distributions
  protocol/major-change     — ENS contract upgrades, L2, DNS registrar, namechain
  protocol/small-change     — minor parameter tweaks, registrar adjustments
  protocol/other            — routine on-chain execution of already-passed proposals
  metagov/major-change      — WG creation/dissolution/restructure, constitution
  metagov/small-change      — quorum, voting period, proposal threshold changes
  metagov/delegate-governance — steward elections, delegate roles, compensation pilots
  metagov/other             — catch-all governance

reform_tags
-----------
Decentralization signals (→ is_decentralizing_reform):
  voting_cap, quadratic, conviction_voting, anti_concentration,
  alt_voting, governance_reform, delegation_reform, power_transfer, proposal_barrier

Structural experiment signals (→ is_structural_experiment):
  wg_creation, wg_dissolution, wg_restructure, new_delegate_mech,
  security_council, pilot_program, new_body
"""

import json
import logging
import os
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Max body words to scan — avoids false positives from long quoted sections
_BODY_WORD_LIMIT = 2000

_URL_RE   = re.compile(r"https?://\S+")
_MD_NOISE = re.compile(r"[#*_`\[\]()-]+")

# Fields that must be present in a cache entry for it to be considered current
_COMPLEXITY_FIELDS = frozenset({
    "cognitive_load", "technical_depth", "context_dependency", "time_to_evaluate",
})

_TECHNICAL_KEYWORDS = [
    r"\bsmart\s+contract\b", r"\bsolidity\b", r"\bl2\b", r"\blayer.?2\b",
    r"\bnamechain\b", r"\bregistrar\b", r"\bens\s+contract\b",
    r"\bendowment\b", r"\bkarpatkey\b", r"\busdc\s+conversion\b",
    r"\byield\s+strateg\w+\b", r"\btoken\s+swap\b",
    r"\bquadratic\b", r"\bconviction\s+voting\b", r"\bvoting\s+mechanism\b",
    r"\bconstitution\b",
]

_CONTEXT_KEYWORDS = [
    r"\bep\s*\d+\b", r"\bep[.-]\d+\b",
    r"\bdiscuss\w*\s+in\b", r"\bas\s+discussed\b",
    r"\bforum\b", r"\bdiscourse\b",
    r"\bfollowing\s+the\b", r"\bprevious\s+proposal\b",
    r"\binformal\s+agreement\b", r"\boff.?chain\b",
    r"\bsnapshot\s+vote\b", r"\bprevious\s+snapshot\b",
]

# Valid DAOIP-4 category strings
DAOIP4_TYPES = frozenset([
    "treasury/grant",
    "treasury/budget",
    "treasury/investment",
    "treasury/other",
    "protocol/major-change",
    "protocol/small-change",
    "protocol/other",
    "metagov/major-change",
    "metagov/small-change",
    "metagov/delegate-governance",
    "metagov/other",
])

# Disk cache: persists LLM results keyed by proposal_id
_CACHE_PATH = Path(__file__).parent / ".proposal_cache.json"

# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("proposal_type: cache file corrupt or unreadable — starting fresh")
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except OSError as e:
        logger.warning("proposal_type: could not write cache — %s", e)


# Module-level cache (loaded once per interpreter session)
_CACHE: dict = _load_cache()


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _build_text(title: str, body: str) -> str:
    """
    Lowercase searchable text: title repeated 2× (higher weight) + truncated body.
    URLs and markdown syntax are stripped from the body before concatenation.
    """
    t = str(title) if title else ""
    b = str(body) if body else ""
    b = _URL_RE.sub(" ", b)
    b = _MD_NOISE.sub(" ", b)
    b_words = b.split()[:_BODY_WORD_LIMIT]
    return (t + " " + t + " " + " ".join(b_words)).lower()


def _build_prompt(title: str, body: str) -> str:
    """Build the classification prompt for Claude."""
    truncated_body = " ".join(str(body).split()[:_BODY_WORD_LIMIT]) if body else ""

    return f"""You are classifying an ENS DAO governance proposal according to the DAOIP-4 taxonomy.

## DAOIP-4 Category Definitions

treasury/grant        — One-off ecosystem or project funding; a single grant to an external team or initiative
treasury/budget       — Recurring operational budget: quarterly working group budgets, service provider payment streams, season allocations
treasury/investment   — Endowment operations, ETH/USDC/stablecoin conversions, yield strategies (e.g. karpatkey), token swaps for treasury diversification
treasury/other        — Airdrops, retroactive distributions, liquidity mining, token buybacks
protocol/major-change — Significant ENS protocol changes: contract upgrades, L2 deployments, DNS registrar changes, name normalisation overhauls, namechain
protocol/small-change — Minor parameter adjustments to the protocol, small registrar tweaks, low-risk on-chain parameter changes
protocol/other        — Routine on-chain execution of a proposal that was already approved off-chain (e.g. "Execute EP X")
metagov/major-change  — Working group creation, dissolution, or restructuring; constitution amendments; significant governance overhauls; spin-outs
metagov/small-change  — Small governance parameter changes: quorum adjustments, voting period changes, proposal submission threshold changes
metagov/delegate-governance — Steward elections and nominations, delegate role definitions, compensation structures, delegate incentive pilots, security council elections
metagov/other         — Governance proposals that don't clearly fit any above category

## Attribution Flags

is_decentralizing_reform (bool):
  Set to true if the proposal explicitly aims to reduce governance concentration or change voting mechanics:
  - caps on voting power or delegate power
  - quadratic or conviction voting mechanisms
  - alternative voting mechanisms that distribute power more broadly
  - anti-whale or anti-oligarchy measures
  - governance distribution pilots
  - transfer of root key or contract ownership toward decentralization

is_structural_experiment (bool):
  Set to true if the proposal creates, modifies, or dissolves governance structures, or pilots new coordination mechanisms:
  - creating a new working group or sub-DAO
  - dissolving or winding down a working group
  - restructuring or replacing a working group
  - new delegate incentive or compensation mechanisms
  - security council establishment or reform
  - pilot programs for new governance mechanics
  - new governance bodies (e.g. service provider program)

## reform_tags

Select all applicable tags from these lists:

Decentralization tags: voting_cap, quadratic, conviction_voting, anti_concentration, alt_voting, governance_reform, delegation_reform, power_transfer, proposal_barrier

Structural tags: wg_creation, wg_dissolution, wg_restructure, new_delegate_mech, security_council, pilot_program, new_body

## Complexity Dimensions

Rate each of the following on a scale of 1 (very low) to 5 (very high):

cognitive_load: Overall mental effort to read, parse, and understand this proposal.
  1 = plain language, single topic  /  5 = dense, multi-topic, highly technical

technical_depth: Domain expertise required to evaluate this proposal.
  1 = no specialised knowledge needed  /  5 = deep protocol, financial, or governance theory

context_dependency: Prior knowledge needed beyond this text.
  1 = fully self-contained  /  5 = requires many past proposals, forum debates, informal agreements

time_to_evaluate: Estimated effort to form a well-informed opinion before voting.
  1 = under 5 minutes  /  5 = hours of research and linked document reading

## Proposal to Classify

Title: {title}

Body (truncated to {_BODY_WORD_LIMIT} words):
{truncated_body}

## Instructions

Return ONLY a JSON object with exactly these keys. No explanation, no markdown fences:

{{
  "proposal_category": "<one of the 11 DAOIP-4 type strings above>",
  "is_decentralizing_reform": <true or false>,
  "is_structural_experiment": <true or false>,
  "reform_tags": [<zero or more tag strings from the lists above>],
  "cognitive_load": <integer 1-5>,
  "technical_depth": <integer 1-5>,
  "context_dependency": <integer 1-5>,
  "time_to_evaluate": <integer 1-5>
}}"""


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------

def _classify_with_llm(proposal_id: str, title: str, body: str) -> dict | None:
    """
    Call Claude to classify a single proposal.
    Returns a dict with the four output keys, or None on failure.
    """
    try:
        import anthropic  # imported lazily — keeps module usable without the package
    except ImportError:
        logger.warning("proposal_type: 'anthropic' package not installed — using rule-based fallback")
        return None

    client = anthropic.Anthropic()
    prompt = _build_prompt(title, body)

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=384,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if model adds them despite instructions
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        # Validate and coerce
        category = result.get("proposal_category", "metagov/other")
        if category not in DAOIP4_TYPES:
            logger.warning(
                "proposal_type: LLM returned unknown category %r for %s — using metagov/other",
                category, proposal_id,
            )
            category = "metagov/other"

        return {
            "proposal_category":        category,
            "is_decentralizing_reform": bool(result.get("is_decentralizing_reform", False)),
            "is_structural_experiment": bool(result.get("is_structural_experiment", False)),
            "reform_tags":              sorted(set(result.get("reform_tags", []))),
            "cognitive_load":           _clamp_complexity(result.get("cognitive_load")),
            "technical_depth":          _clamp_complexity(result.get("technical_depth")),
            "context_dependency":       _clamp_complexity(result.get("context_dependency")),
            "time_to_evaluate":         _clamp_complexity(result.get("time_to_evaluate")),
        }

    except (json.JSONDecodeError, KeyError, IndexError, anthropic.APIError) as e:
        logger.warning("proposal_type: LLM classification failed for %s — %s", proposal_id, e)
        return None


# ---------------------------------------------------------------------------
# Rule-based fallback (DAOIP-4 mapped)
# ---------------------------------------------------------------------------

# H2.2 — decentralizing reforms
_REFORM_KEYWORDS: dict = {
    "voting_cap":         [r"\bvoting\s+cap\b", r"\bvp\s+cap\b", r"\bpower\s+cap\b"],
    "quadratic":          [r"\bquadratic\b"],
    "conviction_voting":  [r"\bconviction\s+voting\b"],
    "anti_concentration": [r"\bconcentrat\w*\b", r"\boligarch\b", r"\bwhale\b"],
    "alt_voting":         [r"\bvoting\s+mechanism\b", r"\balternative\s+vot\w+\b",
                           r"\bvoting\s+reform\b"],
    "governance_reform":  [r"\bgovernance\s+reform\b", r"\breform.*govern\w*\b"],
    "delegation_reform":  [r"\bdelegation\s+incentive\b", r"\bgovernance\s+distribution\b",
                           r"\bgovernance\s+pilot\b"],
    "power_transfer":     [r"\bdecentrali[sz]\w*\b", r"\btransfer.*ownership\b",
                           r"\broot\s+key\b"],
    "proposal_barrier":   [r"\bproposal\s+bond\b", r"\bproposal\s+threshold\b"],
}

# H6.3 — structural experiments
_STRUCTURAL_KEYWORDS: dict = {
    "wg_creation":       [r"\bcreate.*working\s+group\b", r"\bfoundational\s+working\b",
                          r"\bnew\s+working\s+group\b", r"\bestablish.*working\s+group\b"],
    "wg_dissolution":    [r"\bdissolve.*working\s+group\b", r"\bwind.*down.*working\b",
                          r"\bwind.*down.*group\b", r"\bdisband.*working\s+group\b"],
    "wg_restructure":    [r"\breplace.*working\s+group\b", r"\breplace.*\bwg\b",
                          r"\badmin\s+panel\b", r"\brepeal.*working\s+group\b",
                          r"\bamend.*working\s+group\b", r"\bworking\s+group\s+rules\b"],
    "new_delegate_mech": [r"\bdelegation\s+incentive\b", r"\bgovernance\s+distribution\b",
                          r"\bsteward\s+compensation\b", r"\bsteward\s+vesting\b"],
    "security_council":  [r"\bsecurity\s+council\b"],
    "pilot_program":     [r"\bpilot\s+program\b", r"\bpilot.*govern\w*\b",
                          r"\bexperiment.*govern\w*\b"],
    "new_body":          [r"\bservice\s+provider\s+program\b", r"\bspp\s+season\b"],
}

# Primary category rules → DAOIP-4 strings; first match wins
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("metagov/delegate-governance", [r"\bsteward\s+election\b", r"\bsteward\s+nomination\b",
                                     r"\belect\w*\s+steward\b", r"\bappoint\w*\s+steward\b"]),
    ("protocol/other",              [r"\bexecute\s+ep\b", r"\bimplement\s+ep\b",
                                     r"\bon.?chain\s+execution\b"]),
    ("treasury/budget",             [r"\bservice\s+provider\b", r"\bspp\s+season\b",
                                     r"\brenew\s+service\b"]),
    ("treasury/budget",             [r"\bfunding\s+request\b", r"\bbudget\s+request\b",
                                     r"\bq[1-4]\s+\d{4}\b", r"\bwindow\s+\d+\b",
                                     r"\bworking\s+group\s+fund\w*\b"]),
    ("treasury/investment",         [r"\bendowment\b", r"\busdc\s+conversion\b",
                                     r"\btreasury\b", r"\bkarpatkey\b",
                                     r"\bfund\s+transfer\b", r"\btoken\s+transfer\b"]),
    ("metagov/major-change",        [r"\bcreate.*working\s+group\b", r"\bdissolve.*working\s+group\b",
                                     r"\breplace.*working\s+group\b", r"\bworking\s+group\s+rules\b",
                                     r"\badmin\s+panel\b", r"\brepeal.*working\s+group\b",
                                     r"\bfoundational\s+working\s+group\b"]),
    ("metagov/delegate-governance", [r"\bdelegation\s+incentive\b", r"\bgovernance\s+distribution\b",
                                     r"\bsteward\s+compensation\b", r"\bsteward\s+vesting\b",
                                     r"\bsecurity\s+council\b", r"\bpilot\s+program\b"]),
    ("protocol/major-change",       [r"\bname\s+normali[sz]\w+\b", r"\bdns\s+registrar\b",
                                     r"\bl2\b", r"\blayer.?2\b", r"\bens\s+contract\b",
                                     r"\bregistrar\b", r"\bnamechain\b"]),
    ("treasury/other",              [r"\bairdrop\b", r"\bretroactive\s+distribution\b"]),
    ("metagov/small-change",        [r"\bproposal\s+bond\b", r"\bquorum\b", r"\bvoting\s+period\b",
                                     r"\bconstitution\b", r"\bgovernance\s+process\b",
                                     r"\bproposal\s+threshold\b"]),
]


def _match_tags(text: str, keyword_dict: dict) -> list:
    """Return tag names (keys) whose patterns match anywhere in text."""
    matched = []
    for tag, patterns in keyword_dict.items():
        for pat in patterns:
            if re.search(pat, text):
                matched.append(tag)
                break
    return matched


def _clamp_complexity(val, default: int = 3) -> int:
    """Coerce LLM complexity value to int in [1, 5]."""
    try:
        return max(1, min(5, int(val)))
    except (TypeError, ValueError):
        return default


def _complexity_fallback(title: str, body: str) -> dict:
    """Derive 1–5 complexity ratings from content signals (no LLM required)."""
    text = _build_text(title, body)
    raw  = str(body) if body else ""
    wc   = len(raw.split())
    lc   = len(_URL_RE.findall(raw))

    # cognitive_load: word count + structural density (tables, code blocks)
    cl = 1
    if wc > 300:  cl += 1
    if wc > 700:  cl += 1
    if wc > 1500: cl += 1
    if re.search(r"\|[-:]+\|", raw) or re.search(r"```", raw): cl += 1
    cl = min(cl, 5)

    # technical_depth: domain vocabulary hit count
    hits = sum(1 for p in _TECHNICAL_KEYWORDS if re.search(p, text))
    td = 1 if hits == 0 else 2 if hits == 1 else 3 if hits <= 3 else 4 if hits <= 5 else 5

    # context_dependency: references to prior context + external link density
    ctx_hits = sum(1 for p in _CONTEXT_KEYWORDS if re.search(p, text))
    cd = 1
    if ctx_hits >= 1: cd += 1
    if ctx_hits >= 3: cd += 1
    if lc >= 3:       cd += 1
    if lc >= 8:       cd += 1
    cd = min(cd, 5)

    # time_to_evaluate: composite of word count, links, technical depth
    te = 1
    if wc > 500:  te += 1
    if wc > 1200: te += 1
    if lc >= 3:   te += 1
    if td >= 4:   te += 1
    te = min(te, 5)

    return {
        "cognitive_load":    cl,
        "technical_depth":   td,
        "context_dependency": cd,
        "time_to_evaluate":  te,
    }


def _rule_based_classify(title: str, body: str) -> dict:
    """Fallback classification using keyword rules mapped to DAOIP-4 strings."""
    text = _build_text(title, body)

    category = "metagov/other"
    for cat, patterns in _CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, text):
                category = cat
                break
        else:
            continue
        break

    reform_tags = sorted(set(
        _match_tags(text, _REFORM_KEYWORDS) + _match_tags(text, _STRUCTURAL_KEYWORDS)
    ))

    cx = _complexity_fallback(title, body)
    return {
        "proposal_category":        category,
        "is_decentralizing_reform": bool(_match_tags(text, _REFORM_KEYWORDS)),
        "is_structural_experiment": bool(_match_tags(text, _STRUCTURAL_KEYWORDS)),
        "reform_tags":              reform_tags,
        **cx,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_proposals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add DAOIP-4 classification columns to a proposals DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: proposal_id, platform, title, body.
        body may be None / NaN.

    Returns
    -------
    pd.DataFrame
        Copy of df with four columns appended:
        proposal_category, is_decentralizing_reform,
        is_structural_experiment, reform_tags.

    Notes
    -----
    LLM results are cached to .proposal_cache.json (keyed by proposal_id).
    Closed proposals are immutable so cached results are permanent.
    Falls back to rule-based classification if the anthropic package is
    unavailable or an API call fails.
    """
    out = df.copy()
    cache_dirty = False

    results: list[dict] = []
    for _, row in out.iterrows():
        pid   = str(row.get("proposal_id", ""))
        title = str(row["title"]) if "title" in out.columns else ""
        body  = str(row["body"])  if "body"  in out.columns else ""

        # 1. Cache hit — only valid if entry contains all complexity fields
        cached = _CACHE.get(pid)
        if cached is not None and _COMPLEXITY_FIELDS.issubset(cached.keys()):
            results.append(cached)
            continue

        # 2. LLM
        llm_result = _classify_with_llm(pid, title, body)
        if llm_result is not None:
            _CACHE[pid] = llm_result
            cache_dirty = True
            results.append(llm_result)
            continue

        # 3. Rule-based fallback
        fallback = _rule_based_classify(title, body)
        logger.info("proposal_type: used rule-based fallback for %s", pid)
        results.append(fallback)
        # Do not cache fallback results — next run should retry LLM

    if cache_dirty:
        _save_cache(_CACHE)

    out["proposal_category"]         = [r["proposal_category"]         for r in results]
    out["is_decentralizing_reform"]  = [r["is_decentralizing_reform"]  for r in results]
    out["is_structural_experiment"]  = [r["is_structural_experiment"]  for r in results]
    out["reform_tags"]               = [r["reform_tags"]               for r in results]
    out["cognitive_load"]            = [r["cognitive_load"]            for r in results]
    out["technical_depth"]           = [r["technical_depth"]           for r in results]
    out["context_dependency"]        = [r["context_dependency"]        for r in results]
    out["time_to_evaluate"]          = [r["time_to_evaluate"]          for r in results]

    return out
