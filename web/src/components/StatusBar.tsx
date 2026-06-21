import type { ReactNode } from "react";

import type { Health, State, Strategy } from "../api/types";
import { useNow } from "../hooks/useNow";
import { useTheme } from "../hooks/useTheme";
import { ageLabel } from "../lib/format";
import { OPEN_CHEATSHEET_EVENT } from "../lib/cockpit";
import { OPEN_PALETTE_EVENT } from "./CommandPalette";
import HeartbeatRing from "./HeartbeatRing";
import StatusPill, { type Tone } from "./ui/StatusPill";
import InfoTip from "./ui/Tooltip";

/** Discoverable opener for the ⌘K command palette (dispatches a window event so it
 * needs no shared state with the palette). */
function PaletteChip() {
  return (
    <button
      onClick={() => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT))}
      title="Command palette (⌘K)"
      aria-label="Open command palette"
      className="flex h-7 items-center gap-1 rounded-sm border border-edge bg-panel2 px-2 font-mono text-[10px] text-sub transition hover:border-cyan/60 hover:text-cyan focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
    >
      <span aria-hidden>⌘K</span>
    </button>
  );
}

/** Discoverable opener for the `?` keyboard-shortcuts cheatsheet. */
function HelpChip() {
  return (
    <button
      onClick={() => window.dispatchEvent(new Event(OPEN_CHEATSHEET_EVENT))}
      title="Keyboard shortcuts (?)"
      aria-label="Show keyboard shortcuts"
      className="flex h-7 w-7 items-center justify-center rounded-sm border border-edge bg-panel2 font-mono text-[11px] text-sub transition hover:border-cyan/60 hover:text-cyan focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
    >
      <span aria-hidden>?</span>
    </button>
  );
}

/** Compact dark/light toggle for the header. */
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={toggle}
      title={`Switch to ${next} theme`}
      aria-label={`Switch to ${next} theme`}
      className="flex h-7 w-7 items-center justify-center rounded-sm border border-edge bg-panel2 text-sub transition hover:border-cyan/60 hover:text-cyan focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
    >
      <span aria-hidden className="text-sm leading-none">
        {theme === "dark" ? "☀" : "☾"}
      </span>
    </button>
  );
}

function secondsSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 1000;
}

/** One labelled status: small eyebrow + an optional InfoTip + the pill itself. */
function Labeled({ label, tip, children }: { label: string; tip?: ReactNode; children: ReactNode }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="hidden font-display text-[9px] font-bold uppercase tracking-[0.18em] text-muted sm:inline">
        {label}
      </span>
      {tip}
      {children}
    </span>
  );
}

/** Active universe: the toggled subset when present, else the full token list. */
function activeOf(s: Strategy | null | undefined): string[] {
  return s?.active?.length ? s.active : s?.tokens ?? [];
}

/** Data-driven strategy line — composed from structured params so it can never go
 * stale ("top-2 of 8" updates the moment a token is toggled). Falls back to the
 * server summary, then a static string, for old/static snapshots. */
function strategyLine(s: Strategy | null | undefined): string {
  const p = s?.params;
  if (!p) return s?.summary ?? "Avalanche spot momentum allocator";
  const n = activeOf(s).length || s?.tokens.length || 8;
  return (
    `top-${Math.min(p.top_k, n)} of ${n} by ${p.lookback}-bar momentum · inverse-vol · ` +
    `regime-adaptive deploy ${Math.round(p.cap_floor * 100)}–${Math.round(p.cap_ceiling * 100)}% · ` +
    `daily rebalance · self-signed`
  );
}

/**
 * The top utility strip. Its whole job is to disambiguate the three different things
 * the old UI all called "live": the API CONNECTION, the DATA source (live vs the
 * committed demo snapshot), and the agent's trading MODE.
 */
