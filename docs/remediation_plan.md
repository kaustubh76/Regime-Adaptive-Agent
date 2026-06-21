# Remediation & Submission Plan — Jun 12 → Jun 28

**Companion to [implementation_audit.md](implementation_audit.md)** (finding IDs C1-C4, H1-H4, M1-M6 refer to it). Adversarially reviewed 2026-06-12 (3 lenses: command correctness, schedule logic, deliverable coverage) — this version incorporates all fixes.
**Hard dates:** submission lock Jun 21 (treat as **12:00 UTC** until verified — Step 0.1), trading window **Jun 22 00:00 UTC → Jun 28**.
**Claimed done (must re-verify in Phase 0 — see 0.2):** ERC-8004 mint (agentId 1313) + contest registration (participant `0xE8A3…6215`) on 2026-06-08 per [bnb_strategy_decision.md](bnb_strategy_decision.md). ⚠ `AGENT_ID` is **absent from `.env`**, so the mint result was never persisted — treat registration status as *unverified* until the Phase 0 check.
**Missing runtime artifacts:** zero x402 receipts (`data/x402/` doesn't exist), no live swap tx hash (`allocator_live.jsonl`: 1 row, `tx: []`), no registration proof pack, no LICENSE file.
**Live deploys:** dashboard `https://bnb-mission-control-two.vercel.app` · API `https://bnb-mission-control-api.onrender.com`.

Each step has commands and an **Accept** check. Phases are sequential except where marked parallel-safe.

---

## Phase 0 — TODAY Jun 12: unblock + de-risk (~2.5 h)

### 0.1 Verify deadline + contest rules in the hackathon TG (C3 — 15 min, do first)
Plan says Jun 21 **17:30 UTC**; the scraped hackathon page says **12:00pm UTC**. Check the DoraHacks BUIDL page / ask in TG (`https://t.me/+MhiOLT0YUnlmNWFk`). While there, also confirm: **are pre-window test swaps from the registered wallet allowed and unscored?** (Phases 5.3 and 7 fire real swaps before Jun 22 — scoring should baseline at window open, but get it in writing.)
`mkdir -p data/compete` now (used by every artifact step below).
**Accept:** deadline screenshot + the pre-window-swaps answer saved to `data/compete/`; this file updated if either differs from assumptions.

### 0.2 Verify registration status NOW, not Jun 18 (H2 — read-only, free)
The status check was originally scheduled Jun 18; if it surprises, the contingency would collide with the demo days. It's read-only — do it today:
```bash
make register_agent 2>&1 | tee data/compete/registration_check_2026-06-12.log   # dry run: preflight + `twak compete status --json`
```
- BscScan → CompetitionRegistry (`0x212c…aed5` — re-confirm the address against the official brief; nothing in code reads it) → Read Contract → `isRegistered(AGENT_TRADING_ADDRESS)`.
- BscScan → confirm the ERC-8004 mint tx / tokenId 1313.
- Then repair the un-persisted state in `.env`: set `AGENT_ID=<confirmed tokenId>` and `AGENT_HEARTBEAT_ENABLED=true` (without both, `write_heartbeat` no-ops forever — `run_allocator.py:529`).

**Accept:** `twak compete status --json` shows registered **and** BscScan `isRegistered=true`; `grep '^AGENT_ID=' .env` non-zero. **If NOT registered:** the full contingency runbook (Phase 6) starts **tomorrow** with 8 days of runway, not 3.

### 0.3 Rebuild the venv (C4 — the stale-shebang venv, not just the .pth)
The venv was *created* at the old `Rahul_ideation` path: `pyvenv.cfg` and every console-script shebang (`pip`, `pytest`, `uvicorn`) still point there and execute inside the **old sibling venv**. Reinstalling in place won't fix shebangs — rebuild. First pin `bnbagent==0.3.5` in pyproject (PyPI now serves an untested 0.3.6; don't switch SDK versions 9 days out):
```bash
cd /Users/apple/Desktop/BNB-Hack-CMC
rm -rf .venv && hash -r          # the deleted venv's python3 was first on PATH
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev,api,bnb,tg,ui]"   # [bsc] is empty (twak is npm)
find . -name __pycache__ -type d -not -path "./.venv/*" -prune -exec rm -rf {} +
find . -name '*.pyc' -not -path './.venv/*' -delete
```
**Accept (all four):** ① `cat .venv/lib/python3.13/site-packages/__editable__*.pth` → exactly this repo's `/src`; ② `.venv/bin/python -c "import ictbot; print(ictbot.__file__)"` → this repo; ③ `head -1 .venv/bin/pytest` → this repo's venv; ④ `make test` collects from `./tests` with no `../Rahul_ideation` paths.

### 0.4 Pin `PYTHONPATH=src` in the Makefile (C4 belt-and-braces)
`api` (line 17) and `snapshot` (line 120) already pin. Add the pin to seven recipes (line numbers verified; keep the TAB):

| Line | Target | New recipe |
|---|---|---|
| 8 | `test` | `. .venv/bin/activate && PYTHONPATH=src python -m pytest -q` *(also drops the shebang-sensitive `pytest` script)* |
| 85 | `validate_allocator` | `… PYTHONPATH=src python scripts/validate_allocator.py $(ARGS)` |
| 90 | `ab_regime` | `… PYTHONPATH=src python scripts/ab_regime.py $(ARGS)` |
| 98 | `run_allocator` | `… PYTHONPATH=src python scripts/run_allocator.py $(ARGS)` |
| 104 | `forward_report` | `… PYTHONPATH=src python scripts/report_forward.py $(ARGS)` |
| 109 | `register_agent` | `… PYTHONPATH=src python scripts/register_agent.py $(ARGS)` |
| 115 | `verify_nodereal` | `… PYTHONPATH=src python scripts/verify_nodereal.py $(ARGS)` |

**Accept:** `make -n test run_allocator` shows the pin.

### 0.5 Fix the time-bombed news_alert tests (M6)
In [tests/test_news_alert.py](../tests/test_news_alert.py) replace the frozen `_now()` (verified: file has exactly 8 tests, no absolute-date assertions — the replacement stays deterministic):
```python
def _now() -> datetime:
    # Anchored to the REAL clock (top of the current hour): news_alert._save_alerted
    # prunes entries older than PRUNE_AFTER_DAYS against wall-clock now, so a frozen
    # calendar date silently expires the dedup entry the moment it is saved. All
    # events are built at fixed offsets from this, so assertions stay deterministic.
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
```
(Do **not** shrink the prune in the shared fixture — that silently breaks `test_prune_drops_old_entries`.)
**Accept:** `pytest tests/test_news_alert.py -q` → **8 passed**, including the prune test.

