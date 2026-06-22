# Deploy the Avalanche "Mission Control" dashboard

Two pieces, already split:

```
  Vercel (React SPA)  ──fetch /api/*──▶  Render (read-only FastAPI)
  avax-agentic-payments.vercel.app      avax-agentic-payments-api.onrender.com
```

- **UI** — the React SPA in [`web/`](../web), live on Vercel:
  <https://avax-agentic-payments.vercel.app>
- **API** — the lean read-only FastAPI on Render, surfacing the agent's Avalanche
  legs (CMC/x402 data + revenue · ERC-8004 on-chain identity).

This is the Avalanche Agentic-Payments dashboard. The Render image is **API-only and
lean**: no SPA build, and no Streamlit/Plotly (those are the opt-in `[ui]` extra now,
not core deps).

- Blueprint: [`render.yaml`](../render.yaml)
- Image: [`infra/Dockerfile.dashboard`](../infra/Dockerfile.dashboard) — `pip install .[api,x402]`, `CMD ictbot-api`

---

## Part A — Render API

### 1. Push

```bash
git add render.yaml infra/Dockerfile.dashboard .dockerignore pyproject.toml \
        web/public/config.json docs/deploy_dashboard.md
git commit -m "deploy(dashboard): lean API-only Render blueprint; SPA stays on Vercel"
git push
```

### 2. Create the Blueprint

