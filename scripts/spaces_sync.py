"""Sync large data files between local repo and DigitalOcean Spaces.

Upload (after pipeline runs):
    python3 scripts/spaces_sync.py

Download (for local dev setup or CI):
    python3 scripts/spaces_sync.py --download

Requires in .env:
    DO_SPACE=https://ensretro-data.fra1.digitaloceanspaces.com
    DO_ACCESS_KEY=...   (only needed for upload)
    DO_SECRET_KEY=...   (only needed for upload)
"""

import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SPACE_URL = os.environ.get("DO_SPACE", "https://ensretro-data.fra1.digitaloceanspaces.com")
ACCESS_KEY = os.environ.get("DO_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("DO_SECRET_KEY", "")

REPO_ROOT = Path(__file__).parent.parent

# Parse Space URL → bucket + region
_parts = SPACE_URL.replace("https://", "").replace("http://", "").split(".")
BUCKET = _parts[0]
REGION = _parts[1]

# Files to sync (paths relative to repo root)
FILES_TO_SYNC = [
    "warehouse/ens_retro.duckdb",
    ".dagster/storage/.db",
    ".dagster/storage/index.db",
    ".dagster/storage/schedules.db",
]

# Agora CSV directories to sync
AGORA_DIR = REPO_ROOT / "bronze" / "governance" / "agora"

# Also sync any UUID-named dagster run DBs
DAGSTER_STORAGE = REPO_ROOT / ".dagster" / "storage"


def get_client():
    """Create an S3 client configured for DO Spaces."""
    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=REGION,
        endpoint_url=f"https://{REGION}.digitaloceanspaces.com",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )
    return client


def upload_file(client, local_path: Path, remote_key: str):
    """Upload a file to the Space."""
    size_mb = local_path.stat().st_size / (1024 * 1024)
    print(f"  Uploading {remote_key} ({size_mb:.1f} MB)...")
    client.upload_file(
        str(local_path),
        BUCKET,
        remote_key,
        ExtraArgs={"ACL": "public-read"},
    )
    print(f"  done")


def download_file(local_path: Path, remote_key: str):
    """Download a file from the Space via public URL (no credentials needed)."""
    import urllib.request

    url = f"{SPACE_URL}/{remote_key}"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {remote_key}...")
    urllib.request.urlretrieve(url, str(local_path))
    size_mb = local_path.stat().st_size / (1024 * 1024)
    print(f"  done ({size_mb:.1f} MB)")


def collect_agora_keys() -> list[str]:
    """List all Agora CSV relative paths."""
    if not AGORA_DIR.exists():
        return []
    return [str(p.relative_to(REPO_ROOT)) for p in sorted(AGORA_DIR.rglob("*.csv"))]


def cmd_upload():
    """Upload all data files to DO Spaces."""
    if not all([ACCESS_KEY, SECRET_KEY]):
        print("ERROR: Set DO_ACCESS_KEY and DO_SECRET_KEY in .env")
        sys.exit(1)

    client = get_client()
    print(f"Space: {SPACE_URL}\n")

    # Upload known files
    for rel_path in FILES_TO_SYNC:
        local = REPO_ROOT / rel_path
        if local.exists():
            upload_file(client, local, rel_path)
        else:
            print(f"  Skipped {rel_path} (not found)")

    # Upload UUID-named dagster run DBs
    if DAGSTER_STORAGE.exists():
        for db_file in DAGSTER_STORAGE.glob("*.db"):
            rel = str(db_file.relative_to(REPO_ROOT))
            if rel not in FILES_TO_SYNC:
                upload_file(client, db_file, rel)

    # Upload Agora CSVs
    for rel_path in collect_agora_keys():
        upload_file(client, REPO_ROOT / rel_path, rel_path)

    print(f"\nDone. Files available at {SPACE_URL}/")


def cmd_download():
    """Download all data files from DO Spaces (no credentials needed)."""
    print(f"Downloading from {SPACE_URL}\n")

    for rel_path in FILES_TO_SYNC:
        download_file(REPO_ROOT / rel_path, rel_path)

    # Download Agora CSVs — list from Spaces if local dir is empty
    agora_keys = collect_agora_keys()
    if not agora_keys:
        # Hardcoded list for fresh clones where no local CSVs exist yet
        agora_keys = [
            "bronze/governance/agora/Governor Contract/ProposalCanceled.csv",
            "bronze/governance/agora/Governor Contract/ProposalCreated.csv",
            "bronze/governance/agora/Governor Contract/ProposalExecuted.csv",
            "bronze/governance/agora/Governor Contract/ProposalQueued.csv",
            "bronze/governance/agora/Governor Contract/QuorumNumeratorUpdated.csv",
            "bronze/governance/agora/Governor Contract/VoteCast.csv",
            "bronze/governance/agora/Token Contract/Claim.csv",
            "bronze/governance/agora/Token Contract/DelegateChanged.csv",
            "bronze/governance/agora/Token Contract/DelegateVotesChanged.csv",
            "bronze/governance/agora/Token Contract/MerkleRootChanged.csv",
            "bronze/governance/agora/Token Contract/OwnershipTransferred.csv",
            "bronze/governance/agora/Token Contract/Transfer.csv",
        ]
    for rel_path in agora_keys:
        download_file(REPO_ROOT / rel_path, rel_path)

    print("\nDone. All data files downloaded.")


if __name__ == "__main__":
    if "--download" in sys.argv:
        cmd_download()
    else:
        cmd_upload()
