import { useState } from "react";

import type { StrategyMenuItem } from "../api/types";
import type { UseAllocator } from "../hooks/useAllocator";
import { fmtPct, fmtSignedPct } from "../lib/format";
import Card from "./ui/Card";
import StatusPill, { type Tone } from "./ui/StatusPill";
import { useToast } from "./ui/Toast";
import InfoTip from "./ui/Tooltip";

/**
 * Strategy Lab — the interactive, faithful render of the playbook §11 table. Each
 * registered arm is a selectable row carrying its readiness · GATE (survival) · stability ·
 * forward · SCOREBOARD (backtest return + window win-rate). Selecting an arm switches the
 * SIM/paper track only — the LIVE/contest strategy is operator-controlled (env +
 * ENABLE_LIVE_TRADING) and unaffected here.
 *
 * Framing (load-bearing, per the playbook): SURVIVAL is the GATE (hard pass/fail); PnL &
 * win-rate are a SCOREBOARD over survivors, never an edge claim — so scoreboard numbers are
 * rendered in neutral tone, never green/red. Aliases (AVAX_STRATEGY_0X) are hidden; they map
 * to the same canonical arm.
 */
function readinessView(r: StrategyMenuItem["readiness"]): { label: string; tone: Tone; title?: string } {
  switch (r?.state) {
    case "ready":
      return { label: "READY", tone: "up", title: r.note };
    case "not_ready":
      return { label: "NOT READY", tone: "down", title: r.note };
    case "incumbent":
      return { label: "🔒 LIVE", tone: "violet", title: r.note };
    case "in_progress":
      return { label: r.note?.includes("accruing") ? "ACCRUING" : "IN PROGRESS", tone: "warn", title: r.note };
    default:
      return { label: "—", tone: "neutral" };
  }
}

function survivalView(s: StrategyMenuItem["survival"]) {
  if (!s || s.passed === undefined) return { tone: "neutral" as Tone, label: "—", detail: "" };
  const dd = s.worst_week_dd != null ? `${(s.worst_week_dd * 100).toFixed(1)}% DD` : "";
  const tpw = s.trades_per_week != null ? `${s.trades_per_week.toFixed(0)}/wk` : "";
  return {
    tone: (s.passed ? "up" : "down") as Tone,
    label: s.passed ? "PASS" : "FAIL",
    detail: [dd, tpw].filter(Boolean).join(" · "),
  };
}

function stabilityView(stab: StrategyMenuItem["stability"]): { label: string; tone: Tone } {
  const g = stab?.grade;
  if (!g) return { label: "—", tone: "neutral" };
  if (g === "ROBUST") return { label: "ROBUST", tone: "up" };
  if (g === "FRAGILE") return { label: "FRAGILE", tone: "warn" };
  return { label: "UNSTABLE", tone: "down" };
}

function forwardView(f: StrategyMenuItem["forward"]): { label: string; tone: Tone } {
  if (!f || !f.status) return { label: "—", tone: "neutral" };
  if (f.status !== "evaluated") return { label: "accruing", tone: "neutral" };
  return f.forward_eligible ? { label: "eligible", tone: "up" } : { label: "not yet", tone: "warn" };
}

const btRet = (sb: StrategyMenuItem["scoreboard"]) =>
  sb?.total_return != null ? fmtSignedPct(sb.total_return, 0) : "—";
const winWindow = (sb: StrategyMenuItem["scoreboard"]) =>
  sb?.win_rate != null ? fmtPct(sb.win_rate, 0) : "—";

