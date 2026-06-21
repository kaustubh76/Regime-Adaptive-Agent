# DEMO.md — 3-5 minute demo video script

> Recording script for the submission video. Shows the full autonomous loop on the locked
> **momentum allocator** (not the superseded ICT scanner). Target 3:30-4:30. Voice-over (VO)
> lines are verbatim; shot list per segment. Record per the BNB Hack §12 demo checklist,
> re-mapped to what actually ships.

## Pre-roll setup (have open before recording)

- A terminal in the repo (venv active).
- The live dashboard: <https://bnb-mission-control-two.vercel.app>.
- A BscScan tab + a Base explorer tab (for the x402 payer).
- `twak` CLI authed (`~/.twak/wallet.json`, `TWAK_WALLET_PASSWORD` set).
- `.env` with `ENABLE_LIVE_TRADING=true`, `X402_ENABLED=true` for the live segments.
- Decide live-vs-prerecord per segment (see appendix) — pre-record any network-dependent shot
  as a fallback so a flaky RPC doesn't break the take.

## Segment script

**[0:00-0:25] Hook.** *Shot:* title card → the dashboard hero.
VO: "This is a fully self-custody AI trading agent for the BNB Hack. CoinMarketCap is its
eyes, Trust Wallet Agent Kit is its only signer, and it carries its own on-chain ERC-8004
identity. No CEX, no custodian, no key ever leaves the wallet."

**[0:25-0:55] The honest thesis.** *Shot:* `docs/strategy.md` §2 table on screen.
VO: "We audited this 8-token universe for a long-only edge five ways and found none — so
instead of faking alpha, we engineered for the real scoring function: survive the 30%
drawdown gate, clear the 7-trade floor, and participate when the week trends."

**[0:55-1:40] CMC reads (pillar 1).** *Shot:* run `make run_allocator`; highlight the tick line.
VO: "One rebalance tick. The agent pulls live Fear & Greed and macro from CoinMarketCap,
reads pre-computed technicals through the Agent Hub MCP, and folds them into a regime score."
*Show:* the printed `regime`, `cap`, `F&G` and the held weights.

**[1:40-2:10] The decision + the agent's voice.** *Shot:* the journaled rationale line.
VO: "The regime score sets an adaptive deployment cap in the 40-to-85% band, picks the top-2
by momentum, sizes them inverse-vol — and explains itself in plain language. That sentence is
written on-chain as a heartbeat each tick it runs."

**[2:10-2:55] TWAK executes (pillar 2).** *Shot:* `make run_allocator ARGS="--mode live"` (or a
pre-recorded live tick); the `twak swap` call.
VO: "Execution is Trust Wallet Agent Kit — the sole signer. The swap signs locally from
`~/.twak/wallet.json` — no cosigner, no prompt, no exported key — and returns a transaction
hash." *Show:* the tx hash, then open it on BscScan confirming.

**[2:55-3:20] On-chain identity + x402 (pillars 3 + 1).** *Shot:* BscScan token page for agentId
133085; then the CMC Agent Hub panel on the dashboard.
VO: "The agent owns ERC-8004 identity 133085, and it pays for its own data — ten real USDC
micropayments settled on Base through x402, no API key." *Show:* the panel's settled count +
USDC spent + MCP calls.

**[3:20-3:50] Guardrails (why it can't blow up).** *Shot:* the dashboard RegimeDial +
RebalanceTable + trades-toward-7 counter.
VO: "Two contest gates, each with a strategy defense and a mechanical defense: an adaptive cap
plus a hard drawdown halt against the high-water mark for the 30% line, and a trade-floor
nudge for the 7-trade minimum. Failed swaps are contained, state writes are atomic, overlapping
crons can't double-execute."

**[3:50-4:20] Close.** *Shot:* the three-pillar panel; end card with links.
VO: "Self-custody, autonomous, x402-funded — read by CoinMarketCap, signed by Trust Wallet,
identified on BNB Chain. Repo and live dashboard in the description."

## Appendix — commands + live-vs-prerecord

| Segment | Command / action | Live or pre-record |
|---|---|---|
| CMC read | `make run_allocator` | live (sim — safe, no spend) |
| TWAK swap | `make run_allocator ARGS="--mode live"` | **pre-record** (needs live BNB + a clean RPC); banks the real tx hash |
| x402 panel | dashboard CMC Agent Hub panel | live (reads existing receipts) |
| BscScan/identity | open tx + token 133085 | live |
| Dashboard | https://bnb-mission-control-two.vercel.app | live |

**Dropped from the brief's stale checklist** (superseded by the momentum allocator): "ICT BUY
signal", "exit watcher closing on TP touch", "Prometheus counter" — there is no ICT signal, no
SL/TP bracket, and telemetry is the read-only dashboard, not a `:9100` scrape.

**Runtime gaps to close before recording** (user, ~Jun 20): record the video and fill the demo
URL in [README.md](README.md) §1 + [SUBMISSION.md](SUBMISSION.md); a real live-swap tx hash and
the x402-on tick are both capturable on camera.
