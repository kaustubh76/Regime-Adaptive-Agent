# ADR 0005 — RR floor for live deployment

## Status
Proposed (2026-05-27). Binds future live trading work; will move to
Accepted when B5 (paper-trade) lands.

## Context
findings.md §15 produced one unambiguous lesson: every pair that
held out-of-sample at 50k bars picked an RR ≥ 5 configuration (XRP and
PAXG, rr=5). Every losing pair picked configurations in the rr 1.2–3.1
range and lost net to friction. The friction model is:

```
friction_R = 2 × (FEE_PER_SIDE + SLIPPAGE_PER_SIDE) / risk_distance_pct
```

With `FEE_PER_SIDE = 0.0005` and `SLIPPAGE_PER_SIDE = 0.0002`, tight
stops produce friction north of 0.5R per round-trip. At rr=1.2, that's
half the gross win eaten before WR even matters.

## Decision
Live trading must not begin until:

1. The chosen sweep config has TRAIN expectancy > 0, TEST expectancy
   > 0, AND TEST closures ≥ 20 (F3 gate, ROADMAP §F3).
2. The config's effective RR is ≥ 2:1 — enforced by `GRIDS["rr2plus"]`
   (ROADMAP §B1) being the grid B5/B6 evaluate against.
3. The config has passed 30 calendar days of paper-trade with per-trade
   expectancy within ±0.2R of backtest (ROADMAP §B5).

These three gates exist BECAUSE the §15 saga proved every shortcut
fails. We are not optimising; we are protecting against
re-relitigation of conclusions the codebase has already paid for.

## Consequences
- `BybitLiveBroker.place_order` (C1) reaches its core only when both
  `ENABLE_LIVE_TRADING=true` AND the pair is in `allowed_pairs`. The
  enabling action is intentionally manual — flipping the env var is
  not enough; the kill switch sentinel must also be released.
- The dashboard banner (C3) shows live state and offers a one-click
  kill. Going from green (disabled) to red (enabled) is a human
  decision that this ADR documents.
- Adding a new grid to `sweep.py` must declare its RR floor in a
  comment so future grids can't sneak below 2:1.

## Related
- findings.md §15, §16.
- ROADMAP.md §B1 / §B5 / §B6 / §F3 / §C1 / §C3.
