import { useState } from "react";
import type { GlossaryKey } from "../lib/glossary";
import type { CommerceBlock, CommerceCreateJobResult } from "../api/types";
import { postCreateCommerceJob } from "../api/client";
import { shortHash, shortAddr, cmcLabel, fmtPctRounded, regimeColor, fgColor, networkLabel, ipfsUrl, getExplorerBase } from "../lib/format";
import Card from "./ui/Card";
import StatusPill from "./ui/StatusPill";
import InfoTip from "./ui/Tooltip";

// The SELL side of the agent economy (ERC-8004 agentic commerce). Violet to distinguish from the
// blue CMC-Hub (buy side). The two panels together tell the "two-sided agent economy" story.
const COMMERCE_VIOLET = "#8b9dff";

function Tile({ label, value, color, tip }: { label: string; value: string; color?: string; tip?: GlossaryKey }) {
  return (
    <div className="rounded-sm border border-edge bg-panel2 px-2.5 py-1.5">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted">
        {label}
        {tip && <InfoTip term={tip} />}
      </div>
      <div
        className="font-mono text-sm font-semibold leading-tight break-words"
        style={{ color: color ?? "rgb(var(--c-ink))" }}
      >
        {value}
      </div>
    </div>
  );
}

function fmtU(n: number): string {
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 6 })} U`;
}

// Exact U → wei (18dp) without float rounding: split on the decimal point and pad/truncate the
// fractional part to 18 digits, then BigInt-combine. "" / invalid → "0".
function uToWei(u: string): string {
  const m = (u ?? "").trim().match(/^(\d*)(?:\.(\d*))?$/);
  if (!m) return "0";
  const whole = m[1] || "0";
  const frac = (m[2] || "").slice(0, 18).padEnd(18, "0");
  return (BigInt(whole) * 10n ** 18n + BigInt(frac || "0")).toString();
}

/**
 * Agent Commerce — the agent SELLS its CMC Regime Report to other agents over on-chain job escrow.
 * The capability is REAL before the first on-chain job settles, so
 * the panel always shows the genuine offering (the advertised service + a live deliverable preview)
 * plus an on-chain job ledger that fills in honestly once a faucet-funded job settles. No fake jobs.
 */
export default function AgentCommercePanel({
  commerce,
  live = true,
}: {
  commerce?: CommerceBlock | null;
  live?: boolean;
}) {
  // "Create a job" — runs the REAL agentic-commerce loop (create→fund→serve→settle) on a LOCAL operator
  // run. `can_create` is false on the read-only cloud deploy (no signing key), so the button is
  // disabled there. Hooks must precede the early `if (!commerce)` return (rules of hooks).
  const canCreate = !!commerce?.can_create;
  const [jobQuery, setJobQuery] = useState("Give me your current CMC regime read + momentum ranking.");
  const [jobPayU, setJobPayU] = useState("0.1"); // U the buyer pays into escrow (real revenue)
  const [jobBusy, setJobBusy] = useState(false);
  const [jobResult, setJobResult] = useState<CommerceCreateJobResult | null>(null);
  const onCreateJob = async () => {
    if (!canCreate || jobBusy || !jobQuery.trim()) return;
    setJobBusy(true);
    setJobResult(null);
    try {
      const wei = uToWei(jobPayU);
      setJobResult(await postCreateCommerceJob(jobQuery, wei !== "0" ? wei : undefined));
    } catch (e) {
      setJobResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setJobBusy(false);
    }
  };

  const caption = (
    <span className="text-[10px] text-muted">
      buys data via x402 · sells its regime report on-chain
    </span>
  );

  // Truly absent (an ancient snapshot with no commerce block) → explain the capability, never blank.
  if (!commerce) {
    return (
      <Card
        label="Agent Commerce · ERC-8004"
        accent={COMMERCE_VIOLET}
        right={<StatusPill tone="neutral">snapshot</StatusPill>}
      >
        <div className="flex h-24 flex-col items-center justify-center gap-1 text-center text-xs text-muted">
          <div>The agent can sell its live CMC Regime Report to other agents via on-chain job escrow.</div>
          {caption}
        </div>
      </Card>
    );
  }

  const explorerBase = getExplorerBase(commerce.network);
  const served = commerce.jobs_served;
  const idle = served === 0;
  const armed = commerce.enabled;
  const service = commerce.service;
  const preview = commerce.preview;

  return (
    <Card
      label="Agent Commerce · ERC-8004"
      accent={COMMERCE_VIOLET}
      right={
        <span className="flex items-center gap-1.5">
          {caption}
          <StatusPill tone={armed ? "up" : "neutral"} dot pulse={live && armed && !idle}>
            {armed ? `armed · ${networkLabel(commerce.network)}` : "config off"}
          </StatusPill>
        </span>
      }
    >
      <div className="space-y-3">
        {/* WHAT THE AGENT SELLS — the advertised service, anchored to its ERC-8004 identity. */}
        {service && (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-muted">sells</span>
              <span className="text-right font-mono text-sm font-semibold" style={{ color: COMMERCE_VIOLET }}>
                {cmcLabel(service.name)}
                <span className="ml-1 text-[10px] font-normal text-muted">{service.report_schema}</span>
              </span>
            </div>
            {service.capabilities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {service.capabilities.map((c) => (
                  <span
                    key={c}
                    className="rounded-sm border border-edge bg-panel2 px-1.5 py-0.5 font-mono text-[10px] text-sub"
                  >
                    {cmcLabel(c)}
                  </span>
                ))}
              </div>
            )}
            {(service.agent_id > 0 || service.provider) && (
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
                {service.agent_id > 0 && (
                  <span>
                    identity <span className="font-mono text-sub">#{service.agent_id}</span>
                  </span>
                )}
                {service.provider && (
                  <a
                    href={`${explorerBase}/address/${service.provider}`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-cyan hover:underline"
                  >
                    {shortAddr(service.provider)} ↗
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {/* LIVE DELIVERABLE PREVIEW — the genuine product the agent would hand over this instant. */}
        {preview ? (
          <div className="space-y-2 border-t border-edge pt-2">
            <div className="text-[10px] uppercase tracking-wider text-muted">live deliverable preview</div>
            <div className="grid grid-cols-3 gap-2">
              <Tile
                label="Regime"
                value={preview.regime_score != null ? preview.regime_score.toFixed(2) : "—"}
                color={regimeColor(preview.regime_score)}
              />
              <Tile label="Deploy cap" value={fmtPctRounded(preview.deploy_cap)} />
              <Tile
                label="Fear & Greed"
                value={preview.fear_greed != null ? String(preview.fear_greed) : "—"}
                color={fgColor(preview.fear_greed)}
              />
            </div>
            {preview.momentum_ranking.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-[10px] uppercase tracking-wider text-muted">momentum</span>
                {preview.momentum_ranking.map((t, i) => (
                  <span
                    key={t}
                    className="rounded-sm border border-edge bg-panel2 px-1.5 py-0.5 font-mono text-[11px]"
                  >
                    {i + 1}. {cmcLabel(t)}
                  </span>
                ))}
              </div>
            )}
            {preview.rationale && (
              <div className="text-[11px] leading-snug text-sub">{cmcLabel(preview.rationale)}</div>
            )}
          </div>
        ) : (
          <div className="border-t border-edge pt-2 text-[11px] text-muted">
            Deliverable preview appears after the first allocator tick.
          </div>
        )}

        {/* ON-CHAIN JOB LEDGER — fills in for real once a faucet-funded agentic-commerce job settles. */}
        <div className="space-y-2 border-t border-edge pt-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted">on-chain jobs</span>
            <StatusPill tone={idle ? "neutral" : "up"}>
              {idle ? "awaiting first job" : `${served} served`}
            </StatusPill>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Tile label="Jobs Served" value={String(served)} color={served > 0 ? "#16c784" : undefined} />
            <Tile label="Escrow Rev" value={fmtU(commerce.revenue_u)} color={commerce.revenue_u > 0 ? "#16c784" : undefined} />
            <Tile label="Network" value={networkLabel(commerce.network)} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
            <span className="rounded-sm border border-edge bg-panel2 px-1.5 py-0.5 font-mono">
              created {commerce.jobs_created}
            </span>
            <span className="rounded-sm border border-edge bg-panel2 px-1.5 py-0.5 font-mono">
              funded {commerce.jobs_funded}
            </span>
            <span className="rounded-sm border border-edge bg-panel2 px-1.5 py-0.5 font-mono">
              settled {commerce.jobs_settled}
            </span>
          </div>

          {/* x402 SERVER — the agent GETS PAID over x402 (USDC settled on Avalanche). The net-new
              headline: peers pay to read the CMC Regime Report; each settlement is a real on-chain tx. */}
          {commerce.x402_server?.enabled && (
            <div className="space-y-2 rounded-sm border border-edge bg-panel2 p-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-muted">x402 server · agent gets paid</span>
                <StatusPill tone={commerce.x402_server.served_jobs > 0 ? "up" : "neutral"}>
                  {commerce.x402_server.served_jobs > 0 ? `${commerce.x402_server.served_jobs} paid` : "awaiting payment"}
                </StatusPill>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Tile label="x402 Jobs" value={String(commerce.x402_server.served_jobs)} color={commerce.x402_server.served_jobs > 0 ? "#16c784" : undefined} />
                <Tile label="USDC Rev" value={`$${commerce.x402_server.revenue_usdc.toFixed(2)}`} color={commerce.x402_server.revenue_usdc > 0 ? "#16c784" : undefined} />
                <Tile label="Price" value={`$${commerce.x402_server.price_usdc.toFixed(2)}`} />
              </div>
              {commerce.x402_server.last_settlement_tx && (
                <a
                  href={`${explorerBase}/tx/${commerce.x402_server.last_settlement_tx}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-block font-mono text-[11px] text-cyan hover:underline"
                >
                  last settlement {shortHash(commerce.x402_server.last_settlement_tx)} ↗
                </a>
              )}
            </div>
          )}

          {(commerce.last_deliverable_hash || commerce.last_tx) && (
            <div className="space-y-1 font-mono text-[11px]">
              {commerce.last_deliverable_hash && (
                <div className="flex justify-between gap-2">
                  <span className="text-muted">last deliverable</span>
                  {commerce.last_deliverable_url ? (
                    // The deliverable is pinned on IPFS — link straight to the real product the agent sold.
                    <a
                      href={ipfsUrl(commerce.last_deliverable_url)}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                      style={{ color: COMMERCE_VIOLET }}
                    >
                      {shortHash(commerce.last_deliverable_hash)} ↗
                    </a>
                  ) : (
                    <span style={{ color: COMMERCE_VIOLET }}>{shortHash(commerce.last_deliverable_hash)}</span>
                  )}
                </div>
              )}
              {commerce.last_tx && (
                <div className="flex justify-between gap-2">
                  <span className="text-muted">submit tx</span>
                  <a
                    href={`${explorerBase}/tx/${commerce.last_tx}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-cyan hover:underline"
                  >
                    {shortHash(commerce.last_tx)} ↗
                  </a>
                </div>
              )}
            </div>
          )}

          {/* Settlement is OPTIMISTIC — a served job sits "deferred" until the kernel's ~7-day dispute
              window elapses, then auto-finalizes. Without this, served>0 / settled=0 reads as a failure. */}
          {served > 0 && commerce.jobs_settled === 0 && (
            <div className="text-[10px] leading-snug text-muted">
              optimistic settlement — finalizes automatically after the ~7-day dispute window; nothing to do.
            </div>
          )}
        </div>

        {/* CREATE A JOB — buy side. Runs the genuine agentic-commerce loop (create→fund→serve→settle) on a
            LOCAL operator run so the ledger above fills with a REAL served job. Disabled on the
            read-only cloud deploy (no signing key) — never a fake job. */}
        <div className="space-y-2 border-t border-edge pt-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted">create a job</span>
            {!canCreate && <span className="text-[10px] text-muted">operator-only · no cloud key</span>}
          </div>
          <textarea
            value={jobQuery}
            onChange={(e) => setJobQuery(e.target.value)}
            rows={2}
            disabled={!canCreate || jobBusy}
            placeholder="Ask the agent for a CMC regime report…"
            className="w-full rounded-sm border border-edge bg-panel2 px-2 py-1.5 text-[11px] text-sub outline-none disabled:opacity-50"
          />
          <label className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted">
            pay
            <input
              type="number"
              min="0"
              step="0.01"
              value={jobPayU}
              onChange={(e) => setJobPayU(e.target.value)}
              disabled={!canCreate || jobBusy}
              className="w-20 rounded-sm border border-edge bg-panel2 px-2 py-1 text-right font-mono text-[11px] text-sub outline-none disabled:opacity-50"
            />
            <span className="font-mono normal-case">U</span>
          </label>
          <button
            onClick={onCreateJob}
            disabled={!canCreate || jobBusy || !jobQuery.trim()}
            title={
              canCreate
                ? "Run the real agentic-commerce loop: create → fund → serve → settle"
                : "Operator-only — the cloud dashboard has no signing key"
            }
            className="w-full rounded-sm border px-2 py-1.5 text-xs font-semibold transition-opacity disabled:opacity-40"
            style={{ color: COMMERCE_VIOLET, borderColor: COMMERCE_VIOLET }}
          >
            {jobBusy ? "creating job on-chain…" : "Create + serve a real job"}
          </button>
          {jobResult && (
            <div className="rounded-sm border border-edge bg-panel2 px-2 py-1.5 text-[11px]">
              {jobResult.ok ? (
                <div className="space-y-1">
                  <div style={{ color: "#16c784" }}>
                    ✓ served job #{jobResult.job_id}
                    {jobResult.status && jobResult.status !== "settle-deferred" ? ` (${jobResult.status})` : ""}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono">
                    {jobResult.tx && (
                      <a
                        href={`${explorerBase}/tx/${jobResult.tx}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan hover:underline"
                      >
                        submit tx {shortHash(jobResult.tx)} ↗
                      </a>
                    )}
                    {jobResult.deliverable_url && (
                      // The deliverable the agent just sold, pinned on IPFS — clickable proof.
                      <a
                        href={ipfsUrl(jobResult.deliverable_url)}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline"
                        style={{ color: COMMERCE_VIOLET }}
                      >
                        deliverable ↗
                      </a>
                    )}
                  </div>
                  {jobResult.status === "settle-deferred" && (
                    <div className="text-[10px] leading-snug text-muted">
                      optimistic settlement — finalizes automatically after the ~7-day dispute window; nothing to do.
                    </div>
                  )}
                </div>
              ) : jobResult.need != null ? (
                <div style={{ color: "#f0b90b" }}>
                  fund buyer {jobResult.buyer ? shortAddr(jobResult.buyer) : ""} with ≥ {jobResult.need}{" "}
                  {jobResult.token ?? "U"}
                  {jobResult.network ? ` on ${networkLabel(jobResult.network)}` : ""} (have {jobResult.have ?? 0}), then retry
                </div>
              ) : (
                <div className="text-muted">{jobResult.message || "job failed"}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
