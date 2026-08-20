#!/usr/bin/env python3
"""CAL-P078 — read the PUBLISHED curve's population DB-direct, and reconcile.

Gate 0's instrument. Runs the canonical population fold against the database,
reads ``/api/calibration``, and reports whether they agree **within the bank's
own disclosed drift** — the restated Gate 0 invariant, not equality.

    python3 scripts/measure_published_twin.py --out artifacts/cal-p078/twin.json
    python3 scripts/measure_published_twin.py --plan-only     # print the SQL
    python3 scripts/measure_published_twin.py --payload p.json  # offline replay

Read-only by construction: one SELECT, no write, no DDL, no task. It is bounded
by an explicit ``statement_timeout`` because CAL-P077's first 49-cell sweep died
in an UNCOVERED branch after measuring thirty cells, and losing the cheap cells
moved a pooled headline 3.76 -> 5.02 pp purely by absence. A cell that cannot be
read is NAMED here, never dropped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.calibration_published_twin import (  # noqa: E402
    fold_rows_to_cells,
    published_population_fold_sql,
    reconcile,
)

DEFAULT_TIMEOUT_MS = 240_000


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", help="write the artifact here")
    p.add_argument("--plan-only", action="store_true", help="print the SQL and exit")
    p.add_argument("--payload", help="a saved /api/calibration body, for offline replay")
    p.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    p.add_argument(
        "--api",
        default=os.environ.get("BAINLUCK_API", "https://api.bainluck.com"),
        help="base URL for the published payload",
    )
    return p.parse_args(argv)


async def _fold(*, timeout_ms: int) -> tuple[list, float, str | None]:
    """Run the fold. Returns ``(rows, duration_s, error)`` — never raises.

    An error is RETURNED rather than thrown so the artifact records that the
    read was attempted and failed, which is a different fact from a read that
    was never made (ruling 075 clause 2).
    """
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    sql = published_population_fold_sql()
    started = time.monotonic()
    try:
        async with get_task_session() as session:
            await session.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
            result = await session.execute(text(sql))
            rows = result.all()
        return rows, time.monotonic() - started, None
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return [], time.monotonic() - started, f"{type(exc).__name__}: {exc}"


def _load_payload(args) -> tuple[dict, str | None]:
    if args.payload:
        try:
            return json.loads(Path(args.payload).read_text()), None
        except Exception as exc:  # noqa: BLE001
            return {}, f"payload_unreadable: {exc}"
    try:
        import urllib.request

        with urllib.request.urlopen(f"{args.api}/api/calibration", timeout=60) as resp:
            return json.loads(resp.read().decode()), None
    except Exception as exc:  # noqa: BLE001
        return {}, f"api_unreachable: {type(exc).__name__}: {exc}"


async def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.plan_only:
        print(published_population_fold_sql())
        return 0

    rows, duration_s, fold_error = await _fold(timeout_ms=args.timeout_ms)
    payload, payload_error = _load_payload(args)

    cells = fold_rows_to_cells(rows)
    verdict = reconcile(
        db_cells=cells,
        published_buckets=payload.get("buckets") or [],
        staged=payload.get("staged"),
    )

    artifact = {
        "queue": "CAL-P078",
        "issue": 2007,
        "gate": "Gate 0 — bounded agreement, published curve vs DB-direct",
        "fold_duration_s": round(duration_s, 2),
        "fold_error": fold_error,
        "payload_error": payload_error,
        "published_generated_at": payload.get("generated_at"),
        "published_availability": payload.get("availability"),
        "staged": payload.get("staged"),
        "db_cells": len(cells),
        "db_rows": sum(
            b["n"] for buckets in cells.values() for b in buckets.values()
        ),
        **verdict,
    }
    # A read that failed must never present as a clean 'agrees' over zero rows.
    if fold_error or payload_error:
        artifact["verdict"] = "unmeasurable"
        artifact.setdefault("unmeasurable_reason", fold_error or payload_error)

    text_out = json.dumps(artifact, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text_out)
    print(text_out)
    # Exit 1 ONLY on a real disagreement. Unmeasurable exits 2 — a distinct code,
    # because "the gate found a problem" and "the gate could not run" are
    # different stories and gotcha #54's amendment says to read the value.
    if artifact["verdict"] == "disagrees":
        return 1
    if artifact["verdict"] == "unmeasurable":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
