# BNB Hack 2026 — Execution Plan
### Track 1 (Autonomous Trading Agents, $24K pool) + Best Use of TWAK ($2K special)
### Codename: `ictbot-bnb` (fork of `ictbot`)

> **🔒 LOCKED STRATEGY (read first; supersedes the strategy sections below).** The agent that ships is a **long-only spot momentum allocator** signed end-to-end by **TWAK** — *not* an ICT/confluence signal and *not* perps. Rationale, proven five ways: there is **no positive-edge long-only TA strategy** on the 8-token contest universe (`make validate_trend` failed; a 2,338-window portfolio search found no positive median weekly return), and **TWAK cannot sign perps for agents**. So we optimize for **survive-the-DQ-gate + participate + craft**, not alpha. The allocator (top-2 of 8 by 120-bar momentum, inverse-vol, cash-filtered) uses **regime-adaptive deployment** — the cap scales with a live risk-on score (breadth + trend + vol + Fear&Greed) into the participatory band **[0.40, 0.85]**, so it reacts to the unfolding week rather than a frozen backtest. It's **DQ-proof** (worst-week DD ~17.6% « 30%), **active** (~11.5 trades/wk » 7), and — since a backtest can't validate a forward week — **validated forward in paper** daily from now → the contest (`make forward_report`). **All THREE Track-1 pillars are wired:** ① **CMC** reads markets (live price + Fear&Greed → regime score), ② **Trust Wallet/TWAK** signs + executes spot swaps (native gas; gasless via MegaFuel when `TWAK_GASLESS` is enabled), ③ **BNB AI Agent SDK** gives the agent its on-chain **ERC-8004 identity** (live: **agentId 133085**, minted 2026-06-12 direct-gas from the pinned identity wallet, heartbeating every tick — see the dated correction in [bnb_strategy_decision.md](bnb_strategy_decision.md); MegaFuel gasless stays a config flip once the sponsor policy is set) plus the **CMC AI Agent Hub x402** paid-data path — plus a natural-language strategy spec + per-tick plain-language rationale (the agent "talks"). Full record: **[bnb_strategy_decision.md](bnb_strategy_decision.md)** §4. Build status: strategy + regime-adaptive layer + three-pillar agent + runtime + 39 tests are **done and green** (`make validate_allocator`, `make run_allocator`, `make register_agent`). The sections below are the original planning context / research trail.

---

## 0. Context

### Why this plan exists
You're entering the **BNB Hack: AI Trading Agent Edition** ($36K pool, 14 days remaining to submission deadline 2026-06-21, 7-day live trading window 2026-06-22 → 2026-06-28). You want to leverage the mature `ictbot` codebase (a Bybit/Delta perp ICT scalping bot with 184 tests, full broker/cap/journal pipeline) as the starting point.

### Honest fit verdict (one paragraph)
The **signal-generation framework** (ICT indicators, strategy class, cap gate, scanner, kill switch) is venue-agnostic and reuses ~85% as-is. The **execution layer, data source, and asset class** require new code — different chain (BSC vs Bybit/Delta), different exec semantics (DEX swaps via TWAK vs CEX brackets), different timeframe (1h via CMC vs 1m via ccxt), different direction (spot-only vs long+short). **Your own [findings.md](findings.md) §12 says the perp ICT setup has no measurable OOS edge** — so the plan does NOT bet on the existing tuning transferring. We rebuild the entry condition around **multi-signal confluence** (ICT structure + CMC sentiment/flow + funding) with **strict 15% DD ceiling well inside the 30% disqualifier**, optimizing for "don't blow up, hit minimum 7 trades, place in the middle of the pack" rather than "moonshot the leaderboard".

### Strategic shape
- **Primary**: Track 1, $24K pool, judged on live PnL with DD ≤ 30% (we cap at 15%).
- **Secondary**: Best Use of Trust Wallet Agent Kit ($2K special), scored on TWAK depth + self-custody + autonomous loop + x402 + originality + demo.
- **Realistic prize ceiling**: top-5 Track 1 ($2K minimum) + TWAK special ($2K) = **$4K floor / $12K+ stretch**. The honest pitch isn't "we win Track 1 1st" — it's "we place + we own the TWAK special because nobody else builds an autonomous loop this carefully".

---

## 0.5 `.env.example` template (copy-paste ready)

Consolidated env block. Copy to `.env`, fill in the blanks. Never commit `.env`.

```bash
# === CoinMarketCap Agent Hub ===
CMC_API_KEY=                                # Basic free tier from coinmarketcap.com/api

# === Trust Wallet Agent Kit ===
TWAK_WALLET_PASSWORD=                       # Local wallet password (also in OS keychain)
TWAK_AGENT_ADDRESS=                         # Auto-filled after `twak wallet create`

# === BNB Smart Chain ===
BNB_RPC_URL=https://bsc-dataseed1.binance.org
COMPETITION_REGISTRY_ADDR=0x212c61b9b72c95d95bf29cf032f5e5635629aed5

# === Strategy ===
EXCHANGE=cmc
PAIRS=USDT/ETH,USDT/CAKE,USDT/LINK,USDT/UNI,USDT/AVAX,USDT/DOT,USDT/DOGE
TOKEN_ALLOWLIST=ETH,CAKE,LINK,UNI,AVAX,DOT,DOGE
HTF_TIMEFRAME=1d
BIAS_TIMEFRAME=4h
POI_TIMEFRAME=1h
ENTRY_TIMEFRAME=1h
STRATEGY_MODE=follow                        # spot-only; no fade
BIAS_ENGINE=swing                           # 1h bars favor structural over fast SMA
POI_ENGINE=order_block

# === Risk gates ===
ENABLE_LIVE_TRADING=false                   # FLIP TO TRUE ONLY AFTER GATE B PASSES
RISK_PCT=0.005                              # see §4.7 phasing table
MAX_DD=0.15
MAX_SLIPPAGE_PCT=1
DAILY_LOSS_LIMIT_R=2.0
MAX_OPEN_POSITIONS=1
MAX_LIVE_TRADES_PER_DAY=3
NEWS_BLACKOUT_MINUTES=30

# === Notify ===
TELEGRAM_TOKEN=                             # @BotFather → /newbot
TELEGRAM_CHAT_ID=                           # Your user ID via @userinfobot
TG_OPERATOR_USER_ID=                        # Same as chat ID for solo operator
```

---

## 0.6 Dependency list (consolidated)

```toml
# pyproject.toml [project.dependencies]
"ccxt>=4.0",                # public REST fallback (funding proxy)
"pandas>=2.0",
"numpy>=1.26",
"pydantic-settings>=2.0",
"python-dotenv>=1.0",
"requests>=2.31",           # CMC REST + Forex Factory feed
"web3>=6.0",                # CompetitionRegistry.register()
"streamlit>=1.30",          # dashboard
"prometheus-client>=0.19",  # /metrics endpoint
"python-telegram-bot>=21.0", # Telegram confirm-then-fire (optional)
"pytest>=7.4",              # tests (dev-dep)
"hypothesis>=6.0",          # property tests (dev-dep)
```

**System tools** (installed manually, not via pip):
- **TWAK CLI**: `curl -fsSL https://agent-kit.trustwallet.com/install.sh | bash` (or `npx @trustwallet/cli`)
- **Node.js 20+** (for `npx` path)
- **Python 3.11+**
- **jq** (parsing TWAK CLI JSON output in shell scripts)
- **make** (Makefile targets: `smoke-cmc`, `smoke-twak`, `smoke-bsc`, `register`, `live`, `demo`, `submit`)

---

## 1. Hackathon hard facts (locked-in)

