#!/usr/bin/env python3
"""CAL-P078 — read the PUBLISHED curve's population DB-direct, and reconcile.

Gate 0's instrument. Runs the canonical population fold against the database,
reads ``/api/calibration``, and reports whether they agree **within the bank's
own disclosed drift** — the restated Gate 0 invariant, not equality.

    python3 scripts/measure_published_twin.py --out artifacts/cal-p078/twin.json
    python3 scripts/measure_published_twin.py --plan-only     # print the SQL
    python3 scripts/measure_published_twin.py --payload p.json  # offline replay

CAL-P086B — ``--bank``, the one-off-dyno shape (#2076)
------------------------------------------------------
    heroku run:detached -a bainluck -- \\
      python3 scripts/measure_published_twin.py --bank --timeout-ms 5400000

#2076's option 1 (raise the budget) is refuted at 240 s, 900 s and 1,350 s, and
options 2/3 (narrow/chunk) are refuted by plan — a tail-filtered chunk costs
1.0000x the unfiltered fold and the root-filtered form leaves the binding chunk
at 0.7616x over a 3-way partition. What is left is CAL-P079's finding: the
reader belongs on a host whose budget is its own. **1,350,000 ms is the CELERY
task's ceiling** (``soft_time_limit=1800``), not the query's; a one-off dyno has
no such limit.

``--bank`` therefore runs the SAME function the beat runs
(``run_published_twin``) at ``ONE_OFF_MAX_TIMEOUT_MS``, rather than
re-implementing the fold here — a gate that fires on a dyno must be the gate the
beat would have fired. And it banks the durable snapshot, which is the half that
was actually missing: this script's ``--out`` file and its stdout BOTH die with a
detached dyno (gotcha #48 — never trust a detached run's stdout; prove it with a
durable row). After it finishes, read it at
``GET /api/admin/calibration-twin/last``.

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
    tolerance_pp,
)

DEFAULT_TIMEOUT_MS = 240_000


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", help="write the artifact here")
    p.add_argument("--plan-only", action="store_true", help="print the SQL and exit")
    p.add_argument(
        "--bound-only",
        action="store_true",
        help="report the BOUND from the payload alone; run no fold and claim no verdict",
    )
    p.add_argument("--payload", help="a saved /api/calibration body, for offline replay")
    p.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    p.add_argument(
        "--bank",
        action="store_true",
        help="run through the worker and BANK the durable snapshot, at the "
        "one-off-dyno ceiling. Use this on `heroku run:detached`, where a file "
        "and a stdout both die with the dyno.",
    )
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


def _bound_only(args) -> int:
    """Report Gate 0's BOUND without touching the database.

    CAL-P079 separated two things this script had always computed together, and
    they have different reachability:

    * the **bound** comes from :func:`tolerance_pp`, which reads only the
      payload's ``staged`` block — ``units_banked``, ``units_drifted``,
      ``units_drift_unknown``. No database, no fold, no credentials.
    * the **verdict** needs ``db_cells``, and therefore the fold.

    The fold is unreachable from an agent sandbox (TCP 5432 egress is blocked)
    and — measured in CAL-P079 — is also unreachable through the admin db-query
    rail, whose row path hardcodes a 10 s ``statement_timeout`` against an
    instrument whose own default budget is 240 s. That is a real bound on where
    the verdict can be produced, and it was making the BOUND unreportable too,
    purely by being in the same function.

    So this mode exists to stop a reachable measurement from being blocked by an
    unreachable one. It never claims ``agrees``: with no fold there is nothing to
    agree with, and a mode that could return the gate's pass value while checking
    nothing is the failure this whole module was written against.
    """
    payload, payload_error = _load_payload(args)
    staged = payload.get("staged")
    bound = tolerance_pp(staged)

    artifact = {
        "queue": "CAL-P079",
        "issue": 2007,
        "gate": "Gate 0 — BOUND ONLY (no fold, no verdict)",
        "mode": "bound_only",
        "payload_error": payload_error,
        "published_generated_at": payload.get("generated_at"),
        "published_availability": payload.get("availability"),
        "staged": staged,
        "tolerance_pp": bound,
        # Named, not implied. A reader must not be able to mistake this for the
        # gate having run.
        "verdict": "bound_only",
        "verdict_note": (
            "The fold was deliberately not run, so no agreement verdict exists. "
            "This reports only the tolerance the payload's own disclosure earns."
        ),
    }
    if bound is None:
        artifact["unmeasurable_reason"] = (
            payload_error or "staged block absent or unmeasured — no bound is earned"
        )

    text_out = json.dumps(artifact, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text_out)
    print(text_out)
    # 0 = a bound was earned and reported. 2 = it could not be, matching the
    # full mode's "the gate could not run" code (gotcha #54's amendment: the
    # VALUE of a non-zero exit is the story).
    return 0 if bound is not None else 2


# Bound at module scope so a test can substitute it, and so the import cost of
# the worker (which pulls in a large slice of the app) is paid only by the
# ``--bank`` path.
async def _run_published_twin(*, timeout_ms: int, ceiling=None) -> dict:
    from app.tasks.calibration_published_twin_worker import run_published_twin

    return await run_published_twin(timeout_ms=timeout_ms, ceiling=ceiling)


async def _bank(args) -> int:
    """Run the worker's own path and require the durable write to have landed.

    Exit codes extend the script's existing vocabulary rather than replacing it,
    because a caller reading them should not have to know which mode ran
    (gotcha #54's amendment: the VALUE of a non-zero exit is the story).

    * ``0`` agrees, banked
    * ``1`` disagrees, banked -- the gate working
    * ``2`` unmeasurable -- the gate could not run
    * ``3`` **the artifact was not banked.** New, and specific to this mode: on
      a detached dyno the durable row IS the result, so a run whose verdict is
      perfect and whose durable write failed has produced nothing any reader
      will ever see. Reporting that as ``0`` would be gotcha #53 at the exact
      point this mode exists to defend.
    """
    from app.tasks.calibration_published_twin_worker import ONE_OFF_MAX_TIMEOUT_MS

    artifact = await _run_published_twin(
        timeout_ms=args.timeout_ms, ceiling=ONE_OFF_MAX_TIMEOUT_MS
    )
    text_out = json.dumps(artifact, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text_out)
    print(text_out)

    if artifact.get("durable") != "published":
        return 3
    verdict = artifact.get("verdict")
    if verdict == "disagrees":
        return 1
    if verdict != "agrees":
        return 2
    return 0


async def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.plan_only:
        print(published_population_fold_sql())
        return 0

    if args.bound_only:
        return _bound_only(args)

    if args.bank:
        return await _bank(args)

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
