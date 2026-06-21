import type { UseAllocator } from "../hooks/useAllocator";
import { sectionId } from "../lib/sections";
import AgentCommercePanel from "./AgentCommercePanel";
import Cheatsheet from "./Cheatsheet";
import CmcAgentHubPanel from "./CmcAgentHubPanel";
import CommandPalette from "./CommandPalette";
import ControlPanel from "./ControlPanel";
import KeyboardLayer from "./KeyboardLayer";
import EquityCurve from "./EquityCurve";
import HeroRow from "./HeroRow";
import IdentityCard from "./IdentityCard";
import LiveWalletCard from "./LiveWalletCard";
import MarketIntelPanel from "./MarketIntelPanel";
import NavCard from "./NavCard";
import PnLCard from "./PnLCard";
import RationaleTicker from "./RationaleTicker";
import RebalanceTable from "./RebalanceTable";
import StackStrip from "./StackStrip";
import StatusBar from "./StatusBar";
import SystemDiagnostics from "./SystemDiagnostics";
import StrategySelectPanel from "./StrategySelectPanel";
import Tour from "./Tour";
import TokenRotationCard from "./TokenRotationCard";
import TokenTogglePanel from "./TokenTogglePanel";
import Collapsible from "./ui/Collapsible";
import ErrorBoundary from "./ui/ErrorBoundary";
import DashboardSkeleton from "./ui/Skeleton";
import WeightsDonut from "./WeightsDonut";
import { rotationFromSnapshot } from "../lib/rotation";
import type { ReactNode } from "react";

/** Wrap a panel so a single render failure degrades to a notice, never a blank app.
 * Also stamps a scroll-target id + label so the command palette can jump to it. */
function Panel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ErrorBoundary label={label}>
      <div id={sectionId(label)} data-section-label={label} className="h-full scroll-mt-20">
        {children}
      </div>
    </ErrorBoundary>
  );
}

