> **📦 ARCHIVED 2026-06 — upstream ICT perp bot.** This README describes the original
> `ictbot` product (CEX perp scalping: Binance/Delta, ICT confluence, Streamlit). It is
> **superseded for the BNB Hack by the momentum allocator** — see the [root README](../../README.md).
> Kept verbatim for provenance; links below are rewritten relative to this archived location.

# ICT AI BOT PRO MAX

A scalping bot that scores crypto perpetuals against an ICT-style
checklist (HTF bias → LTF bias → POI → POI tap → MSS → Micro FVG →
Delta), routes BUY/SELL signals through a multi-broker live execution
layer, and serves a live Streamlit dashboard.

> **Status:** **Live execution proven through Phase 11** (PAXG
> dropped per the Phase 9.A `no edge` WFO verdict). The active
> trading set is now **BTC, ETH, SOL, XRP**. XRP TP fired at +5.02R
> end-to-end on 2026-06-06; full smoke round-trip on Binance testnet
> the same day. Acceptance gate (broker truth = wallet truth)
> **green** for XRP; the 4-pair smoke gate is **PENDING** on
> BTC/ETH/SOL until they produce their first broker-truth closes
> (1–3 days of observation in expectation).
>
> **Phase 17** (2026-06-07) ripped Bybit out of the codebase: the
> live trading set is now **Binance (testnet, ongoing)** and
> **Delta (mainnet, once user is confident)**. `EXCHANGE=bybit` is
> rejected at boot.
>
> See [`docs/autotrade_plan.md`](../autotrade_plan.md) for the
> full phase-by-phase rollout log,
> [`docs/operations.md`](../operations.md) for the runbook, and
> [`docs/findings.md`](../findings.md) for empirical results.

## Project layout

```
Rahul_ideation/
├── src/ictbot/
│   ├── orchestrator/           # scanner.py + analyzer.py + router.py + shadow_router.py
│   ├── exec/                   # paper.py, binance_live.py, delta_live.py, factory.py, orders.py
│   ├── strategy/               # ict_pro_max.py — the canonical scoring orchestrator
│   ├── indicators/             # ICT primitives (bias_sma, bias_slope, poi, mss, fvg, delta, atr, …)
│   ├── portfolio/              # journal.py, account.py, caps.py
│   ├── runtime/                # kill_switch.py, pause.py, news.py, sessions.py, signal_memory.py
│   ├── notify/                 # telegram.py, tg_confirm.py, signal_check.py
│   ├── data/                   # binance.py + delta.py exchange fetchers, factory.py, cache.py
│   ├── engine/                 # backtest.py, sweep.py, wfo.py, compare.py
│   ├── cli/                    # shadow_report.py, journal_cmd.py
│   └── ui/                     # Streamlit dashboard
├── scripts/                    # standalone tools — see "Scripts" below
├── tests/                      # 290 Phase 9-16-affected + 888 full sweep (2 skipped), all mocked (no network)
├── docs/                       # autotrade_plan, operations, architecture, findings, …
├── infra/                      # prometheus_alerts.yaml
├── data/                       # runtime artefacts (gitignored)
│   ├── journal/                # signals.json (live broker truth), wallet_baseline_usdt.txt
│   ├── runs/                   # backtest_curve.json
│   ├── logs/                   # scanner.stdout.log, scanner.log (json), heartbeat.ts
│   └── cache/                  # parquet OHLCV cache
└── docs/autotrade_plan.md      # Phase A → 6 rollout log
```

## Setup

```bash
cd /Users/apple/Desktop/Rahul_ideation
make install
cp .env.example .env    # then fill in TELEGRAM_TOKEN + TELEGRAM_CHAT_ID
                         # + venue creds (BINANCE_API_KEY/_SECRET or DELTA_…)
```

Live trading requires `ENABLE_LIVE_TRADING=true` plus a matching venue
API key/secret. The boot guard (Fix 5.I) refuses to start if live is on
and the venue's creds are empty.

## Run

| Command | What it does |
|---|---|
| `make app` | Streamlit dashboard at <http://localhost:8501> |
| `make scan` | Background scanner → live broker (per `EXCHANGE`) + Telegram |
| `make test` | Run the test suite |
| `make backtest PAIR=ETH/USDT:USDT BARS=5000` | Walk-forward replay one config |
| `make best PAIR=BTC/USDT:USDT BARS=5000` | Current best-known config |
| `make sweep PAIR=BTC/USDT:USDT BARS=500` | Grid-search params on one pair |
| `make scoreboard BARS=500` | Sweep every pair, ranked scoreboard |
| `make wfo PAIR=BTC/USDT:USDT BARS=5000` | Walk-forward optimisation on one pair |
| `make wfo_all BARS=5000` | WFO on every pair — which edges hold OOS |
| `make wfo_per_pair ARGS="--bars 10000 --grid rr2plus"` | **Phase 12.C**: per-pair WFO driver (writes `data/wfo/per_pair_<date>.json`) |
| `make smoke_gate` | **Phase 12.C**: 4-pair Phase 9 acceptance gate; exit 0 if every pair has broker-truth closes |
| `make smoke_pairs` | **Phase 12.C**: testnet round-trip every pair (writes `data/smoke_pairs_<date>.json`) |
| `make pair_readiness` | **Phase 12.C**: per-pair leverage / margin / ticker / min_notional status |
| `make status` | **Phase 13.C**: ops snapshot — wallet, open positions, smoke gate, heartbeat, last 5 broker-truth closes |
| `make edge_check` | **Phase 14.D**: per-pair t-stat vs 0 + vs WFO TEST expectancy; exit codes 0/1/2 = edge/pending/no-truth |
| `make session_report` | **Phase 16.C**: daily MD report — IN_SESSION (London+NY) vs OFF_SESSION (Tokyo+off-hours) with Welch's t verdict + per-pair × bucket breakdown |
| `make bias_compare PAIR=BTC/USDT:USDT BARS=5000` | sma vs swing vs slope on one pair |
| `make bias_scoreboard BARS=5000` | bias_compare on every pair |
| `make bt_curve PAIR=BTC/USDT:USDT BARS=5000` | Write backtest equity curve for dashboard |
| `make journal` | Signal journal + win-rate |

