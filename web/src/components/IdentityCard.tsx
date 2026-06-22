import { verifyPillars } from "../api/client";
import type { Identity, NodeRealPillar } from "../api/types";
import { shortAddr, networkLabel, getExplorerBase } from "../lib/format";
import Card from "./ui/Card";
import CheckButton from "./ui/CheckButton";
import CopyButton from "./ui/CopyButton";
import StatusPill from "./ui/StatusPill";
import InfoTip from "./ui/Tooltip";

async function verifyCheck() {
  const p = await verifyPillars();
  const np = p.nodereal;
  return {
    ok: !!np.reachable && !!np.chain_ok,
    detail: np.reachable
      ? `chain ${np.chain_id ?? "—"} · agent #${np.agent_id || "unminted"} · nonce ${np.nonce ?? "—"}`
      : np.note ?? "Avalanche RPC unreachable",
  };
}

function HeartbeatLine({ np }: { np: NodeRealPillar }) {
  // Is pillar-3 alive? Show the heartbeat status + the direct-gas funding (0 AVAX = the broken state).
  const ok = np.last_heartbeat_ok;
  const bnb = np.identity_wallet_bnb;
  const funded = bnb != null && bnb >= 0.001;
  const tone = ok ? "up" : ok === false ? "down" : funded ? "armed" : "violet";
  const label =
    ok ? "heartbeat live" : ok === false ? "heartbeat failing" : np.heartbeat_enabled ? "heartbeat armed" : "heartbeat off";
  const gas = np.use_paymaster ? "gasless" : `direct-gas ${bnb != null ? bnb.toFixed(4) : "—"} AVAX`;
  return (
    <div className="flex items-center justify-between gap-2 border-t border-edge pt-2 text-[11px]">
      <span className="flex items-center gap-1.5">
        <StatusPill tone={tone} dot>{label}</StatusPill>
        <span className="text-muted">{gas}</span>
      </span>
      {np.last_heartbeat_tx ? (
        <a
          href={`${getExplorerBase(np.network)}/tx/${np.last_heartbeat_tx}`}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-cyan hover:underline"
        >
          last ↗
        </a>
      ) : ok === false && np.last_heartbeat_error ? (
        // Surface WHY the last beat failed (truncated; full reason on hover) instead of just "failing".
        <span className="max-w-[55%] truncate text-[10px]" style={{ color: "#f6685e" }} title={np.last_heartbeat_error}>
          {np.last_heartbeat_error}
        </span>
      ) : (
        !funded && !np.use_paymaster && <span className="text-[10px] text-muted">fund wallet to enable</span>
      )}
    </div>
  );
}

export default function IdentityCard({
  identity,
  agentId,
  nodereal,
}: {
  identity: Identity | null | undefined;
  agentId?: number | null;
  nodereal?: NodeRealPillar | null;
}) {
  const minted = (agentId ?? 0) > 0;
  if (!identity) {
    return (
      <Card label="On-chain Identity" accent="#8b9dff" className="h-full">
        <div className="flex h-24 items-center justify-center text-xs text-muted">identity unavailable</div>
      </Card>
    );
  }
  const ep = identity.endpoints[0];
  const explorer = `${getExplorerBase(identity.network)}/address/${identity.trading_wallet}`;
  return (
    <Card
      label={
        <span className="inline-flex items-center gap-1">
          On-chain Identity <InfoTip term="erc8004" side="bottom" />
        </span>
      }
      accent="#8b9dff"
      className="h-full"
      right={
        <StatusPill tone={minted ? "up" : "violet"} srText={minted ? "minted on-chain" : "configured, not yet minted"}>
          {minted ? `ERC-8004 #${agentId}` : "ERC-8004"}
        </StatusPill>
      }
    >
      <div className="space-y-3">
        <div>
          <div className="font-display text-sm font-bold text-ink">{identity.name}</div>
          <div className="text-[11px] text-muted">{networkLabel(identity.network)}</div>
          {/* Honest mint status — the profile is a key-free DECLARATION until a token
              is actually minted (audit H3 / ties to backend B1 persisting AGENT_ID). */}
          <div className="text-[10.5px]" style={{ color: minted ? "#16c784" : "#8a8f9c" }}>
            {minted ? `minted · on-chain identity #${agentId}` : "configured · not yet minted"}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <a href={explorer} target="_blank" rel="noreferrer" className="font-mono text-xs text-cyan hover:underline">
            {shortAddr(identity.trading_wallet)} ↗
          </a>
          <CopyButton text={identity.trading_wallet} />
        </div>
        {ep && (
          <div className="flex flex-wrap gap-1">
            {ep.capabilities.map((c) => (
              <span key={c} className="rounded-sm bg-panel2 px-1.5 py-0.5 text-[10px] text-sub">
                {c}
              </span>
            ))}
          </div>
        )}
        {nodereal && <HeartbeatLine np={nodereal} />}
        <div className="flex justify-end">
          <CheckButton label="verify on-chain" run={verifyCheck} />
        </div>
      </div>
    </Card>
  );
}
