# ICT AI BOT PRO MAX — End-Goal Plan

> **Status:** scoping doc. Nothing here is committed code; this is the
> destination we want the repo to reach. Treat each phase as an
> independent merge-friendly chunk.

---

## 0. Why this document exists

The repo today is a working prototype: it fetches OHLCV from Bybit,
scores it through a fixed ICT checklist, pushes Telegram alerts, runs
walk-forward backtests, and renders a Streamlit dashboard. It is *not*
yet a deployable trading system. Eleven scripts sit at the project root,
secrets live next to runtime artefacts, the analyzer mutates module
globals during comparison runs, and there is no path from "BUY signal"
to "order on an exchange."

This plan describes the shape the repo should grow into, and the order
in which to migrate. We do not ship every phase at once — each phase is
a self-contained PR.

---

## 1. Gaps identified in the current implementation

### 1.1 Critical / security
| # | Gap | Where | Impact |
|---|---|---|---|
| C1 | Live Telegram bot token persisted in `.env` on disk | `.env` | Token is recoverable by anyone with shell access; rotate now. |
| C2 | No order execution — alerts only | (missing) | The "bot" cannot actually trade. |
| C3 | No portfolio-level risk: no equity tracking, no daily loss cap, no max-concurrent-position rule, no kill-switch | (missing) | First live mistake is uncapped. |
| C4 | Confidence scoring is internally inconsistent | `analyzer.evaluate_frames` (4×25) vs README (5×20, "+20 always") | Confidence numbers shown in UI are misleading. |

### 1.2 Architecture / engineering
| # | Gap | Where |
|---|---|---|
| A1 | 11 flat scripts at repo root, no package | `analyzer.py`, `backtest.py`, `sweep.py`, `wfo.py`, `bias_compare.py`, `size.py`, `bt_curve.py`, `scanner.py`, `app.py`, `journal.py`, `config.py` |
| A2 | No `pyproject.toml`; only `requirements.txt`; tests rely on `sys.path.insert` hack | `tests/conftest.py:12` |
| A3 | Module-level globals get patched at runtime to switch bias engines | `bias_compare._set_engine` writes both `config.BIAS_ENGINE` and `analyzer.BIAS_ENGINE` |
| A4 | Hard coupling to ccxt.bybit; no `Exchange` protocol | `core/exchange.py:12` |
| A5 | Every backtest refetches data — no on-disk cache, no offline replay | `core/exchange.py:get_data` |
| A6 | `analyze_pair` does fetch + evaluate + telegram + journal | `analyzer.py:288–336` |
| A7 | Runtime artefacts (`signals.json`, `last_signal.json`, `backtest_curve.json`, `scanner.log`) dumped at repo root | `config.py:38–40`, `core/logger.py:11` |
| A8 | `__pycache__` folders present throughout the working tree |  |
| A9 | No CI, no linter (ruff), no formatter (black/ruff format), no type-check (mypy/pyright), no pre-commit hook |  |
| A10 | No Dockerfile, no compose — deployment is undocumented |  |
| A11 | Single text logger; no structured/JSON logs, no metrics endpoint | `core/logger.py` |
| A12 | README mixes setup + run + empirical findings + decision log | `README.md` |
| A13 | Inconsistent CLIs across sibling scripts (`--invert`, `--no-fvg` defaults differ between `bias_compare.py` and `bt_curve.py`) | `bias_compare.py:162–169`, `bt_curve.py:46–49` |

