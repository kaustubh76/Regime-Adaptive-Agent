"""CliTwakClient command-construction tests (subprocess mocked — no twak needed)."""

from __future__ import annotations

import json
import subprocess

import pytest

from ictbot.exec.twak_client import BSC_TOKENS, CliTwakClient


class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _patch(monkeypatch, payload, rc=0):
    calls: dict = {}

    def fake_run(argv, **kw):
        calls["argv"] = argv
        calls["env"] = kw.get("env")
        return _FakeProc(json.dumps(payload), rc)

    monkeypatch.setattr("ictbot.exec.twak_client.subprocess.run", fake_run)
    return calls


def _client(price_fn=None):
    # Pin an explicit address + binary so the argv is deterministic regardless of the ambient
    # .env (AGENT_TRADING_ADDRESS / TWAK_BINARY — a cron .env sets the absolute nvm path).
    return CliTwakClient(
        binary="twak",
        access_id="aid",
        hmac_secret="hs",
        wallet_password="pw",
        address="0x000000000000000000000000000000000000dEaD",
        price_fn=price_fn,
    )


def test_price_builds_argv_and_injects_creds(monkeypatch):
    calls = _patch(monkeypatch, {"token": "BNB", "chain": "bsc", "priceUsd": 596.3})
    px = _client().price("BNB")
    assert px == 596.3
    assert calls["argv"] == ["twak", "price", "BNB", "--chain", "bsc", "--json"]
    assert calls["env"]["TWAK_ACCESS_ID"] == "aid"
    assert calls["env"]["TWAK_HMAC_SECRET"] == "hs"
    assert calls["env"]["TWAK_WALLET_PASSWORD"] == "pw"


def test_usdt_price_is_one_no_call(monkeypatch):
    _patch(monkeypatch, {})
    assert _client().price("USDT") == 1.0


def test_swap_quote_uses_quote_only_and_parses_output(monkeypatch):
    calls = _patch(
        monkeypatch, {"output": "0.16675 BNB", "minReceived": "0.165 BNB", "provider": "LiquidMesh"}
    )
    res = _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=False)
    assert res.amount_to == pytest.approx(0.16675, abs=1e-5)
    assert "--quote-only" in calls["argv"]
    assert "--password" not in calls["argv"]
    assert calls["argv"][:5] == ["twak", "swap", "100.0000000000", "USDT", "BNB"]


def test_swap_execute_passes_wallet_password(monkeypatch):
    calls = _patch(monkeypatch, {"output": "0.16 BNB", "txHash": "0xabc"})
    res = _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    assert "--password" in calls["argv"] and "pw" in calls["argv"]
    assert "--quote-only" not in calls["argv"]
    assert res.tx == "0xabc" and res.ok


def test_swap_execute_appends_slippage_flag(monkeypatch):
    # A1: a live execute passes --slippage explicitly (default 1.0); a quote does not.
    calls = _patch(monkeypatch, {"output": "0.16 BNB", "txHash": "0xabc"})
    _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    argv = calls["argv"]
    assert "--slippage" in argv
    assert argv[argv.index("--slippage") + 1] == "1.0"

    calls = _patch(monkeypatch, {"output": "0.16 BNB"})
    _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=False)
    assert "--slippage" not in calls["argv"]  # quote never appends it


def test_swap_slippage_flag_suppressed_when_empty(monkeypatch):
    # A1: an empty TWAK_SLIPPAGE_FLAG disables the flag entirely (trivially disableable).
    from ictbot.settings import settings

    monkeypatch.setattr(settings, "twak_slippage_flag", "")
    calls = _patch(monkeypatch, {"output": "0.16 BNB", "txHash": "0xabc"})
    _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    assert "--slippage" not in calls["argv"]


def test_swap_parses_execute_field_name_variants(monkeypatch):
    # execute responses may use amountOut/transactionHash/feeUSD instead of output/txHash/feeUsd
    _patch(monkeypatch, {"amountOut": "0.16 BNB", "transactionHash": "0xdef", "feeUSD": 0.01})
    res = _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    assert res.amount_to == pytest.approx(0.16, abs=1e-6)
    assert res.tx == "0xdef"
    assert res.fee_paid == pytest.approx(0.01)
    assert res.ok


def test_balance_native_has_no_token_or_coin(monkeypatch):
    # native BNB balance = --chain/--address only (no --token/--coin); value under "available"
    calls = _patch(monkeypatch, {"available": "1.5", "symbol": "BNB"})
    bal = _client().balance("BNB")
    assert bal == pytest.approx(1.5)
    assert "--token" not in calls["argv"] and "--coin" not in calls["argv"]
    assert "--address" in calls["argv"]


