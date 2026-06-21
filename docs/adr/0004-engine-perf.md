# ADR 0004 — Engine performance via monkey-patched fast indicators

## Status
Accepted (2026-05-27). 6× speedup verified for the original three
patches; F2 adds the bias-SMA fast path on top.

## Context
The first 50k-bar WFO sweep was projected at 2.5 hours. `cProfile`
showed three hot loops:

1. `get_atr(df)` recomputing TR over the entire growing window every
   bar (67 % of runtime).
2. Per-bar boolean mask `df[df["time"] <= T]` to slice timeframes —
   O(n) per slice across n bars = O(n²) total.
3. `get_delta(df)` summing signed volume over the same growing window.

F2 (this ADR's later addition) found the next hot spot:

4. `sma_htf_bias` and `sma_ltf_bias` doing `rolling(N).mean().iloc[-1]`
   on the growing window per bar (O(n²) again).

## Decision
- ATR (1): switch to `df.tail(period+1)` slice so each ATR computation
  is O(period) instead of O(n).
- Slicing (2): pre-extract `time.to_numpy()` once per timeframe;
  per-bar slice is `np.searchsorted(times, T, side="right")`. O(log n)
  instead of O(n).
- Delta (3): precompute cumulative signed-volume prefix sum once per
  run; per-bar delta is a single array indexing. Wire it in via
  `unittest.mock.patch` so live/test callers see the original
  `get_delta`.
- Bias SMA (4 / F2): precompute SMA20/SMA50/SMA10/SMA20 series once
  per run; per-bar bias is a single comparison. Same monkey-patch
  trick.

## Consequences
- The patches make `run_backtest` heavier to read: there are now five
  `mock.patch.object(...).start()` calls before the loop and five
  `.stop()` calls after. Mitigation: comment the WHY of each patch
  (the per-function comments in `backtest.py`).
- Tests in `test_backtest_searchsorted.py`, `test_atr.py`,
  `test_engine_bias_perf.py` confirm mathematical equivalence
  between the patched fast path and the original O(n²) path on the
  same synthetic data.
- A 50k full-grid sweep dropped from ~30 minutes (post-original 3
  patches) toward sub-10-minutes (F2 added).

## Why monkey-patch instead of refactoring the functions
- The functions (`get_atr`, `get_delta`, `sma_htf_bias`,
  `sma_ltf_bias`) are also called from analyze_pair / Streamlit
  dashboard / scanner where the per-call cost is fine and the
  precomputation overhead would be wasted. Patching at the
  backtest-engine boundary preserves the simple live-path code.

## Related
- `src/ictbot/engine/backtest.py` (the patch block)
- `src/ictbot/indicators/atr.py`
- ADR 0005 (RR floor) is the empirical reason these perf wins matter:
  to evaluate enough grid combinations to find the RR threshold
  honestly.
