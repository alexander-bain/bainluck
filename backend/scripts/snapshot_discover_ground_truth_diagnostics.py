"""Persist Discover ground-truth diagnostics from the admin debug feed.

This script intentionally reads the existing `/api/feed?debug=true` response
instead of making the hot feed route write diagnostics during normal requests.
It can be run manually or scheduled after email/curator exports refresh.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.discover_ground_truth_diagnostics import (  # noqa: E402
    DEFAULT_FEED_URL,
    build_diagnostic_rows_from_debug_payload,
    fetch_debug_payload,
    persist_diagnostic_rows,
)


async def _run(args: argparse.Namespace) -> int:
    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text())
    else:
        admin_secret = args.admin_secret or os.getenv("ADMIN_TOKEN")
        if not admin_secret:
            raise SystemExit("ADMIN_TOKEN or --admin-secret is required")
        payload = fetch_debug_payload(
            feed_url=args.feed_url,
            admin_secret=admin_secret,
            limit=args.limit,
        )

    run_id = args.run_id or str(uuid.uuid4())
    rows = build_diagnostic_rows_from_debug_payload(payload, run_id=run_id)
    if args.print_json:
        print(json.dumps({"run_id": run_id, "rows": rows}, default=str, indent=2))
    if args.dry_run:
        print(f"dry_run rows={len(rows)} run_id={run_id}")
        return 0

    inserted = await persist_diagnostic_rows(rows)
    print(f"inserted={inserted} run_id={run_id}")
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--feed-url", default=os.getenv("FEED_AUDIT_URL", DEFAULT_FEED_URL)
    )
    parser.add_argument("--admin-secret", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args(argv)
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
