"""
Avalanche x402 + ERC-8004 SDK integration — unit tests (no network writes, no real USDC).

Covers the REAL SDK surface: the official x402 SDK gates the server (the 402 challenge lives in the
`payment-required` response header), the canonical web3 ERC-8004 client (`erc8004_client`) replaces
bnbagent on the identity path, and the lean x402_cmc reads stay. Settlement (on-chain) is opt-in in
tests/test_x402_real_integration.py. conftest forces x402_enabled=False so nothing settles here.
"""

from __future__ import annotations

import base64
import json

from ictbot.settings import Settings, settings

_TEST_ADDR = "0xA9aa558b0a8006390f01A89824832086C080904a"
FUJI_USDC = "0x5425890298aed601595a70AB815c96711a31Bc65"
FUJI_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"


def _decode_challenge(resp):
    """The x402 SDK puts the 402 challenge in the base64 `payment-required` response header."""
    hdr = resp.headers.get("payment-required")
    return json.loads(base64.b64decode(hdr).decode()) if hdr else None


# --------------------------------------------------------------------------- #
# Config defaults (fresh Settings, independent of the dev .env)
# --------------------------------------------------------------------------- #
def test_avax_settings_defaults():
    s = Settings(_env_file=None)
    assert s.x402_network == "eip155:43113"
    assert s.x402_usdc_avax_address == FUJI_USDC
    assert s.erc8004_registry_avax == FUJI_REGISTRY
    assert s.avax_rpc_url.endswith("/ext/bc/C/rpc")
    assert "ultravioletadao" in s.x402_facilitator_url
    assert Settings(_env_file=None, AGENT_NETWORK="avax-testnet").agent_network == "avax-testnet"
    assert Settings(_env_file=None, AGENT_NETWORK="avax").agent_network == "avax"


# --------------------------------------------------------------------------- #
# Lean x402 consumer reads
# --------------------------------------------------------------------------- #
def test_x402_consumer_targets_avalanche():
    from ictbot.data import x402_cmc

    assert x402_cmc.PREFERRED_NETWORK == settings.x402_network
    assert x402_cmc.base_usdc_balance is x402_cmc.usdc_balance


# --------------------------------------------------------------------------- #
# ERC-8004 — canonical web3 client (no bnbagent on the avax path)
# --------------------------------------------------------------------------- #
def test_erc8004_client_surface():
    from ictbot.agent import erc8004_client as e

    assert e.available() is True
    assert e._chain_id() == 43113  # Fuji by default (agent_network not avax → still Fuji registry)
    for name in ("register", "set_metadata", "get_metadata", "token_uri", "owner_of",
                 "build_agent_uri", "available"):
        assert callable(getattr(e, name))


def test_erc8004_write_path_offline():
    """Prove the ERC-8004 mint + heartbeat write path is correct WITHOUT funds: web3 resolves the
    canonical `register` overloads + `setMetadata`, ABI-encodes the two register forms to DISTINCT
    selectors, and the `Registered(agentId, agentURI, owner)` event decodes to the agentId — exactly
    the receipt-parse `erc8004_client.register()` relies on to return the minted agentId."""
    from eth_abi import encode as abi_encode
    from web3 import Web3
    from web3.logs import DISCARD

    from ictbot.agent import erc8004_client as e

    reg = e._registry(e._w3())
    # 1) overload resolution + arg binding (deterministic, no network)
    assert reg.get_function_by_signature("register(string)").fn_name == "register"
    assert reg.get_function_by_signature("register(string,(string,bytes)[])").fn_name == "register"
    assert reg.get_function_by_signature("setMetadata(uint256,string,bytes)").fn_name == "setMetadata"
    reg.functions.register("uri")                              # register(string)
    reg.functions.register("uri", [("served_jobs", b"1")])     # register(string, MetadataEntry[])
    reg.functions.setMetadata(1, "heartbeat", b'{"ts":1}')     # the heartbeat write
    assert reg.encode_abi("register", args=["uri"]) != reg.encode_abi(
        "register", args=["uri", [("k", b"v")]]
    ), "the two register overloads must encode to different selectors"

    # 2) the Registered event receipt-parse (the mint reads agentId from this)
    log = {
        "address": reg.address,
        "topics": [
            Web3.keccak(text="Registered(uint256,string,address)"),
            (4242).to_bytes(32, "big"),                # indexed agentId
            bytes(12) + bytes.fromhex("ab" * 20),      # indexed owner
        ],
        "data": abi_encode(["string"], ["data:application/json,{}"]),
        "logIndex": 0, "transactionIndex": 0, "transactionHash": b"\x11" * 32,
        "blockHash": b"\x22" * 32, "blockNumber": 1, "removed": False,
    }
    decoded = reg.events.Registered().process_receipt({"logs": [log]}, errors=DISCARD)
    assert decoded and int(decoded[0]["args"]["agentId"]) == 4242


def test_identity_is_avax():
    from ictbot.agent import identity

    assert identity._is_avax("avax-testnet") is True
    assert identity._is_avax("avax") is True
    assert identity._is_avax("bsc") is False


