# Regime-Adaptive Momentum Agent — Avalanche Agentic-Payments submission

> Paste-ready submission text + the links block. Track: **Agentic Payments** (x402 + ERC-8004 on
> Avalanche C-Chain). Judged on value proposition, technical complexity (use of x402 + ERC-8004),
> and usage of Avalanche technologies.

---

**One autonomous AI agent that PAYS for its inputs and GETS PAID for its outputs — both over x402
(USDC, EIP-3009) — tied to a single ERC-8004 on-chain identity, settled on Avalanche C-Chain.**

The agent reads CoinMarketCap (price, Fear & Greed, macro) to compute a live **CMC Regime Report** —
a regime score + an inverse-vol momentum ranking with an adaptive deployment cap. That report is the
product. Each cycle the agent: **(1)** pays USDC over x402 for its market data, **(2)** computes the
report, **(3)** writes an ERC-8004 on-chain heartbeat (its identity + reasoning), and **(4)** serves
the report from its **own x402-gated endpoint** that other agents pay USDC to read. One self-custody
wallet funds the payments, holds the identity, and receives the revenue — a two-sided agent economy
on one identity, settled on Avalanche.

**This is a real first-party SDK integration, not hand-rolled HTTP.** The x402 leg is built on the
**official `x402` Python SDK** (`x402ResourceServer` + `PaymentMiddlewareASGI` gate the server;
`x402ClientSync` signs the EIP-3009 payment on the consumer side), settled through the **Ultravioleta
DAO** facilitator on Fuji. ERC-8004 talks **directly to the canonical reference contracts via web3.py**
(there is no mature Avalanche ERC-8004 Python SDK, so the reference contracts *are* the integration) —
`register` parses the `Registered` event for the agentId, `setMetadata`/`getMetadata` carry the
heartbeat. We verified every Avalanche parameter live before relying on it: the Fuji USDC EIP-712
domain (recomputed domain separator == on-chain), the canonical ERC-8004 registry (it's already
deployed deterministically on Fuji — no deploy needed), and the facilitator's `/supported`.

**It works on-chain.** The agent paid its own server 0.01 USDC: the SDK signed the
`TransferWithAuthorization`, the facilitator's `/verify` validated the signature and `/settle`
submitted a real `transferWithAuthorization` on the Fuji USDC contract; the report changed hands and
the provider ledger recorded the revenue. The agent owns ERC-8004 identity **#218** on the canonical
registry, with a heartbeat written and read back on-chain. All three transactions are linked below.

**The product is honest.** We audited this universe for a long-only TA edge five independent ways and
found none, so the agent is engineered for risk-controlled, regime-adaptive participation — an
adaptive deployment cap in a [0.40, 0.85] band plus a hard drawdown halt — not a fabricated alpha
number. The regime report it sells is exactly what it would trade on.

**Self-custody + zero-secret deploy.** The signing key never leaves the local wallet; the public
Mission Control dashboard (Vercel SPA + a read-only Render API) holds no secret and reads public
on-chain state by address, so a cloud compromise leaks nothing. The whole loop reproduces with
`make api` + `make avax_demo`.

## Links

- **Repo:** <this repository>
- **Live dashboard (Mission Control):** https://avax-agentic-payments.vercel.app
- **Read-only API:** https://avax-agentic-payments-api.onrender.com (`/api/health`, `/api/snapshot`, `/api/pillars`)
- **Agent wallet** (pays + gets paid + holds the identity): [`0xA9aa558b0a8006390f01A89824832086C080904a`](https://testnet.snowtrace.io/address/0xA9aa558b0a8006390f01A89824832086C080904a)
- **x402 settlement** (agent pays its own server, USDC on Fuji): [`0x14ddec…55f4`](https://testnet.snowtrace.io/tx/0x14ddec0e2b201ed11a4209e4ed90b46a43047ba93550c5754ea845c91efe55f4)
- **ERC-8004 identity:** agentId **218** on the canonical Fuji registry — [`0x8004A818…BD9e`](https://testnet.snowtrace.io/nft/0x8004A818BFB912233c491871b3d84c89A494BD9e/218) · mint [`0x34f98d…2148`](https://testnet.snowtrace.io/tx/0x34f98d37d5cb3227432972efca3377d875995ffb3ce3680cf01f175b0dec2148) · heartbeat [`0x00808e…cdc6`](https://testnet.snowtrace.io/tx/0x00808edc77b3e3f58bfe52563ed868e60901f5fef98f016577cf69808a93cdc6)
- **What changed (the documented delta):** [`docs/AVAX_DELTA.md`](docs/AVAX_DELTA.md)
- **Demo video:** `<TBD: demo video URL — record per DEMO.md>`
- **Submission (DoraHacks / Team1 form):** `<TBD: BUIDL / submission URL>`

---
*Built on the official x402 Python SDK + the canonical ERC-8004 reference contracts. Avalanche Fuji
testnet (C-Chain mainnet is a one-config stretch). Confirm the Speedrun deadline on the Team1 India
form before the cutoff.*
