"""Dagster sensors for post-materialization side effects.

vector_store_sync_sensor:
    Fires after all 5 gold assets materialise successfully in the same run.
    Re-exports gold tables to markdown and refreshes the OpenAI vector store
    so the ChatKit agent always has current data.
"""

import os
import time
import logging
from pathlib import Path

import httpx
from dagster import (
    AssetKey,
    RunStatusSensorContext,
    asset_sensor,
    DagsterRunStatus,
    RunRequest,
    SensorResult,
    sensor,
    MultiAssetSensorDefinition,
    multi_asset_sensor,
    MultiAssetSensorEvaluationContext,
    SkipReason,
)
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = logging.getLogger(__name__)

_GOLD_ASSET_KEYS = [
    AssetKey(["gold", "decentralization_index"]),
    AssetKey(["gold", "delegate_scorecard"]),
    AssetKey(["gold", "governance_activity"]),
    AssetKey(["gold", "participation_index"]),
    AssetKey(["gold", "treasury_summary"]),
]

_VS_ID = "vs_69d291d5a5fc819194838e0475405ef7"
_DB_PATH = Path(__file__).resolve().parent.parent / "warehouse" / "ens_retro.duckdb"
_EXPORT_DIR = Path(__file__).resolve().parent.parent / "DEV" / "vector-store-exports"
_IDS_FILE = _EXPORT_DIR / ".gold-file-ids"

_GOLD_TABLES = [
    "decentralization_index",
    "delegate_scorecard",
    "governance_activity",
    "participation_index",
    "treasury_summary",
]


# ---------------------------------------------------------------------------
# Vector store sync logic (same as scripts/sync_vector_store.py but inline
# so the sensor runs it in-process without a subprocess)
# ---------------------------------------------------------------------------

def _export_tables() -> list[tuple[str, Path]]:
    import duckdb
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(_DB_PATH), read_only=True)
    exported = []
    for table in _GOLD_TABLES:
        if table == "delegate_scorecard":
            df = con.execute("""
                SELECT address, name, ens_name, voting_power, delegators_count,
                       participation_rate, snapshot_votes_cast, tally_votes_cast
                FROM main_gold.delegate_scorecard
                WHERE voting_power > 0
                ORDER BY voting_power DESC
                LIMIT 500
            """).fetchdf()
            name = "gold_export__delegate_scorecard_top500.md"
        else:
            df = con.execute(f"SELECT * FROM main_gold.{table}").fetchdf()
            name = f"gold_export__{table}.md"
        path = _EXPORT_DIR / name
        df.to_markdown(str(path), index=False)
        exported.append((name, path))
        log.info("vector_store_sync: exported %s (%d rows)", name, len(df))
    con.close()
    return exported


def _delete_stale(api_key: str) -> None:
    if not _IDS_FILE.exists():
        return
    old_ids = _IDS_FILE.read_text().strip().splitlines()
    vs_headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "assistants=v2",
    }
    file_headers = {"Authorization": f"Bearer {api_key}"}
    for fid in old_ids:
        httpx.delete(f"https://api.openai.com/v1/vector_stores/{_VS_ID}/files/{fid}",
                     headers=vs_headers)
        httpx.delete(f"https://api.openai.com/v1/files/{fid}", headers=file_headers)
        log.info("vector_store_sync: deleted stale file %s", fid)


def _upload_and_attach(exports: list[tuple[str, Path]], api_key: str) -> None:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    new_ids = []
    for name, path in exports:
        with open(path, "rb") as f:
            obj = client.files.create(file=(name, f), purpose="assistants")
        new_ids.append(obj.id)
        log.info("vector_store_sync: uploaded %s → %s", name, obj.id)

    # Save IDs for next run's cleanup
    _IDS_FILE.write_text("\n".join(new_ids))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "assistants=v2",
    }
    resp = httpx.post(
        f"https://api.openai.com/v1/vector_stores/{_VS_ID}/file_batches",
        headers=headers,
        json={"file_ids": new_ids},
    )
    resp.raise_for_status()
    batch_id = resp.json()["id"]

    # Poll until complete (max 90s)
    for _ in range(30):
        time.sleep(3)
        r = httpx.get(
            f"https://api.openai.com/v1/vector_stores/{_VS_ID}/file_batches/{batch_id}",
            headers=headers,
        )
        data = r.json()
        if data["status"] in ("completed", "failed"):
            counts = data["file_counts"]
            log.info(
                "vector_store_sync: batch %s — %d completed, %d failed",
                batch_id, counts["completed"], counts["failed"],
            )
            return

    log.warning("vector_store_sync: batch %s timed out", batch_id)


def _run_sync() -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "SKIPPED: OPENAI_API_KEY not set"
    if not _DB_PATH.exists():
        return f"SKIPPED: warehouse not found at {_DB_PATH}"
    exports = _export_tables()
    _delete_stale(api_key)
    _upload_and_attach(exports, api_key)
    return f"OK: synced {len(exports)} tables to {_VS_ID}"


# ---------------------------------------------------------------------------
# Sensor definition
# ---------------------------------------------------------------------------

@multi_asset_sensor(
    monitored_assets=_GOLD_ASSET_KEYS,
    name="vector_store_sync_sensor",
    description=(
        "After all 5 gold assets materialise, re-exports them to markdown "
        "and refreshes the OpenAI vector store for the ChatKit agent."
    ),
    minimum_interval_seconds=300,  # don't fire more than once per 5 minutes
)
def vector_store_sync_sensor(context: MultiAssetSensorEvaluationContext):
    # Check that every gold asset has a new materialisation since last cursor
    asset_events = context.latest_materialization_records_by_key()

    unmaterialised = [
        str(k) for k, record in asset_events.items() if record is None
    ]
    if unmaterialised:
        return SkipReason(f"Waiting for: {', '.join(unmaterialised)}")

    # All gold assets have materialised — run the sync
    context.log.info("All gold assets materialised. Starting vector store sync...")
    result = _run_sync()
    context.log.info("vector_store_sync result: %s", result)

    # Advance cursor so we don't re-fire until the next materialisation
    context.advance_all_cursors()

    return SkipReason(f"Sync complete — {result}")