export default function StatusBar({
  health,
  strategy,
  connection,
  freshness,
  state,
  onRetry,
}: {
  health: Health | undefined;
  strategy: Strategy | null | undefined;
  state?: State | undefined;
  connection: { stale: boolean; error: string | null; lastUpdated: number | null };
  freshness?: { lastTxTs: string | null; servedAt: string | null; live: boolean };
  onRetry?: () => void;
}) {
  const live = health?.live_trading_enabled;
  const killed = health?.kill_switch_engaged;
  const halted = state?.halted;
  const fromLive = freshness?.live ?? true;
  const servedAge = secondsSince(freshness?.servedAt);

  // Live "updated Ns ago" ticker — re-renders each second; only meaningful when the
  // poll is actually reaching a live backend (not the frozen demo snapshot).
  const now = useNow(1000);
  const liveAgo =
    fromLive && !connection.error && connection.lastUpdated != null
      ? Math.max(0, Math.round((now - connection.lastUpdated) / 1000))
      : null;

  // 1 — CONNECTION: is the poll loop reaching the backend right now?
  const conn = connection.error
    ? { tone: "down" as Tone, label: "OFFLINE", color: "#ea3943" }
    : connection.stale
      ? { tone: "warn" as Tone, label: "STALE", color: "#f0b90b" }
      : { tone: "up" as Tone, label: "LIVE", color: "#16c784" };

  // 2 — DATA: live API payload, or the frozen snapshot.json fallback?
  const dataPill = fromLive
    ? { tone: "up" as Tone, label: "LIVE DATA" }
    : { tone: "neutral" as Tone, label: "DEMO SNAPSHOT" };

  // 3 — MODE: what is the agent actually allowed to do?
  const mode = halted
    ? { tone: "down" as Tone, label: "HALTED", sr: "trading halted" }
    : killed
      ? { tone: "down" as Tone, label: "KILL-SWITCH", sr: "kill switch engaged" }
      : live
        ? { tone: "armed" as Tone, label: "LIVE-ARMED", sr: "armed for live trading" }
        : { tone: "info" as Tone, label: "PAPER", sr: "paper simulation, no real funds at risk" };

  return (
    <div className="glow-card flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <span
          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full animate-pulseDot"
          style={{ background: conn.color }}
        />
        <div className="leading-tight">
          <div className="flex items-center gap-2 font-display text-base font-bold tracking-tight text-ink">
            Regime-Adaptive Momentum Agent
            {strategy && (
              <StatusPill
                tone={activeOf(strategy).length < strategy.tokens.length ? "brand" : "neutral"}
                srText={`${activeOf(strategy).length} of ${strategy.tokens.length} tokens active`}
              >
                {activeOf(strategy).length}/{strategy.tokens.length} ACTIVE
              </StatusPill>
            )}
            {strategy?.name === "momentum_cmc" && (
              <StatusPill tone="info" srText="every decision input is CoinMarketCap data; zero exchange data">
                100% CMC
              </StatusPill>
            )}
          </div>
          <div className="text-[11px] text-muted">{strategyLine(strategy)}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Labeled label="Connection">
          {onRetry ? (
            <button
              onClick={onRetry}
              title="click to re-poll the API now"
              aria-label={`connection ${conn.label.toLowerCase()} — click to retry`}
              className="flex min-h-[40px] cursor-pointer items-center rounded-sm transition hover:brightness-125 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60 sm:min-h-0"
            >
              <StatusPill tone={conn.tone} dot pulse={conn.label === "LIVE"} srText={`connection ${conn.label.toLowerCase()}, click to retry`}>
                {conn.label}
              </StatusPill>
            </button>
          ) : (
            <StatusPill tone={conn.tone} dot pulse={conn.label === "LIVE"} srText={`connection ${conn.label.toLowerCase()}`}>
              {conn.label}
            </StatusPill>
          )}
          <HeartbeatRing lastUpdated={connection.lastUpdated} live={fromLive} error={connection.error} />
          {liveAgo !== null && (
            <span className="hidden font-mono text-[10px] tabular-nums text-muted sm:inline" aria-label={`updated ${liveAgo} seconds ago`}>
              updated {liveAgo}s ago
            </span>
          )}
        </Labeled>

        <Labeled
          label="Data"
          tip={
            <InfoTip
              side="bottom"
              title="Data source"
              text="LIVE DATA = streamed from the agent's API. DEMO SNAPSHOT = a frozen, real but offline capture used when the API isn't reachable."
            />
          }
        >
          <StatusPill tone={dataPill.tone} srText={fromLive ? "live data" : `demo snapshot ${ageLabel(servedAge)}`}>
            {dataPill.label}
            {!fromLive && servedAge !== null && (
              <span className="ml-1 font-normal normal-case opacity-70">· {ageLabel(servedAge)}</span>
            )}
          </StatusPill>
        </Labeled>

        <Labeled
          label="Mode"
          tip={
            <InfoTip
              side="bottom"
              title="Trading mode"
              text="PAPER = simulated book, no real funds. LIVE-ARMED = cleared to sign real swaps. KILL-SWITCH / HALTED = stopped and flat."
            />
          }
        >
          <StatusPill tone={mode.tone} srText={mode.sr}>
            {mode.label}
          </StatusPill>
        </Labeled>

        <PaletteChip />
        <HelpChip />
        <ThemeToggle />
      </div>
    </div>
  );
}
