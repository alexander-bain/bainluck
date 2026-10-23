#!/usr/bin/env python3
"""#683 archive recovery — READ-ONLY dry run. Writes nothing, anywhere.

PILLAR: TRUTH. SHIP: settled Kalshi questions that have no price history get
back their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

It selects zero-snapshot resolved Kalshi outcomes, reads Kalshi's historical tier
for each one by its EXACT stored ticker, and prints the exact-ID plan
(``app.services.kalshi_archive_recovery``). Each planned point says whether it
could be a calibration FORECAST (the whole candle ends at or before the
authoritative start), READER-ONLY history, or refused. The digest is repeatable.

    python3 scripts/kalshi_archive_recovery_dry_run.py --limit 20 --max-requests 45 \
        --output /tmp/683-plan.json
    python3 scripts/kalshi_archive_recovery_dry_run.py --outcome-ids 101,102 --output ...
    python3 scripts/kalshi_archive_recovery_dry_run.py --after-id <next_after_id> ...

``--outcome-ids`` reads the stored identity WITHOUT the keyset's local backstop
and status filters; the venue's settlement and the provider cutoff choose the
tier. A run that stops mid-outcome reports ``held_outcome`` (listing cursor, or
the unread hourly/minute windows) and does not advance ``next_after_id`` past it.
Its sealed ``continuation`` is the next run's input:

    python3 scripts/kalshi_archive_recovery_dry_run.py --after-id <next_after_id> \
        --continue-from /tmp/683-plan.json --output /tmp/683-plan-2.json

The held outcome then resumes under the new run's own request budget: windows
already read are re-verified from their stored response text and never asked
again. An outcome planned ``incomplete`` names its ``owed_windows``.

THE ATTENDED BOUNDS (``app.services.kalshi_archive_bounds``). ``--deadline`` is
INCLUSIVE: the cooldown read, the database read, every GET, cancelling an
in-flight GET, closing the client, writing the output and delivering the
console summary all happen inside it.
Every response is streamed under ``--max-response-bytes`` and the run under
``--max-total-bytes``; console output under ``--max-console-bytes`` and the
plan file under ``--max-artifact-bytes`` (written whole or not at all, never
over an existing file). ``--stop-on-429`` sends nothing after any 429, even
``Retry-After: 0``, and refuses to start if the shared cooldown is unreadable.
The first attended sample's profile:

    python3 scripts/kalshi_archive_recovery_dry_run.py --outcome-ids O --limit 1 \
        --max-requests 3 --pace 2 --deadline 120 --stop-on-429 \
        --max-response-bytes 1048576 --max-total-bytes 3145728 \
        --max-artifact-bytes 262144 --max-console-bytes 262144 --output P

Exit codes: 0 only for ``terminal: complete``; 3 when a budget, the wall or an
output cap stopped the run (held, resumable, nothing sold as complete), the
loop's bounded shutdown left work running (``shutdown.clean`` false), or the
console could not take the summary inside the wall (then the plan file, if
written, is the record and the process ends at the wall); 1 for
every other terminal (partial with owed outcomes, rate_limited, cooldown,
cooldown_unknown, failed); 2 for a refused invocation. None of them is
permission to retry.

Needs ``DATABASE_URL`` for the candidate read (a read-only transaction whose
connections carry the archive statement and lock bounds) and makes public
Kalshi GETs. This script never writes. ``--apply`` is refused with exit 2:
the attended writer is ``scripts/kalshi_archive_import.py``, which takes this
script's ``--output`` file and its ``plan_digest``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNPAID_GATES = (
    "this dry run never writes; the attended writer is scripts/kalshi_archive_import.py",
    "independent exact-cohort + raw-payload validation (Measurement)",
    "authenticated access + rate budget for the archive endpoints (Measurement)",
    "the archive-store migration and any production apply are attended (Alex)",
)


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--limit", type=int, default=20, help="outcomes to plan (hard max 200)"
    )
    p.add_argument(
        "--after-id", type=int, default=0, help="keyset resume: plan outcome ids > this"
    )
    p.add_argument(
        "--outcome-ids", default="", help="comma-separated exact outcome ids"
    )
    p.add_argument(
        "--max-requests",
        type=int,
        default=45,
        help="Kalshi GETs this run (hard max 400)",
    )
    p.add_argument(
        "--pace", type=float, default=1.0, help="seconds between GETs (min 0.5)"
    )
    p.add_argument(
        "--deadline",
        type=float,
        default=600.0,
        help="inclusive wall-clock seconds (DB, GETs, cancel, close, output)",
    )
    p.add_argument(
        "--stop-on-429",
        action="store_true",
        help="send nothing after any 429 (even Retry-After: 0); unreadable cooldown refuses",
    )
    p.add_argument(
        "--max-response-bytes", type=int, default=1 << 20, help="per response, streamed"
    )
    p.add_argument(
        "--max-total-bytes", type=int, default=3 << 20, help="all responses this run"
    )
    p.add_argument(
        "--max-artifact-bytes", type=int, default=256 << 10, help="the --output file"
    )
    p.add_argument(
        "--max-console-bytes", type=int, default=256 << 10, help="stdout+stderr together"
    )
    p.add_argument("--output", default="", help="write the full JSON plan here")
    p.add_argument(
        "--continue-from",
        default="",
        help="an earlier --output whose run stopped mid-outcome; resume it",
    )
    p.add_argument(
        "--apply", action="store_true", help="REFUSED: this script never writes"
    )
    return p.parse_args(argv)


#: Exit codes (see the module doc).
EXIT_COMPLETE, EXIT_OTHER, EXIT_REFUSED, EXIT_HELD = 0, 1, 2, 3


def main(argv=None, *, service_factory=None, session_factory=None) -> int:
    args = _parse(argv)
    if args.apply:
        print("REFUSED: this dry run has no write path. Gates:", file=sys.stderr)
        for gate in UNPAID_GATES:
            print(f"  - {gate}", file=sys.stderr)
        return EXIT_REFUSED
    # Installed before the app is imported, so every logging handler built
    # during import writes through the cap too.
    from app.services.kalshi_archive_bounds import ConsoleCap

    try:
        console = ConsoleCap(args.max_console_bytes).install()
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        code = _run(args, console, service_factory, session_factory)
    finally:
        console.restore()
    if console.overflowed and code == EXIT_COMPLETE:
        return EXIT_HELD
    return code


def _run(args, console, service_factory, session_factory) -> int:
    from app.services import kalshi_archive_bounds as bounds

    try:
        wall = bounds.OperationWall(args.deadline)
        budget = bounds.ArchiveByteBudget(
            response_cap=args.max_response_bytes, total_cap=args.max_total_bytes
        )
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    console.bind(wall)
    if args.output and os.path.lexists(args.output):
        print(f"REFUSED: --output exists, never overwritten: {args.output}", file=sys.stderr)
        return EXIT_REFUSED
    ids = [int(x) for x in args.outcome_ids.split(",") if x.strip()] or None
    carry = None
    if args.continue_from:
        try:
            with wall.sync_phase("continuation_load"):
                carry = bounds.read_bounded_json(
                    args.continue_from, args.max_artifact_bytes
                ).get("continuation")
        except (bounds.InputTooLarge, bounds.WallExpired, ValueError) as e:
            print(f"REFUSED: --continue-from unreadable: {e}", file=sys.stderr)
            return EXIT_REFUSED
        if carry is None:
            print("REFUSED: --continue-from holds no continuation", file=sys.stderr)
            return EXIT_REFUSED

    from app.services.kalshi_archive_recovery import plan_archive_recovery

    # Half the wall's reserve unwinds the planner (cancel + close); the other
    # half writes the receipt. Work stops at the wall's work deadline.
    planner_end = wall.deadline - wall.reserve / 2
    progress: dict = {}
    shutdown: dict = {}
    extra = {}
    if service_factory is not None:
        extra["service_factory"] = service_factory
    if session_factory is not None:
        extra["session_factory"] = session_factory
    try:
        report = bounds.run_bounded_loop(
            bounds.run_within_wall(
                lambda: plan_archive_recovery(
                    limit=args.limit,
                    after_id=args.after_id,
                    outcome_ids=ids,
                    max_requests=args.max_requests,
                    pace_seconds=args.pace,
                    deadline_seconds=max(wall.remaining(), 0.0),
                    hard_deadline_seconds=max(planner_end - wall.monotonic(), 0.0),
                    continuation=carry,
                    stop_on_first_429=args.stop_on_429,
                    byte_budget=budget,
                    progress=progress,
                    **extra,
                ),
                wall=wall,
                progress=progress,
                cancel_until=planner_end,
            ),
            close_by=planner_end,
            shutdown=shutdown,
        )
    except bounds.WallExpired as e:
        report = _wall_receipt(progress, e.phase, budget)
    # What the loop's bounded shutdown abandoned is on the receipt; work left
    # running is never a complete run (``_emit`` holds it).
    report["shutdown"] = shutdown
    return _emit(args, wall, report)


def _wall_receipt(progress: dict, phase: str, budget) -> dict:
    """What a run the outer wall cut off may say: held, nothing planned, no digest."""
    seen = dict(progress.get("report") or {})
    return {
        "mode": "dry_run",
        "writes": 0,
        "terminal": "partial",
        "budget_stop": "wall",
        "wall": progress.get("wall"),
        "cancel": progress.get("cancel"),
        "phase": phase,
        "requests_sent": seen.get("requests_sent", 0),
        "response_bytes": budget.as_report(),
        "selection": seen.get("selection"),
        "after_id": seen.get("after_id"),
        # Nothing it half-read is a plan, an absence, or an advanced cursor.
        "next_after_id": seen.get("after_id"),
        "plans": [],
        "plan_digest": None,
        "importable_points": 0,
        "continuation": None,
        "held_outcome": seen.get("held_outcome"),
    }


def _emit(args, wall, report: dict) -> int:
    """Seal the artifact, then deliver the summary, both inside the wall.

    The plan file is sealed by ``wall.artifact_deadline``; serializing and
    delivering the summary has the rest, to the hard deadline
    (``bounds.deliver_receipt``). Nothing gets a fresh allowance: a late
    summary is unavailable, never a wait, and the exit is held at 3.
    """
    from app.services import kalshi_archive_bounds as bounds

    code = EXIT_COMPLETE if report.get("terminal") == "complete" else EXIT_OTHER
    if report.get("budget_stop") or not (report.get("shutdown") or {}).get("clean", True):
        code = EXIT_HELD
    summary = {k: v for k, v in report.items() if k not in ("plans", "continuation")}
    summary["continuation_sealed"] = (
        None if report.get("continuation") is None else report["continuation"]["digest"]
    )
    try:
        with wall.sync_phase("serialize", work=False, end=wall.artifact_deadline):
            if args.output:
                summary["artifact_bytes"] = bounds.write_bounded_artifact(
                    args.output, report, args.max_artifact_bytes
                )
                summary["artifact"] = args.output
    except bounds.ArtifactOverflow as e:
        # Never truncated into something that looks like a plan.
        summary.update(artifact=None, artifact_refused=str(e), terminal_output="overflow")
        code = EXIT_HELD
    except FileExistsError as e:
        summary.update(artifact=None, artifact_refused=f"exists:{e}")
        code = EXIT_HELD
    except bounds.WallExpired as e:
        # Past the artifact's turn: no plan file, but the console's turn is
        # still inside the wall, so the operator gets the receipt if the
        # console can take it in time.
        summary.pop("artifact_bytes", None)
        if args.output and os.path.lexists(args.output):
            # Linked whole just before the alarm (it never pre-exists: refused).
            summary.update(artifact=args.output, artifact_written_at_wall=True)
        else:
            summary.update(artifact=None, artifact_refused=f"wall_expired:{e.phase}")
        summary["budget_stop"] = summary.get("budget_stop") or "wall"
        code = EXIT_HELD
    if not bounds.deliver_receipt(wall, lambda: json.dumps(summary, indent=2, default=str)):
        code = EXIT_HELD
    return code


if __name__ == "__main__":
    from app.services.kalshi_archive_bounds import exit_process

    exit_process(main())
