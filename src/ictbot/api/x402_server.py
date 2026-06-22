"""
x402 SERVER — the agent GETS PAID (built on the official `x402` Python SDK).

The repo already PAYS for data over x402 (consumer). This module adds the SELL side the "Agentic
Payments" track wants: a 402-gated HTTP endpoint other agents pay USDC (EIP-3009) to read the
agent's live **CMC Regime Report**, settled on **Avalanche Fuji** via the **Ultravioleta DAO**
facilitator. This is a REAL SDK integration — the x402 `x402ResourceServer` + `PaymentMiddlewareASGI`
gate the route, and the facilitator verifies + settles on-chain. No hand-rolled HTTP, no bnbagent.

    GET /x402/regime-report
      no / invalid payment  -> 402 + the SDK's x402 challenge (the `accepts` payment options)
      valid payment         -> the SDK verifies + settles via the facilitator, the handler returns
                               the report, and the SDK sets the `PAYMENT-RESPONSE` header (the tx)

Settlement happens INSIDE the middleware AFTER the route handler runs, so the handler can't see the
tx hash. We therefore journal the settlement from an OUTER middleware (`X402LedgerMiddleware`) that
reads the `PAYMENT-RESPONSE` header — keeping `server_stats()` + the `data/x402/server_jobs.jsonl`
provider ledger + the dashboard fields byte-for-byte compatible.

For the demo the agent pays its OWN server (`pay_and_fetch`, the SDK's sync requests client). The
deliverable (`regime_report.build_report`) is PUBLIC market analysis only — no secret crosses the wire.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter
from starlette.middleware.base import BaseHTTPMiddleware

from ictbot.settings import DATA_DIR, settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/x402", tags=["x402"])

SERVER_LEDGER = DATA_DIR / "x402" / "server_jobs.jsonl"
_ZERO = "0x0000000000000000000000000000000000000000"
# Set True once the x402 payment middleware is mounted. The /regime-report handler refuses to serve
# the report unless this is True — so if the x402 SDK is absent (middleware not mounted), the report
# is NEVER served for free; it always returns 402.
_PAYMENT_GATED = False


# --------------------------------------------------------------------------- #
# Provider identity + ledger (SDK-free — keep importable without the x402 extra)
# --------------------------------------------------------------------------- #
def _provider_address() -> str | None:
    """The wallet that GETS PAID (= the agent identity wallet). Public display address is fine."""
    try:
        from ictbot.agent.identity import display_address

        return display_address()
    except Exception:
        return None


def _journal(event: str, **fields) -> None:
    try:
        SERVER_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
        with SERVER_LEDGER.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def server_stats() -> dict:
    """Summarize the x402 server ledger for the dashboard panel. Zeros if no jobs served yet."""
    out = {"enabled": bool(settings.x402_server_enabled), "served_jobs": 0,
           "revenue_usdc": 0.0, "last_settlement_tx": None, "last_ts": None, "price_usdc": 0.0}
    try:
        out["price_usdc"] = round(int(settings.x402_price_units) / 1e6, 6)
    except Exception:
        pass
    try:
        lines = SERVER_LEDGER.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return out
    units = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (ValueError, TypeError):
            continue
        if r.get("event") == "SETTLED":
            out["served_jobs"] += 1
            try:
                units += int(r.get("value") or 0)
            except (TypeError, ValueError):
                pass
            if r.get("tx"):
                out["last_settlement_tx"] = r.get("tx")
            out["last_ts"] = r.get("ts")
    out["revenue_usdc"] = round(units / 1e6, 6)
    return out


# --------------------------------------------------------------------------- #
# Routes (the handler is pure — the middleware gates + settles)
# --------------------------------------------------------------------------- #
@router.get("/info")
def x402_info():
    """Key-free advertisement of the paid service (the discovery surface for other agents)."""
    return {
        "service": "CMC Regime Report",
        "report_schema": "cmc-regime-report/v1",
        "price_usdc": round(int(settings.x402_price_units) / 1e6, 6),
        "asset": settings.x402_usdc_avax_address,
        "network": settings.x402_network,
        "pay_to": _provider_address(),
        "facilitator": settings.x402_facilitator_url,
        "sdk": "x402",
        "endpoint": "/x402/regime-report",
        "stats": server_stats(),
    }


@router.get("/regime-report")
def regime_report_paid():
    """402-gated CMC Regime Report. The x402 PaymentMiddlewareASGI runs this handler only after the
    payment verifies, and settles + sets the PAYMENT-RESPONSE header afterward — so the handler is
    just the deliverable. If the middleware isn't mounted (x402 SDK absent), refuse to serve free."""
    if not _PAYMENT_GATED:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=402,
            content={"error": "x402 payment required — server not configured (x402 SDK absent)"},
        )
    from ictbot.agent.regime_report import build_report

    return build_report()


# --------------------------------------------------------------------------- #
# x402 SDK wiring (lazy — so this module imports without the x402 extra)
# --------------------------------------------------------------------------- #
def _payment_option():
    from x402 import AssetAmount
    from x402.http import PaymentOption

    return PaymentOption(
        scheme="exact",
        pay_to=_provider_address() or _ZERO,
        network=settings.x402_network,
        price=AssetAmount(
            amount=str(int(settings.x402_price_units)),
            asset=settings.x402_usdc_avax_address,
            extra={"name": "USD Coin", "version": "2"},
        ),
    )


def _routes():
    from x402.http import RouteConfig

    return {
        "GET /x402/regime-report": RouteConfig(
            accepts=_payment_option(),
            mime_type="application/json",
            description="CMC Regime Report — live regime score + momentum ranking (CoinMarketCap)",
        )
    }


