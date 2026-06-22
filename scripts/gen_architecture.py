#!/usr/bin/env python3
"""Generate docs/architecture.excalidraw — the DETAILED, UNIFORM full-flow execution diagram
of the AVALANCHE momentum agent (AVAX Agentic Payments).

Layout = a strict grid: two balanced top→down stage-banded columns (LEFT: entry → guards → risk
gate · RIGHT: decide → execute → persist), joined by an off-page connector Ⓐ. Every card shares
one size, every row shares one pitch, every guard's SKIP/HALT terminal sits in an aligned outer
column reached by a straight horizontal arrow — no diagonals. A centre lane carries the CMC data
sub-cards + the dd-watch fast loop; the far-right lane carries the strategy core, identity and
Mission Control. Zero ICT.

Emits a complete modern Excalidraw schema (autoResize text, boundElements=[]) PLUS a deterministic
1:1 SVG mirror (docs/architecture.svg) and, if cairosvg is present, a PNG — so the diagram is
viewable in any browser / GitHub, immune to render-cache or frozen-link quirks.
"""
import json
import math
import os

EL = []
_n = [0]
CIRCLED = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤", 6: "⑥", 7: "⑦", 8: "⑧", 9: "⑨",
           10: "⑩", 11: "⑪", 12: "⑫", 13: "⑬", 14: "⑭", 15: "⑮", 16: "⑯", 17: "⑰"}


def _id():
    _n[0] += 1
    return _n[0]


def _el(**kw):
    i = _id()
    d = dict(id=f"el{i}", angle=0, strokeColor="#1e1e1e", backgroundColor="transparent",
             fillStyle="solid", strokeWidth=2, strokeStyle="solid", roughness=0, opacity=100,
             groupIds=[], frameId=None, roundness=None, seed=10007 + i * 131, version=2,
             versionNonce=20011 + i * 977, isDeleted=False, boundElements=[],
             updated=1700000000000, link=None, locked=False)
    d.update(kw)
    return d


def rect(x, y, w, h, stroke, fill, sw=2, rounded=True, dashed=False):
    EL.append(_el(type="rectangle", x=x, y=y, width=w, height=h, strokeColor=stroke,
                  backgroundColor=fill, strokeWidth=sw,
                  strokeStyle="dashed" if dashed else "solid",
                  roundness={"type": 3} if rounded else None))


def diamond(x, y, w, h, stroke, fill, sw=2):
    EL.append(_el(type="diamond", x=x, y=y, width=w, height=h, strokeColor=stroke,
                  backgroundColor=fill, strokeWidth=sw, roundness={"type": 2}))


def ellipse(x, y, w, h, stroke, fill, sw=2):
    EL.append(_el(type="ellipse", x=x, y=y, width=w, height=h, strokeColor=stroke,
                  backgroundColor=fill, strokeWidth=sw))


def text(x, y, s, size=15, color="#1e1e1e", family=2):
    lines = s.split("\n")
    w = max((len(ln) for ln in lines), default=1) * size * 0.55
    h = len(lines) * size * 1.25
    EL.append(_el(type="text", x=x, y=y, width=w, height=h, strokeColor=color, strokeWidth=1,
                  fontSize=size, fontFamily=family, text=s, originalText=s, textAlign="left",
                  verticalAlign="top", containerId=None, lineHeight=1.25, autoResize=True))


def tcenter(cx, cy, s, size=14, color="#1e1e1e", family=2):
    lines = s.split("\n")
    w = max((len(ln) for ln in lines), default=1) * size * 0.6
    h = len(lines) * size * 1.25
    EL.append(_el(type="text", x=cx - w / 2, y=cy - h / 2, width=w, height=h, strokeColor=color,
                  strokeWidth=1, fontSize=size, fontFamily=family, text=s, originalText=s,
                  textAlign="center", verticalAlign="top", containerId=None, lineHeight=1.25,
                  autoResize=True))