[Render Dashboard](https://dashboard.render.com) → **New +** → **Blueprint** →
connect this repo. Render detects [`render.yaml`](../render.yaml) and proposes
**`avax-agentic-payments-api`** (Docker, free). **Apply**. First build ~2–3 min.

### 3. Secrets — set NONE (zero-secret deploy)

**Render free tier has no account 2FA**, so we deploy **zero secrets** — nothing to
leak if the account is ever compromised. Leave the Environment tab empty; every var
is a committed non-secret in `render.yaml` (`AGENT_NETWORK=avax-testnet`, the **public**
`AGENT_IDENTITY_ADDRESS`, the X402 *display-only* vars, `API_SEED_ON_START=1`, the Vercel
CORS origin). The dashboard runs fully on public on-chain data + the committed snapshot.

> 🔒 **Never set on Render:** `AGENT_PRIVATE_KEY`, `AGENT_WALLET_PASSWORD` — and without
> 2FA, not even `CMC_API_KEY`. All keys stay local. The dashboard never signs, mints, or
> pays, so it needs no key.

**Optional (only if you accept the no-2FA risk):**

| Key | Risk | Adds |
|---|---|---|
| `CMC_API_KEY` | low — rate-limited **data** key (can't move funds) | live Fear & Greed + USD pricing (else from the snapshot) |

### 4. Verify

```bash
curl https://avax-agentic-payments-api.onrender.com/api/health      # {"ok":true,...}
curl -s https://avax-agentic-payments-api.onrender.com/api/pillars   # ERC-8004 identity: chain_id / agent_id
# CORS preflight from the Vercel origin:
curl -si -X OPTIONS https://avax-agentic-payments-api.onrender.com/api/snapshot \
     -H 'Origin: https://avax-agentic-payments.vercel.app' \
     -H 'Access-Control-Request-Method: GET' | grep -i access-control-allow-origin
```

---

## Part B — Point the Vercel SPA at the Render API

The SPA resolves its API base from [`web/public/config.json`](../web/public/config.json)
(runtime) or the `VITE_API_BASE` build env (takes precedence). `config.json` is
already set to `https://avax-agentic-payments-api.onrender.com`.

- **If the Render service URL matches** that value → just **redeploy on Vercel**
  (push, or Vercel → Deployments → Redeploy) so it picks up the committed
  `config.json`. The dashboard now polls live data + shows `live api` in the
  freshness chip.
- **If the URL differs** (name taken → random suffix) → either edit
  `web/public/config.json` to the real URL and redeploy, or set
  `VITE_API_BASE=https://<your-api>.onrender.com` in Vercel → Settings →
  Environment Variables and redeploy.

> CORS: the API allows the Vercel origin via `API_CORS_ORIGINS` in `render.yaml`.
> If you use a different Vercel domain, update that value (comma-separated list,
> or `*` for any origin) and redeploy Render.

---

## Security & 2FA

The agent's signing key controls its on-chain identity + its x402 wallet, so the
deploy is designed to keep **every fund-controlling secret OFF the cloud**.

**1. Never deploy a signing key to the dashboard.** It's read-only — it shows the
identity wallet via the **public** `AGENT_IDENTITY_ADDRESS` and reads balances by
address. `AGENT_PRIVATE_KEY` and `AGENT_WALLET_PASSWORD` stay **only on your local
machine** (where the agent signs, mints, and pays). The blueprint does not list them;
don't add them.

**2. Keep funds minimal.** The agent wallet (`0xA9aa558b0a8006390f01A89824832086C080904a`)
is a **throwaway Avalanche Fuji testnet** wallet holding only faucet USDC + AVAX gas —
a worst-case key compromise loses testnet funds only. (For a mainnet run, keep just a
few dollars of USDC for x402 micropayments.)

**3. Turn on 2FA everywhere these keys live or deploy from:**

| Account | 2FA | Why / mitigation |
|---|---|---|
| **GitHub** (`kaustubh76/Regime-Adaptive-Agent`) | enable | 2FA stops a takeover from exposing history |
| **Render** | ❌ not on free plan | **can't enable 2FA on free** → mitigated by deploying **zero secrets** (nothing to leak) |
| **Vercel** | enable | controls the deployed UI + its env (no secrets there either) |
| **CoinMarketCap** | enable | controls the API key/quota (key kept local) |

> Because Render free has no 2FA, the deploy is built so a Render compromise leaks
> **nothing** — no key is stored there. That's the whole point of the zero-secret design.

**4. Rotate anything that was ever exposed.** `.env` is git-ignored; if it was ever
committed, rotate `CMC_API_KEY` and **re-create the agent wallet** if `AGENT_PRIVATE_KEY`
was ever committed.

**5. Tighten CORS** once stable: `API_CORS_ORIGINS` is pinned to your Vercel origin
(not `*`), so only your SPA can call the API from a browser.

## Dynamism & persistence

- **Live by design:** the identity + x402 pillars (on-chain identity, x402 wallet/
  balance/served-jobs/revenue) are computed server-side per request with a 60 s TTL
  cache — dynamic on every plan.
- **Free tier** has no persistent disk and sleeps after 15 min idle, so the journal
  is **reseeded** (one sim tick) on each cold start. Keep it warm with an
  [UptimeRobot](https://uptimerobot.com) HTTP monitor on `/api/health` every 5 min.
- **Continuously-updating NAV feed (paid):** upgrade the instance, add a disk so the
  journal persists, and run the allocator loop alongside the API. In `render.yaml`,
  under the service:

  ```yaml
      disk:
        name: avax-data
        mountPath: /app/data
        sizeGB: 1
  ```

  then schedule `python scripts/run_allocator.py --loop --interval-min 240`. The API
  reads the growing `data/journal/allocator_journal.jsonl` and the NAV curve advances.

## Static fallback

The SPA also ships a committed `web/public/snapshot.json` (offline fallback for when
the API is cold). Refresh it before a Vercel deploy with `make snapshot` (or
`make refresh_dashboard` to reseed the Render image too).

---

## Operations

| Task | How |
|---|---|
| Tail API logs | Render → service → **Logs** |
| Redeploy API | push to the connected branch (auto-deploy on) |
| Redeploy SPA | Vercel → Deployments → Redeploy (or push) |
| Update env | Render → service → **Environment** → edit → Save |
| Show the live track | set `DASHBOARD_JOURNAL=live` once the live track runs |
| Run the old Streamlit UI locally | `pip install -e ".[ui]"` then `streamlit run src/ictbot/ui/app.py` |
