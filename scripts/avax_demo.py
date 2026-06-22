#!/usr/bin/env python3
"""
One-shot Avalanche headline demo — the agent PAYS and GETS PAID, then proves its identity.

Run AFTER funding the agent wallet (see `scripts/avax_derisk.py keygen`):
    python scripts/avax_demo.py            # full loop
    python scripts/avax_demo.py --no-mint  # x402 pay→get-paid only (no identity gas)
    python scripts/avax_demo.py --no-x402  # ERC-8004 mint + heartbeat only

Steps (all REAL, on Avalanche Fuji):
  [1] x402: the agent pays its OWN x402 server USDC to read the CMC Regime Report — one funded
      agent paying another, the report changing hands on-chain (via the official x402 SDK client +
      the Ultravioleta facilitator). Needs a LIVE server (`make api`).
  [2] ERC-8004: mint the agent's Identity NFT on the canonical Fuji registry via web3.py (reused if
      AGENT_ID is set) + write an on-chain heartbeat (set_metadata).

Prints every settlement / mint / heartbeat tx as a testnet.snowtrace.io link. Never crashes a
later step if an earlier one fails — each step is independently guarded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEY_FILE = REPO / "data" / "avax" / "agent_wallet.json"
JOURNAL = REPO / "data" / "journal" / "allocator_journal.jsonl"
SNOWTRACE = "https://testnet.snowtrace.io"


def _load_key() -> tuple[str | None, str | None]:
    if KEY_FILE.exists():
        try:
            d = json.loads(KEY_FILE.read_text())
            return d.get("private_key"), d.get("address")
        except Exception:
            pass
    return None, None


def _configure(settings, key: str, addr: str) -> None:
    """Point the identity + x402 layers at the funded Fuji wallet for this run (mutates the
    in-process settings singleton — no .env edit needed to demo)."""
    settings.agent_network = "avax-testnet"
    settings.agent_private_key = key
    if not settings.agent_wallet_password:
        settings.agent_wallet_password = "avax-demo"
    settings.agent_identity_address = addr
    settings.x402_server_enabled = True
    settings.x402_enabled = True
    # The ERC-8004 agentId is per-chain — IGNORE the .env AGENT_ID (that's the BNB-chain identity) and
    # use the Fuji one persisted in the keyfile after the first mint (absent → 0 → mint a fresh one).
    try:
        settings.agent_id = int(json.loads(KEY_FILE.read_text()).get("agent_id") or 0)
    except Exception:
        settings.agent_id = 0


def _persist_agent_id(aid: int) -> None:
    """Save the minted Fuji agentId to the keyfile so later runs reuse it (heartbeat-only)."""
    try:
        d = json.loads(KEY_FILE.read_text())
        d["agent_id"] = int(aid)
        KEY_FILE.write_text(json.dumps(d, indent=2))
    except Exception:
        pass


def _tx_of(res) -> str | None:
    if not isinstance(res, dict):
        return None
    for k in ("transactionHash", "txHash", "tx", "hash"):
        v = res.get(k)
        if v:
            return str(v)
    return None


def _agent_id_of(res) -> int:
    if not isinstance(res, dict):
        return 0
    for k in ("agentId", "agent_id", "tokenId", "id"):
        v = res.get(k)
        try:
            if v is not None and int(v) > 0:
                return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def _run_x402(settings) -> str | None:
    """The agent pays its OWN x402 server via the official x402 SDK client (auto 402 → sign EIP-3009
    → settle via the Ultravioleta facilitator on Fuji). Needs a LIVE server (`make api`, or set
    X402_SERVER_URL) — the SDK client hits a real URL and the facilitator settles on-chain."""
    from ictbot.api.x402_server import pay_and_fetch

    base = settings.x402_server_url or "http://127.0.0.1:8000"
    report = pay_and_fetch(base)
    if not report:
        print(f"  ✗ no settlement — is the x402 server running? (`make api`; server={base})", file=sys.stderr)
        print("    start it in another shell, fund the wallet, then re-run.", file=sys.stderr)
        return None
    tx = (report.get("_x402") or {}).get("tx")
    print(f"  ✓ paid + served — regime_score={report.get('regime_score')}, status={report.get('status')}, tx={tx}")
    return tx


def _run_identity(settings) -> list[tuple[str, str]]:
    """Mint the ERC-8004 identity (reused if AGENT_ID set) + write one heartbeat."""
    from ictbot.agent import identity

    out: list[tuple[str, str]] = []
    if not identity._identity_available():
        print('  ✗ ERC-8004 backend unavailable (`pip install -e ".[x402]"`)', file=sys.stderr)
        return out

    aid = int(settings.agent_id or 0)
    if aid <= 0:
        try:
            res = identity.register_identity()
            tx = _tx_of(res)
            aid = _agent_id_of(res)
            settings.agent_id = aid
            if tx:
                out.append(("ERC-8004 mint", tx))
            if aid:
                _persist_agent_id(aid)  # later runs reuse it (heartbeat-only)
            print(f"  ✓ minted identity — agent_id={aid or '?'} (persisted to the keyfile for reuse)")
            if not aid:
                print(f"    (could not parse agent_id; raw result: {json.dumps(res, default=str)[:200]})")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ mint failed: {type(e).__name__}: {e}", file=sys.stderr)
            return out
    else:
        print(f"  • reusing AGENT_ID={aid}")

    if aid > 0:
        res = identity.write_heartbeat(
            "AVAX x402 demo: paid USDC for CMC data + got paid USDC for the regime report.",
            nav=1000.0, agent_id=aid,
        )
        if res and res.get("ok") and res.get("tx"):
            out.append(("ERC-8004 heartbeat", res["tx"]))
            print("  ✓ heartbeat written on-chain")
            _journal_heartbeat(ok=True, tx=res["tx"])  # reflect it on the dashboard, not just on-chain
            try:
                back = identity.read_heartbeat(aid)
                if back:
                    print(f"    read-back: {json.dumps(back)[:160]}")
            except Exception:
                pass
        else:
            print(f"  ✗ heartbeat failed: {(res or {}).get('error')}", file=sys.stderr)
            _journal_heartbeat(ok=False, error=(res or {}).get("error"))
    return out


def _journal_heartbeat(ok: bool, tx: str | None = None, error: str | None = None) -> None:
    """Stamp the on-chain heartbeat result onto the allocator journal's latest tick so the
    dashboard's IdentityCard reflects it (write_heartbeat settles on-chain but doesn't journal)."""
    import time

    try:
        from ictbot.agent.heartbeat_journal import record_heartbeat

        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record_heartbeat(JOURNAL, ok=ok, tx=tx, ts=ts, error=error)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="One-shot Avalanche pay/get-paid + ERC-8004 demo")
    ap.add_argument("--no-mint", action="store_true", help="skip the ERC-8004 mint + heartbeat")
    ap.add_argument("--no-x402", action="store_true", help="skip the x402 pay→get-paid loop")
    args = ap.parse_args()

    key, addr = _load_key()
    if not key or not addr:
        print("No agent wallet found — run `python scripts/avax_derisk.py keygen` first.", file=sys.stderr)
        return 2

    from ictbot.settings import settings

    _configure(settings, key, addr)

    from ictbot.agent.identity import identity_wallet_bnb
    from ictbot.data.x402_cmc import usdc_balance

    avax = identity_wallet_bnb(addr) or 0.0
    usdc = usdc_balance(addr) or 0.0
    print(f"agent wallet: {addr}")
    print(f"  AVAX {avax:.5f} (gas) | USDC {usdc:.4f}   {SNOWTRACE}/address/{addr}")
    if avax <= 0:
        print("✗ 0 AVAX gas — fund the wallet first (scripts/avax_derisk.py keygen prints faucet links).",
              file=sys.stderr)
        return 2

    txs: list[tuple[str, str]] = []

    if not args.no_x402:
        print("\n[1] x402 — agent pays its OWN server for the CMC Regime Report …")
        if usdc <= 0:
            print("  ✗ 0 USDC — fund Fuji USDC first (faucet.circle.com → Avalanche Fuji).", file=sys.stderr)
        else:
            tx = _run_x402(settings)
            if tx:
                txs.append(("x402 settlement", tx))

    if not args.no_mint:
        print("\n[2] ERC-8004 — mint identity + write heartbeat on Fuji …")
        txs.extend(_run_identity(settings))

    print("\n=== on-chain proof (Snowtrace) ===")
    if txs:
        for label, tx in txs:
            print(f"  {label:22s} {SNOWTRACE}/tx/{tx}")
    else:
        print("  (nothing settled this run — see the messages above)")
    return 0 if txs else 1


if __name__ == "__main__":
    raise SystemExit(main())
