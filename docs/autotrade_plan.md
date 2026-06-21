# Live Autotrade from Telegram Signals — 4-Phase Plan

> Approved implementation plan for turning the existing Telegram BUY/SELL
> signal stream into real exchange execution. Each phase ships behind an
> off-by-default env flag with an explicit rollback.

## Context

The bot already pushes BUY/SELL alerts to Telegram and has a complete
paper-trading pipeline (Strategy → analyze_pair → SignalRouter →
PaperBroker → CapGate → Account → journal). The execution layer is also
already built: `DeltaLiveBroker` and `BybitLiveBroker` each implement a
3-leg bracket (market entry + reduce-only stop + reduce-only TP),
emergency flatten on partial failure, `_on_close` callback wiring,
position reconciliation, and a `LiveTradingDisabled` gate.

**What's missing** to turn TG signals into real fills:

1. Nothing currently validates the live broker against a real exchange
   — every existing test mocks ccxt.
2. There's no measurement of live-vs-paper slippage before flipping
   real capital in.
3. There's no human-in-the-loop confirmation channel — no
   `python-telegram-bot` callback handler, no inline buttons.
4. There's no tiered autonomy: today it's all-or-nothing on
   `ENABLE_LIVE_TRADING`.

This plan rolls out live execution in four phases, each with its own
rollback flag. The user-selected configuration is:

- **Exchanges:** Bybit testnet (Phase A) → Bybit mainnet shadow (Phase
  B) → Delta mainnet smoke (after Phase B with rotated keys).
- **Scope:** All four phases A→D.
- **Risk per live trade:** 0.05% of equity (`RISK_PCT_LIVE=0.0005`).

The point of view: minimal new code, maximum reuse of the existing
broker / router / caps surface, every new behaviour off-by-default so
the working scanner is untouched until each phase is flipped on.

---

## Phase A — Bybit testnet validation (zero risk)

**Goal.** Place real 3-leg bracket orders on Bybit testnet from the
existing scanner. Validate the live broker's place / reconcile / close
/ emergency-flatten paths against a real venue before any mainnet
capital is touched.

### Files to modify

- [src/ictbot/settings.py](../src/ictbot/settings.py) — add
  `bybit_testnet: bool = Field(default=False, alias="BYBIT_TESTNET")`
  and re-export at the bottom alongside `EXCHANGE`,
  `ENABLE_LIVE_TRADING`.
