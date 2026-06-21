"""Tests for the lean x402 payment-wallet reads + the official x402 SDK consumer.

The EIP-3009 signing that used to live here moved to the official `x402` Python SDK (see
api/x402_server.pay_and_fetch). What remains in x402_cmc is the chain-agnostic, key-free reads the
dashboard imports. These offline tests assert the lean surface + that the SDK client wires up.
"""

from __future__ import annotations

from ictbot.settings import settings

# Throwaway well-known test key (Hardhat account #0) — no funds; offline signing only.
TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def test_consumer_targets_avalanche():
    from ictbot.data import x402_cmc as x

    assert x.PREFERRED_NETWORK == settings.x402_network
    assert x.AVAX_CHAIN_ID == x._preferred_chain_id()


def test_base_usdc_balance_is_avalanche_alias():
    from ictbot.data import x402_cmc as x

    assert x.base_usdc_balance is x.usdc_balance


def test_bnbagent_signing_is_removed():
    """The bnbagent EIP-3009 signing path is gone — signing now lives in the x402 SDK."""
    from ictbot.data import x402_cmc as x

    for name in ("_signer", "_wallet", "_signing_policy", "build_payment", "pick_accept",
                 "fetch_x402", "fetch_challenge", "dex_search", "_payment_header"):
        assert not hasattr(x, name), f"{name} should be gone (signing moved to the x402 SDK)"


def test_available_reflects_flag(monkeypatch):
    from ictbot.data import x402_cmc as x

    monkeypatch.setattr(settings, "x402_enabled", False, raising=False)
    assert x.available() is False
    monkeypatch.setattr(settings, "x402_enabled", True, raising=False)
    assert x.available() is True


def test_x402_sdk_consumer_constructs_offline():
    """The official x402 SDK consumer (x402ClientSync + EthAccountSigner) builds + registers the
    exact-EVM scheme with NO network — proving the SDK signing path is wired (deterministic, offline)."""
    from eth_account import Account
    from x402 import x402ClientSync
    from x402.mechanisms.evm import EthAccountSigner
    from x402.mechanisms.evm.exact.register import register_exact_evm_client

    client = x402ClientSync()
    register_exact_evm_client(client, EthAccountSigner(Account.from_key(TEST_KEY)))
    assert client is not None
