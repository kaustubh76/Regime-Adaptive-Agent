"""
Read helpers for the dashboard API — the ccxt-free, network-light data layer.

Every function here either reads a JSON/JSONL artifact the allocator already wrote
or calls a key-free pure helper (`identity.profile`, `strategy_spec.summary`,
`heartbeat.age_seconds`). It NEVER constructs a live broker (no ccxt) and never
blocks the poll loop on the network: current weights/regime/F&G are taken from the
latest journal row, and the only optional network call (live CMC Fear&Greed) is
TTL-cached and lazily imported.

Design notes baked in from the plan's risk review:
  - Journal reads are bounded to a tail (default 500 lines) and tolerate a
    truncated final line (a tick caught mid-write).
  - Paths come from `settings.JOURNAL_DIR` (absolute), so reads are CWD-safe.
  - F&G prefers the value embedded in the latest journal row (zero network).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ictbot.settings import DATA_DIR, JOURNAL_DIR, settings

# "sim" = paper forward run (pre-contest); "live" = the real contest track.
_LIVE = settings.dashboard_journal == "live"
JOURNAL = JOURNAL_DIR / ("allocator_live.jsonl" if _LIVE else "allocator_journal.jsonl")
STATE = JOURNAL_DIR / ("allocator_live_state.json" if _LIVE else "allocator_state.json")

DEFAULT_TAIL = 500
_FG_TTL_S = 60.0
_fg_cache: dict = {"value": None, "ts": 0.0}


# --------------------------------------------------------------------------- #
# Low-level artifact reads
# --------------------------------------------------------------------------- #
def read_journal(limit: int = DEFAULT_TAIL) -> list[dict]:
    """Last `limit` parsed JSONL rows, oldest-first. Skips blank/corrupt lines
    (e.g. a final line caught mid-write)."""
    if not JOURNAL.exists():
        return []
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return out


def read_state() -> dict:
    if not STATE.exists():
        return {"hwm": None, "halted": False, "balances": {}}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        data.setdefault("balances", {})
        return data
    except (OSError, ValueError):
        return {"hwm": None, "halted": False, "balances": {}}


def _rebalances(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("event") == "REBALANCE"]


def _latest_rebalance(rows: list[dict]) -> dict | None:
    rebs = _rebalances(rows)
    return rebs[-1] if rebs else None


def _latest_event(rows: list[dict], event: str) -> dict | None:
    for r in reversed(rows):
        if r.get("event") == event:
            return r
    return None


def _fg_label(fg: int | None) -> str:
    if fg is None:
        return "unknown"
    if fg <= 24:
        return "extreme fear"
    if fg <= 44:
        return "fear"
    if fg <= 55:
        return "neutral"
    if fg <= 74:
        return "greed"
    return "extreme greed"


def _explorer_base() -> str:
    """Block-explorer tx base for on-chain links — Snowtrace on Avalanche (Fuji / mainnet)."""
    net = settings.agent_network
    if net == "avax-testnet":
        return "https://testnet.snowtrace.io/tx/"
    if net == "avax":
        return "https://snowtrace.io/tx/"
    if net == "bsc-testnet":
        return "https://testnet.bscscan.com/tx/"
    return "https://bscscan.com/tx/"


def _x402_server_stats() -> dict:
    """The agent's x402 SERVER ledger (served jobs + USDC revenue + last settlement tx) — the
    'agent gets paid' side. Best-effort; zeros when the server hasn't served a paid job yet."""
    try:
        from ictbot.api.x402_server import server_stats

        return server_stats()
    except Exception:
        return {"enabled": bool(settings.x402_server_enabled), "served_jobs": 0,
                "revenue_usdc": 0.0, "last_settlement_tx": None, "last_ts": None, "price_usdc": 0.0}


# --------------------------------------------------------------------------- #
# Card builders (each maps to one endpoint; all return plain dicts)
# --------------------------------------------------------------------------- #
def health_card() -> dict:
    from ictbot.runtime import heartbeat, kill_switch

    age = heartbeat.age_seconds()
    last = heartbeat.last_beat()
    last_iso = (
        datetime.fromtimestamp(last, tz=timezone.utc).isoformat() if last is not None else None
    )
    return {
        "ok": True,
        "heartbeat_age_s": round(age, 1) if age is not None else None,
        "last_beat_iso": last_iso,
        "mode": settings.twak_mode,
        # Which track the dashboard is reading, and whether it disagrees with the
        # agent's execution mode (e.g. viewing the SIM journal while trading LIVE).
        "journal_mode": settings.dashboard_journal,
        "journal_mismatch": settings.dashboard_journal != settings.twak_mode,
        "live_trading_enabled": bool(settings.enable_live_trading),
        "kill_switch_engaged": kill_switch.is_engaged(),
    }


def identity_card() -> dict | None:
    """ERC-8004 profile (key-free; no chain access)."""
    try:
        from ictbot.agent.identity import profile

        return profile()
    except Exception:
        return None


