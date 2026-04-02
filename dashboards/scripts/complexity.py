"""
Proposal complexity scoring utility.

This module is intentionally free of Streamlit, database, and dashboard
dependencies so that the same logic can be imported by:

  - Dashboard scripts (current use)
  - dbt Python models (future: infra/dbt/models/silver/proposal_complexity.py)
  - Unit tests

Column contract
---------------
Input DataFrame must contain:
  - proposal_id  : str
  - platform     : str  ("Snapshot" | "Tally")
  - body         : str  (raw markdown proposal text)
  - choices      : list[str] | None  (Snapshot only; None/NaN for Tally)

Output adds these columns (names are stable — future silver model will match):
  - word_count        : int    — whitespace-split token count after stripping markdown
  - link_count        : int    — number of http/https URLs in body
  - choice_count      : int    — len(choices); 0 for Tally proposals
  - fk_grade          : float  — Flesch-Kincaid Grade Level (higher = harder to read)
  - complexity_score  : float  — min-max normalised composite, range [0, 1]

SQL migration notes
-------------------
word_count  → array_length(str_split(regexp_replace(body, '[#*_`\\[\\]()]', ' '), ' '))
link_count  → regexp_count(body, 'https?://')
choice_count→ array_length(choices)   -- Snapshot only; 0 for Tally
fk_grade    → not SQL-expressible; requires dbt Python model
complexity_score → derived from above columns after normalisation
"""

import re

import numpy as np
import pandas as pd

try:
    # Ensure NLTK cmudict is available (textstat dependency); bypass SSL on macOS.
    import ssl
    import nltk
    _ssl_ctx = ssl._create_default_https_context
    ssl._create_default_https_context = ssl._create_unverified_context
    nltk.download("cmudict", quiet=True)
    ssl._create_default_https_context = _ssl_ctx

    import textstat
    _TEXTSTAT_AVAILABLE = True
except Exception:  # pragma: no cover
    _TEXTSTAT_AVAILABLE = False

_MD_STRIP = re.compile(r"[#*_`\[\]()\-]+")
_URL_RE   = re.compile(r"https?://\S+")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_markdown(text: str) -> str:
    """Remove common markdown syntax before readability scoring."""
    text = _URL_RE.sub(" ", text)          # strip URLs first
    text = _MD_STRIP.sub(" ", text)
    return " ".join(text.split())          # normalise whitespace


def _word_count(text: str) -> int:
    return len(_strip_markdown(text).split())


def _link_count(text: str) -> int:
    return len(_URL_RE.findall(text))


def _choice_count(choices) -> int:
    """Safe len() for choices — handles list, ndarray, None, and NaN."""
    if choices is None:
        return 0
    try:
        if pd.isna(choices):
            return 0
    except (TypeError, ValueError):
        pass
    return len(choices)


def _fk_grade(text: str) -> float:
    """Flesch-Kincaid Grade Level on stripped text. Returns NaN if textstat unavailable."""
    if not _TEXTSTAT_AVAILABLE:
        return float("nan")
    clean = _strip_markdown(text)
    if not clean.strip():
        return float("nan")
    return textstat.flesch_kincaid_grade(clean)


def _normalise(series: pd.Series) -> pd.Series:
    """Min-max normalise a series; returns 0 if all values identical."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (series - mn) / (mx - mn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_proposals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add complexity columns to a proposals DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: proposal_id, platform, body, choices.
        `choices` may be None / NaN for Tally rows.

    Returns
    -------
    pd.DataFrame
        Original DataFrame with complexity columns appended (copy).
    """
    out = df.copy()
    body = out["body"].fillna("")

    out["word_count"]   = body.map(_word_count)
    out["link_count"]   = body.map(_link_count)
    out["choice_count"] = out["choices"].map(_choice_count) if "choices" in out.columns else 0
    out["fk_grade"]     = body.map(_fk_grade)

    # Composite score: normalise each component then average
    # fk_grade excluded from composite when unavailable
    components = [
        _normalise(out["word_count"]),
        _normalise(out["link_count"]),
    ]
    if _TEXTSTAT_AVAILABLE:
        fk_filled = out["fk_grade"].fillna(out["fk_grade"].median())
        components.append(_normalise(fk_filled))

    out["complexity_score"] = np.mean(components, axis=0)

    return out
