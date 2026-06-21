# ADR 0002 — Two POI engines (min_max + order_block)

## Status
Accepted (2026-05-27). `POI_ENGINE` setting selects between them at
runtime; both are exercised in tests.

## Context
"POI" (Point of Interest) is the price level the strategy waits for
price to retest. Two interpretations:

1. **min_max** (legacy): the recent local low (for BULLISH bias) or
   high (for BEARISH). Simple, fast, no notion of order blocks.
2. **order_block** (ICT-canonical): the last opposite-colour candle
   before a market structure break. Closer to ICT theory but depends
   on `find_swings` detecting a valid swing.

## Decision
- Ship both. Keep `min_max` as the default so we have a working
  fallback when `order_block` returns None (which happens often on
  short windows or low-volatility regimes).
- `find_order_block` returns None instead of raising when no OB can be
  detected — the strategy then falls back to the swing-low/high.

## Consequences
- The strategy code carries the dispatch:
    ```
    if poi_engine == "order_block":
        ltf_poi = get_ob_poi(...)
    else:
        ltf_poi = get_ltf_poi(...)
    ```
  This is acceptable: two short branches in one place, no inheritance
  hierarchy.
- E3 mitigation is wired into both engines; min_max gets it via the
  existing `mitigation_bars` plumbing, order_block via the dedicated
  branch in `get_ob_poi`.

## Related
- `src/ictbot/indicators/poi_min_max.py`
- `src/ictbot/indicators/poi_order_block.py`
- ADR 0005 (RR floor) documents why neither engine alone produces an
  edge without the rr2plus grid.
