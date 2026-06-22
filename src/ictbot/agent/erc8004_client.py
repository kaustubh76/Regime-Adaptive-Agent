"""
ERC-8004 Identity Registry client for Avalanche C-Chain — REAL canonical-contract integration.

No mature Avalanche-supporting ERC-8004 Python SDK exists (chaoschain-sdk excludes Fuji), so the
identity layer talks to the CANONICAL reference registry directly via web3.py + the official ABI
(vendored from erc-8004/erc-8004-contracts at `abis/IdentityRegistry.json`). This replaces the
BNB-chain `bnbagent` SDK on the Avalanche path.

The registry is an ERC-721 + URIStorage contract deployed deterministically at the same vanity
address on every testnet (`0x8004A818…` on Fuji) / mainnet (`0x8004A169…`). We call:
  - register(agentURI[, MetadataEntry[]]) -> agentId   (the agentId is emitted in the
    `Registered(agentId, agentURI, owner)` event — a tx can't return the uint256, so we parse it)
  - setMetadata(agentId, key, bytes)  /  getMetadata(agentId, key) -> bytes   (heartbeats live here)
  - tokenURI(agentId) / ownerOf(agentId)   (views)

Signing is local eth-account over AGENT_PRIVATE_KEY (or the de-risk keyfile); native AVAX gas
(EIP-1559) — same pattern as scripts/avax_derisk.py. Pure read paths never need a key.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from pathlib import Path

from ictbot.settings import DATA_DIR, settings

log = logging.getLogger(__name__)

_ABI = json.loads((Path(__file__).parent / "abis" / "IdentityRegistry.json").read_text())


def _chain_id() -> int:
    """43114 for avax mainnet, else 43113 (Fuji). Mirrors identity._avax_chain_id (no import cycle)."""
    return 43114 if settings.agent_network in ("avax", "avax-mainnet") else 43113


def _w3():
    from web3 import Web3

    return Web3(Web3.HTTPProvider(settings.avax_rpc_url, request_kwargs={"timeout": 20}))


def _registry(w3):
    from web3 import Web3

    return w3.eth.contract(
        address=Web3.to_checksum_address(settings.erc8004_registry_avax), abi=_ABI
    )


def _key() -> str | None:
    """Signing key for writes: AGENT_PRIVATE_KEY, else the de-risk keyfile. None → reads only.
    Same precedence as the x402 consumer/relayer key (one agent address everywhere)."""
    if settings.agent_private_key:
        return settings.agent_private_key
    try:
        kf = Path(DATA_DIR) / "avax" / "agent_wallet.json"
        if kf.exists():
            return json.loads(kf.read_text()).get("private_key")
    except Exception:
        pass
    return None


def available() -> bool:
    """True iff web3/eth-account are importable AND a registry address is configured. (Reads work
    without a key; writes additionally need _key().)"""
    try:
        import eth_account  # noqa: F401
        import web3  # noqa: F401
    except Exception:
        return False
    return bool(settings.erc8004_registry_avax)


def _send(fn):
    """Build + sign + submit an EIP-1559 tx for a contract call, paying native AVAX gas. Returns
    (receipt, tx_hex). Raises if no signing key. Gas pattern mirrors scripts/avax_derisk.py."""
    from eth_account import Account

    key = _key()
    if not key:
        raise RuntimeError("ERC-8004 write needs AGENT_PRIVATE_KEY (or the generated keyfile)")
    w3 = _w3()
    acct = Account.from_key(key)
    try:
        gas = int(fn.estimate_gas({"from": acct.address}) * 1.3)
    except Exception:
        gas = 500_000
    # EIP-1559 fees: maxFee = 2*baseFee + priority guarantees maxFee >= priority on a quiet Fuji
    # (where gas_price*2 can fall below a fixed 1-gwei priority → "max priority fee > max fee").
    base = w3.eth.get_block("latest").get("baseFeePerGas") or w3.eth.gas_price
    priority = w3.to_wei(1, "gwei")
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": _chain_id(),
        "gas": gas,
        "maxFeePerGas": int(base) * 2 + priority,
        "maxPriorityFeePerGas": priority,
    })
    signed = Account.sign_transaction(tx, key)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    tx_hex = tx_hash.hex()
    tx_hex = tx_hex if tx_hex.startswith("0x") else "0x" + tx_hex
    return receipt, tx_hex


def register(agent_uri: str, metadata: list[dict] | None = None) -> dict:
    """Mint the agent's ERC-8004 identity NFT. `metadata` = [{"key": str, "value": str|bytes}, ...].
    Parses the `Registered(agentId, agentURI, owner)` event for the agentId (fallback: the ERC-721
    `Transfer` mint log). Returns {ok, agentId, transactionHash, agentURI} (keys the existing
    identity/register_agent callers already parse)."""
    from web3.logs import DISCARD

    w3 = _w3()
    reg = _registry(w3)
    if metadata:
        entries = [
            (m["key"], m["value"].encode() if isinstance(m["value"], str) else m["value"])
            for m in metadata
        ]
        fn = reg.functions.register(agent_uri, entries)
    else:
        fn = reg.functions.register(agent_uri)
    receipt, tx_hex = _send(fn)

    agent_id = 0
    try:
        evs = reg.events.Registered().process_receipt(receipt, errors=DISCARD)
        if evs:
            agent_id = int(evs[0]["args"]["agentId"])
    except Exception as e:  # noqa: BLE001
        log.debug("Registered event decode failed: %s", e)
    if not agent_id:  # fallback: ERC-721 mint Transfer(from=0x0, to=owner, tokenId)
        try:
            for e in reg.events.Transfer().process_receipt(receipt, errors=DISCARD):
                if int(e["args"]["from"], 16) == 0:
                    agent_id = int(e["args"]["tokenId"])
                    break
        except Exception as e:  # noqa: BLE001
            log.debug("Transfer event decode failed: %s", e)
    return {"ok": True, "agentId": agent_id, "transactionHash": tx_hex, "agentURI": agent_uri}


def set_metadata(agent_id: int, key: str, value: str | bytes) -> dict:
    """Write a metadata entry on the agent's record (e.g. the per-cycle "heartbeat" blob). Returns
    {ok, transactionHash} (identity.write_heartbeat reads `transactionHash`)."""
    value_bytes = value.encode() if isinstance(value, str) else value
    reg = _registry(_w3())
    _receipt, tx_hex = _send(reg.functions.setMetadata(int(agent_id), key, value_bytes))
    return {"ok": True, "transactionHash": tx_hex}


def get_metadata(agent_id: int, key: str) -> str | None:
    """Read a metadata entry back (view). Decodes bytes→str; None when empty/missing. Never raises."""
    try:
        raw = _registry(_w3()).functions.getMetadata(int(agent_id), key).call()
        if not raw:
            return None
        try:
            return raw.decode()
        except Exception:
            return raw.hex()
    except Exception as e:  # noqa: BLE001
        log.debug("getMetadata failed: %s", e)
        return None


def token_uri(agent_id: int) -> str | None:
    try:
        return _registry(_w3()).functions.tokenURI(int(agent_id)).call()
    except Exception:
        return None


def owner_of(agent_id: int) -> str | None:
    try:
        return _registry(_w3()).functions.ownerOf(int(agent_id)).call()
    except Exception:
        return None


def build_agent_uri(profile: dict) -> str:
    """The ERC-721 tokenURI for the identity — the agent's registration card (name, description,
    endpoints, capabilities). Returns a self-contained `data:application/json` URI (no IPFS/HTTP
    dependency); falls back to the agent's public /x402/info URL if the card is large."""
    blob = json.dumps(profile, separators=(",", ":"))
    uri = "data:application/json," + urllib.parse.quote(blob)
    if len(uri) > 8000:
        base = (settings.x402_server_url or "").rstrip("/")
        if base:
            return base + "/x402/info"
    return uri
