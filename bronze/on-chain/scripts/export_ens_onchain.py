"""Standalone Etherscan data export for ENS DAO on-chain data.

Usage:
    python bronze/on-chain/scripts/export_ens_onchain.py

Requires ETHERSCAN_API_KEY in .env file or environment.
Writes JSON outputs to bronze/on-chain/.
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

API_URL = "https://api.etherscan.io/api"
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

OUTPUT_DIR = Path(__file__).resolve().parent.parent  # bronze/on-chain/

if not API_KEY:
    sys.exit("ETHERSCAN_API_KEY not set. Add it to .env or export it.")


def run_query(params: dict) -> dict:
    full_params = {**params, "apikey": API_KEY}
    resp = requests.get(API_URL, params=full_params, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited — waiting 60s ...")
        time.sleep(RATE_LIMIT_DELAY)
        return run_query(params)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "0" and data.get("message") != "No records found":
        msg = data.get("result", "Unknown error")
        if "Max rate limit reached" in str(msg):
            print("  Rate limited — waiting 60s ...")
            time.sleep(RATE_LIMIT_DELAY)
            return run_query(params)
        raise RuntimeError(f"Etherscan error: {msg}")
    return data


def decode_address(hex_topic: str) -> str:
    return "0x" + hex_topic[-40:].lower()


def paginate(params: dict, *, start_block=0, end_block=99_999_999) -> list[dict]:
    all_results = []
    page = 1
    base = {**params, "startblock": start_block, "endblock": end_block,
            "sort": "asc", "offset": PAGE_SIZE}

    while True:
        base["page"] = page
        data = run_query(base)
        results = data.get("result", [])
        if not isinstance(results, list) or not results:
            break
        all_results.extend(results)
        if len(results) < PAGE_SIZE:
            break
        if page >= MAX_PAGES:
            last_block_hex = results[-1].get("blockNumber", "0x0")
            try:
                last_block = int(last_block_hex, 16)
            except (ValueError, TypeError):
                last_block = int(last_block_hex)
            if last_block < end_block:
                remaining = paginate(params, start_block=last_block + 1,
                                     end_block=end_block)
                all_results.extend(remaining)
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return all_results


def fetch_delegations() -> list[dict]:
    print("  Querying DelegateChanged events ...")
    params = {"module": "logs", "action": "getLogs",
              "address": ENS_TOKEN_CONTRACT, "topic0": DELEGATE_CHANGED_TOPIC0}
    raw = paginate(params)
    events = []
    for log in raw:
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
    return events


def fetch_token_distribution() -> list[dict]:
    print("  Querying Transfer events (this may take a few minutes) ...")
    params = {"module": "logs", "action": "getLogs",
              "address": ENS_TOKEN_CONTRACT, "topic0": TRANSFER_TOPIC0}
    raw = paginate(params)
    print(f"  Processing {len(raw)} transfer events ...")

    balances: dict[str, int] = defaultdict(int)
    latest_block = 0
    for log in raw:
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

    positive = {a: b for a, b in balances.items() if b > 0}
    total = sum(positive.values()) or 1
    distribution = [
        {"address": a, "balance": str(b),
         "percentage": round(b / total * 100, 6), "snapshot_block": latest_block}
        for a, b in positive.items()
    ]
    distribution.sort(key=lambda r: int(r["balance"]), reverse=True)
    return distribution


def fetch_treasury() -> list[dict]:
    all_flows = []
    seen: set[str] = set()
    for label, address in DAO_WALLETS.items():
        print(f"  Fetching txs for {label} ({address}) ...")
        # Normal ETH txs
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
        time.sleep(REQUEST_DELAY)
        # ERC-20 token txs
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
    all_flows.sort(key=lambda r: (r["block_number"], r["timestamp"]))
    return all_flows


def write_json(data: list[dict], filename: str):
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
