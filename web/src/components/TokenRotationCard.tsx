import { useEffect, useState } from "react";

import type { Snapshot, TokenRotation } from "../api/types";
import { clockHM, tokenColor } from "../lib/format";
import { sourceLabel } from "../lib/rotation";
import Card from "./ui/Card";
import StatusPill from "./ui/StatusPill";
import InfoTip from "./ui/Tooltip";

/**
 * Token Rotation — which of the 8 contest tokens have actually been traded, and how.
 *
 * The momentum allocator only ever holds `top_k` (2) tokens; the contest-floor rotation reaches the
 * rest of the universe with tiny ~0-NAV round-trips so every token is touched over the week. This card
 * makes that visible WITHOUT overclaiming: a "floor" touch is explicitly labelled as the ≥1-trade
 * contest floor, never a momentum conviction. Data: `snapshot.token_rotation` (see token_rotation_card).
 *
 * Source resolution (honest, auto-upgrading):
 *   - `hasLiveField` → the live API served `token_rotation`: render it as LIVE (real campaign coverage).
 *   - else → the live backend predates the field; fall back to the committed SIM snapshot
 *     (`/snapshot.json`, the demonstrated full rotation) badged `SIM` so the mechanism is visible now.
 *     The instant the live backend exposes the field, the card switches to live data on its own.
 */
export default function TokenRotationCard({
  rotation,
  hasLiveField = false,
  live = true,
}: {
  rotation: TokenRotation | null;
  hasLiveField?: boolean;
  live?: boolean;
}) {
  // When live data lacks token_rotation, pull the committed sim demonstration (8/8) so the deployed
  // dashboard shows the full rotation now — never fabricated, just sourced from the sim snapshot.
  const [simPreview, setSimPreview] = useState<TokenRotation | null>(null);
  const needPreview = !hasLiveField;
  useEffect(() => {
    if (!needPreview) {
      setSimPreview(null);
      return;
    }
    let cancelled = false;
    fetch("/snapshot.json", { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Snapshot>) : null))
      .then((s) => {
        if (!cancelled && s?.token_rotation?.tokens?.length) setSimPreview(s.token_rotation);
      })
      .catch(() => {
        /* static snapshot unavailable — fall back to whatever `rotation` we derived */
      });
    return () => {
      cancelled = true;
    };
  }, [needPreview]);

  const usingSim = needPreview && simPreview != null;
  const rot = usingSim ? simPreview : rotation;

  const badge = usingSim ? (
    <StatusPill tone="violet" srText="sim demonstration of the rotation">
      SIM
    </StatusPill>
  ) : live ? (
    <StatusPill tone="up" dot pulse srText="live rotation">
      LIVE
    </StatusPill>
  ) : (
    <StatusPill tone="neutral" srText="static snapshot">
      SNAPSHOT
    </StatusPill>
  );

  const right = (
    <span className="flex items-center gap-1.5">
      <InfoTip
        title="Token rotation"
        text="Which of the 8 tokens have been traded. The momentum arm holds only the top-2; the contest-floor rotation touches the rest with ~0-NAV round-trips. Coverage, not an edge claim."
      />
      {badge}
    </span>
  );

  if (!rot || !rot.tokens.length) {
    return (
      <Card label="Token Rotation" accent="#f0b90b" className="flex h-full flex-col" right={right}>
        <div className="flex flex-1 items-center justify-center py-8 text-center text-xs text-muted">
          no rotation data yet
        </div>
      </Card>
    );
  }

  const { tokens, touched_count, total } = rot;
  const allTouched = touched_count >= total;

  return (
    <Card label="Token Rotation" accent="#f0b90b" className="flex h-full flex-col" right={right}>
      {/* Headline: N / total rotated */}
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wider text-muted">universe coverage</span>
        <span className="font-display text-lg font-bold tabular-nums">
          <span className={allTouched ? "text-neon" : "text-ink"}>{touched_count}</span>
          <span className="text-muted">/{total}</span>
          <span className="ml-1.5 text-xs font-normal text-muted">rotated</span>
        </span>
      </div>

      {usingSim && (
        <p className="mb-2 text-[10px] leading-snug text-violet">
          SIM demonstration of the contest-floor rotation. The live campaign holds the momentum top-2
          today and fills the rest as the ≥1-trade floor fires over the contest week.
        </p>
      )}

      {/* 8-token grid */}
      <ul className="grid flex-1 grid-cols-2 gap-1.5 text-xs sm:grid-cols-4">
        {tokens.map((t) => {
          const touched = t.touched;
          const isHeld = t.source === "held" || t.source === "both";
          return (
            <li
              key={t.token}
              className={`flex flex-col gap-0.5 rounded-sm border px-2 py-1.5 transition ${
                touched ? "border-line bg-panel2" : "border-line/40 opacity-60"
              }`}
              title={
                t.last_ts
                  ? `${t.token} · ${sourceLabel(t.source)} · last ${clockHM(t.last_ts)} · ${t.count}×`
                  : `${t.token} · not yet touched`
              }
            >
              <span className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ background: touched ? tokenColor(t.token) : "transparent", border: touched ? "none" : `1px solid ${tokenColor(t.token)}` }}
                  />
                  <span className={touched ? "text-ink" : "text-muted"}>{t.token}</span>
                </span>
                <span
                  className={touched ? "text-neon" : "text-muted"}
                  aria-label={touched ? "rotated" : "pending"}
                >
                  {touched ? "✓" : "○"}
                </span>
              </span>
              <span className="flex items-center justify-between font-mono text-[10px] text-sub">
                <span className={isHeld ? "text-brand" : "text-muted"}>{sourceLabel(t.source)}</span>
                {t.last_ts && <span className="text-muted">{clockHM(t.last_ts)}</span>}
              </span>
            </li>
          );
        })}
      </ul>

      {/* Honest footnote — the floor touches are NOT an edge claim */}
      <p className="mt-3 text-[10px] leading-snug text-muted">
        <span className="text-brand">momentum</span> = a real top-{2} holding ·{" "}
        <span className="text-sub">floor</span> = a ~0-NAV contest ≥1-trade nudge that rotates the rest of
        the universe. Coverage, not conviction — never an edge claim.
      </p>
    </Card>
  );
}
