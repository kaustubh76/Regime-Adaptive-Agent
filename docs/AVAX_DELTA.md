# Avalanche Port — Documented Delta (x402 + ERC-8004 on C-Chain)

> Submission asset for the **Avalanche "Agentic Payments · Speedrun · June 2026"** track.
> This file documents exactly what changed to port the agent from Base/BSC to **Avalanche
> C-Chain**, and how to run + verify it. Source spec: [`AVAX_PORT_SPEC.md`](../AVAX_PORT_SPEC.md).

## The headline

**One autonomous agent that PAYS for its inputs and GETS PAID for its outputs — both over x402
(USDC, EIP-3009), tied to one ERC-8004 identity, settled on Avalanche C-Chain.** Built on the
**official `x402` Python SDK** + the **canonical ERC-8004 reference contracts** (web3.py) — first-party
SDKs, not hand-rolled HTTP.

- **Gets paid** (provider, *net-new*): `GET /x402/regime-report` gated by the **x402 SDK**
  (`x402ResourceServer` + `PaymentMiddlewareASGI`); other agents pay USDC to read the agent's live
  **CMC Regime Report**, settled via the **Ultravioleta DAO** facilitator on Fuji.
- **Pays** (consumer): the **x402 SDK client** (`x402ClientSync` + `wrapRequestsWithPayment`) signs
  the EIP-3009 payment. For the demo the agent pays its **own** server (agent-to-agent), so the
  report changes hands on-chain in a self-contained loop.
- **Identity** (ERC-8004): a **web3.py client over the canonical reference ABI** mints an Identity
  NFT on the registry **already deployed on Fuji** and writes a per-cycle heartbeat (`setMetadata`).
  (No mature Avalanche ERC-8004 Python SDK exists, so the reference contracts *are* the integration.)

## Verified Avalanche parameters (all confirmed live, not assumed)

| Item | Value | How verified |
|---|---|---|
| Fuji USDC (6dp, EIP-3009) | `0x5425890298aed601595a70AB815c96711a31Bc65` | Circle docs + on-chain |
| USDC EIP-712 domain | `name="USD Coin"`, `version="2"` | recomputed domain separator == on-chain `DOMAIN_SEPARATOR()` |
| Fuji RPC | `https://api.avax-test.network/ext/bc/C/rpc` | — |
| Explorer | `https://testnet.snowtrace.io` | — |
| ERC-8004 Identity Registry (Fuji) | `0x8004A818BFB912233c491871b3d84c89A494BD9e` | `eth_getCode` on Fuji (canonical reference, same vanity addr on all testnets) — **no deploy needed** |
| x402 network id / version | `eip155:43113` / `2`, scheme `exact` | facilitator `/supported` (live) |
| Facilitator (settle) | Ultravioleta DAO `https://facilitator.ultravioletadao.xyz` | live `/health` + `/supported` (gasless, ~2s); fallback PayAI |

Mainnet (for the stretch bonus): USDC `0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E`, registry
`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`, RPC `https://api.avax.network/ext/bc/C/rpc`,
network `eip155:43114`.

## What changed (file by file)

**Net-new**
- `src/ictbot/api/x402_server.py` — the x402 **server**, built on the **x402 SDK**: `x402ResourceServer`
  + `HTTPFacilitatorClient` + a `PaymentOption(price=AssetAmount(Fuji-USDC))`, mounted as
  `PaymentMiddlewareASGI` gating `GET /x402/regime-report`. An outer `X402LedgerMiddleware` reads the
  SDK's `PAYMENT-RESPONSE` header (settlement runs *after* the handler) and journals a `SETTLED` row
  to the provider ledger (`data/x402/server_jobs.jsonl`) → `server_stats()` for the dashboard.
  `pay_and_fetch()` = the agent-pays-its-own-server loop via the **x402 SDK sync client**.
- `src/ictbot/agent/erc8004_client.py` — a **web3.py ERC-8004 client over the canonical reference ABI**
  (`register` / `setMetadata` / `getMetadata` / `tokenURI` / `ownerOf`); parses the `Registered` event
  for the agentId; signs with eth-account + native AVAX gas.
- `src/ictbot/agent/abis/IdentityRegistry.json` — the vendored canonical ERC-8004 ABI.
- `scripts/avax_derisk.py` (wallet bootstrap + Fuji EIP-3009 spike) and `scripts/avax_demo.py`
  (the one-shot pay→get-paid + mint + heartbeat loop).
- `tests/test_avax_x402_port.py` — SDK integration unit tests (the real 402 challenge in the
  `payment-required` header, the ERC-8004 client surface, the identity adapter, Snowtrace base).
- `docs/AVAX_DELTA.md` — this file.

**Config retarget**
- `pyproject.toml` — a new `[x402]` extra (`x402[fastapi,httpx,evm]` 2.13.1 + eth-account + web3).
  `bnbagent` kept under `[bnb]` only for the out-of-scope ERC-8183 commerce + BSC path.
