# CMC Agent Hub — captured reference snippets

> Provenance: raw text captured 2026-06 from CoinMarketCap's public x402 and Hackathon pages
> (coinmarketcap.com → AI Integrations). Trimmed 2026-06-12 to the two sections other docs cite:
> the **x402 payment-flow transcript** (cited by [x402_receipts.md](x402_receipts.md) §2) and the
> **hackathon timeline/deadline** (cited by [implementation_audit.md](implementation_audit.md) C3).
> Full pages live at https://coinmarketcap.com/ai/x402 and https://coinmarketcap.com/ai/hackathon.

---

## Section 1 — x402: pay-per-request crypto data (payment-flow transcript)

Power AI Agents with Crypto Data via x402 — instant pay-per-request access to CoinMarketCap
crypto data via x402. No API keys or subscriptions.

```
$ curl -i "https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest?id=1"

HTTP/2 402 PAYMENT REQUIRED
payment-required: eyJ4NDAyVmVyc2lvbiI6MiwiZXJyb3I...

# base64 decode -> payment JSON
# pay, then send PAYMENT-SIGNATURE

{
  "error": "Payment required",
  "resource": "/x402/v3/cryptocurrency/quotes/latest",
  "accepts": [ { scheme: "exact", amount: "0.01" } ]
}
```

### STEP 01 — First Request (Get 402 Challenge)

Call once to get HTTP 402 and a base64 `payment-required` header. Decode it for payment terms.

```
curl -i "https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest?id=1"

< HTTP/2 402
< payment-required: eyJ4NDAyVmVyc2lvbiI6MiwiZXJyb3IiOiJQYXltZW50IHJlcXVpcmVkIiwicmVzb3VyY2UiOnsidXJsIjoiL3g0MDIvdjMvY3J5cHRvY3VycmVuY3kvcXVvdGVzL2xhdGVzdCIsImRlc2NyaXB0aW9uIjoiY21jIGNyeXB0byBxdW90ZSBsYXRlc3QgZGF0YSBhcGkifSwiYWNjZXB0cyI6W3sic2NoZW1lIjoiZXhhY3QiLCJuZXR3b3JrIjoiZWlwMTU1Ojg0NTMiLCJhc3NldCI6IjB4ODMzNTg5ZkNENmVEYjZFMDhmNGM3QzMyRDRmNzFiNTRiZEEwMjkxMyIsImFtb3VudCI6IjEwMDAwIiwicGF5VG8iOiIweDI3MTE4OWM4NjBEQjI1YkM0MzE3M0IwMzM1Nzg0YUQ2OGE2ODA5MDgiLCJtYXhUaW1lb3V0U2Vjb25kcyI6MzAsImV4dHJhIjp7Im5hbWUiOiJVU0QgQ29pbiIsInZlcnNpb24iOiIyIiwieDQwMlBheW1lbnRDb25maWdJZCI6IjY5OWRiYWI3OWYzMmZmZGU2NTAxMDRhYSJ9fV19

< {
  "x402Version": 2,
  "error": "Payment required",
  "resource": {
    "url": "/x402/v3/cryptocurrency/quotes/latest",
    "description": "cmc crypto quote latest data api"
  },
  "accepts": [...]
}
```

### STEP 02 — Second Request (Attach Payment Signature)

Sign the payment according to the returned challenge, then resend the same request with a
`PAYMENT-SIGNATURE` header. This proves authorization for the required USDC amount.

```
curl -i "https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest?id=1" \
  -H "PAYMENT-SIGNATURE: eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9..."

// Required payment terms are returned in Step 01
// network: eip155:8453 (Base)
// asset: USDC
// amount: 0.01 (smallest unit)
```

### STEP 03 — Receive 200 Response Data

After signature verification succeeds, the API immediately returns HTTP 200 with the requested
market data payload.

```
< HTTP/2 200
< {
  "status": { "error_code": 0, "error_message": null },
  "data": { "1": {...} }
}
```

### x402-Enabled Endpoints

| Endpoint | Purpose |
|---|---|
| `/x402/v3/cryptocurrency/quotes/latest` | Latest cryptocurrency quote data |
| `/x402/v3/cryptocurrency/listing/latest` | Latest cryptocurrency listing data |
| `/x402/v4/dex/pairs/quotes/latest` | Latest DEX pair quote data |
| `/x402/v1/dex/search` | Search DEX data |
| `/x402/mcp` | MCP endpoint via x402 |

Each MCP tool call costs 0.01 USDC, charged via the x402 payment protocol (USDC on Base,
chain `eip155:8453`). "This feature is currently in beta and may be subject to change."

---

## Section 2 — Hackathon page (timeline + deadline, as published)

CMC HACKATHON — June 3rd - 21st, 2026 — Build the Autonomous Trading Agent Stack

> **Submission lock - June 21st · 12:00pm UTC**
> ⚠ Note: docs/bnb_hackathon_plan.md §1 records 2026-06-21 **17:30 UTC** from the original brief.
> The two sources disagree by 5.5 h — plan for the EARLIER one (12:00 UTC) until confirmed in
> the hackathon TG (remediation_plan.md Phase 0.1).

2 tracks. $36,000. Agent-native end-to-end. Build on sponsor stack — CoinMarketCap, Trust
Wallet, or BNB Chain. Stack all three to maximize your shot at winning.

### Tracks

- **TRACK 1 — Autonomous Trading Agents.** Trade live on BSC. Read CMC signals, decide, then
  sign and execute via Trust Wallet Agent Kit. PancakeSwap and BSC perps, within user-defined
  rules. (CMC Agent Hub · TWAK · BNB AI Agent SDK · BSC)
- **TRACK 2 — Strategy Skills.** Build CMC Skills that generate trading strategies from market
  data. Ship a backtestable spec, not a live agent. (CMC Agent Hub & Data API · pre-computed
  indicators · Skills Marketplace · x402 optional)
- Tips: *Recommended* — stack all three; projects using CMC + TWT + BNB capabilities have the
  strongest shot. *Required* — build with at least one sponsor capability.

### Prizes

| Rank | Track 1 | Track 2 |
|---|---|---|
| 1st | $10,000 | $3,000 |
| 2nd | $6,000 | $2,000 |
| 3rd | $4,000 | $1,000 |
| 4th & 5th | $2,000 | — |

Special prizes ($2,000 each, stackable): Best Use of CoinMarketCap Data & Signal · Best Use of
Trust Wallet Agent Kit · Best Use of BNB AI Agent SDK.
Benefits: CMC Pro API credits for top winners · Claude API tokens or equivalent · 1 mentor per
finalist team · Kickstart eligibility · TWT Developer Portal listing.

### Timeline

| Date | Milestone |
|---|---|
| June 3rd, 12:00pm UTC | Registration opens (DoraHacks) |
| June 3rd - 21st | Build phase (3 weeks, weekly mentor office hours) |
| **June 21st** | **Submission lock (12:00pm UTC per this page; 17:30 UTC per the brief)** |
| June 22nd - 28th | Live trading window, Track 1 — performance tracked in real market conditions |
| June 29th - July 5th | Judging — live PnL replay window + panel review |
| Week of July 6th | Winners announced (co-published across all 3 partners) |

### FAQ highlights

- Who can participate? Any builder, solo or team, 18+. Must ship a working agent or skill.
- Do I need all three stacks (CMC + TWT + BNB)? At least one sponsor capability required;
  stacking all three recommended.
- Are special prizes stackable with main prizes? (Listed as stackable above.)
