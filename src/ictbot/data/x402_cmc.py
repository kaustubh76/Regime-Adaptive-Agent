"""
x402 payment-wallet reads for Avalanche (the consumer SIGNING now lives in the official x402 SDK).

Historically this module hand-signed EIP-3009 USDC payments via a BNB-chain SDK's X402Signer. The
Avalanche port moves ALL x402 signing to the official `x402` Python SDK — the server is gated by the
SDK's payment middleware (`api/x402_server`), and the agent pays its own server via the SDK's client
(`api/x402_server.pay_and_fetch`). No bnbagent here anymore.

What remains is the chain-agnostic, key-free bits the dashboard + readiness checks import: the x402
payment-wallet ADDRESS (the agent identity wallet, also the server's payTo) and its USDC balance on
Avalanche. Both are pure web3 reads — no private key, safe on the read-only deploy.
"""

from __future__ import annotations

import logging

from ictbot.settings import settings

log = logging.getLogger(__name__)

# The x402 payment leg targets Avalanche C-Chain (USDC via EIP-3009). Network from settings, so
# Fuji <-> mainnet is one env flip. Kept here because the dashboard/readiness code imports them.
PREFERRED_NETWORK = settings.x402_network  # CAIP-2, e.g. "eip155:43113" (Fuji)


def _preferred_chain_id() -> int:
    """Numeric chainId from the configured x402 network ("eip155:43113" -> 43113; Fuji fallback)."""
    try:
        return int(str(settings.x402_network).split(":")[-1])
    except (ValueError, AttributeError):
        return 43113


AVAX_CHAIN_ID = _preferred_chain_id()


def available() -> bool:
    """True iff the x402 payment path is enabled. (The official x402 SDK now owns signing/settling;
    this just reflects the X402_ENABLED flag for the readiness checks that gate the balance read.)"""
    return bool(settings.x402_enabled)


def payment_address() -> str | None:
    """The address x402 pays FROM and the server's payTo — the agent identity wallet. Fund THIS with
    USDC + AVAX on Avalanche (Fuji 43113). Uses the DISPLAY address (public AGENT_IDENTITY_ADDRESS
    when set) so a read-only dashboard can show it + read the balance with NO key."""
    from ictbot.agent.identity import display_address

    return display_address()


def usdc_balance(address: str | None = None) -> float | None:
    """USDC balance (Avalanche, 6dp) of the x402 payment wallet — to confirm funding landed.
    Best-effort read via AVAX_RPC_URL; None on any failure (never raises)."""
    addr = address or payment_address()
    if not addr:
        return None
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(settings.avax_rpc_url))
        usdc = Web3.to_checksum_address(settings.x402_usdc_avax_address)
        erc20 = w3.eth.contract(
            address=usdc,
            abi=[
                {
                    "constant": True,
                    "inputs": [{"name": "a", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function",
                }
            ],
        )
        raw = erc20.functions.balanceOf(Web3.to_checksum_address(addr)).call()
        return raw / 1e6
    except Exception:
        return None


# Back-compat alias: callers (api/onchain.py, api/reads.py, scripts/*) still import
# `base_usdc_balance`; it now reads the Avalanche USDC balance (the x402 budget moved chains).
base_usdc_balance = usdc_balance