def strategy_card(rows: list[dict] | None = None) -> dict | None:
    try:
        from ictbot.agent.strategy_spec import load_spec, summary

        params, floor, ceiling = load_spec()
        from ictbot.runtime import active_tokens
        from ictbot.strategy.momentum_allocator import CONTEST_TOKENS

        active = active_tokens.load()
        # Which registered strategy is running. Prefer the arm that ACTUALLY produced the latest
        # journaled tick (seeded into the Render image → env-independent: the dashboard reflects
        # what ran even when the serving process lacks the STRATEGY_NAME env). Fall back to the
        # configured default (STRATEGY_NAME, else the ALLOC_ADAPTIVE-derived locked default).
        rows = read_journal() if rows is None else rows
        journaled = (_latest_rebalance(rows) or {}).get("strategy")
        name = journaled or settings.strategy_name or (
            "momentum_adaptive" if settings.alloc_adaptive else "momentum"
        )
        # The locked momentum default keeps its judge-facing config summary
        # (config/strategy.md); a non-default strategy uses the registry one-liner.
        summ = summary(n_tokens=len(active))
        if name not in ("momentum", "momentum_adaptive"):
            try:
                from ictbot.strategy import registry

                summ = registry.get(name).summary(params, n_tokens=len(active))
            except Exception:
                pass
        return {
            "name": name,
            "summary": summ,
            "tokens": list(CONTEST_TOKENS),
            "active": active,
            "params": {
                "top_k": params.top_k,
                "lookback": params.lookback,
                "cap_floor": floor,
                "cap_ceiling": ceiling,
                "rebal_bars": params.rebal_bars,
            },
        }
    except Exception:
        return None


_INCUMBENT = "momentum_adaptive"  # the locked contest default


def _readiness_verdict(
    name: str, survival: dict | None, stability: dict | None, forward: dict | None
) -> dict:
    """Fuse the three signals into ONE contest-readiness verdict for the dashboard.

    Inlined mirror of scripts/contest_readiness._readiness (kept here so the API process
    never imports scripts/ — campaign/forward_promote — into the per-poll read path).
    Never auto-promotes; READY just means all automated gates cleared (human sign-off
    is still the final step)."""
    if name == _INCUMBENT:
        return {"state": "incumbent", "note": "locked contest default"}
    sv_pass = bool(survival and survival.get("passed"))
    grade = (stability or {}).get("grade")
    if not sv_pass:
        return {"state": "not_ready", "note": "survival failed"}
    if grade == "UNSTABLE":
        return {"state": "not_ready", "note": "stability UNSTABLE"}
    if forward and forward.get("forward_eligible"):
        return {"state": "ready", "note": "all gates cleared"}
    note = "forward not yet" if (forward or {}).get("status") == "evaluated" else "forward accruing"
    return {"state": "in_progress", "note": note}


def strategies_card() -> dict:
    """The registry menu + persisted verdicts + the current SIM selection — powers the
    dashboard strategy selector. SIM-only: `current` is what the SIM track runs; LIVE
    is operator-controlled and unaffected (enforced in run_allocator)."""
    from ictbot.runtime import stability_grades, strategy_select, verdicts
    from ictbot.strategy import registry
    from ictbot.strategy.momentum_allocator import CONTEST_TOKENS

    default = settings.strategy_name or (
        "momentum_adaptive" if settings.alloc_adaptive else "momentum"
    )
    current = strategy_select.load(default)
    vmap = verdicts.load()
    gmap = stability_grades.load()  # robust/fragile/unstable grades (make stability)
    items = []
    for name in registry.available():
        try:
            summ = registry.get(name).summary(
                registry.get(name).default_params(), n_tokens=len(CONTEST_TOKENS)
            )
        except Exception:
            summ = name
        alias_of = registry.alias_target(name)
        # An alias inherits its target arm's verdict/grade when it has none of its own (the
        # logic is identical, so re-validating under the alias name is unnecessary).
        v = vmap.get(name) or (vmap.get(alias_of) if alias_of else None) or {}
        stab = gmap.get(name) or (gmap.get(alias_of) if alias_of else None)
        survival, forward = v.get("survival"), v.get("forward")
        items.append(
            {
                "name": name,
                "summary": summ,
                "current": name == current,
                "alias_of": alias_of,
                "survival": survival,
                "forward": forward,
                "stability": stab,
                # SCOREBOARD (backtest perf) — pass-through of the persisted `perf`; never an edge claim.
                "scoreboard": v.get("perf"),
                "readiness": _readiness_verdict(name, survival, stab, forward),
            }
        )
    return {"items": items, "current": current}