def arrow(x1, y1, x2, y2, color="#495057", sw=2.5, label=None, dashed=False):
    EL.append(_el(type="arrow", x=x1, y=y1, width=x2 - x1, height=y2 - y1, strokeColor=color,
                  strokeWidth=sw, strokeStyle="dashed" if dashed else "solid",
                  points=[[0.0, 0.0], [float(x2 - x1), float(y2 - y1)]],
                  lastCommittedPoint=None, startBinding=None, endBinding=None,
                  startArrowhead=None, endArrowhead="arrow", roundness={"type": 2}))
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if abs(x2 - x1) < abs(y2 - y1):      # vertical → label to the side
            text(mx + 7, my - 9, label, 11, color)
        else:                                 # horizontal → label above
            tcenter(mx, my - 11, label, 11, color)


# ---------------- colours (stroke, fill, faint-band) ----------------
DATA = ("#1971c2", "#e7f5ff", "#f3f9ff")
STRAT = ("#2b8a3e", "#ebfbee", "#f4fdf6")
EXEC = ("#3b5bdb", "#edf2ff", "#f5f7ff")
SAFE = ("#c92a2a", "#ffe3e3", "#fff5f5")
IDENT = ("#6741d9", "#f3f0ff", "#f8f6ff")
OBS = ("#0c8599", "#e3fafc", "#f2fcfd")
PROC = ("#495057", "#f8f9fa", "#fbfcfd")
SKIPC = ("#868e96", "#f1f3f5", "#fafafa")

# ---------------- grid ----------------
TOP = 320
PITCH = 150
CARD_W, CARD_H = 440, 100
DIA_W, DIA_H = 320, 100
COL1_X, COL2_X = 320, 1180
C1, C2 = COL1_X + CARD_W / 2, COL2_X + CARD_W / 2     # 540, 1400
TERM_L_X, TERM_L_W = 40, 250
TERM_R_X, TERM_R_W = 1660, 460
GUT_X, GUT_W = 800, 350                                # 800..1150 (between columns)


def ry(i):
    return TOP + i * PITCH


def card(col_x, i, title, subs, role, num=None, dashed=False):
    st, fi = role[0], role[1]
    y = ry(i)
    rect(col_x, y, CARD_W, CARD_H, st, fi, sw=2, dashed=dashed)
    t = f"{CIRCLED[num]}  {title}" if num else title
    text(col_x + 16, y + 9, t, 15, "#1e1e1e")
    yy = y + 33
    for s in subs:
        text(col_x + 16, yy, s, 11.5, st, family=3)
        yy += 16
    return (col_x, y, CARD_W, CARD_H)


def gate(cx, i, label, caption, role=SAFE):
    st, fi = role[0], role[1]
    y = ry(i)
    diamond(cx - DIA_W / 2, y, DIA_W, DIA_H, st, fi, sw=2)
    tcenter(cx, y + DIA_H / 2 - 9, label, 14, "#1e1e1e")
    if caption:
        tcenter(cx, y + DIA_H / 2 + 12, caption, 10, st)
    return (cx - DIA_W / 2, y, DIA_W, DIA_H)


def vconnect(cx, i_from, i_to, label=None, color="#495057"):
    arrow(cx, ry(i_from) + CARD_H, cx, ry(i_to), color, sw=2.5, label=label)


def term(side, i, edge, title, sub, role, dia_cx):
    """Aligned outer-column terminal reached by a straight horizontal arrow."""
    st, fi = role[0], role[1]
    th = 70
    y = ry(i) + (CARD_H - th) / 2
    if side == "L":
        rect(TERM_L_X, y, TERM_L_W, th, st, fi, sw=2.5)
        text(TERM_L_X + 14, y + 11, title, 12.5, "#1e1e1e")
        if sub:
            text(TERM_L_X + 14, y + 31, sub, 9.5, st, family=3)
        arrow(dia_cx - DIA_W / 2, ry(i) + DIA_H / 2, TERM_L_X + TERM_L_W, y + th / 2, st, sw=2.5, label=edge)
    else:
        rect(TERM_R_X, y, TERM_R_W, th, st, fi, sw=2.5)
        text(TERM_R_X + 14, y + 11, title, 12.5, "#1e1e1e")
        if sub:
            text(TERM_R_X + 14, y + 31, sub, 9.5, st, family=3)
        arrow(dia_cx + DIA_W / 2, ry(i) + DIA_H / 2, TERM_R_X, y + th / 2, st, sw=2.5, label=edge)
    return (TERM_L_X if side == "L" else TERM_R_X, y, TERM_L_W if side == "L" else TERM_R_W, th)


