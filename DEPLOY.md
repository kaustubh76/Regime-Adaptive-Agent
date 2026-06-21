# Deploy on Render (free tier)

> ⚠️ **This is the LEGACY ICT-scanner deploy guide** (the Delta/Binance signal
> bot). The BNB Hack × CMC **dashboard** has its own fresh, self-contained
> blueprint — see **[docs/deploy_dashboard.md](docs/deploy_dashboard.md)**.
> The repo's `render.yaml` now deploys the **dashboard** (`bnb-mission-control`),
> not the scanner; this document is kept only for the scanner image at
> `./Dockerfile`. Don't mix the two.

This deploys the scanner as a Render **Web Service** on the free plan.
The free plan does not include Background Workers, so the scanner has
to look like a web app — it now binds `$PORT` and serves `/health` so
Render is happy. An external pinger (UptimeRobot) hits `/health` every
10 minutes to keep the instance from sleeping after 15 min of idle.

If you ever decide $7/mo is fine, upgrade to a Background Worker; the
pinger becomes unnecessary and the cold-start risk goes away. See
"Upgrade path" at the bottom.

---

## What you need

- A GitHub account with this repo pushed to it.
- A free Render account (https://render.com).
- A free UptimeRobot account (https://uptimerobot.com).
- Your `.env` values handy: at minimum `TELEGRAM_TOKEN`,
  `TELEGRAM_CHAT_ID`, plus the venue creds for whichever exchange
  you set via `EXCHANGE`:
    - `EXCHANGE=binance` → `BINANCE_API_KEY` + `BINANCE_API_SECRET`
      (+ `BINANCE_TESTNET=true` to point at
      `testnet.binancefuture.com`)
    - `EXCHANGE=delta` → `DELTA_API_KEY` + `DELTA_API_SECRET`
      (mainnet only — no testnet)
  The Fix 5.I boot guard refuses to start when
  `ENABLE_LIVE_TRADING=true` and either the API key OR the secret
  for the active venue is empty.

---

## Step 1 — Push the repo to GitHub

If the repo isn't on GitHub yet:

```bash
# from /Users/apple/Desktop/Rahul_ideation
gh repo create ictbot --private --source=. --remote=origin --push
```

If it's already there, just push the new deploy files:

```bash
git add render.yaml .dockerignore src/ictbot/runtime/health_server.py \
        src/ictbot/orchestrator/scanner.py DEPLOY.md
git commit -m "deploy: Render free-tier Web Service + /health endpoint"
git push
```

`.env` is git-ignored on purpose — you'll enter secrets in the Render
dashboard, never commit them.

---

## Step 2 — Create the Render service

1. Sign in at https://dashboard.render.com.
2. **New +** → **Web Service** → **Build and deploy from a Git repository**.
3. Connect your GitHub account and pick this repo.
4. Render will detect `render.yaml`. Confirm:
   - **Name**: `ictbot-scanner`
   - **Region**: pick **Singapore** (closest to Delta Exchange — APAC).
   - **Branch**: `main` (or whichever branch you push to).
   - **Plan**: **Free**.
   - **Runtime**: Docker.
5. Click **Apply**.

The first build will take 3–5 minutes (compiles ccxt + numpy).

---

## Step 3 — Set the secrets

In the service → **Environment** tab, add the minimum:

| Key | Value |
|---|---|
| `TELEGRAM_TOKEN` | your bot token |
| `TELEGRAM_CHAT_ID` | your chat id |
| `EXCHANGE` | one of `binance` / `delta` |
| `<EXCHANGE>_API_KEY` / `_API_SECRET` | venue creds for the chosen exchange |

For testnet validation also set `BINANCE_TESTNET=true`.

For live execution (after testnet acceptance gate passes), add:

| Key | Default | Notes |
|---|---|---|
| `ENABLE_LIVE_TRADING` | `false` | Master switch. Boot guards (Fix 5.I) refuse if creds are missing. |
| `RISK_PCT_LIVE` | `0.0005` | Per-trade risk as fraction of equity. Fix 2.D guarantees this is used whenever `is_live=True`, regardless of `SHADOW_MODE`. |
| `MAX_LIVE_RISK_PER_TRADE_PCT` | `0.001` | Hard ceiling; boot refuses if `RISK_PCT_LIVE` exceeds. |
| `MAX_OPEN_POSITIONS` | `3` | Fix 5.H + Phase 9.B: raised from 1 → 3 so 3 of 5 pairs can hold positions concurrently. |
| `MAX_SAME_DIRECTION` | `2` | **Phase 9.B**: anti-correlation cap. At most 2 BUYs or 2 SELLs concurrent. Set 0 to disable. |
| `DAILY_LOSS_LIMIT_R` | `1.0` | **Phase 13.A**: cumulative loss in R-multiples that `DailyLossLimit` enforces per UTC day. Boot guard refuses if ≤ 0 (no cap is a misconfiguration). |
| `MAX_DRAWDOWN_FRAC` | `0.05` | **Phase 13.B**: peak-to-trough drawdown ceiling that `MaxDrawdown` enforces. Boot guard refuses outside `(0, 1)` (0 = no cap; ≥ 1 = nonsensical). |
| `STRICT_PAIR_INIT` | `true` | **Phase 9.C / 9.E**: refuse boot if any pair's leverage or margin mode mismatches requested values, or `verify_pair_readiness` fails. Auto-defers when Binance returns -4047 ("can't change while position open"). |
| `MAX_LIVE_TRADES_PER_DAY` | `3` | Daily cap on bracket placements; reads UTC-stamped count from `signals.json`. **Phase 15**: set to `0` (or any value ≤ 0) to disable the cap during the testing-phase observation window. Other safety caps stay active. |
| `SL_FRAC` / `TP_FRAC` | `0.005` / `0.025` | **Global fallback** bracket fractions (Phase E WFO winner is 0.005 / 0.025 = 1:5 RR). Per-pair overrides ship in Phase 9.A. |
| `SL_FRAC_<TOKEN>` / `TP_FRAC_<TOKEN>` | _unset_ | **Phase 9.A** per-pair override. `<TOKEN>` ∈ {`BTC`, `ETH`, `SOL`, `XRP`} (Phase 11 dropped `PAXG` after its `no edge` WFO verdict). Unset → fall back to global `SL_FRAC`/`TP_FRAC`. Operator promotes WFO winners from `data/wfo/per_pair_<date>.json` here. |
| `POI_TAP_TOLERANCE_<TOKEN>` | _unset_ | **Phase 12.A** per-pair POI tap tolerance override. Same fall-back-to-global semantics as `SL_FRAC_<TOKEN>`. Phase 9.A WFO showed a 7× spread (BTC 0.0015 → SOL 0.01). |
| `BIAS_ENGINE` | `swing` | `swing` (spec) / `sma` / `slope`. WFO winner: `slope`. |
| `REQUIRE_BIAS_ALIGNMENT` | `true` | Phase E gate: `htf_bias == ltf_bias` required. |
| `RE_ANCHOR_BRACKET` | `true` | Fix 2.E: shift SL/TP by `(actual_avg - strategy_entry)` after market entry fills, preserving intended risk distance. |
| `MAX_ENTRY_SLIPPAGE_BPS` | `30` | Fix 2.E: emergency-flatten + journal `REJECTED (slippage_exceeded)` when unfavourable slip exceeds the bound. |
| `TG_NOTIFY_ON_CLOSE` | `true` | Fix 5.C: TG one-liner on every live close. |
| `TG_NOTIFY_REJECTIONS_EVERY` | `0` | Fix 5.E: throttled summary every Nth rejection per `(pair, reason)`. 0 = silent. |
| `TG_COMMANDS_MODE` | `true` | Operator can `/kill`, `/pause`, `/status`, `/journal` from their phone. |
| `TG_OPERATOR_USER_ID` | _your numeric Telegram id_ | Required when `TG_CONFIRM_MODE` or `TG_COMMANDS_MODE` is on. |
| `SHADOW_MODE` | `false` | Phase B shadow router. Independent of `RISK_PCT_LIVE` wiring after Fix 2.D. |

The non-secret defaults already live in `render.yaml`. Override them
in this tab if you need to.

### Boot guard refusal modes (Fix 5.I, Phase 2 Fix 2.D, Phase 9.C / 9.E)

The scanner refuses to start at import time when any of these hold
(error printed to stderr, exit code 1):

- `ENABLE_LIVE_TRADING=true` AND `RISK_PCT_LIVE > MAX_LIVE_RISK_PER_TRADE_PCT`
- `ENABLE_LIVE_TRADING=true` AND the active venue's API key OR
  secret is empty
- `TG_CONFIRM_MODE=true` AND `TG_OPERATOR_USER_ID=0`
- `TG_COMMANDS_MODE=true` AND `TG_OPERATOR_USER_ID=0`
- **`STRICT_PAIR_INIT=true`** AND any pair's leverage (post-
  `set_leverage`) ≠ `5` per `fetch_positions` read-back (Fix 9.C)
- **`STRICT_PAIR_INIT=true`** AND any pair's margin mode (post-
  `set_margin_mode`) ≠ `isolated` per `fetch_positions` read-back
  (Fix 9.C). **Auto-deferred** when Binance returns `-4047` ("can't
  change while position open") so a held position doesn't block
  restart.
- **`STRICT_PAIR_INIT=true`** AND `verify_pair_readiness` reports
  any pair as not ok (no leverage / no margin / no ticker / sized
  notional below `min_notional`) (Fix 9.E)
- **`DAILY_LOSS_LIMIT_R ≤ 0`** — zero or negative means the cap is
  effectively disabled, which is almost always a misconfiguration
  (Fix 13.A)
- **`MAX_DRAWDOWN_FRAC` outside `(0, 1)`** — 0 disables the cap;
  ≥ 1.0 (100 % drawdown allowed) is nonsensical (Fix 13.B)

If Render shows the service failing immediately after a deploy, check
the **Events** tab — the `RuntimeError` message names the missing
variable or failed pair.

### Phase 9 boot banner

With `ENABLE_LIVE_TRADING=true` + venue creds, after `on_reconnect`
the scanner prints a per-pair readiness banner:

```
pair readiness:
  BTC/USDT:USDT  lev=5x margin=isolated ticker=$60,929.80 min_notional=$5.00  sized_qty=0.0009 OK
  ETH/USDT:USDT  lev=5x margin=isolated ticker=$1,573.20  min_notional=$5.00  sized_qty=0.013  OK
  SOL/USDT:USDT  lev=5x margin=isolated ticker=$62.57     min_notional=$5.00  sized_qty=0.08   OK
  XRP/USDT:USDT  lev=5x margin=isolated ticker=$1.09      min_notional=$5.00  sized_qty=4.6    OK
```

(Phase 11 dropped `PAXG/USDT:USDT` — banner now shows 4 pairs.)

Every pair must report `OK` under `STRICT_PAIR_INIT=true`, otherwise
the scanner refuses to start. Common failures:
- `lev=50x` (residual from prior session) → set leverage manually
  in the Binance UI or wait for `_ensure_pair_init` to re-assert.
- `margin=cross` → set margin mode to isolated in UI (can't be
  changed by API while a position is open).
- `sized_qty=?` or `sized_qty=0` → the pair-specific SL fraction
  is too tight at current `RISK_PCT_LIVE × equity`; either raise
  `RISK_PCT_LIVE` (within ceiling) or set `SL_FRAC_<TOKEN>` wider.

Override: set `STRICT_PAIR_INIT=false` to log-and-continue on
failures (not recommended for production).

Hit **Save Changes**. Render will redeploy with the secrets injected.

---

## Step 4 — Verify the service is live

In the Render service page, copy the URL — it looks like
`https://ictbot-scanner.onrender.com`.

```bash
curl https://ictbot-scanner.onrender.com/health
# → ok heartbeat_age_s=12.3
```

Also check the **Logs** tab. For paper trading you should see:

```
ICT AI BOT PRO MAX scanner started for 5 pairs.
health endpoint live at /, /health, /healthz on :10000
router using broker=paper cap_gate=3 caps
tg heartbeat: per-pair card pack will fire every 1 cycle(s)
--- SCAN COMPLETE (cycle 1) ---
tg heartbeat sent=True (cycle 1)
```

For live trading (`ENABLE_LIVE_TRADING=true`) you should see
`broker=binance-live` (or `delta-live`) and
`cap_gate=4 caps` (the 4th being `MaxLiveTradesPerDay`):

```
router using broker=binance-live cap_gate=4 caps
TG service on: confirm=False commands=True operator=<id> timeout=180s
```

The bot should DM your @-bot within ~40 s of the service going green.

### Verify acceptance gate after the first close

Once the bot has placed and closed at least one live trade, run:

```bash
.venv/bin/python scripts/diagnose_live_pnl.py --json | jq '.acceptance'
.venv/bin/python scripts/verify_wallet_parity.py
```

`acceptance: true` and `parity_ok` exit 0 mean Phase 3 Layer 2 has
passed for this deploy. See
[docs/operations.md](docs/operations.md) for the runbook.

---

## Step 5 — Wire up UptimeRobot to keep it awake

Render's free Web Service sleeps after **15 minutes** of no inbound
HTTP. Without the pinger your scanner naps most of the day and
Telegram only fires when somebody (you) accidentally visits the URL.

1. Sign in at https://uptimerobot.com (free).
2. **Add New Monitor** → settings:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: `ictbot health`
   - **URL**: `https://ictbot-scanner.onrender.com/health`
   - **Monitoring Interval**: **5 minutes** (free tier minimum). 5 min
     is well under Render's 15-min sleep threshold, so it'll stay warm.
   - Leave everything else default.
3. **Create Monitor**.

You'll get email alerts if `/health` ever returns 503 (which means the
scanner is up but its heartbeat is stale — i.e. the scan loop is stuck).
That's a real failure signal, not noise.

