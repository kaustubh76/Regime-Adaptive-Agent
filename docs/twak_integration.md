# Trust Wallet Agent Kit — integration depth (Best Use of TWAK)

> Artifact for the **Best Use of Trust Wallet Agent Kit** special prize. TWAK is the agent's
> **sole signer** — every on-chain action (swaps, the contest registration, even the gas
> top-up that funded the identity wallet) goes through the local `twak` CLI; no key is ever
> exported, no cosigner, no custodial step.

## 0. Rubric map

The published rubric weights (per the brief) — **with the caveat that these weights are not
confirmed on external press / the public DoraHacks copy; screenshot the live BUIDL rubric and
re-weight if it differs** ([bnb_hackathon_plan.md](bnb_hackathon_plan.md) §1, §14):

| Criterion | Wt | What we ship | Evidence |
|---|--:|---|---|
| TWAK integration depth | 30 | TWAK is the sole exec layer — 3 surfaces (signing/swaps · `twak compete` registration · the gas transfer), not one swap call | §1 below · `exec/twak_client.py` |
| Self-custody integrity | 25 | Keys stay in `~/.twak/wallet.json`; password from env/keychain; no cosigner; identity key ≠ funds key | §2 below |
| Autonomous execution + guardrails | 20 | Unattended rebalance loop + a deep guardrail chain (DD halt, trade-floor, failed-swap containment, flock, RECON_DRIFT) | §3 below · `exec/bsc_spot_live.py` |
| Native x402 usage | 10 | Real per-call USDC settlement on CMC's x402 endpoints; 20+ receipts | [x402_receipts.md](x402_receipts.md) |
| Originality + real-world relevance | 10 | "A self-custody spot-rotation agent for a user who doesn't trust a CEX" | §5 below |
| Demo + presentation | 5 | The loop on camera, swap signs locally with no cosigner | [DEMO.md](../DEMO.md) |

## 1. Integration depth (30) — TWAK is the only thing that signs

The execution layer is [`twak_client.py`](../src/ictbot/exec/twak_client.py) +
[`bsc_spot_live.py`](../src/ictbot/exec/bsc_spot_live.py). The pinned CLI verb surface:

- `twak price <token> --chain bsc` → live BSC price.
- `twak swap <amt> <from> <to> --chain bsc` with `--quote-only` (quote) or `--password`
  (execute) and **`--slippage`** (default 1%). Per-swap size is bounded by the broker, not the
  CLI: a $1 min-notional floor (`min_swap_usd`) and a 2%-of-NAV skip threshold
  (`min_rebal_frac`) in [`bsc_spot_live.py`](../src/ictbot/exec/bsc_spot_live.py).
- `twak balance --chain bsc` (native + ERC-20 holdings).
- `twak compete register | status` — the contest registration itself.
- MegaFuel **gasless** swaps via a `--gasless` flag when `TWAK_GASLESS` is enabled (the
  sponsor-policy path; native-gas otherwise).

Two clients share one protocol: **`CliTwakClient`** (live; shells to the `twak` binary) and
**`SimTwakClient`** (paper; never touches a key — used for tests and dry-runs). The agent uses
*three* distinct TWAK surfaces (swaps, registration, the funding transfer), not a single swap
call.

## 2. Self-custody integrity (25) — keys never leave the wallet

- The agent wallet `0xE8A30d24BbA030D3e8a844bD1c4F6e1374EA6215` was created by `twak setup`;
  its key is an encrypted mnemonic in `~/.twak/wallet.json`, unlocked by
  `TWAK_WALLET_PASSWORD` (env / OS keychain) — **never exported, never interactive-prompted**
  in an unattended run.
- **No cosigner, no custodial step.** When the identity wallet needed a little BNB for gas, we
  sent it **through the `twak` CLI's own transfer** (tx
  [`0x3de881…189d`](https://bscscan.com/tx/0x3de881a91c9e308bb21036db712bd42408a8acdcdbbe0e4dc4e91cdfdf17189d),
  captured in `data/compete/gas_transfer_2026-06-12.json`), with the destination pinned —
  rather than extracting the key. The custody model held even for an internal top-up.
