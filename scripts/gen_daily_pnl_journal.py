#!/usr/bin/env python3
"""Generate a real multi-day, daily-PnL allocator journal for the dashboard.

The Mission-Control NAV/equity curve reads each REBALANCE row's `nav_after`. A fresh 4h sim on the
cached candle snapshot is FLAT (no intra-window price movement), so the curve looks dead. This script
instead REPLAYS the live `momentum_cmc` arm over the accumulated CMC **daily** candles (the same
engine as `make cmc_pnl`) and writes ONE journal tick per day — giving the dashboard a genuine
daily-PnL trajectory on the Avalanche universe (real day-by-day NAV, holdings, deploy-cap, regime).

Honest by construction — long-only spot, NO edge claim; the value is the daily participation curve.

    PYTHONPATH=src python scripts/gen_daily_pnl_journal.py [--window 90 --days 400 --start-nav 1000]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from ictbot.data.cmc import daily_close_matrix  # noqa: E402
from ictbot.engine.portfolio_replay import (  # noqa: E402
    ONE_WAY_70BPS,
    returns_matrix,
    simulate,
)
from ictbot.settings import JOURNAL_DIR, settings  # noqa: E402
from ictbot.strategy.momentum_allocator import (  # noqa: E402
    CONTEST_TOKENS,
    AllocatorParams,
    weight_path,
)
from ictbot.strategy.regime_score import cap_series, regime_score  # noqa: E402

_FEE_ONE_WAY = 0.0035  # 35bps/side (= 70bps round-trip), matches ONE_WAY_70BPS


def _fng_label(fg: int | None) -> str:
    if fg is None:
        return "neutral"
    if fg <= 24:
        return "extreme fear"
    if fg <= 44:
        return "fear"
    if fg <= 55:
        return "neutral"
    if fg <= 74:
        return "greed"
    return "extreme greed"


def _current_fng() -> int | None:
    """Latest Fear & Greed for the most-recent tick (from the committed market-intel seed)."""
    try:
        seed = json.loads((Path(__file__).resolve().parents[1] / "infra" / "seed" / "market_intel.json").read_text())
        trend = seed.get("fng_trend") or []
        if trend:
            return int(trend[-1].get("value"))
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=400, help="CMC daily candles to fetch")
    ap.add_argument("--window", type=int, default=90, help="recent days to emit as journal ticks")
    ap.add_argument("--start-nav", type=float, default=1000.0)
    a = ap.parse_args()

    df = daily_close_matrix(days=a.days)  # dates x tokens (defaults to CONTEST_TOKENS; drops candle-less)
    if df is None or df.shape[0] < 60 or df.shape[1] < 3:
        print(f"ERROR: not enough CMC daily history (shape={None if df is None else df.shape}); "
              "set CMC_INTEL_ENABLED=true + a CMC key.", file=sys.stderr)
        return 2
    tokens = list(df.columns)
    close = df.to_numpy()
    n, k = close.shape

    p = AllocatorParams(
        lookback=20, vol_lookback=10, rebal_bars=1,
        top_k=settings.alloc_top_k, abs_filter=settings.alloc_abs_filter,
    )
    caps = cap_series(close, floor=settings.alloc_cap_floor,
                      ceiling=settings.alloc_cap_ceiling, ma_window=settings.alloc_breadth_ma)
    w = weight_path(close, p, cap_series=caps)
    eq, _txns = simulate(w, returns_matrix(close), ONE_WAY_70BPS)
    nav = np.asarray(eq, dtype=float) * float(a.start_nav)

    start_i = max(p.lookback + 5, n - a.window)  # skip warmup
    fng_last = _current_fng()
    rows: list[dict] = []
    cum_swaps = 0
    for i in range(start_i, n):
        ts = df.index[i]
        weights = {tokens[j]: round(float(w[i, j]), 4) for j in range(k) if w[i, j] > 1e-4}
        turnover = float(np.sum(np.abs(w[i] - w[i - 1]))) if i > 0 else float(np.sum(w[i]))
        n_swaps = int(np.sum(np.abs(w[i] - w[i - 1]) > 1e-4)) if i > 0 else len(weights)
        cum_swaps += n_swaps
        try:
            rs = float(regime_score(close, i, ma_window=settings.alloc_breadth_ma))
        except Exception:
            rs = None
        is_last = i == n - 1
        fg = fng_last if is_last else None
        row = {
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "REBALANCE",
            "mode": "sim",
            "strategy": "momentum_cmc",
            "candle_source": "cmc_daily",
            "nav_before": round(float(nav[i - 1]), 2) if i > 0 else float(a.start_nav),
            "nav_after": round(float(nav[i]), 2),
            "weights_after": weights,
            "target": weights,
            "deploy_cap": round(float(caps[i]), 4),
            "regime_score": round(rs, 4) if rs is not None else None,
            "fear_greed": fg,
            "fear_greed_available": fg is not None,
            "n_swaps": n_swaps,
            "n_swaps_total": n_swaps,
            "n_failed": 0,
            "failed_swaps": [],
            "fees_usd": round(turnover * float(nav[i]) * _FEE_ONE_WAY, 2),
            "cumulative_swaps": cum_swaps,
            "tx": [],  # paper replay — no on-chain tx
        }
        if is_last:
            held = ", ".join(f"{int(round(v * 100))}% {t}" for t, v in
                             sorted(weights.items(), key=lambda kv: -kv[1]))
            cap_pct = int(round(float(caps[i]) * 100))
            row["rationale"] = (
                f"CMC daily-replay on the Avalanche universe: risk-on score "
                f"{rs:.2f} ({_fng_label(fg)}) → deploying {cap_pct}% of book "
                f"({held or 'cash'}, inverse-vol weighted), {100 - cap_pct}% in USDT. "
                f"Long-only spot momentum; participation over a bear-dominated tape."
            ) if rs is not None else None
        rows.append(row)

    out = JOURNAL_DIR / "allocator_journal.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    pnl = (nav[-1] / a.start_nav - 1.0) * 100.0
    print(f"wrote {len(rows)} daily ticks -> {out}")
    print(f"  window {rows[0]['ts'][:10]} -> {rows[-1]['ts'][:10]} | tokens {tokens}")
    print(f"  NAV {a.start_nav:.0f} -> {nav[-1]:.2f}  ({pnl:+.1f}% over the window)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
