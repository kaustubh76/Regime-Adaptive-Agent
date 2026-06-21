# Operations runbook

> How to run, monitor, and roll back ictbot. Walks step-by-step from a
> fresh shell.

## Prerequisites

- Python 3.10+ (3.13 is the dev target).
- `git`, a working venv tool (`python3 -m venv`).
- Binance USDT-M Futures testnet works without KYC; sign up at
  <https://testnet.binancefuture.com> and use the USDT faucet. Live
  trading requires API keys with **trade** permission.
- `prometheus_client` is a HARD dependency as of `137afea` (Phase D
  metrics rely on it; the no-op shim used to mask metric drops on the
  `/metrics` endpoint). Installed automatically via `pip install -e .`.
- Optional: `python-telegram-bot>=21.0` for Phase C confirm-buttons AND
  Phase D operator commands. Install via `pip install -e .[tg]`.

## First-time setup

```bash
git clone <repo> ictbot && cd ictbot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pre-commit install   # one-time

cp .env.example .env   # then edit; never commit the populated .env
mkdir -p data/cache data/journal data/logs data/runs
```

`.env` keys that matter:

| Key                    | Value                                    |
| ---------------------- | ---------------------------------------- |
| `TELEGRAM_TOKEN`       | from @BotFather                          |
| `TELEGRAM_CHAT_ID`     | from `https://api.telegram.org/bot<T>/getUpdates` |
| `TG_OPERATOR_USER_ID`  | numeric user id (msg @userinfobot) — required for `TG_CONFIRM_MODE` or `TG_COMMANDS_MODE` |
| `ENABLE_LIVE_TRADING`  | `false` (default; flip ONLY after B5 paper-trade) |
| `EXCHANGE`             | `delta` (default) / `binance` — Bybit removed in Phase 17; `EXCHANGE=bybit` now refused at boot |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | only when `EXCHANGE=binance` AND live; testnet keys from `https://testnet.binancefuture.com` |
| `BINANCE_TESTNET`      | `true` while validating; `false` for mainnet (don't unless you mean it) |

**Phase D/E knobs** (defaults preserve pre-Phase-D behaviour, override per-deployment):

| Key                            | Default  | Purpose |
| ------------------------------ | -------- | ------- |
| `AUTO_EXECUTE_MIN_CONFIDENCE`  | `100`    | conf ≥ this auto-routes; below + `TG_CONFIRM_MODE=on` → confirm DM; else drop |
| `MAX_LIVE_TRADES_PER_DAY`      | `3`      | journal-derived daily cap (UTC date) |
| `MAX_LIVE_RISK_PER_TRADE_PCT`  | `0.001`  | boot guard: refuses to start if `RISK_PCT_LIVE` exceeds this |
| `TG_COMMANDS_MODE`             | `false`  | enable `/status /journal /kill /resume /pause /whoami /help` |
| `REQUIRE_BIAS_ALIGNMENT`       | `true`   | Phase E gate: HTF and LTF bias must agree before fire |
| `BIAS_ENGINE`                  | `swing`  | `slope` recommended in current regime (see Phase E WFO) |
| `SL_FRAC` / `TP_FRAC`          | `0.005` / `0.015` | WFO winner: `0.005` / `0.025` for 1:5 RR |

Verify install:
```bash
.venv/bin/python -m pytest -q
```
All tests should pass. If they don't, do not proceed.

## BNB Hack — PnL campaign cron (forward paper track)

The forward sim track runs unattended from a crontab (installed 2026-06-13; local IST = UTC+5:30):

```cron
40 5,17 * * *        scripts/forward_tick.sh        # 12h forward sim tick (00/12 UTC bar close +10m)
*/15 * * * *         scripts/dd_watch.sh sim        # 15-min risk watcher: 10% DD halt + profit-lock
40 3 23-29 6 *       scripts/daily_floor.sh live    # live-week >=1-trade/day floor (inert until armed)
```

Logs: `data/logs/allocator_cron.log` (ticks), `data/logs/dd_watch_sim.log` (watcher). The full
campaign runbook — `--anchor-nav`, `--resume` vs `--unlock-profit`, `make sweep_campaign` — lives in
[bnb_strategy_decision.md §8](bnb_strategy_decision.md). The **live-arming steps** (the SIM→live `.env`
flip, the contest-week crons, kill-switch/resume brakes, roll-back) are consolidated into the single
operator checklist: **[live_arming_runbook.md](live_arming_runbook.md)**.
Track-1 fit is checked row-by-row in [track1_alignment.md](track1_alignment.md).

> **Postmortem (why this section exists):** the prior forward cron pointed at a stale
> `"BNB Hack * CMC"` path and silently no-op'd — the Jun 8–12 ticks were manual. Both wrappers
> now repoint to `BNB-Hack-CMC` and all levers live in `.env` (one source of truth).

## Daily ops

### Status snapshot (Phase 13.C)

The single-command operator dashboard. Read-only, no orders placed.
Pulls wallet balance, open positions, the 4-pair smoke gate,
heartbeat age, and the last 5 broker-truth closes:

```bash
make status                   # pretty-printed
make status ARGS="--json"     # machine-readable
```

Sample output:

```
[Wallet]
  free USDT = $9921.41   delta vs baseline = $-2.73

[Open positions]
  (none — all flat)

[4-pair smoke gate]
  verdict = PENDING
  passed  (1): ['XRP/USDT:USDT']
  pending (3): ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

[Heartbeat]
  age = 2s   last = 2026-06-06T09:58:11+00:00

[Last 5 broker-truth closes]
  2026-06-06T04:37:30+00:00  XRP/USDT:USDT  WIN  reason=—  R=+5.019  fee=n/a
```

Heartbeat shows `⚠ STALE` when age > 5 minutes (scanner unresponsive
or crashed). The wallet baseline initialises on first
`scripts/verify_wallet_parity.py` run.

### Start the scanner (live, non-trading)
```bash
.venv/bin/python -m ictbot.orchestrator.scanner
```
Logs go to stdout (plain) and `data/logs/scanner.json.log` (structured).
Metrics on `http://localhost:9100/metrics` if `prometheus_client` is
installed (D1).

### Open the dashboard
```bash
streamlit run src/ictbot/ui/app.py
```
Visit `http://localhost:8501`. The sidebar shows the live-trading state
banner and the kill switch (C3).

### One-shot signal check via Telegram
```bash
make signal_check          # → sends a single Telegram message
make signal_check DRY=1    # → prints to stdout, no network
```
Runs `analyze_pair()` once for every configured pair (no journal write,
no dedup) and sends ONE Telegram message containing per-pair status
(BUY / SELL / NO ENTRY + blockers) plus the canonical robustness
checklist from `docs/archive/architecture_ictbot_upstream.excalidraw §4b` — the WRONG / GAP /
PARTIAL rows are what the executor still needs before live trading.

### Run a single backtest
```bash
.venv/bin/python -m ictbot.engine.backtest BTC/USDT:USDT --bars 5000
```

### Run a sweep
```bash
.venv/bin/python -m ictbot.engine.sweep --all --bars 25000 --grid rr2plus
```

### Run walk-forward optimisation
```bash
.venv/bin/python -m ictbot.engine.wfo --all --bars 50000 --grid rr2plus
```

### Gates A/B (B4)
```bash
.venv/bin/python scripts/wfo_gates_ab.py --all --bars 25000 --grid rr2plus
```

## Monitoring

- **Prometheus**: scrape `localhost:9100/metrics`. Key counters:
  `ictbot_signals_fired_total{pair,direction}`,
  `ictbot_evaluations_total{pair,outcome}`,
  `ictbot_cap_rejections_total{cap}`,
  `ictbot_live_trades_total{pair,direction}` (Phase D — only real
  broker fills, paper/shadow excluded),
  `ictbot_kill_switch_engaged` (gauge, 1=engaged, for alerting),
  `ictbot_funnel_step_failures_total{pair,step,direction}` (first
  drop-off per non-firing eval, includes the Phase E `bias_align` step).
- **Latency**: `ictbot_evaluate_latency_seconds` histogram.
- **Alerts**: rule file at [`infra/prometheus_alerts.yaml`](../infra/prometheus_alerts.yaml).
  5 rules: `ICTBotLiveTradeCapHit`, `ICTBotKillSwitchEngaged`,
  `ICTBotNoLiveFillsToday`, `ICTBotShadowDivergenceHigh`,
  `ICTBotEvaluationStalled`. Load via Prometheus `rule_files:` directive.
- **Logs**: `data/logs/scanner.json.log` is line-delimited JSON; pipe
  through `jq` or ingest via Loki/ELK.
- **Journal**: `data/journal/signals.json` is the durable BUY/SELL
  history. `score_journal()` aggregates wins/losses across restarts.
  As of `9edffb2`, ONLY the router/broker writes journal rows — the
  analyzer no longer pre-writes "signal detected" rows (they used to
  pollute `settle_open_signals` with phantom WIN/LOSS for cap-rejected
  signals that were never actually placed).

## Binance USDT-M order visibility (the SL "missing" trap)

**Symptom**: the testnet/mainnet UI's *Open Orders* tab shows only the
LIMIT TP legs of an active bracket. The STOP_MARKET SL legs appear to
be missing, and `ccxt.fetch_open_orders(pair)` returns the same
incomplete list. The position is real, the TPs are visible, but where
are the stops? It *looks* like the bot is running naked.

**Cause**: Binance Futures routes STOP_MARKET / TAKE_PROFIT_MARKET
through a separate **conditional / algo orders** queue. They have a
distinct 16-digit `algoId` namespace (e.g. `1000000097044054`), live
behind `sapiGetAlgoFuturesOpenOrders`, and never appear in the
regular `/fapi/v1/openOrders` endpoint that ccxt's `fetch_open_orders`
queries.

Worse for testnet: our broker short-circuits SAPI calls (no testnet
SAPI host exists — see `_apply_testnet_routing` in `binance_live.py`),
so even if you tried to list algo orders via ccxt's SAPI binding,
you'd get an empty list. The orders are real and triggerable — they
just aren't enumerable on testnet.

**Where to look**:

| Surface | Regular LIMIT/MARKET | Conditional STOP/TP_MARKET |
|---|---|---|
| Binance UI | "Open Orders" tab | "Stop Orders" / "Trigger Orders" tab (sometimes "Open TP/SL") |
| ccxt | `fetch_open_orders(pair)` ✓ | empty list (testnet) / mainnet via SAPI only |
| Raw fapi | `/fapi/v1/openOrders` ✓ | `/sapi/v1/algo/futures/openOrders` (mainnet only) |
| Order ID format | 8–10 digits (e.g. `209709887`) | 16 digits (e.g. `1000000097044054`) |

**Quick verification** that a placed STOP_MARKET actually landed —
read the create_order response's `info` dict:

```python
r = c.create_order(pair, 'STOP_MARKET', 'buy', qty, None,
                   {'stopPrice': sl, 'reduceOnly': True})
assert r['info']['orderType'] == 'STOP_MARKET'
assert r['info']['algoStatus'] == 'NEW'
assert r['info']['triggerPrice'] == f'{sl:.4f}'
```

If `algoStatus == 'NEW'` (or `WORKING`), the SL is live in the algo
queue regardless of what `fetch_open_orders` reports later.

**Implication for `_reconcile_from_exchange`**: the broker's close
detection uses `fetch_positions` (not `fetch_open_orders`), so it
still sees position drains correctly when an SL fires — the algo
queue invisibility doesn't break the live close path. But any manual
audit ("are my stops in place?") must NOT use `fetch_open_orders`
alone — check the UI's Stop Orders tab or trust the
`create_order` response's `info.algoStatus`.

**Recovery if SLs were actually cancelled** (manual UI cancel,
exchange maintenance, etc.) and the position is genuinely naked:

```bash
.venv/bin/python -c "
from ictbot.exec.binance_live import BinanceLiveBroker
from ictbot.settings import settings
b = BinanceLiveBroker(allowed_pairs={'PAXG/USDT:USDT'},
    testnet=settings.binance_testnet,
    api_key=settings.binance_api_key,
    api_secret=settings.binance_api_secret)
c = b._client
r = c.create_order('PAXG/USDT:USDT', 'STOP_MARKET', 'buy',
                   QTY, None, {'stopPrice': SL_PRICE, 'reduceOnly': True})
print(r['info']['algoStatus'])  # should be 'NEW'
"
```

Replace `QTY` and `SL_PRICE` with the size and trigger you want.
Side is `buy` for a SHORT position's SL, `sell` for a LONG. The
`reduceOnly` flag is mandatory — without it the order could open a
new opposite position instead of closing the existing one.

## Telegram operator commands (Phase D)

Enable with `TG_COMMANDS_MODE=true` (independent of `TG_CONFIRM_MODE`).
Requires `TG_OPERATOR_USER_ID`. DM your bot:

| Command | Action |
| ------- | ------ |
| `/whoami` | Sanity check: shows operator_id vs your id |
| `/status` | Per-pair signal card pack (same content as TG heartbeat) |
| `/journal [n]` | Last n closes (default 10, max 50) |
| `/kill <reason>` | Engage kill switch (halts evaluation, rewrites .env) |
| `/resume yes` | Strict: clears kill switch + pause. Does **NOT** flip ENABLE_LIVE_TRADING back on — that's a manual .env edit + restart |
| `/pause <minutes>` | Auto-expiring evaluation halt (file at `data/PAUSED_UNTIL`) |
| `/help` | Lists the above |

Non-operator users are silently dropped (defence in depth — even if the
bot's @handle leaks, only the configured operator can drive it).

## Walk-forward optimization (WFO) — Phase E validation

After the `ce4abaf` pagination fix, real bar counts now flow through to
the backtest. Quick BTC A/B between follow and fade modes:

```bash
.venv/bin/python -m ictbot.engine.wfo BTC/USDT:USDT --bars 10000 --quick \
    2>&1 | tee /tmp/wfo_follow.log
.venv/bin/python -m ictbot.engine.wfo BTC/USDT:USDT --bars 10000 --quick --invert \
    2>&1 | tee /tmp/wfo_fade.log
```

Decision rule (Phase E baseline):
- **TEST `total_R > 0` AND win-rate ≥ 25%** → keep current direction, deploy winner config to `.env`
- **Fade TEST positive, follow negative** → flip `STRATEGY_MODE=fade`
- **Both negative** → drop RR (lower `TP_FRAC`), rerun
- **Zero signals** → loosen one of `REQUIRE_MFVG_RETEST` / `REQUIRE_FVG_AFTER_MSS`

## Standard restart procedure

The scanner is single-process; restart is `kill + relaunch`.

```bash
# Find the running scanner
pgrep -af "ictbot.orchestrator.scanner"

# Stop it (SIGTERM is graceful — flushes Prometheus + closes PTB poll)
kill <PID>

# Wait for clean exit, force only if needed
sleep 2 && ps -p <PID> > /dev/null && kill -9 <PID>

# Relaunch in background, log to file
nohup .venv/bin/python -m ictbot.orchestrator.scanner \
    > data/logs/scanner.stdout.log 2>&1 &
echo "new pid=$!"
```

The boot banner should show:
```
ICT AI BOT PRO MAX scanner started for 5 pairs.
Prometheus /metrics on :9100 (prometheus_client available).
router using broker=<binance-live|paper> cap_gate=<5> caps
TG service on: confirm=<bool> commands=<bool> operator=<id>
```

`cap_gate=5` indicates Phase D `MaxLiveTradesPerDay` + Phase 9.B
`MaxConcurrentSameDirection` are active on the live path (was 4
pre-Phase-9). `broker=binance-live` confirms
`ENABLE_LIVE_TRADING=true` AND `kill_switch.is_engaged()==False`.

### Phase 9 restart procedure (with Phase 9 + Phase 11 + Phase 13 code)

Phase 9 adds the per-pair init + readiness gate. Phase 11 drops
PAXG. Phase 13 promotes the last two hardcoded caps to env vars.
The expected boot sequence:

```bash
# 0. Phase 15 observation-window setup (one-time): disable the
#    daily trade-count cap entirely so every conf=100 signal fires.
#    The other safety caps stay active as the wise-skip layer:
#    MAX_OPEN_POSITIONS=3 (anti-pileup), MAX_SAME_DIRECTION=2
#    (anti-correlation), DAILY_LOSS_LIMIT_R=1.0 + MAX_DRAWDOWN_FRAC=0.05
#    (account safety). The N≥30 broker-truth closes needed for
#    `make edge_check` arrive in days instead of weeks.
echo "MAX_LIVE_TRADES_PER_DAY=0" >> .env       # 0 = disabled (Phase 15)
# Revert to MAX_LIVE_TRADES_PER_DAY=3 before mainnet — the safety
# default. The other caps will continue to wisely skip pile-on
# scenarios in the meantime.

# 1. Snapshot any open positions on testnet (optional, ops sanity).
.venv/bin/python -c "from ictbot.exec.binance_live import BinanceLiveBroker; \
from ictbot.settings import settings; \
b = BinanceLiveBroker(allowed_pairs=set(settings.pairs), \
testnet=settings.binance_testnet, \
api_key=settings.binance_api_key, api_secret=settings.binance_api_secret); \
print([(p.get('symbol'), p.get('contracts')) \
for p in b._client.fetch_positions(symbols=sorted(settings.pairs)) \
if float(p.get('contracts') or 0) > 0])"

# 1b. Phase 11 pre-restart: PAXG dropped from settings.pairs after
# 429af9c+. After restart, on_reconnect no longer queries PAXG, so an
# open PAXG position would become an unmanaged orphan. Confirm flat
# explicitly (does not rely on settings.pairs):
.venv/bin/python -c "from ictbot.exec.binance_live import BinanceLiveBroker; \
from ictbot.settings import settings; \
b = BinanceLiveBroker(allowed_pairs={'PAXG/USDT:USDT'}, \
testnet=settings.binance_testnet, \
api_key=settings.binance_api_key, api_secret=settings.binance_api_secret); \
print([(p.get('symbol'), p.get('contracts')) \
for p in b._client.fetch_positions(symbols=['PAXG/USDT:USDT']) \
if float(p.get('contracts') or 0) > 0])"
# Expected: [] — empty list means PAXG is flat. If not, flatten BEFORE
# restart via: .venv/bin/python scripts/close_test_order.py PAXG/USDT:USDT

# 2. Flatten any other open position if you want a clean restart (optional).
.venv/bin/python scripts/close_test_order.py BTC/USDT:USDT

# 3. Graceful stop of the running scanner.
PID=$(pgrep -f "ictbot.orchestrator.scanner")
echo "killing $PID"
kill "$PID" && sleep 5
ps -p "$PID" > /dev/null && kill -9 "$PID"

# 4. Relaunch on Phase 9 code.
nohup .venv/bin/python -m ictbot.orchestrator.scanner \
    > data/logs/scanner.stdout.log 2>&1 &
NEW=$!
echo "new pid=$NEW"

# 5. Wait one cycle, then verify the Phase 9 boot banner.
sleep 30
grep -A 6 "pair readiness" data/logs/scanner.stdout.log | tail -8
```

Expect the readiness banner per Fix 9.E:

```
pair readiness:
  BTC/USDT:USDT  lev=5x margin=isolated ticker=$60,929.80 min_notional=$5.00 sized_qty=0.0009 OK
  ETH/USDT:USDT  lev=5x margin=isolated ticker=$1,573.20  min_notional=$5.00 sized_qty=0.013  OK
  SOL/USDT:USDT  lev=5x margin=isolated ticker=$62.57     min_notional=$5.00 sized_qty=0.08   OK
  XRP/USDT:USDT  lev=5x margin=isolated ticker=$1.09      min_notional=$5.00 sized_qty=4.6    OK
```

(Phase 11 dropped PAXG; the banner now lists 4 pairs.)

If any pair shows FAIL and `STRICT_PAIR_INIT=true`, the scanner
refuses to start (loud, exit code 1) rather than silently failing on
first signal hours later — the intended Fix 9.E behaviour.

Common FAIL triage:
- `lev=50x` (residual from prior session) → either operate the
  Binance UI to reset to 5x, or trust the next restart after current
  position closes (Fix 9.C re-asserts via `on_reconnect`).
- `margin=cross` → can't be changed via API while a position is
  open (Binance -4047); flatten first, restart.
- `sized_qty=0` → the pair-specific SL fraction is too tight at
  current `RISK_PCT_LIVE × equity`. Either widen `SL_FRAC_<TOKEN>`
  or raise `RISK_PCT_LIVE` (within `MAX_LIVE_RISK_PER_TRADE_PCT`).

Override path: `STRICT_PAIR_INIT=false` in `.env` to log-and-continue
on FAIL — not recommended for production but useful during
investigation.

### Post-restart sanity checks

After the readiness banner clears:

```bash
# Heartbeat is fresh:
cat data/logs/heartbeat.ts

# Daily smoke-gate check (Fix 9.G):
.venv/bin/python scripts/diagnose_live_pnl.py --smoke-gate

# Wallet parity baseline (Fix 5.F):
.venv/bin/python scripts/verify_wallet_parity.py
```

## Live re-engage checklist (Phase E baseline)

Use this whenever flipping `ENABLE_LIVE_TRADING=false → true`:

1. **WFO validation** (latest): run `python -m ictbot.engine.wfo
   BTC/USDT:USDT --bars 10000 --quick`. Confirm TEST half shows
   `total_R > 0` and win-rate ≥ 25%. Capture the log.
2. **.env review**: confirm `RISK_PCT_LIVE ≤ MAX_LIVE_RISK_PER_TRADE_PCT`
   (boot guard) and `TG_OPERATOR_USER_ID` is set if any TG mode is on.
3. **Caps confirmation**: tests for `MaxLiveTradesPerDay` and
   `NewsBlackoutCap` should pass: `pytest tests/test_caps.py -v`.
4. **Flip the flag**: edit `.env`, set `ENABLE_LIVE_TRADING=true`.
5. **Restart** per the procedure above.
6. **Verify**: boot banner shows `broker=binance-live cap_gate=4 caps`;
   `curl localhost:9100/metrics | grep ictbot_kill_switch_engaged`
   shows `0`; first SIGNAL log line should produce a `PLACED ...` line
   within 30s (or a `live gate refused: ...` if Binance rejects).

If something feels off after the first fill: `/kill investigating`
from your Telegram (engages kill switch instantly, halts evaluation).

## Incident response

### Scanner crashed
- Check `data/logs/scanner.log` for the latest exception.
- Common causes:
  - Bybit rate limit (F1 cooldown should retry once; persistent
    throttle raises after the second attempt).
  - Disk full (journal/parquet writes will fail).
- Restart: `python -m ictbot.orchestrator.scanner`. The cache means
  no data is lost.

### Exchange disconnected
- `BybitExchange.fetch_ohlcv` raises after the single F1 retry. The
  scanner's outer try/except logs and sleeps 10s. Sustained outage:
  stop the scanner, investigate Bybit status, restart.

### Runaway losses

**Fastest path** (Phase D): DM `/kill <reason>` to your Telegram bot
(requires `TG_COMMANDS_MODE=true`). Same effect as the dashboard button:
creates `data/KILL_SWITCH_ENGAGED`, rewrites `.env` to
`ENABLE_LIVE_TRADING=false`, scanner halts evaluation on next tick.

**Manual fallback** (no TG):
```bash
touch data/KILL_SWITCH_ENGAGED   # scanner halts on next tick
# Or, more thorough:
.venv/bin/python -c "from ictbot.runtime import kill_switch; kill_switch.engage('manual')"
```

Then:
1. Manually cancel any open positions through the exchange UI.
   - Binance testnet: https://testnet.binancefuture.com → Positions tab.
   - There's also `scripts/close_test_order.py` for a fast
     reduce-only flatten on Binance testnet.
2. Read the journal + signal logs to understand what fired:
   ```bash
   .venv/bin/python -m ictbot.cli.journal_cmd --limit 20
   ```
3. After diagnosis, resume with `/resume yes` from TG (clears kill
   switch + pause; **does NOT** flip ENABLE_LIVE_TRADING back on —
   that's a deliberate manual step).

### Suspected bad config flip
Roll back the working tree to the last known-good commit:
```bash
git log --oneline -n 20
git checkout <good-sha> -- src/ictbot/settings.py
```
Re-run tests, restart the scanner.

## Rollback procedures

### Code rollback
```bash
git revert <bad-sha>
# or for the whole branch
git checkout main
git reset --hard origin/main   # destructive — be sure
```

### Journal rollback
Journals are append-only JSON arrays. Restore from a backup:
```bash
cp data/journal/signals.json.bak data/journal/signals.json
```
Make a backup before bulk operations:
```bash
cp data/journal/signals.json data/journal/signals.json.bak.$(date +%s)
```

### Cache rebuild
Cache is gitignored and reproducible:
```bash
rm -rf data/cache
python -c "from ictbot.data.bybit import BybitExchange; b=BybitExchange(); b.fetch_ohlcv('BTC/USDT:USDT','1m',5000)"
```
Subsequent fetches re-warm the cache.

## Live-trading checklist (ADR 0005 + Phase D/E gates)

Before flipping `ENABLE_LIVE_TRADING=true`:

- [ ] WFO walk-forward TEST half: `total_R > 0`, `win_rate ≥ 25%`,
      `n_signals ≥ 15` (Phase E thresholds; see §"Walk-forward
      optimization" above).
- [ ] On the same WFO, fade A/B (`--invert`) confirms current direction
      is correct (fade TEST should be worse, otherwise flip
      `STRATEGY_MODE=fade`).
- [ ] `.env` knobs locked: `SL_FRAC`, `TP_FRAC`, `BIAS_ENGINE`,
      `REQUIRE_BIAS_ALIGNMENT` reflect the WFO winner.
- [ ] `RISK_PCT_LIVE ≤ MAX_LIVE_RISK_PER_TRADE_PCT` (boot guard will
      refuse otherwise).
- [ ] `MAX_LIVE_TRADES_PER_DAY` set (default 3) — verifies the cap
      stack at boot reports `cap_gate=4 caps`.
- [ ] `LIVE_ALLOWED_PAIRS` in `.env` lists ONLY the pair you intend to
      trade (start with one).
- [ ] `CapGate` has `MaxOpenPositions(1)`, `DailyLossLimit(1.0R)`,
      `MaxDrawdown(0.05)`, `MaxLiveTradesPerDay(N)`.
- [ ] `TG_COMMANDS_MODE=true` with `TG_OPERATOR_USER_ID` set, so you
      can `/kill` from your phone within seconds.
- [ ] Phase D `prometheus_alerts.yaml` loaded in your Prometheus +
      `ICTBotKillSwitchEngaged` routed to a channel you watch.
- [ ] First 24h after flip: monitor `ictbot_live_trades_total` (must
      tick up at all), forward win rate (must trend toward the WFO TEST
      number), and the journal for any LOSS streak ≥ 3.

Anything less and you are at odds with this runbook.

## TG visibility (Phase 5 Tier 2)

Three real-time TG channels were added so the operator never has to
poll for state.

### Close notifications (Fix 5.C)

Every live close fires a one-line TG message after the journal mirror
write. Fires on `is_live=True` routers only; paper backtests stay
silent.

Format:
```
CLOSE  XRP/USDT:USDT  SELL  reason=TP
entry=1.0857  exit=1.0586  qty=916.6
R=+5.019 fees=$0.0500
```

When the close was on a `reconciled stub` (Order rebuilt by
`on_reconnect` rather than placed via the live bracket), the message
is prefixed `[reconciled stub]` so you know the R is approximate.

Env:
- `TG_NOTIFY_ON_CLOSE` — default `true`. Set `false` to silence (e.g.
  during high-volume backfills or paper-only sessions).

### Emergency-flatten alert (Fix 5.D)

When `BinanceLiveBroker._emergency_flatten` itself raises (the bracket
SL/TP placement failed AND the reduce-only flatten couldn't get out),
a `[BOT EMERGENCY]` TG message fires before the exception re-raises.
This always fires regardless of `TG_NOTIFY_ON_CLOSE` — it's a safety
alert, not a notification preference.

Format:
```
[BOT EMERGENCY] flatten failed pair=PAXG/USDT:USDT qty=0.184 side=buy err=...
Position may be unhedged — manual intervention required.
```

Acknowledge by checking the Binance UI for residual positions and
flatten manually via `python scripts/close_test_order.py <PAIR>`.

### Throttled rejection summary (Fix 5.E)

Cap rejections accumulate in the journal but don't fire TG by default.
For early-validation visibility, set:

- `TG_NOTIFY_REJECTIONS_EVERY=N` — sends a one-line TG summary every
  Nth rejection per `(pair, reason)`. 0 = off (default).

In-memory counter per process; resets on restart. Useful in early
validation to confirm caps are firing without firehosing.

## Wallet-vs-journal parity (Phase 5 Tier 3 — Fix 5.F)

The acceptance criterion from the original autotrade plan: "Diagnostic
implied USDT P&L matches the testnet wallet's `fetch_balance` change
within fee precision."

```bash
.venv/bin/python scripts/verify_wallet_parity.py
```

First run initialises a baseline file at
`data/wallet_baseline_usdt.txt` with the current wallet balance and
exits 0. Re-run after each close to confirm parity.

```bash
# Re-set the baseline (e.g. after a manual deposit/withdrawal)
.venv/bin/python scripts/verify_wallet_parity.py --rebase

# Custom tolerance / cutoff
.venv/bin/python scripts/verify_wallet_parity.py --tolerance 1.0 --since 2026-06-06
```

Exit codes:
- `0` — parity OK (or baseline initialised)
- `1` — drift exceeds tolerance (`|wallet_delta - journal_usdt| > tolerance`)
- `2` — infra error (no journal, wallet fetch failed, …)

Suitable for a CI cron once parity has been stable for ≥ 24h.

## Phase 3 Layer 2 acceptance gate (Fix 2.J + 6.B)

```bash
.venv/bin/python scripts/diagnose_live_pnl.py --json | jq '.acceptance'
```

`true` iff:
1. At least 1 row classifies as `broker-truth` or `broker-truth-no-fee`.
2. Zero rows classify as `synthetic-live-bug`.

Classifier buckets:
| Bucket | Meaning |
|---|---|
| `broker-truth` | `pnl_r` populated AND `fees_paid` populated AND broker is non-paper. Phase 2 + 5 + 6 working end-to-end. |
| `broker-truth-no-fee` | `pnl_r` populated, broker live, fees missing. Legacy `fetch_order` path took the close (no fee extraction). |
| `synthetic-paper` | No `pnl_r`, `closed_price` bit-for-bit on tp/sl, broker is paper. Normal paper-broker shape. |
| `synthetic-live-bug` | No `pnl_r`, `closed_price` bit-for-bit on tp/sl, broker is live. **The regression Fix 2.B prevents** — must never recur on new live rows. |

The human report flags any `synthetic-live-bug` count with a
`⚠ FIX-2.B REGRESSION` warning.

## On_reconnect semantics (Fix 2.I + 5.B)

When the scanner is restarted while a position is already open on the
exchange, `BinanceLiveBroker.on_reconnect()` runs once during
`_build_router`. Behaviour:

1. `fetch_positions(symbols=allowed_pairs)` recovers `entryPrice` and
   `contracts` for each non-zero position.
2. `fetch_open_orders()` is scanned for `STOP_MARKET` (→ SL price) and
   `LIMIT reduceOnly` (→ TP price) so the rebuilt Order has the
   actual bracket.
3. If `fetch_open_orders` yields nothing (typical on Binance testnet
   where the algo queue is SAPI-only), falls back to
   `entry × (1 ± SL_FRAC)` / `entry × (1 ± TP_FRAC)`.
4. `Order.is_reconciled = True` is stamped so the close notification
   (Fix 5.C) is prefixed `[reconciled stub]`.

Position cap (`MaxOpenPositions`) now correctly counts pre-existing
positions on restart — no more orphan-doubling.

## Boot guards (Fix 5.I + Phase 2 Fix 2.D)

The scanner refuses to start at import time when any of the following
hold (the failure is a `RuntimeError` printed on stderr, exit code 1):

| Condition | Error message |
|---|---|
| `ENABLE_LIVE_TRADING=true` AND `RISK_PCT_LIVE > MAX_LIVE_RISK_PER_TRADE_PCT` | `RISK_PCT_LIVE (…) exceeds MAX_LIVE_RISK_PER_TRADE_PCT (…); refusing to boot.` |
| `ENABLE_LIVE_TRADING=true` AND venue API key OR secret empty | `ENABLE_LIVE_TRADING=true with EXCHANGE=… but BINANCE_API_KEY or BINANCE_API_SECRET is empty in .env.` (per-venue) |
| `TG_CONFIRM_MODE=true` AND `TG_OPERATOR_USER_ID=0` | `TG_CONFIRM_MODE=true requires TG_OPERATOR_USER_ID to be set …` |
| `TG_COMMANDS_MODE=true` AND `TG_OPERATOR_USER_ID=0` | Same shape, for the commands path. |

To fix: edit `.env`, lower `RISK_PCT_LIVE`, populate the missing
credential, or unset the TG flag. The guard runs in the test suite too
([tests/test_settings_boot_guards.py](../tests/test_settings_boot_guards.py))
via subprocess so the message format is regression-checked.

## Journal schema (Phase 2 Fix 2.A + 2.F + 5.B)

`data/journal/signals.json` is a JSON list of dicts. Schema as of
2026-06-06:

```json
{
  "ts": "2026-06-06T04:01:16.123456+00:00",
  "pair": "XRP/USDT:USDT",
  "entry": "SELL",
  "price": 1.0857,
  "sl": 1.0911,
  "tp": 1.0586,
  "rr": 5.0,
  "confidence": 100,
  "outcome": "WIN",
  "closed_ts": "2026-06-06T04:36:31.123Z",
  "closed_price": 1.0586,
  "broker": "binance-live",
  "pnl_r": 5.018518518518682,
  "entry_fill_price": 1.0857,
  "fees_paid": null
}
```

Field semantics (post-Phase-6):

| Field | Source | Notes |
|---|---|---|
| `ts` | router's `_journal_placed` at signal placement | UTC ISO-8601 with timezone offset |
| `pair`, `entry`, `price`, `sl`, `tp`, `rr`, `confidence` | strategy result dict | `price`/`sl`/`tp` are the **strategy's** pre-fill computed values; the broker may re-anchor per Fix 2.E (see `entry_fill_price`) |
| `outcome` | `mark_closed_from_broker` on close | `OPEN` while position is live; `WIN`/`LOSS`/`BE`/`CLOSED` after close. `BE` is the MANUAL fallback. |
| `closed_ts`, `closed_price` | `mark_closed_from_broker` | The broker's authoritative close timestamp + price. **Not** bit-for-bit equal to `tp`/`sl` for natural STOP_MARKET fills (drift from spread); IS bit-for-bit for LIMIT TP fills (limit price by definition). |
| `broker` (Fix 2.A) | router's `_journal_placed` | `"paper"` for `PaperBroker`, `"binance-live"` for `BinanceLiveBroker`, etc. Defaults to `"paper"` if missing (backwards-compat for pre-Fix-2.A rows). Drives the `settle_open_signals` gate (Fix 2.B). |
| `pnl_r` (Fix 2.F) | `Order.realised_pnl_R()` at close | Fee-inclusive R when `fees_paid` is set; gross R when None. |
| `entry_fill_price` (Fix 2.E + 2.F) | `Order.entry` at close | The broker-captured actual fill avg from ccxt `order["average"]`, possibly different from `price` if there was slippage. |
| `fees_paid` (Fix 2.F) | `_fee_from_info` over entry + close legs | USDT-denominated round-trip fee. None when the close path couldn't extract them (legacy `fetch_order` fallback). |

REJECTED rows use the same shape with `entry = "REJECTED (cap_name (…) reached …)"`.

The journal is the **single source of truth** for closed trades. The
broker writes via `mark_closed_from_broker`; the synthetic
`settle_open_signals` only touches rows with `broker == "paper"` per
the Fix 2.B gate.

---

## Phase 9 — Per-token completeness

The 4 configured pairs (BTC, ETH, SOL, XRP) now go through the same
hardened path. (Phase 9 originally shipped for 5 pairs; Phase 11
dropped PAXG after its `no edge` WFO verdict.) Summary:

### Per-pair SL/TP (Fix 9.A)

Each pair can carry its own `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` env
override. Defaults are `None` → fall back to the global `SL_FRAC` /
`TP_FRAC`. Use to tune for per-pair volatility regime.

Per-pair WFO driver writes the winning `(sl_frac, tp_frac)` per pair:

```bash
make wfo_per_pair ARGS="--bars 10000 --grid rr2plus"   # Phase 12.C convenience
# or directly: python3 scripts/wfo_per_pair.py --bars 10000 --grid rr2plus
# Writes data/wfo/per_pair_<UTC-date>.json
```

Promote winners into `.env` once validated end-to-end:

```bash
SL_FRAC_BTC=0.003   TP_FRAC_BTC=0.025   # small sample (TEST +0.09R)
SL_FRAC_ETH=0.003   TP_FRAC_ETH=0.015   # ✅ holds (TEST +0.45R)
SL_FRAC_SOL=0.003   TP_FRAC_SOL=0.015   # ✅ holds (TEST +0.80R)
SL_FRAC_XRP=0.008   TP_FRAC_XRP=0.025   # small sample (TEST +0.88R)
# See data/wfo/per_pair_<date>.json for the full scoreboard.
```

### Per-pair POI tolerance (Fix 12.A)

Phase 9.A's WFO scoreboard also exposed a 7× spread in the winning POI
tap tolerance across pairs (BTC 0.0015 → SOL 0.01). Phase 12.A adds
per-pair `POI_TAP_TOLERANCE_<TOKEN>` env overrides with the same
fall-back-to-global semantics as `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>`.

Promote winners into `.env`:

```bash
POI_TAP_TOLERANCE_BTC=0.0015     # WFO winning POI tol
POI_TAP_TOLERANCE_ETH=0.005      # WFO winning POI tol
POI_TAP_TOLERANCE_SOL=0.01       # WFO winning POI tol — 2× looser
POI_TAP_TOLERANCE_XRP=0.003      # WFO winning POI tol
```

Helper: `settings.get_poi_tap_tolerance(pair)`. Default `None` → global
`POI_TAP_TOLERANCE=0.005`. Unknown pair → global.

### Anti-correlation cap (Fix 9.B)

`MAX_OPEN_POSITIONS` default raised `1 → 3`. Paired with
`MAX_SAME_DIRECTION` (default 2): prevents 3 SELLs or 3 BUYs stacking
on correlated crypto pairs. Set `MAX_SAME_DIRECTION=0` to disable.

### Per-pair init (Fix 9.C)

On boot AND `on_reconnect`, the broker sets `ISOLATED` margin +
leverage 5 per pair, then reads back via `fetch_positions`. Refuses
to boot if either mismatches the requested value (gated by
`STRICT_PAIR_INIT`, default `true`). Mismatch checks are auto-deferred
when Binance returns `-4047` ("cannot change while position open") —
the next restart re-asserts after the position closes.

### Precision normalization (Fix 9.D)

Every `qty` / `stopPrice` / TP price goes through ccxt's
`amount_to_precision` / `price_to_precision` before reaching
`create_order`. Normalized values are stamped back onto the `Order`
so the journal matches what Binance acted on.

### Boot readiness gate (Fix 9.E)

`verify_all_pairs_ready()` runs after `on_reconnect` and prints a
per-pair banner:

```
pair readiness:
  BTC/USDT:USDT  lev=5x margin=isolated ticker=$70,234.10 min_notional=$5.00 sized_qty=0.001 OK
  ETH/USDT:USDT  lev=5x margin=isolated ticker=$3,180.50  min_notional=$5.00 sized_qty=0.002 OK
  SOL/USDT:USDT  lev=5x margin=isolated ticker=$62.57     min_notional=$5.00 sized_qty=0.08  OK
  XRP/USDT:USDT  lev=5x margin=isolated ticker=$1.09      min_notional=$5.00 sized_qty=4.6   OK
```

Refuses to start under strict mode if any pair fails (leverage /
margin mismatch, no ticker, or qty floors below `min_notional`).

Operator convenience: `make pair_readiness` runs the same check
out-of-scanner so you can verify pre-restart without killing the
running scanner. Useful when triaging a FAIL banner before risking
a restart.

### Live smoke test (Fix 9.F)

Round-trip every pair on testnet to verify plumbing pre-restart:

```bash
make smoke_pairs                                  # Phase 12.C convenience
make smoke_pairs ARGS="--pair BTC/USDT:USDT"      # single pair
make smoke_pairs ARGS="--dry-run"                 # no orders
# or directly: python3 scripts/smoke_test_pairs.py [--pair … | --dry-run]
```

Refuses unless `BINANCE_TESTNET=true`. Writes
`data/smoke_pairs_<UTC-date>.json` with per-pair status + latency.

### 4-pair smoke gate (Fix 9.G, Phase 11 scope)

Every configured pair needs ≥ 1 broker-truth close to be
operationally proven. PAXG was dropped in Phase 11; its historical
rows in `signals.json` are silently ignored by the classifier.

```bash
make smoke_gate                                  # Phase 12.C convenience
# or directly: python3 scripts/diagnose_live_pnl.py --smoke-gate
# 4-pair smoke gate: PENDING
#   passed  (1): ['XRP/USDT:USDT']
#   pending (3): ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']
```

Exit 0 when all pairs pass, 1 when any pending. JSON via
`--json --smoke-gate` for CI. Mainnet promotion (Tier 5 deferred)
waits until `smoke_gate_pass: true`.

---

## Phase 14 — Edge reality check

A short read-only audit pattern operators can run any time to ask
"is the live distribution consistent with the WFO model, or am I
fooling myself with a small sample?"

### One-command check

```bash
make edge_check                            # pretty-printed
make edge_check ARGS="--json"              # machine-readable
make edge_check ARGS="--min-n 20"          # lower the significance bar
make edge_check ARGS="--wfo path/to.json"  # custom WFO baseline
```

`scripts/edge_check.py` (Phase 14.D) reads `data/journal/signals.json`,
filters to broker-truth closes, and per pair reports:

- **n** — sample size
- **mean R** — realised expectancy
- **std R** — sample standard deviation
- **sum R** — cumulative R
- **WFO TEST** — comparison baseline from Phase 9.A scoreboard
  (hardcoded fallback; override with `--wfo path/to.json`)
- **t vs 0** — one-sample t-statistic against the null "no edge"
- **p vs 0** — two-sided p-value, normal-approximation (only shown
  when n ≥ min_n; below that, CLT hasn't kicked in)

Per-pair verdict, then an overall aggregate.

Exit codes (suitable for CI):
- `0` — at least one pair has confirmed real edge
- `1` — pending more data (no pair has crossed the bar yet)
- `2` — zero broker-truth closes (pre-restart / infra issue)

### Interpreting the numbers

| Signal | What it means |
|---|---|
| `n < 10` per pair | Insufficient sample; whatever the mean R shows is luck |
| `n ≥ 10, mean R ≥ +0.5` | Possible edge; widen the sample to be sure |
| `n ≥ 30, mean R ≥ +0.5` | Real edge confirmed for this pair |
| `n ≥ 30, mean R ≈ 0` | No edge; WFO winner was curve-fit |
| `n ≥ 30, mean R < 0` | Contradicts WFO; investigate the live data |

### Phase E WFO model baseline

| Pair | TEST expectancy | TEST W/L | Verdict |
|---|---|---|---|
| SOL | +0.80R | 17/28 | ✅ holds |
| ETH | +0.45R | 8/17 | ✅ holds |
| XRP | +0.88R | 4/4 | small sample |
| BTC | +0.09R | 1/5 | small sample |

(Source: `data/wfo/per_pair_2026-06-06.json`)

If live data after N≥30 per pair drifts more than ~1R from these
TEST expectancies, the gap signals either market-regime change or
WFO overfit. Re-run `make wfo_per_pair ARGS="--bars 30000 --grid
rr2plus"` against fresher data and compare.

### Why the morning-XRP TP doesn't tell you anything yet

A single +5R win is what the model predicts will happen ~38.9% of
the time at 1:5 RR — observing one early is consistent with edge,
and consistent with luck. With N=1 you cannot distinguish them.

The fastest path to an answer: set `MAX_LIVE_TRADES_PER_DAY=0` (Phase 15
testing-phase trust mode), restart on Phase 13 code, watch ~3-4 days,
then run `make edge_check`.

---

## Phase 16 — Daily session-bucketed report

The user's ICT prior: edge concentrates in London (07–15 UTC in BST,
08–16 UTC in GMT) and New York (12–21 UTC in EDT) killzones. The
session report tests that prior every day.

```bash
make session_report                              # today UTC
make session_report ARGS="--date 2026-06-07"     # specific UTC day
make session_report ARGS="--no-write"            # stdout only
make session_report ARGS="--out /tmp/x.md"       # custom path
```

Writes `data/reports/session_<UTC-date>.md` with:
- **Top-line bucket table**: IN_SESSION (London+NY) vs OFF_SESSION
  (Tokyo+off-hours) vs OVERALL — n, mean R, sum R, win rate, t-stat
  vs 0
- **In-vs-off comparison**: Welch's t with verdict
  (`IN_SESSION edge LIKELY` / `inconclusive` / `OFF_SESSION winning —
  hypothesis CONTRADICTED`)
- **Per-pair × bucket** breakdown
- **Trade-by-trade** log of broker-truth closes
- **Cap-rejection breakdown** by session bucket
- **Decision-quality note** at the bottom: KEEP project / KEEP +
  KILLZONE_REQUIRED / DROP, based on Phase 14.D thresholds (n ≥ 30,
  |t| > 2)

### How session attribution works

Fix 16.A: new journal rows persist `active_session` at signal-fire
time. Legacy rows (pre-Fix-16.A) fall back to reconstruction via
`runtime.sessions.get_sessions(at=row['ts'])`. Both paths produce the
same output today; going forward the stored field is authoritative
(no DST drift if session boundaries ever change).

### Operator workflow

Each morning: open `data/reports/session_<yesterday>.md`. Review the
verdict line. After ~3-4 days at `MAX_LIVE_TRADES_PER_DAY=0`, the
sample crosses N=30 and the decision-quality note becomes definitive.

## Debug & one-off utilities (scripts/ — not wired to any Makefile target)

Operator-facing tools kept for verification and recovery; none are required by the
runtime. (Audit M2: `fire_test_order.py` / `close_test_order.py` were legacy
CEX-perp helpers and have been deleted — older runbook sections in this file that
still reference `close_test_order.py` predate the deletion; flatten manually via the
exchange UI instead.)

| Script | Purpose |
|---|---|
| `scripts/probe_cmc.py` | Ad-hoc probe of the CMC Pro API (quota, endpoints, latency). |
| `scripts/probe_agent_hub.py` | Ad-hoc probe of the CMC Agent Hub MCP + x402 endpoints. |
| `scripts/verify_wallet_parity.py` | Journal-implied P&L vs exchange wallet balance drift check (legacy CEX path). |
| `scripts/wfo_gates_ab.py` | One-off WFO gates A/B comparison (research). |
| `scripts/archive_journal.py` | Rotate `data/journal/signals.json` to start a clean acceptance window (legacy CEX path). |
| `scripts/gen_architecture.py` | Regenerates `docs/architecture.{excalidraw,svg,png}` (the momentum-agent diagram). |
| `scripts/check_env_example.py` | Audit M1 acceptance: every Settings field is named in `.env.example` (`missing: 0`). |
| `scripts/tg_send_test.sh` / `tg_test_signal.sh` | Legacy Telegram debug helpers (CEX path): raw send + synthetic signal card. |
