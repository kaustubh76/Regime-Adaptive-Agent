# ADR 0001 — Fade vs Follow mode

## Status
Accepted (2026-05-27). The strategy ships both modes; default is `fade`
per `settings.STRATEGY_MODE`. Empirical verdict is "no measurable edge
at 50k bars in either mode except XRP+PAXG with rr=5" (findings §15).

## Context
ICT setups can be played two ways:

- **follow**: the strategy fires BUY/SELL in the direction the indicator
  stack agrees on (HTF bias bullish + POI tap + bullish MSS → BUY).
- **fade**: the same setup fires the OPPOSITE direction (HTF bullish +
  POI tap + bullish MSS → SELL).

We tried fade first because the v1 dataset's BUY win-rate was 38% and
"flip everything" promised a 62% win-rate. Findings §13 then ran fade at
20k bars and saw expectancy below the friction floor on every pair.

Switching to follow (§14, §15) lifted XRP and PAXG with rr=5 to positive
TEST expectancy, but only because the tight-stop combos in the default
grid lose to friction first.

## Decision
- Keep both modes in code. The `strategy_mode` constructor arg + the
  `STRATEGY_MODE` setting let the experiment harness sweep both.
- Do NOT pick one as canonical until a §16-track config has 30 days of
  paper-trade agreement with backtest.

## Consequences
- The sweep grids (B1 rr2plus, B2 atr) implicitly cover both modes via
  the `--invert` CLI flag — no separate "fade vs follow" knob needed in
  the grid definitions.
- The dashboard's "ACTIVE CONFIG" sidebar must show which mode is on so
  a screenshot is interpretable later.
- Default flips here are blocked behind real out-of-sample evidence.

## Related
- findings.md §13, §14, §15.
- ROADMAP.md tracks B1–B6 (the §16 research path).