### 1.3 Strategy correctness
| # | Gap | Where |
|---|---|---|
| S1 | `round(price, 2)` hard-coded — breaks for low-priced assets (XRP/PEPE) | `analyzer.py:192–204`, `ict/poi.py:14`, `ict/order_block.py:75–79` |
| S2 | MSS rule is degenerate: `last_high > prev_high`, not a real break of a protected swing | `ict/mss.py:13–21` |
| S3 | POI `min_max` engine never marks a POI as mitigated — same level returned forever | `ict/poi.py:12–15` |
| S4 | Order-block engine doesn't track mitigation either | `ict/order_block.py:63–80` |
| S5 | No FVG fill tracking — only "is there a fresh 3-candle imbalance right now?" | `ict/fvg.py:13–21` |
| S6 | Delta is a candle-color × volume proxy, not real CVD with aggressor flags | `ict/delta.py:11–14` |
| S7 | Killzones are decorative — `sessions.get_sessions()["allow_trade"] = True` always | `core/sessions.py:58` |
| S8 | Trail-to-BE exists only in backtest, not in scanner/journal — live vs backtest will diverge | `backtest.py:121–133` vs `analyzer.py` |
| S9 | No regime filter (trend vs range vs high-vol) — fixed params for all conditions | (missing) |
| S10 | "Confidence +20 always" hardcodes 24h crypto allowance into the score | README §"Confidence score" |

### 1.4 Tests / quality
| # | Gap |
|---|---|
| T1 | No integration test for `analyze_pair` against a mocked `get_data` |
| T2 | No tests for `fetch_history` pagination |
| T3 | No property-based tests (`hypothesis`) for indicator pure functions |
| T4 | No smoke test for `app.py` (Streamlit) |
| T5 | No load test for scanner loop |

---

## 2. Target project structure

```
ictbot/                                  # repo root (rename Rahul_ideation → ictbot)
├── README.md                            # short: what / setup / run only
├── LICENSE
├── pyproject.toml                       # project meta + deps + entry points
├── Makefile                             # thin wrappers around the unified CLI
├── Dockerfile
├── docker-compose.yml                   # scanner + dashboard + (optional) redis
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml              # ruff + ruff-format + mypy
│
├── docs/
│   ├── archive/architecture_ictbot_upstream.md  # upstream codebase map (archived)
│   ├── strategy_spec.md                 # ICT checklist as a formal contract
│   ├── findings.md                      # empirical findings (extracted from README)
│   ├── operations.md                    # how to run + monitor + roll back
│   └── adr/                             # architecture decision records
│       ├── 0001-fade-vs-follow.md
│       ├── 0002-poi-engines.md
│       ├── 0003-data-cache.md
│       └── ...
│
├── src/
│   └── ictbot/
│       ├── __init__.py
│       ├── settings.py                  # pydantic-settings (was config.py)
│       │
│       ├── data/                        # data layer
│       │   ├── exchange.py              # Exchange protocol + factory
│       │   ├── bybit.py                 # ccxt.bybit impl
│       │   ├── binance.py               # placeholder for future
│       │   ├── cache.py                 # parquet OHLCV cache
│       │   └── replay.py                # offline replay from cache
│       │
│       ├── indicators/                  # leaf primitives (was ict/)
│       │   ├── atr.py
│       │   ├── bias_sma.py · bias_swing.py · bias_slope.py
│       │   ├── poi_min_max.py · poi_order_block.py
│       │   ├── mss.py · fvg.py · delta.py
│       │   ├── structure.py · risk.py
│       │   └── mitigation.py            # NEW: shared mitigation tracking
│       │
│       ├── strategy/                    # composition of indicators
│       │   ├── base.py                  # Strategy ABC: evaluate(frames) → Signal
│       │   ├── ict_pro_max.py           # current strategy, parameterised
│       │   └── signal.py                # Signal dataclass (entry/sl/tp/rr/conf/diag)
│       │
│       ├── engine/                      # offline analysis tools
│       │   ├── backtest.py              # walk-forward replayer
│       │   ├── sweep.py
│       │   ├── wfo.py
│       │   ├── compare.py               # bias-engine comparison
│       │   ├── sizing.py                # fixed / Kelly
│       │   ├── risk_of_ruin.py
│       │   └── friction.py              # fee + slip math
│       │
│       ├── portfolio/                   # NEW — equity / caps / journal
│       │   ├── account.py
│       │   ├── caps.py                  # daily loss cap, max open pos, max DD
│       │   └── journal.py               # was core/journal.py
│       │
│       ├── exec/                        # NEW — order routing
│       │   ├── broker.py                # Broker protocol
│       │   ├── paper.py                 # paper broker (simulated fills)
│       │   ├── bybit_live.py            # real (gated by ENABLE_LIVE_TRADING)
│       │   └── orders.py                # order types + state machine
│       │
│       ├── notify/
│       │   ├── telegram.py
│       │   └── format.py                # signal → message
│       │
│       ├── runtime/                     # cross-cutting infra
│       │   ├── logger.py                # structured JSON logs
│       │   ├── metrics.py               # Prometheus counters / histograms
│       │   ├── sessions.py
│       │   └── signal_memory.py
│       │
│       ├── orchestrator/                # composition root
│       │   ├── analyzer.py              # orchestrates Strategy + Notify + Journal
│       │   └── scanner.py               # async loop over PAIRS
│       │
│       ├── cli/                         # unified entry point
│       │   ├── __main__.py              # `python -m ictbot <cmd>`
│       │   ├── backtest_cmd.py · sweep_cmd.py · wfo_cmd.py
│       │   ├── compare_cmd.py · size_cmd.py · bt_curve_cmd.py
│       │   ├── journal_cmd.py · scan_cmd.py
│       │   └── ui_cmd.py                # streamlit launcher
│       │
│       └── ui/                          # Streamlit dashboard, broken into parts
│           ├── app.py
│           ├── theme.py
│           └── components/
│               ├── flow_cards.py · chart.py · equity_curve.py · diagnostics.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── indicators/                  # 1 file per leaf
│   │   ├── strategy/
│   │   ├── engine/
│   │   └── portfolio/
│   ├── integration/
│   │   ├── test_analyzer_e2e.py         # mocked ccxt → full pipeline
│   │   └── test_scanner.py
│   └── property/                        # optional, hypothesis-based
│
├── data/                                # gitignored
│   ├── cache/                           # parquet OHLCV by (exchange, symbol, tf)
│   ├── journal/                         # signals.json, equity, etc.
│   ├── runs/                            # backtest report dumps
│   └── logs/                            # scanner.log, structured JSON
│
├── scripts/                             # one-off, hand-run
│   └── bootstrap_journal.py
│
└── .github/
    └── workflows/
        ├── tests.yml
        └── lint.yml
```

