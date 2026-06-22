# DEMO.md — 3-4 minute demo video script

> Recording script for the submission video. Shows the full **Agentic Payments** loop on Avalanche:
> the agent **pays** for data and **gets paid** for its regime report over x402, and proves its
> **ERC-8004** identity — all settled on Avalanche Fuji. Target 3:00-4:00. Voice-over (VO) lines are
> verbatim; shot list per segment.

## Pre-roll setup (have open before recording)

- A terminal in the repo (venv active), funded agent wallet (`python scripts/avax_derisk.py balance`
  shows AVAX + USDC > 0).
- The live dashboard: <https://avax-agentic-payments.vercel.app>.
- A Snowtrace tab: <https://testnet.snowtrace.io/address/0xA9aa558b0a8006390f01A89824832086C080904a>.
- The x402 server running in a second shell: `make api`.
- Pre-record any network-dependent shot as a fallback so a flaky RPC / cold facilitator doesn't break
  the take (the on-chain settle waits ~30s for confirmation).

## Segment script

**[0:00-0:25] Hook.** *Shot:* title card → the dashboard hero.
VO: "This is an autonomous AI agent for the Avalanche Agentic-Payments track. It pays for its own
data and gets paid for its analysis — both over x402 in USDC — and it carries one ERC-8004 on-chain
identity. Everything settles on Avalanche, on the real x402 SDK and the canonical ERC-8004 contracts."

**[0:25-0:55] The product (the honest thesis).** *Shot:* run a regime read / the dashboard regime dial.
VO: "Its product is a live CMC Regime Report — a regime score and an inverse-vol momentum ranking from
CoinMarketCap. We audited this universe for a long-only edge five ways and found none, so the agent is
engineered for risk-controlled, regime-adaptive participation, not a fake alpha number. The report it
sells is exactly what it acts on."

**[0:55-2:05] x402 — pays and gets paid.** *Shot:* `make avax_demo`; highlight the x402 lines.
VO: "One command runs the loop. The agent's x402 client signs an EIP-3009 USDC payment and calls its
OWN x402 server. The server — gated by the official x402 SDK's payment middleware — verifies the
signature with the Ultravioleta facilitator and settles a real `transferWithAuthorization` on the Fuji
USDC contract. Then it returns the regime report." *Show:* the printed `SETTLED tx:` line; open it on
Snowtrace confirming a `transferWithAuthorization` to the USDC contract; flip to the dashboard's
**x402-server panel** showing served-jobs and USDC revenue tick up.

**[2:05-2:55] ERC-8004 — on-chain identity.** *Shot:* the demo's identity step; the dashboard identity card.
VO: "Same loop, the identity leg: the agent mints an ERC-8004 identity on the canonical Fuji registry —
agent #218 — and writes an on-chain heartbeat with its timestamp, NAV, and plain-language rationale,
through web3 against the reference contracts. We read it straight back from the chain." *Show:* the mint
+ heartbeat tx hashes; open the identity NFT on Snowtrace (`ownerOf` = the agent wallet); the dashboard
ERC-8004 card with the Snowtrace links.

**[2:55-3:30] Why it holds up.** *Shot:* the dashboard panels; a quick scroll of the README "See it live".
VO: "This is a real SDK integration — the x402 SDK does the signing, verifying, and settling; ERC-8004
is the canonical contracts via web3, no BNB-chain shim. We verified every Avalanche parameter on-chain
before trusting it: the USDC EIP-712 domain, the already-deployed registry, the facilitator. The
public dashboard is zero-secret — Vercel SPA plus a read-only API — so a cloud compromise leaks
nothing."

**[3:30-3:50] Close.** *Shot:* the three-link proof (x402 settle · ERC-8004 mint · heartbeat); end card.
VO: "An agent that pays, gets paid, and proves its identity autonomously — settled on Avalanche.
Live dashboard and the three on-chain transactions are in the description."

## Appendix — commands + live-vs-prerecord

| Segment | Command / action | Live or pre-record |
|---|---|---|
| Regime read | the dashboard regime dial / a sim regime read | live (safe, no spend) |
| x402 pay→get-paid | `make api` (shell 1) + `make avax_demo` (shell 2) | **pre-record** (the settle waits ~30s for Fuji confirmation); banks the real `SETTLED tx` |
| x402 panel | dashboard x402-server panel | live (reads the provider ledger) |
| ERC-8004 mint + heartbeat | `make avax_demo` (identity leg) | live or pre-record; banks the mint + heartbeat tx |
| Snowtrace / identity | open the x402 settle tx + the NFT `#218` | live |
| Dashboard | https://avax-agentic-payments.vercel.app | live |

**On-chain proof to show (Avalanche Fuji):**
- x402 settle: `0x14ddec0e2b201ed11a4209e4ed90b46a43047ba93550c5754ea845c91efe55f4`
- ERC-8004 mint (#218): `0x34f98d37d5cb3227432972efca3377d875995ffb3ce3680cf01f175b0dec2148`
- ERC-8004 heartbeat: `0x00808edc77b3e3f58bfe52563ed868e60901f5fef98f016577cf69808a93cdc6`

**Runtime gaps to close before recording** (user): record the video and fill the demo-video URL in
[README.md](README.md) ("See it live") + [SUBMISSION.md](SUBMISSION.md); a fresh x402 settle + a fresh
heartbeat are both capturable on camera via `make avax_demo`.
