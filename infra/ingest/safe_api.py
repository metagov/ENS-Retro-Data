"""Safe Transaction Service API client for ENS DAO multisig wallets.

Fetches wallet balances (ETH + ERC-20) and multisig transaction history
from the Safe Global Transaction Service (no API key required).

Endpoints used:
- GET /api/v1/safes/{address}/balances/usd/  — token balances with USD prices
- GET /api/v1/safes/{address}/multisig-transactions/ — executed multisig txs
"""

import json
import logging
import struct
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFE_TX_SERVICE_URL = "https://safe-transaction-mainnet.safe.global"

# Token contracts we care about for balance reporting
ENS_TOKEN = "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72"
USDC_TOKEN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

TOKEN_DECIMALS = {
    ENS_TOKEN.lower(): 18,
    USDC_TOKEN.lower(): 6,
}
TOKEN_SYMBOLS = {
    ENS_TOKEN.lower(): "ENS",
    USDC_TOKEN.lower(): "USDC",
}

REQUEST_DELAY = 0.5  # Be polite to the free API


def _keccak256(data: bytes) -> bytes:
    """Minimal pure-Python Keccak-256 (EIP-55 uses keccak, not NIST SHA-3)."""
    # Keccak-f[1600] round constants
    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    ROT = [
        [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
    ]

    def rot64(v, n):
        return ((v << n) | (v >> (64 - n))) & 0xFFFFFFFFFFFFFFFF

    def keccak_f(st):
        for rc in RC:
            # Theta
            c = [st[x][0] ^ st[x][1] ^ st[x][2] ^ st[x][3] ^ st[x][4] for x in range(5)]
            d = [c[(x - 1) % 5] ^ rot64(c[(x + 1) % 5], 1) for x in range(5)]
            st = [[st[x][y] ^ d[x] for y in range(5)] for x in range(5)]
            # Rho + Pi
            b = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    b[y][(2 * x + 3 * y) % 5] = rot64(st[x][y], ROT[x][y])
            # Chi
            st = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
            # Iota
            st[0][0] ^= rc
        return st

    rate = 136  # rate in bytes for keccak-256
    # Padding (Keccak, not SHA-3 — uses 0x01 not 0x06)
    msg = bytearray(data)
    msg.append(0x01)
    while len(msg) % rate != 0:
        msg.append(0x00)
    msg[-1] |= 0x80

    state = [[0] * 5 for _ in range(5)]
    for block_start in range(0, len(msg), rate):
        block = msg[block_start:block_start + rate]
        words = struct.unpack_from("<17Q", bytes(block))
        for i, w in enumerate(words):
            state[i % 5][i // 5] ^= w
        state = keccak_f(state)

    # Squeeze 32 bytes
    out = bytearray()
    for y in range(5):
        for x in range(5):
            out += struct.pack("<Q", state[x][y])
            if len(out) >= 32:
                return bytes(out[:32])
    return bytes(out[:32])


def _to_checksum_address(address: str) -> str:
    """Apply EIP-55 checksum to an Ethereum address (pure Python, no web3 dependency)."""
    addr = address.lower().lstrip("0x")
    h = _keccak256(addr.encode()).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(addr))
WALLETS_PATH = Path(__file__).resolve().parent.parent.parent / "bronze" / "financial" / "enswallets.json"


def _load_wallets() -> dict:
    """Load the enswallets.json registry."""
    with open(WALLETS_PATH) as f:
        return json.load(f)


def _get_all_addresses(wallets: dict) -> list[dict]:
    """Flatten all wallet entries into a list of {name, address, working_group, type}."""
    entries = []
    for contract in wallets.get("operational_contracts", []):
        entries.append({
            "name": contract["name"],
            "ens_name": contract.get("ens_name"),
            "address": contract["address"],
            "working_group": None,
            "wallet_type": contract["type"],
        })
    for endow in wallets.get("endowment", []):
        entries.append({
            "name": endow["name"],
            "ens_name": endow.get("ens_name"),
            "address": endow["address"],
            "working_group": None,
            "wallet_type": endow["type"],
        })
    for ms in wallets.get("working_group_multisigs", []):
        entries.append({
            "name": ms["name"],
            "ens_name": ms.get("ens_name"),
            "address": ms["address"],
            "working_group": ms.get("working_group"),
            "wallet_type": "multisig",
        })
    return entries


def _safe_get(url: str, params: dict | None = None, *, retries: int = 3) -> dict | list:
    """GET request to Safe Transaction Service with retry logic."""
    try:
        resp = requests.get(url, params=params, timeout=30)
    except (requests.ConnectionError, requests.Timeout):
        if retries <= 0:
            raise
        logger.warning("Request failed, retrying (%d left)", retries)
        time.sleep(REQUEST_DELAY * 3)
        return _safe_get(url, params, retries=retries - 1)

    if resp.status_code == 429:
        logger.warning("Rate limited, backing off 30s")
        time.sleep(30)
        return _safe_get(url, params, retries=retries)

    if resp.status_code == 404:
        return {}

    if resp.status_code == 422:
        msg = f"[SAFE] 422 for {url} — not a valid Safe address, skipping"
        print(msg, flush=True)
        print(msg, file=sys.stderr, flush=True)
        logger.warning(msg)
        return {}

    if not resp.ok:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        msg = f"[SAFE] HTTP {resp.status_code} for {url}: {err_body}"
        print(msg, flush=True)
        print(msg, file=sys.stderr, flush=True)
        logger.error(msg)

    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Balances — fetch ETH + ENS + USDC balances for all wallets
# ---------------------------------------------------------------------------


def _fetch_safe_balances(address: str) -> dict:
    """Fetch token balances for a single Safe address via the Safe TX Service."""
    address = _to_checksum_address(address)
    url = f"{SAFE_TX_SERVICE_URL}/api/v1/safes/{address}/balances/usd/"
    data = _safe_get(url)
    if not isinstance(data, list):
        return {"ETH": 0.0, "ENS": 0.0, "USDC": 0.0}

    balances = {"ETH": 0.0, "ENS": 0.0, "USDC": 0.0}
    for item in data:
        token_addr = item.get("tokenAddress")
        balance_raw = int(item.get("balance", "0"))

        if token_addr is None:
            # Native ETH
            balances["ETH"] = round(balance_raw / 1e18, 4)
        elif token_addr.lower() in TOKEN_SYMBOLS:
            symbol = TOKEN_SYMBOLS[token_addr.lower()]
            decimals = TOKEN_DECIMALS[token_addr.lower()]
            balances[symbol] = round(balance_raw / (10 ** decimals), 4)

    return balances


def fetch_all_balances() -> list[dict]:
    """Fetch fresh ETH/ENS/USDC balances for every wallet in enswallets.json.

    Returns list of dicts with keys:
        name, ens_name, address, working_group, wallet_type, balances {ETH, ENS, USDC}
    """
    wallets = _load_wallets()
    entries = _get_all_addresses(wallets)
    results = []

    for entry in entries:
        address = entry["address"]
        logger.info("Fetching balances for %s (%s)", entry["name"], address)
        balances = _fetch_safe_balances(address)
        results.append({
            **entry,
            "balances": balances,
        })
        time.sleep(REQUEST_DELAY)

    return results


# ---------------------------------------------------------------------------
# 2. Multisig transactions — fetch executed transactions for Safe wallets
# ---------------------------------------------------------------------------


def _fetch_safe_transactions(address: str) -> list[dict]:
    """Fetch all executed multisig transactions for a Safe address.

    Paginates through the Safe Transaction Service API.
    Returns raw transaction dicts.
    """
    address = _to_checksum_address(address)
    url = f"{SAFE_TX_SERVICE_URL}/api/v1/safes/{address}/multisig-transactions/"
    all_txs = []
    params = {"executed": "true", "limit": 100, "ordering": "-executionDate"}

    while url:
        data = _safe_get(url, params)
        if not isinstance(data, dict):
            break

        results = data.get("results", [])
        all_txs.extend(results)
        logger.info("Fetched %d transactions (total: %d)", len(results), len(all_txs))

        url = data.get("next")
        params = None  # next URL already includes query params
        time.sleep(REQUEST_DELAY)

    return all_txs


def _classify_transfer(tx: dict, safe_address: str, all_safe_addresses: set[str]) -> dict:
    """Parse a Safe multisig transaction into a flat, tagged record.

    Handles native ETH sends and ERC-20 token transfers.
    """
    safe_addr_lower = safe_address.lower()
    to_addr = (tx.get("to") or "").lower()
    value_wei = int(tx.get("value") or "0")
    execution_date = tx.get("executionDate", "")[:10]  # YYYY-MM-DD

    # Check for ERC-20 transfers in decoded data
    transfers = []

    # Native ETH transfer
    if value_wei > 0:
        transfers.append({
            "token": "ETH",
            "amount": round(value_wei / 1e18, 6),
            "to_address": to_addr,
        })

    # Parse ERC-20 transfers from dataDecoded
    data_decoded = tx.get("dataDecoded")
    if data_decoded:
        method = data_decoded.get("method", "")
        params = {p["name"]: p["value"] for p in data_decoded.get("parameters", [])}

        if method == "transfer":
            token_addr = to_addr  # For ERC-20, 'to' is the token contract
            to_recipient = (params.get("to") or params.get("_to") or "").lower()
            raw_value = int(params.get("value") or params.get("_value") or "0")

            symbol = TOKEN_SYMBOLS.get(token_addr, "UNKNOWN")
            decimals = TOKEN_DECIMALS.get(token_addr, 18)
            amount = round(raw_value / (10 ** decimals), 4)

            transfers.append({
                "token": symbol,
                "amount": amount,
                "to_address": to_recipient,
            })

        elif method == "multiSend":
            # Multi-send: iterate internal transactions
            for internal_tx in data_decoded.get("parameters", [{}])[0].get("valueDecoded", []):
                int_to = (internal_tx.get("to") or "").lower()
                int_value = int(internal_tx.get("value") or "0")

                int_decoded = internal_tx.get("dataDecoded")
                if int_decoded and int_decoded.get("method") == "transfer":
                    int_params = {p["name"]: p["value"] for p in int_decoded.get("parameters", [])}
                    token_addr = int_to
                    to_recipient = (int_params.get("to") or int_params.get("_to") or "").lower()
                    raw_value = int(int_params.get("value") or int_params.get("_value") or "0")

                    symbol = TOKEN_SYMBOLS.get(token_addr, "UNKNOWN")
                    decimals = TOKEN_DECIMALS.get(token_addr, 18)
                    amount = round(raw_value / (10 ** decimals), 4)

                    transfers.append({
                        "token": symbol,
                        "amount": amount,
                        "to_address": to_recipient,
                    })
                elif int_value > 0:
                    transfers.append({
                        "token": "ETH",
                        "amount": round(int_value / 1e18, 6),
                        "to_address": int_to,
                    })

    records = []
    for xfer in transfers:
        to_lower = xfer["to_address"]
        is_internal = to_lower in all_safe_addresses
        category = "Internal Transfer" if is_internal else "Services"

        records.append({
            "safe_address": safe_address,
            "tx_hash": tx.get("transactionHash") or tx.get("safeTxHash", ""),
            "direction": "outgoing",
            "token": xfer["token"],
            "amount": xfer["amount"],
            "to_address": xfer["to_address"],
            "from_address": safe_address,
            "category": category,
            "description": "",
            "date": execution_date,
            "nonce": tx.get("nonce"),
            "block_number": tx.get("blockNumber"),
        })

    # If no transfers were parsed, still record the transaction
    if not records:
        records.append({
            "safe_address": safe_address,
            "tx_hash": tx.get("transactionHash") or tx.get("safeTxHash", ""),
            "direction": "outgoing",
            "token": "ETH",
            "amount": round(value_wei / 1e18, 6),
            "to_address": to_addr,
            "from_address": safe_address,
            "category": "Other",
            "description": data_decoded.get("method", "") if data_decoded else "",
            "date": execution_date,
            "nonce": tx.get("nonce"),
            "block_number": tx.get("blockNumber"),
        })

    return records


def fetch_all_safe_transactions() -> list[dict]:
    """Fetch and classify all multisig transactions across ENS DAO Safe wallets.

    Reads enswallets.json for the list of multisig addresses, fetches their
    transaction history from Safe Transaction Service, and classifies each
    transfer as Internal Transfer or Services based on whether the recipient
    is another known DAO wallet.

    Returns list of flat dicts with keys:
        safe_address, safe_name, safe_ens_name, working_group,
        tx_hash, direction, token, amount, to_address, from_address,
        category, description, date, nonce, block_number
    """
    wallets = _load_wallets()
    multisigs = wallets.get("working_group_multisigs", [])

    # Build lookup sets for classification
    all_safe_addresses = set()
    for ms in multisigs:
        all_safe_addresses.add(ms["address"].lower())
    for contract in wallets.get("operational_contracts", []):
        all_safe_addresses.add(contract["address"].lower())
    for endow in wallets.get("endowment", []):
        all_safe_addresses.add(endow["address"].lower())

    all_records = []
    for ms in multisigs:
        address = ms["address"]
        logger.info("Fetching transactions for %s (%s)", ms["name"], address)

        raw_txs = _fetch_safe_transactions(address)
        logger.info("Got %d raw transactions for %s", len(raw_txs), ms["name"])

        for tx in raw_txs:
            records = _classify_transfer(tx, address, all_safe_addresses)
            for rec in records:
                rec["safe_name"] = ms["name"]
                rec["safe_ens_name"] = ms.get("ens_name")
                rec["working_group"] = ms.get("working_group")
            all_records.extend(records)

        time.sleep(REQUEST_DELAY)

    # Sort by date descending, then by safe name
    all_records.sort(key=lambda r: (r["date"], r["safe_name"]), reverse=True)

    logger.info("Total transaction records: %d", len(all_records))
    return all_records
