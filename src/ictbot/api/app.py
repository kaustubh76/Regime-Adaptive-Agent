"""
FastAPI app for the "Mission Control" dashboard.

Serves a read-only view of the momentum agent (health, identity, strategy, NAV +
drawdown, regime/F&G, recent rebalances, and the agent's rationale feed) plus two
guarded demo controls (sim-tick, kill switch — see controls.py). When `web/dist`
exists it also serves the built React SPA at `/` (same origin → no CORS).

Deployment shapes:
  - Local / single host: serves SPA + API on one origin (CORS off).
  - Split (Vercel SPA + this API on Render): set API_CORS_ORIGINS to the SPA origin
    (or "*"); the SPA calls this API cross-origin.

Run:
  make api                                  # uvicorn ... --reload (dev)
  ictbot-api                                # console script → run() below
  uvicorn ictbot.api.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ictbot.api import reads
from ictbot.api.schemas import (
    AgentHubOut,
    AgentHubPingOut,
    CmcApiOut,
    HealthOut,
    IdentityOut,
    MarketIntelOut,
    NavOut,
    PillarsOut,
    RationaleOut,
    RebalancesOut,
    RegimeOut,
    SnapshotOut,
    StateOut,
    StrategyOut,
    WalletOut,
)
from ictbot.settings import PROJECT_ROOT, settings


async def _seed_once() -> None:
    """Best-effort: if the journal is empty, run ONE sim tick so a freshly-deployed
    API has real data to show. Gated by API_SEED_ON_START; fully isolated."""
    try:
        if reads.read_journal():
            return
        from ictbot.api.controls import _load_tick

        tick = _load_tick()
        await asyncio.to_thread(tick, "sim", settings.max_drawdown_frac)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("API_SEED_ON_START"):
        asyncio.create_task(_seed_once())
    yield


app = FastAPI(
    title="Avalanche Momentum Agent — Mission Control API",
    description="Read-only dashboard backend for the regime-adaptive momentum allocator.",
    version="0.1.0",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    """Allowed origins from API_CORS_ORIGINS (comma-separated, or '*'). Dev adds the
    Vite origin when API_DEV_CORS is set. Empty → CORS middleware not installed."""
    raw = os.environ.get("API_CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if os.environ.get("API_DEV_CORS"):
        origins += ["http://localhost:5173", "http://127.0.0.1:5173"]
    return origins


_origins = _cors_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

api = APIRouter(prefix="/api")


@api.get("/health", response_model=HealthOut)
def health():
    return reads.health_card()


@api.get("/identity", response_model=IdentityOut | None)
def identity():
    return reads.identity_card()


@api.get("/strategy", response_model=StrategyOut | None)
def strategy():
    return reads.strategy_card()


@api.get("/state", response_model=StateOut)
def state():
    return reads.state_card()


@api.get("/nav", response_model=NavOut)
def nav():
    return reads.nav_card()


@api.get("/regime", response_model=RegimeOut)
def regime():
    return reads.regime_card()


@api.get("/rebalances", response_model=RebalancesOut)
def rebalances(n: int = 10):
    return reads.rebalances_card(n)


@api.get("/rationale", response_model=RationaleOut)
def rationale(n: int = 20):
    return reads.rationale_card(n)


@api.get("/pillars", response_model=PillarsOut)
def pillars():
    return reads.pillars_card()


@api.get("/wallet", response_model=WalletOut)
def wallet():
    return reads.wallet_card()


@api.get("/market-intel", response_model=MarketIntelOut)
def market_intel():
    return reads.market_intel_card()


@api.get("/cmc-api", response_model=CmcApiOut)
def cmc_api():
    return reads.cmc_api_card()


@api.get("/agent-hub", response_model=AgentHubOut)
def agent_hub():
    """CMC Agent Hub exhibit — Data MCP call counts + the composed market-overview skill
    (regime, risk budget, derivatives/macro/quotes/news) + x402 receipts."""
    return reads.agent_hub_card()


@api.get("/agent-hub/ping", response_model=AgentHubPingOut)
def agent_hub_ping():
    """LIVE on-demand proof: makes a REAL CMC MCP call (tools/list + sample tools/call) + a fresh
    composed-Skill read at request time. Shows the MCP + Skill genuinely work on THIS server — not
    seeded snapshot data. Button-triggered (the panel's 'test hub'); never on the poll loop."""
    return reads.agent_hub_ping()


@api.get("/snapshot", response_model=SnapshotOut)
def snapshot():
    return reads.snapshot()


app.include_router(api)

# Guarded demo controls (sim-tick + kill switch). Imported after the read router so
# its POST routes register too; isolated so the read surface stays auditable.
try:
    from ictbot.api.controls import router as controls_router

    app.include_router(controls_router)
except Exception:  # pragma: no cover - controls are optional at boot
    pass

# Guarded commerce control (create + serve a real ERC-8183 job). Operator-local only — its guard
# (commerce.buyer_available()) is False on the read-only deploy, so the route returns 403 there.
try:
    from ictbot.api.commerce_controls import router as commerce_router

    app.include_router(commerce_router)
except Exception:  # pragma: no cover - commerce controls are optional at boot
    pass

# x402 SERVER (the agent GETS PAID): a 402-gated endpoint other agents pay USDC to read the CMC
# Regime Report, settled on Avalanche via the x402 SDK + Ultravioleta facilitator. The router holds
# /x402/info + the /x402/regime-report handler; mount_payment_middleware() adds the SDK payment
# middleware (gates the route, unpaid GET -> 402 challenge) + the ledger middleware. Both guarded —
# a missing `x402` extra (ImportError) just skips the server. This is the headline of the port.
try:
    from ictbot.api import x402_server

    app.include_router(x402_server.router)
    try:
        x402_server.mount_payment_middleware(app)
    except Exception:  # pragma: no cover - the x402 SDK extra may be absent; /info still serves
        pass
except Exception:  # pragma: no cover - x402 server is optional at boot
    pass


@app.get("/config.json")
def spa_config() -> dict:
    """Runtime API base for the SPA when THIS app serves it. Always same-origin (`apiBase: ""`) — the
    SPA talks to the very server that served it, on EVERY hostname (localhost, 0.0.0.0, a LAN IP, or
    the Render URL). This wins over the static `dist/config.json` because it's an explicit route,
    registered before the catch-all `/` StaticFiles mount.

    Why same-origin is always right HERE: a server that serves the bundle also answers `/api/*`, so
    pointing the SPA elsewhere never makes sense. The keyed local `make api_commerce` run gets a
    `can_create:true` snapshot regardless of which printed URL the operator opens (the bug this
    fixes). The PUBLIC Vercel deploy is unaffected — it's static CDN, not this app, and its own
    `config.json` (→ Render) is written separately by scripts/deploy_dashboard.sh."""
    return {"apiBase": ""}


def _mount_spa() -> None:
    """Serve the built Vite SPA from web/dist at '/' (after the API routes win).
    No-op when the bundle isn't present (e.g. the API-only Render service)."""
    from fastapi.staticfiles import StaticFiles

    dist = PROJECT_ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")


_mount_spa()


def run() -> None:
    """Console-script entrypoint (`ictbot-api`). chdir to the repo root FIRST so
    kill_switch's relative `data/` + `.env` paths resolve correctly regardless of
    where the process was launched, then serve binding $PORT (Render injects it)."""
    import uvicorn

    os.chdir(PROJECT_ROOT)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
