"""
Proposal type classification utility.

This module is intentionally free of Streamlit, database, and dashboard
dependencies so that the same logic can be imported by:

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
  - proposal_category       : str       — primary semantic label (see CATEGORIES)
  - is_decentralizing_reform: bool      — H2.2 flag; proposal reduces concentration
                                          or changes voting mechanics
  - is_structural_experiment: bool      — H6.3 flag; proposal creates/modifies/
                                          dissolves delegate or working-group structures
  - reform_tags             : list[str] — all matched keyword tag names (for drill-down)

Categories
----------
  election             — steward / officer elections
  working_group_funding— routine WG quarterly budget requests
  service_provider     — SP selection, streams, SPP budgets
  treasury             — endowment, financial ops, ETH / USDC conversions
  ecosystem_protocol   — ENS protocol changes, DNS, L2, name normalisation
  structural_reform    — WG creation / dissolution / restructure
  delegate_structure   — delegate roles, compensation, incentive pilots
  meta_governance      — governance process rules, quorum, security council
  routine_executable   — on-chain execution of an already-passed proposal
  airdrop_legacy       — airdrop, retroactive distribution
  general              — catch-all

SQL migration notes
-------------------
proposal_category        → CASE expression on lower(title) keyword patterns
is_decentralizing_reform → regexp_count(lower(title || ' ' || body), pattern) > 0
is_structural_experiment → same with structural keyword set
reform_tags              → array_agg of matched tag strings (dbt Python model required
                           for full regex; pure-SQL approximation feasible for top tags)
"""

import re

import pandas as pd

# Max body words to scan — avoids false positives from long quoted sections
_BODY_WORD_LIMIT = 2000

_URL_RE   = re.compile(r"https?://\S+")
_MD_NOISE = re.compile(r"[#*_`\[\]()-]+")


# ---------------------------------------------------------------------------
# Internal helpers
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


def _match_tags(text: str, keyword_dict: dict) -> list:
    """Return tag names (keys) whose patterns match anywhere in text."""
    matched = []
    for tag, patterns in keyword_dict.items():
        for pat in patterns:
            if re.search(pat, text):
                matched.append(tag)
                break  # one match per tag is sufficient
    return matched


# ---------------------------------------------------------------------------
# Keyword dictionaries
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

# Primary category rules — first match wins; evaluated on combined title + body text
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("election",             [r"\bsteward\s+election\b", r"\bsteward\s+nomination\b",
                              r"\belect\w*\s+steward\b", r"\bappoint\w*\s+steward\b"]),
    ("routine_executable",   [r"\bexecute\s+ep\b", r"\bimplement\s+ep\b",
                              r"\bon.?chain\s+execution\b"]),
    ("service_provider",     [r"\bservice\s+provider\b", r"\bspp\s+season\b",
                              r"\brenew\s+service\b"]),
    ("working_group_funding", [r"\bfunding\s+request\b", r"\bbudget\s+request\b",
                               r"\bq[1-4]\s+\d{4}\b", r"\bwindow\s+\d+\b",
                               r"\bworking\s+group\s+fund\w*\b"]),
    ("treasury",             [r"\bendowment\b", r"\busdc\s+conversion\b",
                              r"\btreasury\b", r"\bkarpatkey\b",
                              r"\bfund\s+transfer\b", r"\btoken\s+transfer\b"]),
    ("structural_reform",    [r"\bcreate.*working\s+group\b", r"\bdissolve.*working\s+group\b",
                              r"\breplace.*working\s+group\b", r"\bworking\s+group\s+rules\b",
                              r"\badmin\s+panel\b", r"\brepeal.*working\s+group\b",
                              r"\bfoundational\s+working\s+group\b"]),
    ("delegate_structure",   [r"\bdelegation\s+incentive\b", r"\bgovernance\s+distribution\b",
                              r"\bsteward\s+compensation\b", r"\bsteward\s+vesting\b",
                              r"\bsecurity\s+council\b", r"\bpilot\s+program\b"]),
    ("ecosystem_protocol",   [r"\bname\s+normali[sz]\w+\b", r"\bdns\s+registrar\b",
                              r"\bl2\b", r"\blayer.?2\b", r"\bens\s+contract\b",
                              r"\bregistrar\b", r"\bnamechain\b"]),
    ("airdrop_legacy",       [r"\bairdrop\b", r"\bretroactive\s+distribution\b"]),
    ("meta_governance",      [r"\bproposal\s+bond\b", r"\bquorum\b", r"\bvoting\s+period\b",
                              r"\bconstitution\b", r"\bgovernance\s+process\b",
                              r"\bproposal\s+threshold\b"]),
]


def _assign_category(text: str) -> str:
    """Return the first matching category, or 'general' if none match."""
    for category, patterns in _CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, text):
                return category
    return "general"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_proposals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add classification columns to a proposals DataFrame.

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
    """
    out = df.copy()

    texts = [
        _build_text(
            row["title"] if "title" in out.columns else "",
            row["body"]  if "body"  in out.columns else "",
        )
        for _, row in out.iterrows()
    ]

    out["proposal_category"]         = [_assign_category(t) for t in texts]
    out["is_decentralizing_reform"]  = [bool(_match_tags(t, _REFORM_KEYWORDS))     for t in texts]
    out["is_structural_experiment"]  = [bool(_match_tags(t, _STRUCTURAL_KEYWORDS)) for t in texts]
    out["reform_tags"]               = [
        sorted(set(
            _match_tags(t, _REFORM_KEYWORDS) + _match_tags(t, _STRUCTURAL_KEYWORDS)
        ))
        for t in texts
    ]

    return out