export default function StrategySelectPanel({ allocator }: { allocator: UseAllocator }) {
  const { data, busy, live, setStrategy } = allocator;
  const { toast } = useToast();
  const [msg, setMsg] = useState<string | null>(null);

  // §11 shows the canonical arms — hide AVAX_STRATEGY_0X aliases (same underlying arm).
  const allItems = data?.strategies?.items ?? [];
  const arms = allItems.filter((s) => !s.alias_of);
  const currentRaw = data?.strategies?.current ?? "—";
  // Resolve current → canonical arm (the operator may have selected via a AVAX_STRATEGY_0X alias).
  const currentCanonical = allItems.find((i) => i.name === currentRaw)?.alias_of ?? currentRaw;
  const challengers = arms.filter((s) => s.readiness?.state !== "incumbent");
  const readyN = challengers.filter((s) => s.readiness?.state === "ready").length;

  async function onSelect(name: string) {
    setMsg(null);
    try {
      const r = await setStrategy(name);
      setMsg(r.message);
      if (r.ok) toast.success(r.message, { key: "strategy", title: "Strategy" });
      else toast.error(r.message, { key: "strategy", title: "Strategy" });
    } catch {
      const m = "controls need the live API — connect the Render backend";
      setMsg(m);
      toast.error(m, { key: "strategy", title: "Strategy" });
    }
  }

  if (arms.length === 0) {
    return (
      <Card label="Strategy Lab" accent="#3861fb">
        <div className="text-[12px] text-muted">strategy registry unavailable</div>
      </Card>
    );
  }

  return (
    <Card
      label="Strategy Lab"
      accent="#3861fb"
      right={
        <span className="flex flex-wrap items-center gap-2">
          <StatusPill tone={readyN > 0 ? "up" : "neutral"} srText={`${readyN} of ${challengers.length} challenger arms contest-ready`}>
            {readyN}/{challengers.length} READY
          </StatusPill>
          <StatusPill tone="brand" srText={`SIM strategy: ${currentRaw}`}>
            SIM: {currentRaw}
          </StatusPill>
        </span>
      }
    >
      <div className="mb-2 flex items-center gap-1 text-[10px] leading-snug text-muted/80">
        <span>
          Survival is the <span className="text-sub">GATE</span> (pass/fail) · PnL &amp; win-rate are a{" "}
          <span className="text-sub">SCOREBOARD</span> over survivors — not an edge claim
        </span>
        <InfoTip term="scoreboard" />
      </div>

      <div className="mb-3 rounded-sm border border-cyan/30 bg-cyan/5 px-2 py-1 text-[11px] text-cyan">
        SIM track only — selecting an arm switches the paper track; the live/contest strategy is
        operator-controlled and unaffected.
      </div>
      {!live && (
        <div className="mb-3 rounded-sm border border-amber/40 bg-amber/10 px-2 py-1 text-[11px] text-amber">
          demo snapshot — connect the live API to switch the SIM strategy
        </div>
      )}

      {/* Desktop: the §11 table; rows are selectable (SIM) */}
      <div className="-mx-1 hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-muted">
              <th className="px-1 pb-2 font-medium">arm</th>
              <th className="px-1 pb-2 font-medium">
                <span className="inline-flex items-center gap-1">ready <InfoTip term="readiness" /></span>
              </th>
              <th className="px-1 pb-2 font-medium">
                <span className="inline-flex items-center gap-1">gate <InfoTip term="gate" /></span>
              </th>
              <th className="px-1 pb-2 font-medium">
                <span className="inline-flex items-center gap-1">stability <InfoTip term="stabilityGrade" /></span>
              </th>
              <th className="px-1 pb-2 font-medium">
                <span className="inline-flex items-center gap-1">forward <InfoTip term="forwardCheck" /></span>
              </th>
              <th className="px-1 pb-2 text-right font-medium">
                <span className="inline-flex items-center gap-1">bt ret <InfoTip term="backtestReturn" /></span>
              </th>
              <th className="px-1 pb-2 text-right font-medium">
                <span className="inline-flex items-center gap-1">win% <InfoTip term="windowWinRate" /></span>
              </th>
            </tr>
          </thead>
          <tbody>
            {arms.map((s) => {
              const rv = readinessView(s.readiness);
              const sv = survivalView(s.survival);
              const stv = stabilityView(s.stability);
              const fv = forwardView(s.forward);
              const isCurrent = s.name === currentCanonical;
              const selectable = live && !isCurrent && !busy;
              return (
                <tr
                  key={s.name}
                  onClick={selectable ? () => onSelect(s.name) : undefined}
                  onKeyDown={
                    selectable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onSelect(s.name);
                          }
                        }
                      : undefined
                  }
                  tabIndex={selectable ? 0 : undefined}
                  aria-disabled={!selectable}
                  title={selectable ? `Run ${s.name} on the SIM track` : isCurrent ? "current SIM strategy" : undefined}
                  className={`border-t border-edge/60 align-middle transition-colors duration-150 ${
                    isCurrent
                      ? "bg-cyan/10"
                      : selectable
                        ? "cursor-pointer hover:bg-panel2/50 focus:outline-none focus-visible:bg-panel2/70"
                        : "opacity-70"
                  }`}
                >
                  <td className="px-1 py-2">
                    <span className="flex items-center gap-1.5">
                      <span className="font-display text-[13px] font-bold text-ink">{s.name}</span>
                      {isCurrent && <span className="font-mono text-[9px] text-cyan">◀ SIM</span>}
                    </span>
                  </td>
                  <td className="px-1 py-2">
                    <StatusPill tone={rv.tone} srText={rv.title}>
                      {rv.label}
                    </StatusPill>
                  </td>
                  <td className="px-1 py-2">
                    <span className="flex flex-col gap-0.5">
                      <StatusPill tone={sv.tone}>{sv.label}</StatusPill>
                      {sv.detail && <span className="font-mono text-[9px] text-muted">{sv.detail}</span>}
                    </span>
                  </td>
                  <td className="px-1 py-2">
                    <StatusPill tone={stv.tone}>{stv.label}</StatusPill>
                  </td>
                  <td className="px-1 py-2">
                    <StatusPill tone={fv.tone}>{fv.label}</StatusPill>
                  </td>
                  {/* SCOREBOARD — neutral tone on purpose (not an edge claim) */}
                  <td className="px-1 py-2 text-right font-mono text-sub">{btRet(s.scoreboard)}</td>
                  <td className="px-1 py-2 text-right font-mono text-sub">{winWindow(s.scoreboard)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile: one card per arm, same data, tap to select */}
      <ul className="space-y-2 md:hidden">
        {arms.map((s) => {
          const rv = readinessView(s.readiness);
          const sv = survivalView(s.survival);
          const stv = stabilityView(s.stability);
          const fv = forwardView(s.forward);
          const isCurrent = s.name === currentCanonical;
          const selectable = live && !isCurrent && !busy;
          return (
            <li key={s.name}>
              <button
                onClick={selectable ? () => onSelect(s.name) : undefined}
                disabled={!selectable}
                aria-pressed={isCurrent}
                className={`w-full rounded-sm border-3 p-2.5 text-left shadow-brut-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60 disabled:cursor-not-allowed ${
                  isCurrent ? "border-cyan/60 bg-cyan/10" : "border-edge bg-transparent hover:border-muted disabled:opacity-50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5">
                    <span className="font-display text-sm font-bold text-ink">{s.name}</span>
                    {isCurrent && <span className="font-mono text-[9px] text-cyan">◀ SIM</span>}
                  </span>
                  <StatusPill tone={rv.tone} srText={rv.title}>
                    {rv.label}
                  </StatusPill>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                  <span className="flex items-center gap-1 text-muted">
                    gate
                    <StatusPill tone={sv.tone}>{sv.label}</StatusPill>
                    {sv.detail && <span className="font-mono text-[9px] text-muted">{sv.detail}</span>}
                  </span>
                  <span className="flex items-center gap-1 text-muted">
                    stability <StatusPill tone={stv.tone}>{stv.label}</StatusPill>
                  </span>
                  <span className="flex items-center gap-1 text-muted">
                    forward <StatusPill tone={fv.tone}>{fv.label}</StatusPill>
                  </span>
                  <span className="flex items-center gap-1 text-muted">
                    bt ret <span className="font-mono text-sub">{btRet(s.scoreboard)}</span>
                    <span className="ml-1">win {winWindow(s.scoreboard)}</span>
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-[11px] leading-relaxed text-muted">
        {msg ??
          "Click an arm to run it on the SIM track (applies next tick). 🔒 LIVE = the locked contest allocator (momentum_adaptive). No arm is live-eligible until it clears the forward check + operator sign-off."}
      </p>
    </Card>
  );
}
