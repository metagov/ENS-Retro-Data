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
    """Fetch periodic GitHub metric history for ENS repos since a given date.

    Queries timeseries_metrics_by_artifact_v0 joined with metrics_v0 and
    artifacts_v1. Returns one row per (artifact, metric_type, sample_date).

    Args:
        api_key: OSO API key
        since:   ISO date string (YYYY-MM-DD) — fetch rows after this date.
                 Defaults to TIMESERIES_START ('2019-01-01') for first run.
    """
    _emit(f"[OSO] Fetching ENS timeseries metrics since {since} (namespace='{OSO_NAMESPACE}')")
    import pandas as pd
    client = _make_client(api_key)

    # Step 1: resolve artifact IDs for ensdomains (small, fast query)
    df_arts = client.to_pandas(f"""
        SELECT artifact_id, artifact_name, artifact_namespace
        FROM artifacts_v1
        WHERE artifact_namespace = '{OSO_NAMESPACE}'
    """)
    if df_arts.empty:
        _emit("[OSO] No ENS artifacts found — skipping timeseries")
        return []

    artifact_ids = df_arts["artifact_id"].tolist()
    _emit(f"[OSO] Fetching timeseries for {len(artifact_ids)} artifacts in batches of 20")

    # Step 2: fetch metric lookup table locally (tiny table, fast)
    df_metrics = client.to_pandas("""
        SELECT metric_id, metric_name AS event_type, metric_source AS event_source
        FROM metrics_v0
        WHERE metric_event_source = 'GITHUB'
    """)
    github_metric_ids_sql = ", ".join(f"'{mid}'" for mid in df_metrics["metric_id"].tolist())

    # Step 3: batch by artifact ID (20 at a time) — no JOIN, just filter
    BATCH = 20
    chunks = []
    for i in range(0, len(artifact_ids), BATCH):
        batch = artifact_ids[i : i + BATCH]
        ids_sql = ", ".join(f"'{aid}'" for aid in batch)
        try:
            df_batch = client.to_pandas(f"""
                SELECT artifact_id, metric_id, sample_date AS event_time, amount
                FROM timeseries_metrics_by_artifact_v0
                WHERE artifact_id IN ({ids_sql})
                  AND metric_id IN ({github_metric_ids_sql})
                  AND sample_date >= DATE '{since}'
            """)
            chunks.append(df_batch)
            _emit(f"[OSO]   batch {i//BATCH + 1}: {len(df_batch)} rows")
        except Exception as e:
            _emit(f"[OSO]   batch {i//BATCH + 1} ERROR: {e} — skipping")

    if not chunks:
        _emit("[OSO] All timeseries batches failed")
        return []

    df_ts = pd.concat(chunks, ignore_index=True)

    # Step 4: join metric names and artifact metadata locally (fast pandas merges)
    df = df_ts.merge(df_metrics, on="metric_id", how="left")
    df = df.merge(df_arts[["artifact_id", "artifact_name", "artifact_namespace"]], on="artifact_id", how="left")
    df = df.drop(columns=["metric_id"])

    records = df.to_dict(orient="records")
    _emit(f"[OSO] ✓ Fetched {len(records)} timeseries rows total (since {since})")
    return records
