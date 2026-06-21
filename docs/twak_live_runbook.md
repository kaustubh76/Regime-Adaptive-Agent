# TWAK Live Runbook — quote-only integration → mainnet flip (contest 2026-06-22)

The agent's execution layer is the Trust Wallet Agent Kit (`twak` CLI) as the **sole signer**.
The `twak` CLI is **mainnet-only** (`twak chains` lists no BSC testnet), so we de-risk before the
contest by running the FULL loop **quote-only** against the real CLI — real on-chain balances and
real router quotes, `execute=False`, nothing signed or spent — then flip a single flag to execute
for the contest.

## What runs in each mode

| | client | swaps | journal / state | creds / funds |
|---|---|---|---|---|
| `--mode sim` (default) | `SimTwakClient` (paper) | simulated fills | `allocator_journal.jsonl` / `allocator_state.json` | none |
| `--quote-only` (integration) | `CliTwakClient` (real CLI) | **real router quotes, execute=False** | `allocator_dryrun.jsonl` / `allocator_dryrun_state.json` | none — read-only on-chain |
| `--mode live` (contest) | `CliTwakClient` (real CLI) | **signed BSC swaps** | `allocator_live.jsonl` / `allocator_live_state.json` | creds + wallet + `ENABLE_LIVE_TRADING=true` |

The three namespaces are fully isolated — a dry-run can never touch the contest's `allocator_live.*`.

## Prerequisite: resolve the `twak` binary (REQUIRED for cron)

`twak` is an npm global (here under nvm) and is NOT on a minimal cron PATH. Set the absolute path:

```
TWAK_BINARY=/Users/apple/.nvm/versions/node/v26.3.0/bin/twak   # in .env
```

`CliTwakClient` also prepends this binary's directory to the subprocess PATH, so twak's
`#!/usr/bin/env node` shebang finds the co-located `node` even with an empty PATH. Verified: with a
stripped PATH and no shell export, `CliTwakClient().balance("USDT")` returns the real on-chain balance.

## Integration phase (now → 06-21): quote-only

```
# one quote-only tick (full loop vs the real CLI; nothing signed)
PYTHONPATH=src python scripts/run_allocator.py --quote-only --dd-cap 0.10
```

Proven 2026-06-16 on the funded wallet `0xE8A30d24…BbA…6215` (NAV ~$8.20):
- Real on-chain balances read; regime computed (F&G=25 → cap 0.51); 8-token target produced.
- **5 real router quotes** flowed broker → `CliTwakClient` → `twak swap --quote-only` from 2 live
  aggregators (`0x`, `LiquidMesh`); `n_failed=0`. `tx` holds **provider tags, not hashes** (no fill).
- Journaled to `allocator_dryrun.jsonl` as `REBALANCE_DRYRUN` (`dry_run:true`); x402 + heartbeat
  suppressed (no real spend / on-chain write); contest `allocator_live.*` untouched.

### Small-bankroll note (important)
At a small NAV, `1/k`-weight positions fall under the `$1` `min_swap_usd` dust floor and the agent
skips EVERY swap. Lower the floors for a small contest book:
```
ALLOC_MIN_SWAP_USD=0.5        # or lower
ALLOC_MIN_REBAL_FRAC=0.01
```

### Guardrails verified on the live(quote-only) path (2026-06-16)
- **Kill switch:** `kill_switch.engage()` → tick prints `KILL SWITCH ENGAGED — refusing to trade`.
- **Drawdown halt:** with a seeded peak HWM, dd=31.6% > 10% cap → `DD_HALT` + `emergency_flatten`
  (quote-only sells of both held positions, `flatten_partial:false`).
- **Token allowlist:** structural — the universe is `CONTEST_TOKENS`; deselecting a held token sells
  it toward 0 next tick (demonstrate at flip with a real fill).
- **Slippage:** `--slippage <TWAK_SLIPPAGE_PCT>` is appended only on an EXECUTE; demonstrate the
  breach path at the mainnet flip (a quote has no fill to slip).

## Mainnet flip for the contest (2026-06-22)

Config diff (quote-only → live). Everything else (creds, `AGENT_ID=133085`, x402 on Base, cron,
guardrails) is unchanged:

