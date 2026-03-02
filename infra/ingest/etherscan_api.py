"""Etherscan REST API client for ENS DAO on-chain data.

Fetches delegation events, token transfers (for distribution), and treasury
transactions from the Etherscan API.  Designed for the free tier (3 req/sec,
1 000 records per page).

Follows the same structural conventions as snapshot_api.py and tally_api.py:
module-level constants, a shared run_query() with 429 retry, then domain-
specific fetch functions that return list[dict].
"""

import time
from collections import defaultdict

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://api.etherscan.io/api"
ENS_TOKEN_CONTRACT = "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72"

# keccak256("DelegateChanged(address,address,address)")
DELEGATE_CHANGED_TOPIC0 = (
    "0x3134e8a2e6d97e929a7e54011ea5485d7d196dd5f0ba4d4ef95803e8e3fc257f"
)

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC0 = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

# Known ENS DAO wallet addresses.
# wallet.ensdao.eth is the DAO timelock / main treasury.
DAO_WALLETS: dict[str, str] = {
    "wallet.ensdao.eth": "0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7",
}

PAGE_SIZE = 1000        # Etherscan free-tier max records per page
REQUEST_DELAY = 0.35    # ~3 req/sec with safety margin
RATE_LIMIT_DELAY = 60   # Back-off on 429 / "Max rate limit reached"
MAX_PAGES_PER_RANGE = 10  # Etherscan caps getLogs at 10 000 results

ZERO_ADDRESS = "0x" + "0" * 40

# ---------------------------------------------------------------------------
# Core query helpers
# ---------------------------------------------------------------------------


def run_query(params: dict, api_key: str) -> dict:
    """Execute an Etherscan GET request with rate-limit retry.

    Handles both HTTP-level 429 and Etherscan's in-body rate-limit errors.
    Treats "No records found" (status 0) as an empty — not an error.
    """
    full_params = {**params, "apikey": api_key}
    resp = requests.get(API_URL, params=full_params, timeout=30)
    if resp.status_code == 429:
        time.sleep(RATE_LIMIT_DELAY)
        return run_query(params, api_key)
    resp.raise_for_status()

    data = resp.json()

    if data.get("status") == "0" and data.get("message") != "No records found":
        msg = data.get("result", "Unknown Etherscan error")
        if "Max rate limit reached" in str(msg):
            time.sleep(RATE_LIMIT_DELAY)
            return run_query(params, api_key)
        raise RuntimeError(f"Etherscan API error: {msg}")

    return data


def _decode_address(hex_topic: str) -> str:
    """Extract a 20-byte address from a 32-byte zero-padded topic."""
    return "0x" + hex_topic[-40:].lower()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _paginate(
    params: dict,
    api_key: str,
    *,
    start_block: int = 0,
    end_block: int = 99_999_999,
    max_pages: int | None = None,
) -> list[dict]:
    """Generic paginator for Etherscan list endpoints.

    Pages through results using page/offset.  When *max_pages* is set and the
    last page is full (i.e. more records may exist beyond the cap), the
    function advances ``start_block`` to the block after the last record and
    recurses to fetch the remaining data.

    This "sliding window" approach keeps the implementation simple while
    handling the free-tier 10 000-result cap on getLogs.
    """
    all_results: list[dict] = []
    page = 1

    base = {
        **params,
        "startblock": start_block,
        "endblock": end_block,
        "sort": "asc",
        "offset": PAGE_SIZE,
    }

    while True:
        base["page"] = page
        data = run_query(base, api_key)
        results = data.get("result", [])

        if not isinstance(results, list) or not results:
            break

        all_results.extend(results)

        if len(results) < PAGE_SIZE:
            break

        if max_pages is not None and page >= max_pages:
            # Determine the last block seen and fetch the remainder.
            last_block_hex = results[-1].get("blockNumber", "0x0")
            try:
                last_block = int(last_block_hex, 16)
            except (ValueError, TypeError):
                last_block = int(last_block_hex)
            if last_block < end_block:
                remaining = _paginate(
                    params,
                    api_key,
                    start_block=last_block + 1,
                    end_block=end_block,
                    max_pages=max_pages,
                )
                all_results.extend(remaining)
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_results


# ---------------------------------------------------------------------------
# 1. Delegation events
# ---------------------------------------------------------------------------


def fetch_delegation_events(api_key: str) -> list[dict]:
    """Fetch all DelegateChanged events for the ENS token contract.

    Returns list of dicts with keys matching the downstream staging model:
    ``delegator, delegate, block_number, timestamp, token_balance``.

    ``token_balance`` is ``None`` because the DelegateChanged event does not
    emit balance information.  The silver layer handles this safely via
    ``try_cast``.
    """
    params = {
        "module": "logs",
        "action": "getLogs",
        "address": ENS_TOKEN_CONTRACT,
        "topic0": DELEGATE_CHANGED_TOPIC0,
    }

    raw_logs = _paginate(
        params, api_key, max_pages=MAX_PAGES_PER_RANGE,
    )

    events: list[dict] = []
    for log in raw_logs:
        topics = log.get("topics", [])
        if len(topics) < 4:
            continue

        delegator = _decode_address(topics[1])
        to_delegate = _decode_address(topics[3])
        block_hex = log.get("blockNumber", "0x0")
        ts_hex = log.get("timeStamp", "0x0")

        events.append({
            "delegator": delegator,
            "delegate": to_delegate,
            "block_number": int(block_hex, 16),
            "timestamp": int(ts_hex, 16),
            "token_balance": None,
        })

    return events


