#!/usr/bin/env python3
"""
Dump the current dashboard snapshot to web/public/snapshot.json.

Vite copies public/* into the build, so this becomes the SPA's OFFLINE FALLBACK:
when the live API isn't reachable (e.g. a static Vercel deploy, or the Render API
cold-starting), the dashboard still renders real — if frozen — data instead of
blanking. Run by scripts/build_web.sh before each build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Pin the LOCAL ictbot (this venv otherwise resolves ictbot to a sibling repo).
sys.path.insert(0, str(ROOT / "src"))

from ictbot.api import reads  # noqa: E402


def main() -> int:
    out = ROOT / "web" / "public" / "snapshot.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reads.snapshot(), indent=2, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