def band(col_x, i0, i1, label, role):
    st, _, faint = role
    x = col_x - 22
    y = ry(i0) - 30
    w = CARD_W + 44
    h = (ry(i1) + CARD_H) - y + 14
    rect(x, y, w, h, st, faint, sw=1.5)
    text(x + 12, y + 6, label, 13, st)


def ctx(x, y, w, h, title, sub, body, role, dashed=False):
    st, fi = role[0], role[1]
    rect(x, y, w, h, st, fi, sw=2.5, dashed=dashed)
    text(x + 14, y + 10, title, 13.5, st)
    if sub:
        text(x + 14, y + 30, sub, 9.5, st, family=3)
    text(x + 14, y + (50 if sub else 32), body, 11, "#1e1e1e")


# ============================================================ HEADER
text(60, 34, "AVAX Agentic Payments — Momentum Agent · full execution flow", 30)
text(60, 78, "One allocator tick(), end to end   ·   pillars:  CMC (data)  ·  x402 USDC (payments)  ·  ERC-8004 (on-chain identity)", 15, "#1971c2")
text(60, 104, "Read DOWN the left column (entry → guards → risk), jump at Ⓐ, then DOWN the right column (decide → execute → persist).  Every guard fails safe — skip or halt, never crash.", 12, "#495057")
# legend + return-code key
ly = 134
leg = [("process", PROC), ("◆ decision", SAFE), ("CMC data", DATA), ("strategy", STRAT),
       ("swap exec", EXEC), ("identity", IDENT), ("observability", OBS), ("skip/halt", SKIPC)]
lx = 60
for lab, role in leg:
    rect(lx, ly, 15, 15, role[0], role[1], sw=2)
    text(lx + 21, ly - 1, lab, 11, "#343a40")
    lx += 26 + len(lab) * 7.1
text(60, ly + 26, "return codes:   0 = ok / no-op   ·   1 = drawdown HALT (flattened)   ·   2 = skip this tick (guard tripped)", 11, "#868e96", family=3)

# ============================================================ STAGE BANDS (drawn first → behind)
band(COL1_X, 0, 2, "1 · ENTRY", PROC)
band(COL1_X, 3, 9, "2 · INPUTS & GUARDS", DATA)
band(COL1_X, 10, 12, "3 · RISK GATE", SAFE)
band(COL2_X, 0, 4, "4 · DECIDE · pluggable registry", STRAT)
band(COL2_X, 5, 9, "5 · EXECUTE", EXEC)
band(COL2_X, 10, 13, "6 · PERSIST & SIGNAL", IDENT)

# ============================================================ LEFT COLUMN (entry · guards · risk)
# r0 start
rect(COL1_X, ry(0), CARD_W, CARD_H, "#1e1e1e", "#e9ecef", sw=2.5)
text(COL1_X + 16, ry(0) + 18, "CRON  fires", 16, "#1e1e1e")
text(COL1_X + 16, ry(0) + 46, "live_tick.sh / forward_tick.sh  ·  shell flock", 11.5, "#495057", family=3)
text(COL1_X + 16, ry(0) + 66, "12h forward tick (campaign)  ·  + dd-watch every ~15 min", 11.5, "#495057", family=3)