| Item | Value | Source |
|---|---|---|
| Submission deadline | **2026-06-21 17:30** UTC | brief |
| Trading window | **2026-06-22 → 2026-06-28** | brief |
| Judging | 2026-06-29 → 2026-07-05 | brief |
| Winners | week of 2026-07-06 | brief |
| **Today** | **2026-06-07** | env |
| **Days remaining** | **14 days** (today + 13 → submission) | — |
| Plan first written | 2026-06-04 (we are Day 4 of build) | — |
| Competition contract | `0x212c61b9b72c95d95bf29cf032f5e5635629aed5` on BSC mainnet | brief + bscscan-verified |
| Contract type | `CompetitionRegistry` with `register()`, `isRegistered(address)`, `registrationStart()`, `registrationDeadline()` | research |
| Registration window | Opens 2026-06-03 12:00 UTC, closes when trading window opens (2026-06-22) | brief |
| Eligible tokens | 149 BEP-20 listed on CMC (full list in brief lines 146) | brief |
| Minimum trades | ≥1/day, ≥7 over trading week | brief |
| Max drawdown DQ | 30% (we target ≤15%) | brief |
| Submission deliverables | Public repo + on-chain agent address + demo link/video + strategy explanation on DoraHacks | brief |
| Hackathon TG | `https://t.me/+MhiOLT0YUnlmNWFk` | brief |

### Track 1 scoring (verbatim)
> Live PnL. Your agent trades on a held-out window and is ranked by total return, with a max drawdown cap as a risk gate. Blow past the drawdown threshold (for example 30%) and you are disqualified, no matter how good the headline number looks. A minimum trade count and simulated transaction costs apply.

### TWAK special scoring (verbatim, with our column for "what we ship")
| Criterion | Weight | What we ship |
|---|---:|---|
| TWAK integration depth | 30 | TWAK is sole exec layer; use signing + autonomous mode + x402 (3 surfaces, not 1 swap call) |
| Self-custody integrity | 25 | Keys live in `~/.twak/wallet.json`; password from env + OS keychain; no cosigner, no custodial step |
| Autonomous execution + guardrails | 20 | `CapGate` chain: MaxOpenPositions=1, DailyLossLimit=2R, MaxDrawdown=0.15, MaxLiveTradesPerDay=3, NewsBlackout, token allowlist, `--slippage 1` per swap |
| Native x402 usage | 10 | `mcp.coinmarketcap.com/x402/mcp` for the 4 supported tools ($0.01 USDC/req on Base); receipts logged |
| Originality + real-world relevance | 10 | "Spot rotation agent for a self-custody user who doesn't trust a CEX" — narrative aimed at the panel |
| Demo + presentation | 5 | Video showing the loop: CMC data → ICT signal → TWAK sign → BSC swap → BscScan tx hash → journal close |

### ⚠️ Three claims in the brief that external research could NOT verify
**Verify these in the hackathon Telegram (joined at link above) BEFORE writing the code that depends on them.**
1. **`twak compete register` CLI command and `competition_register` MCP action don't appear in TWAK's public docs** (research found 18 subcommands, none matching). The contract itself is real — we have a robust fallback (plain web3.py call) — but ask the organizers whether the TWAK CLI flow is in private beta.
2. **30/25/20/10/10/5 weights for TWAK Best Use are in your brief but not in external press releases or DoraHacks public copy.** Screenshot the actual DoraHacks BUIDL page rubric. If weights change, the priority shifts.
3. **CMC "funding rates" and "KOL sentiment" are marketing-mentioned but no concrete endpoint surfaced.** Plan B: fall back to Bybit/Binance public REST for funding and skip KOL sentiment.

---

## 2. Strategic call — and why

### Why Track 1 + TWAK (not CMC or BNB SDK as the bonus)
- **TWAK is your execution layer for Track 1 anyway** → marginal extra effort to qualify for the special is small.
- **TWAK's rubric is the most concrete** of the three (per brief). CMC Best Use rubric is qualitative; BNB SDK Best Use is "most inventive integration" (vague).
- **Track 1 + TWAK is a stack-coherent story**: "the only fully self-custody, autonomous, x402-funded trading agent in the field." That's a panel pitch the others will struggle to match.
- **CMC Best Use is still partially within reach passively** — your data layer uses CMC anyway. Don't actively chase it, but don't reject it if the panel notices.

### What we're explicitly NOT chasing
- **Track 2 ($6K)** — would require pivoting the deliverable from a live agent to a Skill spec. Different surface; would fragment focus.
- **Track 1 1st place ($10K)** — requires either (a) a strategy with proven edge or (b) outrageous luck during the trading week. Neither is in our control. **We optimize for "place top-5"** ($2K guaranteed if we land 5th) + the TWAK special, not the headline number.
- **Best Use of BNB SDK** — its ERC-8004/8183 identity/escrow story doesn't naturally map to "AI trades spot tokens" without inventing a job-delegation narrative we don't have time to build credibly. Pass.

---

## 3. Reusability map (verified)

From the codebase exploration: the ictbot is split exactly along the right seams for this fork.

### Reuse as-is (zero changes) → **copy into `ictbot-bnb` and never touch**
- **All 16 ICT indicators** in [../src/ictbot/indicators/](../src/ictbot/indicators/) — `atr`, `delta`, `fvg`, `liquidity`, `mss`, `poi_min_max`, `poi_order_block`, `structure`, `bias_sma`, `bias_slope`, `regime`, `mfvg_retest`, `mitigation`, `risk`, `tick`. All pure OHLCV-in/dict-out.
- **Strategy core**: [../src/ictbot/strategy/ict_pro_max.py](../src/ictbot/strategy/ict_pro_max.py) — `ICTProMaxStrategy(bias_engine, poi_engine, strategy_mode, ...)`. Venue-agnostic. The `evaluate()` 25-key result dict is exactly what we need.
- **Backtest engine**: [../src/ictbot/engine/backtest.py](../src/ictbot/engine/backtest.py) — generic walk-forward replay, no perp assumptions. Reused for offline strategy validation pre-live.
- **Broker protocol + Order struct + PaperBroker**: [../src/ictbot/exec/broker.py](../src/ictbot/exec/broker.py), [../src/ictbot/exec/orders.py](../src/ictbot/exec/orders.py), [../src/ictbot/exec/paper.py](../src/ictbot/exec/paper.py). PaperBroker is *exactly the right shape* for spot — it already treats SL/TP as implicit-in-Order checked per-bar (not as separate exchange orders), which is what TwakBroker needs.
- **All 5 caps**: [../src/ictbot/portfolio/caps.py](../src/ictbot/portfolio/caps.py) — `MaxOpenPositions`, `DailyLossLimit`, `MaxDrawdown`, `MaxLiveTradesPerDay`, `NewsBlackoutCap`. Zero perp coupling.
- **Account model**: [../src/ictbot/portfolio/account.py](../src/ictbot/portfolio/account.py) — equity tracking, DD computation. Reused.
- **Router + scanner**: [../src/ictbot/orchestrator/router.py](../src/ictbot/orchestrator/router.py), [../src/ictbot/orchestrator/scanner.py](../src/ictbot/orchestrator/scanner.py). Drop-in.
- **Runtime utilities**: [../src/ictbot/runtime/](../src/ictbot/runtime/) — `kill_switch`, `heartbeat`, `sessions`, `metrics`, `signal_memory`, `news`. All venue-agnostic.
- **Test framework**: lift the tests for the modules above (assume ~120 of the 184 tests transfer).

