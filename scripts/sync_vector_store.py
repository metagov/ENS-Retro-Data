"""Sync DuckDB gold tables to the OpenAI vector store.

Run this after any Dagster pipeline run that materialises gold assets.
It re-exports all gold tables to markdown, deletes the stale files from
the vector store, and uploads fresh ones.

Usage:
    python3 scripts/sync_vector_store.py

Hook into Dagster by adding a sensor or run-success hook in infra/.
"""

import os
import sys
import time
import httpx
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
VS_ID = "vs_69d291d5a5fc819194838e0475405ef7"
DB_PATH = Path(__file__).parent.parent / "warehouse" / "ens_retro.duckdb"
EXPORT_DIR = Path(__file__).parent.parent / "DEV" / "vector-store-exports"

GOLD_TABLES = [
    "delegate_scorecard",
    "governance_activity",
    "decentralization_index",
    "participation_index",
    "treasury_summary",
]

# Tag used to identify auto-generated files so we only delete ours, not
# the static Phase 1 docs or schema report.
FILE_TAG_PREFIX = "gold_export__"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
    "OpenAI-Beta": "assistants=v2",
}


def export_tables() -> list[tuple[str, Path]]:
    """Export gold tables to markdown. Returns list of (filename, path)."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    exported = []

    for table in GOLD_TABLES:
        if table == "delegate_scorecard":
            # Top 500 only — full 37k rows is too noisy for semantic search
            df = con.execute("""
                SELECT address, name, ens_name, voting_power, delegators_count,
                       participation_rate, snapshot_votes_cast, tally_votes_cast
                FROM main_gold.delegate_scorecard
                WHERE voting_power > 0
                ORDER BY voting_power DESC
                LIMIT 500
            """).fetchdf()
            name = f"{FILE_TAG_PREFIX}delegate_scorecard_top500.md"
        else:
            df = con.execute(f"SELECT * FROM main_gold.{table}").fetchdf()
            name = f"{FILE_TAG_PREFIX}{table}.md"

        path = EXPORT_DIR / name
        df.to_markdown(str(path), index=False)
        row_count = len(df)
        print(f"  Exported {table}: {row_count} rows → {name}")
        exported.append((name, path))

    con.close()
    return exported


def list_vs_files() -> list[dict]:
    """Return all files currently in the vector store."""
    resp = httpx.get(
        f"https://api.openai.com/v1/vector_stores/{VS_ID}/files?limit=100",
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def delete_stale_exports(vs_files: list[dict]) -> None:
    """Delete auto-generated gold export files from the vector store."""
    stale = [
        f for f in vs_files
        # We can't filter by filename via API — filter by checking our known file IDs
        # stored in the tag file, or by deleting all and re-uploading.
        # Simplest: delete files whose purpose is assistants and were uploaded by this script.
        # We track them in .vector-store-file-ids
    ]
    ids_file = EXPORT_DIR / ".gold-file-ids"
    if not ids_file.exists():
        print("  No previous export file IDs found — skipping delete.")
        return

    old_ids = ids_file.read_text().strip().splitlines()
    for file_id in old_ids:
        # Remove from vector store
        r = httpx.delete(
            f"https://api.openai.com/v1/vector_stores/{VS_ID}/files/{file_id}",
            headers=HEADERS,
        )
        # Delete the file object itself
        httpx.delete(
            f"https://api.openai.com/v1/files/{file_id}",
            headers={k: v for k, v in HEADERS.items() if k != "OpenAI-Beta"},
        )
        print(f"  Deleted stale file {file_id} ({r.status_code})")


def upload_files(exports: list[tuple[str, Path]]) -> list[str]:
    """Upload markdown files to OpenAI and return file IDs."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    ids = []
    for name, path in exports:
        with open(path, "rb") as f:
            obj = client.files.create(file=(name, f), purpose="assistants")
        ids.append(obj.id)
        print(f"  Uploaded {name} → {obj.id}")
    return ids


def attach_to_vector_store(file_ids: list[str]) -> None:
    """Attach uploaded files to the vector store and wait for completion."""
    resp = httpx.post(
        f"https://api.openai.com/v1/vector_stores/{VS_ID}/file_batches",
        headers=HEADERS,
        json={"file_ids": file_ids},
    )
    resp.raise_for_status()
    batch = resp.json()
    batch_id = batch["id"]
    print(f"  Batch {batch_id} created — polling for completion...")

    for _ in range(30):
        time.sleep(3)
        r = httpx.get(
            f"https://api.openai.com/v1/vector_stores/{VS_ID}/file_batches/{batch_id}",
            headers=HEADERS,
        )
        data = r.json()
        counts = data["file_counts"]
        if data["status"] == "completed":
            print(f"  ✅ Done: {counts['completed']} completed, {counts['failed']} failed")
            return
        if data["status"] == "failed":
            print(f"  ❌ Batch failed: {counts}")
            return
        print(f"  ... {counts['in_progress']} in progress")

    print("  ⚠️  Timed out waiting for batch completion")


def save_file_ids(file_ids: list[str]) -> None:
    ids_file = EXPORT_DIR / ".gold-file-ids"
    ids_file.write_text("\n".join(file_ids))


def main():
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    print(f"Vector store: {VS_ID}")
    print(f"Database: {DB_PATH}")
    print()

    print("1. Exporting gold tables...")
    exports = export_tables()

    print("\n2. Removing stale gold exports from vector store...")
    vs_files = list_vs_files()
    delete_stale_exports(vs_files)

    print("\n3. Uploading fresh exports...")
    new_ids = upload_files(exports)
    save_file_ids(new_ids)

    print("\n4. Attaching to vector store...")
    attach_to_vector_store(new_ids)

    print("\nDone. Vector store is up to date.")


if __name__ == "__main__":
    main()