---

## 3. Phased migration roadmap — all 11 phases ✅ complete (2026-05-27)

Test count grew from 109 → **167** across the migration; suite stays
green at every phase boundary. Live trading remains off (gap C2/C3 is
*scaffolded*, not enabled — `BybitLiveBroker.place_order` still raises
`NotImplementedError`).

| Phase | What landed | Tests |
|------:|-------------|------:|
| 0  | data/ skeleton, README split, secrets hygiene, pycache sweep              | 118 |
| 1  | src/ictbot/ package + pyproject.toml + pip install -e                     | 118 |
| 2  | Unified `python -m ictbot <cmd>` CLI, harmonised --invert/--no-fvg flags  | 118 |
| 3  | pydantic-settings + ENABLE_LIVE_TRADING kill switch                       | 118 |
| 4  | Strategy as a class — kills bias_compare._set_engine global mutation       | 118 |
| 5  | Exchange protocol, BybitExchange, parquet cache, ReplayExchange            | 124 |
| 6  | tick-size rounding, real-MSS (swing mode), mitigation tracking            | 137 |
| 7  | killzone gate + ATR-percentile regime filter                              | 142 |
| 8  | Order/Broker/PaperBroker + gated BybitLiveBroker + portfolio caps         | 155 |
| 9  | JSON structured logger + Prometheus metrics catalogue (no-op fallback)    | 158 |
| 10 | pre-commit (ruff/format/detect-secrets), GH Actions tests+lint, Dockerfile + compose | 158 |
| 11 | analyzer e2e + Bybit pagination + hypothesis property tests + app smoke   | **167** |