card(COL1_X, 1, "run_allocator.py  tick(--mode)", ["sim ↔ live · flags: --dd-watch · --resume · --dd-cap", "--anchor-nav · --ensure-daily-floor · --unlock-profit"], PROC, num=1)
g_lock = gate(C1, 2, "lock acquired?", "fcntl flock · per-mode")
card(COL1_X, 3, "load_state", ["HWM · cumulative_swaps · halted · balances", "atomic .tmp+os.replace  ·  corrupt → safe defaults"], PROC, num=2)
card(COL1_X, 4, "fetch 4h candles ×8 → align_close_matrix", ["8 momentum majors · regime-adaptive universe", "CMC 4h candles → disk-cache fallback"], DATA, num=3)
g_bars = gate(C1, 5, "data sufficient?", "≥ 200 bars · ≥ 3 tokens")
g_age = gate(C1, 6, "candles fresh?", "latest bar age ≤ 12h")
card(COL1_X, 7, "CMC reads", ["price_fn · fear_greed", "(flag) build_regime_intel: dominance · mktcap · F&G 7d"], DATA, num=4)
card(COL1_X, 8, "LIVE preflight  +  reconcile", ["_live_preflight: creds · wallet · enable_live", "_reconcile_live → drift? journal RECON_DRIFT"], DATA, num=5, dashed=True)
g_px = gate(C1, 9, "prices ok & NAV>0?", "every px > 0 · nav > 0")
card(COL1_X, 10, "NAV  +  HWM  +  drawdown", ["nav = USDT + Σ holdings·px", "HWM = max(nav, HWM)  ·  dd = (HWM − nav) / HWM"], SAFE, num=6)
g_halt = gate(C1, 11, "already halted?", "state.halted (prior breach)")
g_dd = gate(C1, 12, "dd > cap?", "0.10 campaign · 0.30 DQ")

# left-column vertical flow
vconnect(C1, 0, 1)
vconnect(C1, 1, 2)
vconnect(C1, 2, 3, "yes")
vconnect(C1, 3, 4)
vconnect(C1, 4, 5)
vconnect(C1, 5, 6, "yes")
vconnect(C1, 6, 7, "yes")
vconnect(C1, 7, 8)
vconnect(C1, 8, 9, "ok")
vconnect(C1, 9, 10, "yes")
vconnect(C1, 10, 11)
vconnect(C1, 11, 12, "no")

# left terminals (aligned, straight horizontal)
term("L", 2, "no", "SKIP  (2)", "another tick running", SKIPC, C1)
term("L", 5, "no", "SKIP  (2)", "thin data", SKIPC, C1)
term("L", 6, "no", "SKIP  (2)", "stale — LIVE skips, SIM warns", SKIPC, C1)
term("L", 8, "fail", "SKIP  (2)", "missing creds / live off", SKIPC, C1)
term("L", 9, "no", "SKIP  (2)", "guards a FALSE halt", SKIPC, C1)
term("L", 11, "yes", "return 0", "book flat · no trade", OBS, C1)
# dd>cap → emergency flatten → DD_HALT (special two-pill terminal, aligned at row 12)
fy = ry(12) + (CARD_H - 70) / 2
rect(TERM_L_X, fy, TERM_L_W, 70, SAFE[0], SAFE[1], sw=2.5)
text(TERM_L_X + 14, fy + 10, "EMERGENCY FLATTEN", 12.5, "#1e1e1e")
text(TERM_L_X + 14, fy + 31, "emergency_flatten · sell→USDT · 3× retry", 9, SAFE[0], family=3)
arrow(C1 - DIA_W / 2, ry(12) + DIA_H / 2, TERM_L_X + TERM_L_W, fy + 35, SAFE[0], sw=2.5, label="yes")
rect(TERM_L_X + 18, fy + 86, TERM_L_W - 36, 44, SAFE[0], "#ffc9c9", sw=2.5)
text(TERM_L_X + 32, fy + 96, "DD_HALT  (return 1)", 12, "#1e1e1e")
text(TERM_L_X + 32, fy + 114, "halt=True · source=daily_tick", 9, SAFE[0], family=3)
arrow(TERM_L_X + TERM_L_W / 2, fy + 70, TERM_L_X + TERM_L_W / 2, fy + 86, SAFE[0], sw=2.5)

# off-page connector Ⓐ : leave left column bottom → enter right column top
arrow(C1, ry(12) + CARD_H, C1, ry(12) + CARD_H + 26, STRAT[0], sw=3)
ellipse(C1 - 20, ry(12) + CARD_H + 26, 40, 40, STRAT[0], "#d3f9d8", sw=2.5)
tcenter(C1, ry(12) + CARD_H + 46, "Ⓐ", 18, STRAT[0])
text(C1 + 30, ry(12) + CARD_H + 34, "no — within cap →  continue at Ⓐ (top of DECIDE, right)", 11, STRAT[0])

