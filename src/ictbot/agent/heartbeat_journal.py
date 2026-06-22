"""Record an ERC-8004 heartbeat result into the allocator journal's latest tick.

The dashboard's IdentityCard reads the last heartbeat from the latest REBALANCE row's
`heartbeat` field (`pillars_card` in `ictbot.api.reads`). `identity.write_heartbeat()` settles
the heartbeat ON-CHAIN but does not itself touch the allocator journal, so without this seam the
demo proves the heartbeat on Snowtrace yet the dashboard keeps showing the previous (stale/failed)
result. This module is the reusable bridge: after a real on-chain heartbeat, stamp the verified
`{ok, tx, ts}` onto the latest tick so the dashboard reflects the proven fact.

Pure stdlib — safe to import without web3 / the x402 extra.
"""

from __future__ import annotations

import json
from pathlib import Path


def record_heartbeat(
    journal: str | Path,
    ok: bool,
    tx: str | None = None,
    ts: str | None = None,
    error: str | None = None,
) -> bool:
    """Stamp the latest REBALANCE row's `heartbeat` with the given result.

    Returns True if a row was found and the journal rewritten, else False. Idempotent: re-running
    with the same values overwrites the heartbeat in place (no row is appended). Unparseable lines
    are preserved verbatim so a malformed row never costs data.
    """
    p = Path(journal)
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return False

    rows: list[dict | None] = []
    last_rebalance = -1
    for i, line in enumerate(lines):
        try:
            row = json.loads(line)
        except ValueError:
            rows.append(None)  # keep the raw line; never drop data
            continue
        rows.append(row)
        if row.get("event") == "REBALANCE":
            last_rebalance = i
    if last_rebalance < 0:
        return False

    hb: dict = {"ok": bool(ok)}
    if tx:
        hb["tx"] = tx
    if ts:
        hb["ts"] = ts
    if error:
        hb["error"] = error
    rows[last_rebalance]["heartbeat"] = hb  # type: ignore[index]

    out = [lines[i] if r is None else json.dumps(r, default=str) for i, r in enumerate(rows)]
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True