Each phase below stays for reference. The original "1 phase = 1 PR"
intent maps to one commit per row in the table above.

### Phase 0 — Hygiene (1 sitting, no behaviour change)
- Rotate the Telegram bot token (revoke the one in `.env`, issue a new
  one, store in a password manager not in the repo).
- Add `.env` to `.gitignore`'s top (already there — verify) and add a
  pre-commit `detect-secrets` hook.
- Move runtime artefacts under `data/`:
  `signals.json` → `data/journal/signals.json`,
  `last_signal.json` → `data/journal/last_signal.json`,
  `backtest_curve.json` → `data/runs/backtest_curve.json`,
  `scanner.log` → `data/logs/scanner.log`.
  Update `config.py` paths.
- Delete all `__pycache__/` directories from the working tree;
  ensure `.gitignore` already excludes them (it does).
- Split `README.md` into `README.md` (setup + run only, ≤80 lines) and
  `docs/findings.md` (the empirical journal currently inlined).

### Phase 1 — Package skeleton (no logic change)
- Add `pyproject.toml` with build-system, deps, `[project.scripts]`,
  `[tool.ruff]`, `[tool.mypy]`.
- Create `src/ictbot/` and move every existing module under it:
  - `config.py` → `src/ictbot/settings.py` (keep as plain constants
    for now; pydantic-settings comes in Phase 3).
  - `core/exchange.py` → `src/ictbot/data/bybit.py`.
  - `core/journal.py` → `src/ictbot/portfolio/journal.py`.
  - `core/sessions.py` → `src/ictbot/runtime/sessions.py`.
  - `core/signal_memory.py` → `src/ictbot/runtime/signal_memory.py`.
  - `core/telegram.py` → `src/ictbot/notify/telegram.py`.
  - `core/logger.py` → `src/ictbot/runtime/logger.py`.
  - `ict/*` → `src/ictbot/indicators/*`.
  - `analyzer.py` → `src/ictbot/orchestrator/analyzer.py`.
  - `scanner.py` → `src/ictbot/orchestrator/scanner.py`.
  - `backtest.py · sweep.py · wfo.py · bias_compare.py · bt_curve.py`
    → `src/ictbot/engine/*.py`.
  - `size.py` → `src/ictbot/engine/sizing.py`.
  - `app.py` → `src/ictbot/ui/app.py`.
  - `journal.py` → `src/ictbot/cli/journal_cmd.py`.
- Add `tests/__init__.py`, fix imports, delete the `sys.path.insert`
  hack in `conftest.py`.
- Run `pip install -e .[dev]`, ensure all 109 tests still pass.

### Phase 2 — Unified CLI
- Add `src/ictbot/cli/__main__.py` dispatcher so the user runs:
  `python -m ictbot backtest BTC/USDT:USDT --bars 5000` instead of
  `python backtest.py BTC/USDT:USDT --bars 5000`.
- Normalise flag names across sub-commands: `--invert` / `--no-fvg` /
  `--bars` have the same default and meaning everywhere. (Currently
  `bt_curve.py` defaults `invert=True` while `backtest.py` defaults
  `invert=False`.)
- Rewrite `Makefile` to wrap the new CLI (one-line targets).

### Phase 3 — Settings + secrets
- Replace ad-hoc constants in `settings.py` with pydantic-settings:
  - `TelegramSettings`, `ExchangeSettings`, `StrategySettings`,
    `RiskSettings`, `BacktestSettings` — each a `BaseSettings` with
    env prefix.
  - All paths derived from a single `DATA_DIR` (default `./data`).
- Add `ENABLE_LIVE_TRADING: bool = False` as the master kill switch.

### Phase 4 — Strategy as a first-class object
- Define `Strategy(ABC)` in `strategy/base.py` with
  `evaluate(frames: Frames) → Signal`.