```
TWAK_MODE=live
ENABLE_LIVE_TRADING=true
# TWAK_CHAIN=bsc            # default; mainnet
# AGENT_NETWORK=bsc         # default; mainnet identity
ALLOC_MIN_SWAP_USD=0.5      # match the actual bankroll (see note above)
```

Then drop `--quote-only` — the SAME loop now signs:

```
# preflight (creds + ENABLE_LIVE_TRADING + resolved strategy; no swap)
PYTHONPATH=src python scripts/run_allocator.py --mode live --preflight-only
# arm the daily tick + intraday DD watch via cron (note the explicit nvm/PATH)
10 0 * * *  cd <repo> && . .venv/bin/activate && PYTHONPATH=src python scripts/run_allocator.py --mode live --dd-cap 0.10 >> data/logs/allocator_live.log 2>&1
*/30 * * * * cd <repo> && . .venv/bin/activate && PYTHONPATH=src python scripts/run_allocator.py --mode live --dd-watch --dd-cap 0.10 >> data/logs/allocator_live.log 2>&1
```

Checklist:
1. `TWAK_BINARY` set to the absolute path (cron resolution).
2. Fund the trading wallet `0xE8A30d24…6215` (USDT + a little BNB for gas). *(manual)*
3. `CONTEST_START=2026-06-22` / `CONTEST_END` at real values (undo any Phase-2 drill bracketing).
4. No stale `allocator_live_state.json` (absent today → first live tick re-seeds HWM from on-chain NAV).
   `PROFIT_LOCK_ENABLED=1` is set — use `--anchor-nav` if relying on profit-lock.
5. Kill switch released; `ENABLE_LIVE_TRADING=true` restored after any drill.
6. `--preflight-only` green.

## Open items (tracked separately)
- **Docs coherence:** done — x402 counts trued-up to 20+/$0.20+ in `SUBMISSION.md` / docs.
- **x402 breadth (stretch):** add a second paid surface (`quotes_latest` per tick) beyond `dex_search`.

---

# ALL-PILLARS MAINNET MVP — armed for 2026-06-22

The four integrations as one coherent mainnet MVP. **Armed, not live**: everything is wired +
validated; no real swap fires until the 06-22 flip. Status today (2026-06-16):

| Pillar | Mainnet status | What it needs to go live |
|---|---|---|
| **x402 (CMC data, Base)** | ✅ LIVE — 21 settled, $0.21 | nothing (Base USDC already funded) |
| **TWAK (trading, BSC)** | ✅ armed — proven quote-only | the 06-22 `.env` flip + trading-wallet funds |
| **ERC-8004 (identity heartbeat)** | ⚠️ wired + verifiable — **fixed** (below) | fund identity wallet ~0.002 BNB (direct-gas) |
| **ERC-8183 (commerce)** | ✅ testnet-proven, mainnet-ready | `ERC8183_NETWORK=bsc-mainnet` + mainnet "U" (optional) |

## The broken ERC-8004 heartbeat wiring — FIXED (2026-06-16)
Heartbeats silently never landed (gasless 403 + the direct-gas identity wallet ≈ 0 BNB, and
`write_heartbeat` swallowed the reason). Now:
- `write_heartbeat` returns `{ok, tx?, error?}` and **logs the real reason** (no silent swallow); the
  tick journals it (`heartbeat` field) → dashboard surfaces it (IdentityCard "heartbeat" line).
- `read_heartbeat()` reads the on-chain blob back — **verification** (proven against 133085, which
  already holds a real heartbeat from 2026-06-14).