- **Identity key ≠ funds key.** The ERC-8004 identity + x402 payments use a *separate*
  bnbagent-managed wallet (`0xEb7b…9655`); a compromise of one is not a compromise of the
  other. The public read-only dashboard runs with **zero** secrets.

## 3. Autonomous execution + guardrails (20)

The unattended loop: `CMC → regime score → target weights →` **`TwakSpotBroker`** `→ journal`.
The broker ([`bsc_spot_live.py`](../src/ictbot/exec/bsc_spot_live.py)) is deliberately a
**rebalancer, not a bracket trader**: it sells overweight legs to USDT first, then buys
underweight legs (so it never needs more USDT than it has), skips moves < 2% NAV, and exposes
`emergency_flatten`. There are no SL/TP brackets because an AMM swap has no native stop —
risk is the adaptive cap + the drawdown halt instead.

Guardrails (live-safe, unattended — [bnb_strategy_decision.md](bnb_strategy_decision.md) §7):
drawdown halt vs high-water mark (atomic state writes); a failed `twak swap` returns
`ok=False` and is journaled (one bad swap can't crash a rebalance); tick-skip on
invalid/zero price, zero NAV, stale candles; per-mode `flock` so overlapping crons can't
double-execute; trade-floor nudges to clear the ≥7 minimum; live preflight + on-chain
`RECON_DRIFT` reconciliation; a kill switch. `ENABLE_LIVE_TRADING=false` hard-disables real
swaps (`LiveTradingDisabled`).

## 4. Native x402 usage (10)

Real per-call USDC settlement on CMC's x402 endpoints — **20+ settled receipts, $0.20+** (live count
in `data/x402/receipts.json`), via
`pro-api.coinmarketcap.com/x402/v1/dex/search` and `/x402/v3/cryptocurrency/quotes/latest`
(the brief's `mcp.coinmarketcap.com/x402/mcp` was not the payable path; the real ones are
above). Full mechanics, safety rails, and the receipts table: **[x402_receipts.md](x402_receipts.md)**.

## 5. Originality + real-world relevance (10)

The narrative is coherent and real: **a self-custody spot-rotation agent for a user who
doesn't trust a CEX.** Spot-only is a feature, not a limitation — the user's keys stay in
their own wallet, the agent rotates a small book autonomously within hard risk caps, and it
even **funds its own market-data feed** via x402 micropayments. Nothing about it requires
trusting a centralized venue or a custodian.

## 6. Demo (5)

See **[DEMO.md](../DEMO.md)** — the script shows a swap **signing locally with no cosigner**,
the tx confirming on BscScan, and the journal + Mission Control updating.

## 7. On-chain proof appendix

| Item | Value |
|---|---|
| Agent / trading wallet (TWAK-custodied, contest-registered) | `0xE8A30d24BbA030D3e8a844bD1c4F6e1374EA6215` |
| `CompetitionRegistry.isRegistered` | **true** (registry `0x212c61b9b72c95d95bf29cf032f5e5635629aed5`) |
| ERC-8004 identity | **agentId 133085**, owner `0xEb7bF36aab4912c955474206EF0b835170389655` (registry `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`) |
| Captured artifacts | `data/compete/identity_mint_2026-06-12.json`, `registration_check_2026-06-12.log`, `gas_transfer_2026-06-12.json`, `live_swap_2026-06-12.json`; `data/x402/receipts.json` |
| Sample live swap (TWAK-signed) | a pre-window proof round-trip: [`0x9d64…67d1`](https://bscscan.com/tx/0x9d64945b28ce5f217471299599bb30406ac5a9f7a6fb873c917aa697aa5867d1) USDT→CAKE + [`0xf08f…0380`](https://bscscan.com/tx/0xf08f1b4f0b7d00a23ff7255f6da70270dbfba389b5f19d182dd055ec6a5c0380) CAKE→USDT (both `status=1`, signed locally via the `twak` CLI, ~$1 round-trip) |
| Still TODO | in-window swaps during the trading week + the registration/mint BscScan screenshots (part of the [DEMO.md](../DEMO.md) recording checklist) |
