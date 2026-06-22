# Regime-Adaptive Momentum Agent — Agentic Payments on Avalanche (x402 + ERC-8004)

**One autonomous agent that PAYS for its inputs and GETS PAID for its outputs — both over x402
(USDC, EIP-3009), tied to a single ERC-8004 on-chain identity, settled on Avalanche C-Chain.**

The agent reads CoinMarketCap (price, Fear & Greed, macro) to compute a live **CMC Regime Report**
(regime score + momentum ranking), then:

- **pays** USDC over x402 for its data,
- **sells** that report from its own **x402-gated endpoint** that other agents pay USDC to read,
- **holds** an ERC-8004 identity it **heartbeats** on-chain each cycle.

Built for the **Avalanche "Agentic Payments · Speedrun · June 2026"** track on the **real first-party
SDKs** — the official **`x402` Python SDK** and the **canonical ERC-8004 reference contracts** (via
web3.py) — not hand-rolled HTTP.

> Documented delta (every file that changed + verification): [`docs/AVAX_DELTA.md`](docs/AVAX_DELTA.md)

---

## See it live (judges: start here)

| | link |
|---|---|
| 🟢 **Mission Control dashboard** (Vercel) | <https://avax-agentic-payments.vercel.app> |
| 🔌 **Read-only API** (Render; free tier cold-starts ~30s) | [`/api/health`](https://avax-agentic-payments-api.onrender.com/api/health) · [`/api/snapshot`](https://avax-agentic-payments-api.onrender.com/api/snapshot) · [`/api/pillars`](https://avax-agentic-payments-api.onrender.com/api/pillars) |
| ⛓ **On-chain proof** (Avalanche Fuji) | x402 settle [`0x14ddec…55f4`](https://testnet.snowtrace.io/tx/0x14ddec0e2b201ed11a4209e4ed90b46a43047ba93550c5754ea845c91efe55f4) · ERC-8004 mint [`0x34f98d…2148`](https://testnet.snowtrace.io/tx/0x34f98d37d5cb3227432972efca3377d875995ffb3ce3680cf01f175b0dec2148) · heartbeat [`0x00808e…cdc6`](https://testnet.snowtrace.io/tx/0x00808edc77b3e3f58bfe52563ed868e60901f5fef98f016577cf69808a93cdc6) |
| 🪪 **ERC-8004 identity** | agentId **218** on the canonical Fuji registry [`0x8004A818…BD9e`](https://testnet.snowtrace.io/nft/0x8004A818BFB912233c491871b3d84c89A494BD9e/218) |
| 🤖 **Agent wallet** (pays + gets paid + holds the identity) | [`0xA9aa558b…904a`](https://testnet.snowtrace.io/address/0xA9aa558b0a8006390f01A89824832086C080904a) |

```bash
# reproduce the whole loop yourself (after funding the wallet — see §5):
make api          # the x402 server + dashboard API
make avax_demo    # agent pays its own server (x402) + mints/heartbeats its ERC-8004 identity
```

---

## 1. The headline demo — pay → get paid → prove identity

For the live demo, one funded agent pays **its own** x402 server, so judges watch the CMC Regime
Report change hands on-chain in a self-contained loop, then the agent stamps its ERC-8004 identity:

```
  ┌─ one demo run (scripts/avax_demo.py) ─────────────────────────────────────────────┐
  │  ① x402 consumer  → GET /x402/regime-report → 402 challenge (x402 SDK client)      │
  │  ② sign EIP-3009 USDC payment → resend → facilitator settles on Fuji  (the PAY)    │
  │  ③ x402 server    → verifies + returns the CMC Regime Report          (GET PAID)   │
  │  ④ ERC-8004       → mint identity (web3) + setMetadata heartbeat       (IDENTITY)  │
  └───────────────────────────────────────────────────────────────────────────────────┘
```

One self-custody wallet funds the payments, holds the ERC-8004 identity, and receives the revenue.

## 2. The real SDK integration (the technical core)

| Leg | SDK / contract | Where |
|---|---|---|
| **x402 server** (gets paid) | official `x402` SDK — `x402ResourceServer` + `PaymentMiddlewareASGI` + `HTTPFacilitatorClient` | [`api/x402_server.py`](src/ictbot/api/x402_server.py) |
| **x402 client** (pays) | official `x402` SDK — `x402ClientSync` + `wrapRequestsWithPayment` (sync) | [`api/x402_server.py`](src/ictbot/api/x402_server.py) `pay_and_fetch()` |
| **Settlement** | Ultravioleta DAO facilitator (gasless), `eip155:43113`, Fuji USDC | `https://facilitator.ultravioletadao.xyz` |
| **ERC-8004 identity** | **canonical reference contracts** via web3.py (no bnbagent on Avalanche) | [`agent/erc8004_client.py`](src/ictbot/agent/erc8004_client.py) + [`agent/abis/IdentityRegistry.json`](src/ictbot/agent/abis/IdentityRegistry.json) |

Engineering notes worth knowing:
- The x402 SDK runs the route handler **before** settlement, so the handler can't see the tx hash —
  an outer `X402LedgerMiddleware` reads the SDK's `PAYMENT-RESPONSE` header and journals the
  settlement, keeping the dashboard's `server_stats()` intact.
- ERC-8004 `register()` returns the `agentId` via the `Registered` event (a tx can't return a value),
  so the client parses it from the receipt; heartbeats are `setMetadata(agentId, "heartbeat", …)`.
- There is **no mature Avalanche ERC-8004 Python SDK** (chaoschain-sdk excludes Fuji), so the
  canonical reference contracts *are* the integration — called directly with the official ABI.
- The installed `x402` wheel (2.13.1) API differs from the GitHub `main` examples; imports are pinned
  to the installed package.

## 3. The product — the CMC Regime Report (what the agent sells)

Each cycle, over an 8-token universe, the agent computes the report it both trades on and sells:

1. **Rank** tokens by trailing 120-bar (4h) return.
2. **Hold the top-k** by relative momentum (always deployed into the strongest names).
3. **Size** by inverse volatility (30-bar).
4. **Deploy adaptively** — a live risk-on score (basket breadth + index trend + volatility + CMC
   Fear & Greed) scales the deployment cap inside `[0.40, 0.85]`: high when the basket trends up,
   pulled toward cash when it doesn't.

The deliverable ([`agent/regime_report.build_report()`](src/ictbot/agent/regime_report.py)) is
secret-free, JSON-serialisable public market analysis — exactly what another agent pays to read. The
strategy is real and was audited for a long-only edge five independent ways
and found none; the agent is engineered for risk-controlled, regime-adaptive participation, not
fabricated alpha ([docs/findings.md](docs/findings.md)).

Code: [`strategy/momentum_allocator.py`](src/ictbot/strategy/momentum_allocator.py) ·
[`strategy/regime_score.py`](src/ictbot/strategy/regime_score.py) ·
[`data/cmc_agent_hub.py`](src/ictbot/data/cmc_agent_hub.py) (CMC Data MCP — the eyes).

## 4. Verified Avalanche parameters (all confirmed live, not assumed)

| Item | Value | How verified |
|---|---|---|
| Fuji USDC (6dp, EIP-3009) | `0x5425890298aed601595a70AB815c96711a31Bc65` | Circle docs + on-chain |
| USDC EIP-712 domain | `name="USD Coin"`, `version="2"` | recomputed domain separator == on-chain `DOMAIN_SEPARATOR()` |
| ERC-8004 Identity Registry (Fuji) | `0x8004A818BFB912233c491871b3d84c89A494BD9e` | `eth_getCode` + live `ownerOf` — canonical, **no deploy needed** |
| x402 network / scheme | `eip155:43113` / `exact` | facilitator `/supported` (live) |
| Facilitator | Ultravioleta DAO (gasless, ~2s) | live `/health` + `/supported` |
| RPC / explorer | `api.avax-test.network/ext/bc/C/rpc` / `testnet.snowtrace.io` | — |

Full table incl. C-Chain mainnet (stretch): [`docs/AVAX_DELTA.md`](docs/AVAX_DELTA.md).

## 5. Run it

```bash
# 0) install the real SDKs (official x402 + web3 for canonical ERC-8004)
python -m pip install -e ".[x402,api,bnb,dev]"

# 1) mint + fund the agent wallet (prints the address + faucet links)
python scripts/avax_derisk.py keygen
#    fund AVAX (core.app faucet) + Fuji USDC (faucet.circle.com → Avalanche Fuji), then:
python scripts/avax_derisk.py settle     # a real EIP-3009 transferWithAuthorization tx on Snowtrace

# 2) put AGENT_PRIVATE_KEY / AGENT_IDENTITY_ADDRESS + AGENT_NETWORK=avax-testnet + X402_SERVER_ENABLED=1
#    + X402_SERVER_URL=http://127.0.0.1:8000 in .env, then run the API (dashboard + x402 server)
make api          # uvicorn ictbot.api.app:app --port 8000

# 3) the agent pays its OWN server via the x402 SDK, then mints + heartbeats its ERC-8004 identity —
#    prints every settlement / mint / heartbeat tx as a Snowtrace link
make avax_demo    # python scripts/avax_demo.py   (--no-mint / --no-x402 to scope)
```

| Command | What it does |
|---|---|
| `make avax_derisk ARGS=domain` | verify the USDC EIP-712 domain matches on-chain (no funds) |
| `make avax_derisk` | keygen → balance → settle-if-funded (the Fuji EIP-3009 spike) |
| `make avax_demo` | the headline pay→get-paid + ERC-8004 mint + heartbeat loop |
| `make api` + `cd web && npm run dev` | Mission Control locally (FastAPI :8000 + Vite :5173) |
| `make test` | the full suite (on-chain settle is opt-in / skipped) |

`GET /x402/info` advertises the paid service (price, network, payTo, facilitator, served-jobs).

## 6. Mission Control — dashboard

**Live:** <https://avax-agentic-payments.vercel.app>

A React/Vite SPA polls a read-only FastAPI and renders the regime dial + adaptive cap, the rebalance
table with the plain-language rationale, the ERC-8004 identity card (Snowtrace links), and the
**x402-server panel** (served jobs + USDC revenue + last settlement tx). The deploy is split + zero-secret:
the **Vercel** CDN serves the static SPA; the SPA reads `config.json` and polls the **Render** read-only
API (`avax-agentic-payments-api.onrender.com`, CORS-locked to the Vercel origin), falling back to the
committed `snapshot.json` if the free-tier API is cold. No key is ever held — it reads public on-chain
state by address. Deploy pipeline: [`docs/deploy_dashboard.md`](docs/deploy_dashboard.md) (`make deploy_dashboard`).

## 7. Verification status — proven on-chain (Fuji)

**Both headline legs are settled on-chain** from the agent wallet
`0xA9aa558b0a8006390f01A89824832086C080904a`:

| Leg | tx | proof |
|---|---|---|
| **x402** — agent pays its own server 0.01 USDC | [`0x14ddec…55f4`](https://testnet.snowtrace.io/tx/0x14ddec0e2b201ed11a4209e4ed90b46a43047ba93550c5754ea845c91efe55f4) | SDK signs EIP-3009 → facilitator `/verify`+`/settle` → real `transferWithAuthorization` on Fuji USDC (`status=1`); report served; ledger `served_jobs=1` |
| **ERC-8004** — mint identity **#218** | [`0x34f98d…2148`](https://testnet.snowtrace.io/tx/0x34f98d37d5cb3227432972efca3377d875995ffb3ce3680cf01f175b0dec2148) | `ownerOf(218)` = the agent wallet; `tokenURI` = the agent card |
| **ERC-8004** — heartbeat (`setMetadata`) | [`0x00808e…cdc6`](https://testnet.snowtrace.io/tx/0x00808edc77b3e3f58bfe52563ed868e60901f5fef98f016577cf69808a93cdc6) | `getMetadata("heartbeat")` reads back `{ts, nav, rationale}` |

The SDK integration (x402 2.13.1 + canonical ERC-8004 via web3) passes the full test suite; rerun the
whole loop any time with `make avax_demo`. Confirm the Speedrun submission deadline on the Team1 India
form before the cutoff. Full detail: [`docs/AVAX_DELTA.md`](docs/AVAX_DELTA.md).

## 8. Repo map

```
src/ictbot/
├── api/x402_server.py            # x402 SERVER on the official SDK + ledger middleware + sync client
├── agent/erc8004_client.py       # ERC-8004 identity via web3 + the canonical reference ABI
├── agent/abis/IdentityRegistry.json   # vendored canonical ERC-8004 ABI
├── agent/identity.py             # ERC-8004 register/heartbeat (web3 adapter over erc8004_client)
├── agent/regime_report.py        # the SELLABLE product (CMC Regime Report)
├── data/x402_cmc.py              # lean x402 payment-wallet reads (USDC balance / address)
├── strategy/momentum_allocator.py · regime_score.py   # the regime read the report packages
└── api/                          # read-only FastAPI behind Mission Control
scripts/avax_derisk.py            # wallet bootstrap + Fuji EIP-3009 settlement spike
scripts/avax_demo.py              # one-shot pay→get-paid + ERC-8004 mint + heartbeat
web/                              # Mission Control React/Vite SPA
```

The spot-trading execution layer (`src/ictbot/exec/*`) is **out of scope** and left inert — the track
is about payments, not trading. The repo grew from `ictbot`, a CEX engine that supplied the
journal/caps/runtime plumbing.

## 9. Further reading

- [`docs/AVAX_DELTA.md`](docs/AVAX_DELTA.md) — the documented delta (every file that changed, verification)
- [docs/findings.md](docs/findings.md) — the negative-edge audit behind the regime report (the product)

**License:** [MIT](LICENSE)
