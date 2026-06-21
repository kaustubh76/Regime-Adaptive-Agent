# ictbot Architecture

> A one-stop map of the codebase. If a new contributor can't navigate
> the system from this page in 15 minutes, the doc is wrong.

This document has eight sections:

1. [30-second overview](#1-30-second-overview)
2. [Runtime processes](#2-runtime-processes)
3. [Module layer dependency map](#3-module-layer-dependency-map)
4. [The ICT evaluation pipeline](#4-the-ict-evaluation-pipeline)
5. [Live signal → order flow](#5-live-signal--order-flow)
6. [Backtest replay flow](#6-backtest-replay-flow)
7. [Order lifecycle + on-disk state](#7-order-lifecycle--on-disk-state)
8. [Known holes overlay](#8-known-holes-overlay)

---

> **2026-06-06 note (updated post-Phase-9):** This document was
> authored against the pre-Phase-2 codebase (May 2026). Component
> diagrams below still apply; the following components were added or
> renamed during Phases 2–9 and are NOT yet re-drawn in the diagrams:
>
> ### Phases 2–6 (P&L plumbing + acceptance):
> - **Live brokers** are under `src/ictbot/exec/` (binance_live,
>   delta_live + factory.py + orders.py), not `core/`. Phase 17
>   removed `bybit_live`.
> - **`SignalRouter`** lives at `src/ictbot/orchestrator/router.py`
>   and now emits broker-truth journal closes via
>   `mark_closed_from_broker` (Fix 2.A + 2.F).
> - **`ShadowRouter`** wraps live + shadow legs at
>   `src/ictbot/orchestrator/shadow_router.py`.
> - **`on_reconnect` recovery path** (Fix 2.I + 5.B):
>   `_build_router` → `broker.on_reconnect()` → `fetch_positions` +
>   `fetch_open_orders` → recreate `Order` stubs with non-zero risk
>   distance + `is_reconciled=True` flag.
> - **Standalone scripts** under `scripts/`:
>   `diagnose_live_pnl.py` (acceptance gate),
>   `verify_wallet_parity.py` (Fix 5.F wallet truth check),
>   `archive_journal.py` (clean-slate journal rotation),
>   `close_test_order.py` / `fire_test_order.py` (operator escape hatches).
>
> ### Phase 9 (per-token completeness, commit `429af9c`):
> - **Per-pair RR knobs** at `src/ictbot/settings.py`:
>   `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` env Field aliases +
>   `settings.get_sl_frac(pair)` / `settings.get_tp_frac(pair)`
>   helpers that derive the base-asset token from the ccxt pair
>   string and fall back to global on miss (Fix 9.A).
> - **New cap** at `src/ictbot/portfolio/caps.py`:
>   `MaxConcurrentSameDirection(max_same=MAX_SAME_DIRECTION)`.
>   `CapGate.evaluate` now forwards `**ctx` (e.g. `side=`) so caps
>   that need signal context get it; older caps ignore via `**_`
>   (Fix 9.B).
> - **Per-pair init** at `src/ictbot/exec/binance_live.py`:
>   `_ensure_pair_init(pair)` runs `set_margin_mode("ISOLATED", pair)`
>   + `set_leverage(5, pair)` then reads back via `fetch_positions`.
>   Defers strict check on Binance `-4046` (no need) / `-4047`
>   (can't change while position open) / `-4048` so the broker
>   doesn't fail to construct when state is locked. `on_reconnect`
>   re-asserts on restart (Fix 9.C).
> - **Precision helpers** at `src/ictbot/exec/binance_live.py`:
>   `_amount_to_precision(pair, qty)` and `_price_to_precision(pair, price)`
>   wrap ccxt's official helpers and stamp normalized values back
>   onto the `Order` at the four `create_order` call sites
>   (entry / SL / TP / re-anchor) so the journal and the exchange
>   agree (Fix 9.D).
> - **Boot readiness gate** at `src/ictbot/exec/binance_live.py`:
>   `verify_pair_readiness(pair)` aggregates leverage / margin /
>   ticker / min_notional / sized notional per pair;
>   `verify_all_pairs_ready()` returns a `{pair: status}` map.
>   Scanner's `_build_router` calls this after `on_reconnect` and
>   prints a banner; refuses to start under `STRICT_PAIR_INIT=true`
>   if any pair fails (Fix 9.E).
> - **Boot order** in `src/ictbot/orchestrator/scanner.py`
>   `_build_router`: `build_live_broker` →
>   `BinanceLiveBroker.__init__` runs `_ensure_pair_init(pair)` for
>   each pair → `broker.on_reconnect()` (re-asserts +
>   reconciles open positions) → `verify_all_pairs_ready()` →
>   `SignalRouter(...)` → caps wired (including
>   `MaxConcurrentSameDirection`) → scanner main loop.
> - **New scripts** under `scripts/`:
>   `wfo_per_pair.py` (drives `engine.wfo` across 5 pairs,
>   writes `data/wfo/per_pair_<date>.json`),
>   `smoke_test_pairs.py` (testnet round-trip per pair, writes
>   `data/smoke_pairs_<date>.json`),
>   `diagnose_live_pnl.py --smoke-gate` (per-pair Phase 9
>   acceptance: exit 0 = all pairs have ≥1 broker-truth close).
>
> See [autotrade_plan.md](autotrade_plan.md) for the full Phase 2–9
> rollout log + commit chain.

## 1. 30-second overview

```
                    ┌─────────────────────────────────────────────┐
                    │      Binance USDT-M Futures (testnet)       │
                    │  (OHLCV + trades + order placement REST)    │
                    └────────────────┬────────────────────────────┘
                                     │
                        ccxt.binance │ HTTPS
                                     │
        ┌────────────────────────────┼───────────────────────────┐
        │                            ▼                           │
        │                ┌───────────────────────┐               │
        │                │  data/binance.py      │               │
        │                │  BinanceExchange      │               │
        │                │  + parquet cache      │               │
        │                └───────────┬───────────┘               │
        │                            │ pandas DataFrames         │
        │                            ▼                           │
        │   ┌─────────────────────────────────────────────────┐  │
        │   │   indicators/    (atr, mss, fvg, poi, delta…)   │  │
        │   └────────────────────────┬────────────────────────┘  │
        │                            ▼                           │
        │   ┌─────────────────────────────────────────────────┐  │
        │   │   strategy/ict_pro_max.py                       │  │
        │   │   Strategy.evaluate(htf,bias,poi,entry,session) │  │
        │   │   → result dict (entry, sl, tp, rr, conf, …)    │  │
        │   └────────────────────────┬────────────────────────┘  │
        │                            │                           │
        │  ┌─── LIVE PATH ───────────┼──── OFFLINE PATH ───┐     │
        │  ▼                         ▼                     ▼     │
        │ ┌──────────────────┐  ┌─────────────────┐ ┌──────────┐ │
        │ │ orchestrator/    │  │ orchestrator/   │ │ engine/  │ │
        │ │ scanner.py       │  │ analyzer.py     │ │ backtest │ │
        │ │ (infinite loop)  │  │ (one-shot)      │ │ sweep wfo│ │
        │ └────────┬─────────┘  └────────┬────────┘ │ compare  │ │
        │          ▼                     │          └────┬─────┘ │
        │  ┌──────────────────┐          │               │       │
        │  │ orchestrator/    │          │               │       │
        │  │ router.py        │          │               │       │
        │  │ (CapGate→Broker) │          │               │       │
        │  └────┬─────┬───────┘          │               │       │
        │       │     │                  │               │       │
        │       ▼     ▼                  ▼               ▼       │
        │  ┌────────┐ ┌────────┐  ┌─────────────┐  ┌──────────┐  │
        │  │ paper. │ │binance_│  │ notify/     │  │ ui/app.py│  │
        │  │ py     │ │ live   │  │ telegram.py │  │ Streamlit│  │
        │  │ Broker │ │ Broker │  │             │  │          │  │
        │  └────────┘ └───┬────┘  └─────────────┘  └──────────┘  │
        │                 │                                      │
        │                 └─ (gated by ENABLE_LIVE_TRADING        │
        │                    + LIVE_ALLOWED_PAIRS + kill switch) │
        │                                                        │
        │   portfolio/   {caps, account, journal}                │
        │   runtime/     {logger, metrics, sessions, kill_switch}│
        │                                                        │
        └────────────────────────────────────────────────────────┘
                              ictbot process(es)
```

**Three callers, one strategy:**
- The **scanner** drives the strategy on a 30-second loop and routes signals into a broker.
- The **dashboard** (Streamlit) reads the same strategy output for visualisation only.
- The **engine** CLI tools (`backtest`, `sweep`, `wfo`, `compare`) replay history through the same strategy offline.

---

## 2. Runtime processes

Three things actually *run*. Everything else is a library imported by these.

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ Process: scanner                                                 │
 │ Entry:   python -m ictbot.orchestrator.scanner                   │
 │                                                                  │
 │   while True:                                                    │
 │     if kill_switch.is_engaged(): sleep(30); continue             │
 │     for pair in PAIRS:                                           │
 │        result = analyze_pair(pair)        # fetch + evaluate     │
 │        if result.entry in {BUY,SELL}:                            │
 │           router.route(result)            # caps → broker        │
 │           telegram.send(...)              # dedup'd by signal    │
 │     sleep(30)                                                    │
 │                                                                  │
 │  Sidecars: prometheus /metrics on :9100  +  data/logs/*.json.log │
 └──────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────┐
 │ Process: dashboard                                               │
 │ Entry:   streamlit run src/ictbot/ui/app.py                      │
 │                                                                  │
 │   Reads:  data/journal/signals.json                              │
 │           data/runs/backtest_curve.json                          │
 │           live evaluate_frames() per UI pair                     │
 │   Writes: nothing (except via the kill switch button → engage()) │
 └──────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────┐
 │ Process: engine CLI tools (one-shot)                             │
 │ Entry:   python -m ictbot.engine.{backtest|sweep|wfo|compare}    │
 │                                                                  │
 │   Fetch history (optionally via parquet cache)                   │
 │   Replay bar-by-bar through ICTProMaxStrategy                    │
 │   Print report; optionally write backtest_curve.json             │
 └──────────────────────────────────────────────────────────────────┘
```

The three processes never communicate directly. They share state only through `data/` (JSON + parquet + log files).

---

## 3. Module layer dependency map

Arrows are import direction. Lower layers never import upper ones.

```
 LAYER 7  Entry points         ┌──────────────────────────────────┐
                               │  cli/__main__.py  ui/app.py      │
                               │  orchestrator/scanner.py         │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 6  Orchestration        ┌────────────────▼─────────────────┐
                               │  orchestrator/analyzer.py        │
                               │  orchestrator/router.py          │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 5  Offline engines      ┌────────────────▼─────────────────┐
                               │  engine/{backtest,sweep,wfo,     │
                               │          compare,sizing}.py      │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 4  Strategy             ┌────────────────▼─────────────────┐
                               │  strategy/base.py (ABC)          │
                               │  strategy/ict_pro_max.py         │
                               │  strategy/signal.py (G1, typed)  │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 3  Side-effect          ┌────────────────▼─────────────────┐
          subsystems           │  portfolio/{caps,account,journal}│
                               │  exec/{broker,paper,binance_live,│
                               │         delta_live,orders}.py    │
                               │  notify/telegram.py              │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 2  Indicator primitives ┌────────────────▼─────────────────┐
                               │  indicators/{atr,bias_sma,       │
                               │   bias_slope,structure,mss,fvg,  │
                               │   poi_min_max,poi_order_block,   │
                               │   delta,risk,regime,mitigation,  │
                               │   tick}.py                       │
                               └────────────────┬─────────────────┘
                                                │
 LAYER 1  Data + runtime       ┌────────────────▼─────────────────┐
          infrastructure       │  data/{delta,binance,cache,      │
                               │        replay,exchange,          │
                               │        factory}.py               │
                               │  exec/factory.py                 │
                               │  runtime/{logger,metrics,        │
                               │   sessions,kill_switch,          │
                               │   signal_memory}.py              │
                               │  settings.py                     │
                               └──────────────────────────────────┘

 Exchange swap (Delta ⇄ Binance) is a single setting:
   .env: EXCHANGE=delta     (default — delta.exchange perpetuals)
   .env: EXCHANGE=binance   (current testing venue — Binance USDT-M Futures)

   data/factory.py::get_default_exchange()  picks the data adapter
   exec/factory.py::build_live_broker()     picks the live broker
   Both venues use the same ccxt symbol format (BTC/USDT:USDT) and
   the same OHLCV DataFrame shape, so callers above this layer are
   venue-agnostic.
```

Rules of the layer cake:
- **Indicators are pure.** No I/O, no globals, deterministic on DataFrames. If you reach for `time.now()` inside `indicators/`, you broke the rule.
- **Strategy composes indicators.** No exchange, no notification, no journal.
- **Side-effect subsystems hide I/O.** `journal.py` writes JSON; `binance_live.py` writes orders; `telegram.py` posts HTTP. These are the only files allowed to mutate the world outside the process.
- **Engine + orchestrator wire the layers.** They are the only modules permitted to import from both strategy and side-effect subsystems.

---

## 4. The ICT evaluation pipeline

What actually happens inside `Strategy.evaluate()` — the 4-timeframe ICT funnel that produces a BUY/SELL signal.

```
   ┌──────────────────────────────────────────────────────────┐
   │  INPUT FRAMES  (oldest → newest, naive UTC timestamps)   │
   │                                                          │
   │   htf_df    4h    bars   ≥ 50   (htf bias)               │
   │   bias_df   15m   bars   ≥ 20   (ltf bias, diag)         │
   │   poi_df    3m    bars   ≥ 20   (POI tap check)          │
   │   entry_df  1m    bars   ≥ 5    (MSS, FVG, delta, ATR)   │
   │   session   dict          {killzone_active, tokyo, …}    │
   └─────────────────────────────┬────────────────────────────┘
                                 │
                  ┌──────────────┼──────────────┐
                  │              │              │
                  ▼              ▼              ▼
        ┌─────────────────┐ ┌──────────┐ ┌──────────────┐
        │ HTF bias        │ │ POI      │ │ MSS (1m)     │
        │ engine ∈ {sma,  │ │ engine ∈ │ │ mode ∈ {     │
        │  swing, slope}  │ │ {min_max,│ │  simple,     │
        │ → BULL/BEAR     │ │  ob}     │ │  swing}      │
        └────────┬────────┘ │ → level  │ │ → MSS|NO MSS │
                 │          └─────┬────┘ └──────┬───────┘
                 │                │             │
                 │       poi_tap (dist < tol)?  │
                 │                │             │
                 ▼                ▼             ▼
        ┌──────────────────────────────────────────────────┐
        │ Confidence (4 × 25 = 100)                        │
        │    +25 POI tapped                                │
        │    +25 MSS direction matches HTF bias            │
        │    +25 micro-FVG (or skipped if require_fvg=F)   │
        │    +25 delta sign agrees with HTF bias           │
        │             ↳ delta_mode=sign  : delta > 0       │
        │             ↳ delta_mode=relative : |rel| > thr  │
        └────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │ Environmental gates (opt-in)                     │
        │   killzone_required  ?  London|NY OPEN           │
        │   skip_in_low_vol    ?  regime != LOW_VOL        │
        │     → if any gate blocks: gate_blocked = reason  │
        └────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │ Entry decision                                   │
        │   bullish_setup = bias=BULL ∧ tap ∧ MSS+ ∧ fvg+  │
        │                   ∧ delta_buy ∧ ¬gate            │
        │   bearish_setup = mirror                         │
        │   else: NO ENTRY                                 │
        │                                                  │
        │ SL/TP:                                           │
        │   if sl_atr_mult & tp_atr_mult:                  │
        │       sl = price - mult * ATR(14)                │
        │       tp = price + mult * ATR(14)                │
        │   else:                                          │
        │       sl = price * (1 ± sl_frac)                 │
        │       tp = price * (1 ± tp_frac)                 │
        │                                                  │
        │ price rounded by round_to_tick(p, tick_size)     │
        │   ⚠ POI itself is still round(p,2) — see §8      │
        └────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │ Fade flip (if strategy_mode == "fade")           │
        │   BUY ↔ SELL ; reflect SL/TP across entry        │
        └────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │ RESULT DICT                                      │
        │  identity   : pair, error                        │
        │  prices     : price, last_close                  │
        │  ict stack  : htf_bias, ltf_bias, ltf_poi,       │
        │               poi_tap, ltf_mss, fvg, delta,      │
        │               relative_delta, delta_mode, atr_1m │
        │  signal     : entry, sl, tp, rr, confidence      │
        │  gates      : gate_blocked, regime               │
        │  diag       : buy_blockers, sell_blockers,       │
        │               closest_direction, near_miss       │
        │  session    : india_time, tokyo/london/ny + sts  │
        │  frames     : ltf_df, poi_df (for UI charts)     │
        └──────────────────────────────────────────────────┘
```

Confidence is **diagnostic, not gating** — even at 75 % a single missing condition keeps `entry = "NO ENTRY"`. All four 25-point bits must light up.

---

## 5. Live signal → order flow

This is what happens on every iteration of the scan loop for one pair.

```
                  ┌────────────────────────────┐
                  │  scanner._evaluate_with_   │
                  │  metrics(pair)             │  ← Prom histogram
                  └─────────────┬──────────────┘
                                │
                                ▼
                  ┌────────────────────────────┐
                  │  analyzer.analyze_pair(p)  │
                  │   1. get_data × 4 frames   │ ← ccxt.bybit
                  │   2. evaluate_frames(…)    │ ← Strategy
                  │   3. settle_open_signals() │ ← journal SL/TP check
                  │   4. telegram send if new  │ ← signal_memory dedup
                  │   5. append_signal()       │ ← journal write
                  └─────────────┬──────────────┘
                                │ result dict
                                ▼
            ┌───────────────────────────────────────────┐
            │  scanner._route_signal(router, result)    │
            └───────────────────────────────────────────┘
                                │
                                ▼
            ┌───────────────────────────────────────────┐
            │  SignalRouter.route(result)               │
            │                                           │
            │   open = broker.positions()  ── ─ ─ ─ ─ ─ │ ── ─ ─ ─ ─┐
            │   d    = cap_gate.evaluate(open_orders=…) │           │
            │   if not d.allow:                         │           │
            │       journal REJECTED, return            │           │
            │                                           │           │
            │   qty  = _qty_for_risk(bal, risk%, …)     │           │
            │   ord  = Order(pair, side, entry, sl, tp, │           │
            │                qty=qty)                   │           │
            │   broker.place_order(ord)                 │           │
            └───────────────────────┬───────────────────┘           │
                                    │                               │
              ┌─────────────────────┴─────────────────────┐         │
              ▼                                           ▼         │
       ┌─────────────────┐                       ┌─────────────────┐│
       │ PaperBroker     │                       │ BybitLiveBroker ││
       │  fills @ entry  │                       │  3 ccxt calls:  ││
       │  on_bar()       │                       │   market entry  ││
       │  drives TP/SL   │                       │   stop-market SL││
       │  (deterministic)│                       │   limit TP      ││
       │                 │                       │   reduce_only   ││
       │  ⚠ never called │                       │  ⚠ no rollback ││
       │     from        │                       │     on partial  ││
       │     scanner — §8│                       │     failure §8  ││
       └────────┬────────┘                       └────────┬────────┘│
                │                                         │         │
                └───────────────────┬─────────────────────┘         │
                                    │                               │
                                    ▼                               │
                          ┌─────────────────────┐                   │
                          │ data/journal/       │                   │
                          │ signals.json append │                   │
                          └─────────────────────┘                   │
                                                                    │
                          ┌─────────────────────────────────────────┘
                          │
                          ▼
                ┌────────────────────────────┐
                │ caps:                      │
                │   MaxOpenPositions ✓ uses  │
                │     broker.positions()     │
                │   DailyLossLimit  ⚠ never  │
                │     fed close R-multiples  │
                │   MaxDrawdown     ⚠ same — │
                │     Account.book_close()   │
                │     never called           │
                └────────────────────────────┘
```

Three pieces of state the live path mutates:
1. `data/journal/signals.json`   — every fired signal (and rejections).
2. `data/journal/last_signal.json` — last Telegram-sent `{pair}_{direction}` for dedup.
3. `broker._orders` (in-memory) — paper or live; reconciled with exchange in live mode.

---

## 6. Backtest replay flow

Why backtest looks "the same but isn't" — and where the engine optimisations bend the indicator contract.

```
 fetch_history(pair, bars)
   │ paginates ccxt.fetch_ohlcv backwards in time, with optional
   │ parquet-cache write/read (data/cache/bybit/<symbol>/<tf>.parquet)
   ▼
 history = {htf, bias, poi, entry}   # full DataFrames, oldest → newest
   │
 ┌─┴───────────────────────────────────────────────────────────────┐
 │ run_backtest(pair, bars, …)                                     │
 │                                                                 │
 │  Pre-loop monkey-patches (only for this run's duration):        │
 │    delta_prefix  = cumulative signed-volume on entry_full       │
 │      → patches ictbot.strategy.ict_pro_max.get_delta            │
 │    htf_sma{20,50}/bias_sma{10,20} precomputed on full series    │
 │      → patches sma_htf_bias / sma_ltf_bias (O(n) per bar→O(1))  │
 │    (rationale: ADR 0004 — engine perf, ATR tail-slice + these)  │
 │                                                                 │
 │  For i in range(start, end+1):                                  │
 │     T = entry_times[i-1]                                        │
 │     session = get_sessions(at=T)         # E5: bar-time aware   │
 │                                                                 │
 │     if active_position:                                         │
 │        trail-to-BE check (⚠ runs BEFORE SL check — see §8)      │
 │        SL/TP fill against bar.high/bar.low                      │
 │        on close → compute net_R = gross_R - friction_R          │
 │        signals.append(); active_position = None                 │
 │        continue                                                 │
 │                                                                 │
 │     # No open position — slice all 4 frames at time T           │
 │     htf_w  = htf_full.iloc[:searchsorted(htf_times, T)]         │
 │     bias_w = bias_full.iloc[:searchsorted(bias_times, T)]       │
 │     poi_w  = poi_full.iloc[:searchsorted(poi_times, T)]         │
 │     entry_w = entry_full.iloc[:i]                               │
 │                                                                 │
 │     r = evaluate_frames(htf_w, bias_w, poi_w, entry_w, session) │
 │                                                                 │
 │     if r.entry in {BUY,SELL}:                                   │
 │        active_position = {entry, sl, tp, rr, orig_sl, …}        │
 │     elif near_miss: record blocker                              │
 │                                                                 │
 │  Restore all monkey-patches.                                    │
 └─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
 report = {pair, bars_scanned, counts, signals, near_misses}
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      backtest print_report   sweep _score   wfo classify()
                                                    │
                                       {no edge | small sample |
                                        ✅ holds  | ❌ overfit  |
                                        no closures}
```

Two important asymmetries between backtest and live:
- **`entry_window` grows monotonically** in backtest (`entry_full.iloc[:i]`). In live, `entry_df` is a fixed 300-bar tail. Any indicator that aggregates over the *whole frame* (today: `get_delta`) computes a different thing in the two paths. See §8.
- **`session` is bar-time-aware in backtest**, wall-clock-now in live. Same call, different behaviour, by design.

---

## 7. Order lifecycle + on-disk state

### Order state machine

```
              ┌─────┐
              │ NEW │  ← created in router.route() (not yet placed)
              └──┬──┘
                 │ broker.place_order(order)
                 ▼
            ┌────────┐
            │  OPEN  │  ← position is live (paper: instant; bybit: 3-leg)
            └───┬────┘
                │                          ┌───────────────────┐
       ┌────────┼──────────────┐           │ cancel / exchange │
       │        │              │           │ rejection         │
       ▼        ▼              ▼           ▼                   │
 ┌─────────┐  ┌────────┐  ┌────────┐   ┌───────────┐  ┌────────┴┐
 │ FILLED  │  │ FILLED │  │ FILLED │   │ CANCELLED │  │REJECTED │
 │ TP hit  │  │ SL hit │  │ manual │   │           │  │         │
 └─────────┘  └────────┘  └────────┘   └───────────┘  └─────────┘

  close_price + close_reason ∈ {"TP","SL","MANUAL"} populated on FILLED
  realised_pnl_R() = (close - entry) / |entry - sl|   (sign-aware)
```

PaperBroker drives this transition via `on_bar(pair, bar)`. BybitLiveBroker drives it via `_reconcile_from_exchange()` polling `fetch_positions`.

### State storage on disk

```
 Rahul_ideation/
 ├── .env                              secrets + ENABLE_LIVE_TRADING flag
 │
 └── data/                              (all gitignored)
     ├── cache/                         parquet OHLCV cache
     │   └── bybit/
     │       └── BTC_USDT_USDT/
     │           ├── 1m.parquet
     │           ├── 3m.parquet
     │           ├── 15m.parquet
     │           └── 4h.parquet
     │
     ├── journal/
     │   ├── signals.json               every BUY/SELL ever fired
     │   │                              schema in portfolio/journal.py
     │   └── last_signal.json           {"signal": "BTC..._BUY"} dedup
     │
     ├── runs/
     │   └── backtest_curve.json        equity curve for the dashboard
     │
     ├── logs/
     │   ├── scanner.log                plain text (WARNING+ only)
     │   ├── scanner.json.log           structured JSON (INFO+)
     │   └── *.json.log                 one per get_json_logger(name)
     │
     └── KILL_SWITCH_ENGAGED            sentinel file (presence = halt)
                                        written by runtime.kill_switch.engage()
```

Anything that needs to survive a restart goes here. Anything in-process (broker `_orders`, signal_memory cache, Prometheus counter values) **does not** — be aware of that when reasoning about correctness across restarts.

### Key contracts (data shapes)

```
 OHLCV DataFrame             columns: time(UTC, naive), open, high, low,
                                      close, volume
                             ordering: oldest → newest, monotonic time
                             dtype:   time=datetime64[ns], rest=float64

 Strategy.evaluate() dict    keys listed in §4 box "RESULT DICT".
                             Stable shape — UI + scanner + backtest
                             all unpack by string key.
                             Typed mirror: strategy/signal.py::Signal
                             (Signal.from_dict / .to_dict round-trip)

 Order dataclass             pair, side(BUY|SELL), entry, sl, tp, qty,
                             id, status(NEW|OPEN|FILLED|CANCELLED|
                             REJECTED), created_at, filled_at,
                             closed_at, close_price, close_reason,
                             entry/sl/tp_order_id (exchange-side)

 session dict                india_time, tokyo_time + status,
                             london_time + status, newyork_time +
                             status, active_session, allow_trade,
                             killzone_active

 CapDecision                 allow: bool ; reason: str
```

---

## 8. Known holes overlay

These are flagged in `ROADMAP.md` and an earlier deep-audit. Listed here on the architecture so you can see *where in the system* they live. Items in **bold** were missed by the roadmap and surfaced by the gap audit.

```
 LAYER 6  orchestrator/
            ├── scanner.py:191   30s sleep, but 1m bars → same bar
            │                    re-evaluated ~2× per minute ⚠ §A
            ├── scanner.py:134   no broker.on_bar() call → paper
            │                    positions never close → MaxOpen
            │                    cap deadlocks after first signal ⚠ §B
            ├── router.py:51     _qty_for_risk: no lot-step rounding,
            │                    hardcoded balance=10_000 ⚠ §C
            └── analyzer.py:174  settle_open_signals uses iloc[-1]
                                 (in-progress bar) — premature close ⚠ §D

 LAYER 5  engine/
            └── backtest.py:263  trail-to-BE check runs BEFORE SL
                                 check → optimistic intra-bar order
                                 → backtest more profitable than live ⚠ §E

 LAYER 4  strategy/
            └── ict_pro_max.py:166  get_delta(entry_df) — entry_df is
                                    300 bars live vs 50 000 bars at
                                    end of backtest. Sign of delta
                                    means different things in the two
                                    paths. Likely root cause of the
                                    §15 "no edge" finding ⚠ §F

 LAYER 3  portfolio/
            ├── caps.py:54   DailyLossLimit.record() ✓ fed by
            │                router.on_close, wired into both paper
            │                and live brokers via _on_close hook §G
            └── account.py:25 book_close() ✓ wired through router
                              on_close → cap layer sees realised R §G

          exec/
            ├── bybit_live.py:107  bracket placement ✓ partial-failure
            │                      rollback + emergency flatten §H
            ├── bybit_live.py:70   ✓ category="linear", positionIdx=0,
            │                      set_leverage on construction §I
            ├── delta_live.py:84   ✓ Delta set_leverage on construction
            │                      (parity with Bybit) §I
            ├── delta_live.py:170  ✓ contract-size aware: coin qty →
            │                      integer contracts, sub-contract
            │                      rejected with ValueError §I-Delta
            ├── bybit_live.py:122  stopPrice key — still using ccxt's
            │                      legacy mapping; verify on testnet ⚠ §J
            ├── bybit_live.py:284  ✓ 2-strike reconcile guard — transient
            │                      empty fetch_positions read no longer
            │                      finalizes on the first pass §K
            └── delta_live.py:298  ✓ 2-strike reconcile guard (Delta
                                   parity); both brokers wire fetch_order
                                   to resolve real SL/TP fill price into
                                   close_price + close_reason — feeds
                                   router.on_close → caps + account §K

 LAYER 2  indicators/
            ├── poi_min_max.py:15  hard-coded round(price, 2) bypasses
            │                      the tick-size fix; XRP at $0.5 sees
            │                      ~1 % rounding jitter vs 0.5 % tol ⚠ §L
            ├── poi_order_block.py:90  same issue in OB fallback ⚠ §L
            └── delta.py:11      sums over whole df — see §F above ⚠ §F

 LAYER 1  data/                no monotonic-time assert after pagination
                               → out-of-order Bybit pages silently
                               corrupt searchsorted slicing ⚠ §M

          runtime/sessions.py   no DST regression test ⚠ §N
          portfolio/journal.py  no file locking — concurrent writer
                                from dashboard + scanner can corrupt ⚠ §O
```

Severity (from prior audit):
- **Critical** (block live trading): §B paper-broker deadlock, §F delta semantics, §G dead caps, §H naked positions, §L POI rounding.
- **High** (silent functional gaps): §A double-eval, §D in-progress settlement, §E optimistic trail-BE, §I-K Bybit live correctness.
- **Medium**: §C balance/risk plumbing, §M-O hygiene + safety.

The unifying theme: **the components are unit-tested, but the live integration path isn't**. A single end-to-end test that replays a fixture history through `analyzer → router → paper broker → cap.record → journal` and asserts state consistency at every step would catch §A, §B, §D, §G in one go. That's where the next test PR should land.

---

## Appendix — quick navigation

| You want to change…    | Land in…                                   |
|------------------------|--------------------------------------------|
| an indicator           | `indicators/`, then wire into `ict_pro_max.py:evaluate` |
| a strategy variant     | new subclass of `strategy/base.py::Strategy` |
| a parameter grid       | `engine/sweep.py:GRIDS` (+ `_iter_combos` if shape differs) |
| a risk cap             | `portfolio/caps.py` (+ append to `CapGate.caps`) |
| a broker               | implement `exec/broker.py::Broker`, wire into `scanner._build_router` |
| a metric               | `runtime/metrics.py` (no-op shim handles missing dep) |
| a notification channel | `notify/` (mirror the `telegram.py` shape) |
| session/killzone logic | `runtime/sessions.py` (bar-time-aware via `at=…`) |
| an ADR                 | `docs/adr/000N-*.md`, link from `ROADMAP.md` |
