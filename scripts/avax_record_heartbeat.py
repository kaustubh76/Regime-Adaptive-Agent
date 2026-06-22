#!/usr/bin/env python3
"""CLI: stamp a heartbeat result onto an allocator journal's latest tick.

Thin wrapper over `ictbot.agent.heartbeat_journal.record_heartbeat`. Used to reflect a verified
on-chain ERC-8004 heartbeat on the dashboard (the demo wires this automatically; this CLI is for
correcting committed seeds / the live journal to a proven tx without re-spending gas).

    python scripts/avax_record_heartbeat.py data/journal/allocator_journal.jsonl \
        --ok --tx 0x00808e… --ts 2026-06-22T09:38:18Z
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ictbot.agent.heartbeat_journal import record_heartbeat  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a heartbeat result into a journal's latest tick")
    ap.add_argument("journal", help="path to the allocator journal (.jsonl)")
    ap.add_argument("--ok", action="store_true", help="mark the heartbeat as successful")
    ap.add_argument("--fail", action="store_true", help="mark the heartbeat as failed")
    ap.add_argument("--tx", help="on-chain tx hash (0x…) of the set_metadata heartbeat")
    ap.add_argument("--ts", help="UTC timestamp of the heartbeat (e.g. 2026-06-22T09:38:18Z)")
    ap.add_argument("--error", help="failure reason (only with --fail)")
    a = ap.parse_args()

    ok = a.ok and not a.fail
    wrote = record_heartbeat(a.journal, ok=ok, tx=a.tx, ts=a.ts, error=a.error)
    print(f"{'recorded heartbeat in' if wrote else 'no REBALANCE row found in'} {a.journal}")
    return 0 if wrote else 1


if __name__ == "__main__":
    raise SystemExit(main())