---

## Step 6 — Confirm end-to-end

- Open Telegram. Within ~5 min you should be getting a fresh per-pair
  card pack every cycle.
- In UptimeRobot, the monitor turns green and shows ~100 % uptime.
- In Render logs, the cycle counter keeps ticking.

You're done. The bot now runs 24/7 for $0.

---

## Operations cheat-sheet

| Task | How |
|---|---|
| Tail logs | Render dashboard → service → **Logs** tab |
| Redeploy | Push to the connected branch; auto-deploy is on |
| Manual restart | Render → service → **Manual Deploy** → **Deploy latest commit** |
| Update secrets | Render → service → **Environment** → edit → Save |
| Pause the bot | Render → service → **Suspend** (kills the container) |
| Lower TG noise | Set `TG_HEARTBEAT_EVERY_N_CYCLES=3` (every 3rd cycle ≈ 2 min) |
| Turn off TG heartbeat | Set `TG_HEARTBEAT_EVERY_N_CYCLES=0` (only fire on BUY/SELL) |

---

## Canonical-flow env vars (Phases A–F)

Every Box of the canonical ICT flow has a knob. Spec-aligned defaults
ship in `settings.py`; flip individually in Render → Environment when
iterating, or hit the kill-switch to revert everything at once.

| Env var | Default | Box | What it does |
|---|---|---|---|
| `CANONICAL_FLOW` | `on` | — | Master kill-switch. Set `off` to roll **every** flag below back to legacy values regardless of other env vars. One-line rollback. |
| `STRATEGY_MODE` | `follow` | 1 | `follow` trades with bias (spec); `fade` trades against it. |
| `BIAS_ENGINE` | `swing` | 1 | `swing` derives bias from swing structure (spec); `sma` / `slope` are legacy. |
| `POI_ENGINE` | `order_block` | 2 | `order_block` = real ICT OB (spec); `min_max` = legacy recent-swing-low/high. |
| `POI_FRAME` | `htf_then_poi` | 2 | `htf_then_poi` tries 4h POI then falls back to 3m on WAITING. `htf` = strict 4h only. `poi` = legacy 3m. |
| `MSS_TIMEFRAME` | `poi` | 3 | `poi` = MSS on 3m frame (spec). `entry` = legacy 1m. |
| `REQUIRE_FVG_AFTER_MSS` | `true` | 4 | MFVG must form strictly after the MSS confirmation bar. |
| `REQUIRE_MFVG_RETEST` | `true` | 5 | A later bar's CLOSE must fall inside the MFVG range before entry fires. |
| `SL_ANCHOR` | `fixed` | 7 | `structural` anchors SL to the MFVG floor/ceiling (spec). `fixed` uses `sl_frac` (legacy). Opt-in default — see below. |
| `STRUCTURAL_TP1_RR` | `2.0` | 8 | TP1 = entry ± N × R when `SL_ANCHOR=structural`. Default 1:2 (spec). |

