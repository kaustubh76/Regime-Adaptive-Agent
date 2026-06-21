# ictbot Implementation Roadmap

> Forward-looking companion to [`PLAN.md`](PLAN.md) (which is the retrospective
> log of Phases 0–11 + the post-merge bug fixes) and
> [`docs/findings.md`](docs/findings.md) (the empirical journal).
>
> Every task in this file has: **Goal · Files · Acceptance · Deps · Effort · Risk.**
> Tasks are ordered by track, not by recommended sequence — see
> [§ Sequencing](#sequencing) at the end for the order-of-execution.

**Repo state at time of writing (2026-06-07, post-Phase-17):**
- Branch: `feat/rr2plus-grid` (Phase 9 per-token completeness +
  Phase 11 PAXG removal + Phase 17 Bybit removal). Pushed to origin.
- **Phase 17** ripped Bybit entirely: `src/ictbot/data/bybit.py`,
  `src/ictbot/exec/bybit_live.py`, the 3 dedicated Bybit test files,
  and the 2 Bybit operator scripts deleted. `settings.exchange`
  narrowed to `Literal["delta", "binance"]` — `EXCHANGE=bybit` now
  refused at boot. ccxt stays (covers both surviving venues).
- **Active trading set: 4 pairs (BTC, ETH, SOL, XRP)**. Phase 11
  dropped PAXG/USDT:USDT after the Phase 9.A WFO returned `no edge`
  (TRAIN -0.85R; 3 of 4 historical broker-truth closes were MANUAL
  settlements rather than natural TP/SL fills).
- Tests: **224 Phase 9-affected green** (broker + caps + journal +
  router + scanner + diagnose + wallet-parity + per-pair RR + smoke +
  boot guards); **full sweep 797 passing, 2 skipped, 0 regressions**
  (3 pre-existing unrelated failures in `test_delta_live_broker.py` +
  `test_news_alert.py` stay out of scope per Phase 3 Layer 1).
- Engine: 6× faster than at session start (ATR tail-slice +
  searchsorted + delta prefix-sum).
- Empirical strategy verdict (**updated 2026-06-06**): Phase E WFO
  winner (sl=0.005 / tp=0.025 / 1:5 RR / slope bias /
  `REQUIRE_BIAS_ALIGNMENT=true`) is validated **live** — first XRP
  TP at +5.02R booked 2026-06-06 04:36 UTC, wallet delta matches
  journal-implied USDT, Phase 3 Layer 2 acceptance gate green. Phase
  9.A per-pair WFO over the same window (rr2plus grid, 10k bars)
  confirms SOL + ETH hold OOS (✅), BTC + XRP small-sample positive;
  PAXG verdict `no edge` triggered the Phase 11 removal. See
  `data/wfo/per_pair_2026-06-06.{txt,json}` for the full scoreboard.
- Live trading: **shipped and proven on Binance Futures testnet
  through Phase 9; trading set pared to 4 in Phase 11.** Bracket
  placement, fill capture, fee accounting, TG visibility, wallet
  parity, on_reconnect, boot guards all live. Phase 9 added per-pair
  init (margin mode + leverage read-back), precision normalization,
  readiness gate banner, per-pair env overrides, anti-correlation
  cap, live smoke test script, and the per-pair `--smoke-gate`
  classifier. 5/5 pairs round-tripped on testnet 2026-06-06
  (`data/smoke_pairs_2026-06-06.json`); Phase 11 then dropped PAXG
  from the active set. Mainnet rollout pending the 4-pair smoke
  gate (XRP already green; BTC/ETH/SOL pending broker-truth
  closes).

### Status of pre-Phase-2 tracks (as of `429af9c`)

| Track | Status |
|---|---|
| Track C — Execution wiring (Phase 8.5) | **DONE**. PaperBroker + BinanceLiveBroker + BybitLiveBroker + DeltaLiveBroker shipped; route via `SignalRouter`; `CapGate` enforces 3 open (Phase 9.B) + 2 same-direction (Phase 9.B) + 1R daily loss + 5% MDD + 3 live trades/day. Binance-side validated through Phase 9. |
| Track D — Observability (Phase 9 follow-up) | **DONE**. Prometheus on `:9100`; `infra/prometheus_alerts.yaml` with 5 rules; structured JSON logs; weekly shadow-report CI in `.github/workflows/`. Phase 9.E adds the per-pair readiness banner; Phase 9.G adds the `--smoke-gate` classifier. |
| Track E — Phase 5 parquet cache | Cache layer shipped (`src/ictbot/data/cache.py`); used by fetcher to avoid redundant exchange calls. |
| Phase A (Bybit testnet) | Skipped — Bybit testnet rejected derivatives with retCode 10024 (KYC). Routed through Binance testnet instead (per autotrade_plan.md). |
| Phase B (shadow mode) | Shipped but not active — `SHADOW_MODE=false` in current production after Fix 2.D guaranteed `RISK_PCT_LIVE` applies unconditionally. |
| Phase C (TG confirm) | Shipped; off by default (`TG_CONFIRM_MODE=false`). Operator commands active via `TG_COMMANDS_MODE=true`. |
| Phase D (tiered autonomy + caps) | Shipped — `MaxLiveTradesPerDay`, `MaxOpenPositions` (env-overridable per Fix 5.H; default raised 1→3 in Phase 9.B), `NewsBlackoutCap`, plus the boot guard on `MAX_LIVE_RISK_PER_TRADE_PCT`. |
| Phase E (bias-alignment) | Shipped + live-validated. SL_FRAC/TP_FRAC default to 1:5 RR globally; per-pair overrides shipped in Phase 9.A (`SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` aliases with global fallback). |
| Phases 2–6 (P&L plumbing + acceptance) | Shipped through `b403ef2`. See `docs/autotrade_plan.md` for the full per-fix log. |
| **Phase 9 (per-token completeness)** | **DONE** (`429af9c`). Per-pair `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` env vars + `settings.get_sl_frac(pair)`; new `MaxConcurrentSameDirection` cap + `MAX_OPEN_POSITIONS=3` / `MAX_SAME_DIRECTION=2` / `STRICT_PAIR_INIT=true` defaults; `BinanceLiveBroker._ensure_pair_init` (margin mode + leverage read-back); `_amount_to_precision` + `_price_to_precision` helpers; `verify_pair_readiness` + scanner banner; `scripts/wfo_per_pair.py` driver; `scripts/smoke_test_pairs.py` testnet round-trip; `--smoke-gate` classifier. Live smoke against testnet 2026-06-06 reports 5/5 pairs `status=ok`. |
| **Phase 11 (PAXG dropped)** | **DONE**. After the Phase 9.A WFO returned `no edge` for PAXG (TRAIN -0.85R), Phase 11 removed PAXG from `_DEFAULT_PAIRS` and from the per-pair env field set. Active trading set is now `{BTC, ETH, SOL, XRP}`. Historical PAXG rows in `data/journal/signals.json` stay; the `--smoke-gate` classifier silently ignores them. |
| **Phase 12 (POI per-pair + operator UX)** | **DONE**. Per-pair `POI_TAP_TOLERANCE_<TOKEN>` overrides + `settings.get_poi_tap_tolerance(pair)` helper mirror the Phase 9.A SL/TP pattern. `.env.example` refreshed with every Phase 9 + 11 + 12 env var + WFO winners as commented opt-ins. Makefile gains `make smoke_gate / smoke_pairs / wfo_per_pair / pair_readiness`. `diagnose_live_pnl.py` smoke-gate banner now reads the pair count dynamically (`4-pair` post-Phase-11, not hardcoded). |
| **Phase 13 (Tunable caps + status snapshot)** | **DONE**. Promoted `DailyLossLimit(limit_R=1.0)` and `MaxDrawdown(limit=0.05)` from hardcoded values to `DAILY_LOSS_LIMIT_R` and `MAX_DRAWDOWN_FRAC` env vars with sanity boot guards (refuse on ≤ 0 / outside (0, 1)). New `scripts/status.py` + `make status` consolidate wallet + open positions + smoke gate + heartbeat + last 5 broker-truth closes into a single read-only command. |
| **Phase 14 (Edge reality check)** | **DONE-AUDIT-ONLY**. Read-only audit of `signals.json`: today's journal has 1 broker-truth WIN (XRP TP at +5.019R) + 3 MANUAL flattens + 65 cap-rejected setups. **N=1** real natural close — cannot distinguish edge from luck. The "SLs hitting" perception is the REJECTED dashboard rows (cap layer blocking signals at the day's 3-trade ceiling), not real losses. Procedural fix in Phase 15. Phase 14.D shipped `scripts/edge_check.py` (per-pair t-stats vs 0 + vs WFO TEST expectation, exit codes 0=real edge, 1=pending, 2=no truth). |
| **Phase 15 (Testing-phase trust mode)** | **DONE**. `MaxLiveTradesPerDay.check()` now allows `limit ≤ 0` as "no cap" semantic — mirrors `MaxConcurrentSameDirection`'s disabled pattern. Operator sets `MAX_LIVE_TRADES_PER_DAY=0` in `.env` for the testing-phase observation window so every conf=100 signal fires; default stays `3` for mainnet safety. Other caps (`MAX_OPEN_POSITIONS=3`, `MAX_SAME_DIRECTION=2`, `DAILY_LOSS_LIMIT_R=1.0`, `MAX_DRAWDOWN_FRAC=0.05`) remain active as the wise-skip layer. |
| **Phase 16 (Session-bucketed report)** | **DONE**. `journal.append_signal` now persists the killzone-aware `session` label on each row (legacy rows reconstruct via `runtime.sessions.get_sessions(at=ts)`). New `scripts/session_report.py` writes a daily markdown report at `data/reports/session_<UTC-date>.md` with IN_SESSION (London+NY) vs OFF_SESSION (Tokyo+off-hours) buckets, Welch's t comparison, per-pair × bucket breakdown, trade-by-trade log, cap-rejection breakdown, and decision-quality verdict per Phase 14.D thresholds. `make session_report` wraps it; 36 new tests in `tests/test_session_report.py`. |
| **Phase 14 (NearPriceDedup cap)** | **DONE**. New `NearPriceDedup` risk cap rejects a new entry when a recently-PLACED entry on the same `(pair, side)` sits within `NEAR_PRICE_DEDUP_BPS` (default 20 bps) of the current price AND inside `NEAR_PRICE_DEDUP_WINDOW_S` (default 900 s). Catches the signal-pyramid failure mode where the analyzer re-emits the same conf=100 signal each cycle at near-identical price (XRP saw 4 prints within 70 s on 2026-06-06). Only PLACED rows seed dedup — REJECTED rows do not. 15 new tests in `tests/test_caps.py`. Same scope label collision as Phase 14 audit — distinct work; this is the cap fix, audit was Phase 14.A/B. |
| **Phase 17 (Bybit removed)** | **DONE** (`<commit>`). Bybit dropped entirely: `src/ictbot/{data/bybit.py, exec/bybit_live.py}` deleted; 3 dedicated test files + 2 operator scripts deleted; `settings.exchange` narrowed to `Literal["delta", "binance"]`; venue cred dict + module-level `BYBIT_TESTNET` export gone. Pre-existing F1/J3/J4/C1/E1 Bybit work in this file (and in `docs/autotrade_plan.md` Phase A) stays as past-tense record. Going forward: **Binance** = testnet (ongoing testing), **Delta** = mainnet target. |

