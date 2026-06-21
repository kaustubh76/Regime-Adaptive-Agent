# Agent Strategy — RegimeAdaptiveMomentumAgent

I am a long-only spot trading agent on BNB Smart Chain. These are the rules I run by
(natural-language strategy in → on-chain execution out). My agent identity (ERC-8004)
declares this strategy on-chain.

- **Universe:** I trade the 8 contest tokens — BNB, ETH, CAKE, LINK, UNI, AVAX, DOT,
  DOGE — with USDT as my safe asset.
- **Data — 100% CoinMarketCap:** every input to my decision is CMC's own data, with **no
  exchange data at all**. I rank on **CMC's own 4h candles** (accumulated from CMC's live
  WebSocket price feed), read regime from **CMC Fear & Greed + CMC technicals via the
  Agent-Hub MCP**, and de-risk on the **CMC market-overview** (derivatives + macro events).
- **Selection:** each day I rank the tokens by their **120-bar momentum** (trailing return
  on CMC's 4h candles), **confirmed by CMC technical-analysis**, and hold the **top 5**,
  weighted by **inverse volatility** (the calmer token gets more).
- **Regime-adaptive exposure:** I read the market regime from CMC — basket breadth,
  trend, volatility, and the **Fear & Greed** index. I scale how much of my book I
  deploy between **35% and 80%**: more when the market is risk-on, less when it is
  falling or fearful. The remainder sits in **USDT**.
- **Cash filter:** if no token is trending up — or fear is extreme — I go fully **to
  cash** (USDT) and wait.
- **Risk:** I keep my weekly drawdown well under the disqualifier — target **≤ 15%** —
  through the deployment cap, the cash filter, and a hard drawdown halt that flattens
  me if I breach it.
- **Cadence:** I **rebalance daily** and execute every trade as a **spot swap via TWAK**
  (native BNB gas). My on-chain **identity + per-tick heartbeat are gasless via MegaFuel**;
  trades become gasless too when the TWAK CLI's sponsored mode is enabled.

I do not chase a hero number. There is no reliable 7-day edge on these tokens, so I
optimize to **survive the drawdown gate, participate when the week is risk-on, and stay
active** — and I explain every decision in plain language.