# ============================================================ RIGHT COLUMN (decide · execute · persist)
ellipse(C2 - 20, ry(0) - 62, 40, 40, STRAT[0], "#d3f9d8", sw=2.5)
tcenter(C2, ry(0) - 42, "Ⓐ", 18, STRAT[0])
arrow(C2, ry(0) - 22, C2, ry(0), STRAT[0], sw=3, label="from RISK")

card(COL2_X, 0, "resolve strategy", ["strategy_select.json (SIM selector) / settings (LIVE pin)", "registry.get(name) → pluggable PortfolioStrategy"], STRAT, num=7)
card(COL2_X, 1, "assemble StratContext", ["regime score (breadth+trend+vol+F&G+CMC) · cap band", "TA-health · TA token-scores · intel · active tokens"], STRAT, num=8)
card(COL2_X, 2, "strat.target_weights_now(ctx)", ["→ WeightDecision{ weights, score, cap }", "momentum_adaptive (default) · arms · overlay-composed"], STRAT, num=9)
card(COL2_X, 3, "target = weights × cap", ["(flag) momentum_tilt by CMC 7-day rel-strength", "deployment preserved · remainder = USDT"], STRAT, num=10)
g_floor = gate(C2, 4, "trade-floor short?", "≥7/wk + ≥1/day · window 06-22→28", role=STRAT)
card(COL2_X, 5, "rebalance diff", ["spot_broker.rebalance(target, prices)", "skip moves < 2% of NAV (min-rebal threshold)"], EXEC, num=11)
card(COL2_X, 6, "SELL overweight → USDT", ["frees quote first · qty = min(bal, −Δ/px)"], EXEC, num=12)
card(COL2_X, 7, "BUY underweight ← USDT", ["spend = min(Δ, USDT bal) · min-notional $1"], EXEC, num=13)
card(COL2_X, 8, "spot swap  (self-custody)", ["Avalanche C-Chain · slippage cap · retry/backoff", "self-custody signer (eth-account) · native AVAX gas"], EXEC, num=14)
g_swap = gate(C2, 9, "swap ok?", "amount_out > 0 AND tx", role=EXEC)
card(COL2_X, 10, "journal  REBALANCE", ["strategy · nav b/a · dd · regime · cap · target · weights", "n_swaps/total/failed · fees · tx[] · rationale"], IDENT, num=15)
card(COL2_X, 11, "save_state  (atomic)", [".tmp + os.replace · HWM · cum_swaps · halted"], IDENT, num=16)
card(COL2_X, 12, "heartbeat → ERC-8004", ["write_heartbeat · set_metadata{ts,nav,rationale}", "web3 eth-account · native AVAX gas · best-effort"], IDENT, num=17)
# r13 end pill
rect(COL2_X + 60, ry(13), CARD_W - 120, 64, "#1e1e1e", "#e9ecef", sw=2.5)
tcenter(C2, ry(13) + 32, "return 0   ✓", 16, "#1e1e1e")

# right-column vertical flow
vconnect(C2, 0, 1)
vconnect(C2, 1, 2)
vconnect(C2, 2, 3)
vconnect(C2, 3, 4)
vconnect(C2, 4, 5, "no / after nudge")
vconnect(C2, 5, 6)
vconnect(C2, 6, 7)
vconnect(C2, 7, 8)
vconnect(C2, 8, 9)
vconnect(C2, 9, 10, "ok")
vconnect(C2, 10, 11)
vconnect(C2, 11, 12)
arrow(C2, ry(12) + CARD_H, C2, ry(13), "#495057", sw=2.5)

# right terminals
term("R", 4, "yes", "FLOOR_NUDGE", "_ensure_trade_floor · bounded round-trips · ~0 NAV", STRAT, C2)
term("R", 9, "no", "failed_swaps[]", "journaled · tick continues (never crashes)", SKIPC, C2)

