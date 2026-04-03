"""Open Source Observer (OSO) API client for ENS GitHub activity data.

Uses pyoso to query the OSO data lake via SQL.
Fetches three datasets for ENS repos (artifact_namespace = 'ensdomains'):
  - repos:          artifact registry (name, namespace, source)
  - code_metrics:   per-repo health snapshot (stars, forks, commits, PRs, issues)
  - timeseries:     periodic GitHub metrics history (all metric types)

OSO table versions used (as of 2026-04):
  - artifacts_v1
  - repositories_v0        (star_count, fork_count, language, created_at, updated_at)
  - key_metrics_by_artifact_v0   (all-time aggregate snapshots per metric)
  - timeseries_metrics_by_artifact_v0  (periodic timeseries per metric)
  - metrics_v0             (metric_id → metric_name lookup)

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

    Combines:
      - repositories_v0: star_count, fork_count, language, created_at, updated_at
      - key_metrics_by_artifact_v0 + metrics_v0: contributor/commit/PR/issue counts

    Returns a wide-format list of dicts — one per artifact.
    """
    _emit(f"[OSO] Fetching ENS code metrics (artifact_namespace='{OSO_NAMESPACE}')")
    client = _make_client(api_key)

    # Base: repo metadata with star/fork counts (dedup artifact_id)
    try:
        df_repos = client.to_pandas(f"""
            SELECT
                a.artifact_id,
                a.artifact_name,
                a.artifact_namespace,
                MAX(r.star_count)  AS star_count,
                MAX(r.fork_count)  AS fork_count,
                MAX(r.language)    AS language,
                MIN(r.created_at)  AS first_commit_date,
                MAX(r.updated_at)  AS last_commit_date
            FROM artifacts_v1 a
            JOIN repositories_v0 r ON r.artifact_id = a.artifact_id
            WHERE a.artifact_namespace = '{OSO_NAMESPACE}'
            GROUP BY a.artifact_id, a.artifact_name, a.artifact_namespace
            ORDER BY a.artifact_name
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching repo metadata: {e}")
        raise

    # Key aggregate metrics per artifact (all-time snapshots)
    METRIC_MAP = {
        "GITHUB_contributors_over_all_time":       "contributor_count",
        "GITHUB_commits_over_all_time":            "commit_count",
        "GITHUB_merged_pull_requests_over_all_time": "merged_pull_request_count",
        "GITHUB_opened_pull_requests_over_all_time": "opened_pull_request_count",
        "GITHUB_opened_issues_over_all_time":      "opened_issue_count",
        "GITHUB_closed_issues_over_all_time":      "closed_issue_count",
    }
    metric_names_sql = ", ".join(f"'{n}'" for n in METRIC_MAP)

    try:
        df_metrics = client.to_pandas(f"""
            SELECT
                k.artifact_id,
                m.metric_name,
                k.amount
            FROM key_metrics_by_artifact_v0 k
            JOIN metrics_v0 m ON m.metric_id = k.metric_id
            JOIN artifacts_v1 a ON a.artifact_id = k.artifact_id
            WHERE a.artifact_namespace = '{OSO_NAMESPACE}'
              AND m.metric_name IN ({metric_names_sql})
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching key metrics: {e}")
        raise

    # Pivot metrics wide and merge with repo metadata
    if not df_metrics.empty:
        import pandas as pd
        pivot = df_metrics.pivot_table(
            index="artifact_id", columns="metric_name", values="amount", aggfunc="max"
        ).reset_index()
        pivot.columns.name = None
        pivot = pivot.rename(columns=METRIC_MAP)
        df = df_repos.merge(pivot, on="artifact_id", how="left")
    else:
        df = df_repos
        for col in METRIC_MAP.values():
            df[col] = None

    df["event_source"] = "GITHUB"

    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched code metrics for {len(records)} repos")
    return records


# ---------------------------------------------------------------------------
# Timeseries events
# ---------------------------------------------------------------------------


def fetch_ens_timeseries(api_key: str, *, since: str = TIMESERIES_START) -> list[dict]:
    """Fetch activity metric snapshot for ENS repos from OSO.

    NOTE: OSO's timeseries_metrics_by_artifact_v0 exceeds the query stage
    limit (183 > 150) for any filter combination and cannot be queried.
    This function uses key_metrics_by_artifact_v0 instead, which returns
    the most recent snapshot of weekly/monthly activity metrics per repo.
    It is not a true time series — sample_date reflects the OSO refresh date.

    Args:
        api_key: OSO API key
        since:   unused (kept for API compatibility)
    """
    _emit(f"[OSO] Fetching ENS activity metrics snapshot (namespace='{OSO_NAMESPACE}')")
    import pandas as pd
    client = _make_client(api_key)

    # Step 1: resolve artifact IDs for ensdomains
    df_arts = client.to_pandas(f"""
        SELECT artifact_id, artifact_name, artifact_namespace
        FROM artifacts_v1
        WHERE artifact_namespace = '{OSO_NAMESPACE}'
    """)
    if df_arts.empty:
        _emit("[OSO] No ENS artifacts found — skipping")
        return []

    # Step 2: fetch key activity metrics (all-time aggregates — only variant in key_metrics table)
    ACTIVITY_METRICS = (
        "GITHUB_commits_over_all_time",
        "GITHUB_contributors_over_all_time",
        "GITHUB_merged_pull_requests_over_all_time",
        "GITHUB_opened_pull_requests_over_all_time",
        "GITHUB_opened_issues_over_all_time",
        "GITHUB_closed_issues_over_all_time",
        "GITHUB_stars_over_all_time",
        "GITHUB_forks_over_all_time",
        "GITHUB_comments_over_all_time",
        "GITHUB_releases_over_all_time",
        "GITHUB_first_time_contributor_over_all_time",
    )
    names_sql = ", ".join(f"'{n}'" for n in ACTIVITY_METRICS)
    df_metrics = client.to_pandas(f"""
        SELECT metric_id, metric_name AS event_type, metric_source AS event_source
        FROM metrics_v0
        WHERE metric_name IN ({names_sql})
    """)
    if df_metrics.empty:
        _emit("[OSO] No matching metric IDs — skipping")
        return []

    # Step 3: join artifacts_v1 by namespace (avoids large artifact_id IN clause)
    try:
        df_km = client.to_pandas(f"""
            SELECT k.artifact_id, k.metric_id, k.sample_date AS event_time, k.amount
            FROM key_metrics_by_artifact_v0 k
            JOIN metrics_v0 m ON m.metric_id = k.metric_id
            JOIN artifacts_v1 a ON a.artifact_id = k.artifact_id
            WHERE a.artifact_namespace = '{OSO_NAMESPACE}'
              AND m.metric_name IN ({names_sql})
        """)
    except Exception as e:
        _emit(f"[OSO] ERROR fetching activity metrics: {e}")
        raise

    # Step 4: join metric and artifact metadata locally
    df = df_km.merge(df_metrics, on="metric_id", how="left")
    df = df.merge(df_arts[["artifact_id", "artifact_name", "artifact_namespace"]], on="artifact_id", how="left")
    df = df.drop(columns=["metric_id"])

    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched {len(records)} activity metric rows")
    return records