- `src/ictbot/settings.py` — `agent_network` Literal gains `avax-testnet`/`avax`; new fields
  `avax_rpc_url`, `x402_usdc_avax_address`, `erc8004_registry_avax`, `x402_network`, `x402_price_units`,
  `x402_facilitator_url`, `x402_server_url`, `x402_server_enabled`. Removed the dead Base-only x402
  fields + the SDK-superseded wire fields (`x402_version`/`x402_header`/`x402_settle_mode`).
  Chain-neutral, payments-forward `agent_description`.
- `src/ictbot/data/x402_cmc.py` — STRIPPED to the lean key-free web3 reads (`usdc_balance`,
  `payment_address`, `base_usdc_balance` alias) the dashboard imports. All bnbagent EIP-3009 signing
  + the CMC-on-Base x402 functions removed (signing now lives in the x402 SDK).
- `src/ictbot/agent/identity.py` — the avax branch of `_agent()` returns a `_Erc8004AvaxAdapter` over
  `erc8004_client` (web3), replacing bnbagent on Avalanche while preserving the
  `register_agent`/`set_metadata`/`get_metadata` seam. `register_identity`/`write_heartbeat`/
  `read_heartbeat` return shapes unchanged; BSC path still on bnbagent.

**Dashboard + API reads**
- `src/ictbot/api/app.py` — mounts the x402 router + the SDK payment middleware (guarded).
- `src/ictbot/api/reads.py` — Snowtrace explorer base for `avax-*`; new `x402_server` block in the
  snapshot (served jobs + USDC revenue + last settlement tx).
- `src/ictbot/api/schemas.py` — `X402ServerOut` model on the commerce block.
- `src/ictbot/api/onchain.py` — Snowtrace links; an Avalanche "real funds" card (agent AVAX + USDC)
  that replaces the BSC trading-wallet read on the avax path.
- `web/src/lib/format.ts` — `getExplorerBase()` (Snowtrace/BscScan) + Avalanche network labels;
  `web/src/components/{AgentCommercePanel,IdentityCard,HeroRow,StackStrip}.tsx` use it; the commerce
  panel renders the x402-server tiles + a Snowtrace settlement link; `web/src/api/types.ts` adds
  `X402Server`.

**Out of scope (untouched, per the hard rules):** the spot-trading execution layer
(`src/ictbot/exec/*`), the trading brain (off-chain Python by necessity).

## Run it

```bash
# 0) install the real SDKs (the official x402 SDK + web3 for canonical ERC-8004)
python -m pip install -e ".[x402,api,bnb,dev]"

# 1) mint + fund the agent wallet (prints the address + faucet links)
python scripts/avax_derisk.py keygen
#    fund AVAX (core.app faucet) + Fuji USDC (faucet.circle.com), then:
python scripts/avax_derisk.py settle        # real transferWithAuthorization tx on testnet.snowtrace.io

# 2) put AGENT_PRIVATE_KEY / AGENT_IDENTITY_ADDRESS + AGENT_NETWORK=avax-testnet + X402_SERVER_ENABLED=1
#    + X402_SERVER_URL=http://127.0.0.1:8000 in .env, then run the API (dashboard + x402 server)
ictbot-api      # or: uvicorn ictbot.api.app:app --port 8000

# 3) the agent pays its OWN server (agent-to-agent) via the x402 SDK client — a real Fuji settlement
curl -is localhost:8000/x402/regime-report | grep -i payment-required   # the SDK 402 challenge
python -c "from ictbot.api.x402_server import pay_and_fetch; print(pay_and_fetch('http://localhost:8000'))"

# — or the one-shot headline: pay→get-paid (x402) + mint ERC-8004 identity + heartbeat, all on
#   Fuji, printing every Snowtrace tx (needs the funded wallet):
make avax_demo            # or: python scripts/avax_demo.py   (--no-mint / --no-x402 to scope)
```

## Verification status (truthfulness)

Per the hard rule, "deployed on Avalanche C-Chain" is only claimed once Section 8 of the spec passes.
Done so far (this branch): integrated the **official x402 SDK** (2.13.1) + the **canonical ERC-8004
contracts** via web3 (bnbagent removed from the avax paths); EIP-712 domain verified on-chain; Fuji
USDC + ERC-8004 registry presence verified via `eth_getCode` (live `ownerOf` read returns a real
address); the SDK emits the correct 402 challenge (Fuji USDC, `eip155:43113`) live against the
Ultravioleta facilitator; full test suite (1568) green. **Pending a funded wallet:** the live on-chain
settlement tx + the ERC-8004 mint + heartbeat tx (`make avax_demo`, then link the Snowtrace txns here).

> Note: the June-2026 Speedrun submission deadline is on the Team1 India form
> (`india.team1.network/speedrun/june-2026`) — confirm it before the cutoff.
