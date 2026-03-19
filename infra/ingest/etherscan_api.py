"""Etherscan REST API client for ENS DAO on-chain data.

Fetches delegation events, token transfers (for distribution), and treasury
transactions from the Etherscan API.  Designed for the free tier (3 req/sec,
1 000 records per page).

Supports resumable fetching: each fetch function saves progress to a
checkpoint file after every page.  If interrupted, the next run automatically
resumes from the last checkpoint.  Checkpoints are stored in
``bronze/on-chain/.checkpoints/`` and cleaned up on successful completion.
"""

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1  # Ethereum mainnet
ENS_TOKEN_CONTRACT = "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72"

# keccak256("DelegateChanged(address,address,address)")
DELEGATE_CHANGED_TOPIC0 = "0x3134e8a2e6d97e929a7e54011ea5485d7d196dd5f0ba4d4ef95803e8e3fc257f"

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Known ENS DAO wallet addresses.
# wallet.ensdao.eth is the DAO timelock / main treasury.
DAO_WALLETS: dict[str, str] = {
    "wallet.ensdao.eth": "0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7",
}

PAGE_SIZE = 1000  # Etherscan free-tier max records per page
REQUEST_DELAY = 0.25  # ~4 req/sec (free tier allows 5/sec)
RATE_LIMIT_DELAY = 60  # Back-off on 429 / "Max rate limit reached"
MAX_PAGES_PER_RANGE = 10  # Etherscan caps getLogs at 10 000 results

ZERO_ADDRESS = "0x" + "0" * 40

CHECKPOINT_DIR = (
    Path(__file__).resolve().parent.parent.parent / "bronze" / "on-chain" / ".checkpoints"
)
CHECKPOINT_EVERY = 10  # Save checkpoint every N pages (avoids I/O thrashing)

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def _load_checkpoint(name: str) -> dict | None:
    """Load a checkpoint file if it exists. Returns None if absent or corrupt."""
    path = CHECKPOINT_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        logger.info(
            "Loaded checkpoint '%s' (resume_block=%s)",
            name,
            data.get("resume_block"),
        )
        return data
    except (json.JSONDecodeError, KeyError):
        logger.warning("Corrupt checkpoint '%s', starting fresh", name)
        return None