# ---------------------------------------------------------------------------
# 2. Token distribution (computed from Transfer events)
# ---------------------------------------------------------------------------


def fetch_token_transfers(api_key: str) -> list[dict]:
    """Compute ENS token distribution from on-chain Transfer events.

    Fetches every Transfer event on the ENS token contract, then aggregates
    inflows and outflows per address to derive current balances.

    Returns list of dicts with keys matching the staging model:
    ``address, balance (wei string), percentage, snapshot_block``.
    """
    params = {
        "module": "logs",
        "action": "getLogs",
        "address": ENS_TOKEN_CONTRACT,
        "topic0": TRANSFER_TOPIC0,
    }

    raw_logs = _paginate(
        params, api_key, max_pages=MAX_PAGES_PER_RANGE,
    )

    balances: dict[str, int] = defaultdict(int)
    latest_block = 0

    for log in raw_logs:
        topics = log.get("topics", [])
        if len(topics) < 3:
            continue

        from_addr = _decode_address(topics[1])
        to_addr = _decode_address(topics[2])
        value = int(log.get("data", "0x0"), 16)

        block_hex = log.get("blockNumber", "0x0")
        block_num = int(block_hex, 16)
        if block_num > latest_block:
            latest_block = block_num

        if from_addr != ZERO_ADDRESS:
            balances[from_addr] -= value
        if to_addr != ZERO_ADDRESS:
            balances[to_addr] += value

    # Keep only positive balances, compute total supply for percentages.
    positive = {addr: bal for addr, bal in balances.items() if bal > 0}
    total_supply = sum(positive.values()) or 1  # avoid div-by-zero

    distribution = [
        {
            "address": addr,
            "balance": str(bal),
            "percentage": round(bal / total_supply * 100, 6),
            "snapshot_block": latest_block,
        }
        for addr, bal in positive.items()
    ]
    distribution.sort(key=lambda r: int(r["balance"]), reverse=True)

    return distribution


# ---------------------------------------------------------------------------
# 3. Treasury flows
# ---------------------------------------------------------------------------


def fetch_treasury_transactions(
    api_key: str,
    wallets: dict[str, str] | None = None,
) -> list[dict]:
    """Fetch ETH + ERC-20 transactions for ENS DAO treasury wallets.

    For each wallet, queries both normal transactions (``txlist``) and token
    transfers (``tokentx``), then merges and deduplicates.

    Returns list of dicts matching the staging model:
    ``tx_hash, from, to, value (wei str), token, block_number, timestamp, category``.
    """
    if wallets is None:
        wallets = DAO_WALLETS

    all_flows: list[dict] = []
    seen: set[str] = set()

    for _label, address in wallets.items():
        # --- Normal ETH transactions ---
        eth_txs = _fetch_account_txs(
            address, api_key, action="txlist",
        )
        for tx in eth_txs:
            tx_hash = tx.get("hash", "")
            if tx_hash in seen:
                continue
            seen.add(tx_hash)
            all_flows.append({
                "tx_hash": tx_hash,
                "from": tx.get("from", "").lower(),
                "to": tx.get("to", "").lower(),
                "value": tx.get("value", "0"),
                "token": "ETH",
                "block_number": int(tx.get("blockNumber", "0")),
                "timestamp": int(tx.get("timeStamp", "0")),
                "category": "unknown",
            })

        time.sleep(REQUEST_DELAY)

        # --- ERC-20 token transfers ---
        token_txs = _fetch_account_txs(
            address, api_key, action="tokentx",
        )
        for tx in token_txs:
            dedup_key = f"{tx.get('hash', '')}:{tx.get('logIndex', '')}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            all_flows.append({
                "tx_hash": tx.get("hash", ""),
                "from": tx.get("from", "").lower(),
                "to": tx.get("to", "").lower(),
                "value": tx.get("value", "0"),
                "token": tx.get("tokenSymbol", "UNKNOWN"),
                "block_number": int(tx.get("blockNumber", "0")),
                "timestamp": int(tx.get("timeStamp", "0")),
                "category": "unknown",
            })

    all_flows.sort(key=lambda r: (r["block_number"], r["timestamp"]))
    return all_flows


def _fetch_account_txs(
    address: str,
    api_key: str,
    *,
    action: str = "txlist",
) -> list[dict]:
    """Paginate through account transaction endpoints (txlist / tokentx)."""
    params = {
        "module": "account",
        "action": action,
        "address": address,
    }
    return _paginate(params, api_key)