def _build_server():
    from x402 import x402ResourceServer
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=settings.x402_facilitator_url))
    server = x402ResourceServer(facilitator)
    server.register(settings.x402_network, ExactEvmServerScheme())
    # Deliberately NO server.initialize() here. The SDK's PaymentMiddlewareASGI initializes lazily on
    # the FIRST paid request (sync_facilitator_on_start=True) and RETRIES on failure — so the boot is
    # non-blocking and a transient facilitator outage self-heals per request. The unpaid-402 challenge
    # never touches the facilitator at all (the middleware emits it before init).
    return server


def mount_payment_middleware(app) -> bool:
    """Gate /x402/regime-report with the x402 SDK middleware + journal settlements via an outer
    ledger middleware. Raises ImportError if the x402 extra is missing — the caller (app.py) guards.

    Starlette runs `add_middleware` in REVERSE order, so adding the ledger middleware FIRST makes it
    the OUTER wrapper that sees the final response headers (incl. PAYMENT-RESPONSE set after settle)."""
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    server = _build_server()
    routes = _routes()
    # Starlette runs the LAST-added middleware OUTERMOST (it processes the response LAST). The x402
    # payment middleware sets the PAYMENT-RESPONSE header AFTER settlement, so the ledger middleware
    # must be added AFTER it (= outermost) to see that header on the final response and journal it.
    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
    app.add_middleware(X402LedgerMiddleware)
    global _PAYMENT_GATED
    _PAYMENT_GATED = True
    return True


# --------------------------------------------------------------------------- #
# Ledger seam — journal a settlement from the PAYMENT-RESPONSE header (set AFTER the handler)
# --------------------------------------------------------------------------- #
def _journal_settled_from_header(header_val: str) -> None:
    try:
        data = json.loads(base64.b64decode(header_val).decode())
    except Exception:
        return
    if not data.get("success"):
        return
    _journal(
        "SETTLED",
        tx=data.get("transaction"),
        value=int(settings.x402_price_units),
        payer=data.get("payer"),
        network=data.get("network") or settings.x402_network,
    )


class X402LedgerMiddleware(BaseHTTPMiddleware):
    """Reads the x402 `PAYMENT-RESPONSE` header off a settled 200 and writes a `SETTLED` row to the
    provider ledger, so `server_stats()` (served jobs + revenue + last tx) stays unchanged."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            if request.url.path.endswith("/x402/regime-report") and response.status_code == 200:
                hdr = response.headers.get("PAYMENT-RESPONSE") or response.headers.get("X-PAYMENT-RESPONSE")
                if hdr:
                    _journal_settled_from_header(hdr)
        except Exception:
            pass
        return response


# --------------------------------------------------------------------------- #
# Consumer — the agent pays its OWN server (sync, via the x402 SDK requests client)
# --------------------------------------------------------------------------- #
def _consumer_key() -> str | None:
    """Signing key for the consumer: AGENT_PRIVATE_KEY, else the de-risk keyfile."""
    if settings.agent_private_key:
        return settings.agent_private_key
    try:
        kf = Path(DATA_DIR) / "avax" / "agent_wallet.json"
        if kf.exists():
            return json.loads(kf.read_text()).get("private_key")
    except Exception:
        pass
    return None


def pay_and_fetch(base_url: str | None = None, timeout: float = 120.0) -> dict | None:
    """The agent pays its OWN x402 server for the report, using the x402 SDK's sync requests client
    (auto 402 → sign EIP-3009 → settle via the facilitator). Returns the report dict (with an
    `_x402` {settled, tx, explorer} block) on success, else None. Drives a LIVE server URL — the
    SDK client signs + the facilitator settles on-chain, so this is a real agent-to-agent payment."""
    key = _consumer_key()
    if not key:
        log.warning("x402 pay_and_fetch needs AGENT_PRIVATE_KEY (or the generated keyfile)")
        return None
    try:
        import requests
        from eth_account import Account
        from x402 import x402ClientSync
        from x402.http.clients import wrapRequestsWithPayment
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client
    except Exception as e:  # noqa: BLE001
        log.warning("x402 SDK/requests unavailable: %s", e)
        return None

    base = (base_url or settings.x402_server_url or "http://127.0.0.1:8000").rstrip("/")
    url = base + "/x402/regime-report"
    try:
        client = x402ClientSync()
        register_exact_evm_client(client, EthAccountSigner(Account.from_key(key)))
        session = wrapRequestsWithPayment(requests.Session(), client)
        r = session.get(url, timeout=timeout)
        if r.status_code != 200:
            log.warning("x402 pay_and_fetch: server returned %s (payment not settled)", r.status_code)
            return None
        report = r.json()
        hdr = r.headers.get("PAYMENT-RESPONSE") or r.headers.get("X-PAYMENT-RESPONSE")
        tx = None
        if hdr:
            try:
                tx = json.loads(base64.b64decode(hdr).decode()).get("transaction")
            except Exception:
                tx = None
        if tx:
            net = str(getattr(settings, "x402_network", "") or "")
            base = "https://snowtrace.io/tx/" if net.endswith("43114") else "https://testnet.snowtrace.io/tx/"
            report.setdefault("_x402", {}).update(settled=True, tx=tx, explorer=f"{base}{tx}")
        return report
    except Exception as e:  # noqa: BLE001
        log.warning("x402 pay_and_fetch failed: %s: %s", type(e).__name__, str(e)[:120])
        return None
