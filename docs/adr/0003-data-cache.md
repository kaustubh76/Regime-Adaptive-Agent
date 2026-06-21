# ADR 0003 — Parquet OHLCV cache + ReplayExchange

## Status
Accepted (2026-05-27, Phase 5 in PLAN.md).

## Context
A full WFO sweep on 50k bars × 4 pairs × 4 timeframes pulls a few MB
of data per pair but takes minutes per fetch because of Bybit's 1000-
bar page limit + IP throttle. Re-running an experiment with the same
window from scratch wastes hours.

## Decision
- Cache OHLCV per (pair, timeframe) as parquet files under `data/cache/`.
- `CachedExchange` is the write-through layer: on `fetch_ohlcv`, check
  the cache first; if missing, pull from Bybit and write back; if
  present but stale, merge new bars at the tail.
- `ReplayExchange` is the read-only counterpart used by experiment
  scripts — never hits Bybit, just serves what's in cache. Raises
  KeyError if a needed window isn't there so the test harness fails
  loudly instead of silently using yesterday's prices.
- Cache merge semantics: keep ALL bars, dedup on `time`, sort.

## Consequences
- A 50k WFO sweep that takes ~12 minutes uncached takes ~30 seconds
  cached (most cost is now strategy evaluation, not data fetch).
- The cache is gitignored (`.gitignore` lists `data/**`); we re-fetch
  on a fresh clone but never commit binary blobs.
- F1 (ROADMAP §F1) belongs in BybitExchange, not the cache layer —
  the cache is the cheap path; the retry handles the expensive path
  when we hit the network.

## Related
- `src/ictbot/data/cache.py`
- `src/ictbot/data/replay.py`
- `src/ictbot/data/bybit.py`
- PLAN.md §3 Phase 5 for the migration story.