def test_balance_erc20_uses_token_address(monkeypatch):
    calls = _patch(monkeypatch, {"available": "12.0"})
    bal = _client().balance("ETH")
    assert bal == pytest.approx(12.0)
    assert "--token" in calls["argv"] and BSC_TOKENS["ETH"] in calls["argv"]


def test_error_payload_raises(monkeypatch):
    _patch(monkeypatch, {"error": "No wallet password found", "errorCode": "PASSWORD_MISSING"})
    with pytest.raises(RuntimeError, match="wallet password"):
        _client().balance("ETH")


# --------------------------- _run() retry / backoff / classification ------------------------- #
def _seq_run(monkeypatch, actions):
    """fake subprocess.run consuming `actions` ('timeout' | (returncode, payload_dict|stderr_str)).
    Records (mocked) sleeps so backoff is asserted without real waits."""
    sleeps: list[float] = []
    monkeypatch.setattr("ictbot.exec.twak_client.time.sleep", lambda s: sleeps.append(s))
    it = iter(actions)

    def fake_run(argv, **kw):
        a = next(it)
        if a == "timeout":
            raise subprocess.TimeoutExpired(cmd=argv, timeout=180)
        rc, body = a
        return (
            _FakeProc(json.dumps(body), rc)
            if isinstance(body, dict)
            else _FakeProc("", rc, stderr=body)
        )

    monkeypatch.setattr("ictbot.exec.twak_client.subprocess.run", fake_run)
    return sleeps


def test_run_retries_timeout_then_succeeds(monkeypatch):
    sleeps = _seq_run(monkeypatch, ["timeout", (0, {"priceUsd": 596.0})])
    assert _client().price("BNB") == 596.0  # price() -> _run("price") (no price_fn)
    assert len(sleeps) == 1  # one backoff slept, then success


def test_run_retries_transient_error_then_succeeds(monkeypatch):
    sleeps = _seq_run(
        monkeypatch, [(0, {"error": "rpc 503 unavailable"}), (0, {"priceUsd": 596.0})]
    )
    assert _client().price("BNB") == 596.0  # transient error payload -> retry -> ok
    assert len(sleeps) == 1


def test_run_permanent_error_raises_without_retry(monkeypatch):
    sleeps = _seq_run(monkeypatch, [(0, {"error": "No wallet password found"})])
    with pytest.raises(RuntimeError, match="wallet password"):
        _client().price("BNB")
    assert sleeps == []  # permanent -> NO backoff/retry (fail fast)


def test_run_exhausts_transient_retries_and_raises(monkeypatch):
    sleeps = _seq_run(
        monkeypatch, [(0, {"error": "503"}), (0, {"error": "503"}), (0, {"error": "503"})]
    )
    with pytest.raises(RuntimeError, match="failed"):
        _client().price("BNB")  # retries=2 -> 3 attempts, 2 backoffs, then raise
    assert len(sleeps) == 2


def test_run_exhausts_timeout_retries_and_raises(monkeypatch):
    sleeps = _seq_run(monkeypatch, ["timeout", "timeout", "timeout"])
    with pytest.raises(RuntimeError, match="timeout"):
        _client().price("BNB")  # 3 consecutive timeouts -> 2 backoffs -> raise
    assert len(sleeps) == 2


# --------------------------- swap() silent-degradation branches ------------------------------ #
def test_swap_ok_but_price_raises_yields_zero_price(monkeypatch):
    # a fully-valid swap (amount + tx, ok=True) where the price read raises -> price=0.0, NOT a crash.
    _patch(monkeypatch, {"output": "0.16 BNB", "txHash": "0xabc"})

    def boom(_t):
        raise RuntimeError("price feed down")

    res = _client(price_fn=boom).swap("USDT", "BNB", 100.0, execute=True)
    assert res.ok is True and res.tx == "0xabc" and res.price == 0.0


def test_swap_non_numeric_fee_degrades_to_zero(monkeypatch):
    _patch(monkeypatch, {"output": "0.16 BNB", "txHash": "0xabc", "feeUsd": "n/a"})
    res = _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    assert res.ok is True and res.fee_paid == 0.0  # float("n/a") -> ValueError -> 0.0


def test_swap_run_failure_returns_ok_false_not_raise(monkeypatch):
    _patch(monkeypatch, {"error": "No wallet password found"})  # _run raises -> swap catches
    res = _client(price_fn=lambda t: 596.0).swap("USDT", "BNB", 100.0, execute=True)
    assert res.ok is False and "failed" in res.error
