"""Standalone Etherscan data export for ENS DAO on-chain data.

Usage:
    python bronze/on-chain/scripts/export_ens_onchain.py

Requires ETHERSCAN_API_KEY in .env file or environment.
Writes JSON outputs to bronze/on-chain/.

Supports resumable fetching: if interrupted, re-run the script and it
will pick up from the last checkpoint automatically.
"""

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1  # Ethereum mainnet
API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ENS_TOKEN_CONTRACT = "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72"

DELEGATE_CHANGED_TOPIC0 = (
    "0x3134e8a2e6d97e929a7e54011ea5485d7d196dd5f0ba4d4ef95803e8e3fc257f"
)
TRANSFER_TOPIC0 = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
DAO_WALLETS = {
    "wallet.ensdao.eth": "0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7",
}

PAGE_SIZE = 1000
REQUEST_DELAY = 0.35
RATE_LIMIT_DELAY = 60
MAX_PAGES = 10
ZERO_ADDRESS = "0x" + "0" * 40
CHECKPOINT_EVERY = 10  # Save checkpoint every N pages

OUTPUT_DIR = Path(__file__).resolve().parent.parent  # bronze/on-chain/
CHECKPOINT_DIR = OUTPUT_DIR / ".checkpoints"

if not API_KEY:
    sys.exit("ETHERSCAN_API_KEY not set. Add it to .env or export it.")


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint(name):
    path = CHECKPOINT_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        print(f"  Warning: corrupt checkpoint '{name}', starting fresh")
        return None


def save_checkpoint(name, data):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, default=str)
    tmp.rename(path)


def clear_checkpoint(name):
    path = CHECKPOINT_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
    if CHECKPOINT_DIR.exists() and not any(CHECKPOINT_DIR.iterdir()):
        CHECKPOINT_DIR.rmdir()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def run_query(params, *, _retries=3):
    full_params = {**params, "chainid": CHAIN_ID, "apikey": API_KEY}
    try:
        resp = requests.get(API_URL, params=full_params, timeout=30)
    except (requests.ConnectionError, requests.Timeout):
        if _retries <= 0:
            raise
        print(f"  Request timed out, retrying ({_retries} left) ...")
        time.sleep(REQUEST_DELAY * 5)
        return run_query(params, _retries=_retries - 1)
    if resp.status_code == 429:
        print("  Rate limited — waiting 60s ...")
        time.sleep(RATE_LIMIT_DELAY)
        return run_query(params, _retries=_retries)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "0" and data.get("message") != "No records found":
        msg = data.get("result", "Unknown error")
        if "Max rate limit reached" in str(msg):
            print("  Rate limited — waiting 60s ...")
            time.sleep(RATE_LIMIT_DELAY)
            return run_query(params, _retries=_retries)
        raise RuntimeError(f"Etherscan error: {msg}")
    return data


def decode_address(hex_topic):
    return "0x" + hex_topic[-40:].lower()


def paginate(params, *, start_block=0, end_block=99_999_999, on_page=None):
    all_results = []
    current_start = start_block

    while True:
        page = 1
        base = {**params,
                "startblock": current_start, "endblock": end_block,
                "fromBlock": current_start, "toBlock": end_block,
                "sort": "asc", "offset": PAGE_SIZE}
        hit_cap = False

        while True:
            base["page"] = page
            data = run_query(base)
            results = data.get("result", [])
            if not isinstance(results, list) or not results:
                break
            all_results.extend(results)
            if on_page is not None:
                on_page(results)
            if len(results) < PAGE_SIZE:
                break
            if page >= MAX_PAGES:
                hit_cap = True
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        if not hit_cap:
            break

        last_block_hex = results[-1].get("blockNumber", "0x0")
        try:
            last_block = int(last_block_hex, 16)
        except (ValueError, TypeError):
            last_block = int(last_block_hex)
        if last_block >= end_block:
            break
        current_start = last_block + 1

    return all_results


# ---------------------------------------------------------------------------
# Fetchers with checkpoint support
# ---------------------------------------------------------------------------


def fetch_delegations():
    ckpt = load_checkpoint("delegations")
    events = ckpt["records"] if ckpt else []
    start_block = ckpt["resume_block"] if ckpt else 0

    if ckpt:
        print(f"  Resuming from block {start_block} ({len(events)} events loaded)")

    page_count = 0

    def on_page(page_results):
        nonlocal page_count
        for log in page_results:
            topics = log.get("topics", [])
            if len(topics) < 4:
                continue
            events.append({
                "delegator": decode_address(topics[1]),
                "delegate": decode_address(topics[3]),
                "block_number": int(log.get("blockNumber", "0x0"), 16),
                "timestamp": int(log.get("timeStamp", "0x0"), 16),
                "token_balance": None,
            })
        page_count += 1
        if events and page_count % CHECKPOINT_EVERY == 0:
            print(f"  Progress: {len(events)} events, block {events[-1]['block_number']}")
            save_checkpoint("delegations", {
                "resume_block": events[-1]["block_number"] + 1,
                "records": events,
            })

    print("  Querying DelegateChanged events ...")
    params = {"module": "logs", "action": "getLogs",
              "address": ENS_TOKEN_CONTRACT, "topic0": DELEGATE_CHANGED_TOPIC0}
    paginate(params, start_block=start_block, on_page=on_page)

    clear_checkpoint("delegations")
    return events