def state_card(rows: list[dict] | None = None) -> dict:
    rows = read_journal() if rows is None else rows
    state = read_state()
    latest = _latest_rebalance(rows)
    nav = latest.get("nav_after") if latest else (state.get("hwm") or settings.alloc_start_usdt)
    weights = (latest.get("weights_after") or {}) if latest else {}
    # Halt reason/time — surfaced from the latest DD_HALT row so the dashboard can
    # show WHY the agent stopped, not just that it did.
    halted = bool(state.get("halted"))
    halt = _latest_event(rows, "DD_HALT")
    halt_reason = halt_ts = None
    if halted:
        if halt and halt.get("dd") is not None:
            halt_reason = (
                f"drawdown {halt['dd'] * 100:.1f}% > cap {(halt.get('dd_cap') or 0) * 100:.0f}%"
            )
            halt_ts = halt.get("ts")
        else:
            halt_reason = "drawdown halt"
    # Trades toward the >=7 contest floor (prefer the latest rebalance row, which
    # journals the running count; fall back to state).
    cum = (latest or {}).get("cumulative_swaps")
    if cum is None:
        cum = state.get("cumulative_swaps", 0)
    # PnL-campaign profit-lock status — surfaced from the persisted state (authoritative)
    # so the dashboard can show "ARMED +X%" / "PROFIT LOCKED". Derived from the state
    # file (not settings) so it works zero-secret on the cloud: a campaign anchor in the
    # state IS the signal the campaign is live. None when no anchor was ever set.
    profit_lock = None
    anchor = state.get("campaign_start_nav")
    if anchor:
        profit_lock = {
            "armed": bool(state.get("profit_lock_armed")),
            "locked": bool(state.get("profit_locked")),
            "campaign_start_nav": anchor,
            "cum_ret": round(nav / anchor - 1.0, 4) if (nav and anchor) else None,
            "peak_since_trigger": state.get("peak_since_trigger"),
            "lock_floor": state.get("lock_floor"),
        }
    return {
        "hwm": state.get("hwm"),
        "halted": halted,
        "halt_reason": halt_reason,
        "halt_ts": halt_ts,
        "nav": nav,
        "balances": state.get("balances") or {},
        "weights": weights,
        "cumulative_swaps": int(cum or 0),
        "trade_floor": int((latest or {}).get("trade_floor_min", settings.trade_floor_min)),
        "profit_lock": profit_lock,
    }


def nav_card(rows: list[dict] | None = None) -> dict:
    rows = read_journal() if rows is None else rows
    rebs = _rebalances(rows)
    curve = [
        {"ts": r["ts"], "nav": r.get("nav_after")} for r in rebs if r.get("nav_after") is not None
    ]
    dd_series = [{"ts": r["ts"], "dd": float(r.get("dd_from_hwm") or 0.0)} for r in rebs]
    state = read_state()
    fallback_nav = state.get("hwm") or settings.alloc_start_usdt
    return {
        "curve": curve,
        "current_nav": curve[-1]["nav"] if curve else fallback_nav,
        "hwm": state.get("hwm") or fallback_nav,
        "drawdown": {
            "current": dd_series[-1]["dd"] if dd_series else 0.0,
            "series": dd_series,
        },
        "caps": {"team": 0.15, "dq": 0.30, "configured": settings.max_drawdown_frac},
    }


def _fear_greed_with_fallback(latest: dict | None) -> tuple[int | None, bool]:
    """Prefer the F&G already in the latest journal row (zero network). Only fall
    back to a TTL-cached live CMC call. Returns (value, stale)."""
    if latest and latest.get("fear_greed") is not None:
        return int(latest["fear_greed"]), False
    now = time.time()
    if now - _fg_cache["ts"] < _FG_TTL_S:
        return _fg_cache["value"], _fg_cache["value"] is not None
    try:
        from ictbot.data.cmc import fear_greed

        val = fear_greed(settings.cmc_api_key or None)
    except Exception:
        val = None
    _fg_cache.update(value=val, ts=now)
    return val, True


def regime_card(rows: list[dict] | None = None) -> dict:
    rows = read_journal() if rows is None else rows
    latest = _latest_rebalance(rows)
    fg, stale = _fear_greed_with_fallback(latest)
    return {
        "regime_score": (latest or {}).get("regime_score"),
        "fear_greed": fg,
        "fear_greed_label": _fg_label(fg),
        "deploy_cap": (latest or {}).get("deploy_cap"),
        "stale": stale,
    }


