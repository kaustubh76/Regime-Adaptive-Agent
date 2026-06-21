"""
One guarded commerce control: create + serve a REAL ERC-8183 job end-to-end so the agent's
on-chain job ledger fills with a genuine served job (the "buy side" the dashboard was missing).

SAFETY CONTRACT (mirrors controls.py):
  - OPERATOR-LOCAL ONLY. The full loop signs on BOTH sides (provider identity keystore + a DISTINCT
    buyer keystore), so it runs only where both passwords are set. The read-only cloud deploy has
    neither → `commerce.buyer_available()` is False → this returns 403 and never attempts to sign.
  - Real on-chain round-trips are slow + must not overlap, so a single in-flight job is allowed
    (409 while busy). The work runs off the event loop via `asyncio.to_thread`.
  - The response is PUBLIC job metadata only (ids, hashes, amounts, public addresses) — never a
    secret. The deliverable itself is public CMC market analysis (see commerce.on_job).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ictbot.agent import commerce
from ictbot.api.schemas import CommerceCreateJobIn, CommerceCreateJobOut

router = APIRouter(prefix="/api/commerce")

_job_lock = asyncio.Lock()


@router.post("/create-job", response_model=CommerceCreateJobOut)
async def create_job(body: CommerceCreateJobIn):
    if not commerce.buyer_available():
        # Operator-only: no signing key in this process (the cloud deploy is intentionally inert).
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "message": "operator-only: ERC-8183 job creation needs ERC8183_ENABLED, the SDK, "
                "and BOTH AGENT_WALLET_PASSWORD + CLIENT_WALLET_PASSWORD (a distinct buyer keystore) "
                "set locally — unavailable on the read-only deploy.",
            },
        )
    if _job_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"ok": False, "message": "a commerce job is already in flight — try again shortly"},
        )
    async with _job_lock:
        try:
            result = await asyncio.to_thread(
                commerce.create_and_serve_job,
                body.description,
                amount=body.amount,
                expiry_min=body.expiry_min,
            )
        except Exception as e:  # surfaced to the UI, never crashes the server
            return CommerceCreateJobOut(ok=False, message=f"create-job failed: {e}")
    return CommerceCreateJobOut(**result)
