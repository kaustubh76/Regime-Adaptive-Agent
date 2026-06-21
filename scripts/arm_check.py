#!/usr/bin/env python3
"""
ARM CHECK — one read-only command that runs every NO-FUNDS go-live check and prints a
single readiness table, so an operator can confirm the mainnet flip is safe BEFORE
spending a cent or flipping ENABLE_LIVE_TRADING.

It reuses the SAME guards the live runtime uses (it does not re-implement them):
  - settings boot guards (just importing `ictbot.settings` runs them — settings.py:841+)
  - TWAK creds + wallet password + kill switch (mirrors run_allocator._live_preflight)
  - TWAK binary resolution + a real router price (proves the `twak` CLI runs on this PATH)
  - identity.heartbeat_gas_ready() — paymaster reachable+sponsorable, or direct-gas BNB
  - commerce.buyer_available()/buyer_wallet_info() — ERC-8183 buyer + payment token
  - x402_cmc.base_usdc_balance() — the x402 pay wallet on Base

Verdicts:
  ✓ PASS  — ready
  ⛽ FUND  — the ONLY thing missing is money (a deliberate, manual step) — NOT a hard blocker
  ✗ FAIL  — a real blocker (missing creds, sponsor policy unset, binary unresolved, …)
  • INFO  — informational (a deliberate pre-arm state, or an optional capability)

Exit code: non-zero iff any ✗ FAIL row (a real blocker). ⛽ FUND rows do NOT fail the run —
funding is the deliberate manual step. SECURITY: prints only public data (addresses, balances,
booleans, token symbols) — NEVER a key, password, JWT, or API secret.

  make arm_check
  PYTHONPATH=src python scripts/arm_check.py
"""

from __future__ import annotations

import argparse
import sys

# Importing settings runs ALL boot guards (settings.py:841-980). If a guard raises, the
# import fails loudly here — which is itself the "boot guards" check failing.
from ictbot.settings import settings

# A LIVE tick refuses candles older than this (run_allocator.MAX_BAR_AGE_H) — so a cold CMC
# feed makes every tick SKIP. Kept in sync with run_allocator without importing it (heavy).
MAX_BAR_AGE_H = 12.0

PASS, FUND, FAIL, INFO = "PASS", "FUND", "FAIL", "INFO"
_GLYPH = {PASS: "✓", FUND: "⛽", FAIL: "✗", INFO: "•"}