def rebalances_card(n: int = 10, rows: list[dict] | None = None) -> dict:
    rows = read_journal() if rows is None else rows
    base = _explorer_base()
    items = []
    for r in _rebalances(rows)[-n:][::-1]:  # newest-first
        items.append(
            {
                "ts": r.get("ts"),
                "event": r.get("event", "REBALANCE"),
                "mode": r.get("mode", "sim"),
                "strategy": r.get("strategy"),  # which registered strategy produced this tick
                "candle_source": r.get("candle_source"),  # data provenance (None in old rows)
                "quote_source": r.get("quote_source"),  # 7d-tilt source: cmc_ws | rest | None
                "onchain_signals": r.get("onchain_signals"),  # CMC on-chain DEX signals (or None)
                "nav_before": r.get("nav_before"),
                "nav_after": r.get("nav_after"),
                "n_swaps": r.get("n_swaps", 0),
                "n_swaps_total": r.get("n_swaps_total", r.get("n_swaps", 0)),
                "n_failed": r.get("n_failed", 0),
                "failed_swaps": r.get("failed_swaps") or [],
                "fees_usd": r.get("fees_usd", 0.0),
                # Only linkify REAL on-chain hashes (0x…); paper-tick ids ("sim-1") would 404 on Snowtrace.
                "tx": [{"hash": h, "url": f"{base}{h}"} for h in (r.get("tx") or []) if str(h).startswith("0x")],
                "target": r.get("target") or {},
                "weights_after": r.get("weights_after") or {},
                "rationale": r.get("rationale"),
                "x402_dex": r.get("x402_dex"),  # pillar-1 per-tick CMC AI Agent Hub read (or None)
                "active_tokens": r.get(
                    "active_tokens"
                ),  # universe the tick ranked over (None = pre-toggle)
                "profit_lock": r.get(
                    "profit_lock"
                ),  # PnL-campaign ratchet status for this tick (or None)
            }
        )
    return {"items": items}


def rationale_card(n: int = 20, rows: list[dict] | None = None) -> dict:
    rows = read_journal() if rows is None else rows
    items = [
        {"ts": r.get("ts"), "rationale": r.get("rationale")}
        for r in _rebalances(rows)
        if r.get("rationale")
    ]
    return {"items": items[-n:][::-1]}  # newest-first


def token_rotation_card(rows: list[dict] | None = None) -> dict:
    """Per-token activity across the WHOLE journal — which of the contest universe have actually been
    traded — split honestly into two sources:
      • HELD   : appeared in a REBALANCE `weights_after` > 0 (a real momentum top-k holding), and
      • NUDGED : appeared in a FLOOR_NUDGE `tokens` (a ~0-NAV contest-floor round-trip that touches
                 the rest of the universe over the week).
    The momentum allocation only ever holds `top_k` (2) tokens; the floor rotation is what reaches the
    other six. This is NOT an edge claim — the nudges are deliberately ~0 NAV. Drives the dashboard
    'Token Rotation' card (N/8 touched, held vs floor-rotated, last-touched per token)."""
    rows = read_journal() if rows is None else rows
    from ictbot.strategy.momentum_allocator import CONTEST_TOKENS

    EPS = 1e-9
    held: dict[str, dict] = {}  # token -> {"count": int, "last_ts": str|None}
    nudged: dict[str, dict] = {}
    for r in rows:
        ev, ts = r.get("event"), r.get("ts")
        if ev == "REBALANCE":
            for tok, w in (r.get("weights_after") or {}).items():
                if isinstance(w, (int, float)) and w > EPS:
                    e = held.setdefault(tok, {"count": 0, "last_ts": None})
                    e["count"] += 1
                    e["last_ts"] = ts
        elif ev == "FLOOR_NUDGE":
            for tok in r.get("tokens") or []:
                e = nudged.setdefault(tok, {"count": 0, "last_ts": None})
                e["count"] += 1
                e["last_ts"] = ts

    tokens, touched_count = [], 0
    for tok in CONTEST_TOKENS:
        h, ng = held.get(tok), nudged.get(tok)
        source = "both" if (h and ng) else "held" if h else "nudged" if ng else "none"
        touched = source != "none"
        touched_count += int(touched)
        last_ts = max(
            (t for t in ((h or {}).get("last_ts"), (ng or {}).get("last_ts")) if t),
            default=None,
        )
        tokens.append(
            {
                "token": tok,
                "touched": touched,
                "source": source,  # held | nudged | both | none
                "count": (h["count"] if h else 0) + (ng["count"] if ng else 0),
                "last_ts": last_ts,
            }
        )
    return {
        "tokens": tokens,
        "touched_count": touched_count,
        "total": len(CONTEST_TOKENS),
        "held": sorted(held),  # momentum holdings (real allocation)
        "nudged": sorted(nudged),  # contest-floor rotation (~0 NAV)
    }


# --------------------------------------------------------------------------- #
# Three-pillar status (CMC/x402 · TWAK · BNB-SDK/NodeReal) — best-effort, the
# only network reads (NodeReal RPC + Base USDC balance) are TTL-cached so the
# 4s snapshot poll stays fast and never blocks on a cold endpoint.
# --------------------------------------------------------------------------- #
_PILLARS_TTL_S = 60.0
_pillars_net_cache: dict = {"value": None, "ts": 0.0}


