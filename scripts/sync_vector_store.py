"""Sync gold tables + docs to the OpenAI vector store.

Run this after any Dagster pipeline run that materialises gold assets,
or after updating docs/. It:

1. Exports all gold tables to markdown (top-500 for delegate_scorecard)
2. Collects docs/ markdown files for the chatbot's knowledge base
3. Deletes previously-uploaded auto-generated files from the vector store
4. Uploads fresh files and attaches them to the vector store

Static files (Phase 1 research PDFs, kickoff materials) are uploaded
separately via the OpenAI dashboard and are NOT touched by this script.

Usage:
    python3 scripts/sync_vector_store.py

Hook into Dagster via the vector_store_sync_sensor in infra/sensors.py.
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
DOCS_DIR = Path(__file__).parent.parent / "docs"
REPO_ROOT = Path(__file__).parent.parent

GOLD_TABLES = [
    "delegate_scorecard",
    "governance_activity",
    "governance_discourse_activity",
    "decentralization_index",
    "participation_index",
    "treasury_summary",
]

# Prefix used to identify auto-generated files so we only delete ours,
# not the static Phase 1 docs uploaded via the OpenAI dashboard.
AUTO_TAG = "auto__"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
    "OpenAI-Beta": "assistants=v2",
}


# ---------------------------------------------------------------------------
# 1. Export gold tables to markdown
# ---------------------------------------------------------------------------

def export_gold_tables() -> list[tuple[str, Path]]:
    """Export gold tables to markdown. Returns list of (vs_filename, local_path)."""
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
        else:
            df = con.execute(f"SELECT * FROM main_gold.{table}").fetchdf()

        vs_name = f"{AUTO_TAG}gold_{table}.md"
        local_path = EXPORT_DIR / vs_name
        df.to_markdown(str(local_path), index=False)
        row_count = len(df)
        print(f"  Gold: {table} ({row_count} rows) → {vs_name}")
        exported.append((vs_name, local_path))

    con.close()
    return exported


# ---------------------------------------------------------------------------
# 2. Collect docs/ files for upload
# ---------------------------------------------------------------------------

def collect_docs() -> list[tuple[str, Path]]:
    """Collect markdown files from docs/ for vector store upload.

    Skips PDFs and binary files (those are uploaded manually via the
    OpenAI dashboard as static research docs).
    """
    collected = []

    # Developer docs
    dev_docs = DOCS_DIR / "developer-docs"
    if dev_docs.exists():
        for md in sorted(dev_docs.glob("*.md")):
            vs_name = f"{AUTO_TAG}docs_devdocs_{md.name}"
            collected.append((vs_name, md))
            print(f"  Doc:  developer-docs/{md.name} → {vs_name}")

    # Schema report
    schema_report = DOCS_DIR / "schema-report.md"
    if schema_report.exists():
        vs_name = f"{AUTO_TAG}docs_schema-report.md"
        collected.append((vs_name, schema_report))
        print(f"  Doc:  schema-report.md → {vs_name}")

    # Lighthouse ledger analysis reports
    ledger_dir = DOCS_DIR / "references" / "lighthouse-ledger-analysis" / "reports"
    if ledger_dir.exists():
        for md in sorted(ledger_dir.glob("*.md")):
            vs_name = f"{AUTO_TAG}docs_ledger_{md.name}"
            collected.append((vs_name, md))
            print(f"  Doc:  ledger/{md.name} → {vs_name}")

    # Dashboard config (challenges + hypotheses) — uploaded as .md so
    # OpenAI's vector store accepts it (YAML is not a supported file type)
    config_yaml = REPO_ROOT / "dashboards" / "config.yaml"
    if config_yaml.exists():
        vs_name = f"{AUTO_TAG}config_challenges.md"
        collected.append((vs_name, config_yaml))
        print(f"  Config: config.yaml → {vs_name}")

    # taxonomy.yaml — same .md extension workaround
    taxonomy = REPO_ROOT / "taxonomy.yaml"
    if taxonomy.exists():
        vs_name = f"{AUTO_TAG}taxonomy.md"
        collected.append((vs_name, taxonomy))
        print(f"  Config: taxonomy.yaml → {vs_name}")

    return collected


# ---------------------------------------------------------------------------
# 3. Vector store file management
# ---------------------------------------------------------------------------

def list_vs_files() -> list[dict]:
    """Return all files currently in the vector store."""
    resp = httpx.get(
        f"https://api.openai.com/v1/vector_stores/{VS_ID}/files?limit=100",
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def delete_auto_files() -> None:
    """Delete previously auto-uploaded files (identified by the .auto-file-ids tracker)."""
    ids_file = EXPORT_DIR / ".auto-file-ids"
    if not ids_file.exists():
        print("  No previous auto-file IDs found — skipping delete.")
        return

    old_ids = [line.strip() for line in ids_file.read_text().strip().splitlines() if line.strip()]
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
        status = "ok" if r.status_code in (200, 204) else f"warn:{r.status_code}"
        print(f"  Deleted {file_id} ({status})")

    ids_file.unlink(missing_ok=True)


def upload_files(files: list[tuple[str, Path]]) -> list[str]:
    """Upload files to OpenAI and return file IDs."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    ids = []
    for vs_name, local_path in files:
        with open(local_path, "rb") as f:
            obj = client.files.create(file=(vs_name, f), purpose="assistants")
        ids.append(obj.id)
        print(f"  Uploaded {vs_name} → {obj.id}")
    return ids


def attach_to_vector_store(file_ids: list[str]) -> None:
    """Attach uploaded files to the vector store and wait for completion."""
    if not file_ids:
        print("  No files to attach.")
        return

    resp = httpx.post(
        f"https://api.openai.com/v1/vector_stores/{VS_ID}/file_batches",
        headers=HEADERS,
        json={"file_ids": file_ids},
    )
    resp.raise_for_status()
    batch = resp.json()
    batch_id = batch["id"]
    print(f"  Batch {batch_id} created — polling for completion...")

    for _ in range(60):
        time.sleep(3)
        r = httpx.get(
            f"https://api.openai.com/v1/vector_stores/{VS_ID}/file_batches/{batch_id}",
            headers=HEADERS,
        )
        data = r.json()
        counts = data["file_counts"]
        if data["status"] == "completed":
            print(f"  Done: {counts['completed']} completed, {counts['failed']} failed")
            return
        if data["status"] == "failed":
            print(f"  Batch failed: {counts}")
            return
        print(f"  ... {counts['in_progress']} in progress, {counts['completed']} completed")

    print("  Timed out waiting for batch completion")


def save_file_ids(file_ids: list[str]) -> None:
    """Save file IDs so the next run can delete them."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ids_file = EXPORT_DIR / ".auto-file-ids"
    ids_file.write_text("\n".join(file_ids) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)

    print(f"Vector store: {VS_ID}")
    print(f"Database:     {DB_PATH}")
    print(f"Docs:         {DOCS_DIR}")
    print()

    print("1. Exporting gold tables to markdown...")
    gold_files = export_gold_tables()

    print("\n2. Collecting docs/ files...")
    doc_files = collect_docs()

    all_files = gold_files + doc_files
    print(f"\n   Total files to sync: {len(all_files)}")

    print("\n3. Removing previous auto-uploaded files...")
    delete_auto_files()

    print("\n4. Uploading fresh files...")
    new_ids = upload_files(all_files)
    save_file_ids(new_ids)

    print(f"\n5. Attaching {len(new_ids)} files to vector store...")
    attach_to_vector_store(new_ids)

    print(f"\nDone. {len(new_ids)} files synced to vector store {VS_ID}.")


if __name__ == "__main__":
    main()
