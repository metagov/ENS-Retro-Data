"""Open Source Observer (OSO) API client for ENS GitHub activity data.

Uses pyoso to query the OSO data lake via SQL.
Fetches three datasets for ENS repos (artifact_namespace = 'ensdomains'):
  - repos:          artifact registry (name, namespace, source)
  - code_metrics:   per-repo health snapshot (stars, forks, commits, PRs, issues)
  - timeseries:     daily GitHub event history (all event types)

Authentication: OSO_API_KEY environment variable, passed via OsoApiConfig resource.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def _emit(msg: str) -> None:
    """Print to stdout, stderr, and logger."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)
    logger.info(msg)

OSO_NAMESPACE = "ensdomains"
TIMESERIES_START = "2019-01-01"


def _make_client(api_key: str):
    """Instantiate a pyoso Client."""
    from pyoso import Client  # lazy import — not installed until pyproject.toml dep added

    return Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Repos
# ---------------------------------------------------------------------------


def fetch_ens_repos(api_key: str) -> list[dict]:
    """Fetch all ENS GitHub repositories registered in OSO.

    Queries artifacts_by_project_v1 for the ENS project, returning
    one row per GitHub repo.
    """
    _emit(f"[OSO] Fetching ENS repo list (artifact_namespace='{OSO_NAMESPACE}')")
    client = _make_client(api_key)
    try:
        df = client.to_pandas(f"""
            SELECT
                artifact_id,
                artifact_name,
                artifact_namespace,
                artifact_source,
                artifact_source_id,
                project_id,
                project_name,
                project_namespace,
                project_source
            FROM artifacts_by_project_v1
            WHERE artifact_namespace = '{OSO_NAMESPACE}'
              AND artifact_source = 'GITHUB'
            ORDER BY artifact_name
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching repos: {e}")
        raise
    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched {len(records)} repos")
    return records


# ---------------------------------------------------------------------------
# Code metrics
# ---------------------------------------------------------------------------


def fetch_ens_code_metrics(api_key: str) -> list[dict]:
    """Fetch per-repo code health metrics for ENS GitHub repos.

    Queries code_metrics_by_artifact_v0 for all ensdomains repos.
    Returns current snapshot: stars, forks, contributors, commit counts,
    PR counts, issue counts (6-month windows where applicable).
    """
    _emit(f"[OSO] Fetching ENS code metrics (artifact_namespace='{OSO_NAMESPACE}')")
    client = _make_client(api_key)
    try:
        df = client.to_pandas(f"""
            SELECT
                artifact_id,
                artifact_name,
                artifact_namespace,
                event_source,
                star_count,
                fork_count,
                contributor_count,
                contributor_count_6_months,
                active_developer_count_6_months,
                fulltime_developer_average_6_months,
                new_contributor_count_6_months,
                commit_count_6_months,
                merged_pull_request_count_6_months,
                opened_pull_request_count_6_months,
                opened_issue_count_6_months,
                closed_issue_count_6_months,
                first_commit_date,
                last_commit_date
            FROM code_metrics_by_artifact_v0
            WHERE artifact_namespace = '{OSO_NAMESPACE}'
            ORDER BY artifact_name
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching code metrics: {e}")
        raise
    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched code metrics for {len(records)} repos")
    return records


# ---------------------------------------------------------------------------
# Timeseries events
# ---------------------------------------------------------------------------


def fetch_ens_timeseries(api_key: str, *, since: str = TIMESERIES_START) -> list[dict]:
    """Fetch daily GitHub event history for ENS repos since a given date.

    Queries timeseries_events_by_artifact_v0 for all ensdomains artifacts.
    Returns all event types (COMMIT_CODE, PULL_REQUEST_MERGED, ISSUE_OPENED, etc.).

    Args:
        api_key: OSO API key
        since:   ISO date string (YYYY-MM-DD) — fetch events after this date.
                 Defaults to TIMESERIES_START ('2019-01-01') for first run.
    """
    _emit(f"[OSO] Fetching ENS timeseries events since {since} (namespace='{OSO_NAMESPACE}')")
    client = _make_client(api_key)
    try:
        df = client.to_pandas(f"""
            SELECT
                artifact_id,
                artifact_name,
                artifact_namespace,
                event_source,
                event_source_id,
                event_type,
                from_artifact_id,
                to_artifact_id,
                amount,
                time
            FROM timeseries_events_by_artifact_v0
            WHERE artifact_namespace = '{OSO_NAMESPACE}'
              AND time > '{since}'
            ORDER BY time DESC
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching timeseries: {e}")
        raise
    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched {len(records)} timeseries event rows (since {since})")
    return records