### Remaining (Phase 7+)

- **4-pair smoke gate** (Phase 9.G): currently XRP has ≥ 1
  broker-truth close; BTC + ETH + SOL still pending. Daily
  check: `.venv/bin/python scripts/diagnose_live_pnl.py --smoke-gate`.
  Estimated time to close at typical Phase E placement rate: 1–3 days.
- **Phase 9.A per-pair `.env` overrides.** WFO completed 2026-06-06
  (`data/wfo/per_pair_2026-06-06.json`): SOL + ETH ✅ holds, BTC +
  XRP small-sample positive. Operator workflow: promote
  `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` for the ✅/small-sample pairs
  into `.env`. PAXG already removed in Phase 11.
- **Mirror Fix 2.E, 2.F, 5.A, 5.B, 9.C, 9.D, 9.E into bybit_live.py +
  delta_live.py.** Mechanical port. Estimated effort: M per broker.
  Tier 5 in the autotrade plan — deferred until the 4-pair smoke
  gate passes.
- **Mainnet shadow.** Requires Bybit KYC clearance (or Delta key
  rotation per DEPLOY.md gotcha #5). Code-side ready (`SHADOW_MODE`).
- **Strategy WFO refresh.** Now that broker truth is honest, re-run
  WFO at `--bars 50000` against the live-data window and update the
  expectancy model. Phase 9.A scoreboard at 10k bars is a starting
  point.

**Legend:**
- **Effort:** S = <1 hour, M = 1–4 hours, L = 4–16 hours, XL = multi-session.
- **Deps:** prerequisite task IDs.
- **Risk:** what could go wrong / what would invalidate the design.

---

## Track A — User-action (only you can do)

### A1. Rotate the Telegram bot token
- **Goal:** Replace the token in `.env` that's been visible in this session and on disk since Phase 0.
- **Files:** `.env` (your edit, locally — never committed).
- **Acceptance:** The old token (`8854671551:AAGOwQ3wa…`) returns 401 from `https://api.telegram.org/bot<TOKEN>/getMe`; the new one returns 200.
- **Deps:** —
- **Effort:** S (5 minutes).
- **Risk:** Forgetting to do it. The .env is gitignored so the new token never lands in git, but the old one is presumed compromised until revoked.
- **Procedure:** `@BotFather` → pick the bot → `/revoke` → `/token` → paste new value into `.env`.

### A2. Enable GitHub branch protection on `main`
- **Goal:** Enforce the no-direct-push-to-main policy you set up after the first push.
- **Files:** GitHub web UI (Settings → Branches).
- **Acceptance:** A direct `git push origin main` fails with `branch protection rule`. PRs to `main` must have ≥1 approval and a green `tests` + `lint` check.
- **Deps:** —
- **Effort:** S (2 minutes).
- **Risk:** Setting it too tight (require code owners on a solo repo blocks every PR). Recommended: require PR + status checks, allow self-approval.

---

## Track B — Research path to a deployable edge (§16 plan)

The six §16 steps from `docs/findings.md`. Each one is gated by a numeric
acceptance bar; failing a gate means the next step doesn't happen, period.

### B1. Step 1 — `GRIDS["rr2plus"]` (RR ≥ 2:1 sweep grid)
- **Goal:** Strip loss-prone tight-RR combos from the sweep grid. The §15 finding showed both holding pairs picked rr=5; the failing pairs picked rr=1.2–3.1 and lost to friction.
- **Files:**
  - `src/ictbot/engine/sweep.py` — add `GRIDS["rr2plus"]` with 48 combos:
    - `(sl, tp)` ∈ {(0.003, 0.010), (0.003, 0.015), (0.003, 0.025), (0.005, 0.015), (0.005, 0.025), (0.008, 0.025)} — all rr ≥ 2:1, most ≥ 3:1.
    - `poi_tol` ∈ {0.0015, 0.003, 0.005, 0.01}
    - `require_fvg` ∈ {True, False}
  - `src/ictbot/engine/sweep.py`, `src/ictbot/engine/wfo.py` — add `--grid {default,quick,rr2plus}` CLI flag; CLI dispatcher in `cli/__main__.py` already passes flags through.
  - `tests/test_sweep_grid.py` (new) — assert every combo in `GRIDS["rr2plus"]` has `tp / sl ≥ 2.0`.
- **Acceptance:**
  1. New unit test passes: every rr2plus combo has rr ≥ 2.
  2. `python -m ictbot wfo --all --bars 50000 --grid rr2plus --invert` (follow mode) produces ≥ 2 pairs with verdict `✅ holds` AND TRAIN > 0 AND TEST > 0 AND TEST closures ≥ 20.
- **Deps:** —
- **Effort:** M (1–2 hours: grid + CLI plumbing + test + run + write findings §17).
- **Risk:** The 48-combo grid still misses the right RR for some pair. Mitigation: leave `GRIDS["default"]` untouched as escape hatch; rr2plus is opt-in.

### B2. Step 2 — ATR-scaled stops grid
- **Goal:** Replace fixed-fraction stops with ATR-scaled stops so friction tracks volatility per pair instead of being identical across regimes.
- **Files:**
  - `src/ictbot/engine/sweep.py` — `GRIDS["atr"]` with 48 combos: `(sl_atr, tp_atr) ∈ {(0.5,1.5), (0.5,2.5), (1.0,2.0), (1.0,3.0), (1.0,5.0), (1.5,3.0)}`, same `poi_tol` × `require_fvg` outer product.
  - `src/ictbot/engine/sweep.py` — extend `run_sweep` to forward `sl_atr_mult` + `tp_atr_mult` (currently hard-codes fixed-fraction). Same for `wfo.py`.
  - `tests/test_atr_grid.py` (new) — assert sweep iterates ATR combos and forwards both mult params.
- **Acceptance:** `python -m ictbot wfo --all --bars 50000 --grid atr --invert` lifts ≥ 3 pairs above the same bar (TRAIN > 0, TEST > 0, n ≥ 20).
- **Deps:** B1 (so we can compare ATR-grid winners against rr2plus winners on equal footing).
- **Effort:** M (2–3 hours).
- **Risk:** ATR over the 1m frame may produce stops too tight; pre-check by running `python -m ictbot backtest BTC/USDT:USDT --bars 5000 --sl-atr 1.0 --tp-atr 3.0` and inspecting one fired signal's SL/TP distances.

### B3. Step 3 — Widen the signal funnel
- **Goal:** Get signal count above n ≥ 30 per 25k TRAIN bars so the WR estimate is statistically meaningful at high RR.
- **Files:**
  - `src/ictbot/settings.py` — flip `POI_TAP_TOLERANCE` default from 0.0015 → 0.005 (every §15 holding config used 0.005+).
  - `src/ictbot/strategy/ict_pro_max.py` — `require_fvg` constructor default goes from `True` → `False` (every §15 holding config had `fvg=False`).
  - `src/ictbot/indicators/delta.py` — add `get_relative_delta(df, window=20)`: returns `delta / median_of_abs_delta_over_window`, so the BUY/SELL condition becomes "delta significant for this regime" instead of "absolute sign positive/negative."
  - `src/ictbot/strategy/ict_pro_max.py` — new constructor arg `delta_mode: Literal["sign", "relative"]`, default `"sign"` for backwards compat.
  - `tests/test_funnel.py` (new) — sweep shows ≥ 30 signals/25k bars on at least 3 pairs.
- **Acceptance:** signal count per pair per 25k TRAIN bars ≥ 30 AND WR ≥ 35 % at RR ≥ 3.
- **Deps:** B2 (we need a known-good baseline before changing strategy defaults).
- **Effort:** M (2–3 hours).
- **Risk:** Loosening conditions may degrade gross edge faster than it improves sample size. Mitigation: introduce each change one at a time, A/B vs baseline on the same window.

### B4. Step 4 — Killzone + regime gate A/B
- **Goal:** Decide whether `killzone_required=True` and/or `skip_in_low_vol=True` improve the edge — or just add complexity that doesn't pay.
- **Files:**
  - `src/ictbot/runtime/sessions.py` — **first fix the bug from S7 below** (sessions should accept an explicit timestamp for backtesting, not always use `datetime.now()`). Otherwise the gate is uniformly on/off across an entire replay.
  - `src/ictbot/engine/backtest.py` — pass `session` per bar instead of session from `get_sessions()` once at start. Compute session from the bar's `time` via a new `session_for_bar(timestamp)` helper.
  - A/B experiment script (`/tmp/wfo_gates_ab.py`) — 4 runs per pair: no gates, killzone only, regime only, both. Same 50k window.
- **Acceptance:** at least one gate setting lifts WR by ≥ 5 pp OR raises expectancy by ≥ 0.2R vs baseline. If yes, lock in that gate (update `STRATEGY_MODE` defaults + tests). If no, leave both gates as opt-in and don't add complexity.
- **Deps:** B3 + S7 (bar-time-aware sessions must land first).
- **Effort:** L (4–6 hours: bug fix + plumbing + experiment + write-up).
- **Risk:** Bar-time sessions break the existing scanner (it uses `datetime.now()` for "current" session). Mitigation: scanner calls `session_for_bar(now)` as a special case.

### B5. Step 5 — 30-day paper-trade vs backtest comparison
- **Goal:** Verify the chosen strategy + grid combination behaves the same on live data over a calendar month as it did in the WFO backtest.
- **Files:**
  - `src/ictbot/orchestrator/paper_runner.py` (new) — long-running loop: on each new 1m bar from `data.bybit.BybitExchange`, call `analyze_pair`; if signal, place an order on `PaperBroker` instead of (or in addition to) Telegram alert. Write each trade to `data/journal/paper_trades.json`.
  - `scripts/compare_paper_vs_backtest.py` (new) — read both journals, compute net_R per trade, plot the two equity curves side-by-side.
  - `ui/app.py` — surface paper-trade equity curve on the dashboard.
- **Acceptance:** per-trade net expectancy of the paper-trade run is within ±0.2R of the backtest expectancy over the same window, across ≥ 30 closed paper trades.
- **Deps:** B1–B4 must have produced a config that meets the bars. C2 (orchestrator wiring) must land first so the paper broker is reachable from the scanner.
- **Effort:** L (calendar-month wait + ~6 hours of plumbing).
- **Risk:** A divergence > 0.2R signals execution slippage we haven't modelled (e.g., the 1m bar's close ≠ where we'd actually fill). Mitigation: log fill prices vs theoretical prices and write up the gap.

### B6. Step 6 — First live trade, gated
- **Goal:** Flip `ENABLE_LIVE_TRADING=true` for one pair, 0.5% risk/trade, 1R daily loss cap. Survive 30 calendar days.
- **Files:**
  - `.env` — set `ENABLE_LIVE_TRADING=true`.
  - `src/ictbot/settings.py` — add `LIVE_ALLOWED_PAIRS` setting (default empty set), used by `BybitLiveBroker(allowed_pairs=settings.live_allowed_pairs)`.
  - `src/ictbot/portfolio/caps.py` — verify defaults match (1R daily cap, 1 max open, 20% max DD).
  - `src/ictbot/ui/app.py` — display live-trading state + one-click kill button (kill = set `ENABLE_LIVE_TRADING=false` and cancel all open orders).
- **Acceptance:** 30 calendar days live trading with no cap breach, PnL within ±0.5R of expected based on signal count × backtest expectancy.
- **Deps:** B5 passed + C1 (live broker implementation) + C3 (dashboard live UI).
- **Effort:** L (calendar-month wait + ~4 hours of UI + cap defaults).
- **Risk:** Cap defaults too loose. Mitigation: start with `MAX_OPEN_POSITIONS=1`, `DAILY_LOSS_LIMIT_R=1`, `MAX_DRAWDOWN=0.05`.

---

## Track C — Execution wiring (Phase 8.5)

### C1. Implement `BybitLiveBroker.place_order`
- **Goal:** Replace the `NotImplementedError` with actual ccxt calls.
- **Files:**
  - `src/ictbot/exec/bybit_live.py` — `place_order(order)`:
    1. `self._client.create_order(symbol, "market", order.side.lower(), order.qty)` — entry.
    2. `self._client.create_order(symbol, "stop_market", opposite_side, order.qty, params={"stopPrice": order.sl, "reduceOnly": True})` — SL.
    3. `self._client.create_order(symbol, "limit", opposite_side, order.qty, order.tp, params={"reduceOnly": True})` — TP.
    4. Store `entry_order_id`, `sl_order_id`, `tp_order_id` on the `Order` object.
  - `src/ictbot/exec/bybit_live.py` — `cancel(order_id)`: cancel SL + TP, close position via market.
  - `src/ictbot/exec/bybit_live.py` — `positions()`: poll `fetch_positions(symbols=allowed)` and reconcile with local `_orders`.
  - `src/ictbot/exec/bybit_live.py` — `on_reconnect()`: handle the case where we restart and there's an open position from the previous run.
  - `tests/test_bybit_live_broker.py` — mock `ccxt.bybit().create_order` and verify the three-order bracket lands correctly. Don't hit the real exchange.
- **Acceptance:** Mocked test confirms `place_order` issues exactly 3 ccxt calls (entry/SL/TP) and records all three IDs. `cancel` issues 2 cancels + 1 reduce-only market.
- **Deps:** —
- **Effort:** L (6–10 hours of careful Bybit-specific work).
- **Risk:** Bybit's perpetual API has quirks (position mode = one-way vs hedge, `category` parameter, reduce-only flag mechanics). Mitigation: test on Bybit testnet first (`ccxt.bybit({"testnet": True})`).

### C2. Orchestrator wiring (Strategy → CapGate → Broker)
- **Goal:** Today `analyze_pair` just sends a Telegram alert and journals. Need a path that constructs a Broker, asks `CapGate` before placing, and routes the signal to whichever broker is configured.
- **Files:**
  - `src/ictbot/orchestrator/router.py` (new) — `SignalRouter(broker, cap_gate, journal, notifier)`: on a BUY/SELL signal, call `cap_gate.evaluate(open_orders=broker.positions())`; if allowed, construct `Order` from the signal, call `broker.place_order(order)`, then journal + notify.
  - `src/ictbot/orchestrator/scanner.py` — construct router with `PaperBroker` by default (or `BybitLiveBroker` if `ENABLE_LIVE_TRADING`), pass to a new `analyze_and_route(pair, router)`.
  - `tests/test_router.py` (new) — paper broker + caps; verify rejection on cap breach, success otherwise.
- **Acceptance:** Scanner with `PaperBroker` opens an `Order` for each BUY/SELL signal and reports the order in `broker.positions()`. Daily-loss-cap breach blocks subsequent signals for the rest of the calendar day.
- **Deps:** —
- **Effort:** M (3–5 hours).
- **Risk:** Threading + reentrancy if the scanner's evaluation loop overlaps with `on_bar` (paper broker fill checking). Mitigation: single-threaded loop, evaluate broker's `on_bar` first on every iteration.

### C3. Dashboard live-trading UI
- **Goal:** Live-trading state visible + killable from the Streamlit dashboard.
- **Files:**
  - `src/ictbot/ui/app.py` — new sidebar section "Live trading":
    - Red banner if `ENABLE_LIVE_TRADING=true`, green otherwise.
    - List of `LIVE_ALLOWED_PAIRS`.
    - "Kill switch" button → calls a helper that writes `ENABLE_LIVE_TRADING=false` to `.env` and cancels all open positions via the broker.
  - `src/ictbot/runtime/kill_switch.py` (new) — atomic rewrite of the `ENABLE_LIVE_TRADING` line in `.env`.
- **Acceptance:** Clicking the kill button (a) flips the env var so the next scanner iteration refuses, (b) closes any open position via the broker. State visible in the dashboard before/after.
- **Deps:** C1, C2.
- **Effort:** M (2–3 hours).
- **Risk:** Race condition between dashboard kill click and the next scanner iteration. Mitigation: kill switch sets a sentinel file the scanner checks every iteration.

---

## Track D — Observability (Phase 9 follow-up)

### D1. Scanner uses JSON logger + emits Prometheus metrics
- **Goal:** Today the scanner uses plain-text `get_logger("scanner")` and never increments any metric. The Phase 9 catalogue is dead code.
- **Files:**
  - `src/ictbot/orchestrator/scanner.py` — swap `get_logger` → `get_json_logger`. After each signal: `signals_fired_total.labels(pair=p, direction=d).inc()`. After each evaluation: `evaluations_total.labels(pair=p, outcome=o).inc()`. Wrap `analyze_pair` call in `evaluate_latency_seconds.time()`.
  - `src/ictbot/orchestrator/scanner.py` — `main()` calls `start_metrics_server(port=9100)` if `metrics.is_available()`.
  - `tests/test_scanner_emits_metrics.py` (new) — patch `metrics.signals_fired_total`, run one scanner iteration with a synthetic signal, assert `.inc()` was called.
- **Acceptance:** `curl localhost:9100/metrics | grep ictbot_signals_fired_total` returns a real counter after a signal fires.
- **Deps:** —
- **Effort:** S (1–2 hours).
- **Risk:** None significant.

### D2. Prometheus + Grafana in docker-compose
- **Goal:** Visualise the metrics from D1.
- **Files:**
  - `docker-compose.yml` — add `prometheus` service (scrapes `scanner:9100/metrics`) + `grafana` service (port 3000, datasource = prometheus).
  - `infra/prometheus.yml` (new) — scrape config.
  - `infra/grafana/dashboards/ictbot.json` (new) — pre-baked dashboard: signals/hr, win rate, equity curve, latency histogram.
- **Acceptance:** `docker compose up -d` starts all four services; Grafana at `http://localhost:3000` shows the ictbot dashboard with non-zero signals counter after the scanner runs for ≥ 30 minutes.
- **Deps:** D1.
- **Effort:** M (3–4 hours, mostly Grafana dashboard JSON).
- **Risk:** None significant.

---

## Track E — Correctness debt (S-series carryovers from PLAN.md §1.3)

### E1 (S1). Auto-discover `tick_size` from exchange metadata
- **Goal:** `round_to_tick(price, tick_size)` exists but nobody reads `tick_size` from `exchange.markets[symbol]['precision']['price']`.
- **Files:**
  - `src/ictbot/data/bybit.py` — `BybitExchange.tick_size(symbol) -> float` (lazy-load + cache via `_client.load_markets()`).
  - `src/ictbot/orchestrator/analyzer.py` — pass `tick_size=ex.tick_size(pair)` when constructing the strategy.
  - `tests/test_tick_autodiscovery.py` (new) — mocked exchange returns `{"precision": {"price": 0.5}}`; verify strategy receives `tick_size=0.5`.
- **Acceptance:** XRP backtest with `tick_size=auto` shows SL/TP at 4 decimals instead of 2; BTC shows tick = 0.5.
- **Deps:** —
- **Effort:** S (1 hour).
- **Risk:** Some Bybit symbols may not expose `precision.price`. Fall back to `round(price, 2)`.

### E2 (S2). Promote `mss_mode="swing"` to default
- **Goal:** Once §16 Steps 1–4 confirm swing-MSS doesn't kill signal frequency, flip the default.
- **Files:**
  - `src/ictbot/strategy/ict_pro_max.py` — `mss_mode: str = "swing"`.
  - `tests/` — find every test that passes `mss_mode="simple"` and decide whether to keep it (for backwards-compat coverage) or drop it (if the test is asserting current default behaviour).
- **Acceptance:** Default `python -m ictbot backtest BTC/USDT:USDT --bars 1000` uses swing-MSS; tests still pass.
- **Deps:** B4 (need empirical confirmation swing-MSS doesn't kill signal count).
- **Effort:** S (30 min).
- **Risk:** None if dependency holds.

### E3 (S3/S4/S5). Wire `is_mitigated()` into FVG and order-block engines
- **Goal:** POI uses `mitigation_bars`; FVG and OB engines don't track tap → retirement.
- **Files:**
  - `src/ictbot/indicators/fvg.py` — `get_micro_fvg(df, bias, mitigation_bars=None)`: if `mitigation_bars` is set and the FVG has been filled (price has crossed back through the gap) within `mitigation_bars`, return `"NO FVG"`.
  - `src/ictbot/indicators/poi_order_block.py` — same treatment in `find_order_block`.
  - `src/ictbot/strategy/ict_pro_max.py` — forward `mitigation_bars` into both indicator calls.
  - `tests/test_fvg_mitigation.py`, `tests/test_ob_mitigation.py` — confirm filled FVGs and tapped OBs disappear after `mitigation_bars`.
- **Acceptance:** With `mitigation_bars=10`, an FVG that gets filled at bar i disappears at bar i+11.
- **Deps:** —
- **Effort:** M (2–3 hours).
- **Risk:** None significant.

### E4 (S6). Real CVD via `ccxt.fetch_trades`
- **Goal:** Delta is a candle-color × volume proxy. Real CVD uses trade-level aggressor flags.
- **Files:**
  - `src/ictbot/data/bybit.py` — `BybitExchange.fetch_cvd(symbol, since_ms, until_ms) -> float`: paginate `fetch_trades`, sum `buy_volume - sell_volume` based on the `side` field.
  - `src/ictbot/indicators/delta.py` — `get_cvd(symbol, bar_time, exchange)` — wraps the above; falls back to current `get_delta` proxy if exchange doesn't support trades.
  - `src/ictbot/strategy/ict_pro_max.py` — new constructor arg `cvd_mode: Literal["candle", "trades"]`, default `"candle"`.
  - `tests/test_cvd.py` (new) — mocked trades feed; verify aggregation.
- **Acceptance:** Backtest with `cvd_mode="trades"` produces noticeably different delta values than `"candle"` on the same bars.
- **Deps:** —
- **Effort:** L (4–6 hours: pagination + caching + new bar-aligned aggregation).
- **Risk:** `fetch_trades` is rate-limit-expensive (no aggregated cvd endpoint). Mitigation: cache CVD per bar in the parquet cache alongside OHLCV.

### E5 (S7). Bar-time-aware sessions for backtesting
- **Goal:** `get_sessions()` uses `datetime.now()` — wrong for replays. Killzone gating is uniformly on/off across an entire backtest.
- **Files:**
  - `src/ictbot/runtime/sessions.py` — `get_sessions(at: datetime | None = None)`: if `at` is provided, compute Tokyo/London/NY status at that timestamp instead of `now`.
  - `src/ictbot/engine/backtest.py` — pass `at=entry_full["time"].iloc[i-1]` per bar instead of once at start.
  - `src/ictbot/orchestrator/analyzer.py` — when called live (no `at`), defaults to `now`.
  - `tests/test_sessions_bar_time.py` (new) — at 2026-01-01 09:00 UTC (Tokyo open), Tokyo=OPEN; at the same wall-clock seconds later but with `at=2026-01-01 16:00 UTC`, Tokyo=CLOSED.
- **Acceptance:** Backtest with `killzone_required=True` produces a different (smaller) signal count than `False`. Live scanner behaviour unchanged.
- **Deps:** —
- **Effort:** M (2–3 hours).
- **Risk:** This is a behavioural change for any caller passing `killzone_required=True` to a backtest. None passes it today.

---

## Track F — Engine perf + robustness

### F1. Bybit rate-limit retry with cooldown
- **Goal:** Promote the `/tmp/warm_cache_50k.py` retry pattern into `data/bybit.py` so all fetches survive the IP throttle.
- **Files:**
  - `src/ictbot/data/bybit.py` — `BybitExchange.fetch_ohlcv` catches `ccxt.RateLimitExceeded` + generic `"10006"` messages, sleeps `RETRY_COOLDOWN=90` seconds, retries once. Configurable via constructor arg.
  - `tests/test_bybit_retry.py` (new) — mock the ccxt client to raise once, then succeed; verify single retry.
- **Acceptance:** A unit test verifies the retry path. Integration: re-run a 50k cache warm in CI and the script finishes without manual intervention.
- **Deps:** —
- **Effort:** M (1–2 hours).
- **Risk:** Cooldown too short → retry loops infinitely on a persistent throttle. Mitigation: single retry only; after that, raise.

### F2. Engine perf round 2 — precomputed bias series
- **Goal:** `bias_sma` is still O(n) per bar (rolling SMA over the growing HTF slice). Same for `bias_slope` (EWM) and `bias_swing` (`find_swings`).
- **Files:**
  - `src/ictbot/engine/backtest.py` — at start of `run_backtest`, precompute `htf_full["close"].rolling(20).mean()` and `.rolling(50).mean()` once. Build a closure-wrapped `fast_sma_htf_bias(df)` that looks up by `len(df)-1`. Patch `ictbot.strategy.ict_pro_max.sma_htf_bias` via `unittest.mock.patch` for the run's duration (same trick as the delta prefix-sum).
  - Same treatment for `sma_ltf_bias` (uses `bias_full`).
  - For `bias_slope`, precompute `htf_full["close"].ewm(span=20, adjust=False).mean()` once.
  - For `bias_swing`, harder — `find_swings` is O(n) and the swing list grows. Skip this one unless profiling shows it dominant.
  - `tests/test_engine_bias_perf.py` (new) — assert that with the patches, a 50k backtest produces the same signal list as without (mathematical equivalence).
- **Acceptance:** Single 25k-bar backtest drops from ~2.4s to under 1s. 50k full-grid sweep finishes in under 10 minutes (currently ~30).
- **Deps:** —
- **Effort:** M (3–4 hours: profile first to confirm SMAs are the new dominant cost).
- **Risk:** Monkey-patching three more module functions makes `run_backtest` harder to reason about. Mitigation: factor the patches into a single `@contextmanager` `fast_strategy_indicators()` so the surface area is one block.

### F3. Verdict logic min-sample-size gate
- **Goal:** PAXG in findings §15 got "✅ holds" with TEST W/L = 2/6 (n=8). At that sample size the verdict is statistically meaningless.
- **Files:**
  - `src/ictbot/engine/wfo.py` — `classify(train_exp, test_exp, test_closures=None, min_closures=10)`: if `test_closures < min_closures`, return `"small sample"` instead of `"✅ holds"`/`"❌ overfit"`.
  - `src/ictbot/engine/wfo.py` `print_scoreboard` — pass `r["test_score"]["wins"] + r["test_score"]["losses"]` as `test_closures`.
  - `tests/test_wfo_verdict.py` — add cases: `classify(+1.0, +0.5, test_closures=3)` → `"small sample"`; same with `test_closures=15` → `"✅ holds"`.
- **Acceptance:** PAXG's 50k verdict re-classifies from `✅ holds` to `small sample`; XRP (TEST closures = 25) stays `✅ holds`.
- **Deps:** —
- **Effort:** S (1 hour).
- **Risk:** A pair that genuinely holds with n=8 gets demoted — but that's the right call.

---

## Track G — Code structure debt

### G1. Typed `Signal` dataclass
- **Goal:** `strategy/base.py` literally promises this in its docstring. Today `evaluate()` returns a dict that 25+ call sites unpack by string keys — fragile.
- **Files:**
  - `src/ictbot/strategy/signal.py` (new) — `@dataclass(frozen=True) class Signal` with every field currently in the result dict.
  - `src/ictbot/strategy/ict_pro_max.py` — return `Signal(...)` instead of dict. Add `.to_dict()` method for backwards compat.
  - `src/ictbot/orchestrator/analyzer.py`, `src/ictbot/engine/backtest.py`, `src/ictbot/ui/app.py` — migrate callers from `result["entry"]` → `result.entry`, etc. Or just `result.to_dict()["entry"]` to defer the migration.
- **Acceptance:** All tests still pass. Type-checker (`mypy` or `pyright`) reports no `Any` on the signal data flow.
- **Deps:** —
- **Effort:** L (4–6 hours, mostly migrating 25+ call sites).
- **Risk:** Big diff. Mitigation: keep `to_dict()` shim and migrate call sites incrementally.

---

## Track H — Documentation

### H1. Architecture Decision Records (ADRs)
- **Goal:** PLAN.md §2 scaffolded `docs/adr/` but never populated. Each ADR captures one structural decision so future-us doesn't re-relitigate.
- **Files (5 ADRs):**
  - `docs/adr/0001-fade-vs-follow.md` — the §13 → §15 saga: why we tried fade, why we tried follow, why both have no edge at 50k.
  - `docs/adr/0002-poi-engines.md` — why we kept both `min_max` and `order_block`.
  - `docs/adr/0003-data-cache.md` — Phase 5 parquet cache layout + merge semantics.
  - `docs/adr/0004-engine-perf.md` — the ATR + searchsorted + delta-prefix-sum optimisations and why monkey-patching was the right tool.
  - `docs/adr/0005-rr-floor.md` — the §16 plan as a forward-looking ADR; locks in "no live trade without TRAIN+TEST > 0 + n ≥ 20".
- **Acceptance:** 5 files, each ~1 page, following the lightweight ADR template (Context / Decision / Consequences).
- **Deps:** —
- **Effort:** M (3–4 hours total).
- **Risk:** None.

### H2. `docs/archive/architecture_ictbot_upstream.md`
- **Goal:** One-page map of the codebase. New contributors find their way in ≤ 15 minutes.
- **Files:** `docs/archive/architecture_ictbot_upstream.md` (archived upstream codebase map).
- **Sections:** module-level dependency diagram (data → indicators → strategy → engine → portfolio → exec → orchestrator → notify), explanation of the "evaluate_frames returns dict" contract, where the `Strategy` ABC lives, why we monkey-patch in run_backtest.
- **Acceptance:** Manually verifiable — show it to anyone unfamiliar with the repo and confirm they can navigate.
- **Deps:** G1 (Signal dataclass) so we document the typed contract.
- **Effort:** M (2 hours).
- **Risk:** Gets stale fast. Mitigation: link directly to file paths so file rename breaks the link visibly.

### H3. `docs/strategy_spec.md`
- **Goal:** Formal contract for the v1 ICT strategy — entry preconditions, exit rules, R-multiple definition, edge cases.
- **Files:** `docs/strategy_spec.md`.
- **Acceptance:** Reading the spec, you can implement the strategy from scratch without reading code.
- **Deps:** B4 (we want the final ICT spec, not v1).
- **Effort:** M (2–3 hours).
- **Risk:** None.

### H4. `docs/operations.md`
- **Goal:** How to run, monitor, roll back.
- **Files:** `docs/operations.md`.
- **Sections:** prerequisites, first-time setup, daily ops (start scanner, view dashboard, check metrics), incident response (scanner crashed, exchange disconnected, runaway losses), rollback (revert to last known-good commit, restore from data/journal backup).
- **Acceptance:** Each procedure walks step-by-step from a new shell.
- **Deps:** D2 (Grafana stack), C1+C2+C3 (live broker + orchestrator + dashboard).
- **Effort:** M (2–3 hours).
- **Risk:** None.

---

## Track I — Verification

### I1. Verify CI workflows actually fire on PR
- **Goal:** `.github/workflows/tests.yml` + `lint.yml` were added in Phase 10 but never exercised — we've only pushed direct to `main` and to `feat/rr2plus-grid` (no PR opened).
- **Files:** none.
- **Procedure:** open a draft PR from `feat/rr2plus-grid` → `main`; verify both workflows run, observe pass/fail, fix anything broken.
- **Acceptance:** PR shows ✓ on both `tests` and `lint` checks.
- **Deps:** B1 finished (something committed on this branch to PR).
- **Effort:** S (5 minutes if everything works, M if a workflow file has a typo).
- **Risk:** GitHub Actions may charge minutes you don't have on a free plan. Mitigation: it's a free public repo — unlimited minutes for public.

---

## Sequencing

Two pragmatic orderings. Pick one based on priority.

### Order R — research velocity first (recommended)

The premise: don't optimise the path to deploying a strategy until you've
proven the strategy has an edge.

1. **A1, A2** (5 minutes — only-you-can-do).
2. **B1** (Step 1 — rr2plus grid). 1–2 hours.
3. **F3** (verdict min-sample gate). 1 hour. Run before B1's WFO so the result is honestly classified.
4. **F1** (Bybit retry). 1–2 hours. Reduces friction on every subsequent experiment.
5. **B2** (Step 2 — ATR-scaled stops). 2–3 hours.
6. **E5** (S7 — bar-time sessions). 2–3 hours. Required by B4.
7. **B3** (Step 3 — widen funnel). 2–3 hours.
8. **B4** (Step 4 — gates A/B). 4–6 hours.
9. **Gate:** if none of B1–B4 lifts ≥ 3 pairs over the bar, STOP. Switch to a different strategy/market per §16 off-ramp. Don't continue building execution for a non-edge.
10. **C2** (orchestrator wiring). 3–5 hours.
11. **D1** (scanner JSON + metrics). 1–2 hours. Now that signals are real, observe them.
12. **B5** (Step 5 — 30-day paper trade). Calendar month + 6 hours.
13. **C1** (live broker implementation). 6–10 hours. Done while B5 runs.
14. **C3** (dashboard live UI). 2–3 hours.
15. **E1** (auto tick-size). 1 hour. Needed before live trading on low-priced assets.
16. **B6** (Step 6 — first live). Calendar month + 4 hours.
17. **Everything else** (E2/E3/E4, F2, G1, H1–H4, D2, I1) as polish.

**Total to first live trade:** ~2 calendar months including the two 30-day observation windows.

### Order S — ship-readiness first

Premise: prepare every execution rail in parallel, then evaluate strategy
edge once everything is in place. Higher risk of throwing it all away
if the strategy doesn't pan out.

1. **A1, A2** (5 minutes).
2. **C1, C2, C3, D1, D2** in parallel sub-tracks. ~3–4 days.
3. **G1, H1–H4** for code+docs cleanliness. ~1 week.
4. Then **B1 → B6** as in Order R, but the rails are already there.

**Risk:** if B1–B4 don't produce an edge, you've spent ~2 weeks on
infrastructure that may need to be reshaped for a different strategy.

---

## Track J — Audit follow-ups (carried from 2026-05-27 review)

The 2026-05-27 audit identified 28 gaps. #1–#8 landed alongside the
audit response (e2e test + per-fix regressions in
`tests/test_audit_regressions.py` + `tests/test_e2e_replay_integration.py`).
#9–#28 are tracked here.

### J1. Single-source-of-truth for journal vs broker state (audit #9)
- **Goal:** `data/journal/signals.json` is a read-only mirror of broker
  close events, not an independent settlement path.
- **Files:** `src/ictbot/portfolio/journal.py` (drop `settle_open_signals`
  altogether or make it broker-driven); router or scanner subscribes
  to close events and updates the journal.
- **Effort:** M. **Risk:** any UI that reads journal.json directly may
  need a refresh.

### J2. Exchange precision + min-notional for live qty (audit #10)
- **Goal:** `BybitExchange.qty_step(symbol)` + `min_notional(symbol)`
  read from `load_markets()['precision']['amount']` and `['limits']`.
  Router's `_qty_for_risk` rounds DOWN to the step; rejects below
  min-notional with a CapDecision-style reason.
- **Effort:** M. **Blocker for live trading on tick-sensitive pairs.**

### J3. Bybit perpetual-specific params (audit #11)
- **Goal:** Every `create_order` call passes
  `params={"category": "linear", "positionIdx": 0}`; broker construction
  calls `set_leverage(N, symbol)` for each allowed pair (N in settings).
- **Effort:** S. **Blocker for live trading on Unified accounts.**

### J4. Validate ccxt stop-trigger semantics on Bybit testnet (audit #12)
- **Goal:** Confirm `stopPrice` maps to Bybit `triggerPrice`+`triggerBy=MarkPrice`
  in the ccxt version we pin. Pin a known-good version; add an integration
  test against Bybit testnet (gated behind an env var so CI skips it).
- **Effort:** M.

### J5. SL-first ordering in backtest bar close (audit #13)
- **Goal:** Within a single bar that touches both BE-trigger and original SL,
  check SL FIRST. Today the engine promotes SL to BE first → a real loss
  becomes a break-even. Fix biases backtest rosy by the trail savings.
- **Files:** `src/ictbot/engine/backtest.py` position-close block.
- **Effort:** S. **Re-run §15/§17 after fixing.**

### J6. Live broker on_reconnect should rebuild SL/TP IDs (audit #14)
- **Goal:** `BybitLiveBroker.on_reconnect` fetches `open_orders` and
  matches reduce-only-against-position-direction to populate
  `sl_order_id`/`tp_order_id` on the stub Order. Without this, `cancel()`
  after restart leaves orphan SL/TP on the exchange.
- **Effort:** M.

### J7. Confirm-then-FILL rule for position reconcile (audit #15)
- **Goal:** `_reconcile_from_exchange` requires two consecutive
  zero-contract reads (or an order-history confirmation) before marking
  an Order FILLED. Single transient zero from a rate-limit blip should
  not free all caps.
- **Effort:** S.

### J8. evaluations_total counts errors via try/except (audit #16)
- **Goal:** Wrap `analyze_pair` in `_evaluate_with_metrics` so an
  exception path still emits `outcome="error"`.
- **Effort:** S.

### J9. File locking on journal + signal_memory (audit #17)
- **Goal:** Atomic rewrite (the kill_switch pattern) OR `filelock` on
  every JSON read-modify-write. Dashboard + scanner concurrent writes
  currently race.
- **Effort:** S.

### J10. Heartbeat + watchdog (audit #18)
- **Goal:** `scanner.py` writes `data/logs/heartbeat.ts` per iteration;
  a separate supervisor (or `monit`/systemd timer) alerts on staleness
  > 2 × iteration interval.
- **Effort:** S.

### J11. broker.equity() — real balance, not hard-coded (audit #19)
- **Goal:** Move `balance=10_000.0` out of `scanner.py:_build_router`.
  Add `equity()` method on broker protocol; PaperBroker tracks a running
  number from Account; BybitLiveBroker reads `fetch_balance`.
- **Effort:** M.

### J12. DST-aware session windows + tests (audit #20)
- **Goal:** Property tests for `_session_status` across the Mar/Oct DST
  boundaries. Today's local-hour comparison silently shifts the killzone
  by an hour on transition days.
- **Effort:** M.

### J13. Assert monotonic bar timestamps (audit #21)
- **Goal:** `BybitExchange.fetch_ohlcv` asserts
  `df["time"].is_monotonic_increasing` after pagination; raise if not.
  `np.searchsorted` in the backtest assumes monotonicity.
- **Effort:** S.

### J14. Diagnostics under delta_mode="relative" (audit #22)
- **Goal:** `_diagnose` reads `rel_delta` when `delta_mode == "relative"`
  so blocker strings reflect the gate that actually fired.
- **Effort:** S.

### J15. evaluate_frames keeps a Strategy instance (audit #23)
- **Goal:** Construct `ICTProMaxStrategy` once per
  `(bias_engine, poi_engine, mode, knobs)` tuple; reuse across calls.
  Removes 50k constructor calls per backtest.
- **Effort:** M.

### J16. Property tests on ICTProMaxStrategy.evaluate (audit #25)
- **Goal:** `hypothesis` tests for invariants — e.g. "fade(fade(x)) == x"
  on SL/TP geometry, "every BUY's tp > entry > sl" for ATR + fixed-frac
  paths, "confidence ∈ {0,25,50,75,100} for every input".
- **Effort:** M.

### J17. Fault-injection tests for live bracket (audit #26)
- **Goal:** Already covered by J5 regression tests in
  `tests/test_audit_regressions.py::test_sl_failure_triggers_emergency_flatten`
  and the TP-fail variant. Extend with cancel-also-fails and
  network-flap-then-recover.
- **Effort:** S.

### J18. Retire tight-RR combos from GRIDS["default"] (audit #27)
- **Goal:** After §16 validates `rr2plus`, delete RR < 2 combos from
  `GRIDS["default"]` (or rename to `GRIDS["legacy"]`).
- **Deps:** §17 (the gates A/B writeup must agree rr2plus is the path).
- **Effort:** S.

### J19. OB mitigation indexed to OB's own bar (audit #28)
- **Goal:** `is_mitigated` for OBs should measure bars-since-tap from
  the OB's index, not from `len(df) - 1`. Today a deep-history OB can
  be incorrectly classified as "mitigated" by a tap that happened after
  the OB stopped being relevant.
- **Files:** `src/ictbot/indicators/poi_order_block.py:78-86`.
- **Effort:** S.

---

## Done / Won't-do

For completeness — things removed from the radar because they've shipped
or been explicitly de-prioritised:

- ✅ Phases 0–11 (PLAN.md §3).
- ✅ Bug fixes B1/B2/B3/P1 (PLAN.md §4.5).
- ✅ 50k follow-mode WFO + finding §15.
- ✅ Engine 6× speedup (ATR tail-slice + searchsorted + delta prefix-sum).
- ✅ Git init + 8 commits + initial GitHub push.
- ⛔ **Multi-account / multi-user.** Out of scope. Single-user single-account.
- ⛔ **Partial-fill simulation in backtest.** Out of scope until live P&L
  proves the simpler model insufficient.
- ⛔ **Maker rebate optimisation / queue-position modelling.** Out of
  scope at retail volume.
- ⛔ **Different exchanges (Binance, OKX).** Out of scope until Bybit
  live trading has 90+ days of data validating the strategy.

---

*This roadmap is meant to be a living doc. When a task lands, mark it
✅ in the relevant track and link the PR. When new gaps surface, append
them to the relevant track with the same Goal/Files/Acceptance/Deps/
Effort/Risk format.*