def test_identity_avax_uses_erc8004_adapter(monkeypatch):
    """On avax, identity._agent returns the ERC-8004 web3 adapter (not bnbagent) — preserving the
    set_metadata/get_metadata/register_agent/generate_agent_uri seam the heartbeat path + tests use."""
    from ictbot.agent import identity

    monkeypatch.setattr(settings, "agent_network", "avax-testnet", raising=False)
    monkeypatch.setattr(settings, "agent_private_key", "0x" + "11" * 32, raising=False)
    a = identity._agent("avax-testnet")
    assert type(a).__name__ == "_Erc8004AvaxAdapter"
    assert all(hasattr(a, m) for m in ("set_metadata", "get_metadata", "register_agent", "generate_agent_uri"))
    assert identity._identity_available("avax-testnet") is True
    assert identity._identity_signable("avax-testnet") is True
    # the agent address derives from the pinned key via eth-account (no bnbagent keystore)
    assert (identity._identity_address() or "").startswith("0x")


# --------------------------------------------------------------------------- #
# Snowtrace explorer base
# --------------------------------------------------------------------------- #
def test_explorer_base_snowtrace(monkeypatch):
    from ictbot.api import reads

    monkeypatch.setattr(settings, "agent_network", "avax-testnet", raising=False)
    assert reads._explorer_base() == "https://testnet.snowtrace.io/tx/"
    monkeypatch.setattr(settings, "agent_network", "avax", raising=False)
    assert reads._explorer_base() == "https://snowtrace.io/tx/"


# --------------------------------------------------------------------------- #
# The x402 SERVER (the SDK middleware gates the route)
# --------------------------------------------------------------------------- #
def test_server_stats_shape():
    from ictbot.api import x402_server

    st = x402_server.server_stats()
    for k in ("enabled", "served_jobs", "revenue_usdc", "last_settlement_tx", "last_ts", "price_usdc"):
        assert k in st


def test_server_stats_counts_settled_rows(monkeypatch, tmp_path):
    """server_stats() drives the dashboard's x402-server panel — assert it actually parses a SETTLED
    row (served_jobs + USDC revenue + last tx) and ignores non-SETTLED events, on an ISOLATED ledger
    so the assertion is deterministic (not coupled to the real accumulating provider ledger)."""
    from ictbot.api import x402_server

    tx = "0x14ddec0e2b201ed11a4209e4ed90b46a43047ba93550c5754ea845c91efe55f4"
    ledger = tmp_path / "server_jobs.jsonl"
    ledger.write_text(
        '{"ts": "2026-06-17T18:52:06Z", "event": "REJECTED", "reason": "recipient mismatch"}\n'
        '{"ts": "2026-06-22T09:51:33Z", "event": "SETTLED", "tx": "' + tx + '", '
        '"value": 10000, "payer": "0xA9aa558b0a8006390f01A89824832086C080904a"}\n'
    )
    monkeypatch.setattr(x402_server, "SERVER_LEDGER", ledger)
    monkeypatch.setattr(settings, "x402_price_units", 10000, raising=False)

    st = x402_server.server_stats()
    assert st["served_jobs"] == 1                       # the REJECTED row must NOT count
    assert st["revenue_usdc"] == 0.01                   # 10000 units / 1e6
    assert st["last_settlement_tx"] == tx
    assert st["last_ts"] == "2026-06-22T09:51:33Z"
    assert st["price_usdc"] == 0.01


def test_http_unpaid_returns_402_with_sdk_challenge():
    """The x402 SDK middleware returns 402 + an x402 challenge in the `payment-required` header,
    advertising the Avalanche Fuji USDC payment requirement."""
    from fastapi.testclient import TestClient

    from ictbot.api.app import app

    r = TestClient(app).get("/x402/regime-report")
    assert r.status_code == 402
    challenge = _decode_challenge(r)
    assert challenge is not None, "no payment-required header on the 402"
    assert challenge["x402Version"] == 2
    acc = challenge["accepts"][0]
    assert acc["scheme"] == "exact"
    assert acc["network"] == "eip155:43113"
    assert acc["asset"] == FUJI_USDC
    assert acc["amount"] == "10000"
    assert acc["extra"]["name"] == "USD Coin" and acc["extra"]["version"] == "2"


def test_http_bad_payment_rejected():
    from fastapi.testclient import TestClient

    from ictbot.api.app import app

    bad = base64.b64encode(b'{"not":"a valid x402 payment"}').decode()
    r = TestClient(app).get("/x402/regime-report", headers={"X-PAYMENT": bad})
    assert r.status_code == 402  # the SDK rejects the malformed payment, re-challenges


def test_http_info_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from ictbot.api.app import app

    monkeypatch.setattr(settings, "agent_identity_address", _TEST_ADDR, raising=False)
    r = TestClient(app).get("/x402/info")
    assert r.status_code == 200
    info = r.json()
    assert info["network"] == settings.x402_network
    assert info["asset"] == settings.x402_usdc_avax_address
    assert info["pay_to"].lower() == _TEST_ADDR.lower()
    assert info["sdk"] == "x402"
    # served_jobs here reads the REAL accumulating provider ledger (live demo settlements land here),
    # so this route asserts only the shape; the parse is covered deterministically by
    # test_server_stats_counts_settled_rows above.
    assert isinstance(info["stats"]["served_jobs"], int)