def fetch_token_distribution():
    ckpt = load_checkpoint("token_transfers")
    if ckpt:
        balances = defaultdict(int, {a: int(b) for a, b in ckpt["balances"].items()})
        latest_block = ckpt["latest_block"]
        start_block = ckpt["resume_block"]
        print(f"  Resuming from block {start_block} ({len(balances)} addresses loaded)")
    else:
        balances = defaultdict(int)
        latest_block = 0
        start_block = 0

    page_count = 0

    def on_page(page_results):
        nonlocal latest_block, page_count
        for log in page_results:
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            from_addr = decode_address(topics[1])
            to_addr = decode_address(topics[2])
            value = int(log.get("data", "0x0"), 16)
            block_num = int(log.get("blockNumber", "0x0"), 16)
            if block_num > latest_block:
                latest_block = block_num
            if from_addr != ZERO_ADDRESS:
                balances[from_addr] -= value
            if to_addr != ZERO_ADDRESS:
                balances[to_addr] += value
        page_count += 1
        if page_count % CHECKPOINT_EVERY == 0:
            print(f"  Progress: {len(balances)} addresses, block {latest_block}")
            save_checkpoint("token_transfers", {
                "resume_block": latest_block + 1,
                "latest_block": latest_block,
                "balances": {a: str(b) for a, b in balances.items()},
            })

    print("  Querying Transfer events (this may take a few minutes) ...")
    params = {"module": "logs", "action": "getLogs",
              "address": ENS_TOKEN_CONTRACT, "topic0": TRANSFER_TOPIC0}
    paginate(params, start_block=start_block, on_page=on_page)

    positive = {a: b for a, b in balances.items() if b > 0}
    total = sum(positive.values()) or 1
    distribution = [
        {"address": a, "balance": str(b),
         "percentage": round(b / total * 100, 6), "snapshot_block": latest_block}
        for a, b in positive.items()
    ]
    distribution.sort(key=lambda r: int(r["balance"]), reverse=True)

    clear_checkpoint("token_transfers")
    return distribution


def fetch_treasury():
    ckpt = load_checkpoint("treasury_flows")
    if ckpt:
        all_flows = ckpt["records"]
        seen = set(ckpt["seen_keys"])
        completed = set(ckpt.get("completed_steps", []))
        print(f"  Resuming ({len(all_flows)} records, {len(completed)} steps done)")
    else:
        all_flows = []
        seen = set()
        completed = set()

    for label, address in DAO_WALLETS.items():
        step = f"{label}:txlist"
        if step not in completed:
            print(f"  Fetching ETH txs for {label} ({address}) ...")
            params = {"module": "account", "action": "txlist", "address": address}
            for tx in paginate(params):
                h = tx.get("hash", "")
                if h in seen:
                    continue
                seen.add(h)
                all_flows.append({
                    "tx_hash": h, "from": tx.get("from", "").lower(),
                    "to": tx.get("to", "").lower(), "value": tx.get("value", "0"),
                    "token": "ETH", "block_number": int(tx.get("blockNumber", "0")),
                    "timestamp": int(tx.get("timeStamp", "0")), "category": "unknown",
                })
            completed.add(step)
            save_checkpoint("treasury_flows", {
                "records": all_flows, "seen_keys": list(seen),
                "completed_steps": list(completed),
            })

        time.sleep(REQUEST_DELAY)

        step = f"{label}:tokentx"
        if step not in completed:
            print(f"  Fetching ERC-20 txs for {label} ({address}) ...")
            params = {"module": "account", "action": "tokentx", "address": address}
            for tx in paginate(params):
                key = f"{tx.get('hash', '')}:{tx.get('logIndex', '')}"
                if key in seen:
                    continue
                seen.add(key)
                all_flows.append({
                    "tx_hash": tx.get("hash", ""), "from": tx.get("from", "").lower(),
                    "to": tx.get("to", "").lower(), "value": tx.get("value", "0"),
                    "token": tx.get("tokenSymbol", "UNKNOWN"),
                    "block_number": int(tx.get("blockNumber", "0")),
                    "timestamp": int(tx.get("timeStamp", "0")), "category": "unknown",
                })
            completed.add(step)
            save_checkpoint("treasury_flows", {
                "records": all_flows, "seen_keys": list(seen),
                "completed_steps": list(completed),
            })

    all_flows.sort(key=lambda r: (r["block_number"], r["timestamp"]))
    clear_checkpoint("treasury_flows")
    return all_flows


# ---------------------------------------------------------------------------
# Output + main
# ---------------------------------------------------------------------------


def write_json(data, filename):
    path = OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    size = path.stat().st_size
    print(f"  Wrote {len(data)} records to {path} ({size:,} bytes)")


def main():
    print("=== ENS On-Chain Data Export (Etherscan) ===\n")

    print("[1/3] Delegation events")
    delegations = fetch_delegations()
    print(f"  Total: {len(delegations)} events")
    write_json(delegations, "delegations.json")

    print("\n[2/3] Token distribution")
    distribution = fetch_token_distribution()
    print(f"  Total: {len(distribution)} holders with positive balance")
    write_json(distribution, "token_distribution.json")

    print("\n[3/3] Treasury flows")
    flows = fetch_treasury()
    print(f"  Total: {len(flows)} transactions")
    write_json(flows, "treasury_flows.json")

    print("\nDone!")


if __name__ == "__main__":
    main()