def _x402_receipts() -> dict:
    """Summarize data/x402/receipts.json (settled count + USDC spent). Zeros if absent."""
    out = {"total": 0, "settled": 0, "spent_usdc": 0.0, "last_ts": None, "last_status": None}
    try:
        rows = json.loads((DATA_DIR / "x402" / "receipts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if not isinstance(rows, list) or not rows:
        return out
    units = 0
    for r in rows:
        out["total"] += 1
        if r.get("status") == "settled":
            out["settled"] += 1
            try:
                units += int(r.get("value") or 0)
            except (TypeError, ValueError):
                pass
    out["spent_usdc"] = round(units / 1e6, 6)  # USDC is 6dp
    out["last_ts"] = rows[-1].get("ts")
    out["last_status"] = rows[-1].get("status")
    return out


def _commerce_jobs() -> dict:
    """Summarize data/journal/commerce_jobs.jsonl — the ERC-8183 PROVIDER ledger (the agent
    SELLING its CMC Regime Report to other agents). Walks the event stream (CREATE / FUND /
    SUBMIT / SUBMITTED_ONCHAIN / SETTLE) into per-job state. Zeros if absent. Read-only.

    `jobs_served` = distinct jobs the agent actually delivered on-chain (SUBMITTED_ONCHAIN);
    `revenue_u`  = Σ FUND.amount of served jobs / 1e18 (payment token "U" is 18dp)."""
    out = {
        "enabled": bool(settings.erc8183_enabled),
        "network": settings.erc8183_network,
        "jobs_created": 0, "jobs_funded": 0, "jobs_served": 0, "jobs_settled": 0,
        "revenue_u": 0.0, "last_ts": None, "last_event": None,
        "last_deliverable_hash": None, "last_deliverable_url": None, "last_tx": None,
    }
    try:
        lines = (DATA_DIR / "journal" / "commerce_jobs.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    except (OSError, ValueError):
        return out
    jobs: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (ValueError, TypeError):
            continue
        jid = r.get("job_id")
        ev = r.get("event")
        if jid is not None:
            j = jobs.setdefault(str(jid), {})
            if ev == "FUND":
                try:
                    j["amount"] = int(r.get("amount") or 0)
                except (TypeError, ValueError):
                    pass
            elif ev == "SUBMITTED_ONCHAIN":
                j["served"] = True
                if r.get("deliverable_hash"):
                    out["last_deliverable_hash"] = r.get("deliverable_hash")
                if r.get("deliverable_url"):
                    out["last_deliverable_url"] = r.get("deliverable_url")
                if r.get("tx"):
                    out["last_tx"] = r.get("tx")
            elif ev == "SETTLE":
                j["settled"] = True
            if ev == "CREATE":
                j["created"] = True
            if ev == "FUND":
                j["funded"] = True
        out["last_ts"] = r.get("ts") or out["last_ts"]
        out["last_event"] = ev or out["last_event"]
    out["jobs_created"] = sum(1 for j in jobs.values() if j.get("created"))
    out["jobs_funded"] = sum(1 for j in jobs.values() if j.get("funded"))
    out["jobs_served"] = sum(1 for j in jobs.values() if j.get("served"))
    out["jobs_settled"] = sum(1 for j in jobs.values() if j.get("settled"))
    units = sum(int(j.get("amount") or 0) for j in jobs.values() if j.get("served"))
    out["revenue_u"] = round(units / 1e18, 8)  # payment token "U" is 18dp
    return out


def _commerce_service(net: dict, link: dict) -> dict:
    """The ERC-8183 service the agent ADVERTISES — what it sells, anchored to its ERC-8004
    identity. Key-free: reuses the SAME public values the `nodereal` pillar derives (no private
    key / wallet password). The capability is real even before the first job settles, so the
    panel shows the genuine offering rather than a blank."""
    try:
        from ictbot.agent.identity import COMMERCE_CAPABILITIES

        caps = list(COMMERCE_CAPABILITIES)
    except Exception:
        caps = []
    return {
        "name": "CMC Regime Report",
        "report_schema": "cmc-regime-report/v1",
        "price": int(settings.erc8183_service_price or 0),
        "storage": settings.erc8183_storage,
        "capabilities": caps,
        "provider": net.get("pay_wallet"),
        "agent_id": int(settings.agent_id or 0),
        "registry": link.get("registry"),
    }


def _commerce_preview(rows: list[dict]) -> dict | None:
    """A live preview of the deliverable the agent would sell RIGHT NOW — the genuine product,
    NOT a recompute: sourced from the latest allocator tick (regime read + momentum ranking +
    rationale), reusing `regime_card` / `_latest_rebalance`. Returns None until the first
    rebalance exists (panel degrades). Public market data only — no secrets."""
    latest = _latest_rebalance(rows)
    if not latest:
        return None
    reg = regime_card(rows)
    ranking_src = latest.get("target") or latest.get("weights_after") or {}
    ranking = sorted(ranking_src, key=lambda k: ranking_src.get(k) or 0.0, reverse=True)[:6]
    rationale = latest.get("rationale")
    if isinstance(rationale, str) and len(rationale) > 180:
        rationale = rationale[:180].rstrip() + "…"
    return {
        "ts": latest.get("ts"),
        "strategy": latest.get("strategy"),
        "regime_score": reg.get("regime_score"),
        "deploy_cap": reg.get("deploy_cap"),
        "fear_greed": reg.get("fear_greed"),
        "fear_greed_label": reg.get("fear_greed_label"),
        "momentum_ranking": ranking,
        "rationale": rationale,
    }


def _commerce_can_create() -> bool:
    """Whether a LOCAL operator run can sign BOTH sides (provider + a distinct buyer keystore) — gates
    the dashboard 'create job' button. Key-free boolean (no wallet built); False on the read-only
    deploy, which has no signing password."""
    try:
        from ictbot.agent import commerce

        return bool(commerce.buyer_available())
    except Exception:
        return False


def _pillars_net() -> dict:
    """Network-dependent pillar bits (identity wallet, NodeReal link, Base USDC
    balance), TTL-cached. Each piece is independently guarded — a cold RPC degrades
    that field to None, never the whole card."""
    now = time.time()
    cached = _pillars_net_cache["value"]
    if cached is not None and now - _pillars_net_cache["ts"] < _PILLARS_TTL_S:
        return cached
    net: dict = {
        "pay_wallet": None,
        "link": None,
        "base_usdc_balance": None,
        "sdk_installed": False,
        "identity_wallet_bnb": None,
    }
    try:
        from ictbot.agent import identity

        net["sdk_installed"] = identity.available()
        # display_address() prefers the PUBLIC AGENT_IDENTITY_ADDRESS, so the deployed
        # read-only dashboard needs NO private key / wallet password to show the wallet.
        net["pay_wallet"] = identity.display_address()
        # Identity-wallet BNB — the direct-gas heartbeat funding source. Surfaces whether pillar-3
        # heartbeats CAN land (0 BNB = the broken state). Read-only; TTL-cached with the rest.
        net["identity_wallet_bnb"] = identity.identity_wallet_bnb(net["pay_wallet"])
        if settings.nodereal_api_key:
            net["link"] = identity.verify_paymaster_link()  # current AGENT_NETWORK
    except Exception:
        pass
    try:
        if settings.x402_enabled and net["pay_wallet"]:
            from ictbot.data.x402_cmc import base_usdc_balance

            net["base_usdc_balance"] = base_usdc_balance(net["pay_wallet"])
    except Exception:
        pass
    _pillars_net_cache.update(value=net, ts=now)
    return net


def pillars_card(rows: list[dict] | None = None) -> dict:
    """Status of all three Track-1 pillars for the dashboard. Best-effort; degrades
    cleanly when a pillar isn't configured. Network reads are TTL-cached (60s)."""
    rows = read_journal() if rows is None else rows
    latest = _latest_rebalance(rows)
    net = _pillars_net()
    link = net.get("link") or {}
    return {
        # Pillar 1 — CMC AI Agent Hub (x402 paid data)
        "cmc": {
            "x402_enabled": bool(settings.x402_enabled),
            "pay_wallet": net.get("pay_wallet"),
            "base_usdc_balance": net.get("base_usdc_balance"),
            "receipts": _x402_receipts(),
            "last_dex": (latest or {}).get("x402_dex"),
        },
        # Pillar 2 — Trust Wallet / TWAK (execution)
        "twak": {
            "mode": settings.twak_mode,
            "gasless": bool(settings.twak_gasless),
            "gasless_flag": settings.twak_gasless_flag,
            "cumulative_swaps": int((latest or {}).get("cumulative_swaps", 0) or 0),
            "trade_floor": int((latest or {}).get("trade_floor_min", settings.trade_floor_min)),
        },
        # Pillar 3 — BNB AI Agent SDK + NodeReal/MegaFuel (identity + gasless)
        "nodereal": {
            "api_key_set": bool(settings.nodereal_api_key),
            "network": settings.agent_network,
            "sdk_installed": net.get("sdk_installed"),
            "use_paymaster": bool(settings.agent_use_paymaster),
            "reachable": link.get("reachable"),
            "chain_id": link.get("chain_id"),
            "chain_ok": link.get("chain_ok"),
            "sponsorable": link.get("sponsorable"),
            "wallet": link.get("wallet") or net.get("pay_wallet"),
            "nonce": link.get("nonce"),
            "registry": link.get("registry"),
            "note": link.get("note"),
            "agent_id": int(settings.agent_id or 0),
            "heartbeat_enabled": bool(settings.agent_heartbeat_enabled),
            # Heartbeat HEALTH — is pillar 3 actually alive? `identity_wallet_bnb` shows the
            # direct-gas funding (0 = the broken state); last_heartbeat_* comes from the latest
            # tick's journaled `heartbeat` result (key-free on Render, no on-chain read needed).
            "identity_wallet_bnb": net.get("identity_wallet_bnb"),
            "last_heartbeat_ok": ((latest or {}).get("heartbeat") or {}).get("ok"),
            "last_heartbeat_tx": ((latest or {}).get("heartbeat") or {}).get("tx"),
            # Prefer the heartbeat's own on-chain ts; fall back to the tick ts for older rows.
            "last_heartbeat_ts": (((latest or {}).get("heartbeat") or {}).get("ts")
                                  or ((latest or {}).get("ts") if (latest or {}).get("heartbeat") else None)),
            # WHY the last heartbeat failed (e.g. MegaFuel 403 / sponsor unset / insufficient gas) —
            # so the IdentityCard shows the reason, not just "failing". Public, never a secret.
            "last_heartbeat_error": ((latest or {}).get("heartbeat") or {}).get("error"),
        },
        # SDK prize — ERC-8183 agentic commerce: the SELL side (agent monetizes its CMC analysis).
        # Beyond the job ledger, surface the REAL advertised service + a live deliverable preview so
        # the capability is visible before the first on-chain job settles (no seeded/fake jobs).
        "commerce": {
            **_commerce_jobs(),
            "service": _commerce_service(net, link),
            "preview": _commerce_preview(rows),
            "can_create": _commerce_can_create(),
            # x402 SERVER ledger — the 'agent GETS PAID' side (served jobs + USDC revenue + last
            # settlement tx on Snowtrace). The net-new headline of the Avalanche port.
            "x402_server": _x402_server_stats(),
        },
    }


def wallet_card() -> dict:
    """LIVE on-chain holdings of the trading wallet — the "real funds" card that sits
    beside the SIM journal NAV. Lazy-imports the web3 path so the journal-only reads
    stay light; the read itself is TTL-cached + never raises (see api/onchain.py)."""
    from ictbot.api import onchain

    return onchain.wallet_card()


# --------------------------------------------------------------------------- #
# Market intelligence (CMC Startup tier) + CMC API telemetry. The live intel read is
# TTL-cached (300s) so the 4s poll never drives a CMC fetch; regime_terms come from the
# latest journal row (zero network). Both degrade cleanly when intel is disabled.
# --------------------------------------------------------------------------- #
_INTEL_TTL_S = 300.0
_intel_net_cache: dict = {"value": None, "ts": 0.0}


def _market_intel_net() -> dict | None:
    now = time.time()
    cached = _intel_net_cache["value"]
    if cached is not None and now - _intel_net_cache["ts"] < _INTEL_TTL_S:
        return cached
    snap = None
    try:
        from ictbot.data.cmc_intel import market_intel_snapshot

        snap = market_intel_snapshot()
    except Exception:
        snap = None
    _intel_net_cache.update(value=snap, ts=now)
    return snap


def market_intel_card(rows: list[dict] | None = None) -> dict:
    """CMC market intelligence: live global metrics + F&G trend + movers + categories,
    plus the regime-term breakdown from the latest journal row. Live pieces are None/[]
    when CMC_INTEL_ENABLED is off (the panel degrades to the journal's regime terms)."""
    rows = read_journal() if rows is None else rows
    latest = _latest_rebalance(rows)
    snap = _market_intel_net() or {}
    return {
        "enabled": bool(settings.cmc_intel_enabled),
        "global_metrics": snap.get("global"),
        "fng_trend": snap.get("fng_trend") or [],
        "movers": snap.get("movers") or {"gainers": [], "losers": []},
        "categories": snap.get("categories") or [],
        "regime_terms": (latest or {}).get("regime_terms"),
    }


def cmc_api_card() -> dict:
    """CMC client telemetry (credit budget + rate-limit) — reads the ledger, no network."""
    try:
        from ictbot.data.cmc_client import CMC

        return CMC.telemetry()
    except Exception:
        return {}


def agent_hub_card(rows: list[dict] | None = None) -> dict:
    """CMC Agent Hub exhibit (the 'Best Use of CoinMarketCap' panel): the live
    market-overview SKILL read + TA the agent acted on (from the latest journal row), the
    Data MCP call counts, and the x402 pay-per-call receipts. All read-only / from disk."""
    rows = read_journal() if rows is None else rows
    latest = _latest_rebalance(rows) or {}
    try:
        from ictbot.data import cmc_agent_hub

        mcp = cmc_agent_hub.telemetry()
        tools_available = list(cmc_agent_hub.MCP_TOOLS)
    except Exception:
        mcp = {"enabled": False, "calls": 0, "by_tool": {}}
        tools_available = []
    return {
        # Telemetry-aware: the read-only dashboard mirrors the agent's REAL (seeded) MCP
        # activity, so the exhibit shows whenever there's telemetry to show — not only when
        # this serving process happens to carry the CMC_MCP_ENABLED flag. (Display only; the
        # real trade/skill gate `settings.cmc_mcp_enabled` is untouched.)
        "mcp_enabled": bool(settings.cmc_mcp_enabled)
        or bool(mcp.get("calls") or mcp.get("by_tool")),
        "ta_enabled": bool(settings.alloc_ta_enabled),
        "skill_enabled": bool(settings.cmc_skill_regime),
        "mcp": {
            "calls": mcp.get("calls", 0),
            "by_tool": mcp.get("by_tool", {}),
            # Full Data-MCP catalog (12) so the panel shows exercised/available, not just called.
            "tools_available": tools_available,
            "last_call_ts": mcp.get("last_call_ts"),
        },
        "ta_health": latest.get("ta_health"),
        "ta_source": latest.get("ta_source"),
        "skill": latest.get("cmc_skill"),
        "x402": _x402_receipts(),
        "x402_enabled": bool(settings.x402_enabled),
        # On-chain WebSocket signals the agent harvested this tick — read from the JOURNAL row so it
        # renders on Render (the live cmc_stream cache isn't on the deployed disk).
        "onchain": latest.get("onchain_signals"),
        "onchain_enabled": bool(settings.cmc_onchain_enabled) or bool(latest.get("onchain_signals")),
        # CMC-native rotation levers the agent acted on this tick (sector rotation + multi-window
        # momentum). Read from the JOURNAL row so it renders on Render. None unless a lever is on.
        "rotation": latest.get("cmc_rotation"),
        "rotation_enabled": bool(settings.alloc_sector_tilt or settings.alloc_mom_multi_w)
        or bool(latest.get("cmc_rotation")),
    }


def agent_hub_ping() -> dict:
    """LIVE on-demand probe of CMC's Agent Hub — proves the MCP + composed Skill genuinely work on
    THIS server (not seeded snapshot data). Makes real outbound calls at request time: a live MCP
    `tools/list` + a sample `tools/call` (ping), and a fresh `market_overview()` (the composed
    Skill → risk budget). Never raises; returns `enabled:false` if the server has no key / MCP is
    off. Button-triggered only (not on the snapshot poll); underlying tool calls are TTL-cached."""
    out = {"enabled": False, "tools_live": 0, "sample_ok": False, "last_error": None,
           "ts": datetime.now(timezone.utc).isoformat(), "skill": None}
    try:
        from ictbot.data import cmc_agent_hub

        p = cmc_agent_hub.ping() or {}
        out.update(
            enabled=bool(p.get("enabled")),
            tools_live=int(p.get("tools_live") or 0),
            sample_ok=bool(p.get("sample_ok")),
            last_error=p.get("last_error"),
        )
        if out["enabled"]:
            mo = cmc_agent_hub.market_overview()  # the live composed Skill (TTL-cached tool reads)
            if mo:
                out["skill"] = {
                    "risk_budget": mo.get("risk_budget"),
                    "regime": mo.get("regime"),
                    "headline": mo.get("headline"),
                    "tools_used": mo.get("tools_used") or [],
                }
    except Exception as e:  # noqa: BLE001 — read-only probe must never 500 the dashboard
        out["last_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return out


def snapshot() -> dict:
    """One aggregate read for the React poll loop. Each section is independently
    guarded so a single failure degrades that card, not the whole dashboard."""
    rows = read_journal()

    def _safe(fn, *a):
        try:
            return fn(*a)
        except Exception:
            return None

    return {
        "health": _safe(health_card) or {"ok": False},
        "identity": identity_card(),
        "strategy": _safe(strategy_card, rows) or None,
        "strategies": _safe(strategies_card) or {"items": [], "current": ""},
        "state": _safe(state_card, rows) or {},
        "nav": _safe(nav_card, rows) or {},
        "regime": _safe(regime_card, rows) or {},
        "rebalances": _safe(rebalances_card, 10, rows) or {"items": []},
        "rationale": _safe(rationale_card, 20, rows) or {"items": []},
        # Per-token rotation: which of the 8 have been touched (momentum-held vs ~0-NAV floor nudge).
        "token_rotation": _safe(token_rotation_card, rows)
        or {"tokens": [], "touched_count": 0, "total": 0, "held": [], "nudged": []},
        "pillars": _safe(pillars_card, rows) or {},
        # LIVE on-chain real funds (separate ledger from the SIM NAV above).
        "wallet": _safe(wallet_card) or {"ok": False},
        # CMC Startup-tier market intelligence + the CMC credit-budget telemetry.
        "market_intel": _safe(market_intel_card, rows) or {"enabled": False},
        "cmc_api": _safe(cmc_api_card) or {},
        # CMC Agent Hub — the Data MCP + Skills Marketplace + x402 exhibit.
        "agent_hub": _safe(agent_hub_card, rows) or {"mcp_enabled": False},
        # Server clock at read time — lets the SPA show how fresh the data is (and
        # detect a frozen static fallback) instead of trusting tx timestamps alone.
        "served_at": datetime.now(timezone.utc).isoformat(),
    }
