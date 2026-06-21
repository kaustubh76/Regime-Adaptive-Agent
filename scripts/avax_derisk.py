#!/usr/bin/env python3
"""
Avalanche de-risk + agent-wallet bootstrap (x402 / EIP-3009 settlement spike).

This is the Day-1 de-risk for the AVAX port (see AVAX_PORT_SPEC.md §6): it proves a
real USDC `transferWithAuthorization` (EIP-3009) settles on Avalanche Fuji with a tx on
testnet.snowtrace.io — the exact settle path the x402 server depends on — and it also
mints the agent's throwaway test wallet so there is ONE address to fund.

Pure web3.py + eth_account (no bnbagent coupling); never raises on an unfunded wallet —
it prints exactly what to fund and exits cleanly.

Subcommands:
    keygen   Generate (or reuse) the agent test wallet; print its address + funding links.
    balance  Print the wallet's AVAX (gas) + Fuji USDC balances.
    settle   Sign + submit a Fuji USDC transferWithAuthorization (wallet -> self) and
             print the settlement tx + Snowtrace link. Refuses cleanly if unfunded.
    domain   Verify the on-chain EIP-712 DOMAIN_SEPARATOR matches name/version (sanity).
    (no arg) keygen -> balance -> settle-if-funded.

The wallet key is written to data/avax/agent_wallet.json (chmod 600, git-ignored). Copy
AGENT_PRIVATE_KEY + AGENT_WALLET_PASSWORD into .env so the identity + x402 layers derive
the SAME address. For a real submission, fund a wallet you control — this is a test key.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

# --- Avalanche Fuji params (verified against Circle + on-chain; see AVAX_PORT_SPEC.md §5) ---
FUJI_CHAIN_ID = 43113
FUJI_RPC = os.environ.get("AVAX_RPC_URL", "https://api.avax-test.network/ext/bc/C/rpc")
FUJI_USDC = "0x5425890298aed601595a70AB815c96711a31Bc65"  # 6dp, EIP-3009, domain "USD Coin"/"2"
SNOWTRACE = "https://testnet.snowtrace.io"
USDC_DOMAIN_NAME = "USD Coin"
USDC_DOMAIN_VERSION = "2"

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = REPO_ROOT / "data" / "avax" / "agent_wallet.json"

# Minimal USDC (FiatTokenV2) ABI — only what the spike needs.
USDC_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "name", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "version", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "DOMAIN_SEPARATOR", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "bytes32"}]},
    {"name": "authorizationState", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "authorizer", "type": "address"}, {"name": "nonce", "type": "bytes32"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "transferWithAuthorization", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
         {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
         {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
         {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"}, {"name": "s", "type": "bytes32"},
     ], "outputs": []},
]


def _w3():
    from web3 import Web3

    return Web3(Web3.HTTPProvider(FUJI_RPC, request_kwargs={"timeout": 20}))


def _load_or_create_key() -> tuple[str, str]:
    """Return (private_key, address). Prefer AGENT_PRIVATE_KEY env, then the key file,
    else generate a fresh key and persist it (chmod 600). Never overwrites an existing key."""
    from eth_account import Account

    env_key = os.environ.get("AGENT_PRIVATE_KEY", "").strip()
    if env_key:
        acct = Account.from_key(env_key)
        return env_key, acct.address
    if KEY_FILE.exists():
        try:
            data = json.loads(KEY_FILE.read_text())
            pk = data["private_key"]
            return pk, Account.from_key(pk).address
        except Exception:
            pass
    # Generate fresh
    pk = "0x" + secrets.token_hex(32)
    acct = Account.from_key(pk)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(json.dumps(
        {"address": acct.address, "private_key": pk, "network": "avalanche-fuji",
         "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "note": "Throwaway Fuji test wallet. Put AGENT_PRIVATE_KEY in .env to share this "
                 "address with the identity + x402 layers."},
        indent=2,
    ))
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    # Keep the key out of git no matter where data/ sits.
    gi = KEY_FILE.parent / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
    return pk, acct.address


def _balances(w3, addr: str) -> tuple[float, float]:
    """(AVAX, USDC) balances. 0.0 on any read failure (never raises)."""
    from web3 import Web3

    avax = usdc = 0.0
    try:
        avax = float(w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(addr)), "ether"))
    except Exception:
        pass
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(FUJI_USDC), abi=USDC_ABI)
        usdc = c.functions.balanceOf(Web3.to_checksum_address(addr)).call() / 1e6
    except Exception:
        pass
    return avax, usdc


def cmd_keygen() -> int:
    pk, addr = _load_or_create_key()
    print("== Avalanche agent wallet (Fuji) ==")
    print(f"  address : {addr}")
    print(f"  keyfile : {KEY_FILE}  (git-ignored, chmod 600)")
    print(f"  explorer: {SNOWTRACE}/address/{addr}")
    print()
    print("Fund THIS address on Fuji, then re-run `settle`:")
    print("  • AVAX gas   : https://core.app/tools/testnet-faucet/  (or https://faucet.avax.network)")
    print("  • Fuji USDC  : https://faucet.circle.com  (select Avalanche Fuji)")
    print()
    print("Then put these in .env so the identity + x402 layers use the SAME address:")
    print(f"  AGENT_PRIVATE_KEY={pk}")
    print("  AGENT_WALLET_PASSWORD=<any-passphrase>   # encrypts the bnbagent identity keystore")
    print(f"  AGENT_IDENTITY_ADDRESS={addr}            # public display address (read-only dash)")
    return 0


def cmd_balance() -> int:
    _, addr = _load_or_create_key()
    avax, usdc = _balances(_w3(), addr)
    print(f"address : {addr}")
    print(f"AVAX    : {avax:.6f}   (gas)")
    print(f"USDC    : {usdc:.6f}   (Fuji {FUJI_USDC})")
    funded = avax > 0 and usdc > 0
    print(f"funded  : {'yes — ready to settle' if funded else 'NO — fund via the faucets (keygen prints links)'}")
    return 0 if funded else 2


def cmd_domain() -> int:
    """Sanity: recompute the EIP-712 domain separator and compare to the on-chain value."""
    from eth_utils import keccak
    from web3 import Web3

    w3 = _w3()
    c = w3.eth.contract(address=Web3.to_checksum_address(FUJI_USDC), abi=USDC_ABI)
    try:
        onchain = c.functions.DOMAIN_SEPARATOR().call()
        name = c.functions.name().call()
        version = c.functions.version().call()
    except Exception as e:
        print(f"could not read USDC contract: {e}", file=sys.stderr)
        return 1
    type_hash = keccak(text="EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
    computed = keccak(
        type_hash
        + keccak(text=name)
        + keccak(text=version)
        + FUJI_CHAIN_ID.to_bytes(32, "big")
        + bytes.fromhex(FUJI_USDC[2:].rjust(64, "0"))
    )
    match = computed == onchain
    print(f"USDC name/version : {name!r} / {version!r}")
    print(f"on-chain  domain  : 0x{onchain.hex()}")
    print(f"computed  domain  : 0x{computed.hex()}")
    print(f"match             : {match}")
    return 0 if match else 1


def cmd_settle(value_units: int = 10_000) -> int:
    """Sign an EIP-3009 transferWithAuthorization (wallet -> self) and submit it to Fuji USDC,
    paying AVAX gas from the same wallet. Proves the x402 settle path end-to-end. value_units is
    in USDC base units (10_000 = 0.01 USDC)."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from web3 import Web3

    pk, addr = _load_or_create_key()
    w3 = _w3()
    addr = Web3.to_checksum_address(addr)
    avax, usdc = _balances(w3, addr)
    if avax <= 0:
        print(f"✗ {addr} has 0 AVAX — fund gas first (keygen prints the faucet links).", file=sys.stderr)
        return 2
    if usdc * 1e6 < value_units:
        print(f"✗ {addr} has {usdc} USDC (< {value_units / 1e6}) — fund Fuji USDC first.", file=sys.stderr)
        return 2

    now = int(time.time())
    nonce32 = "0x" + secrets.token_hex(32)
    message = {
        "from": addr, "to": addr, "value": int(value_units),
        "validAfter": now - 60, "validBefore": now + 600, "nonce": nonce32,
    }
    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
            ],
        },
        "domain": {
            "name": USDC_DOMAIN_NAME, "version": USDC_DOMAIN_VERSION,
            "chainId": FUJI_CHAIN_ID, "verifyingContract": FUJI_USDC,
        },
        "primaryType": "TransferWithAuthorization",
        "message": message,
    }
    signed = Account.sign_message(encode_typed_data(full_message=typed), private_key=pk)
    v, r, s = signed.v, signed.r.to_bytes(32, "big"), signed.s.to_bytes(32, "big")

    usdc_c = w3.eth.contract(address=Web3.to_checksum_address(FUJI_USDC), abi=USDC_ABI)
    tx = usdc_c.functions.transferWithAuthorization(
        addr, addr, int(value_units), message["validAfter"], message["validBefore"],
        bytes.fromhex(nonce32[2:]), v, r, s,
    ).build_transaction({
        "from": addr,
        "nonce": w3.eth.get_transaction_count(addr),
        "chainId": FUJI_CHAIN_ID,
        "gas": 200_000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(1, "gwei"),
    })
    signed_tx = Account.sign_transaction(tx, pk)
    raw = getattr(signed_tx, "raw_transaction", None) or signed_tx.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    h = tx_hash.hex()
    if not h.startswith("0x"):
        h = "0x" + h
    print(f"→ submitted transferWithAuthorization {value_units / 1e6} USDC ({addr} → self)")
    print(f"  tx: {SNOWTRACE}/tx/{h}")
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    ok = rcpt.get("status") == 1
    print(f"  status: {'SUCCESS ✓ EIP-3009 settles on Fuji' if ok else 'REVERTED ✗'} (block {rcpt.get('blockNumber')})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Avalanche x402/EIP-3009 de-risk + wallet bootstrap")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("keygen")
    sub.add_parser("balance")
    sub.add_parser("domain")
    p_settle = sub.add_parser("settle")
    p_settle.add_argument("--value", type=int, default=10_000, help="USDC base units (10000 = 0.01 USDC)")
    args = ap.parse_args()

    if args.cmd == "keygen":
        return cmd_keygen()
    if args.cmd == "balance":
        return cmd_balance()
    if args.cmd == "domain":
        return cmd_domain()
    if args.cmd == "settle":
        return cmd_settle(args.value)
    # default: keygen -> balance -> settle-if-funded
    cmd_keygen()
    print()
    rc = cmd_balance()
    if rc == 0:
        print()
        return cmd_settle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
