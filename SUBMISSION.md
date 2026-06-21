# BNB Mission Control — DoraHacks submission

> Paste-ready submission text (~500 words) + the links block. Track 1 (Autonomous Trading
> Agents), stacking all three pillars; also entered for Best Use of Trust Wallet Agent Kit.

---

**A self-custody AI trading agent that allocates a long-only spot book across the 8-token
contest universe on BSC — signed end-to-end by Trust Wallet Agent Kit, fed by CoinMarketCap's
Agent Hub, and carrying a live ERC-8004 on-chain identity that heartbeats its reasoning each
tick it runs.**

We started by being honest with ourselves: we audited this universe for a long-only TA edge
**five independent ways and found none** — at realistic DEX friction, across ICT entries,
trend pullbacks, a friction sweep, and a 2,338-window portfolio search, every result was
variance around break-even. A 7-day contest on eight liquid majors is gated by a hard 30%
drawdown disqualifier, so we stopped pretending alpha exists and engineered for the actual
scoring function: **survival, participation, and craft.**

The agent is a **regime-adaptive momentum allocator.** Each ≈daily rebalance it ranks the 8
tokens by 120-bar momentum, holds the top-2 inverse-vol-weighted, and — critically — deploys
*adaptively*: a live risk-on score (basket breadth + trend + volatility + CMC Fear & Greed)
scales the deployed fraction inside a [0.40, 0.85] band, so it leans in when the week trends
and defends to cash when it doesn't. There are no AMM stop brackets; risk is the adaptive cap
plus a hard drawdown halt against the high-water mark. Validation: worst-week drawdown **17.3%**
(vs the 30% DQ line) at **~15.4 trades/wk** (vs the 7-trade floor), then forward-validated in
paper daily on unseen data — because a backtest can't validate a forward week.

**All three pillars are load-bearing, not decorative.** ① **CoinMarketCap** is the eyes: live
price + Fear & Greed drive the regime score, the Agent Hub **MCP** supplies pre-computed
TA/macro that A/B-testing showed *reduces drawdown* (the `enhanced+ta` arm is the best
config), and the agent pays for data via **native x402** — 20+ real USDC micropayments settled
on Base, no API key. ② **Trust Wallet Agent Kit** is the only thing that signs: every swap,
the `twak compete` registration, even the gas top-up went through the local `twak` CLI — keys
never leave `~/.twak/wallet.json`, no cosigner, no custodial step. ③ The **BNB AI Agent SDK**
gives it an on-chain **ERC-8004 identity** (agentId 133085) wired to publish a natural-language
heartbeat (NAV + rationale) each tick — on-chain activity that continues past the one-shot
mint (mint + first heartbeat verified on-chain). It also runs the SDK's **flagship ERC-8183**
agentic-commerce layer: the agent **sells its live CMC Regime Report to other agents** for an
on-chain fee (`create_job → fund → submit signed deliverable → settle`), so it both **buys** data
(x402) and **monetizes** its analysis (ERC-8183) — a two-sided agent economy on one identity
(gasless on bsc-testnet; see [docs/erc8183_agent_commerce.md](docs/erc8183_agent_commerce.md)).

**Why the TWAK depth matters:** this is a genuinely self-custody, autonomous, x402-funded
agent — three TWAK surfaces, zero custodial steps — which is exactly the "agent acts on your
behalf without giving up your keys" story the kit exists for. The public Mission Control
dashboard is read-only and deploys **zero secrets**, so a cloud compromise leaks nothing.

The agent performs spot swaps only — no token launches, fundraising, or airdrop activity
during the event window.

## Links

- **Repo:** <this repository>
- **Dashboard (Mission Control):** https://bnb-mission-control-two.vercel.app
- **Read-only API:** https://bnb-mission-control-api.onrender.com (`/api/health`, `/api/pillars`)
- **Agent / participant address:** `0xE8A30d24BbA030D3e8a844bD1c4F6e1374EA6215` (`isRegistered=true` on `0x212c61b9b72c95d95bf29cf032f5e5635629aed5`)
- **ERC-8004 identity:** agentId 133085 — https://bscscan.com/token/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432?a=133085
- **x402 receipts:** [docs/x402_receipts.md](docs/x402_receipts.md) (20+ settled, $0.20+ on Base; see `data/x402/receipts.json`)
- **Demo video:** `<TBD: demo video URL — record per DEMO.md>`
- **DoraHacks BUIDL:** `<TBD: BUIDL URL>`
- **Sample live swap tx (TWAK-signed, BSC):** [`0x9d64…67d1`](https://bscscan.com/tx/0x9d64945b28ce5f217471299599bb30406ac5a9f7a6fb873c917aa697aa5867d1) (USDT→CAKE) + [`0xf08f…0380`](https://bscscan.com/tx/0xf08f1b4f0b7d00a23ff7255f6da70270dbfba389b5f19d182dd055ec6a5c0380) (CAKE→USDT) — a pre-window proof round-trip; in-window swaps follow during the trading week

---
*Note: the brief's §12 "Prometheus metrics screenshot" deliverable is superseded by the live
Mission Control dashboard URL above (the allocator path exposes its telemetry through the
read-only API, not a `:9100` scrape). Word count ~500; trim the hook if the form is tighter.*
