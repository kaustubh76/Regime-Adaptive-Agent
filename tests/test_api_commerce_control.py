"""POST /api/commerce/create-job — the operator-local "create a real ERC-8183 job" control.

Gated on fastapi (the `[api]` extra). The real loop signs on-chain, so these tests NEVER touch the
chain: they assert the guard (403 on the read-only deploy) and monkeypatch the orchestrator to
verify the success + precheck response shapes.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # TestClient transport

from fastapi.testclient import TestClient  # noqa: E402

from ictbot.agent import commerce  # noqa: E402


@pytest.fixture
def client():
    from ictbot.api.app import app

    return TestClient(app)


def test_create_job_operator_only_403_without_keys(client, monkeypatch):
    # The read-only deploy has no signing key → buyer_available() is False → 403, no signing.
    monkeypatch.setattr(commerce, "buyer_available", lambda: False)
    r = client.post("/api/commerce/create-job", json={"description": "regime read"})
    assert r.status_code == 403
    body = r.json()
    assert body["ok"] is False
    assert "operator-only" in body["message"]


def test_create_job_success_shape(client, monkeypatch):
    monkeypatch.setattr(commerce, "buyer_available", lambda: True)

    def _fake_loop(query, *, amount=None, expiry_min=60):
        assert query == "regime read"  # request body flows through
        return {
            "ok": True, "stage": "served", "job_id": 42, "status": "COMPLETED", "tx": "0xabc",
            "deliverable_hash": "0xdef", "deliverable_url": "ipfs://QmDeliv",
            "buyer": "0xB", "provider": "0xP", "amount": 10000, "token": "U",
        }

    monkeypatch.setattr(commerce, "create_and_serve_job", _fake_loop)
    r = client.post("/api/commerce/create-job", json={"description": "regime read"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["job_id"] == 42 and body["tx"] == "0xabc"
    # The deliverable (IPFS) + the loop stage must survive the response model so the UI can link it.
    assert body["deliverable_url"] == "ipfs://QmDeliv"
    assert body["stage"] == "served"


def test_create_job_insufficient_balance_precheck(client, monkeypatch):
    # The orchestrator returns an actionable fund-precheck dict; buyer/need/have + the loop `stage`
    # survive the response model so the UI can show the funding hint AND distinguish failure modes.
    monkeypatch.setattr(commerce, "buyer_available", lambda: True)
    monkeypatch.setattr(
        commerce, "create_and_serve_job",
        lambda q, **k: {"ok": False, "stage": "fund-precheck", "buyer": "0xB",
                        "token": "U", "need": 10000, "have": 0, "message": "faucet-fund 0xB"},
    )
    r = client.post("/api/commerce/create-job", json={"description": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["need"] == 10000 and body["have"] == 0
    assert body["buyer"] == "0xB"
    assert body["stage"] == "fund-precheck"  # now declared → distinguishes precheck from a loop error


def test_commerce_jobs_surfaces_deliverable_url(tmp_path, monkeypatch):
    # The ledger reader must surface the served job's IPFS deliverable URL (+ hash/tx) so the public
    # dashboard can link straight to the real product — not just show a bare hash.
    from ictbot.api import reads

    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / "commerce_jobs.jsonl").write_text(
        '{"event":"CREATE","job_id":7}\n'
        '{"event":"FUND","job_id":7,"amount":100000000000000000}\n'
        '{"event":"SUBMITTED_ONCHAIN","job_id":7,"tx":"0xfeed",'
        '"deliverable_hash":"0xhash","deliverable_url":"ipfs://QmABC"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(reads, "DATA_DIR", tmp_path)
    out = reads._commerce_jobs()
    assert out["jobs_served"] == 1
    assert out["last_deliverable_url"] == "ipfs://QmABC"
    assert out["last_deliverable_hash"] == "0xhash"
    assert out["last_tx"] == "0xfeed"


def test_create_job_never_500_on_loop_error(client, monkeypatch):
    monkeypatch.setattr(commerce, "buyer_available", lambda: True)

    def _boom(q, **k):
        raise RuntimeError("rpc down")

    monkeypatch.setattr(commerce, "create_and_serve_job", _boom)
    r = client.post("/api/commerce/create-job", json={"description": "x"})
    assert r.status_code == 200  # surfaced as ok:false, never crashes the server
    body = r.json()
    assert body["ok"] is False and "rpc down" in body["message"]