# ============================================================ CENTRE LANE — campaign overlay + CMC sub-cards + dd-watch
# Campaign overlay (2026-06-13) — the .env-only operator config for the forward sim track.
ctx(GUT_X, ry(0), GUT_W, 300, "CAMPAIGN MODE  (2026-06-13)", "operator overlay · .env + active_tokens.json",
    "TARGET +5–7% · honest: ~21% of 9-day\nwindows full-history, ~9% recent regime\n\n10% DD halt (« 30% DQ)\nPROFIT-LOCK ratchet: anchor 1000\n  arm +5% · trail 3% · bank +10%\n  profit_locked ≠ halted (--unlock-profit)\n≥1-trade/DAY floor (+ ≥7/wk)\n7-token universe · lb 60 · 12h cadence\n\nclean clone = validated baseline", STRAT)
arrow(GUT_X, ry(2) + 60, COL1_X + CARD_W, ry(1) + CARD_H / 2, STRAT[0], sw=2, dashed=True, label="governs the tick")
# CMC Agent Hub MCP (pillar 1) — 8 hosted tools composed into a market-overview skill.
ctx(GUT_X, ry(4), GUT_W, 290, "CMC Agent Hub · MCP", "8 tools → market-overview skill (skill_source=composed)",
    "per-token TA  ·  basket TA-health\nglobal metrics: F&G · BTC-dom · mktcap\nmktcap-TA  ·  derivatives leverage-BRAKE\nmacro-event de-risk GUARD · quotes x-check\nnews brake   →   risk budget ∈ [0,1]\n(local technicals fallback if MCP misses)\nsurfaced live → Mission Control CMC Agent Hub panel", DATA)
ctx(GUT_X, ry(7), GUT_W, 100, "x402 · USDC micropayments", "the agent PAYS for data & GETS PAID (Avalanche Fuji)",
    "402 → sign EIP-3009 (USDC@Avalanche) → resend\nconsumer + provider · settle on Snowtrace · served-jobs ledger", DATA)
# feed ④ CMC reads (left guards) + the regime/cap term (right StratContext)
arrow(GUT_X, ry(7) + CARD_H / 2, COL1_X + CARD_W, ry(7) + CARD_H / 2, DATA[0], sw=2, label="market data")
arrow(GUT_X + GUT_W, ry(4) + 30, COL2_X, ry(1) + CARD_H / 2, DATA[0], sw=1.8, dashed=True, label="risk budget → ctx")

# dd-watch fast loop snapped to the RISK band → SAME ◆ dd>cap gate, clean horizontal (no crossing)
rect(GUT_X, ry(10), GUT_W, 370, SAFE[0], SAFE[2], sw=2.5, dashed=True)
text(GUT_X + 14, ry(10) + 12, "dd-watch — FAST LOOP", 13.5, SAFE[0])
text(GUT_X + 14, ry(10) + 32, "run_allocator.py --dd-watch · ~15 min", 9.5, SAFE[0], family=3)
text(GUT_X + 14, ry(10) + 58,
     "shares the same flock · read-only HWM\nprice + NAV validity guards\n◆ dd > cap?  →  emergency_flatten → DD_HALT\n◆ profit-lock? → arm / bank / trail (intraday)\nflatten-only · no opens · no HWM reset\n\n“drawdown = reaction time”:\nslow rebalance + fast intraday monitor\n→ tighter worst-case loss, locked gains", 11, "#1e1e1e")
arrow(GUT_X, ry(12) + DIA_H / 2, C1 + DIA_W / 2, ry(12) + DIA_H / 2, SAFE[0], sw=2, dashed=True, label="same gate, faster")

# ============================================================ FAR-RIGHT LANE — core · identity · observability
ctx(TERM_R_X, ry(0) - 30, TERM_R_W, 162, "THE CORE — what it optimises", "regime_score.py · pluggable strategy registry",
    "8 momentum majors · regime-adaptive cap 0.40–0.90\npluggable registry: momentum_adaptive (default) + 9 sibling strategies + 9 aliases\n+ de-risk overlays · spot via self-custody signer · NO leverage\ncampaign: 10% halt + profit-lock (lock the good path)\nHONEST EDGE: no fixed 7d alpha → built to SURVIVE the\n30% DQ + PARTICIPATE risk-on. 2,338 windows · 1175 tests.", STRAT)

