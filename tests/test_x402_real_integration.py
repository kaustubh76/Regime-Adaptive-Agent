"""
Opt-in REAL Avalanche x402 integration test — the agent pays its OWN x402 server via the SDK.

Skipped by default (no funded wallet / live server in CI). Activate with:
    RUN_X402_INTEGRATION=1 pytest -q tests/test_x402_real_integration.py

What it verifies that offline tests cannot: the agent's own x402 server answers 402 with the real
x402 SDK challenge (in the `payment-required` header).

The on-chain SETTLE is a separate opt-in: set RUN_X402_SETTLE=1 AND run a LIVE server
(`make api`; set X402_SERVER_URL=http://127.0.0.1:8000) AND fund the agent wallet (AGENT_PRIVATE_KEY
+ Fuji USDC + AVAX). Then the x402 SDK client pays the live server and the Ultravioleta facilitator
settles on Fuji. (The SDK client is async over the network, so it needs a real server — not the
in-process TestClient.) Generate + fund the wallet with `python scripts/avax_derisk.py`.
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from ictbot.settings import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_X402_INTEGRATION") != "1",
    reason="set RUN_X402_INTEGRATION=1 to exercise the agent's own Avalanche x402 server",
)


def test_server_challenge_is_payable():
    from fastapi.testclient import TestClient

    from ictbot.api.app import app

    r = TestClient(app).get("/x402/regime-report")
    assert r.status_code == 402, r.text
    hdr = r.headers.get("payment-required")
    assert hdr, "no x402 challenge in the payment-required header"
    challenge = json.loads(base64.b64decode(hdr).decode())
    acc = challenge["accepts"][0]
    assert acc["network"] == settings.x402_network
    assert acc["asset"] == settings.x402_usdc_avax_address
    assert acc["scheme"] == "exact"


@pytest.mark.skipif(
    os.environ.get("RUN_X402_SETTLE") != "1",
    reason="set RUN_X402_SETTLE=1 (+ a LIVE server + funded wallet) to settle real USDC on Fuji",
)
def test_pay_own_server_settles():
    """Full real settle on Fuji — the agent pays its OWN running x402 server via the official x402
    SDK client; the Ultravioleta facilitator settles on-chain and returns the tx. Needs a LIVE
    server (X402_SERVER_URL) + a funded AGENT wallet."""
    from ictbot.api.x402_server import pay_and_fetch

    base = settings.x402_server_url or "http://127.0.0.1:8000"
    report = pay_and_fetch(base)
    assert report is not None, f"no report — is a live x402 server running at {base}?"
    x402 = report.get("_x402") or {}
    assert x402.get("settled") is True, f"payment did not settle: {report.get('_x402')}"
    assert x402.get("tx"), "no settlement tx returned"