- Lift the current logic from `analyzer.evaluate_frames` into
  `ICTProMaxStrategy` taking `bias_engine`, `poi_engine`, `require_fvg`,
  `sl_frac`, `tp_frac`, `sl_atr_mult`, `tp_atr_mult`, `invert` as
  constructor args.
- Delete the `BIAS_ENGINE` / `POI_ENGINE` module-global mutation in
  `bias_compare.py`; comparison runs construct different `Strategy`
  instances instead.
- Fixes A3 and removes the `_set_engine` hack.

### Phase 5 — Data layer
- Define `Exchange` protocol in `data/exchange.py`:
  `fetch_ohlcv(symbol, tf, limit) → DataFrame`.
- Move ccxt.bybit impl into `data/bybit.py`.
- Add `data/cache.py` writing/reading parquet:
  `data/cache/{exchange}/{symbol}/{tf}.parquet`. Cache is append-only
  and idempotent on `time`.
- Add `data/replay.py` so backtests can run offline from the cache.
- Fixes A4, A5.

### Phase 6 — Correctness fixes in indicators
- Tick-size aware rounding: replace `round(price, 2)` with
  `round_to_tick(price, market.precision.price)` in `analyzer`, `poi`,
  `order_block`. Fixes S1 (and the XRP loss documented in README).
- Real MSS: replace `last_high > prev_high` with "broke the most recent
  protected swing high (low for bearish)" using `indicators.structure`.
  Fixes S2.
- Mitigation tracking for POI / OB / FVG: add `indicators/mitigation.py`
  that returns `(level, mitigated_at_index)`. Tapped levels are retired
  for `N` bars. Fixes S3, S4, S5.