def _save_checkpoint(name: str, data: dict) -> None:
    """Atomically write a checkpoint (write to .tmp then rename)."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, default=str)
    tmp.rename(path)


def _clear_checkpoint(name: str) -> None:
    """Remove a checkpoint after successful completion."""
    path = CHECKPOINT_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
    # Clean up empty checkpoint dir
    if CHECKPOINT_DIR.exists() and not any(CHECKPOINT_DIR.iterdir()):
        CHECKPOINT_DIR.rmdir()


# ---------------------------------------------------------------------------
# Core query helpers
# ---------------------------------------------------------------------------


def run_query(params: dict, api_key: str, *, _retries: int = 3) -> dict:
    """Execute an Etherscan GET request with rate-limit and timeout retry.

    Handles HTTP-level 429, Etherscan's in-body rate-limit errors, and
    network timeouts.  Treats "No records found" (status 0) as empty.
    """
    full_params = {**params, "chainid": CHAIN_ID, "apikey": api_key}

    try:
        logger.debug(
            "[ETHERSCAN] → GET %s params=%s",
            API_URL,
            {k: v for k, v in full_params.items() if k != "apikey"},
        )
        resp = requests.get(API_URL, params=full_params, timeout=30)
    except (requests.ConnectionError, requests.Timeout):
        if _retries <= 0:
            logger.error("[ETHERSCAN] Request timed out, no retries left")
            raise
        logger.warning("[ETHERSCAN] Request timed out, retrying (%d left)", _retries)
        time.sleep(REQUEST_DELAY * 5)
        return run_query(params, api_key, _retries=_retries - 1)

    if resp.status_code == 429:
        logger.warning("[ETHERSCAN] Rate limited (429), backing off %ds", RATE_LIMIT_DELAY)
        time.sleep(RATE_LIMIT_DELAY)
        return run_query(params, api_key, _retries=_retries)
    resp.raise_for_status()

    data = resp.json()

    if data.get("status") == "0" and data.get("message") != "No records found":
        msg = data.get("result", "Unknown Etherscan error")
        if "Max rate limit reached" in str(msg):
            logger.warning("[ETHERSCAN] Rate limited (body), backing off %ds", RATE_LIMIT_DELAY)
            time.sleep(RATE_LIMIT_DELAY)
            return run_query(params, api_key, _retries=_retries)
        if not msg or str(msg) == "None":
            if _retries <= 0:
                raise RuntimeError(f"Etherscan API error after retries: {msg}")
            logger.warning(
                "[ETHERSCAN] Etherscan returned empty error, retrying (%d left)", _retries
            )
            time.sleep(REQUEST_DELAY * 5)
            return run_query(params, api_key, _retries=_retries - 1)
        raise RuntimeError(f"Etherscan API error: {msg}")

    result_count = len(data.get("result", [])) if isinstance(data.get("result"), list) else "N/A"
    logger.debug(
        "[ETHERSCAN] ← Response: status=%s, result_count=%s", data.get("status"), result_count
    )

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
    on_page: Callable[[list[dict]], None] | None = None,
) -> list[dict]:
    """Generic paginator for Etherscan list endpoints.

    Pages through results using page/offset.  When *max_pages* is set and the
    last page is full (i.e. more records may exist beyond the cap), the
    function advances ``start_block`` to the block after the last result and
    starts a new window — iteratively, not recursively.

    The optional *on_page* callback is called after each page with that page's
    raw results.  Fetch functions use this to incrementally process data and
    save checkpoints.
    """
    all_results: list[dict] = []
    current_start = start_block
    request_count = 0

    while True:
        page = 1
        base = {
            **params,
            # getLogs uses fromBlock/toBlock; txlist uses startblock/endblock.
            # Include both so the paginator works for all endpoint types.
            "startblock": current_start,
            "endblock": end_block,
            "fromBlock": current_start,
            "toBlock": end_block,
            "sort": "asc",
            "offset": PAGE_SIZE,
        }
        hit_cap = False

        while True:
            base["page"] = page
            request_count += 1
            data = run_query(base, api_key)
            results = data.get("result", [])

            if not isinstance(results, list) or not results:
                if request_count % 10 == 0:
                    logger.debug("[ETHERSCAN] Empty page %d (request #%d)", page, request_count)
                break

            all_results.extend(results)

            if on_page is not None:
                on_page(results)

            if request_count % 10 == 0 or len(results) == PAGE_SIZE:
                logger.info(
                    "[ETHERSCAN] Request #%d: got %d results (total: %d, block_range: %d-%d)",
                    request_count,
                    len(results),
                    len(all_results),
                    current_start,
                    end_block,
                )

            if len(results) < PAGE_SIZE:
                break

            if max_pages is not None and page >= max_pages:
                hit_cap = True
                break

            page += 1
            time.sleep(REQUEST_DELAY)

        if not hit_cap:
            break

        # Advance the window past the last block seen.
        last_block_hex = results[-1].get("blockNumber", "0x0")
        try:
            last_block = int(last_block_hex, 16)
        except (ValueError, TypeError):
            last_block = int(last_block_hex)

        if last_block >= end_block:
            break

        current_start = last_block + 1
        logger.debug("[ETHERSCAN] Hit pagination cap, advancing to block %d", current_start)

    logger.info(
        "[ETHERSCAN] Pagination complete: %d total results in %d requests",
        len(all_results),
        request_count,
    )
    return all_results


# ---------------------------------------------------------------------------
# 1. Delegation events
# ---------------------------------------------------------------------------


def fetch_delegation_events(api_key: str) -> list[dict]:
    """Fetch all DelegateChanged events for the ENS token contract.

    Supports resumable fetching via JSONL checkpoint.  Events are appended
    to a ``.partial.jsonl`` file as they arrive, so checkpoint writes are
    O(page_size) not O(total_events).  A tiny meta file tracks the resume
    block.

    Returns list of dicts with keys:
    ``delegator, delegate, block_number, timestamp, token_balance``.
    """
    meta_path = CHECKPOINT_DIR / "delegations.meta.json"
    partial_path = CHECKPOINT_DIR / "delegations.partial.jsonl"

    # Resume from partial file if it exists.
    events: list[dict] = []
    start_block = 0
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        start_block = meta["resume_block"]
        if partial_path.exists():
            with open(partial_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        logger.info(
            "Resuming delegations from block %d (%d events loaded)",
            start_block,
            len(events),
        )

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    partial_file = open(partial_path, "a")
    page_count = 0

    def on_page(page_results: list[dict]) -> None:
        nonlocal page_count
        for log in page_results:
            topics = log.get("topics", [])
            if len(topics) < 4:
                continue
            block_hex = log.get("blockNumber", "0x0")
            ts_hex = log.get("timeStamp", "0x0")
            event = {
                "delegator": _decode_address(topics[1]),
                "delegate": _decode_address(topics[3]),
                "block_number": int(block_hex, 16),
                "timestamp": int(ts_hex, 16),
                "token_balance": None,
            }
            events.append(event)
            partial_file.write(json.dumps(event, default=str) + "\n")
        partial_file.flush()
        page_count += 1
        if page_count % CHECKPOINT_EVERY == 0:
            # Meta file is tiny — just the resume block.
            meta_path.write_text(
                json.dumps(
                    {
                        "resume_block": events[-1]["block_number"] + 1,
                    }
                )
            )
            logger.info(
                "Delegations progress: %d events, block %d",
                len(events),
                events[-1]["block_number"],
            )

    params = {
        "module": "logs",
        "action": "getLogs",
        "address": ENS_TOKEN_CONTRACT,
        "topic0": DELEGATE_CHANGED_TOPIC0,
    }
    try:
        _paginate(
            params, api_key, start_block=start_block, max_pages=MAX_PAGES_PER_RANGE, on_page=on_page
        )
    finally:
        partial_file.close()
        # Always save final meta so resume works even without CHECKPOINT_EVERY hit.
        if events:
            meta_path.write_text(
                json.dumps(
                    {
                        "resume_block": events[-1]["block_number"] + 1,
                    }
                )
            )

    logger.info("Delegations complete: %d events total", len(events))
    # Clean up checkpoint files on success.
    for p in (partial_path, meta_path):
        if p.exists():
            p.unlink()
    if CHECKPOINT_DIR.exists() and not any(CHECKPOINT_DIR.iterdir()):
        CHECKPOINT_DIR.rmdir()
    return events


# ---------------------------------------------------------------------------
# 2. Token distribution (computed from Transfer events)
# ---------------------------------------------------------------------------


def fetch_token_transfers(api_key: str) -> list[dict]:
    """Compute ENS token distribution from on-chain Transfer events.

    Supports resumable fetching.  The checkpoint stores the accumulated
    balance dict so that interrupted runs don't need to replay transfers.

    Returns list of dicts with keys:
    ``address, balance (wei string), percentage, snapshot_block``.
    """
    ckpt = _load_checkpoint("token_transfers")
    if ckpt:
        balances: dict[str, int] = defaultdict(
            int,
            {a: int(b) for a, b in ckpt["balances"].items()},
        )
        latest_block: int = ckpt["latest_block"]
        start_block: int = ckpt["resume_block"]
        logger.info(
            "Resuming token transfers from block %d (%d addresses loaded)",
            start_block,
            len(balances),
        )
    else:
        balances = defaultdict(int)
        latest_block = 0
        start_block = 0

    page_count = 0

    def on_page(page_results: list[dict]) -> None:
        nonlocal latest_block, page_count
        for log in page_results:
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            from_addr = _decode_address(topics[1])
            to_addr = _decode_address(topics[2])
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
            logger.info(
                "Token transfers progress: %d addresses, block %d", len(balances), latest_block
            )
            _save_checkpoint(
                "token_transfers",
                {
                    "resume_block": latest_block + 1,
                    "latest_block": latest_block,
                    "balances": {a: str(b) for a, b in balances.items()},
                },
            )

    logger.info(
        "Starting token transfer fetch (est. ~10-20 min on free tier — "
        "replays all ENS Transfer events since deployment)"
    )

    params = {
        "module": "logs",
        "action": "getLogs",
        "address": ENS_TOKEN_CONTRACT,
        "topic0": TRANSFER_TOPIC0,
    }
    _paginate(
        params, api_key, start_block=start_block, max_pages=MAX_PAGES_PER_RANGE, on_page=on_page
    )

    # Compute final distribution from accumulated balances.
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

    _clear_checkpoint("token_transfers")
    return distribution


# ---------------------------------------------------------------------------
# 3. Treasury flows
# ---------------------------------------------------------------------------


def fetch_treasury_transactions(
    api_key: str,
    wallets: dict[str, str] | None = None,
) -> list[dict]:
    """Fetch ETH + ERC-20 transactions for ENS DAO treasury wallets.

    Supports resumable fetching.  Checkpoints are saved after each
    (wallet, action) pair completes, so partial wallet fetches are retried
    but completed ones are skipped.

    Returns list of dicts with keys:
    ``tx_hash, from, to, value (wei str), token, block_number, timestamp, category``.
    """
    if wallets is None:
        wallets = DAO_WALLETS

    ckpt = _load_checkpoint("treasury_flows")
    if ckpt:
        all_flows: list[dict] = ckpt["records"]
        seen: set[str] = set(ckpt["seen_keys"])
        completed: set[str] = set(ckpt.get("completed_steps", []))
        logger.info(
            "Resuming treasury flows (%d records, %d/%d steps done)",
            len(all_flows),
            len(completed),
            len(wallets) * 2,
        )
    else:
        all_flows = []
        seen = set()
        completed = set()

    for label, address in wallets.items():
        # --- Normal ETH transactions ---
        step = f"{label}:txlist"
        if step not in completed:
            eth_txs = _fetch_account_txs(address, api_key, action="txlist")
            for tx in eth_txs:
                tx_hash = tx.get("hash", "")
                if tx_hash in seen:
                    continue
                seen.add(tx_hash)
                all_flows.append(
                    {
                        "tx_hash": tx_hash,
                        "from": tx.get("from", "").lower(),
                        "to": tx.get("to", "").lower(),
                        "value": tx.get("value", "0"),
                        "token": "ETH",
                        "block_number": int(tx.get("blockNumber", "0")),
                        "timestamp": int(tx.get("timeStamp", "0")),
                        "category": "unknown",
                    }
                )
            completed.add(step)
            _save_checkpoint(
                "treasury_flows",
                {
                    "records": all_flows,
                    "seen_keys": list(seen),
                    "completed_steps": list(completed),
                },
            )

        time.sleep(REQUEST_DELAY)

        # --- ERC-20 token transfers ---
        step = f"{label}:tokentx"
        if step not in completed:
            token_txs = _fetch_account_txs(address, api_key, action="tokentx")
            for tx in token_txs:
                dedup_key = f"{tx.get('hash', '')}:{tx.get('logIndex', '')}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                all_flows.append(
                    {
                        "tx_hash": tx.get("hash", ""),
                        "from": tx.get("from", "").lower(),
                        "to": tx.get("to", "").lower(),
                        "value": tx.get("value", "0"),
                        "token": tx.get("tokenSymbol", "UNKNOWN"),
                        "block_number": int(tx.get("blockNumber", "0")),
                        "timestamp": int(tx.get("timeStamp", "0")),
                        "category": "unknown",
                    }
                )
            completed.add(step)
            _save_checkpoint(
                "treasury_flows",
                {
                    "records": all_flows,
                    "seen_keys": list(seen),
                    "completed_steps": list(completed),
                },
            )

    all_flows.sort(key=lambda r: (r["block_number"], r["timestamp"]))
    _clear_checkpoint("treasury_flows")
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