# Strategy registry + overlays — the pluggable pool the DECIDE stage selects from.
ctx(TERM_R_X, ry(2) - 10, TERM_R_W, 260, "STRATEGY REGISTRY  +  OVERLAYS", "strategy/registry.py · adapters/ · overlays/",
    "19 registered = 10 strategies + 9 aliases\ndefault (locked): momentum_adaptive\nbase: momentum · momentum_fast · dual_momentum · rotation\n  breakout · mean_reversion · grid\noverlay-composed: momentum_voltarget · momentum_mafilter\noverlays (de-risk only, never lever): vol_target · ma_filter\naliases: AVAX_STRATEGY_01–09 (delegate bit-for-bit)\nLIVE pins the default · SIM picks via dashboard", STRAT)
arrow(TERM_R_X, ry(2) + 116, COL2_X + CARD_W, ry(2) + CARD_H / 2, STRAT[0], sw=2, label="registry.get(name)")

# Multi-strategy validation campaign — `make campaign` wires EVERY arm through the 5-stage gate.
ctx(TERM_R_X, ry(4) + 100, TERM_R_W, 290, "MULTI-STRATEGY CAMPAIGN", "make campaign · strategy_campaign.py (every arm, one shot)",
    "5-stage gate per arm (risk-first · no alpha):\n  1 Registered  →  2 Backtest-survival\n     (Gate-A: worst-wk DD <25% · ≥7 t/wk @0.70%)\n  3 Forward-started → 4 Forward-eligible\n     (7d DD <25% · ≥7 t/wk · median wk-ret ≥0)\n  5 Operator sign-off (human: STRATEGY_NAME+LIVE)\n→ verdicts (strategy_gates.json) · GUARDIAN matrix\n→ risk-first leaderboard · default locked · no auto-promote", PROC)
arrow(TERM_R_X + TERM_R_W / 2, ry(4) + 100, TERM_R_X + TERM_R_W / 2, ry(2) + 240, PROC[0], sw=2, dashed=True, label="verdicts → eligible")

ctx(TERM_R_X, ry(10) - 6, TERM_R_W, 176, "MISSION CONTROL · observability", "api/ (Render) + web/ (Vercel)",
    "journal JSONL → FastAPI /api/snapshot · /api/agent-hub\n  state · nav · regime · rebalances · pillars\n  strategy selector + survival/forward verdicts\n  guardian leaderboard · wallet · cmc-api\nReact: EquityCurve · RegimeDial · WeightsDonut\n  RebalanceTable · RationaleTicker · StrategyPanel\n  CmcAgentHubPanel — MCP tools · Skills · x402 exhibit", OBS)
arrow(COL2_X + CARD_W, ry(10) + CARD_H / 2, TERM_R_X, ry(10) + CARD_H / 2, OBS[0], sw=2.5, label="observes")
ctx(TERM_R_X, ry(12) - 4, TERM_R_W, 118, "ERC-8004 · on-chain identity", "agent/identity.py · erc8004_client (web3)",
    "ERC-8004 on-chain identity NFT (#218 on Fuji)\nheartbeat via web3 eth-account · native AVAX gas\none self-custody wallet signs swaps + x402 + owns identity\n(sole signer · non-custodial keeper)", IDENT)
arrow(COL2_X + CARD_W, ry(12) + CARD_H / 2, TERM_R_X, ry(12) + CARD_H / 2, IDENT[0], sw=2.5)


# ---------------- SVG mirror (deterministic, derived from the SAME elements) ----------------
def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _font(family):
    return "ui-monospace, Menlo, monospace" if family == 3 else "Helvetica, Arial, sans-serif"