- `make heartbeat_check` reports the funding path **actionably** (e.g. "fund 0xEb7b… with ≥ 0.001 BNB
  (have 0.000004)") instead of failing silently.
- **Unblock:** fund identity wallet `0xEb7bF36aab4912c955474206EF0b835170389655` with ~0.002 BNB
  (direct-gas, current config) — OR set `AGENT_USE_PAYMASTER=true` + provision the MegaFuel sponsor
  policy on NodeReal (gasless). Then heartbeats land + `make heartbeat_check` shows `ready:true`.

## Unified fund table (the only manual steps)
| Wallet | Asset | Amount | For |
|---|---|---|---|
| Trading `0xE8A30d24…6215` | USDT + BNB | ~$10 + ~0.005 BNB | TWAK swaps + gas |
| Identity `0xEb7b…9655` | BNB | ~0.002 | ERC-8004 heartbeat gas (direct-gas) |
| Identity `0xEb7b…9655` | Base USDC | already funded | x402 ($0.01/call) |
| (optional) ERC-8183 buyer | mainnet "U" | small | commerce escrow (only if `ERC8183_NETWORK=bsc-mainnet`) |

## The 06-22 go-live (one flip, then arm cron)
```
# .env flip (DISARMED today → live at the window):
TWAK_MODE=live
ENABLE_LIVE_TRADING=true
ALLOC_MIN_SWAP_USD=0.5
DASHBOARD_JOURNAL=live
# AGENT_HEARTBEAT_ENABLED=true, AGENT_ID=133085 already set; x402 already live.

PYTHONPATH=src python scripts/run_allocator.py --mode live --preflight-only   # must be green
make heartbeat_check                                                          # ready:true once funded
# contest-week cron (days 22–28 only; REMOVE after 06-28):
7 13 22-28 6 *   <repo>/scripts/live_tick.sh
*/30 * 22-28 6 * <repo>/scripts/dd_watch.sh
make deploy_dashboard                                                         # flip dashboard to live
```

## Validate NOW (no funds, no live trade)
```
PYTHONPATH=src python -m pytest -q                                            # full suite green
ENABLE_LIVE_TRADING=true TWAK_MODE=live python scripts/run_allocator.py --mode live --preflight-only
python scripts/run_allocator.py --quote-only                                 # real router quotes, execute=False
make heartbeat_check                                                         # actionable readiness + on-chain read-back
```

## ERC-8183 commerce on mainnet (optional)
`ERC8183_NETWORK=bsc-mainnet` (code already routes mainnet → keyed paymaster via `commerce._network`);
the buyer funds mainnet "U" (`0xcE24439F2D9C6a2289F741120FE202248B666666`). Default stays bsc-testnet
(free, proven). See `docs/erc8183_agent_commerce.md`.

## Pre-fund readiness — verified 2026-06-16

**Go-live in 3 steps (on 2026-06-22): fund 2 wallets → flip 2 flags → arm cron.** Everything else is
wired, tested (1538 green), deployed, and dashboard-verified (CMC rotation live; no-"Binance" gate
green; `make verify_dashboard`). A pre-fund sweep — every check possible **without funds** (read-only /
`execute=False`, zero spend) — confirms the ONLY remaining blockers are money + the `.env` flip:

| Check | Command | Verdict (2026-06-16) |
|---|---|---|
| TWAK live preflight | `run_allocator --mode live --preflight-only` | ✅ creds + wallet password + kill-switch + strategy `momentum_cmc` all pass — fails ONLY on `ENABLE_LIVE_TRADING=false` (the intended flip) |
| Quote-only full loop | `run_allocator --mode live --quote-only` | ✅ full loop on real on-chain NAV $8.15 → real CMC decision → `execute=False`, exit 0, 0 failures (router-quote path proven 06-16) |
| ERC-8004 heartbeat | `make heartbeat_check` | ✅ on-chain read-back PROVEN (real heartbeat 06-14) · ⛽ NOT READY — fund identity `0xEb7b…9655` ≥ 0.002 BNB (direct-gas) |
| x402 (CMC data, Base) | `data/x402/receipts.json` | ✅ LIVE — 22 settled on Base (`eip155:8453`) |
| ERC-8183 commerce | testnet-proven | ✅ mainnet-ready via `ERC8183_NETWORK=bsc-mainnet` (optional sell-side) |

**Heartbeat gas note:** MegaFuel gasless sponsorship returns 403 without `NODEREAL_API_KEY` (not
deployed), so the heartbeat go-live path is **direct-gas** — fund the identity wallet ~0.002 BNB (per the
fund table). The on-chain *read-back* already proves a heartbeat landed; funding lets the per-tick writes fire.

No real swap / per-tick heartbeat / mainnet ERC-8183 settle has fired — **by design** (disarmed). Funding
the two wallets + the flip (`TWAK_MODE=live`, `ENABLE_LIVE_TRADING=true`) is exactly what lets those final
txs run. See the **Unified fund table** + **The 06-22 go-live** sections above.