export default function MissionControl({ allocator }: { allocator: UseAllocator }) {
  const { data, error, stale, lastUpdated, live } = allocator;

  if (!data) {
    // First load / Render cold-start: shimmer skeleton instead of a blank screen.
    // If the API is unreachable AND we have no data at all, offer a retry inline.
    return (
      <>
        <DashboardSkeleton message={error ? "can't reach the agent — retrying…" : "connecting to agent…"} />
        {error && (
          <div className="fixed inset-x-0 bottom-4 flex justify-center">
            <button
              onClick={() => void allocator.refresh()}
              className="rounded-sm border-3 border-cool/50 bg-cool/10 px-4 py-2 font-display text-sm font-bold text-cyan shadow-brut-sm transition hover:bg-cool/20"
            >
              ↻ Retry connection
            </button>
          </div>
        )}
      </>
    );
  }

  const freshness = {
    lastTxTs: data.rebalances.items[0]?.ts ?? null,
    servedAt: data.served_at ?? null,
    live,
  };

  return (
    <div className="mx-auto max-w-[1500px] space-y-6 overflow-x-clip p-4 md:p-6">
      <CommandPalette allocator={allocator} />
      <KeyboardLayer allocator={allocator} />
      <Cheatsheet />
      <Tour />
      {/* ── Utility strip: disambiguate connection / data / mode ── */}
      <ErrorBoundary label="Status bar" fallback={null}>
        <StatusBar
          health={data.health}
          strategy={data.strategy}
          state={data.state}
          connection={{ stale, error, lastUpdated }}
          freshness={freshness}
          onRetry={() => void allocator.refresh()}
        />
      </ErrorBoundary>

      {/* ── TIER A — the three numbers that matter ── */}
      <ErrorBoundary label="Hero">
        <HeroRow
          nav={data.nav}
          regime={data.regime}
          state={data.state}
          health={data.health}
          freshness={freshness}
          identity={data.identity}
          agentId={data.pillars?.nodereal?.agent_id ?? null}
          strategy={data.strategy}
        />
      </ErrorBoundary>

      {/* ── TIER B — supporting performance, funds & market context ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Panel label="Equity curve">
            <EquityCurve nav={data.nav} live={live} candleSource={data.rebalances.items[0]?.candle_source} />
          </Panel>
        </div>
        <div className="lg:col-span-4">
          <Panel label="NAV">
            <NavCard nav={data.nav} state={data.state} live={live} />
          </Panel>
        </div>

        <div className="lg:col-span-7">
          <Panel label="P&L">
            <PnLCard nav={data.nav} />
          </Panel>
        </div>
        <div className="lg:col-span-5">
          <Panel label="Wallet">
            <LiveWalletCard wallet={data.wallet} live={live} />
          </Panel>
        </div>

        <div className="lg:col-span-8">
          <Panel label="Market intelligence">
            <MarketIntelPanel intel={data.market_intel} live={live} />
          </Panel>
        </div>
        <div className="lg:col-span-4">
          <Panel label="Weights">
            <WeightsDonut state={data.state} live={live} />
          </Panel>
        </div>

        {/* CMC Agent Hub — the "Best Use of CoinMarketCap" exhibit: which Data-MCP tools
            the agent called + the composed market-overview skill it acted on + x402. */}
        <div className="lg:col-span-12">
          <Panel label="CMC Agent Hub">
            <CmcAgentHubPanel hub={data.agent_hub} live={live} />
          </Panel>
        </div>

        {/* Agent Commerce — the SELL side (ERC-8183): the agent monetizes its CMC analysis.
            With the CMC Agent Hub above (buy side) this is the two-sided agent-economy exhibit. */}
        <div className="lg:col-span-12">
          <Panel label="Agent Commerce">
            <AgentCommercePanel commerce={data.pillars?.commerce} live={live} />
          </Panel>
        </div>
      </div>

      {/* ── TIER C — collapsible detail & on-chain proof ── */}
      <Collapsible title="Detail & Proof" id="detail-band" defaultOpen>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <Panel label="Rebalances">
              <RebalanceTable rebalances={data.rebalances} />
            </Panel>
          </div>
          <div className="lg:col-span-5">
            <Panel label="Rationale">
              <RationaleTicker feed={data.rationale} />
            </Panel>
          </div>

          <div className="lg:col-span-7">
            <Panel label="Token universe">
              <TokenTogglePanel allocator={allocator} />
            </Panel>
          </div>

          <div className="lg:col-span-5">
            <Panel label="Token rotation">
              <TokenRotationCard
                rotation={rotationFromSnapshot(data)}
                hasLiveField={!!data?.token_rotation}
                live={live}
              />
            </Panel>
          </div>

          <div className="lg:col-span-12">
            <Panel label="Strategy Lab">
              <StrategySelectPanel allocator={allocator} />
            </Panel>
          </div>

          <div className="lg:col-span-12">
            <Panel label="System diagnostics">
              <SystemDiagnostics allocator={allocator} />
            </Panel>
          </div>

          <div className="lg:col-span-12">
            <Panel label="Tech stack & proof">
              <StackStrip pillars={data.pillars} hub={data.agent_hub} identity={data.identity} live={live} />
            </Panel>
          </div>

          <div className="lg:col-span-6">
            <Panel label="Identity">
              <IdentityCard
                identity={data.identity}
                agentId={data.pillars?.nodereal?.agent_id ?? null}
                nodereal={data.pillars?.nodereal}
              />
            </Panel>
          </div>
          <div className="lg:col-span-6">
            <Panel label="Controls">
              <ControlPanel allocator={allocator} />
            </Panel>
          </div>
        </div>
      </Collapsible>

      <footer className="pb-2 pt-1 text-center font-mono text-[11px] text-muted">
        Paper $1k book · live Avalanche C-Chain wallet · 100% CoinMarketCap data · zero exchange data · polling every 4s
      </footer>
    </div>
  );
}