### 0.6 Declare web3 (H3)
Add `web3>=6.15.0` to **both** `[api]` and `[bnb]` extras (floor = `bnbagent` 0.3.5's own requirement; venv runs 7.16.0). Note for accuracy: the current Render image is *not* degraded — `infra/Dockerfile.dashboard:32` installs `.[api,bnb]`, so web3 arrives transitively; this fix makes the direct imports (`api/onchain.py`, `data/x402_cmc.py`) survive any future image or dependency change.
**Accept:** fresh-venv smoke: `python3 -m venv /tmp/h3 && /tmp/h3/bin/pip install -q -e ".[api]" && /tmp/h3/bin/python -c "import web3, eth_abi"`; main venv reinstall conflict-free.

### 0.7 Full suite green
**Accept:** `make test` → **1106 passed, 0 failed** (9 live-integration skips remain intentional).

### 0.8 Start the USDC-on-Base funding (Phase 4 prerequisite — needs lead time, parallel-safe)
Getting $1-2 USDC onto Base from a BSC-centric stack is the plan's longest external dependency (CEX withdrawal minimums ~$10, possible 24-72 h new-address holds, bridges costing more than the amount). The pay address is printable today:
1. `make register_agent` (dry run) → prints the x402 pay wallet (= the **ERC-8004 identity wallet**, not the TWAK trading wallet) + its live Base USDC balance.
2. Send ~$10 USDC via a **Base-native route** (e.g. Coinbase native Base withdrawal). Triple-check the network — a wrong-network send is unrecoverable.

**Accept (deadline Jun 15):** Base explorer shows ≥ $1 USDC at the pay address.

---

## Phase 1 — Jun 12-13: commit & deploy (H1) (~1.5 h)

### 1.1 Clean before staging
- `rm docs/Untitled-2024-10-17-0018.excalidraw.png` — 2.3 MB stray export of the OLD ictbot diagram (editable source already preserved at `docs/archive/architecture_ictbot_upstream.excalidraw`).
- **Trim `docs/checkings.md`** (1007 lines of scraped CMC marketing): keep only the x402 curl transcript (~lines 20-90) + a one-line provenance header — it *will be* the cited source for `docs/x402_receipts.md` §2 (authored in Phase 3.3).
- **Decide `docs/architecture.png` once:** commit it (GitHub-render convenience) — do **not** also gitignore it; accept the regen churn consciously.

### 1.2 Six commits, in this exact order (later commits reference earlier files; inventory = 50 entries incl. this plan, verified zero orphans)
1. **`feat(dashboard): BNB-gold design system — semantic tokens, display fonts + 6 new UI primitives`** — `web/index.html`, `web/tailwind.config.js`, `web/src/index.css`, `web/src/main.tsx`, `web/src/components/ui/*` (8), `web/src/lib/{format,glossary,pnl}.ts`
2. **`feat(dashboard): tiered Mission Control — HeroRow + every panel rewired onto the new primitives`** — `HeroRow.tsx` + the 16 modified panels
3. **`chore(dashboard): refresh static snapshot fallback (6/11 wallet read + CMC credit count)`** — `web/public/snapshot.json`
4. **`docs(architecture): regenerate as the momentum-agent flow; archive the upstream ictbot map`** — `scripts/gen_architecture.py`, `docs/architecture.{excalidraw,svg,png}`, `docs/archive/architecture_ictbot_upstream.excalidraw`, deletion of `docs/architecture_bnb.excalidraw`, `src/ictbot/notify/signal_check.py`
5. **`docs: repoint architecture links; capture implementation audit + remediation plan`** — `PLAN.md`, `ROADMAP.md`, `docs/bnb_hackathon_plan.md`, `docs/operations.md`, `docs/checkings.md` (trimmed), `docs/implementation_audit.md`, `docs/remediation_plan.md`, `docs/monetization_plan.md`. **README.md is deliberately NOT here** — it would be archived a day later; it rides with the Phase 2.1 archive+rewrite commit instead (avoids a confusing double-touch and keeps rename detection clean).
6. **`fix(env): rebuild-proof the toolchain — PYTHONPATH pins, web3 dep, bnbagent pin, un-time-bomb news_alert tests`** — Phase 0's Makefile/pyproject/test edits.

### 1.3 Push and verify both deploys
```bash
git push origin feat/implementation
curl -s https://bnb-mission-control-api.onrender.com/api/health
make refresh_dashboard
```
**Accept:** `git status --porcelain` empty except README.md; both URLs serve the refactored UI; `bash scripts/build_web.sh` green locally.

---

## Phase 2 — Jun 13-14: README + license + hygiene (C1, M4, M1, M2, H4) (~4.5 h)

### 2.1 Archive the legacy README, write the new one (C1) — single commit
```bash
git mv README.md docs/archive/README_ictbot_upstream.md
```
In the archived file: prepend a 2-line "Archived 2026-06 — upstream ICT perp bot, superseded by the momentum allocator (see root README)" banner **and fix its relative links with `../../` prefixes** (GitHub resolves links relative to the *file*, not the repo root — the old in-place links break after the move).

New `README.md` — 12 sections, each with an existing source to lift (full source map in the Jun 12 gathering record; key notes):
1. **90-second pitch** — lift the `bnb_hackathon_plan.md` 🔒 LOCKED paragraph + the 🟢 LIVE proof line + the "honest bottom line". ⚠ **Numbers in one vintage only:** use `bnb_strategy_decision.md` §7 (**17.3% worst-week DD, ~15.4 trades/wk**) everywhere — not 17.6/11.5 or 16.8/15.4.
2. **Live links table** (above the fold): Vercel dashboard · Render API (`/api/health`, `/api/pillars`, `/api/nav`) · BscScan identity + registration. Never link `ictbot-scanner.onrender.com` (legacy deploy).
3. **The strategy** — decision record §2-§3 nearly verbatim (5-step list, regime→cap table, code links).
4. **Why this strategy — the honest negative-edge audit** — §1 five-way evidence table.
5. **Three pillars** — §4 diagram + bullets (heartbeat claim is code-verified: `identity.py::write_heartbeat` ← `run_allocator.py:529-534`).
6. **Evidence I: CMC PnL A/B** — frame as "which lever draws down less" (raw returns negative on the down-leaning window); keep the "Data provided by CoinMarketCap" attribution.
7. **Evidence II: forward paper validation** — refresh NAV via `make forward_report` at write time; date-stamp.
8. **Mission Control** — live screenshot + the zero-secret deploy story.
9. **Risk controls & DQ-safety** — both contest gates with strategy-level + mechanical-failure-level defenses; §7 hardening list; **plus the explicit-DQ compliance line: spot swaps only — no token launches, fundraising, or airdrop activity during the event window** (plan §12 rule).
10. **Reproduce it** — command table from the Makefile target comments.
11. **Repo map** — ~15 lines, contest paths only; one italic line on the inherited ICT/CEX engine; name `scripts/gen_architecture.py` as the diagram regenerator.
12. **Provenance & further reading** — single archived-README link; demo video + DoraHacks placeholders (filled Jun 20-21).

Same commit: pyproject `description` →
> *Regime-adaptive, long-only spot momentum allocator for the BNB Hack AI Trading Agent contest — CMC Agent Hub data (MCP/x402), TWAK self-custody execution on BSC (gasless via MegaFuel), and an ERC-8004 on-chain agent identity.*

**Accept:** README has zero Bybit/Delta/Streamlit/`Rahul_ideation` references outside the provenance line; `grep -c 'perpetuals\|ICT-style' pyproject.toml` → 0; plan §12 README checklist rows all present.

### 2.2 LICENSE (plan §12 row 1 — was dropped entirely)
No LICENSE file exists; the repo would go public all-rights-reserved. Create `LICENSE` (MIT, current year, author name) + `license = {text = "MIT"}` in pyproject.
**Accept:** `ls LICENSE` + pyproject license field present.

### 2.3 `.env.example` completion (M1 — **46** missing vars, not 22)
Append the prepared commented-out block (full text in the gathering record: pairs/timeframes, canonical-flow knobs, risk/dedup, TG noise, **all 10 `ALLOC_*` knobs**, contest window + trade floor, agent identity/infra, dashboard vars). **Commit the checker** as `scripts/check_env_example.py` (the Settings-fields-vs-example diff) so the acceptance is reproducible from the repo.
**Accept:** `PYTHONPATH=src .venv/bin/python scripts/check_env_example.py` → `missing: 0`; `import ictbot.settings` still clean.

### 2.4 Orphaned scripts (M2) + docker-compose (H4)
- `docs/operations.md` gains a "Debug & one-off utilities" note covering **all 8**: `probe_agent_hub.py`, `probe_cmc.py`, `verify_wallet_parity.py`, `wfo_gates_ab.py`, `archive_journal.py`, `gen_architecture.py` (keep, with one-line purpose each); `fire_test_order.py`, `close_test_order.py` (legacy CEX-perp — delete).
- docker-compose: **comment out** the `dashboard` service with a LEGACY banner (streamlit moved to `[ui]`; the image no longer contains it → crash-loop). Don't repoint to FastAPI.

**Accept:** `docker compose config --services` → `scanner, prometheus, grafana` and `docker compose config -q` exits 0; `grep -q 'Debug & one-off utilities' docs/operations.md`; the 2 deleted scripts gone.

### 2.5 Create the DoraHacks BUIDL draft NOW (parallel-safe — deadline-day de-risking)
First contact with the submission form must not be deadline morning: create the BUIDL today, fill every static field (profile, logo, track, team), attach placeholder links, and learn which fields are editable post-submit.
**Accept:** draft BUIDL exists; list of post-submit-editable fields saved to `data/compete/`.

---

## Phase 3 — Jun 14-15: the five submission docs (C2) (~1.5 days)

Order matters: strategy.md feeds SUBMISSION.md and DEMO.md. Full outlines + line-level source maps in the gathering record. **Load-balance fix:** SUBMISSION.md and DEMO.md draft on **Jun 15** (they're short); Jun 16 is reserved for Phase 4 runtime work.

### 3.1 `docs/strategy.md` (Jun 14)
9 sections lifted ~wholesale from `bnb_strategy_decision.md` §1-§7 + `cmc_pnl_ab.md` verdict. **Trap:** never source plan §4 ("multi-signal confluence"/ICT — superseded). State `ta_rank` is live-enabled (commit `56e9843` = the A/B "TURN ON" verdict).
**Accept:** file exists; `grep -iL 'multi-signal confluence' docs/strategy.md` (absent); quotes the §7 numbers (17.3%/15.4).

### 3.2 `docs/twak_integration.md` (Jun 14-15) — TWAK special-prize artifact
8 sections; opens with a rubric-map table (30/25/20/10/10/5 → repo evidence). **Traps:** (a) weights externally unverified — screenshot the actual DoraHacks rubric, caveat; (b) describe the *implemented* x402 path (`pro-api.coinmarketcap.com/x402/v1/dex/search`, `/x402/v3/cryptocurrency/quotes/latest`), not the plan's `mcp.coinmarketcap.com/x402/mcp`.
**Accept:** file exists with the rubric-map table + rubric screenshot reference; no `mcp.coinmarketcap.com/x402` claim.

### 3.3 `docs/x402_receipts.md` (Jun 15 skeleton, §6 finalized Jun 16 after Phase 4)
Schema/flow/safety-rails from `x402_cmc.py`; §6 table **generated** from real `data/x402/receipts.json` via a committed regenerator (`make x402_receipts` or a one-liner). State explicitly: the payment wallet is the **identity wallet**, not the TWAK trading wallet.
**Accept (Jun 16):** §6 regenerates byte-identical from the JSON; ≥3 settled rows quoted with date.

### 3.4 `SUBMISSION.md` (Jun 15)
~500 words, 5 paragraphs + links block per plan §12 structure but **hooked on the locked strategy** (honest no-edge thesis). Include the no-token-launch compliance line. Placeholders for: demo URL, sample swap tx, forward NAV — each tagged `<TBD:…>` so the Phase 8 grep gate can find them. Note in-file: the plan-§12 "Prom metrics screenshot" is **superseded** by the live Mission Control URL (the allocator path doesn't export `:9100`).
**Accept:** file exists, ~500 words, all placeholders tagged `<TBD:`.

### 3.5 `DEMO.md` (Jun 15)
9 segments, 0:00-4:45 timing budget (full script in the gathering record). **Traps:** plan §12's "scanner loop / ICT BUY / exit-watcher TP" items are superseded — show an **allocator tick**; replace exit-watcher with the guardrails segment (DD halt, trade-floor nudge, failed-swap journaling). The TWAK swap must visibly sign **locally, no cosigner** (explicit rubric requirement). Pre-record fallbacks for anything network-dependent.
**Accept:** file exists; per-segment command list + timing table present; no ICT/exit-watcher framing.

---

## Phase 4 — Jun 16: generate + **publish** the x402 receipts (~2 h)

Zero settled x402 payments exist; plan §12:752 requires real USDC rows for the TWAK special. Funding already in flight since 0.8.

1. `.env`: `X402_ENABLED=true` (AGENT_WALLET_PASSWORD already set).
2. `make run_allocator` — a **sim tick fires the x402 dex_search** (verified: the x402 read is data-path, not trade-path).
3. Verify locally: `data/x402/receipts.json` has `status: settled` rows; USDC transfers visible on a Base explorer.
4. **Publish to the live dashboard** — without this the panel stays zero (`data/**` is gitignored; `reads.py:288-291` reads the local file; the Dockerfile creates `data/x402` empty): copy `data/x402/receipts.json` → `infra/seed/`, extend `infra/Dockerfile.dashboard`'s seed-COPY (lines 42-45 pattern), commit + push → Render redeploys.
5. Regenerate `docs/x402_receipts.md` §6.

**Accept:** ≥3 settled receipts on disk **and** the live CmcAgentHubPanel shows non-zero spend after the redeploy; x402_receipts.md §6 current.

---

## Phase 5 — Jun 17: hardening buffer + dress rehearsal + **the live swap** (~4 h)

### 5.1 Trade-floor gap tests (M3)
`tests/test_trade_floor.py` has **8** tests today (collect-only verified). Add the three gap tests (exact code in the gathering record): sell-leg failure after a settled buy → `banked == 1` (`run_allocator.py:186-189`, never exercised); odd `needed=3` terminates at `banked=4`; nudge round-trips the **largest USD holding**, not `tokens[0]`.
**Accept:** `pytest tests/test_trade_floor.py -q` → **11 passed**.

### 5.2 Dress rehearsal (end-to-end, sim) + clean-checkout proof
```bash
make validate_allocator && make run_allocator && make forward_report && make refresh_dashboard && make test
# Gate 1 means a CLEAN CHECKOUT, so actually do one (C4 was precisely a stale-env bug):
git clone /Users/apple/Desktop/BNB-Hack-CMC /tmp/clean && cd /tmp/clean \
  && /opt/homebrew/bin/python3 -m venv .venv && .venv/bin/python -m pip install -q -e ".[dev,api,bnb,tg,ui]" && make test
```
Note: plan §12's `make smoke-cmc/smoke-twak/smoke-bsc` were never built — this rehearsal sequence **supersedes** them (record that in SUBMISSION.md's checklist mapping).
**Accept:** all green in both trees; the journal tick shows a rationale; NodeReal dashboard shows the sponsored heartbeat request (possible now that 0.2 set `AGENT_ID` + `AGENT_HEARTBEAT_ENABLED`).

### 5.3 Bank the live swap tx hash (MANDATORY today — no demo-day fallback)
Final gate #6, needed in SUBMISSION.md, README, and the demo. Capturing it on-camera Jun 20 was rejected in review (network-dependent must-have on a single-purpose day with no retry slot).
```bash
# .env: ENABLE_LIVE_TRADING=true, TWAK_MODE=live (minimal size)
make run_allocator ARGS="--mode live"
```
Then revert `.env` to sim until Phase 7.5. **If it fails today:** Jun 18-19 is the designated retry window (Phase 6 only needs ~1 h).
**Accept:** `data/journal/allocator_live.jsonl` has a row with non-empty `tx[]` that resolves on BscScan; hash pasted into SUBMISSION.md + README §12 (clearing those `<TBD:` tags).

---

## Phase 6 — Jun 18-19: registration proof pack (H2) (~1 h; contingency only if 0.2 failed)

Status was verified Jun 12 (0.2); this phase **assembles evidence**:
- Screenshots: BscScan `isRegistered=true` · the mint tx (tokenId 1313) · NodeReal dashboard sponsored MegaFuel requests · DoraHacks BUIDL showing the agent address.
- Hand-write `data/compete/registration.json`: `{tx_hash, agent_id, wallet, registered_at, status_json}` (the script writes nothing to disk itself).
- **Back up the bnbagent identity keystore** (signs heartbeats + x402 payments; losing it loses the identity wallet) — verify the backup restores.
- Address triple-check: DoraHacks address == `AGENT_TRADING_ADDRESS`, copy-pasted from the status JSON.

**Accept:** `ls data/compete/` shows registration.json + 4 screenshots + the check log; keystore backup restorable.

**Contingency (only if 0.2 said NOT registered — running since Jun 13 in that branch):** toolchain preflight (`node ≥22.14`, `twak compete --help`), `make verify_nodereal ARGS="--network mainnet"` (require `chain_id=56`, `sponsorable=✅`), fund ~0.01 BNB, then `make register_agent ARGS="--register" 2>&1 | tee data/compete/registration_$(date +%F).log`. Known risks: `twak compete register` externally unverified (fallback: ~50-line web3.py script — needs the trading key by another route); the 180 s subprocess timeout can false-fail a landed tx (check `status` before any retry); a mint failure does **not** block contest registration (`--register --no-identity`). ⚠ **Boot-guard trap:** `ENABLE_LIVE_TRADING=true` + `TWAK_MODE=sim` routes through the legacy CEX-credentials guard (`settings.py:693-708`) — it only boots because legacy keys are still in `.env`; do **not** strip them before Jun 19, or run with `TWAK_MODE=live` instead.

---

## Phase 7 — Jun 20: demo + final numbers (~3 h)

1. Record the 3-5 min demo per DEMO.md (terminal + Vercel dashboard + BscScan pre-staged; local signing visible). The live swap is a **re-demonstration** — the hash is already banked (5.3).
2. **Upload immediately and verify playback logged-out the same evening** (processing time is real); paste the URL into README §12 + SUBMISSION.md.
3. `make forward_report` → refresh the forward-NAV figure (date-stamped) in README §7 + SUBMISSION ¶5.
4. Final commit + push; confirm both deploys serve the final commit.

**Accept:** demo URL plays in a logged-out browser; `grep -rn '<TBD:' SUBMISSION.md README.md DEMO.md docs/strategy.md docs/twak_integration.md docs/x402_receipts.md` → **zero hits**.

### 7.5 Arm the trading window (Jun 20-21 — the contest itself; was missing from v1 of this plan)
Submission is not the finish line; the agent must trade unattended Jun 22-28:
1. **Final live config** in `.env`: `ENABLE_LIVE_TRADING=true`, `TWAK_MODE=live`, `DASHBOARD_JOURNAL=live` (the settings comment literally says "Flip to live for 06-22" — `settings.py:301`), `AGENT_HEARTBEAT_ENABLED=true`, `X402_ENABLED` per preference.
2. **Install a scheduler** — none exists in the repo. macOS: a `launchd` plist (cron dies on sleep) running `make run_allocator` daily at a fixed UTC hour, with a wake-schedule (`pmset repeat wakeorpoweron`) or `caffeinate`; `ALLOC_REBAL_BARS=6` (≈daily on 4h bars) matches a daily tick, and the trade-floor nudge handles the 7-trade minimum.
3. **Dry-run the scheduler 24 h** (Jun 20 → 21) in sim: two consecutive unattended ticks land in the journal.
4. Write the one-page **Jun 22-28 daily ops checklist**: 09:00 UTC — journal tick present? DD vs halt? trades-toward-7 on pace? dashboard fresh? NodeReal heartbeat? kill criteria (DD > 12% manual review).
5. Fund the trading wallet's USDT capital + gas BNB to final size before Jun 21 EOD.

**Accept:** scheduler fired unattended twice in the dry-run; final `.env` state checklisted; wallet funded.

---

## Phase 8 — Jun 21: submit (target ≤ 10:00 UTC vs the worst-case 12:00 lock)

0. **Placeholder gate:** re-run the `<TBD:` grep across all six submission-facing docs → zero hits.
1. Final `make test` + `bash scripts/build_web.sh` green; `git status` clean; push.
2. Repo public (LICENSE in place since 2.2).
3. DoraHacks BUIDL (drafted since 2.5): swap in final links — repo, demo, agent address (exact), registration + swap tx, dashboard URL — and submit.
4. Screenshot the completed submission → `data/compete/`.
5. After submitting: confirm Phase 7.5's live config is armed for the 00:00 UTC window open.

**Accept:** submission screenshot saved; agent armed.

---

## Phase 9 — competition end (Jun 28): closing artifacts (stub)

Plan §8 requires post-window artifacts with no other owner: export the equity-curve PNG from the live journal, compile the full tx-hash list from `allocator_live.jsonl`, snapshot the final dashboard, and keep everything for judge questions (Jun 29 - Jul 5).

---

## Final acceptance gates

| # | Gate | Producing phase |
|---|---|---|
| 1 | `make test` green **from a clean clone** | 5.2 |
| 2 | README pitches the momentum allocator; consistent numbers (17.3% / 15.4); pyproject description updated | 2.1 |
| 3 | Five docs exist, each passing its own Accept (incl. zero superseded-narrative greps) | 3.1-3.5 |
| 4 | ≥3 settled x402 receipts on disk **and** non-zero on the live dashboard panel | 4 |
| 5 | Registration proof pack in `data/compete/` + restorable keystore backup | 0.2 + 6 |
| 6 | Live swap tx hash banked Jun 17, resolving on BscScan | 5.3 |
| 7 | Demo plays logged-out; zero `<TBD:` placeholders anywhere | 7 |
| 8 | DoraHacks submitted before the verified deadline; screenshot saved | 8 |
| 9 | LICENSE (MIT) in repo + pyproject | 2.2 |
| 10 | 0 uncommitted files; both live URLs serve the final commit | 1.3 / 7.4 |
| 11 | `check_env_example.py` → `missing: 0`; no secrets in `.env.example` | 2.3 |
| 12 | Scheduler dry-run fired 2 unattended ticks; live config armed for Jun 22 00:00 UTC | 7.5 |

**Slack:** Jun 17 is the designated buffer *and* carries the mandatory live swap — if 5.3 slips, Jun 18-19 absorbs it (Phase 6 is ~1 h). Jun 20/21 stay single-purpose. Nothing after Jun 19 depends on a step that can slip.

---

## Progress log

### 2026-06-12 — Phases 0 + 1 executed
**Done (machine-verified):**
- ✅ 0.2 partial: registration dry-run logged to `data/compete/registration_check_2026-06-12.log`. **Contest registration CONFIRMED on-chain** via direct web3 read: `isRegistered(0xE8A3…6215) = TRUE` on `0x212c…aed5`. (`twak` CLI not on PATH in the exec shell — `compete status` JSON still pending, non-blocking.)
- ✅ 0.3 venv rebuilt from this repo, all 4 acceptance checks pass; bytecode purged.
- ✅ 0.4 `PYTHONPATH=src` pinned in all 7 Makefile recipes.
- ✅ 0.5 `test_news_alert._now()` re-anchored → 8/8 green.
- ✅ 0.6 `web3>=6.15.0` in `[api]`+`[bnb]`; `bnbagent==0.3.5` pinned.
- ✅ 0.7 **`make test`: 1106 passed, 0 failed, 9 intentional skips (83 s).**
- ✅ 1.1-1.3: junk PNG deleted, `checkings.md` trimmed to its 2 cited sections, **7 commits pushed** (`17da820`…`be61144`), web build green, Render `/api/health` 200 + Vercel SPA 200.

**🔴 New finding (identity-key mismatch — needs user decision):** on-chain, `ownerOf(1313) = 0x1783…ca4e` with `balanceOf = 2`, while the local bnbagent keystore (`0xEb7b…9655`, created Jun 8 15:00; `~/.bnbagent/wallets` modified Jun 9) owns **0** identity NFTs. The key that minted agentId 1313 is not on this machine. `AGENT_ID` deliberately **not** written to `.env` — heartbeats for 1313 can't be signed by the current key. Options: (a) restore the `0x1783…` key (backup / `AGENT_PRIVATE_KEY`); (b) re-mint a fresh identity with the current keystore — requires fixing the MegaFuel sponsor policy first (dry run shows `sponsorable: ❌`); (c) ship without heartbeats (the 06-08 mint tx still proves pillar 3). Full evidence in the registration log.

**Open user-owned items:** ① TG: confirm the deadline *hour* (12:00 vs 17:30 UTC) + whether pre-window swaps from the registered wallet are unscored (0.1); ② fund the x402 pay wallet `0xEb7bF36aab4912c955474206EF0b835170389655` with ~$10 USDC **on Base** (0.8 — bal $0.00); ③ create the DoraHacks BUIDL draft (2.5); ④ install `twak` CLI on this machine (`npm i -g @trustwallet/cli`, Node ≥ 22.14) so `compete status` runs locally; ⑤ the in-flight `web/src/index.css` dot-grid edit was left uncommitted (not mine to ship).

### 2026-06-12 (cont.) — identity must be minted FROM the agent wallet 0xE8A3…6215 (corrected)
Corrected understanding (the agent wallet is `0xE8A30d24BbA030D3e8a844bD1c4F6e1374EA6215`
= `AGENT_TRADING_ADDRESS`, the contest-registered wallet — NOT the bnbagent keystore).
On-chain reads against ERC-8004 registry `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`:
- `balanceOf(0xE8A3…6215) = 0` — **the agent wallet owns no identity.**
- `ownerOf(1313) = 0x178393…ca4e` — an **unrelated EOA**; "agentId 1313" in the strategy
  doc is on the wrong wallet, not ours. (`0xEb7b…9655` is a throwaway keystore bnbagent
  auto-made because `AGENT_PRIVATE_KEY` is unset — minting to it repeats the mistake.)
- `0xE8A3…6215` already holds **~0.00364 BNB** (direct-gas mint is already funded).

**Root cause:** bnbagent signs the mint from `AGENT_PRIVATE_KEY` if set, else a random
self-managed keystore. With the key unset it minted to a stray wallet. Fix = sign as
the agent wallet.

Staged `scripts/remint_identity.py` (+ `make remint_identity`) — DRY-RUN by default,
mints ONLY the identity (contest registration already confirmed on-chain), and now
**HARD-REFUSES to mint unless the signer == `AGENT_TRADING_ADDRESS`** (encodes the
lesson) AND a gas path is ready. Verified live: it currently blocks with `WRONG SIGNER`
because `AGENT_PRIVATE_KEY` is unset (bnbagent would sign as `0xEb7b…9655`).

**To complete — PREREQUISITE 1 (signer), pick ONE:**
- Set `AGENT_PRIVATE_KEY` = the private key of `0xE8A3…6215` in `.env` (best: unifies
  trade + identity + registration on one wallet), then use this script; **OR**
- if that key is twak-custodied / non-exportable, mint via **`twak erc8004 register`**
  (twak signs with the custodied agent key — no export; bypasses this script).

**PREREQUISITE 2 (gas), pick ONE:**
- **Direct gas (already funded):** `AGENT_USE_PAYMASTER=false` — `0xE8A3…6215` has BNB.
- **Gasless:** MegaFuel sponsor policy on nodereal.io whitelisting registry
  `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` + wallet `0xE8A3…6215`, until
  `make verify_nodereal ARGS="--network mainnet"` shows `sponsorable ✅`.

Then (bnbagent path): `make remint_identity` (expect `READY`) → `make remint_identity ARGS="--mint"`,
set `AGENT_HEARTBEAT_ENABLED=true`, back up `~/.bnbagent/wallets/<addr>.json`.

**⚠ SECURITY (2026-06-12):** `AGENT_WALLET_PASSWORD` was accidentally printed in cleartext
during a presence-check (shell bug; stayed in-session, not sent anywhere external).
**Rotate it and stop reusing it** — it encrypts wallet keystores. (User deferred: fix
functionality first.)

### 2026-06-12 (cont.) — SETTLED MODEL: two wallets; identity key PINNED (gap filled)
Per the bnbagent SDK env docs (PRIVATE_KEY "Recommended, Auto-generate"; "encrypted to
~/.bnbagent/wallets/ on first run, then removable"), the **identity wallet is bnbagent's
own auto-generated wallet `0xEb7bF36aab4912c955474206EF0b835170389655`** — a *separate*
wallet from the twak trading wallet `0xE8A3…6215`. The minted identity NFT **declares**
`trading_wallet=0xE8A3…6215` in its metadata, so the two are linked on-chain. This
two-wallet split is the SDK's intended pattern — supersedes the earlier "mint must be
from 0xE8A3…6215" note. (So no need to export the twak-custodied trading key.)

**Real root cause of losing 1313:** the auto-generated key was never PINNED, so bnbagent
regenerated a different keystore and the identity ended up on a wallet whose key we lost.

**DONE this session — key pinned (the gap):** `make remint_identity ARGS="--pin-key"`
exported the keystore key via the SDK and wrote `AGENT_PRIVATE_KEY` + `AGENT_IDENTITY_ADDRESS=0xEb7b…9655`
to `.env` (gitignored — key never committable). The identity wallet is now **permanent**;
bnbagent will reuse it, not regenerate. `scripts/remint_identity.py` rewritten: `--pin-key`
mode added; the old "wrong signer" hard-block replaced by a **KEY-NOT-PINNED guard** (the
true lesson) + the gas-path guard. Verified live: dry-run now shows `key pinned ✅`.

**REMAINING gap before the mint — a gas path (your action), pick ONE:**
- **Direct gas (simplest):** set `AGENT_USE_PAYMASTER=false` in `.env` and send ~0.005 BNB
  to the identity wallet `0xEb7bF36aab4912c955474206EF0b835170389655`.
- **Gasless:** MegaFuel sponsor policy on nodereal.io whitelisting registry
  `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` + wallet `0xEb7b…9655`, until
  `make verify_nodereal ARGS="--network mainnet"` shows `sponsorable ✅`.

Then: `make remint_identity` (expect READY) → `make remint_identity ARGS="--mint"` →
set `AGENT_HEARTBEAT_ENABLED=true`. Back up `~/.bnbagent/wallets/<addr>.json`.
NOTE: this same wallet is the x402 payment wallet — fund it with USDC on **Base** too (item ②).

### 2026-06-12 (cont.) — ✅ IDENTITY MINTED + HEARTBEAT LIVE (end-to-end proven)
User authorized using the twak trading wallet's funds (it's machine-generated, not on
their phone). Executed end-to-end, all via intended tooling (no key extraction):
1. **twak CLI found** already installed under nvm node v26.3.0 (`twak` 0.18.0).
2. **Gas transfer via twak:** 0.0015 BNB trading → identity wallet, destination pinned
   with `--confirm-to`. Tx `0x3de881…189d` (status 1). Trading wallet keeps ~0.0021 BNB.
3. **SDK gas-floor bug found + fixed:** bnbagent hardcodes `MIN_GAS_PRICE_WEI = 3 gwei`
   (~60x BSC's live 0.05 gwei) — priced the mint at 0.0037 BNB (> all our funds pooled).
   Patched at runtime to max(2x live, 0.1 gwei): in `remint_identity.py` for the mint and
   in `identity.py::_lower_sdk_gas_floor()` for heartbeats (direct-gas mode only;
   paymaster path untouched).
4. **MINTED: `AGENT_ID=133085`**, owner = identity wallet `0xEb7b…9655` (verified
   `ownerOf` on-chain), trading wallet declared in metadata. Gas: ~0.000119 BNB total.
   Proof artifact: `data/compete/identity_mint_2026-06-12.json`.
5. **Heartbeat proven end-to-end:** `AGENT_HEARTBEAT_ENABLED=true`; one sim allocator
   tick (REBALANCE, NAV 1006.55→1006.43, NL rationale) fired a real on-chain heartbeat
   (nonce 2→3, 0.000029 BNB ≈ 2¢). Remaining 0.00135 BNB ≈ 46 heartbeats (week needs ~7-14).
6. Suite green after all changes: **1106 passed** (incl. a test-isolation fix in
   `test_agent.py` — real `.env` now sets `AGENT_IDENTITY_ADDRESS`, the test must blank it).

**Still open:** x402 needs ~$1-2 USDC on **Base** to `0xEb7b…9655` (nothing to rotate —
the 5 USDT is on BSC); optional: MegaFuel sponsor policy → flip `AGENT_USE_PAYMASTER=true`
for gasless ops; back up `~/.bnbagent/wallets/0xEb7b….json`; rotate the leaked password.

### 2026-06-12 (cont.) — ✅ PHASE 2 COMPLETE (C1, M4, M1, M2, H4 + license gap)
- **README rewritten** (12 sections, judge-facing momentum-agent story, agentId 133085,
  one numbers-vintage 17.3%/15.4, live links, compliance line, 2 tagged `<TBD:` placeholders
  for demo + DoraHacks URLs). Legacy ICT README archived verbatim at
  `docs/archive/README_ictbot_upstream.md` (banner + relocated links).
- **Adversarial claims-check (3 lenses): 0 blockers, 0 majors on the README itself.** The
  consistency lens caught 2 majors in *other* docs still telling the pre-correction identity
  story — fixed: decision record §4 (two-wallet model, direct-gas mint) + the hackathon plan's
  LOCKED header + RESOLVED pointers in the audit (1313 → 133085). Also patched: ta_rank wording
  (A/B-gated), test-count phrasing, §3-vs-§7 vintage note, operations.md stale references,
  archive-table deletion annotations, TG debug scripts inventoried.
- **LICENSE (MIT)** added + pyproject `license` field + momentum-allocator `description` (M4).
- **`.env.example` complete:** 46 missing vars documented; reproducible checker committed
  (`scripts/check_env_example.py` → `missing: 0`).
- **Hygiene:** `fire_test_order.py`/`close_test_order.py` deleted; compose `dashboard` service
  legacy-commented (`docker compose config` → scanner/prometheus/grafana); dashboard reseeded
  to the 6/12 forward tick so `/api/nav` matches the README.
- Commits `4968d99`, `12db3a2`, `ad0b312`; suite re-verified 1106 passed during the claims check.

**Remaining user-owned items (unchanged):** deadline-hour + pre-window-swaps TG check (0.1);
~$1-2 USDC on **Base** → `0xEb7b…9655` (0.8, needed for Phase 4 receipts); DoraHacks BUIDL
draft (2.5); keystore backup; password rotation. **Next session: Phase 3 — the five
submission docs (strategy.md → twak_integration.md → x402_receipts.md skeleton → SUBMISSION.md
→ DEMO.md).**

### 2026-06-12 (cont.) — ✅ PHASE 4 COMPLETE (x402 receipts — real on-chain settlement)
User funded the identity wallet with $1.6142 USDC on Base. Generating receipts surfaced
a real bug: the x402 paid path had NEVER settled end-to-end (`RUN_X402_SETTLE` is a
skipped opt-in test), and the hand-rolled resend used the wrong format. Debugged live
against CMC's facilitator and fixed two things in `src/ictbot/data/x402_cmc.py`:
- **header** is `PAYMENT-SIGNATURE` (CMC's published name), not the bare-spec `X-PAYMENT`
  (X-PAYMENT is silently ignored → instant re-challenge);
- the **V2 payload must echo** the chosen `accepted` option AND the `resource`
  (facilitator returns "Missing accepted" / "payment header resource is null" otherwise).

**6 real settlements on Base ($0.06):** 1 format-discovery probe + **5 clean receipts**
across both payable endpoints (`dex/search` ×3, `cryptocurrency/quotes/latest` ×2). On-chain
balance 1.614218 → 1.554218 confirms the spend; `data/x402/receipts.json` holds the 5
settled rows ($0.05).

**Published to the dashboard:** `infra/seed/x402_receipts.json` + a Dockerfile COPY so the
live Render API serves it; static snapshot refreshed (`agent_hub.x402` + `pillars.cmc.receipts`
= 5 settled / $0.05; live Base balance shown). `render.yaml X402_ENABLED=true` is **display-only
safe** (zero-secret deploy has no wallet password → `available()`==False → the API can never
pay; only the read-only balance read runs). `X402_ENABLED=true` also set locally so the live
agent pays per CMC read going forward. Tests updated to the corrected contract + x402-off
isolation; **suite 1106 passed**. Commit `3f5c91c` (push triggers Render redeploy).

**x402 budget:** ~$0.06 of $1.6142 used; ~$1.55 left (≈155 paid calls / plenty for the week).

### 2026-06-12 (cont.) — Phase 4 verification caught two more bugs (both fixed)
Verifying the live dashboard after the Phase-4 push surfaced two issues the real
receipts exposed (commit `e14424c`):
1. **`/api/snapshot` 500** (`ResponseValidationError`): `AgentHubX402.last_status` was
   typed `int | None` in `schemas.py` — it only ever validated because it was always
   `None` (no receipts); a real `"settled"` string broke FastAPI's response_model →
   the SPA's main endpoint 500'd (it had been falling back to the static snapshot).
   Latent since the schema was written; fixed to `str | None`. (`CmcApiOut.last_status`
   stays `int` — that one is an HTTP status code.) Verified via `SnapshotOut.model_validate`.
2. **Test suite was spending real USDC:** the sim-tick hardening tests run a real
   allocator tick that calls the live `dex_search`; with `X402_ENABLED=true` in `.env`
   + the funded wallet, `make test` settled 5 stray real payments (07:11-07:20). Added
   an autouse `conftest` guard forcing `x402_enabled=False` for every test. Verified:
   full-suite USDC balance unchanged (1.504218 → 1.504218).

Net x402 spend this session: **$0.11** of $1.6142 (1 format probe + 5 intentional + 5
test-induced, all real settled). Receipts artifact = **10 settled ($0.10)** across both
payable endpoints; the only code payer remains `run_allocator.py` (the dashboard read
path is balance-read-only — no bleed-on-poll). ~$1.50 USDC left (≈150 paid calls).

**⚠ stale cron (user):** `crontab -l` shows `forward_tick.sh` at 13:07 + 20:43 UTC
pointing at the OLD path `/Users/apple/Desktop/BNB Hack * CMC/` (current repo is
`BNB-Hack-CMC`). Re-point or remove those before the contest, and note the live agent's
forward ticks now pay x402 per tick (~$0.01) since `X402_ENABLED=true` is in `.env`.

### 2026-06-12 (cont.) — ✅ PHASE 3 COMPLETE (the five submission docs — audit C2)
Authored all five judge-facing docs, curated from the decision record / A/B doc / code /
live on-chain artifacts and aligned to the README's canonical vintage:
- **docs/strategy.md** — honest 5-way negative-edge audit → regime-adaptive allocator →
  CMC A/B levers → DQ-safety → reproduce-it.
- **docs/x402_receipts.md** — the real PAYMENT-SIGNATURE flow + safety rails + **10 settled
  receipts ($0.10)** across both payable endpoints (real data, not placeholder).
- **docs/twak_integration.md** — TWAK special-prize rubric map (weights flagged unverified)
  + sole-signer depth + self-custody + guardrails + on-chain proof appendix.
- **SUBMISSION.md** — ~450-word DoraHacks text, locked-strategy hook, links block.
- **DEMO.md** — 3-5 min recording script on the momentum allocator (drops superseded
  ICT/exit-watcher/Prom items).

**Adversarial claims-check (3 lenses): links lens clean, every number verified vs sources +
on-chain artifacts.** Patched: 2 fabricated CLI-flag claims in twak_integration.md
(`--max-usd`, `--confirm-to` — removed/softened to the real broker controls + artifact-backed
transfer), the x402 balance-delta caveat, heartbeat phrasing softened to "each tick it runs"
(mint + first heartbeat verified), strategy.md §3 vintage clause, and the decision-record
06-08 callout (16.8% → 17.3% locked vintage). Commits `22e6cd9`, `0639198`.

**Audit C2 closed.** All build phases (0,1,2,3,4) done. Remaining = user-owned submission
acts only: record the demo video + fill the 3 `<TBD:>` (demo URL, BUIDL URL, sample swap tx);
create the DoraHacks BUIDL; capture registration/mint BscScan screenshots; keystore backup;
password rotation; fix the stale `forward_tick.sh` cron path; flip live config for Jun 22
(Phase 7.5). The repo's documentation set is submission-ready.

### 2026-06-12 (cont.) — ✅ PHASE 5 COMPLETE (hardening + dress rehearsal + live swap)
The live-readiness phase, executed end-to-end (user authorized the live swap as a
minimal round-trip; pre-window swaps confirmed unscored in TG):
- **M3 closed** — 3 trade-floor tests cover the last uncovered `_ensure_trade_floor`
  branches (sell-leg-fail-after-buy→banked==1; needed=3→banked==4; nudge uses the
  largest USD holding). Adversarial verify mutation-tested each: every one fails when
  its branch is broken (non-vacuous). `tests/test_trade_floor.py` 11/11.
- **`make install`** hardened to `.[dev,api,bnb,tg]` (was `[dev]`).
- **🔁 LIVE SWAP — real, on-chain, end-to-end.** `scripts/live_swap_smoke.py` (guarded:
  refuses unless ENABLE_LIVE_TRADING+TWAK_MODE=live, $2 notional cap) fired a minimal
  USDT→CAKE→USDT round-trip through the real TWAK live path. **Both legs `status=1` on
  BSC**, from the trading wallet, on-chain Transfer logs match the amounts:
  buy `0x9d64…67d1`, sell `0xf08f…0380`. Wallet round-tripped back to USDT (~$0.013
  fees; BNB intact — twak sponsored gas). Proof: `data/compete/live_swap_2026-06-12.json`.
  Real tx hashes filled into SUBMISSION.md + README + twak_integration.md (cleared the
  `<TBD: sample swap tx>`). `.env` reverted to `TWAK_MODE=sim`/`ENABLE_LIVE_TRADING=false`.
- **Gate #1 (clean checkout) GREEN** — a fresh `git clone` + venv + suite surfaced a real
  `.env`-dependence bug (`test_twak_cli::test_balance_native_has_no_token_or_coin` assumed
  an ambient `AGENT_TRADING_ADDRESS`); fixed by pinning the address in the test helper.
  Fresh clone now **1108 passed, 0 failed, 10 skipped**.
- **DoD gate** — all three deploy surfaces 200 (`/api/health`, `/api/snapshot`, Vercel);
  `/api/pillars` shows 10 x402 receipts / $0.10; `.env` at safe sim defaults.
- **Adversarial verification (3 lenses): PASS, 0 blockers, 0 majors.** Commits
  `15527ff`, `1d6c397`, `8681eb8`.

NOTE: the working tree also holds an in-progress **"active tokens / token-toggle"** feature
(`active_tokens.py`, `TokenTogglePanel.tsx`, ~30 tests) — left untouched/uncommitted; not
part of Phase 5.