### Why `SL_ANCHOR` defaults to `fixed`

`SL_ANCHOR=structural` is the canonical bracket but it requires a valid
MFVG range on the entry bar; if none is found it falls back to legacy
SL/TP. To trade canonical brackets in production, set:

```
SL_ANCHOR=structural
```

The other Phase-A–F defaults are spec-aligned at boot, so no other
env-var changes are needed to run the canonical flow.

### Rollback procedure

If anything misbehaves after a canonical-flow knob is flipped on:

1. Render dashboard → Environment → set `CANONICAL_FLOW=off` → Save.
2. Render auto-redeploys (~30s); behaviour reverts to pre-Phase-A.
3. Once root cause is fixed, set `CANONICAL_FLOW=on` again.

---

## Known gotchas

1. **Cold start**: if the pinger ever misses (UptimeRobot brief
   downtime, Render maintenance), the service sleeps for ~30 s before
   the next ping wakes it. Telegram alerts are skipped for that
   window. Not fatal but not invisible either.

2. **Free instance limits**: Render free Web Services have 512 MB RAM
   and 0.1 CPU. The scanner sits ~150 MB and ~1 % CPU steady-state —
   well within the limit. Watch the Metrics tab for surprises.

3. **Persistence**: the free plan has **no persistent disk**. State
   that lives under `data/journal/` (signal dedup, near-miss dedup,
   journal log) resets on every redeploy. The scanner runs fine
   without it — the only effect is a one-off duplicate TG alert
   right after a restart. If this bothers you, the smallest paid disk
   on Render is $0.25/GB-mo for 1 GB.

4. **Geographic latency**: Delta Exchange is hosted in APAC. Render
   Singapore region is the closest free option; Frankfurt and Ohio
   add 80–200 ms per fetch which compounds across 20 calls per cycle.

5. **Invalid Delta API key**: The keys currently in `.env` returned
   `invalid_api_key` when probed. They'll keep working for read-only
   OHLCV (public endpoint) but will fail the moment
   `ENABLE_LIVE_TRADING=true`. Generate fresh keys before flipping
   live trading.

---

## Upgrade path → Background Worker ($7/mo)

If you're tired of the keep-alive workaround:

1. Edit `render.yaml`: change `type: web` → `type: worker` and remove
   `healthCheckPath`.
2. In the Render dashboard the service type changes to **Background
   Worker**; it never sleeps and never needs a pinger.
3. Delete the UptimeRobot monitor.
4. The `/health` endpoint code stays in the repo (harmless when `PORT`
   is unset) so a downgrade later is one git revert.