class Rows:
    """Collects (label, verdict, detail) rows; tracks whether any hard blocker fired."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, label: str, verdict: str, detail: str = "") -> None:
        self.rows.append((label, verdict, detail))

    def check(self, label: str, fn) -> None:
        """Run a check that returns (verdict, detail); any exception becomes a FAIL row
        so one broken probe never aborts the whole sweep."""
        try:
            verdict, detail = fn()
        except Exception as e:  # noqa: BLE001 — a probe crash is a FAIL, not a traceback
            verdict, detail = FAIL, f"{type(e).__name__}: {e}"
        self.add(label, verdict, str(detail)[:120])

    @property
    def failed(self) -> bool:
        return any(v == FAIL for _, v, _ in self.rows)

    @property
    def needs_funding(self) -> bool:
        return any(v == FUND for _, v, _ in self.rows)


def _twak_price_probe() -> tuple[str, str]:
    """Build the REAL CliTwakClient and read a live router price — proves the `twak` binary
    resolves on this PATH (the #1 cron footgun) and the router is reachable. No creds, no
    signing, no spend (a price read needs neither wallet nor ENABLE_LIVE_TRADING)."""
    from ictbot.exec.twak_client import CliTwakClient

    px = CliTwakClient().price("BNB")
    if isinstance(px, (int, float)) and px > 0:
        return PASS, f"twak price BNB=${px:,.2f} (binary={settings.twak_binary})"
    return FAIL, f"twak price returned {px!r}"


def _heartbeat_ready() -> tuple[str, str]:
    """identity.heartbeat_gas_ready(): in PAYMASTER mode not-ready means the MegaFuel sponsor
    policy isn't set (a dashboard config blocker → FAIL); in DIRECT-GAS mode not-ready means
    the identity wallet is short BNB (money → FUND)."""
    from ictbot.agent import identity

    r = identity.heartbeat_gas_ready()
    mode, ready, detail = r.get("mode"), r.get("ready"), r.get("detail")
    if ready:
        return PASS, f"{mode}: ready"
    # paymaster → config blocker; direct-gas → just needs BNB.
    return (FAIL if mode == "paymaster" else FUND), f"{mode}: {detail or 'not ready'}"


def _erc8183_buyer() -> tuple[str, str]:
    """ERC-8183 buyer keystore + payment-token funding (optional — only needed to fire MORE
    jobs from the operator side; the first mainnet job already settled)."""
    from ictbot.agent import commerce

    if not commerce.buyer_available():
        return INFO, "buyer keystore not configured (optional — set CLIENT_WALLET_PASSWORD to fire jobs)"
    info = commerce.buyer_wallet_info()
    bal, need, tok = info.get("balance"), info.get("price"), info.get("token") or "U"
    addr, net = info.get("buyer"), info.get("network")
    if bal is not None and need is not None and bal < need:
        return FUND, f"buyer {addr} on {net}: have {bal} {tok}, need >= {need} ({info.get('token_address')})"
    return PASS, f"buyer {addr} on {net}: {bal} {tok} (>= {need})"


def _x402() -> tuple[str, str]:
    """x402 pay-wallet USDC balance on Base (read-only)."""
    from ictbot.data import x402_cmc

    if not x402_cmc.available():
        return INFO, "x402 disabled or no wallet password (X402_ENABLED / AGENT_WALLET_PASSWORD)"
    bal = x402_cmc.base_usdc_balance()
    if bal is None:
        return FUND, "could not read Base USDC balance (RPC?) — verify the pay wallet is funded"
    if bal <= 0:
        return FUND, f"Base USDC balance is {bal} — fund the x402 pay wallet"
    return PASS, f"Base USDC balance {bal:.4f}"


def _live_arm() -> str:
    """The arm a LIVE tick would run (mirrors run_allocator._resolve_strategy_name for mode=live:
    STRATEGY_NAME, else derived from ALLOC_ADAPTIVE)."""
    return settings.strategy_name or ("momentum_adaptive" if settings.alloc_adaptive else "momentum")


def _strategy(arm: str) -> tuple[str, str]:
    """The checked arm resolves in the registry; note whether it's the live-resolved default."""
    from ictbot.strategy import registry

    registry.get(arm)  # raises if unknown → FAIL
    tag = "live-resolved" if arm == _live_arm() else f"override (live arm is '{_live_arm()}')"
    return PASS, f"resolves '{arm}' ({tag})"


def _cmc_feed_warmth() -> tuple[str, str]:
    """The CMC-native arm decides on 4h candles from the streamer (scripts/cmc_stream.py). FAIL if the
    streamer heartbeat is stale (> 180s, the watchdog's own threshold) or the CMC 4h matrix is thin
    (< 200 rows) — either makes every LIVE tick SKIP (→ zero trades → contest DQ)."""
    import time
    from pathlib import Path

    hb = Path("data/logs/cmc_stream_heartbeat.ts")
    if not hb.exists():
        return FAIL, "no streamer heartbeat — start scripts/cmc_stream.sh (a LIVE tick would skip on stale data)"
    try:
        age = time.time() - int(hb.read_text().strip()) / 1000.0
    except Exception as e:  # noqa: BLE001
        return FAIL, f"heartbeat unreadable: {e}"
    rows = None
    try:
        from ictbot.data.cmc import cmc_4h_close_matrix
        from ictbot.strategy.momentum_allocator import CONTEST_TOKENS

        rows = int(cmc_4h_close_matrix(CONTEST_TOKENS).shape[0])
    except Exception as e:  # noqa: BLE001
        return FAIL, f"CMC 4h matrix read failed: {e}"
    if age > 180:
        return FAIL, f"streamer heartbeat STALE {age:.0f}s (>180s) — restart cmc_stream.sh (matrix rows={rows})"
    if rows < 200:
        return FAIL, f"CMC 4h matrix thin ({rows}<200 rows) — tick would skip; let the stream/seed accrue"
    return PASS, f"streamer heartbeat {age:.0f}s fresh; CMC 4h matrix {rows} rows"


def _gate_verdict(arm: str) -> tuple[str, str]:
    """The arm's acceptance-gate verdict from data/reports/strategy_gates.json: FAIL if survival
    failed (DQ rail), INFO if survival passes but forward isn't eligible yet (accruing — live needs
    operator sign-off, not a hard forward-eligible requirement), PASS if fully gate-cleared."""
    import json
    from pathlib import Path

    gp = Path("data/reports/strategy_gates.json")
    if not gp.exists():
        return INFO, "no strategy_gates.json — run `make campaign` / `make forward_track_*_report`"
    try:
        g = (json.loads(gp.read_text()) or {}).get(arm)
    except Exception as e:  # noqa: BLE001
        return INFO, f"gate read failed: {e}"
    if not g:
        return INFO, f"no gate entry for {arm!r} yet"
    surv, fwd, perf = g.get("survival") or {}, g.get("forward") or {}, g.get("perf") or {}
    dd, tpw, ret = surv.get("worst_week_dd"), surv.get("trades_per_week"), perf.get("total_return")
    base = (f"DD={round((dd or 0) * 100, 1)}% tpw={round(tpw or 0, 1)} "
            f"fwd_eligible={fwd.get('forward_eligible')} tot_ret={round((ret or 0) * 100, 1)}%")
    if surv.get("passed") is False:
        return FAIL, f"survival FAILED (DQ rail) — {base}"
    if not fwd.get("forward_eligible"):
        return INFO, f"survival ✓; forward accruing (needs operator sign-off) — {base}"
    return PASS, f"gate-cleared (survival ✓ + forward eligible) — {base}"


def _cmc_only_coherence(arm: str) -> tuple[str, str]:
    """The LIVE entry point (live_tick.sh) exports CMC_ONLY=true, which boot-guards on
    CMC_INTEL_ENABLED and RAISES on any CEX candle path. Assert the live config is coherent: intel
    enabled + the arm sources CMC candles (candle_source starts with 'cmc')."""
    from ictbot.strategy import registry

    if not settings.cmc_intel_enabled:
        return FAIL, "CMC_INTEL_ENABLED=false — live_tick sets CMC_ONLY=true which boot-guards on it"
    cs = getattr(registry.get(arm), "candle_source", "cmc_4h")
    if not str(cs).startswith("cmc"):
        return FAIL, f"{arm} candle_source={cs!r} is not CMC — would RAISE under the live CMC_ONLY firewall"
    return PASS, f"CMC_INTEL_ENABLED=true; {arm} candle_source={cs} (firewall-safe)"


def main() -> int:
    ap = argparse.ArgumentParser(description="No-funds mainnet go-live readiness sweep.")
    ap.add_argument("--arm", default=None,
                    help="strategy arm to check the gate/firewall for (default: the live-resolved arm)")
    args = ap.parse_args()
    arm = args.arm or _live_arm()

    r = Rows()

    # Reaching here means `import ictbot.settings` succeeded → every boot guard passed.
    r.add("boot guards (settings)", PASS, "all settings.py:841-980 guards passed at import")

    # --- TWAK live preflight (the deliberate ENABLE_LIVE_TRADING flip is INFO, not FAIL) ---
    from ictbot.runtime import kill_switch

    r.add(
        "kill switch",
        FAIL if kill_switch.is_engaged() else PASS,
        "ENGAGED — release before live" if kill_switch.is_engaged() else "released",
    )
    creds_ok = bool(settings.twak_access_id and settings.twak_hmac_secret)
    r.add("TWAK creds", PASS if creds_ok else FAIL,
          "TWAK_ACCESS_ID + TWAK_HMAC_SECRET set" if creds_ok else "missing TWAK_ACCESS_ID/TWAK_HMAC_SECRET")
    pw_ok = bool(settings.twak_wallet_password or settings.agent_wallet_password)
    r.add("wallet password", PASS if pw_ok else FAIL,
          "set" if pw_ok else "missing TWAK_WALLET_PASSWORD / AGENT_WALLET_PASSWORD")
    r.check("TWAK binary + router price", _twak_price_probe)
    r.add("ENABLE_LIVE_TRADING", INFO,
          "armed" if settings.enable_live_trading else "disarmed (the deliberate go-live flip)")
    r.add("TWAK_MODE", INFO, settings.twak_mode)

    # --- strategy is LINED UP: resolves, decides on a warm CMC feed, gate-cleared, firewall-coherent ---
    r.check("strategy", lambda: _strategy(arm))
    r.check("CMC feed warmth", _cmc_feed_warmth)
    r.check(f"gate verdict [{arm}]", lambda: _gate_verdict(arm))
    r.check("CMC_ONLY live coherence", lambda: _cmc_only_coherence(arm))

    # --- ERC-8004 heartbeat (paymaster vs direct-gas) ---
    r.check("ERC-8004 heartbeat gas", _heartbeat_ready)
    try:
        from ictbot.agent import identity

        hb = identity.read_heartbeat()
        r.add("ERC-8004 read-back", INFO,
              f"on-chain heartbeat present (ts={hb.get('ts')})" if hb else "none yet / key-free")
    except Exception as e:  # noqa: BLE001
        r.add("ERC-8004 read-back", INFO, f"skipped: {type(e).__name__}")

    # --- ERC-8183 commerce + x402 ---
    try:
        from ictbot.agent import commerce

        r.add("ERC-8183 provider", PASS if commerce.available() else INFO,
              "provider signer available" if commerce.available()
              else "disabled (ERC8183_ENABLED / SDK / password)")
    except Exception as e:  # noqa: BLE001
        r.add("ERC-8183 provider", INFO, f"skipped: {type(e).__name__}")
    r.check("ERC-8183 buyer", _erc8183_buyer)
    r.check("x402 pay wallet (Base)", _x402)

    # --- render ---
    width = max(len(label) for label, _, _ in r.rows)
    print(f"\nARM CHECK — mainnet go-live readiness (no funds, read-only) · arm={arm}\n")
    for label, verdict, detail in r.rows:
        print(f"  {_GLYPH[verdict]} {verdict:<4} {label.ljust(width)}  {detail}")
    print()
    if r.failed:
        print("RESULT: ✗ NOT READY — resolve the ✗ FAIL row(s) above before arming.")
        return 1
    if r.needs_funding:
        print("RESULT: ⛽ READY pending FUNDING — every wiring check passed; fund the ⛽ wallet(s),")
        print("        then flip TWAK_MODE=live + ENABLE_LIVE_TRADING=true (see docs/twak_live_runbook.md).")
        return 0
    print("RESULT: ✓ READY — all checks green. Flip TWAK_MODE=live + ENABLE_LIVE_TRADING=true to arm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