### Adapt with edits → **edit during/after copy**
- **`settings.py`** ([../src/ictbot/settings.py](../src/ictbot/settings.py)) — add `EXCHANGE=cmc`, `TWAK_WALLET_PASSWORD`, `BNB_RPC_URL`, `COMPETITION_REGISTRY_ADDR`, `TOKEN_ALLOWLIST` (CSV), `MAX_SLIPPAGE_PCT=1`, plus override `HTF_TIMEFRAME=1d, BIAS_TIMEFRAME=4h, POI_TIMEFRAME=1h, ENTRY_TIMEFRAME=1h` (forced by CMC granularity).
- **Strategy params** — `STRATEGY_MODE=follow` (no shorting on spot via TWAK), `BIAS_ENGINE=swing` (1h bars favor structural over fast SMA), `POI_ENGINE=order_block`, fixed-frac SL (3-5%) since AMM slippage already kills tight stops.
- **Streamlit dashboard** ([../src/ictbot/ui/app.py](../src/ictbot/ui/app.py)) — strip Bybit-specific UI, add BSC tx-hash column + TWAK wallet balance panel.

### Build new → **net-new modules in `ictbot-bnb`**
- **`data/cmc_exchange.py`** (~200 lines) — implements `Exchange` protocol via CMC Agent Hub. Three layers: x402 path (mcp.coinmarketcap.com/x402/mcp) for cheap quote/listings, Pro API key path for OHLCV (1h bars), local cache (parquet) since rate limits are real.
- **`exec/twak_broker.py`** (~250 lines) — implements `Broker` protocol. `place_order()` = TWAK CLI subprocess `swap` call (with `--slippage 1 --max-usd <cap>`), records `entry_order_id` = tx hash, stores qty/entry/sl/tp on the Order. **No native SL/TP** — adds `on_bar(pair, current_price)` that closes the position via a reverse swap when price touches SL or TP (mirroring PaperBroker's pattern).
- **`exec/exit_watcher.py`** (~80 lines) — background loop polling current prices for every open Order, calling `twak_broker.close(order)` on SL/TP touch.
- **`compete/register.py`** (~50 lines) — web3.py script calling `CompetitionRegistry.register()` from the agent wallet. Uses TWAK CLI flag `--export-pk` (or its programmatic equivalent) just for the signing step — wallet stays local. Logs tx hash to `data/compete/registration.json`.
- **`x402/cmc_client.py`** (~100 lines) — thin wrapper around `mcp.coinmarketcap.com/x402/mcp` with USDC-on-Base payment plumbing (via TWAK x402). Logs every receipt to `data/x402/receipts.json`.
- **`strategy/macro_filter.py`** (~120 lines) — multi-signal confluence gate sitting BEFORE `ICTProMaxStrategy.evaluate()`. Inputs: CMC Fear & Greed, DEX 24h-volume delta, optionally Bybit-public funding. Outputs: `BULLISH | BEARISH | NEUTRAL`. Strategy only fires when `macro_filter.bias == ICT_bias` and `macro_filter != NEUTRAL`.
- **`exec/forced_trade.py`** (~80 lines) — fallback to guarantee ≥1 trade/day. If no signal fires by 22:00 UTC, place a 0.5% notional "minimum-qualifying" trade in the highest-confidence available direction (or skip with a JSON-logged justification if all caps are tripped — but cap is the safety, not the goal).
- **`notify/dorahacks_export.py`** (~60 lines) — generates the DoraHacks submission packet: agent address, strategy summary, on-chain proof links, demo URL.
- **`Makefile`** entries: `make register`, `make smoke-twak`, `make smoke-cmc`, `make smoke-bsc`, `make live`, `make demo`, `make submit`.

---

## 4. Strategy design (the hard part)

### Reality the strategy must respect
1. **No proven edge on perps.** We're not betting ICT-on-1m-Bybit transfers to ICT-on-1h-BSC-spot. We're building a **new, more defensible setup** that uses ICT as ONE of multiple signals.
2. **CMC reliable timeframe: 1h.** Multi-timeframe stack becomes `1d HTF bias → 4h LTF bias → 1h POI/entry`. Slower, fewer signals — but matches what's available.
3. **Spot only, long only.** No short signals. `STRATEGY_MODE=follow` (trade bias direction), reject SELL signals at the router. Or rotate stablecoin ↔ token.
4. **No native SL/TP on AMM.** Exit watcher polls every minute, executes reverse swap on touch. Higher latency than CEX bracket — model 3-5% effective stop tolerance.
5. **AMM friction is brutal on small tokens.** Restrict universe to top-N by PancakeSwap liquidity (see §5).
6. **Must meet 7-trade minimum.** Forced-trade fallback at 22:00 UTC if zero signals that day.

### Edge story (what we tell the judges)
> "Most agents this hackathon will trade impulsively on a single feed. Ours sits in stablecoins by default and only takes a position when **three independent signals** align: ICT structural confluence (HTF bias + POI + MSS + FVG), CMC macro sentiment regime, and BSC DEX flow direction. When they disagree, we sit out — that's how we keep DD ≤15%."

### Concrete entry condition (long-only example)
```
BUY when:
  ict.evaluate() returns BUY  (HTF + LTF + POI tap + MSS + delta confluence)
  AND macro_filter.bias == BULLISH  (Fear&Greed > 50 + DEX 24h vol delta > 0)
  AND funding_proxy(symbol) ≤ 0.01% / 8h  (skip overheated longs)
  AND token in TOKEN_ALLOWLIST  (top-10 BEP-20 by PancakeSwap depth)
  AND CapGate passes
```

#### Multi-signal confluence flow (visual)

```
┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐
│ ICT structure    │  │ CMC macro filter │  │ Funding proxy     │
│ HTF+POI+MSS+FVG  │  │ F&G + DEX 24h    │  │ Bybit public REST │
│ + delta          │  │ flow             │  │                   │
└────────┬─────────┘  └────────┬─────────┘  └─────────┬─────────┘
         │  BUY?               │  BULLISH?            │  ≤ 0.01%/8h?
         └───────────┬─────────┴──────────┬───────────┘
                     ▼                    ▼
              ┌──────────────────────────────────┐
              │  ALL THREE = YES  ──▶ BUY        │
              │  ANY = NO         ──▶ SIT OUT    │
              └──────────────────────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ CapGate (5)  │ ── reject ──▶ log, no trade
                       └──────┬───────┘
                              │ pass
                              ▼
                         place_order
```

The point: a single noisy signal (e.g. CMC F&G alone) is not enough to fire. Three independent feeds must agree, AND five risk caps must clear. This is the structural defense against blowing up the DD cap.

### Concrete exit policy (no bracket → polled exit)
| Trigger | Action |
|---|---|
| Price touches SL (3% below entry) | Reverse swap (token → USDT) within 1 minute |
| Price touches TP (9% above entry — 3R) | Reverse swap |
| 24h holding limit | Reverse swap (no convicted-runner trades) |
| Macro filter flips to BEARISH | Reverse swap |
| Daily loss limit hit | Skip new entries; existing open position rides to its SL |
| Kill switch engaged | Close all positions in next 1 min |

#### Exit decision tree (priority-ordered, evaluated every 60s)

```
On each 60s tick, for each open Order:

  ├── Kill switch engaged?       YES ─▶ reverse swap NOW (highest priority)
  │                              NO  ─▶ continue
  ├── Daily loss exceeded 2R?    YES ─▶ no new entries (open ride to SL)
  │                              NO  ─▶ continue
  ├── Price ≤ SL?                YES ─▶ reverse swap
  │                              NO  ─▶ continue
  ├── Price ≥ TP?                YES ─▶ reverse swap (book +3R)
  │                              NO  ─▶ continue
  ├── 24h since entry?           YES ─▶ reverse swap (no convicted-runner)
  │                              NO  ─▶ continue
  ├── Macro filter → BEARISH?    YES ─▶ reverse swap (regime broke)
  │                              NO  ─▶ continue
  └── otherwise                  ─────▶ wait 60s, recheck
```

Priority matters because some triggers (kill switch, daily loss) are organizational; others (SL/TP) are mechanical; the macro flip is a tactical override. Always check from top to bottom — first YES wins.

### Sizing
- Risk budget = 0.5–1.0% of equity per trade (`RISK_PCT=0.01`).
- Position size = `(equity × RISK_PCT) / (entry − SL)` × `(1 − slippage_buffer)`.
- Hard ceiling: any single trade ≤ 10% of equity in notional terms.

### Why this beats "just deploy the existing ICT setup"
- Multi-signal confluence is **structurally** harder to over-fit than single-signal optimization.
- Forced 24h timeout caps blowups on illiquid tokens.
- Restricting universe to top-10 by depth caps slippage.
- Macro filter prevents counter-trend trades in obvious regime breaks.

### Backtest plan (before live)
- Pull 90 days of 1h OHLCV for top-10 BEP-20 via CMC Pro tier.
- Replay through `engine/backtest.py` with the new exit policy.
- Validation gate: **TRAIN expectancy > 0** AND **TEST expectancy > 0** AND **drawdown < 15%** on the held-out 30-day window.
- If fail → tighten allowlist, raise confluence threshold, re-test. If still fail → **fall back to a pure macro filter strategy** (long when F&G > 60, exit when F&G < 40). Less alpha, but defensible vs DD cap.

### 4.7 RISK_PCT phasing (reconcile across phases)

`RISK_PCT` shows up at 3 different values across the plan because it ramps as confidence grows. This table is the single source of truth — when in doubt, use this:

| Phase | `RISK_PCT` | Capital risked / trade | Purpose |
|---|---:|---:|---|
| Smoke test (mainnet $5) | `0.001` | $0.005 | Verify TWAK swap round-trip works |
| 24h dry-run (Day 17) | `0.001` | ~$1 | Detect surprises before live; cheap to lose |
| **Trading Day 1 (Jun 22)** | `0.005` | ~$5 | Half-intended; observe slippage + gas in live conditions |
| **Trading Day 2-7** | `0.01` | ~$10 | Full intended after first 24h with no surprises |
| Cap-breach recovery | `0.001` | $1 | Conservative re-entry after DD > 10% |

Notional capital assumed: $1000 starting equity. Re-scale linearly if you fund differently.

---

## 5. Universe selection (top-10 BEP-20 by PancakeSwap depth)

From the 149-token list in the brief, the candidates with non-trivial PancakeSwap liquidity AND CMC OHLCV coverage. **Verify liquidity numbers manually on PancakeSwap or DefiLlama before locking the allowlist.**

| Symbol | Rationale | Risk |
|---|---|---|
| **USDT** | Base/quote rotation token | None |
| **USDC** | Alt base | None |
| **ETH** (bETH) | Highest-liquidity non-stable BEP-20 | Bridge token — confirm CMC ticker matches BSC contract |
| **BNB** | Native BSC, deepest liquidity (⚠️ verify it's in the 149) | Gas token — won't have a "swap" path in the same sense |
| **CAKE** | Native PancakeSwap token, high BSC liquidity | None |
| **DOGE** (bridged) | High liquidity on BSC | Memecoin volatility |
| **AVAX** (bridged) | Cross-chain major | Bridge risk |
| **LINK** | DeFi major, decent BSC liquidity | None |
| **UNI** | DEX governance, BSC bridged | None |
| **DOT** | Big-cap, BSC bridged | None |

**Tradeable universe at runtime = USDT/X for X in {ETH, CAKE, LINK, UNI, AVAX, DOT, DOGE}** (7 pairs). Excludes memecoins/microcaps from active trading. Keep BNB only for gas, not as a trading pair (we need BNB balance for gas anyway).

**Action item before lock-in**: pull PancakeSwap v3 depth at 1% slippage for each candidate. Anything that can't absorb 0.5% of your account at 1% slippage drops from the allowlist.

---

## 6. Architecture

```
                       ┌─────────────────────────────┐
                       │   CMC Agent Hub (x402+Pro)  │
                       │   OHLCV 1h + F&G + DEX flow │
                       └────────────┬────────────────┘
                                    │
                                    ▼
┌──────────────┐         ┌─────────────────────┐         ┌───────────────────┐
│  scanner.py  │────────▶│ analyze_pair()       │────────▶│ macro_filter      │
│  (60s loop)  │         │ → ICTProMaxStrategy  │         │ (F&G + flow)      │
└──────────────┘         │ → confluence check   │         └──────────┬────────┘
       │                 └──────────┬───────────┘                    │
       │                            │                                │
       │                            ▼                                │
       │                  ┌─────────────────────┐                    │
       │                  │ SignalRouter        │◀───────────────────┘
       │                  │ + CapGate(5 caps)   │
       │                  └──────────┬──────────┘
       │                             │
       │                             ▼
       │                  ┌─────────────────────┐
       │                  │ TwakBroker          │
       │                  │ ──CLI subprocess──▶ │──▶  TWAK MCP / CLI ──▶ BSC
       │                  └──────────┬──────────┘
       │                             │
       ▼                             ▼
┌──────────────┐         ┌─────────────────────┐
│ kill_switch  │         │ exit_watcher (1m)   │
│ heartbeat    │         │ polls price → close │
│ metrics      │         └─────────────────────┘
└──────────────┘
       │
       ▼
┌──────────────────────────────────┐
│ Telegram alerts + journal +      │
│ Streamlit dashboard + Prom :9100 │
└──────────────────────────────────┘
```

> 📐 **Visual companion**: **view** [architecture.svg](architecture.svg) (opens in any browser, no extension needed), or **edit** [architecture.excalidraw](architecture.excalidraw) in VS Code's Excalidraw extension / drag-drop to https://excalidraw.com. The visual is a top-down flow — the three pillars (CMC · TWAK · BNB SDK) wrapped around the **momentum allocator**, plus the **two-speed drawdown guard**, on-chain identity, and Mission Control. The ASCII above is for terminal / git-diff use. The upstream ictbot (ICT/perps) overview is a **different product**, archived for provenance only under [archive/architecture_ictbot_upstream.excalidraw](archive/architecture_ictbot_upstream.excalidraw).

### Deployment topology
- **Single VPS** (DigitalOcean / Hetzner / Render Pro — see [../DEPLOY.md](../DEPLOY.md) for the existing setup pattern).
- **No public endpoint** required — TWAK CLI runs locally, x402 outbound. Health server on internal port for liveness checks.
- **OS**: Linux x86_64. TWAK CLI distributed as single binary or via npx.
- **Wallet path**: `~/.twak/wallet.json` — encrypted with `TWAK_WALLET_PASSWORD` from `.env` (NOT committed; rotate before the trading window).
- **Backup**: daily encrypted backup of `data/journal/`, `data/compete/`, `~/.twak/wallet.json` to a separate disk.

---

## 7. New repo layout (`ictbot-bnb`)

```
ictbot-bnb/
├── README.md                     # one-page narrative + setup + on-chain proof links
├── DEMO.md                       # script for the 3-min demo video
├── SUBMISSION.md                 # mirror of DoraHacks submission text
├── pyproject.toml                # python deps (cmc-mcp client, web3, ccxt for funding-only fallback)
├── .env.example                  # all env vars documented; no real secrets
├── Makefile                      # smoke-cmc, smoke-twak, smoke-bsc, register, live, demo, submit
├── docs/
│   ├── strategy.md               # the multi-signal confluence story (judge-facing)
│   ├── architecture.excalidraw # visual flow — MOMENTUM strategy hero + 3 pillars (CMC·TWAK·BNB SDK) + drawdown guard + dashboard
│   ├── twak_integration.md       # why TWAK is sole exec + custody story (TWAK special prize artifact)
│   ├── x402_receipts.md          # log of x402 payments (TWAK special prize artifact)
│   └── runbook.md                # daily operations during the trading week
├── src/ictbot_bnb/
│   ├── __init__.py
│   ├── settings.py               # adapted from ictbot
│   ├── indicators/               # COPIED from ictbot (16 files, zero changes)
│   ├── strategy/
│   │   ├── ict_pro_max.py        # COPIED from ictbot
│   │   └── macro_filter.py       # NEW — F&G + DEX flow + funding confluence
│   ├── engine/
│   │   └── backtest.py           # COPIED — for offline 90d validation
│   ├── data/
│   │   ├── exchange.py           # COPIED protocol
│   │   ├── factory.py            # NEW — registers cmc_exchange
│   │   ├── cmc_exchange.py       # NEW — Exchange impl via CMC Pro + x402
│   │   └── cache.py              # COPIED parquet cache
│   ├── x402/
│   │   └── cmc_client.py         # NEW — x402 payment plumbing
│   ├── exec/
│   │   ├── broker.py             # COPIED protocol
│   │   ├── orders.py             # COPIED Order struct
│   │   ├── paper.py              # COPIED PaperBroker
│   │   ├── twak_broker.py        # NEW — sole live broker
│   │   ├── exit_watcher.py       # NEW — polled SL/TP enforcement
│   │   └── forced_trade.py       # NEW — daily minimum-qualifying fallback
│   ├── portfolio/
│   │   ├── caps.py               # COPIED
│   │   └── account.py            # COPIED
│   ├── orchestrator/
│   │   ├── router.py             # COPIED — small edit to inject macro_filter
│   │   └── scanner.py            # COPIED — small edit to start exit_watcher thread
│   ├── runtime/
│   │   ├── kill_switch.py        # COPIED
│   │   ├── heartbeat.py          # COPIED
│   │   ├── sessions.py           # COPIED
│   │   ├── metrics.py            # COPIED (+ new twak_swap_total counter)
│   │   ├── signal_memory.py      # COPIED
│   │   └── news.py               # COPIED
│   ├── compete/
│   │   ├── register.py           # NEW — web3.py call to CompetitionRegistry.register()
│   │   └── verify.py             # NEW — checks isRegistered(agent_addr) and emits receipt
│   ├── notify/
│   │   ├── telegram.py           # COPIED
│   │   └── dorahacks_export.py   # NEW
│   └── ui/
│       └── app.py                # COPIED + adapted (BSC tx column, TWAK balance panel)
├── tests/                        # COPIED relevant tests + NEW twak_broker + cmc_exchange tests
└── data/                         # (gitignored) runtime artifacts
    ├── journal/
    ├── compete/registration.json
    ├── x402/receipts.json
    └── logs/
```

---

## 8. The "very very small details" checklist

These are the details that 90% of teams will miss. The plan accounts for each.

### Registration
- [ ] Verify with hackathon TG whether `twak compete register` exists in private beta. If yes, use it (less custom code). If no, use `compete/register.py` web3.py path.
- [ ] **Register BEFORE 2026-06-22 00:00 UTC** — the brief says entries after trading window opens are rejected. Aim to register by 2026-06-20 (2 days buffer).
- [ ] After `register()` tx confirms, call `isRegistered(agent_addr)` → must return `true`. Store proof tx hash + screenshot.
- [ ] Submit the registered agent address on DoraHacks. **The agent wallet address must match exactly** what's on-chain.
- [ ] Have BNB in the agent wallet for gas BEFORE registering (estimate 0.01 BNB minimum for buffer; check current gas).

### Wallet & custody
- [ ] **Generate the agent wallet inside TWAK** (`twak init` + `twak wallet create`). Never let the mnemonic touch disk in plaintext.
- [ ] `TWAK_WALLET_PASSWORD` lives in `.env` (gitignored) and is also stored in a password manager you control.
- [ ] **NEVER `--export-pk` in any production code path.** The TWAK special prize penalizes any custodial step.
- [ ] Fund the wallet from a separate "treasury" wallet (your personal Trust Wallet on phone) with: BNB for gas (0.05 BNB), USDT for trading capital (start with $100 for testnet, $500–$1000 for live — match RISK_PCT calculations).
- [ ] Back up `~/.twak/wallet.json` encrypted to a separate disk daily during trading week.

### CMC data
- [ ] Get free CMC Pro API key (Basic tier). Test that 1h OHLCV endpoint works for your 7-pair allowlist.
- [ ] Implement client-side cache with TTL = 30 min for OHLCV, 5 min for F&G. Reduces calls + improves test repeatability.
- [ ] Handle "CMC returns empty for newly-listed BEP-20" gracefully — skip the pair with a logged reason, don't crash the loop.
- [ ] x402 payments: log every receipt to `data/x402/receipts.json` with tx hash. **This is the TWAK special prize artifact.**
- [ ] If CMC funding data is unavailable, fall back to Bybit/Binance public REST (no auth needed) for the funding signal in `macro_filter.py`.

### TWAK execution
- [ ] Every `twak swap` call includes `--slippage 1 --max-usd <position_size_usd>`. Never let slippage default to higher.
- [ ] Validate balance via `twak balance` BEFORE every swap — never blind-trust the local Account.
- [ ] **Test the swap-then-reverse-swap loop on BSC mainnet with $5** during the build week to verify the round-trip works.
- [ ] BSC tx confirmation: wait for 2 blocks (~6 sec) before treating an Order as `FILLED`. Don't pollute the journal with pending txs.
- [ ] **Failure recovery**: if `twak swap` returns non-zero exit, parse stderr, classify (rate limit / insufficient gas / slippage exceeded / network), log to `data/logs/twak_failures.json`, and DO NOT retry blindly — escalate to kill switch on >3 failures/hour.
- [ ] **Reverse-swap race**: if exit_watcher detects SL and the user simultaneously hits kill switch, ONLY ONE reverse swap should fire. Add a per-order lock.

### Exit watcher
- [ ] Poll interval: 60s (not faster — CMC rate limits + sufficient for 1h-bar strategy).
- [ ] Use CMC `crypto_quotes_latest` (x402-supported, $0.01/req) for price polls — cheaper than full OHLCV refresh.
- [ ] At 22:00 UTC daily: check if zero trades that day. If so, fire `forced_trade.py` with the highest-confidence pair.
- [ ] At market close of each UTC day: snapshot equity to `data/journal/equity_curve.json` for DD computation.

### Caps
- [ ] `MaxOpenPositions=1` (start single-position; consider 2 after first 3 days if confident).
- [ ] `DailyLossLimit=2R` (matches existing default).
- [ ] `MaxDrawdown=0.15` (your declared 15% — 50% buffer to the 30% DQ line).
- [ ] `MaxLiveTradesPerDay=3` (caps over-trading on noisy days).
- [ ] `NewsBlackoutCap=30min` around macro events (CPI, FOMC, NFP) — same Forex Factory feed the ictbot already uses.
- [ ] Token allowlist enforced at `router.route()` level (reject signal if pair not in `TOKEN_ALLOWLIST`).

### Observability
- [ ] Prom metrics exported on `:9100/metrics`: `signals_fired_total{pair,direction}`, `twak_swaps_total{pair,result}`, `twak_swap_latency_seconds`, `cap_rejections_total{cap}`, `x402_payments_usd_total`, `account_equity`, `account_drawdown_pct`.
- [ ] Grafana dashboard with one alert: `account_drawdown_pct > 0.12` (warning, 3% below the cap).
- [ ] Telegram alert on: signal fired, swap executed, swap failed, kill switch engaged, equity DD > 10%.
- [ ] Heartbeat to `data/logs/heartbeat.ts` every loop. Separate cron alerts if stale > 5 min.

### Live trading week
- [ ] Pre-flight at T-1 day (2026-06-21): run a 24h dry-run on mainnet with $50 capital. Confirm: ≥1 swap fires, exit watcher closes, journal updates.
- [ ] Day-1 of trading (2026-06-22): start with `RISK_PCT=0.005` (half intended). Bump to full after first 24h with no surprises.
- [ ] Daily 09:00 UTC review: equity, DD, trade count, failure log. Decide: stay course / tighten / kill.
- [ ] Last day (2026-06-28): if equity is positive, let it ride. If DD > 12%, manually flatten and sit in USDT.
- [ ] At competition end: tx hash list ready, equity curve PNG ready, demo video uploaded.

### Submission
- [ ] Public repo on GitHub. README has: 90-sec overview, architecture diagram, setup steps, on-chain proof, demo video link.
- [ ] DoraHacks submission text: strategy story, agent address, TWAK depth narrative (for special prize), x402 receipt total.
- [ ] Demo video (3-5 min): screen-record showing CMC fetch → strategy result → TwakBroker swap → BscScan tx → journal close. Voice-over explaining the multi-signal confluence story.
- [ ] No token launches, no fundraising, no airdrop pumps during the event window (brief explicit DQ rule).

---

## 9. 17-day execution timeline

The plan assumes ~6 productive hours/day during build week. Compresses if you can push harder; absorbs slips at the buffers marked `BUF`.

### 9.0 Day 0 prerequisites (verify retroactively — these should all be ✓ by now)

Before the timeline below makes sense, the following must be in place. If any are still missing, knock them out before continuing with Day 4's TwakBroker work.

- [ ] **VPS provisioned** — Hetzner / DigitalOcean / Render Pro. Linux x86_64. SSH key auth.
- [ ] **Python 3.11+** installed (`python3 --version` ≥ 3.11)
- [ ] **Node.js 20+** installed (`node --version` ≥ 20) — needed for `npx @trustwallet/cli` install path
- [ ] **GitHub repo `ictbot-bnb` created** — private is fine until submission; make public Jun 20 latest
- [ ] **CMC account created** at coinmarketcap.com/api — free Basic tier, API key in hand
- [ ] **Trust Wallet mobile app installed** on phone — treasury wallet (separate from agent wallet)
- [ ] **Telegram bot token** from @BotFather + **numeric chat ID** from @userinfobot
- [ ] **Hackathon Telegram joined** — `https://t.me/+MhiOLT0YUnlmNWFk` (open questions to admins)

### Week 1 — Foundations (2026-06-04 → 2026-06-10)

| Day | Date | Goal | Key deliverables |
|---|---|---|---|
| 1 | Wed Jun 4 | **Setup + verify** | Join hackathon TG; verify `twak compete register` claim; install TWAK CLI + bnbagent SDK + CMC Pro key; fork `ictbot` into `ictbot-bnb` directory and strip Bybit-specific code |
| 2 | Thu Jun 5 | **CMC data adapter** | `data/cmc_exchange.py` working — fetches 1h OHLCV for ETH, CAKE, LINK; test against `engine/backtest.py` on cached data |
| 3 | Fri Jun 6 | **TWAK custody + smoke** | Wallet created; mainnet $5 round-trip swap (USDT→CAKE→USDT) via `twak swap`; tx hashes logged |
| **4 ◀ WE ARE HERE** | **Sat Jun 7 (today)** | **TwakBroker MVP** | `exec/twak_broker.py` implements `place_order()` via TWAK CLI subprocess; `exit_watcher.py` polls + closes on SL/TP; PaperBroker still works in parallel for comparison |
| 5 | Sun Jun 8 | **Wire it all** | scanner runs end-to-end with PaperBroker on CMC data; signals fire; journal writes |
| 6 | Mon Jun 9 | **Macro filter** | `strategy/macro_filter.py` integrates F&G + DEX 24h-flow; gate added to router |
| 7 | Tue Jun 10 | **BUF + 90d backtest** | Run `engine/backtest.py` over 90d of 7-pair OHLCV; iterate until TRAIN > 0 AND TEST > 0 AND DD < 15% on held-out 30d |

### Week 2 — Live integration + special-prize artifacts (2026-06-11 → 2026-06-17)

| Day | Date | Goal | Key deliverables |
|---|---|---|---|
| 8 | Wed Jun 11 | **TwakBroker live** | Switch from PaperBroker to TwakBroker; mainnet with $50; confirm 1 full open→close cycle |
| 9 | Thu Jun 12 | **x402 plumbing** | `x402/cmc_client.py` makes paid CMC calls via TWAK x402; receipts logged; total spend < $1 in test |
| 10 | Fri Jun 13 | **Forced-trade fallback + caps verification** | `forced_trade.py` triggers at 22:00 UTC if zero trades; full CapGate chain tested via fault injection |
| 11 | Sat Jun 14 | **48h mainnet shadow** | Run 48h continuous with $100; observe: trade count, slippage, gas, journal integrity |
| 12 | Sun Jun 15 | **Fix what shadow broke** | Whatever surprised you in §11 |
| 13 | Mon Jun 16 | **Streamlit dashboard adaptation** | BSC tx column, TWAK balance panel, x402 spend counter |
| 14 | Tue Jun 17 | **BUF** | Pure buffer — fixes, polish, weird-edge-case hardening |

### Week 3 — Pre-trading-week (2026-06-18 → 2026-06-21)

| Day | Date | Goal | Key deliverables |
|---|---|---|---|
| 15 | Wed Jun 18 | **Documentation pass** | `docs/strategy.md`, `docs/twak_integration.md`, `docs/x402_receipts.md`, README, DEMO.md script |
| 16 | Thu Jun 19 | **Register on-chain** | Run `make register`; confirm `isRegistered=true`; store tx hash; submit address on DoraHacks |
| 17 | Fri Jun 20 | **Demo video + 24h dry-run** | Record 3–5 min demo; start a 24h dry-run with $50 |
| **DEADLINE** | **Sat Jun 21 17:30 UTC** | **Submit on DoraHacks** | Final push of repo; submission text live; demo URL live |

### Trading week (2026-06-22 → 2026-06-28)

| Day | Date | Goal |
|---|---|---|
| Sun Jun 21 → Sun Jun 28 | Live | Daily 09:00 UTC ops review; respect the kill switch; **do not change strategy during the week**; monitor DD obsessively |

### Judging & winners (2026-06-29 → 2026-07-06)

| Day | Date | Goal |
|---|---|---|
| Jun 29 → Jul 5 | Judging | Available for clarifying questions on DoraHacks / TG |
| Jul 6+ | Winners | — |

### Gantt-style strip (visual)

```
   Build (14 days remaining)         Trade (7 days)      Judge (7 days)
                                                                 │
  Jun 04 ─── Jun 07 ─── Jun 21 ─── Jun 22 ─── Jun 28 ─── Jul 05 ─── Jul 06
   │           │          │          │          │          │          │
   ├─ Day 1 ─ TODAY ──── DEADLINE ── WINDOW ─── WINDOW ─── JUDGING ──  WIN
   │           Day 4      17:30 UTC   OPENS     CLOSES     ENDS        announced
   │                                  reg locks
   │                                                                   │
   ▼                                                                   ▼
 BUILD PHASE  ░░░░░░░░░░░░░░░░░░░░░░ │ TRADE PHASE ░░░░░░░ │ JUDGE PHASE
 (code, test,                        │ (no code edits,     │ (panel
  backtest, fix)                     │  observe + protect) │  reviews)
```

Key dates that cannot slip:
- **Jun 19** — register agent on-chain (we aim for 2 days of buffer before reg locks Jun 22)
- **Jun 21 17:30 UTC** — DoraHacks submission deadline (we submit by noon for cushion)
- **Jun 22 00:00 UTC** — trading window opens; registration locks; agent goes live

---

## 10. Pre-go-live verification gates

The agent does NOT flip to live mode (`ENABLE_LIVE_TRADING=true` with real capital > $100) until **all** of these pass.

### Gate A — Backtest health
- [ ] 90-day TRAIN expectancy > 0
- [ ] 30-day TEST expectancy > 0
- [ ] Worst rolling 7-day drawdown in backtest < 15%
- [ ] Trade count ≥ 7/week (matches hackathon minimum)

### Gate B — Mainnet round-trip integrity
- [ ] At least 3 successful `swap → reverse_swap` cycles on mainnet with real (small) capital
- [ ] Average slippage observed < 1.5% on the allowlist
- [ ] No `twak swap` failures classified as unrecoverable

### Gate C — Cap chain integrity
- [ ] Every cap individually fault-injection-tested: `MaxOpenPositions` blocks 2nd entry, `DailyLossLimit` blocks after −2R, `MaxDrawdown` blocks after −15%, `MaxLiveTradesPerDay` blocks after 3, `NewsBlackoutCap` blocks during CPI test
- [ ] Kill switch (`touch data/KILL_SWITCH_ENGAGED`) flips broker to refuse new entries AND closes any open position within 1 minute

### Gate D — Registration
- [ ] `isRegistered(agent_addr) == true` on contract `0x212c...aed5`
- [ ] Agent address submitted on DoraHacks matches exactly
- [ ] BNB balance for gas ≥ 0.05 BNB
- [ ] USDT/USDC balance for trading capital sized for the planned RISK_PCT

### Gate E — Observability
- [ ] Prom metrics endpoint live on `:9100/metrics`
- [ ] Telegram alert on swap executed + DD > 10% confirmed firing
- [ ] Heartbeat staleness alert tested

### Gate dependency graph

```
                ┌──────────────────────────┐
                │ Gate A — Backtest health │  ◀── offline, can run any time
                └──────────┬───────────────┘
                           ▼
                ┌──────────────────────────┐
                │ Gate B — Mainnet round-  │  ◀── needs real $5 on BSC
                │         trip integrity   │
                └──────────┬───────────────┘
                           ▼
   ┌───────────────────────┴───────────────────────┐
   ▼                                                ▼
   ┌───────────────────────┐         ┌──────────────────────────┐
   │ Gate C — Cap chain    │         │ Gate E — Observability   │
   │ integrity (fault inj) │         │ (Prom + TG alerts)       │
   └──────────┬────────────┘         └──────────┬───────────────┘
              └───────────────┬──────────────────┘
                              ▼
                ┌──────────────────────────┐
                │ Gate D — Registration    │  ◀── last; consumes 0.01 BNB
                │         on-chain         │
                └──────────┬───────────────┘
                           ▼
                  ENABLE_LIVE_TRADING=true
                  (and not before)
```

Gates A, C, E can run in parallel; B and D are blocking. The order matters because:
- Registration (D) consumes gas — don't waste BNB if Gate B says swaps are broken.
- Observability (E) needs to be live before D so you can confirm metrics flow before going live.
- Backtest (A) is the cheapest gate — fail fast here and don't waste time on B-D.

---

## 11. Risk register

| ID | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| R1 | TWAK `compete register` CLI doesn't exist → registration depends on web3.py custom path | High (claim unverified) | Low (we have fallback) | `compete/register.py` ready; tested on testnet first; budget 1 hour for live registration |
| R2 | CMC 1h OHLCV unavailable for a pair we want to trade | Medium | Medium | Token allowlist verified pair-by-pair before lock-in; fallback to ccxt-public for non-CMC pairs (note: makes the "Best Use of CMC" weaker, but Track 1 cares about PnL) |
| R3 | Strategy has negative live edge → DD blowup | Medium-High | Catastrophic (DQ) | 15% DD hard cap, kill switch, conservative RISK_PCT (0.5–1%), forced-trade fallback only when ALL caps are OK |
| R4 | TWAK swap fails repeatedly (rate limit / RPC issues) → can't meet 7-trade min | Medium | High (DQ) | Failure classifier; 3-fail/hr → kill switch; `forced_trade.py` retries with different pair |
| R5 | AMM slippage spikes on competition week → friction kills PnL | Medium | Medium | Top-10 allowlist by depth, slippage cap 1%, per-trade $-max sized for depth |
| R6 | BSC gas spike during competition (memecoin pump elsewhere) | Low-Medium | Medium | Larger BNB gas buffer (0.1 BNB); pause trading if gas > 10 gwei sustained for 1h |
| R7 | x402 service down → can't fetch data | Low | Low | Fallback to CMC Pro REST (we have the key anyway); 30-min OHLCV cache cushions |
| R8 | Token in allowlist gets rugged/halted during trading week | Low | Medium | Daily review; if any allowlist token drops > 20% vs BNB, remove from allowlist within 6h |
| R9 | Wallet password lost / file corrupted | Low | Catastrophic | Daily encrypted backup of `~/.twak/wallet.json`; password in 1Password + paper |
| R10 | Time pressure → ship buggy code on day 17 | High | High | Day 14 + 17 are buffer; submit at noon Jun 21, NOT 17:29; freeze code at 24h-dry-run start |
| R11 | Demo video unconvincing / hard to follow | Medium | Medium (special prize) | Script in `DEMO.md`; record on day 17 with fully-working build; show on-chain tx in real time |
| R12 | TWAK weights 30/25/20/10/10/5 not the real rubric | Medium | Low | Verify in TG group; plan generalizes (depth/custody/autonomous/x402 all naturally important regardless) |
| R13 | Two operators / state race in TG confirm path | Low | Low | Single-operator config (TG_OPERATOR_USER_ID); we're solo |
| R14 | A late protocol change (e.g., BNB Chain hard fork during the week) | Very low | High | Out of our control. Monitor BSC infra Telegram. |

### Risk impact heatmap

```
                              IMPACT →
                Low             Medium             High             Catastrophic
                ───────────────────────────────────────────────────────────────────
   High         │ R10              │                │ R3 (no edge)    │
                │ (ship buggy)     │                │ R10 (time press)│
   ▲            ───────────────────────────────────────────────────────────────────
   PROBABILITY  │                  │ R2 (CMC data)  │ R4 (TWAK fail   │
   Medium       │ R12 (rubric)     │ R5 (slippage)  │     → DQ)       │
                │                  │ R11 (demo)     │                 │
                ───────────────────────────────────────────────────────────────────
   ▼            │ R7 (x402 down)   │ R6 (gas spike) │ R14 (BSC fork)  │ R9 (wallet
   Low          │ R13 (operator)   │ R8 (token rug) │                 │    loss)
                ───────────────────────────────────────────────────────────────────
                                          ▲                ▲
                                    R1 (CLI gap)    pre-mitigation
                                    is High prob /  warranted
                                    Low impact —
                                    fallback ready
```

Reading the heatmap:
- **R3 + R10 (top-right)**: the two existential threats. Both have hard mitigations baked into the plan (15% DD cap, buffer days, freeze-at-Day-17).
- **R4 + R9 (catastrophic column)**: low-prob but unbounded impact. R4 is mitigated by the kill-switch + forced-trade. R9 is mitigated by daily encrypted backup.
- **R1 (high-prob, low-impact)**: TWAK CLI may not have `compete register` — but the web3.py fallback removes the impact entirely.
- **Lower-left quadrant** (R7, R12, R13): acknowledged but un-actioned beyond plan documentation.

---

## 12. Submission deliverables (final checklist)

### GitHub repo (`ictbot-bnb`)
- [ ] Public, MIT-licensed (or similar)
- [ ] README with: 90s pitch, architecture diagram, setup steps, on-chain proof, demo video link
- [ ] All code committed (no `_DEPRECATED` cruft)
- [ ] `.env.example` complete; no real secrets
- [ ] Tests pass: `make test`
- [ ] `make smoke-cmc`, `make smoke-twak`, `make smoke-bsc` all green

### On-chain proof
- [ ] Agent address: `<paste 0x...>`
- [ ] Registration tx: `https://bsctrace.com/tx/<paste>`
- [ ] `CompetitionRegistry.isRegistered(<agent_addr>) == true` (screenshot)
- [ ] Sample trade tx (from dry-run): `https://bsctrace.com/tx/<paste>`

### DoraHacks submission text (~500 words)
- 1-paragraph hook: the multi-signal confluence story
- 2-paragraph technical depth: ICT framework + CMC macro filter + TWAK exec
- 1-paragraph "why TWAK depth matters" (special prize positioning)
- 1-paragraph results to date (backtest expectancy, dry-run observations)
- Links: repo, demo video, agent address, sample tx, Prom metrics screenshot

### Demo video (3-5 minutes)
- [ ] Show scanner loop running live in a terminal
- [ ] Show CMC API call returning F&G + 1h OHLCV
- [ ] Show macro filter + ICT strategy producing a BUY signal
- [ ] Show TwakBroker firing a swap on mainnet
- [ ] Show BscScan tx confirming
- [ ] Show journal entry + Prom counter increment
- [ ] Show exit watcher closing position on TP touch
- [ ] Voice-over: explain the multi-signal confluence + DD cap story

### TWAK special prize artifacts
- [ ] `docs/twak_integration.md` (3-4 pages): self-custody story, autonomous loop diagram, x402 receipts table, originality framing
- [ ] `data/x402/receipts.json` showing real USDC payments
- [ ] Demo segment where the TWAK swap signs locally (no cosigner shown)

---

## 13. Out of scope / explicit non-goals

To preserve focus over 14 remaining days, the plan explicitly DOES NOT:
- Target Track 2 ($6K Strategy Skill) — pivots the deliverable; would split focus.
- Target Best Use of CMC Agent Hub ($2K) — wouldn't pay back the time investment vs. TWAK special given we're already using CMC out of necessity.
- Target Best Use of BNB SDK ($2K) — the SDK's ERC-8004/8183 story doesn't naturally fit our trading agent narrative without invented job-delegation glue.
- Implement leverage, shorting, or perps on BSC — TWAK is spot-only; this is a feature, not a bug, for "self-custody trading agent" framing.
- Implement multi-account or copy-trading.
- Optimize backtest beyond the validation gate — once Gate A passes, we stop tuning. **Tuning during the trading week is forbidden.**
- Add a custom UI beyond the existing Streamlit dashboard.
- Build a separate "Skill" submission for the CMC repo (could be future work; not for this hackathon).
- Re-implement the Bybit / Delta brokers — they stay in upstream ictbot for your separate autotrade work.

---

## 14. Open questions to verify before code starts

Resolve these in the first 24 hours. Each one has a fallback plan in §11 so we're not blocked, but answers sharpen the path.

1. **Does `twak compete register` exist?** Ask in `https://t.me/+MhiOLT0YUnlmNWFk`. If yes, prefer it. If no, `compete/register.py` web3.py path.
2. **What's the actual TWAK special rubric on DoraHacks?** Screenshot the BUIDL page. Confirm the 30/25/20/10/10/5 weights.
3. **What's the current Bybit-quality liquidity on PancakeSwap for each allowlist candidate?** Pull data from `https://info.pancakeswap.finance/` or DefiLlama.
4. **Is BNB itself eligible?** The brief's 149-token list includes "ETH, USDT, USDC, XRP..." — re-read line 146 carefully and confirm BNB is in the list. If yes, can be a trading pair (not just gas). If no, treat as gas only.
5. **Does `CompetitionRegistry` have a `register(string strategy)` overload?** Check the verified contract source on BscScan. Brief says "Explain a bit the strategy" — this might be on-chain or just on DoraHacks.
6. **What gas / RPC provider does TWAK use under the hood?** If it's a free public RPC, plan for periodic 429s. Add fallback to `bsc-dataseed1.binance.org` mirror.
7. **What's the CMC Pro Basic free tier rate limit per minute?** Determines polling cadence in exit_watcher.

---

## 15. Verification plan — how we know the build works end-to-end

After the build, this is the integration test (manual, takes ~30 min):

```bash
# 1. Fresh clone, no cached state
git clone <repo> && cd ictbot-bnb
cp .env.example .env  # fill in CMC_API_KEY, TWAK_WALLET_PASSWORD, BNB_RPC_URL

# 2. Setup
make install
make smoke-cmc     # confirms CMC OHLCV returns 1h bars for the 7 pairs
make smoke-twak    # confirms TWAK CLI installed; wallet exists; small balance check
make smoke-bsc     # confirms web3.py can read CompetitionRegistry

# 3. Backtest gate
make backtest      # runs 90d on 7 pairs; expects TRAIN > 0, TEST > 0, DD < 15%

# 4. Mainnet $5 round trip
TWAK_DRYRUN=false RISK_PCT=0.001 PAIRS=USDT/CAKE make oneshot  # places 1 swap, closes within 30 min

# 5. Cap chain
make test-caps     # fault-injects each cap

# 6. Register
make register      # only when above 4 pass

# 7. Live mode dry-run
ENABLE_LIVE_TRADING=true RISK_PCT=0.001 timeout 24h make scan
```

**Definition of done:** all 7 steps green + 24h dry-run produces at least 1 successful trade with no surprises in the journal.

---

## 16. After the hackathon (out of scope for this plan but worth noting)

If you place top-5 or win the TWAK special, you have:
- A **production-tested TWAK execution adapter** that you can re-use for your separate ictbot autotrade work.
- A **CMC data adapter** that opens up "trade altcoins" as a future direction for ictbot.
- Concrete **on-chain proof** of running an autonomous agent — fundraising / consulting credential.

If you don't place: you've still hardened the ictbot exec layer, validated the multi-signal confluence approach on real data, and learned what BSC AMM friction actually looks like — all useful for ictbot proper.

---

## TL;DR

**What you're shipping**: A fresh fork of ictbot, retuned for Track 1, that uses TWAK as sole self-custody execution layer + CMC for data + a multi-signal confluence entry condition. Hard 15% DD cap. Forced-trade fallback to meet the 7-trade minimum. 14 days remaining of build, then 7 days trade.

**Why this can win money**: Not by topping Track 1's leaderboard — by **placing** (top-5 = $2K) AND **owning the TWAK special** ($2K) because nobody else will build an autonomous loop this carefully.

**The biggest risks** (and what we do about them):
1. Strategy has no proven edge → 15% DD cap + macro filter + forced caps prevent disqualification.
2. `twak compete register` may not exist → web3.py fallback ready.
3. CMC 1h granularity forces a strategy redesign → addressed in §4.
4. AMM slippage on small caps → top-10 allowlist enforced.

**Cheeky penguin says ship it.** 🐧