def emit_svg(elements):
    xs, ys = [], []
    for e in elements:
        xs += [e["x"], e["x"] + e.get("width", 0)]
        ys += [e["y"], e["y"] + e.get("height", 0)]
    pad = 36
    minx, miny = min(xs) - pad, min(ys) - pad
    W, H = (max(xs) + pad) - minx, (max(ys) + pad) - miny
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" '
         f'width="{W:.0f}" height="{H:.0f}">',
         f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>']
    for e in elements:                       # shapes first
        t = e["type"]
        dash = ' stroke-dasharray="8 6"' if e.get("strokeStyle") == "dashed" else ""
        if t == "rectangle":
            rx = 14 if e.get("roundness") else 0
            p.append(f'<rect x="{e["x"]:.1f}" y="{e["y"]:.1f}" width="{e["width"]:.1f}" '
                     f'height="{e["height"]:.1f}" rx="{rx}" fill="{e["backgroundColor"]}" '
                     f'stroke="{e["strokeColor"]}" stroke-width="{e["strokeWidth"]}"{dash}/>')
        elif t == "diamond":
            x, y, w, h = e["x"], e["y"], e["width"], e["height"]
            mx, my = x + w / 2, y + h / 2
            p.append(f'<polygon points="{mx:.1f},{y:.1f} {x + w:.1f},{my:.1f} {mx:.1f},{y + h:.1f} '
                     f'{x:.1f},{my:.1f}" fill="{e["backgroundColor"]}" stroke="{e["strokeColor"]}" '
                     f'stroke-width="{e["strokeWidth"]}"{dash}/>')
        elif t == "ellipse":
            p.append(f'<ellipse cx="{e["x"] + e["width"] / 2:.1f}" cy="{e["y"] + e["height"] / 2:.1f}" '
                     f'rx="{e["width"] / 2:.1f}" ry="{e["height"] / 2:.1f}" fill="{e["backgroundColor"]}" '
                     f'stroke="{e["strokeColor"]}" stroke-width="{e["strokeWidth"]}"{dash}/>')
    for e in elements:                       # arrows
        if e["type"] != "arrow":
            continue
        x1, y1 = e["x"], e["y"]
        x2, y2 = e["x"] + e["width"], e["y"] + e["height"]
        col, sw = e["strokeColor"], e["strokeWidth"]
        dash = ' stroke-dasharray="8 6"' if e.get("strokeStyle") == "dashed" else ""
        p.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" '
                 f'stroke-width="{sw}"{dash}/>')
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        bx, by = x2 - 13 * ux, y2 - 13 * uy
        p.append(f'<polygon points="{x2:.1f},{y2:.1f} {bx - 6 * uy:.1f},{by + 6 * ux:.1f} '
                 f'{bx + 6 * uy:.1f},{by - 6 * ux:.1f}" fill="{col}"/>')
    for e in elements:                       # text on top
        if e["type"] != "text":
            continue
        fs = e["fontSize"]
        weight = "700" if fs >= 18 else ("600" if fs >= 14.5 else "400")
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(e.get("textAlign", "left"), "start")
        x = e["x"] if anchor == "start" else (e["x"] + e["width"] / 2 if anchor == "middle" else e["x"] + e["width"])
        y0 = e["y"] + fs
        lh = fs * e.get("lineHeight", 1.25)
        p.append(f'<text x="{x:.1f}" y="{y0:.1f}" font-size="{fs}" font-family="{_font(e.get("fontFamily", 2))}" '
                 f'font-weight="{weight}" fill="{e["strokeColor"]}" text-anchor="{anchor}" xml:space="preserve">')
        for i, ln in enumerate(e["text"].split("\n")):
            p.append(f'<tspan x="{x:.1f}" dy="{0 if i == 0 else lh:.1f}">{_esc(ln) or " "}</tspan>')
        p.append("</text>")
    p.append("</svg>")
    return "\n".join(p)


# ---------------- write ----------------
# Derive docs/ from THIS file's location (scripts/../docs) so the path can't rot
# when the repo is renamed or cloned (the old hardcoded absolute path silently broke).
DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
out = {"type": "excalidraw", "version": 2, "source": "scripts/gen_architecture.py",
       "elements": EL, "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"}, "files": {}}
with open(f"{DOCS}/architecture.excalidraw", "w") as f:
    json.dump(out, f, indent=2)
print(f"wrote {DOCS}/architecture.excalidraw — {len(EL)} elements")

svg = emit_svg(EL)
with open(f"{DOCS}/architecture.svg", "w") as f:
    f.write(svg)
print(f"wrote {DOCS}/architecture.svg — {len(svg)} bytes")

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode(), write_to=f"{DOCS}/architecture.png", scale=2)
    print(f"wrote {DOCS}/architecture.png (via cairosvg)")
except Exception as exc:
    print(f"PNG skipped ({type(exc).__name__}); architecture.svg is the portable render")
