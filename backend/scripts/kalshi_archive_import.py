#!/usr/bin/env python3
"""#683 archive import — ATTENDED. Dry-run unless ``--write`` is given.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web and native, with
archive provenance and honest forecast eligibility.

Takes a plan written by ``kalshi_archive_recovery_dry_run.py --output`` and
imports it into the archive store (``app.services.kalshi_archive_apply``).

    # what WOULD be written, nothing is (read-only transaction):
    python3 scripts/kalshi_archive_import.py apply --plan /tmp/683-plan.json \\
        --expected-digest <plan_digest printed by the dry run>
    # the attended write, same command plus --write:
    python3 scripts/kalshi_archive_import.py apply --plan ... --expected-digest ... --write
    # undo exactly one import's own rows (dry-run first, then --write):
    python3 scripts/kalshi_archive_import.py restore --import-key <key> [--write]
    # cohort accounting for named outcomes (read-only):
    python3 scripts/kalshi_archive_import.py cohort --outcome-ids 101,102

``--expected-digest`` is the plan's content address and must be typed, not
read from the file: the apply refuses when it differs from the digest it
recomputes from the plan's points. Running ``--write`` against production is an
attended action under the existing approval gate. Nothing here schedules
itself, enables a reader or changes the Accuracy curve.

THE ATTENDED BOUNDS (``app.services.kalshi_archive_bounds``). Every subcommand
takes a REQUIRED ``--deadline``: one inclusive wall over connecting, reading and
decoding the plan (``--max-plan-bytes``, refused before decoding), validation,
every database statement, cancel/close, and writing the receipt. Every database
connection carries a 10 s statement and 500 ms lock timeout. ``apply`` also
REQUIRES ``--max-outcomes`` and ``--max-points`` and refuses a larger plan.
Console output is capped by ``--max-console-bytes`` and the ``--output``
receipt by ``--max-artifact-bytes`` (whole or not at all, never over an
existing file). The first attended sample:

    python3 scripts/kalshi_archive_import.py apply --plan P --expected-digest D \
        --max-outcomes 1 --max-points 26 --deadline 30 --output R

Exit codes: 0 applied (complete history for every imported outcome, nothing
refused, nothing uncertain); 1 partial (refusals, conflicts, errors, or a plan
that is not complete history; ``incomplete_reasons`` says which); 2 refused
before anything was written; 3 the wall, an output cap, or an unacknowledged
COMMIT stopped it, so the receipt may describe rows that ARE durable (read
``committed_outcomes``, ``commit_in_flight``, ``uncertain_commits`` and
``readback_owed``). No exit code is permission to retry or to restore.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    def bounded(parser):
        parser.add_argument(
            "--deadline",
            type=float,
            required=True,
            help="inclusive wall-clock seconds for the whole operation",
        )
        parser.add_argument(
            "--max-console-bytes", type=int, default=256 << 10, help="stdout+stderr"
        )

    a = sub.add_parser("apply", help="dry-run (default) or apply one plan")
    a.add_argument("--plan", required=True, help="the dry run's --output JSON")
    a.add_argument("--expected-digest", required=True, help="the plan's digest, typed")
    a.add_argument("--write", action="store_true", help="actually write (attended)")
    a.add_argument("--output", default="", help="write the full result JSON here")
    a.add_argument(
        "--max-outcomes", type=int, required=True, help="refuse a plan with more"
    )
    a.add_argument(
        "--max-points", type=int, required=True, help="refuse a plan with more"
    )
    a.add_argument("--max-plan-bytes", type=int, default=256 << 10)
    a.add_argument("--max-artifact-bytes", type=int, default=256 << 10)
    bounded(a)
    r = sub.add_parser("restore", help="remove one import's own rows")
    r.add_argument("--import-key", required=True)
    r.add_argument("--write", action="store_true", help="actually delete (attended)")
    r.add_argument(
        "--allow-applying",
        action="store_true",
        help="restore an import whose apply never finished (its process is gone)",
    )
    bounded(r)
    c = sub.add_parser("cohort", help="zero-snapshot cohort vs archive history")
    c.add_argument("--outcome-ids", required=True, help="comma-separated ids")
    bounded(c)
    return p.parse_args(argv)


EXIT_APPLIED, EXIT_PARTIAL, EXIT_REFUSED, EXIT_INCOMPLETE = 0, 1, 2, 3


def main(argv=None, *, session_factory=None) -> int:
    args = _parse(argv)
    # Installed before the app is imported (see the planner CLI).
    from app.services.kalshi_archive_bounds import ConsoleCap

    try:
        console = ConsoleCap(args.max_console_bytes).install()
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        code = _run(args, session_factory)
    finally:
        console.restore()
    if console.overflowed and code in (EXIT_APPLIED, EXIT_PARTIAL):
        return EXIT_INCOMPLETE
    return code


def _run(args, session_factory) -> int:
    from app.services import kalshi_archive_apply as imp
    from app.services import kalshi_archive_bounds as bounds

    try:
        wall = bounds.OperationWall(args.deadline)
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    extra = {} if session_factory is None else {"session_factory": session_factory}
    progress: dict = {"phase": "start"}

    def run(make):
        return bounds.run_bounded_loop(
            bounds.run_within_wall(
                make,
                wall=wall,
                progress=progress,
                cancel_until=wall.deadline - wall.reserve / 2,
            )
        )

    if args.cmd == "apply":
        if args.output and os.path.lexists(args.output):
            print(f"REFUSED: --output exists, never overwritten: {args.output}", file=sys.stderr)
            return EXIT_REFUSED
        try:
            with wall.sync_phase("plan_load"):
                report = bounds.read_bounded_json(args.plan, args.max_plan_bytes)
        except (bounds.InputTooLarge, bounds.WallExpired, ValueError, OSError) as e:
            print(f"REFUSED: plan unreadable: {e}", file=sys.stderr)
            return EXIT_REFUSED
        try:
            result = run(
                lambda: imp.apply_archive_plan(
                    report,
                    expected_digest=args.expected_digest,
                    write=args.write,
                    max_outcomes=args.max_outcomes,
                    max_points=args.max_points,
                    wall=wall,
                    progress=progress,
                    **extra,
                )
            )
        except imp.PlanRefused as e:
            print(f"REFUSED: {e.reason}", file=sys.stderr)
            return EXIT_REFUSED
        except bounds.WallExpired as e:
            return _incomplete(args, wall, progress, f"wall_expired:{e.phase}")
        except Exception as e:  # noqa: BLE001 — the receipt says what was durable
            return _incomplete(args, wall, progress, f"{type(e).__name__}: {str(e)[:160]}")
        code = EXIT_APPLIED if result["status"] == "applied" else EXIT_PARTIAL
        if result.get("uncertain_commits") or result.get("commit_in_flight"):
            code = EXIT_INCOMPLETE
        return _emit(args, wall, result, code, artifact=True)

    try:
        if args.cmd == "restore":
            result = run(
                lambda: imp.restore_archive_import(
                    args.import_key,
                    write=args.write,
                    allow_applying=args.allow_applying,
                    progress=progress,
                    **extra,
                )
            )
            code = EXIT_APPLIED if result["refused"] is None else EXIT_PARTIAL
            if result.get("uncertain_commits") or result.get("commit_in_flight"):
                code = EXIT_INCOMPLETE
        else:
            ids = [int(x) for x in args.outcome_ids.split(",") if x.strip()]
            progress["phase"] = "cohort"
            result = run(lambda: imp.archive_cohort(ids, **extra))
            code = EXIT_APPLIED
    except bounds.WallExpired as e:
        return _incomplete(args, wall, progress, f"wall_expired:{e.phase}")
    except Exception as e:  # noqa: BLE001
        return _incomplete(args, wall, progress, f"{type(e).__name__}: {str(e)[:160]}")
    return _emit(args, wall, result, code, artifact=False)


def _incomplete(args, wall, progress: dict, why: str) -> int:
    """The receipt of an operation that did not finish: what IS known, nothing more.

    Acknowledged commits stay listed as durable; a COMMIT still in flight is
    reported as such, so its rows are neither claimed nor denied.
    """
    receipt = {k: v for k, v in progress.items() if k != "outcomes"}
    receipt["status"] = "incomplete"
    receipt["stopped"] = why
    receipt["elapsed_s"] = round(wall.elapsed(), 3)
    if progress.get("commit_in_flight"):
        receipt.setdefault("uncertain_commits", [])
        receipt["uncertain_commits"] = list(receipt["uncertain_commits"]) + [
            {**progress["commit_in_flight"], "error": "acknowledgement_not_received"}
        ]
    if receipt.get("uncertain_commits") or receipt.get("committed_outcomes"):
        from app.services.kalshi_archive_apply import _readback_owed

        receipt["readback_owed"] = _readback_owed(receipt)
    if args.cmd == "apply" and progress.get("import_id") is not None:
        receipt["import_row"] = "applying_or_unknown"
    _emit(args, wall, receipt, EXIT_INCOMPLETE, artifact=args.cmd == "apply", late=True)
    return EXIT_INCOMPLETE


def _emit(args, wall, result: dict, code: int, *, artifact: bool, late: bool = False) -> int:
    from app.services import kalshi_archive_bounds as bounds

    summary = {k: v for k, v in result.items() if k != "outcomes"}
    try:
        if late:
            # Past the wall already: write the receipt without a second alarm.
            if artifact and args.output:
                summary["artifact_bytes"] = bounds.write_bounded_artifact(
                    args.output, result, args.max_artifact_bytes
                )
            text = json.dumps(summary, indent=2, default=str)
        else:
            with wall.sync_phase("serialize", work=False):
                if artifact and args.output:
                    summary["artifact_bytes"] = bounds.write_bounded_artifact(
                        args.output, result, args.max_artifact_bytes
                    )
                text = json.dumps(summary if artifact else result, indent=2, default=str)
    except (bounds.ArtifactOverflow, FileExistsError) as e:
        summary.update(artifact=None, artifact_refused=str(e))
        text = json.dumps(summary, indent=2, default=str)
        code = EXIT_INCOMPLETE
    except bounds.WallExpired as e:
        print(f"INCOMPLETE: wall expired while writing ({e.phase})", file=sys.stderr)
        return EXIT_INCOMPLETE
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