## Scripts (standalone)

The `scripts/` directory ships operator-facing tools. None of them are
required for the scanner to run — they're for verification, recovery,
and one-off ops.

| Script | Purpose |
|---|---|
| `scripts/diagnose_live_pnl.py` | Read-only diagnostic. Classifies every closed journal row as `broker-truth`, `broker-truth-no-fee`, `synthetic-paper`, or `synthetic-live-bug`. Emits an `acceptance: true/false` JSON field — the one-line Phase 3 Layer 2 acceptance check. |
| `scripts/diagnose_live_pnl.py --smoke-gate` | Phase 9.G per-pair acceptance gate. Reports `pairs_passed` / `pairs_pending` and exits 0 only when every configured pair has ≥ 1 broker-truth close. Use as the operational gate before mainnet promotion. |
| `scripts/verify_wallet_parity.py` | Compares journal-implied USDT P&L vs Binance wallet `fetch_balance` change since a baseline. Exit code 0 = parity, 1 = drift, 2 = infra error. Initialise baseline by running once with no flags. |
| `scripts/archive_journal.py` | Move the current `data/journal/signals.json` to `signals_pre_fix_<date>.json` and create a fresh empty journal. Used to start a clean window for acceptance testing. |
| `scripts/wfo_per_pair.py` | **Phase 9.A.** Drives `engine.wfo` independently on each configured pair and writes `data/wfo/per_pair_<date>.json` with the winning `(sl_frac, tp_frac)` per pair plus the classify verdict. Operator promotes winners into `.env` via `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>`. |
| `scripts/smoke_test_pairs.py` | **Phase 9.F.** Round-trips every pair on Binance testnet (market entry + immediate `reduceOnly` flatten) and writes `data/smoke_pairs_<date>.json` with per-pair leverage / margin / precision / latency / status. Refuses unless `BINANCE_TESTNET=true`. |
| `scripts/smoke_binance.sh` | Single-pair live smoke test on Binance testnet — Phase A validation runner. |
| `scripts/close_test_order.py [PAIR]` *(deleted 2026-06, Audit M2)* | Manual flatten of a single pair (cancels open orders + reduce-only market in the opposite direction). Operator escape hatch. |
| `scripts/fire_test_order.py` *(deleted 2026-06, Audit M2)* | Manual bracket placement on a single pair — exercises the broker path with no signal involved. |
| `scripts/check_binance_keys.sh` | Sanity-check Binance API key auth before flipping live trading on. |

## How a signal is scored

```
+25 if POI was tapped this candle
+25 if MSS direction matches bias
+25 if a micro FVG formed in the bias direction (when require_fvg=True)
+25 if delta volume agrees with HTF bias
```

A BUY or SELL signal only fires when **all** of those conditions are
true AND the Phase E bias-alignment gate passes (`htf_bias == ltf_bias`
when `REQUIRE_BIAS_ALIGNMENT=true`). Anything 60–80% on the dashboard
is "almost a setup". See [`docs/autotrade_plan.md`](../autotrade_plan.md)
for the full canonical-flow definition.

## Telegram troubleshooting

If you see `403 Forbidden` when the bot tries to send a message:

1. Open Telegram and search for your bot by its username.
2. Send `/start` to it.
3. That's it — Telegram bots can only DM users who have started a
   conversation with them first.

To find your chat ID, message your bot then visit
`https://api.telegram.org/bot<TOKEN>/getUpdates`; the chat ID is in
`message.chat.id`.

## Operator commands (`TG_COMMANDS_MODE=true`)

DM the bot from the operator account (`TG_OPERATOR_USER_ID`):

- `/status` — current per-pair signal card pack
- `/journal [n]` — last n closes (default 10, max 50)
- `/kill <reason>` — engage kill switch
- `/resume yes` — clear kill switch + pause (does NOT flip `ENABLE_LIVE_TRADING`)
- `/pause <minutes>` — auto-expiring evaluation halt
- `/whoami` — sanity check operator id
- `/help`

## Further reading

- [`docs/autotrade_plan.md`](../autotrade_plan.md) — Phase A → 6
  rollout log; commit chain, evidence, current production config.
- [`docs/operations.md`](../operations.md) — daily ops + incident
  response runbook; acceptance gate procedure.
- [`docs/architecture.svg`](../architecture.svg) — the momentum agent
  architecture (view in any browser; edit `docs/architecture.excalidraw`).
- [`docs/findings.md`](../findings.md) — empirical results: best
  configs, WFO verdicts, friction analysis.
- [`DEPLOY.md`](../../DEPLOY.md) — Render deployment + env-var reference.
- [`ROADMAP.md`](../../ROADMAP.md) — phase-by-phase forward plan.
- [`PLAN.md`](../../PLAN.md) — pre-Phase-2 retrospective log.
