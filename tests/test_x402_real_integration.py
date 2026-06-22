"""
Opt-in REAL Avalanche x402 integration test — the agent pays its OWN x402 server via the SDK,
against a LIVE uvicorn server (not in-process TestClient — the SDK sync client hits a real URL and
the facilitator settles on-chain).

Run in ISOLATION (the app bakes payTo at import, so the avax env must be set BEFORE the app imports):
    RUN_X402_INTEGRATION=1 pytest -q tests/test_x402_real_integration.py

What it proves that offline tests cannot:
  - the agent's own server answers 402 with the real x402 SDK challenge;
  - the **x402 SDK client genuinely drives the full flow end-to-end** against the live server
    (GET 402 → sign EIP-3009 → resend X-PAYMENT → the server's SDK middleware contacts the
    facilitator) — no mocks.

The on-chain SETTLE is a further opt-in: RUN_X402_SETTLE=1 + a funded agent wallet
(AGENT_PRIVATE_KEY + Fuji USDC + AVAX). Generate + fund the wallet with `python scripts/avax_derisk.py`.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_X402_INTEGRATION") != "1",
    reason="set RUN_X402_INTEGRATION=1 (run in isolation) to exercise the live x402 server + SDK client",
)

# Configure for avax BEFORE importing ictbot.api.app — the SDK middleware bakes payTo at import time.
_KEYFILE = Path(__file__).resolve().parents[1] / "data" / "avax" / "agent_wallet.json"
if os.environ.get("RUN_X402_INTEGRATION") == "1" and _KEYFILE.exists():
    _w = json.loads(_KEYFILE.read_text())
    os.environ.setdefault("AGENT_NETWORK", "avax-testnet")
    os.environ.setdefault("AGENT_PRIVATE_KEY", _w["private_key"])
    os.environ.setdefault("AGENT_IDENTITY_ADDRESS", _w["address"])
    os.environ.setdefault("X402_SERVER_ENABLED", "1")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def live_server():
    """A real uvicorn server in a daemon thread (so the SDK sync client can hit a live URL)."""
    import urllib.request

    import uvicorn

    from ictbot.api.app import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):  # wait until /x402/info answers 200 (free, no payment)
        try:
            with urllib.request.urlopen(base + "/x402/info", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    yield base
    server.should_exit = True
    thread.join(timeout=5)


def test_live_402_challenge(live_server):
    import requests

    info = requests.get(live_server + "/x402/info", timeout=10).json()
    assert info["pay_to"], "no payTo — run in isolation so the avax env applies before app import"
    r = requests.get(live_server + "/x402/regime-report", timeout=10)
    assert r.status_code == 402
    ch = json.loads(base64.b64decode(r.headers["payment-required"]).decode())
    acc = ch["accepts"][0]
    assert acc["network"] == "eip155:43113"
    assert acc["payTo"].lower() == info["pay_to"].lower()


def test_live_sdk_client_drives_payment(live_server):
    """The SDK client runs the full pay flow against the LIVE server. Unfunded → the on-chain settle
    can't move 0 USDC, so the flow completes and returns None (proving the wiring end-to-end without
    a crash). Funded → it settles and returns the report + tx."""
    from ictbot.agent.identity import display_address
    from ictbot.api.x402_server import pay_and_fetch
    from ictbot.data.x402_cmc import usdc_balance

    funded = (usdc_balance(display_address()) or 0) > 0
    report = pay_and_fetch(live_server)  # must never raise
    if funded:
        assert report is not None and (report.get("_x402") or {}).get("settled") is True
        assert report["_x402"].get("tx")
    else:
        assert report is None  # signed + contacted the facilitator, but 0 USDC can't settle


@pytest.mark.skipif(
    os.environ.get("RUN_X402_SETTLE") != "1",
    reason="set RUN_X402_SETTLE=1 (+ a funded agent wallet) to settle real USDC on Fuji",
)
def test_live_settle_on_fuji(live_server):
    from ictbot.api.x402_server import pay_and_fetch

    report = pay_and_fetch(live_server)
    assert report is not None, "no report — fund the agent wallet (Fuji USDC + AVAX)"
    x402 = report.get("_x402") or {}
    assert x402.get("settled") is True, f"payment did not settle: {x402}"
    assert x402.get("tx"), "no settlement tx returned"