- Optional: real CVD via ccxt `fetch_trades` (best-effort; falls back to
  the current proxy if trades aren't available). Fixes S6.

### Phase 7 — Killzone gate + regime filter
- `runtime.sessions` exposes `is_killzone_active()`; strategy honours it
  (configurable). Fixes S7.
- Add a simple regime filter (ATR percentile or ADX) — different param
  sets for trend vs range. Fixes S9.

### Phase 8 — Portfolio + execution scaffolding
- `portfolio/caps.py`: `MaxOpenPositions`, `DailyLossLimit`, `MaxDD`.
- `portfolio/account.py`: in-memory equity, hooked into journal close
  events.
- `exec/broker.py`: protocol with `place_order`, `cancel`, `positions`.
- `exec/paper.py`: simulated fills using the next bar's open.
- `exec/bybit_live.py`: real, gated by `settings.ENABLE_LIVE_TRADING`
  AND a per-pair allow-list AND a confirmation prompt on first run.
- Scanner emits a `Signal`; orchestrator routes through `Broker`
  (paper by default). Fixes C2, C3.

### Phase 9 — Observability
- `runtime/logger.py`: structured JSON logger with `pair`, `signal_id`,
  `strategy_version` keys.
- `runtime/metrics.py`: Prometheus counters
  (`signals_fired_total{pair,direction}`, `evaluations_total`,
  `latency_ms`), exposed at `/metrics` from the scanner.
- Compose stack: scanner + dashboard + (optional) Prometheus + Grafana.

### Phase 10 — Dev experience
- `.pre-commit-config.yaml`: ruff, ruff-format, mypy, detect-secrets.
- `.github/workflows/tests.yml`: pytest matrix on push/PR.
- `.github/workflows/lint.yml`: ruff + mypy.
- `Dockerfile` (python:3.12-slim) + `docker-compose.yml` (scanner +
  dashboard services).

### Phase 11 — Tests
- Integration test: `test_analyzer_e2e.py` mocks `Exchange.fetch_ohlcv`
  with golden fixtures and asserts the full pipeline returns a stable
  `Signal`. Fixes T1.
- Pagination test for `fetch_history`. Fixes T2.
- Property tests for indicator pure functions using `hypothesis`. Fixes
  T3.
- Smoke test for `app.py` import + render. Fixes T4.

---

## 4. Non-goals (explicit)

- **Adding more indicators.** The current set is enough; correctness
  beats breadth.
- **A web UI beyond Streamlit.** Streamlit stays.
- **Multi-account / multi-user.** Single-user, single-account.
- **Backtester that simulates partial fills, queue position, or maker
  rebates.** Out of scope until P&L matters live.

---

## 4.5 Bugs discovered post-merge (2026-05-27)

Two correctness bugs + one verdict-logic bug + a performance
bottleneck surfaced when re-running the WFO A/B experiment after
Phase 11. All four now fixed with regression tests.

| # | Issue | Phase that introduced it | Symptom | Fix |
|---|-------|--------------------------|---------|-----|
| B1 | Phase 3 surfaced legacy `.env` keys | 3 | `HTF_TIMEFRAME=15m` overrode the `"4h"` default → strategy ran with HTF == LTF, collapsing the multi-TF setup | Strip legacy keys from `.env`. See `docs/findings.md` §9. |
| B2 | `_bars_needed` used floor division | 1 (carried over) | 5000 / 240 = 20.83 floored to 20 → 93 % INSUFFICIENT_DATA across the replay | Ceiling division + `+1` buffer. Regression in `tests/test_bars_needed.py`. See `docs/findings.md` §10. |
| B3 | `wfo` verdict only checked TEST > 0 | 1 | BTC labelled "✅ holds" at TRAIN = −0.27R when TEST flipped positive — noise, not an edge | Extracted `classify()` helper requiring TRAIN > 0. 8 regression tests in `tests/test_wfo_verdict.py`. See `docs/findings.md` §12. |
| P1 | `get_atr` was O(n) per call | 1 (carried over) | 67 % of `run_backtest` runtime in `get_atr` at 50 000-bar sweeps. A full 50k follow-mode WFO extrapolated to **~2.5 hours**. | Slice `df.tail(period + 1)` *before* computing TR. Identical numerical output (locked by `tests/test_atr.py::test_optimised_atr_equals_slow_atr_*`). Engine ≈ **6× faster** on 50k sweeps. |

Two smaller engine optimisations also landed alongside P1:

- **`np.searchsorted`** for the per-bar HTF/15m/3m slice (replacing
  the O(n) boolean mask `df[df["time"] <= T]`). Equivalence locked by
  `tests/test_backtest_searchsorted.py`.
- **Delta prefix-sum**: `get_delta` over the growing entry-window was
  O(n) per bar = O(n²) over the sweep. `run_backtest` now pre-computes
  the cumulative signed-volume series once and monkey-patches
  `ictbot.strategy.ict_pro_max.get_delta` (`unittest.mock.patch`)
  for the run's duration so the strategy gets an O(1) lookup. Restored
  before `return` so callers outside the backtest are unaffected.

Lesson for future phases: any change that promotes "ignored" config
into "honoured" config (B1) is a behavioural change disguised as a
refactor. Run the full validation matrix (backtest + WFO +
bias_compare) on a known-good pair before merging. The unit suite
missed all three correctness bugs because they only manifest against
live data + multi-pair grids.

---

## 5. Open questions (decide before Phase 8)

1. Paper-trade for how long before flipping `ENABLE_LIVE_TRADING`? (1
   month of live paper trades agreeing with backtest within ±0.2R/trade
   is a reasonable bar.)
2. Which pair(s) go live first? Today only SOL passes WFO; default to
   SOL-only when live trading is enabled.
3. Daily loss cap — 2R or 3R? (Recommend 2R for the first month.)
4. Do we want a Discord notifier alongside Telegram, or stay on
   Telegram only? Affects the shape of `notify/`.

---

## 6. How to use this plan

- One phase per PR. Don't bundle.
- Each phase opens with a one-line "Goal:" and ends with the test suite
  green.
- Update this file when a phase merges — mark it ✅ and link the PR.
- New gaps discovered mid-flight go into `§1` *with the phase that
  should pick them up*, not silently bolted onto the next PR.