- [src/ictbot/exec/factory.py:40-43](../src/ictbot/exec/factory.py#L40-L43)
  — thread `testnet=settings.bybit_testnet` into the
  `BybitLiveBroker(...)` call. `BybitLiveBroker.__init__` already
  accepts this kwarg.
- [scripts/smoke_live.sh](../scripts/smoke_live.sh) (new, ~15 lines) —
  one-line invocation of `python -m ictbot.orchestrator.scanner` with
  `PAIRS=BTC/USDT:USDT`, `EXCHANGE=bybit`, `BYBIT_TESTNET=true`,
  `ENABLE_LIVE_TRADING=true`, `RISK_PCT=0.0005`. Echoes the ccxt
  testnet order-history URL on success.

### Reused utilities

- `build_live_broker` at
  [src/ictbot/exec/factory.py:25](../src/ictbot/exec/factory.py#L25) —
  already venue-aware via `settings.exchange`.
- `BybitLiveBroker.on_reconnect()` and the
  `_zero_position_streak` debouncer already handle the
  `fetch_positions` transient-empty problem on restart.
- `_settle_broker_on_last_closed_bar` in
  [src/ictbot/orchestrator/scanner.py:220](../src/ictbot/orchestrator/scanner.py#L220)
  — the broker's `_on_close` callback already feeds DailyLossLimit +
  Account through `SignalRouter.on_close`
  ([src/ictbot/orchestrator/router.py:159](../src/ictbot/orchestrator/router.py#L159)).
- Kill switch at
  [src/ictbot/runtime/kill_switch.py](../src/ictbot/runtime/kill_switch.py)
  — `_build_router()` at
  [src/ictbot/orchestrator/scanner.py:161](../src/ictbot/orchestrator/scanner.py#L161)
  already short-circuits to `PaperBroker` if engaged.

### Env vars (new in bold)

| Var | Default | Phase-A value |
|---|---|---|
| **`BYBIT_TESTNET`** | **`false`** | `true` |
| `EXCHANGE` | `delta` | `bybit` |
| `ENABLE_LIVE_TRADING` | `false` | `true` |
| `BYBIT_API_KEY`, `BYBIT_API_SECRET` | (none) | testnet keys |
| `PAIRS` | (the 5) | `BTC/USDT:USDT` (single pair) |
| `RISK_PCT` | `0.005` | `0.0005` (0.05%) |

### Verification

1. Get fresh Bybit testnet keys at
   <https://testnet.bybit.com/app/user/api-management>.
2. Run `bash scripts/smoke_live.sh`. Expect log line `router using
   broker=bybit-live cap_gate=3 caps`.
3. Wait for a BUY/SELL. Expect 3 sequential ccxt `create_order` calls
   (market entry → stop_market SL → limit TP), all with
   `category=linear`. Order IDs visible in Bybit testnet UI.
4. Inspect `data/journal/signals.json` for one OPEN row; verify
   `signals_fired_total{pair,direction}` increments on `/metrics`.
5. **Force a close:** edit the SL leg in the testnet UI to the current
   mark to trigger the stop. Within one 1m bar, expect an
   `order_closed` JSON log and the DailyLossLimit counter advancing.
6. **Emergency-flatten check:** mid-test, set
   `BYBIT_API_SECRET=garbage` and restart with a queued signal —
   verify `_emergency_flatten` log + re-raise + zero residual position
   on testnet UI.

**Success criteria.** Bracket placed within 5 s of signal print; SL +
TP both visible on exchange; `_on_close` fires within one bar of stop
trigger; emergency-flatten leaves no orphan position.

**Rollback.** Set `ENABLE_LIVE_TRADING=false` **or** `touch
data/KILL_SWITCH_ENGAGED` — broker falls back to PaperBroker on next
`_build_router()` boot.

---

## Phase B — Mainnet shadow (parallel paper + live)

**Goal.** Run live broker **and** paper broker in parallel against
mainnet data for 7 days at 0.05% risk. Compare fill prices, slippage,
and realised R per pair per day. Validates "the strategy still has an
edge after real friction" before scaling risk.

### Files to add / modify

- [src/ictbot/orchestrator/shadow_router.py](../src/ictbot/orchestrator/shadow_router.py)
  (new, ~80 lines) — `class ShadowRouter` composing two
  `SignalRouter` instances:
    - `live_router` (real broker, real Account, real `RISK_PCT_LIVE`)
    - `shadow_router` (PaperBroker, **separate** Account, normal
      `RISK_PCT`)
    - Public surface: `route(result) -> RouteOutcome` returns the live
      outcome and runs shadow as a side effect, swallowing shadow
      exceptions so the live path is never destabilised.
    - **Separate Account + CapGate per leg** so
      `MaxOpenPositions(1)` on the live side doesn't artificially gate
      the shadow side.
- [src/ictbot/orchestrator/scanner.py:153](../src/ictbot/orchestrator/scanner.py#L153)
  — modify `_build_router()` only: when `settings.shadow_mode` is
  true, wrap the live router in `ShadowRouter`. `_route_signal` at
  [scanner.py:326](../src/ictbot/orchestrator/scanner.py#L326) is
  unchanged because the wrapper preserves the `route()` shape.
- [src/ictbot/runtime/metrics.py](../src/ictbot/runtime/metrics.py) —
  add three counters following the existing `_Counter` / `_Histogram`
  pattern:
    - `ictbot_shadow_fill_slippage_bps{pair,side}` (Histogram)
    - `ictbot_shadow_r_delta{pair}` (Histogram, paper_R − live_R)
    - `ictbot_shadow_diverged_total{pair,reason}` (Counter; reasons:
      `live_rejected` / `shadow_rejected` / `qty_mismatch`)
- [src/ictbot/settings.py](../src/ictbot/settings.py) — add
  `shadow_mode: bool = Field(default=False, alias="SHADOW_MODE")` and
  `risk_pct_live: float = Field(default=0.0005,
  alias="RISK_PCT_LIVE")`.
- [src/ictbot/cli/shadow_report.py](../src/ictbot/cli/shadow_report.py)
  (new, ~50 lines) — reads `data/journal/signals.json` filtered by
  `broker=live` vs `broker=shadow`, prints per-pair |paper_R − live_R|
  and median slippage; flag `--telegram` pipes the table through
  `send_telegram`.
- [tests/test_shadow_router.py](../tests/test_shadow_router.py) (new) —
  asserts: (a) both brokers see the same result dict; (b) a shadow
  exception does not break the live path; (c) divergence counter
  increments when caps reject one side.

### Reused utilities

- `SignalRouter.route()` at
  [router.py:187](../src/ictbot/orchestrator/router.py#L187) — used
  unchanged by both legs.
- `PaperBroker.on_bar` for the shadow leg — already tested.
- `Account.book_close` for live; the shadow Account is a separate
  instance.
- Existing `_Counter` / `_Histogram` wrappers in
  [runtime/metrics.py](../src/ictbot/runtime/metrics.py).

### Env vars (new in bold)

| Var | Default | Phase-B value |
|---|---|---|
| **`SHADOW_MODE`** | **`false`** | `true` |
| **`RISK_PCT_LIVE`** | **`0.0005`** (0.05%) | `0.0005` |
| `RISK_PCT` | `0.005` | `0.005` (shadow leg only) |
| `EXCHANGE` | `delta` | `bybit` |
| `BYBIT_TESTNET` | `false` | `false` |
| `PAIRS` | (the 5) | `BTC/USDT:USDT, ETH/USDT:USDT` |

### Verification

1. Deploy to Render with the Phase-B env block above and real Bybit
   mainnet keys.
2. Grafana panel: `histogram_quantile(0.5,
   ictbot_shadow_fill_slippage_bps)` over 7 days.
3. Every evening: `python -m ictbot.cli.shadow_report --telegram`
   pushes the per-pair table to the ops chat ID.

**Success criteria.** Median fill slippage < 5 bps; |paper_R −
live_R| < 0.1 R over 20+ paired closes; zero "shadow exception killed
live path" log lines for 7 days.

**Delta repeat.** After Bybit shadow passes, rotate the Delta keys
(per DEPLOY.md gotcha #5), set `EXCHANGE=delta` and re-run Phase B for
3 days on Delta. Same success criteria. Phase A is skipped for Delta
because there is no Delta testnet — Phase B at 0.05% risk is the
smallest validation possible.

**Rollback.** `SHADOW_MODE=false` — `_build_router()` returns the bare
`SignalRouter` again.

---

## Phase C — TG inline-button confirm-then-fire

**Goal.** Default-off mode: each BUY/SELL is DM'd to the operator
with `[OK Trade NOW]` / `[X Skip]` inline buttons. The trade executes
only on click within `TG_CONFIRM_TIMEOUT_S`. Existing fan-out channels
(public group, etc.) still receive the unbuttoned alert; only the
operator DM gets the button row.

### Library choice

Add `python-telegram-bot>=21.0` (PTB v21, asyncio). The existing
`notify/telegram.py` raw-`requests` fan-out stays untouched; PTB is
only used for the callback-query channel. Long-poll (not webhook) so
Render free tier needs no TLS endpoint.

### Files to add / modify

- [pyproject.toml](../pyproject.toml) — add
  `"python-telegram-bot>=21.0"` to `[project.dependencies]`.
- [src/ictbot/notify/tg_confirm.py](../src/ictbot/notify/tg_confirm.py)
  (new, ~150 lines):
    - `class PendingSignal` — dataclass `{signal_id, result_dict,
      expires_at, status}`.
    - `class TGConfirmService` — wraps
      `telegram.ext.Application.builder().token(TELEGRAM_TOKEN).build()`.
      Started on a daemon thread from `scanner.main`.
    - `send_signal_with_buttons(result, on_confirm, timeout_s)` —
      reuses the existing TG card format
      ([notify/signal_check.py:209](../src/ictbot/notify/signal_check.py#L209))
      for the body; appends
      `InlineKeyboardMarkup([[Trade, Skip]])` with
      `callback_data="cfm:<signal_id>"` and `"skp:<signal_id>"`.
      Stores `PendingSignal` keyed by `signal_id`.
    - `_on_callback(update, ctx)` — guards
      `from_user.id == settings.tg_operator_user_id`; looks up
      `signal_id`; on `cfm`+not-expired calls
      `on_confirm(stored.result)`; edits the message to "EXECUTED" /
      "SKIPPED" / "EXPIRED".
    - Cross-thread bridge: a `queue.Queue` so `router.route()` runs on
      the scanner thread, not the PTB thread (avoids ccxt re-entry).
- `signal_id` format: `f"{pair}|{closed_bar_iso}|{side}"` (fits TG's
  64-byte `callback_data` budget; unit-test asserts
  `len(callback_data.encode()) <= 64` for every default pair).
  Reuses
  [src/ictbot/runtime/signal_memory.py](../src/ictbot/runtime/signal_memory.py)
  dedup keys so a refire of the same bar collapses to one card.
- [src/ictbot/orchestrator/scanner.py:326](../src/ictbot/orchestrator/scanner.py#L326)
  — `_route_signal`: branch on `settings.tg_confirm_mode`. When ON,
  call
  `tg_confirm.send_signal_with_buttons(r, on_confirm=lambda r2:
  router.route(r2), timeout_s=settings.tg_confirm_timeout_s)`
  instead of `router.route(r)` directly. When OFF (default),
  behaviour is unchanged.
- [src/ictbot/settings.py](../src/ictbot/settings.py) — add:
    - `tg_confirm_mode: bool = Field(default=False,
      alias="TG_CONFIRM_MODE")`
    - `tg_confirm_timeout_s: int = Field(default=180,
      alias="TG_CONFIRM_TIMEOUT_S")`
    - `tg_operator_user_id: int = Field(default=0,
      alias="TG_OPERATOR_USER_ID")` — refuse to start if
      `tg_confirm_mode and not tg_operator_user_id`.
- [tests/test_tg_confirm.py](../tests/test_tg_confirm.py) (new) — mocks
  PTB `CallbackQuery`, asserts: (a) confirm within timeout →
  `on_confirm` called once with stored dict; (b) timeout →
  `on_confirm` never called + `status=EXPIRED`; (c) skip →
  `on_confirm` never called; (d) wrong user_id → silent reject +
  `cap_rejections_total{cap=tg_unauthorized}` increment; (e) duplicate
  `signal_id` within window collapses to one pending row.

### Env vars (new in bold)

| Var | Default | Phase-C value |
|---|---|---|
| **`TG_CONFIRM_MODE`** | **`false`** | `true` |
| **`TG_CONFIRM_TIMEOUT_S`** | **`180`** | `180` |
| **`TG_OPERATOR_USER_ID`** | **`0`** | your numeric Telegram user id |

### Verification

`pytest tests/test_tg_confirm.py -v`; then in staging set the Phase-C
env block, manually click `Trade` on 3 live signals, click `Skip` on
3, let 3 expire. All 9 outcomes must match `data/journal/signals.json`
rows: 3 OPEN, 3 REJECTED (`reason=user_skipped`), 3 REJECTED
(`reason=confirm_timeout`).

**Rollback.** `TG_CONFIRM_MODE=false` — `_route_signal` reverts to
direct `router.route` invocation. Pending in-memory rows simply
expire.

---

## Phase D — Tiered autonomy + silent-failure detection

**Goal.** Auto-execute high-confidence signals; require Phase-C
confirm for anything below threshold. Add Prometheus alert for "live
trading silently stopped".

### Files to add / modify

- [src/ictbot/portfolio/caps.py](../src/ictbot/portfolio/caps.py) —
  append three caps following the `MaxOpenPositions` pattern at
  [caps.py:31](../src/ictbot/portfolio/caps.py#L31):
    - `MaxLiveTradesPerDay(limit)` — date-stamped counter, `record(when)`
      on every `placed=True`, `check()` rejects when ≥ limit.
    - `MinConfidenceCap(threshold)` — `check(*, result, **_)` reads
      `result["confidence"]`. **Requires extending**
      `CapGate.evaluate` at
      [caps.py:97](../src/ictbot/portfolio/caps.py#L97) to forward
      `**ctx`; pass `result=result` from
      [router.py:197](../src/ictbot/orchestrator/router.py#L197).
    - `NewsBlackoutCap(window_min)` — re-runs the same news lookup
      `analyze_pair` uses (`runtime.news.next_event_eta`), as
      defence-in-depth between signal print and order send.
- [src/ictbot/orchestrator/scanner.py:326](../src/ictbot/orchestrator/scanner.py#L326)
  — `_route_signal`: when `TG_CONFIRM_MODE=on`, branch on
  `result["confidence"] >= settings.auto_execute_min_confidence`. If
  ≥ threshold, route directly; else go through the Phase-C confirm
  path. Wire the three new caps into `_build_router()` at
  [scanner.py:167](../src/ictbot/orchestrator/scanner.py#L167).
- [src/ictbot/runtime/metrics.py](../src/ictbot/runtime/metrics.py) —
  add `live_trades_total{pair,direction}` Counter.
- [infra/prometheus_alerts.yaml](../infra/prometheus_alerts.yaml) (new
  or extend) — alert `LiveTradingSilent`:
  `rate(ictbot_live_trades_total[24h]) == 0 AND
  rate(ictbot_signals_fired_total[24h]) > 0` → TG ops channel via
  Alertmanager.
- [.github/workflows/weekly_shadow_report.yml](../.github/workflows/weekly_shadow_report.yml)
  (new) — Monday 09:00 UTC cron runs `python -m
  ictbot.cli.shadow_report --weekly --telegram`. Closes the loop on
  Phase B.

### Env vars (new in bold)

| Var | Default | Phase-D value |
|---|---|---|
| **`AUTO_EXECUTE_MIN_CONFIDENCE`** | **`100`** | `100` (only full-pass signals auto-fire) |
| **`MAX_LIVE_TRADES_PER_DAY`** | **`3`** | `3` |
| **`MAX_LIVE_RISK_PER_TRADE_PCT`** | **`0.005`** | hard ceiling on `RISK_PCT_LIVE` |
| **`NEWS_BLACKOUT_MINUTES_LIVE`** | **`30`** | `30` |

### Verification

Extended `pytest tests/test_caps.py tests/test_router.py -v`.
Synthetic checks:

- Confidence 99 + threshold 100 → confirm path (Phase C card sent).
- Confidence 100 + threshold 100 → direct execution (no card).
- Three live fills today, 4th must reject with
  `cap_rejections_total{cap=max_live_trades_per_day}` increment.
- 24 h of signals with zero live fills → Prometheus alert fires to
  TG ops.

**Rollback.** Either:

- `AUTO_EXECUTE_MIN_CONFIDENCE=101` — impossible threshold, every
  signal forced through Phase-C confirm; or
- `TG_CONFIRM_MODE=false` — reverts to Phase-B shadow behaviour; or
- `ENABLE_LIVE_TRADING=false` — reverts to paper everywhere.

The kill switch (`touch data/KILL_SWITCH_ENGAGED`) overrides all of
the above.

---

## Risks & open questions

1. **Delta has no testnet.** Phase A is Bybit-only. Delta validation
   happens at Phase-B mainnet shadow with 0.05% risk after rotating
   the invalid keys flagged in DEPLOY.md gotcha #5.
2. **PTB long-poll on Render free tier.** The PTB thread doesn't bind
   a port; the existing health server at
   [scanner.py:386](../src/ictbot/orchestrator/scanner.py#L386) keeps
   Render happy. Confirm Render doesn't kill long-poll TCP after the
   15-min idle window — UptimeRobot already pings `/health` every
   5 min so this should be fine.
3. **`callback_data` 64-byte budget.** The proposed `signal_id`
   format fits for current pairs but long names (e.g.
   `PEPE1000/USDT:USDT`) could overflow. Add a unit test asserting
   `len(callback_data.encode()) <= 64` for every pair in `PAIRS`. If
   it ever fails, switch to a short-hash mapping table.
4. **Bracket atomicity under Bybit REST replication lag.**
   `_emergency_flatten` relies on `fetch_positions` returning the
   just-opened position. Phase A explicitly stresses this by killing
   the SL placement deliberately.
5. **Shared cap state in ShadowRouter.** Per-leg Account + CapGate
   instances are the resolution; encoded in the Phase-B file list
   above.
6. **Single operator only.** `TG_OPERATOR_USER_ID` is scalar. If two
   operators want click rights later, change to a comma-list
   following the existing `TELEGRAM_CHAT_ID` fan-out pattern in
   [notify/telegram.py:33](../src/ictbot/notify/telegram.py#L33).

---

## Critical files for implementation

- [src/ictbot/orchestrator/scanner.py](../src/ictbot/orchestrator/scanner.py)
  — single insertion point for Phase B (`_build_router`) and Phase
  C/D (`_route_signal` branching).
- [src/ictbot/orchestrator/router.py](../src/ictbot/orchestrator/router.py)
  — Phase D extends `CapGate.evaluate` context-passing.
- [src/ictbot/exec/factory.py](../src/ictbot/exec/factory.py) — Phase A
  threads `testnet` flag.
- [src/ictbot/notify/tg_confirm.py](../src/ictbot/notify/tg_confirm.py)
  (new) — Phase C inline-button service.
- [src/ictbot/orchestrator/shadow_router.py](../src/ictbot/orchestrator/shadow_router.py)
  (new) — Phase B paper-vs-live wrapper.
- [src/ictbot/portfolio/caps.py](../src/ictbot/portfolio/caps.py) —
  Phase D adds three caps.
- [src/ictbot/settings.py](../src/ictbot/settings.py) — every phase
  adds env-var fields; defaults preserve current behaviour.

---

## End-to-end verification

After all four phases ship:

```bash
# unit + integration tests
pytest -q tests/test_shadow_router.py tests/test_tg_confirm.py \
         tests/test_caps.py tests/test_router.py \
         tests/test_bybit_live_broker.py

# Phase-A testnet smoke
EXCHANGE=bybit BYBIT_TESTNET=true ENABLE_LIVE_TRADING=true \
  RISK_PCT=0.0005 PAIRS=BTC/USDT:USDT \
  python -m ictbot.orchestrator.scanner

# Phase-B + C + D combined env (after each phase is individually green)
EXCHANGE=bybit BYBIT_TESTNET=false ENABLE_LIVE_TRADING=true \
  SHADOW_MODE=true RISK_PCT_LIVE=0.0005 \
  TG_CONFIRM_MODE=true TG_OPERATOR_USER_ID=<your-id> \
  TG_CONFIRM_TIMEOUT_S=180 \
  AUTO_EXECUTE_MIN_CONFIDENCE=100 MAX_LIVE_TRADES_PER_DAY=3 \
  python -m ictbot.orchestrator.scanner

# Daily shadow report
python -m ictbot.cli.shadow_report --telegram
```

Observable success: TG ops chat receives a `[Trade] / [Skip]` card
per BUY/SELL; click `Trade` produces an order row in Bybit UI within
5 s; `data/journal/signals.json` shows matching OPEN row;
`/metrics` shows `live_trades_total` advancing; weekly shadow report
arrives in TG with median slippage < 5 bps.

---

## Phase summary at a glance

| Phase | Risk | New deps | Key env flag | Rollback |
|---|---|---|---|---|
| A — Bybit testnet | 0 (testnet) | none | `BYBIT_TESTNET=true` + `ENABLE_LIVE_TRADING=true` | `ENABLE_LIVE_TRADING=false` |
| B — Mainnet shadow | 0.05%/trade | none | `SHADOW_MODE=true` | `SHADOW_MODE=false` |
| C — TG confirm-then-fire | depends on B | `python-telegram-bot>=21.0` | `TG_CONFIRM_MODE=true` | `TG_CONFIRM_MODE=false` |
| D — Tiered autonomy | depends on B+C | none | `AUTO_EXECUTE_MIN_CONFIDENCE` | set to `101` |
| **E — Bias-alignment gate + RR validation** | depends on D | none | `REQUIRE_BIAS_ALIGNMENT=true` (default) | set `false` |

Global kill switch (`touch data/KILL_SWITCH_ENGAGED`) overrides every
phase — broker falls back to PaperBroker on next loop boot.

---

## Implementation Status (2026-06-05)

### Shipped vs planned

Both Phase A (Bybit testnet) and Phase B (shadow) shipped per plan. Phase
C (TG confirm) shipped per plan. **Phases D and E diverged on several
points** — the as-shipped reality is documented below.

#### Phase D — what actually shipped

| Plan'd | Shipped | Notes |
|---|---|---|
| `MaxLiveTradesPerDay(limit)` | ✅ | Reads `data/journal/signals.json` (route-agnostic) instead of an in-memory counter — survives restart naturally |
| `MinConfidenceCap(threshold)` | ❌ | Dropped. The same goal is achieved cleaner by the tier branch in `_route_signal` (below); no need to extend `CapGate.evaluate` signature |
| `NewsBlackoutCap(window_min)` | ✅ | Reuses `runtime/news.is_blackout` (the strategy-layer cache), no new fetcher |
| Tier branch in `_route_signal` | ✅ | conf ≥ `AUTO_EXECUTE_MIN_CONFIDENCE` → auto; below + `TG_CONFIRM_MODE=on` → confirm; else drop |
| `live_trades_total` Counter | ✅ | Only `SignalRouter(is_live=True)` increments — paper/shadow stay clean |
| `kill_switch_engaged` Gauge | ✅ added | Surfaced for Prometheus alerting |
| `MAX_LIVE_RISK_PER_TRADE_PCT` boot guard | ✅ | Refuses to boot if `ENABLE_LIVE_TRADING=true` AND `RISK_PCT_LIVE > MAX_LIVE_RISK_PER_TRADE_PCT` (default 0.001) |
| Prometheus alerts | ✅ `infra/prometheus_alerts.yaml` with 5 rules |
| Weekly shadow report CI | ✅ `.github/workflows/weekly_shadow_report.yml`, Mon 00:00 UTC |
| `prometheus_client` dependency | ✅ promoted to hard dep in `pyproject.toml` (no-op shim hid the metric calls until installed) |

**TG operator commands** were added alongside Phase D (not in the
original plan but enabled the same PTB Application):

| Command | Behavior |
|---|---|
| `/whoami` | Echo `operator_id` vs caller id |
| `/status` | Current per-pair card pack (reuses `signal_check.build_message`) |
| `/journal [n]` | Last n closes (default 10, max 50) |
| `/kill <reason>` | Engages `kill_switch` |
| `/resume yes` | Strict — clears kill switch + pause, does **not** flip `ENABLE_LIVE_TRADING` |
| `/pause <min>` | New `runtime/pause.py` — file-based, auto-expires |
| `/help` | Lists the above |

Activation: `TG_COMMANDS_MODE=true`, independent of `TG_CONFIRM_MODE`.
Single PTB Application registers both handler types.

#### Phase E — added during validation (not in original plan)

The first live run revealed the strategy was firing 21/21 closed SELL
signals with a 5.6% win rate. Root cause: `ltf_bias` was computed but
never gated on; `htf_bias` alone fired entries even when 15m momentum
opposed the macro direction. Phase E ships a single high-leverage gate:

- `REQUIRE_BIAS_ALIGNMENT: bool = True` (default ON, env override
  `REQUIRE_BIAS_ALIGNMENT=false` reverts behaviour).
- Entry gate at [`ict_pro_max.py:_evaluate`](../src/ictbot/strategy/ict_pro_max.py)
  extended with `bias_aligned = (not require_bias_alignment) or (htf_bias == ltf_bias)`.
- `_diagnose()` emits a `"Bias mismatch: HTF=X vs LTF=Y"` blocker so the
  funnel counter surfaces the drop-off.
- `scanner._STEP_ORDER` adds `bias_align` between `htf_bias` and `poi_tap`.

#### Strategy edge validation (WFO 2026-06-05)

Ran walk-forward optimization on BTC, 10k bars, `--quick` grid, slope
engine, bias-alignment gate ON. Compared follow vs `--invert` (fade):

```
FOLLOW: winner sl=0.005 tp=0.025 (1:5 RR) — TRAIN 66.7% / TEST 38.9% WR, +1.05R/trade ✅
FADE  : winner sl=0.005 tp=0.015 — TRAIN  7.7% / TEST 12.8% WR, -0.77R/trade ❌
```

The strategy is correctly oriented as **follow**; the saved
`data/runs/backtest_curve.json` with `"invert": true` was a stale
experimental artifact. **The optimal RR is 1:5** (tp=0.025), not the
prior 1:3 (tp=0.015). New env knobs `SL_FRAC` / `TP_FRAC` make this
deployable without code edits.

#### Bug fixes that landed during the validation pass

- **Journal hygiene (`9edffb2`).** Two writers (analyzer + router) both
  wrote to `signals.json`. Cap-rejected analyzer rows had no broker fill
  but `settle_open_signals` still settled them against bar high/low,
  producing phantom WIN/LOSS. Stopped the analyzer write entirely
  (router/broker is now the sole journal writer) and added defensive
  skip in `settle_open_signals` for any `entry` not in `{BUY, SELL}`.
- **Fetcher pagination (`ce4abaf`).** `binance.fetch_ohlcv` had
  `PAGE_SIZE=1500` but Binance Futures `/fapi/v1/klines` hard-caps at
  1000 per call. Silent cap fired the `if len(page) < page_limit: break`
  early-termination on every first page. WFO at `--bars 20000` returned
  999 rows. Fixed to `PAGE_SIZE=1000` with empty-page-only termination
  + `max_iters` safety cap. Bybit got the same fix for parity.

### Current production config (2026-06-05)

```
EXCHANGE=binance              # Bybit testnet returned retCode 10024 (KYC)
BINANCE_TESTNET=true
ENABLE_LIVE_TRADING=true      # re-engaged after Phase E + WFO validation
RISK_PCT_LIVE=0.0005          # 0.05% per trade
BIAS_ENGINE=slope             # WFO winner; swing was mis-calling LTF on
                              # BTC/ETH (saw structural HH on a window
                              # that ended in dropping bars)
SL_FRAC=0.005                 # 0.5% stop
TP_FRAC=0.025                 # 2.5% target → 1:5 RR
REQUIRE_BIAS_ALIGNMENT=true   # Phase E gate ON
TG_COMMANDS_MODE=true         # operator runs the bot from phone
TG_CONFIRM_MODE=false         # auto-execute on conf=100, no DM gate
```

Caps applied to live router:
`MaxOpenPositions(1)` + `DailyLossLimit(1R)` + `MaxDrawdown(5%)` +
`MaxLiveTradesPerDay(3)`. Boot guard refuses if
`RISK_PCT_LIVE > MAX_LIVE_RISK_PER_TRADE_PCT (0.001)`.

### Commit chain on `feat/rr2plus-grid` (through Phase E)

```
e834bf9  feat: Phase E winner — SL_FRAC/TP_FRAC env knobs, default 1:5 RR
ce4abaf  fix: exchange fetcher pagination — silent-cap regression on binance
9edffb2  fix: journal hygiene — stop phantom WIN/LOSS on un-placed signals
aad6973  feat: Phase E — HTF/LTF bias-alignment gate (REQUIRE_BIAS_ALIGNMENT)
137afea  feat: Phase D infra — Prometheus alerts + weekly shadow-report CI
514903f  feat: Phase D — tiered autonomy + discipline caps + TG operator commands
```

All six are on `origin/feat/rr2plus-grid` (pushed 2026-06-05).

---

## Phase 2 — Live P&L plumbing (root-cause fixes, 2026-06-05)

The first live testnet run produced a confusing signal: the journal
showed +103R / +$515 cumulative across 88 closes, but the actual
Binance wallet showed roughly zero change. A diagnostic harness
([scripts/diagnose_live_pnl.py](../scripts/diagnose_live_pnl.py))
proved the issue: **46/46 WIN rows had `closed_price` BIT-FOR-BIT
equal to the strategy's `tp`** and **36/37 LOSS rows bit-for-bit
equal to `sl`** — the unmistakable signature of
`journal.settle_open_signals` synthetically closing rows from bar
OHLC while the broker's `_on_close` callback never won the race.

### What landed (Fixes 2.A–2.H)

| Fix | What |
|---|---|
| **2.A** | `journal.append_signal` takes `broker: str = "paper"`; live router passes `broker=self.broker.name` so rows are tagged. |
| **2.B** ⭐ root-cause | `settle_open_signals` skips any row where `broker != "paper"` — the synthetic settler can no longer overwrite real broker closes. |
| **2.D** | `scanner._build_router` uses `RISK_PCT_LIVE` whenever `live=True` regardless of `SHADOW_MODE`. Previously the `(live AND SHADOW_MODE)` gate silently fell back to `RISK_PCT` (10× larger). |
| **2.E** | `BinanceLiveBroker.place_order` captures `entry["average"]` (or `fetch_order` fallback), shifts SL/TP by drift if `RE_ANCHOR_BRACKET=true`, emergency-flattens if `unfavourable_slip > MAX_ENTRY_SLIPPAGE_BPS`. |
| **2.F** | `Order.fees_paid` field; `realised_pnl_R` subtracts `fees / (qty × risk_distance)` when present. `_finalize_filled` extracts entry + close fees from ccxt. `mark_closed_from_broker` persists `pnl_r`, `entry_fill_price`, `fees_paid`. |
| **2.G** | One-shot archive of the synthetic-polluted journal + `scripts/archive_journal.py` for future resets. |
| **2.H** | `cli/shadow_report.py --by-broker` splits per-pair R by broker tag. |
| **2.I** | `scanner._build_router` calls `broker.on_reconnect()` on the live path so restart-orphan-doubling can't recur. |
| **2.J** | `scripts/diagnose_live_pnl.py` ships a `_classify_truth` function + `acceptance` JSON boolean — Phase 3 Layer 2 acceptance becomes a single `jq` check. |

### Phase 2 commit chain

```
9ff8fbb  fix: live P&L plumbing — stop synthetic journal closes for binance-live
ee457b6  docs: Binance USDT-M algo-order visibility gotcha
f94bc2c  fix: on_reconnect wiring + diagnostic broker-truth classifier
```

### Operational discoveries during Phase 2 validation

- **Algo-queue visibility**: STOP_MARKET orders on Binance USDT-M
  futures route through a separate conditional / algo orders queue
  with 16-digit `algoId`s. They're invisible to ccxt's
  `fetch_open_orders` (which queries the regular orders endpoint).
  The SLs WERE being placed correctly — they just lived in a
  different tab the UI labels "Stop Orders" / "Trigger Orders".
  Documented in [docs/operations.md](operations.md#binance-usdt-m-order-visibility-the-sl-missing-trap).
- **Orphan-doubling regression**: an early restart with an open
  position bypassed `MaxOpenPositions(1)` because `broker._orders`
  reset to empty on restart. Fix 2.I (`on_reconnect` wired into
  `_build_router`) closes the door. Tier-1 in Phase 5 makes the
  recovered stub correct (non-zero risk distance) so the eventual
  close books a real R.

---

## Phase 5 — Close known gaps (2026-06-05, evening)

Honest audit of the shipped code surfaced real bugs that today's
smoke test would have exposed within hours, plus visibility gaps
that forced the operator to poll. Tiered four-tier cleanup.

### Tier 1 — Real bugs

- **Fix 5.A — Algo-queue close detection**. `_finalize_filled`
  used `fetch_order(leg_id, pair)` which queries the regular orders
  endpoint. STOP_MARKET algo IDs return `-2013 "Order does not
  exist"`. Every SL fire fell through to MANUAL with
  `close_price=entry` and `pnl_r=0`. The 5 anomalous "BE" rows in
  the archived journal were almost certainly real SL fills the
  broker couldn't identify. Rewrote close detection to use
  `fetch_my_trades(pair, since=created_at)` for the actual close
  fill + direction-based reason inference (SELL closed > entry =
  SL; closed < entry = TP). Falls back to the legacy `fetch_order`
  path for limit TPs in the regular queue.

- **Fix 5.B — `on_reconnect` risk distance**. Rebuilt stub used
  `entry_price` for sl AND tp → risk distance = 0 → realised_pnl_R
  always +0R. Recovers `sl`/`tp` from `fetch_open_orders` when
  present (mainnet); falls back to entry × (1±SL_FRAC/TP_FRAC) on
  testnet. Order grows an `is_reconciled: bool` flag so the close
  handler knows the stub is approximate.

### Tier 2 — Visibility gaps

- **Fix 5.C — TG notify on close**. `router.on_close` now sends a
  one-line summary tagged with realised R, fill prices, fees, qty.
  `[reconciled stub]` prefix when `order.is_reconciled`. Env knob
  `TG_NOTIFY_ON_CLOSE` (default `true`). Live-only; paper closes
  stay silent.

- **Fix 5.D — Emergency-flatten alert**. When `_emergency_flatten`
  itself raises, send `[BOT EMERGENCY]` TG message before
  re-raising. Notification failure cannot mask the original
  critical condition.

- **Fix 5.E — Throttled rejection summary**. New env
  `TG_NOTIFY_REJECTIONS_EVERY=N` (default 0 = off) sends a TG
  summary every Nth rejection per `(pair, reason)`. Per-process
  in-memory counter. Useful in early validation to confirm caps
  are firing without firehosing on `max_open_positions`.

### Tier 3 — Phase 3 Layer 2 acceptance closure

- **Fix 5.F — Wallet parity script**.
  [scripts/verify_wallet_parity.py](../scripts/verify_wallet_parity.py)
  reads journal `pnl_r` × `RISK_PCT_LIVE` × starting_balance, sums
  fees, compares to `fetch_balance` delta vs a baseline file at
  `data/wallet_baseline_usdt.txt`. First run initialises the
  baseline; subsequent runs report drift vs tolerance (default
  $0.50). Exit code 0 = parity, 1 = drift, 2 = infra.

### Tier 4 — Cleanup

- **Fix 5.G** — `datetime.utcnow()` deprecation in
  `scripts/diagnose_live_pnl.py`.
- **Fix 5.H** — `MAX_OPEN_POSITIONS` env override (default 1).
- **Fix 5.I** — Pre-boot API-key sanity check. Refuses to start if
  `ENABLE_LIVE_TRADING=true` and the active venue's API key OR
  secret is empty. Per-venue: binance / bybit / delta.

### Phase 5 commit chain

```
940d06a  fix: algo-queue close detection + on_reconnect risk distance
a4868d6  feat: live TG visibility for closes, rejections, emergency exits
cb8ba4e  feat: wallet-vs-journal parity script (Phase 3 Layer 2 acceptance)
d4187f9  chore: cleanup — datetime, MaxOpenPositions env, pre-boot api-key check
```

Targeted suite after Phase 5: **115 passed** (78 Phase 2 + 37 new).

---

## Phase 6 — Acceptance moment (2026-06-06, morning)

After a clean restart on `d4187f9`, the bot opened a properly-sized
PAXG SELL (qty 0.229 at the intended $5 risk per Fix 2.D), then a
short manual flatten of that position. Scanner's natural cap rotation
picked up an XRP SELL on the very next cycle. **XRP closed at TP**.

### XRP TP — the end-to-end proof point

- Entry: 1.0857 (Fix 2.E captured actual fill from ccxt `average`)
- Exit: TP filled at 1.0586 (LIMIT order, exact fill is by design)
- qty: 916.6
- **Realised R: +5.018** (gross; legacy path didn't extract close
  fees so net would be ~+4.9R after $1 RT fees)
- Wallet change: **+$24.84 net**, $9,899.90 → $9,924.15
- TG close notify (Fix 5.C) landed within 60s:
  `CLOSE XRP/USDT:USDT SELL reason=TP entry=1.0857 exit=1.0586 qty=916.6 R=+5.019 fees=n/a`

This is the **first end-to-end validation** of:
- Fix 2.A (broker field present), Fix 2.B (synthetic settler
  gated), Fix 2.D (`RISK_PCT_LIVE` honoured), Fix 2.E (actual
  fill captured), Fix 2.F (pnl_r populated)
- Fix 5.A (algo-queue safe close detection — legacy fetch_order
  fallback caught the LIMIT TP fill cleanly)
- Fix 5.C (TG notify reached the operator)
- Phase E (WFO predicted +1.05R/trade @ 38.9% WR; one realised
  trade at +5.02R hits the model squarely)

### Fix 6.A — `reduceOnly` filter edge case

A manual PAXG flatten earlier in the session surfaced an edge: a
reduceOnly market order's TRADE record came back with
`reduceOnly=None` (ccxt artifact for manually-issued orders). Fix
5.A's strict filter excluded the trade → fell through to MANUAL.
Fix 6.A relaxes the filter: a trade also counts as a close if
`info.realizedPnl != 0` (Binance's authoritative "this trade
closed a position" signal). Defensive: a `realizedPnl == 0` entry
trade still does NOT misclassify as a close.

### Fix 6.B — Classifier false-positive on LIMIT TP fills

XRP's TP filled at exactly 1.0586 (LIMIT orders fill at the limit
price by definition — no float drift). But Fix 2.J's classifier
flagged the row as `synthetic-live-bug` because closed_price was
bit-for-bit equal to tp, holding the acceptance gate at `false`.
Fix 6.B drops the bit-for-bit check inside the
`pnl_r is not None` branch — trust `pnl_r` as authoritative.
`synthetic-live-bug` is now reserved for the `pnl_r is None`
case where bit-for-bit truly does mean the synthetic settler
won the race.

### Phase 6 commit chain

```
e5a3f64  fix: 6.A — accept realizedPnl-tagged close trades when reduceOnly missing
b403ef2  fix: 6.B — classifier counts LIMIT TP fills as broker-truth
```

After Fix 6.B, the live journal shows `acceptance: True` with 3
`broker-truth-no-fee` rows (2 PAXG MANUAL + XRP TP) and zero
`synthetic-live-bug` rows.

Targeted suite after Phase 6: **117 passed** (115 + 2 new for
Fix 6.A + the inverted classifier test for Fix 6.B).

---

## Phase 8 — End-to-end docs refresh (2026-06-06)

`46ad61c` brought all the long-form docs (README, ROADMAP,
autotrade_plan, operations, DEPLOY, architecture) in sync with the
Phase 6 acceptance moment. No code change; +802 / -69 lines across
6 files. Pushed to origin.

---

## Phase 9 — Per-token completeness pass (2026-06-06, afternoon)

### What the 5-token audit found

The 5 configured pairs (BTC, ETH, SOL, XRP, PAXG) were structurally
symmetric at the scanner / strategy / metrics / scripts layer
(`grep` for hardcoded symbols returned only docstrings). But three
layers below that had **half-finished pieces** that affected
specific tokens differently:

1. **Broker-init plumbing**: `set_leverage` was called per pair but
   its failures were logged and ignored; margin mode was never set
   so different pairs may default to cross vs isolated on Binance
   testnet; `stopPrice` was passed raw without `price_to_precision`;
   qty was floored by the router but never routed through ccxt's
   `amount_to_precision` at broker time.
2. **Sizing**: a single global `SL_FRAC=0.005 / TP_FRAC=0.025`
   applied uniformly across pairs with 4–5× volatility spread (PAXG
   ~1.2 % daily ATR vs SOL ~4–5 %). At 0.5 % SL, SOL was stopped out
   by noise while PAXG rarely reached 2.5 % TP.
3. **Caps**: `MaxOpenPositions=1` ([caps.py:35-47](src/ictbot/portfolio/caps.py))
   starved 4 of 5 pairs whenever any one position was open.
   Confirmed live: XRP conf=100 signals rejected while PAXG held
   the slot for hours.

Plus operational gaps: SOL had **zero** end-to-end broker-truth
closes in the journal; unit tests parametrized only
`BTC/USDT:USDT`; the boot sequence had no per-pair sanity check, so
issues surfaced on the first real signal hours later.

### What landed (Fixes 9.A–9.G in one bundled commit `429af9c`)

| Fix | Component | What it closes |
|---|---|---|
| **9.A** | Per-pair `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` env vars + `settings.get_sl_frac(pair)` + analyzer wiring + `scripts/wfo_per_pair.py` | Single global SL/TP — the dominant edge leak across 5 pairs with different volatility regimes. |
| **9.B** | `MaxConcurrentSameDirection` cap (`portfolio/caps.py`) + `MAX_OPEN_POSITIONS` default `1 → 3` | Cap starving 4 of 5 pairs; correlation guard prevents 3 SELLs stacking on crypto downtrend. |
| **9.C** | `BinanceLiveBroker._ensure_pair_init` — sets `ISOLATED` margin + leverage 5, reads back via `fetch_positions`, refuses boot on mismatch under `STRICT_PAIR_INIT=true` | Silent leverage carry-over from prior sessions + unset margin mode. Defers strict check on -4047 ("can't change while position open") so positions don't block restarts. |
| **9.D** | `_amount_to_precision` + `_price_to_precision` at every `create_order` call site | Raw floats silently rounded by Binance, drifting from journal-stored values. Normalized values stamped back onto Order. |
| **9.E** | `verify_pair_readiness` + scanner boot banner | Per-pair leverage / margin / ticker / min_notional surfaced at boot instead of on first signal hours later. |
| **9.F** | `TestPlaceOrderAcrossPairs` (parametrized 5 pairs) + `scripts/smoke_test_pairs.py` | Unit tests previously only used BTC fixture; live smoke verifies the whole plumbing per pair on testnet. |
| **9.G** | `scripts/diagnose_live_pnl.py --smoke-gate` + ops runbook | No way to operationally prove "all 5 pairs work end-to-end". |

### Phase 9 commit chain

```
429af9c  feat: Phase 9 — per-token completeness pass (Fixes 9.A–9.G)
```

Single bundled commit (same pattern as `9ff8fbb` for Phase 2). 17
files changed, +2220 / -35 lines.

### Phase 9.A — per-pair WFO scoreboard

`scripts/wfo_per_pair.py` running on `rr2plus` grid × 10k bars
across all 5 pairs (~2.5 h compute). Saved to
`data/wfo/per_pair_2026-06-06.{txt,json}`.

| Pair | Verdict | TRAIN exp | TEST exp | TEST W/L | Winning cfg |
|---|---|---|---|---|---|
| **SOL/USDT:USDT** | ✅ holds | +0.82R | +0.80R | 17/28 | poi=0.01, sl=0.003, tp=0.015 |
| **ETH/USDT:USDT** | ✅ holds | +0.65R | +0.45R | 8/17 | poi=0.005, sl=0.003, tp=0.015 |
| **XRP/USDT:USDT** | small sample | +1.92R | +0.88R | 4/4 | poi=0.003, sl=0.008, tp=0.025 |
| **BTC/USDT:USDT** | small sample | +5.53R | +0.09R | 1/5 | poi=0.0015, sl=0.003, tp=0.025 |
| **PAXG/USDT:USDT** | no edge | -0.85R | +0.70R | 5/5 | poi=0.01, sl=0.003, tp=0.01 |

**Operator workflow** (deferred to ops; not a code change):
- Promote `SOL` and `ETH` winners into `.env`:
  `SL_FRAC_SOL=0.003`, `TP_FRAC_SOL=0.015`, `SL_FRAC_ETH=0.003`,
  `TP_FRAC_ETH=0.015`.
- Promote `XRP` and `BTC` cautiously (small sample but positive
  expectancy on TEST).
- Leave PAXG unset — verdict says no edge in-sample.
- Restart scanner to pick up the new values.

### Phase 9.F — live smoke test (2026-06-06)

`scripts/smoke_test_pairs.py` round-tripped all 5 pairs on Binance
testnet. Output `data/smoke_pairs_2026-06-06.json`:

| Pair | Status | Smallest qty | Notional | Latency |
|---|---|---|---|---|
| BTC/USDT:USDT | ok | 0.0009 | $54.83 | 1050 ms |
| ETH/USDT:USDT | ok | 0.013 | $20.44 | 1036 ms |
| SOL/USDT:USDT | ok | 0.08 | $5.01 | 738 ms |
| XRP/USDT:USDT | ok | 4.6 | $5.02 | 975 ms |
| PAXG/USDT:USDT | ok | 0.002 | $8.61 | 589 ms |

All 5 pairs round-tripped clean (entry + `reduceOnly` flatten).
Latency comfortably under the 5 s acceptance ceiling. Wallet
end-state -$0.20 vs start (sum of round-trip fees), as expected.

### Phase 9 verification

- **Layer 1**: 224 Phase 9-affected tests green; **797 / 0 / 2 across
  the full suite**. Pre-existing delta + news_alert failures stay
  out of scope.
- **Layer 2** (live smoke): `data/smoke_pairs_2026-06-06.json` ✓
  all 5 pairs.
- **Layer 3** (observational, post-restart): the per-pair
  `--smoke-gate` waits for ≥ 1 broker-truth close per pair. Current
  state: PAXG ✓, XRP ✓, BTC ⏳, ETH ⏳, SOL ⏳. Estimated 1–3 days
  to close at typical Phase E placement rate.

### Operational notes from Phase 9

- **Manual PAXG flatten**: during Phase 9 implementation, the live
  scanner had an open PAXG SELL (id ~210667330) with uPnL bouncing
  ±$2 around the entry. User asked to end it. Order
  `210737583` (buy 0.23 reduceOnly) flattened cleanly. Wallet ended
  at $9921.51 free USDT, +$21 vs the post-Phase-6 baseline.
- **Margin-mode `-4047` is operationally normal**: PAXG and XRP
  both showed `deferred — pair has an open position/order` warnings
  during the smoke runs. Fix 9.C's deferred-strict pattern handles
  this correctly: the read-back skips the margin check when Binance
  refuses to change the mode while a position is open.

---

## Phase 11 — Drop PAXG/USDT:USDT from the trading set (2026-06-06, evening)

### Why

The Phase 9.A per-pair WFO (`data/wfo/per_pair_2026-06-06.json`)
returned **`no edge`** for PAXG:

| metric | value |
|---|---|
| TRAIN expectancy | **-0.85R** (8 signals, 1 win) |
| TEST W/L | 5/5 on `poi=0.01, sl=0.003, tp=0.01` (sample-of-5 noise) |
| Best in-sample TEST exp | -1.18R to -1.47R across most cells |

The classifier `no edge` short-circuits before any TEST analysis —
TRAIN ≤ 0 means whatever TEST shows is luck.

Plus operational signals:
- Off-hours liquidity is thin (already flagged at
  [data/delta.py:251](src/ictbot/data/delta.py#L251)).
- Margin-mode `-4047` lock during the Phase 9.F live smoke run —
  not a blocker (Fix 9.C's deferred-strict pattern handles it) but
  a sign PAXG's lifecycle differs.
- **3 of 4** PAXG broker-truth closes in the journal are MANUAL
  settlements (operator interventions / on_reconnect anomalies),
  not natural TP / SL fills. The "live distribution" is noise.

### What changed (Fix 11.A–11.D in one commit)

| Fix | Component | What it closes |
|---|---|---|
| **11.A** | `src/ictbot/settings.py` | Drops `"PAXG/USDT:USDT"` from `_DEFAULT_PAIRS`; removes `sl_frac_paxg` + `tp_frac_paxg` Field aliases. `extra="ignore"` in the pydantic-settings config means existing `.env` lines silently drop. |
| **11.B** | 6 test files | Removes PAXG from parametrize lists, fixtures, and the lone PAXG-specific analyzer test. Test counts drop from ~224 → 223 affected (one full test deletion + 5→4 fans). |
| **11.C** | README, ROADMAP, DEPLOY, operations, autotrade_plan | Load-bearing 5-pair language → 4-pair. Banner / scoreboard / config-table examples refreshed. Historical narrative (Phase 6 PAXG TP, Phase 9 PAXG flatten, findings.md WFO entries) stays as past-tense record. |
| **11.D** | operations.md restart procedure | Pre-restart safety check: confirm no open PAXG position before applying the new 4-pair config (after PAXG drops from `allowed_pairs`, `on_reconnect` no longer queries it). |

### What did NOT change

- Existing PAXG rows in `data/journal/signals.json` — historical
  ledger.
- Phase 6 / Phase 9 PAXG narrative in this doc + findings.md +
  ADRs — past tense, correct as written.
- `data/wfo/per_pair_2026-06-06.{txt,json}` and
  `data/smoke_pairs_2026-06-06.json` — dated snapshots, evidence of
  the verdict that drove this removal.
- Comments in `src/ictbot/data/delta.py`,
  `src/ictbot/engine/wfo.py`, etc., that reference PAXG as a past
  failure mode — explanatory context.

### Phase 11 commit chain

```
TODO  chore: Phase 11 — drop PAXG/USDT:USDT (no-edge WFO verdict)
```

(Filled in below in the full commit chain once committed.)

### Verification

- Targeted sweep: **223 passed** post-removal (one less than the
  Phase 9 baseline of 224 — the deleted `test_paxg_uses_per_pair_override_independently`
  plus 5→4 parametrize fans).
- `grep -nE "\bPAXG\b" src/ictbot/` returns only historical
  comments + the settings.py removal-note comment block.
- `python3 scripts/diagnose_live_pnl.py --smoke-gate`: now a 4-pair
  gate. PAXG broker-truth rows in the journal are silently ignored
  (covered by the existing test
  `test_smoke_gate_unknown_pair_in_journal_is_ignored`).

---

## Phase 12 — Per-pair POI tolerance + operator UX (2026-06-06, evening)

### Why

After Phase 11 the active set is 4 pairs and the WFO scoreboard is
the empirical baseline. Reviewing the winners surfaced three
operationally useful gaps:

1. **Per-pair POI tolerance**: Phase 9.A confirmed pairs have
   different volatility regimes and shipped per-pair `SL_FRAC_<TOKEN>`
   / `TP_FRAC_<TOKEN>`. The same scoreboard shows winning POI tap
   tolerance varies **0.0015 → 0.01 across pairs — a 7× spread**:

   | Pair | Winning poi_tol |
   |---|---|
   | BTC | 0.0015 |
   | XRP | 0.003 |
   | ETH | 0.005 |
   | SOL | 0.01 |

   A single global `POI_TAP_TOLERANCE=0.005` is wrong by 3× for BTC
   and 2× for SOL.

2. **`.env.example` was stale** — missing every Phase 9 + Phase 11
   env var. New deployments couldn't see the right baseline; the
   WFO winners were documented only in `autotrade_plan.md`.

3. **No Make targets for Phase 9 ops tools** — operators ran the
   smoke gate / smoke test / per-pair WFO via raw Python.

### What landed (Fix 12.A–12.D in one commit)

| Fix | Component | What it closes |
|---|---|---|
| **12.A** | `settings.py` (4 new Fields + `get_poi_tap_tolerance(pair)` helper) + `analyzer.py` (route through helper) + 9 new tests in `test_settings_per_pair_rr.py` + `test_analyzer_per_pair_rr.py` | Single global `POI_TAP_TOLERANCE` was the next per-pair edge leak after Phase 9.A SL/TP. |
| **12.B** | `.env.example` (rewrite) | Stale operator template. Now covers Telegram, Exchange, Live risk (incl. Phase 9.B + 9.C), Strategy (incl. Phase 12.A), Phase 9.A + 12.A WFO winners as commented opt-ins, Phase 11 removal note. |
| **12.C** | `Makefile` (4 new targets) | `make smoke_gate`, `make smoke_pairs`, `make wfo_per_pair`, `make pair_readiness` — wrappers around existing scripts. Plus a small fix in `diagnose_live_pnl.py`: smoke-gate banner now reads `{n}-pair` from `len(per_pair)` instead of hardcoded "5-pair". |
| **12.D** | docs refresh | operations.md adds Phase 12 POI section + recommends `make` targets throughout. DEPLOY.md adds `POI_TAP_TOLERANCE_<TOKEN>` to env-var table. ROADMAP.md adds Phase 12 row. README/autotrade_plan updated. |

### Phase 12 verification

- 232 Phase 12-affected tests green (was 223 in Phase 11; +9 for the
  new `TestGetPoiTapTolerance` class + 3 analyzer per-pair POI tests
  + minor parametrize touchups).
- Full sweep: 799 / 0 / 2 (no regressions).
- `make smoke_gate` works against the live journal — reports
  `4-pair smoke gate: PENDING` (XRP green, BTC/ETH/SOL pending).
- `make pair_readiness` reports all 4 pairs `ok=True` with
  sized_notional ~$992 each at the current wallet ($9921).
- `grep -oE 'alias="[A-Z_]+"' src/ictbot/settings.py | sort -u` cross-
  checks against `.env.example` — every Phase 9/11/12 alias has a
  matching template line.

### Out of scope

- **Scanner restart** (operator step; PID 51247 still on `d4187f9`).
- **Promoting WFO winners as code defaults** in `settings.py`
  — kept as commented `.env.example` examples so the operator
  controls when to opt in. `Field(default=0.003)` would mask the
  fall-back-to-global test semantics.
- **Tier 5** (Bybit/Delta mirror) — deferred until 4-pair smoke
  gate passes.

### Phase 12 commit chain

```
TODO  feat: Phase 12 — per-pair POI tolerance + .env.example refresh + make targets
```

(Filled in below in the full commit chain once committed.)

---

## Phase 13 — Tunable risk caps + ops status snapshot (2026-06-06, evening)

### Why

After Phase 12 the per-pair config is settled and ops have
`make smoke_gate / smoke_pairs / pair_readiness / wfo_per_pair` for
daily checks. Two production-readiness gaps remained:

1. **Two risk caps were hardcoded** at `scanner.py:203-204`
   (`DailyLossLimit(limit_R=1.0)` + `MaxDrawdown(limit=0.05)`).
   `MaxOpenPositions` (Fix 5.H) and `MaxSameDirection` (Fix 9.B) were
   already env-tunable; promoting the remaining two completes the
   envelope.
2. **No single-shot status check** — operators wanted one command
   showing wallet + positions + gate + heartbeat + recent closes
   instead of running 3-4 separate make / python invocations.

### What landed (Fix 13.A–13.D in one commit)

| Fix | Component | What it closes |
|---|---|---|
| **13.A** | `settings.py` `daily_loss_limit_r` Field + boot guard + module-level export; `scanner.py` reads from constant | Hardcoded `DailyLossLimit(limit_R=1.0)`. Boot refuses on ≤ 0. |
| **13.B** | `settings.py` `max_drawdown_frac` Field + boot guard + module-level export; `scanner.py` reads from constant | Hardcoded `MaxDrawdown(limit=0.05)`. Boot refuses outside `(0, 1)`. |
| **13.C** | New `scripts/status.py` (~280 LOC, 5 sections); `Makefile` `make status` target; `tests/test_status_script.py` (11 tests) | One-shot ops dashboard. Reuses `diagnose_live_pnl.build_smoke_gate` and `BinanceLiveBroker.equity()` rather than reimplementing. |
| **13.D** | docs refresh + .env.example | Operators see new caps + status target. |

### Verification

- 8 new boot-guard tests in `tests/test_settings_boot_guards.py`
  (default values + env overrides + 4 refusal modes); 15 total pass.
- 11 new tests in `tests/test_status_script.py` covering all 5
  sections + recent-closes filtering / ordering / cap.
- Full sweep: 246 targeted, 813 full (was 235 / 802 in Phase 12;
  +11 / +11 = the new tests).
- `make status` runs end-to-end against live testnet — wallet,
  positions, gate, heartbeat, closes all render correctly.

### Phase 13 commit chain

```
TODO  feat: Phase 13 — tunable risk caps (daily-loss + drawdown) + make status
```

(Filled in below in the full commit chain once committed.)

### Out of scope

- **Daily TG digest** — Fix 5.C close notify + Fix 5.E rejection
  summary already cover most of what a digest would add.
- **`/gate` TG command** — `make status` covers it locally.
- **Scanner restart** (still operator step; PID 51247 on `d4187f9`).
- **Tier 5** (Bybit/Delta mirror) — deferred until 4-pair smoke
  gate passes.

---

## Phase 14 — Edge reality check (2026-06-06, evening)

### What prompted this

User asked: *"check the morning XRP trade and the rest of the trade
made after that. It hit the TP and post that hitting only SL. Make a
check that whether it is a by-luck thing or real thing which is done
through my implementation."*

Read-only audit of `data/journal/signals.json` produced an answer
the user didn't expect.

### The hard data

Today (UTC 2026-06-06) the running scanner — still on commit
`d4187f9`, pre-Phase-9 code — placed **exactly 3 live brackets**
(the `MaxLiveTradesPerDay(3)` ceiling):

| Time UTC | Pair | Side | Outcome | R | What it really was |
|---|---|---|---|---|---|
| 00:10:37 | PAXG | SELL | BE | +0.000 | MANUAL flatten (`close_reason=None`, `entry==exit`) |
| 04:01:10 | PAXG | SELL | BE | +0.000 | MANUAL flatten |
| **04:37:30** | **XRP** | **SELL** | **WIN** | **+5.019** | **Real TP fill — only natural close in the journal** |
| 05:47:18 | PAXG | SELL | BE | +0.000 | MANUAL flatten (operator flatten earlier today) |

**4 broker-truth rows total. 1 natural close. 3 MANUAL flattens.**

### Post-XRP-TP — the "SLs hitting" myth

After 04:37:30 the journal shows **65 REJECTED rows + 1 PAXG MANUAL
flatten** and **zero broker-truth LOSSes**. Per-cap breakdown:

| Cap | Count |
|---|---|
| `max_live_trades_per_day` | 53 |
| `max_open_positions` | 12 |

Per-pair:

| Pair | REJECTED count |
|---|---|
| PAXG | 46 |
| BTC | 9 |
| XRP | 7 |
| ETH | 3 |
| SOL | 0 |

What the user perceived as "SL hitting" is one of:
- The REJECTED dashboard rows (cap rejections, no money moved)
- Stop-market orders sitting on Binance's algo queue from now-flat
  PAXG positions (Phase 9 algo-queue visibility gotcha)
- Pre-Phase-2 synthetic SL rows in the archived journal (the
  regression Phase 2 fixed)

### The verdict — edge or luck?

**N = 1 broker-truth natural close.** This is not statistical
evidence either way. Anyone who tells you a single +5R win proves
the strategy works is fooling themselves.

What we **know**:
- The plumbing is correct. XRP TP fired naturally on the algo
  queue, `fetch_my_trades` (Fix 5.A) captured it, `pnl_r` was
  computed against the actual entry fill (Fix 2.E + 2.F), wallet
  delta matched journal-implied USDT (Phase 3 Layer 2 acceptance).
- The strategy IS firing setups — 65 of them were generated after
  the XRP TP, all blocked by caps.
- The +5R outcome matches Phase E's WFO model shape, but that's
  confirmation bias on N=1.

What we **don't know**:
- Whether the strategy has positive expectancy at scale. The
  Phase 9.A WFO scoreboard says SOL + ETH ✅ holds, BTC + XRP
  "small sample". None of that has been confirmed live.
- Whether the 65 REJECTED setups would have won or lost — they
  never got a chance.

**Honest summary**: the morning XRP TP is consistent with both edge
and luck and cannot distinguish them. The implementation is correct
enough that we can find out — once data accumulates.

### Why the journal is starved

The running scanner is on commit `d4187f9` — **pre-Phase-9**. It's
limited by:
- `MAX_OPEN_POSITIONS=1` (old default; Phase 9.B raised to 3)
- `MAX_LIVE_TRADES_PER_DAY=3` (Phase D default)

Phase 9-13 improvements are sitting on `5a91d07` waiting for the
operator to restart. The starved state will continue until restart.

### The procedural fix

**Operator workflow (user-confirmed scope, no code change)**:

1. **Edit `.env`**: set `MAX_LIVE_TRADES_PER_DAY=0` — Phase 15 testing-
   phase trust mode disables the daily count cap entirely so every
   conf=100 signal fires. The other safety caps stay active as the
   wise-skip layer (`MAX_OPEN_POSITIONS=3`, `MAX_SAME_DIRECTION=2`,
   `DAILY_LOSS_LIMIT_R=1.0`, `MAX_DRAWDOWN_FRAC=0.05`). Revert to
   default `3` before mainnet.
2. **Restart the scanner** onto Phase 13 code per the procedure in
   `docs/operations.md` § "Phase 9 restart procedure (with Phase 9 +
   Phase 11 code)". The new code path activates:
   - `MAX_OPEN_POSITIONS=3` (3 of 4 pairs concurrent)
   - `MAX_SAME_DIRECTION=2` (anti-correlation)
   - Per-pair `_ensure_pair_init` (margin + leverage read-back)
   - Boot banner showing 4-pair readiness
3. **Watch the smoke gate close**: `make smoke_gate` should report
   `4-pair smoke gate: PASS` once each of BTC/ETH/SOL produces a
   broker-truth close. Currently only XRP is green. At 9 trades/day
   ÷ 4 pairs ≈ 2 placements per pair per day, N≥30 broker-truth
   closes should accumulate in ~3-4 calendar days.
4. **Once N≥30, the edge-vs-luck question becomes answerable**:
   - Compute realised expectancy_R per pair
   - Compare to Phase E WFO model (+1.05R/trade @ 38.9% WR @ 1:5 RR)
   - Compare to Phase 9.A per-pair WFO TEST expectancy
   - If observed expectancy ≥ +0.5R/trade with N≥30, the edge is
     real
   - If near 0 or negative, the WFO winners were curve-fit and the
     live distribution disagrees

### Phase 14 commit chain

```
TODO  docs: Phase 14 — edge reality check (audit + observation methodology)
```

No code. No scripts. Just the audit findings + restart playbook
note + the cap-raise recommendation for the observation period.

### Out of scope

- **`scripts/edge_check.py`** statistical analysis script —
  deferred (user chose "audit + restart procedure" only). Once
  N≥30 the operator can run a one-off analysis on the journal
  directly.
- **Scanner restart inline** — operator step.
- **Tier 5** (Bybit/Delta mirror) — still waiting on smoke gate.

---

## Phase 15 — Testing-phase trade cap relaxation (2026-06-06, evening)

### Why

User asked: *"as soon as you approach any new signal quickly trigger
a trade on it. Currently we will skip the no. of trades as there is
100% confidence on strategy so we have to trust that and start
executing it in our testing phase which we are in right now so work
on it and remove the no. trade barrier or skip is wisely"*

The Phase 14 audit confirmed `MaxLiveTradesPerDay(3)` was blocking
53 of 65 post-XRP-TP signals. Since `AUTO_EXECUTE_MIN_CONFIDENCE=100`
means every signal that reaches the router is a perfect-score 4-gate
ICT setup, the count cap is the dumb one. The other caps
(`MAX_OPEN_POSITIONS=3`, `MAX_SAME_DIRECTION=2`, `DAILY_LOSS_LIMIT_R`,
`MAX_DRAWDOWN_FRAC`) are the wise-skip layer and stay active.

### What landed (Fix 15.A–15.B in one commit)

| Fix | Component | What it closes |
|---|---|---|
| **15.A** | `portfolio/caps.py` `MaxLiveTradesPerDay.check()` + 2 new tests | Hardcoded count cap that blocked testing-phase observation. `limit <= 0` now means "no cap" — mirrors `MaxConcurrentSameDirection`'s disabled semantic. Short-circuits the journal read entirely when disabled (saves I/O). Default stays `3` for mainnet safety. |
| **15.B** | `.env.example`, `DEPLOY.md`, `docs/operations.md`, `docs/autotrade_plan.md`, `ROADMAP.md` | Documents the disabled semantic + recommends `MAX_LIVE_TRADES_PER_DAY=0` for the testing-phase observation window. Phase 14 restart procedure updated to use `=0` instead of `=9`. |

### Verification

- `tests/test_caps.py`: 18 tests green (16 baseline + 2 new for the
  disabled semantic, including a spy-reader assert that the journal
  is never read when `limit=0`).
- Full sweep stays at 0 regressions.
- Manual sanity: `python -c "from ictbot.portfolio.caps import
  MaxLiveTradesPerDay; print(MaxLiveTradesPerDay(limit=0).check().allow)"`
  prints `True`.

### Phase 15 commit chain

```
TODO  feat: Phase 15 — testing-phase trade-count cap (MAX_LIVE_TRADES_PER_DAY=0 = disabled)
```

### Out of scope

- **Removing other caps** — `MAX_OPEN_POSITIONS`, `MAX_SAME_DIRECTION`,
  `DAILY_LOSS_LIMIT_R`, `MAX_DRAWDOWN_FRAC` are the wise-skip layer
  the user explicitly asked to keep.
- **Changing the default from 3** — mainnet-safe baseline. Testing-
  phase users opt in via `.env`.
- **Per-pair daily count caps** — different feature; not requested.
- **Scanner restart inline** — operator step.

---

## Phase 16 — Session-bucketed daily trade report (2026-06-06, evening)

### Why

User asked: *"During the london session and NY session this strategy
is mostly functional so work on it and get a core analysis of it from
next time trades and make an md file for next day trade regarding the
trades taken from signal with session and without session. Without
session this wouldn't be effective and we want to test that whether
is effective or not!"* Plus: *"this journal detail is well base of
either dropping this project or keeping it. we will be damn serious."*

The user has a strong ICT prior that strategy edge concentrates in
the London + NY killzones. Phase 16 builds a deliberate daily
markdown report that tests that prior on real broker-truth closes.
The report is the artifact the operator opens next morning to make
keep-or-drop decisions.

### What landed (Fix 16.A–16.E in one commit)

| Fix | Component | What it closes |
|---|---|---|
| **16.A** | `journal.append_signal` accepts a `session: str \| None` kwarg + router `_journal_placed` / `_journal_rejected` forward `result["active_session"]` | Journal rows didn't carry session attribution. Going forward each row records the killzone-aware session label at fire time. Legacy rows fall back to reconstruction. |
| **16.B** | New `scripts/session_report.py` (~440 LOC). Bucketing, Welch's t, per-pair × bucket, MD writer. Reuses `runtime.sessions.get_sessions()` for legacy reconstruction and the `edge_check` stats helpers. | No way to test the killzone hypothesis on live data. |
| **16.C** | `Makefile` `session_report` target with `ARGS` forwarding | Operator UX. |
| **16.D** | `tests/test_session_report.py` (36 tests) + `tests/test_journal.py` (1 new for the session round-trip) | Coverage of bucketing, Welch's t formula, MD section structure, exit codes, --no-write / --out / invalid --date. |
| **16.E** | `docs/operations.md` new Phase 16 section + `ROADMAP.md` Phase 16 row + this autotrade_plan.md entry | Operator onboarding. |

### Verification

- 36 new session_report tests + 1 new journal test → 37 additions.
- Targeted sweep: 290+ green (was 254 baseline + Phase 14.D 29 + Phase 15 2 + Phase 16 37 = ~322 expected; reality ≤ slightly lower due to overlap).
- Full sweep: 0 regressions.
- Live verification: `make session_report ARGS="--date 2026-06-06"`
  writes `data/reports/session_2026-06-06.md`. **Surprising finding**:
  the morning XRP TP at 04:37 UTC = TOKYO session (London opens 07:00
  UTC, NY opens 12:00 UTC) → it was OFF_SESSION, not IN_SESSION. The
  two losses at 12:24 UTC (SOL + XRP) were both NEW YORK session.
  Early data at N=5 trends the OPPOSITE of the killzone hypothesis;
  too small to draw conclusions, but the report surfaces it honestly.

### Phase 16 commit chain

```
TODO  feat: Phase 16 — session-bucketed daily trade report (in-session vs off-session)
```

### Out of scope

- **Auto-cron the report** — manual `make session_report` is enough
  during testing. CI cron can wrap this later.
- **Telegram push of the MD** — designed for deliberate morning
  review, not real-time pings.
- **Backfilling session on archived journal rows** — read-time
  reconstruction handles legacy rows on-demand.
- **Flipping `KILLZONE_REQUIRED=true`** — operator decision based
  on the report. The strategy param already exists; flipping is
  an `.env` edit, not a code change.

---

## Phase 17 — Drop Bybit from the codebase (2026-06-07)

After Phase 11 (PAXG removed) and Phases 12-16 (per-pair POI / tunable
caps / edge audit / testing-phase trust mode / session report), the
Binance testnet flow is operationally settled and Delta is the
mainnet target. Bybit had been **dead code** carried since the Phase A
pivot (KYC blocked Bybit testnet derivatives with retCode 10024;
Binance Futures testnet has no KYC).

Phase 17 rips it out entirely.

**Deleted (`git rm`)**:
- `src/ictbot/data/bybit.py` — `BybitExchange` adapter (240 LOC).
- `src/ictbot/exec/bybit_live.py` — `BybitLiveBroker` (446 LOC).
- `tests/test_bybit_pagination.py` / `test_bybit_retry.py` /
  `test_bybit_live_broker.py` — 473 LOC of dedicated Bybit tests.
- `scripts/smoke_live.sh` (Bybit testnet smoke) +
  `scripts/check_bybit_keys.sh` (Bybit cred sanity check).
- `tests/test_cvd.py` — exercised `BybitExchange.fetch_cvd`; Binance
  intentionally doesn't implement `fetch_cvd` (indicators fallback
  handles it), so the test is dead alongside Bybit.
- `tests/test_live_broker_gated.py` — Bybit broker gating tests,
  redundant with the equivalent `BinanceLiveBroker` coverage in
  `test_binance_live_broker.py:143-155`.

**Pruned**:
- `src/ictbot/data/factory.py` + `src/ictbot/exec/factory.py` — the
  `if name == "bybit":` branches and their imports.
- `src/ictbot/settings.py` —
  - `exchange: Literal["delta", "bybit", "binance"]` →
    `Literal["delta", "binance"]`. Pydantic now refuses
    `EXCHANGE=bybit` at boot with a clear validation error.
  - `bybit_api_key` / `bybit_api_secret` / `bybit_testnet` Fields
    removed.
  - `_venue_to_creds["bybit"]` entry dropped from the Fix 5.I boot
    guard.
  - Module-level `BYBIT_TESTNET = settings.bybit_testnet` export
    removed.
- `src/ictbot/portfolio/journal.py` — `"bybit-live"` dropped from
  the broker-type docstring enum.
- `tests/test_exchange_factory.py` — 3 dedicated Bybit factory tests
  deleted + error-message assertion updated to `delta / binance`.
- `tests/test_settings_boot_guards.py` — Bybit cred cleanup parametrize
  pruned + Bybit-without-keys test replaced with a Delta equivalent
  to keep coverage on the second venue's boot guard.
- `tests/test_tick_autodiscovery.py` — `BybitExchange.tick_size` unit
  tests ported to `BinanceExchange.tick_size` (identical shape).
- `tests/test_audit_regressions.py` — #5 bracket rollback section
  (Bybit-specific) deleted; the equivalent Binance coverage in
  `test_binance_live_broker.py` (lines 88, 284, 323) is the
  surviving home for that audit gap.
- `tests/test_cache_replay.py` — venue label switched from `"bybit"`
  to `"binance"`.
- `tests/test_shadow_router.py` — fanout broker mock name updated
  `bybit-live` → `binance-live`.
- All narrative references to Bybit in surviving code-comment
  docstrings (`__init__`, `runtime/kill_switch`, `data/binance`,
  `data/delta`, `data/exchange`, `data/replay`, `engine/backtest`,
  `exec/binance_live`, `exec/delta_live`, `exec/broker`,
  `exec/orders`, `orchestrator/{scanner,analyzer,router}`) cleaned —
  references to deleted symbols swapped for the surviving
  Binance/Delta equivalent, behavior-explaining language kept.

**Docs refreshed**:
- `README.md` — file-layout block + scripts table + Phase 17 status
  note alongside the Phase 11 PAXG note.
- `DEPLOY.md` — env-var table now lists only `binance` / `delta`;
  Bybit example dropped; broker-name table updated.
- `.env.example` — Bybit perps section removed.
- `pyproject.toml` — project description switched from "for Bybit
  perpetuals" to "for crypto perpetuals (Binance Futures testnet;
  Delta Exchange mainnet target)".
- `ROADMAP.md` — repo-state banner notes Phase 17; new Phase 17 row
  in the Status table.

**Kept verbatim** (past-tense record, same pattern as Phase 11):
- `docs/autotrade_plan.md` Phase A — the Bybit testnet → KYC blocked
  → Binance pivot decision is load-bearing project history.
- `ROADMAP.md` F1 / J3 / J4 / C1 / E1 narrative — descriptions of
  *completed* Bybit work that no longer ships, kept for historical
  context.
- `docs/findings.md` — empirical WFO entries that happened to be
  Bybit-sourced; describe what *was* tested.
- ADRs (`docs/adr/*.md`) — historical decision records.

**What this changes operationally**:
- The next scanner restart will boot with `EXCHANGE=binance` (the
  running scanner has been on Binance since Phase 6). Anyone with
  `EXCHANGE=bybit` in `.env` gets a loud pydantic validation error
  rather than a silent fall-through.
- No journal rows have `broker="bybit-live"` (verified — all live
  rows are `binance-live`), so no data migration.

### Verification

- `grep -rE "bybit|Bybit|BYBIT" src/ictbot/ tests/ scripts/` → 0 hits.
- `grep -E "bybit" .env.example pyproject.toml Makefile` → 0 hits.
- Targeted sweep (factory + caps + router + scanner-integration +
  settings boot + Binance broker + Delta broker + tick + journal +
  diagnose + smoke + session) — green minus the pre-existing
  `test_delta_live_broker::test_place_order_refuses_when_live_disabled`
  flake (Phase 3 Layer 1 baseline, unrelated to Phase 17).
- Settings boot smoke: `EXCHANGE=binance` parses, `EXCHANGE=delta`
  parses, `EXCHANGE=bybit` raises `pydantic.ValidationError` —
  exactly the desired behaviour.

### Rollback

Single commit revert. ccxt is shared by Binance + Delta so no
dependency change. Re-adding from history is mechanical.

---

## Current production config (2026-06-07, post-Phase-17)

```
EXCHANGE=binance              # Binance Futures testnet — testing venue
BINANCE_TESTNET=true
ENABLE_LIVE_TRADING=true      # gated by Fix 5.I + RISK_PCT_LIVE boot guards
RISK_PCT_LIVE=0.0005          # 0.05% per trade — now wins whenever live=True (Fix 2.D)
MAX_LIVE_RISK_PER_TRADE_PCT=0.001  # boot guard ceiling
MAX_OPEN_POSITIONS=3          # Fix 9.B — raised from 1; allows 3 of 5 pairs concurrent
MAX_SAME_DIRECTION=2          # Fix 9.B — anti-correlation: ≤ 2 SELLs or ≤ 2 BUYs at once
STRICT_PAIR_INIT=true         # Fix 9.C — refuse to boot if margin/leverage mismatch
DAILY_LOSS_LIMIT_R=1.0        # Fix 13.A — cumulative-R loss cap per UTC day
MAX_DRAWDOWN_FRAC=0.05        # Fix 13.B — peak-to-trough drawdown ceiling
MAX_LIVE_TRADES_PER_DAY=0     # Fix 15.A — testing-phase trust mode (0 = disabled; revert to 3 for mainnet)
BIAS_ENGINE=slope             # WFO winner
SL_FRAC=0.005                 # 0.5% stop — global fallback
TP_FRAC=0.025                 # 2.5% target → 1:5 RR — global fallback
POI_TAP_TOLERANCE=0.005       # global POI tap tolerance (Fix 12.A fallback)
# Phase 9.A + 12.A per-pair overrides (operator opt-in from data/wfo/per_pair_2026-06-06.json):
# SL_FRAC_SOL=0.003   TP_FRAC_SOL=0.015   POI_TAP_TOLERANCE_SOL=0.01    # ✅ holds (TEST +0.80R)
# SL_FRAC_ETH=0.003   TP_FRAC_ETH=0.015   POI_TAP_TOLERANCE_ETH=0.005   # ✅ holds (TEST +0.45R)
# SL_FRAC_XRP=0.008   TP_FRAC_XRP=0.025   POI_TAP_TOLERANCE_XRP=0.003   # small sample (TEST +0.88R)
# SL_FRAC_BTC=0.003   TP_FRAC_BTC=0.025   POI_TAP_TOLERANCE_BTC=0.0015  # small sample (TEST +0.09R)
# (Phase 11: PAXG dropped from the trading set entirely — was `no edge` in WFO.)
REQUIRE_BIAS_ALIGNMENT=true   # Phase E gate ON
RE_ANCHOR_BRACKET=true        # Fix 2.E
MAX_ENTRY_SLIPPAGE_BPS=30     # Fix 2.E
TG_NOTIFY_ON_CLOSE=true       # Fix 5.C
TG_NOTIFY_REJECTIONS_EVERY=0  # Fix 5.E — silent by default
TG_COMMANDS_MODE=true         # operator runs the bot from phone
TG_CONFIRM_MODE=false         # auto-execute on conf=100, no DM gate
```

Caps applied to live router (Phase 9.B order):
`MaxOpenPositions(MAX_OPEN_POSITIONS=3)` +
`MaxConcurrentSameDirection(MAX_SAME_DIRECTION=2)` +
`DailyLossLimit(1R)` + `MaxDrawdown(5%)` + `MaxLiveTradesPerDay(3)`.

Boot guards:
- `RISK_PCT_LIVE > MAX_LIVE_RISK_PER_TRADE_PCT` → refuse.
- `ENABLE_LIVE_TRADING=true` + venue API key or secret empty →
  refuse (per-venue, Fix 5.I).
- `TG_CONFIRM_MODE=true` + no `TG_OPERATOR_USER_ID` → refuse.
- **Phase 9.C**: `STRICT_PAIR_INIT=true` + any pair's leverage or
  margin mode mismatches requested values → refuse. Auto-deferred
  when Binance returns -4047 ("can't change while position open").
- **Phase 9.E**: `STRICT_PAIR_INIT=true` + any pair fails
  `verify_pair_readiness` (no leverage / no margin / no ticker /
  sized_notional below min_notional) → refuse. Banner prints
  per-pair status pre-fail.

---

## Full commit chain on `feat/rr2plus-grid`

```
TODO     feat: Phase 16 — session-bucketed daily trade report (in-session vs off-session)
37ffe72  feat: Phase 15 — testing-phase trade-count cap (MAX_LIVE_TRADES_PER_DAY=0 = disabled)
0b4cace  feat: Phase 14.D — scripts/edge_check.py (statistical edge vs luck)
8d47ba0  docs: Phase 14 — edge reality check (audit + observation methodology)
5a91d07  feat: Phase 13 — tunable risk caps (daily-loss + drawdown) + make status
c64ead7  feat: Phase 12 — per-pair POI tolerance + .env.example refresh + make targets
158fe72  chore: Phase 11 — drop PAXG/USDT:USDT (no-edge WFO verdict)
6161c83  docs: end-to-end refresh for Phase 9 (per-token completeness)
429af9c  feat: Phase 9 — per-token completeness pass (Fixes 9.A–9.G)
46ad61c  docs: end-to-end refresh for Phases 2-6 (P&L plumbing, visibility, acceptance)
b403ef2  fix: 6.B — classifier counts LIMIT TP fills as broker-truth
e5a3f64  fix: 6.A — accept realizedPnl-tagged close trades when reduceOnly missing
d4187f9  chore: cleanup — datetime, MaxOpenPositions env, pre-boot api-key check
cb8ba4e  feat: wallet-vs-journal parity script (Phase 3 Layer 2 acceptance)
a4868d6  feat: live TG visibility for closes, rejections, emergency exits
940d06a  fix: algo-queue close detection + on_reconnect risk distance
f94bc2c  fix: on_reconnect wiring + diagnostic broker-truth classifier
ee457b6  docs: Binance USDT-M algo-order visibility gotcha
9ff8fbb  fix: live P&L plumbing — stop synthetic journal closes for binance-live
e834bf9  feat: Phase E winner — SL_FRAC/TP_FRAC env knobs, default 1:5 RR
ce4abaf  fix: exchange fetcher pagination — silent-cap regression on binance
9edffb2  fix: journal hygiene — stop phantom WIN/LOSS on un-placed signals
aad6973  feat: Phase E — HTF/LTF bias-alignment gate (REQUIRE_BIAS_ALIGNMENT)
137afea  feat: Phase D infra — Prometheus alerts + weekly shadow-report CI
514903f  feat: Phase D — tiered autonomy + discipline caps + TG operator commands
```

All on `origin/feat/rr2plus-grid`. Next:
- **5-pair smoke gate to close** (BTC/ETH/SOL still pending broker-
  truth closes; 1–3 days expected).
- **Operator: promote Phase 9.A per-pair WFO winners into `.env`**
  (SOL + ETH ✅, BTC + XRP small sample, PAXG no-edge — keep unset).
- **Phase 7 (deferred until smoke gate green)**: mirror Fix 2.E, 2.F,
  5.A, 5.B, 9.C, 9.D, 9.E into `bybit_live.py` + `delta_live.py`;
  mainnet shadow (after Bybit KYC clears or Delta keys rotate);
  strategy WFO refresh at `--bars 50000` against the live data
  window.
