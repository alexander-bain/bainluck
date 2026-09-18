"""#5821 — STEP 3 of the undo for the Polymarket container-twin tags (D51).

Reads `bak_5821_container_twin_tags` and removes, from each duplicate row, the
ONE `provenance:duplicate-of:<canonical>` element the sweep appended. Every
fixture goes straight back to serving its spread and totals on the hidden row
and nowhere else, i.e. back to the defect — which is the point of an undo.

🔴 RUNNING THIS ALONE IS NOT A ROLLBACK (#6786 review).
───────────────────────────────────────────────────────
This used to call itself "the one-command undo". It is not one command. The
sweep's beat runs `apply=True` at :27 EVERY HOUR and its planner selects on the
ABSENCE of the tag — so tags removed here are re-applied by the next pass,
within the hour, silently. Stop the sweep first, and confirm the stop landed:

    1. heroku config:set CONTAINER_TWIN_SWEEP_DISABLED=1 -a bainluck
    2. read /api/admin/celery/task-metrics/polymarket_container_twin_sweep
       after the next :27 — `terminal` must be `skipped` and the reason must
       name CONTAINER_TWIN_SWEEP_DISABLED. Do NOT infer this from the clock.
    3. run this script with --apply
    4. heroku config:unset CONTAINER_TWIN_SWEEP_DISABLED -a bainluck  (to resume)

    python3 scripts/restore_5821_container_twin_tags.py            # dry run
    python3 scripts/restore_5821_container_twin_tags.py --apply

Heroku one-off (gotcha #48 — `PROJECT_PATH=backend` puts scripts at /app, so NO
`cd backend`; and never a non-detached run, whose empty stdout is not a result):

    heroku run:detached -a bainluck "python3 scripts/restore_5821_container_twin_tags.py --apply"

SURGICAL REMOVAL, NOT A RESTORE OF THE WHOLE ARRAY
──────────────────────────────────────────────────
The banked `old_tags` are read and counted, but they are NOT written back.
`event_tags` is a shared multi-valued column — the enrichment pass adds
`audience:*` and `narrative:*` elements, the registry adds `provenance:*` ones —
so writing a banked array back would silently delete every tag anyone else has
added since. Instead this removes exactly the element the sweep added, with
jsonb `-`, and leaves the rest of the array untouched. An undo that causes its
own damage is not an undo.

ITS OWN TABLE, ITS OWN UNDO
───────────────────────────
`bak_5896_soccer_ghost_tags` and `bak_2878_twin_ghost_tags` hold the soccer and
tennis sweeps' rows and this script never touches them. The three repairs write
the same KIND of label for different reasons, and an operator rolling back a
container-pairing regression must not also restore every soccer ghost to
advertising a game that was played on Wednesday.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the sweep is idempotent precisely so the pair can be
exercised more than once.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.tasks.polymarket_container_twin_sweep import BAK_TABLE  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id,
       b.canonical_id,
       b.old_tags,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS current_tags
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


#: Postgres SQLSTATE for `undefined_table`. The ONLY read failure that honestly
#: means "the sweep has never written here".
_UNDEFINED_TABLE = "42P01"


def is_missing_backup_table(exc: BaseException) -> bool:
    """Is this exception a genuine "that table does not exist", and nothing else?

    🔴 **A FAILED READ IS NOT AN ABSENCE** (gotcha #53). Until #6786's review this
    script caught *every* exception here and printed "No backup table — nothing to
    undo" with a SUCCESS exit. A dropped connection, a permission error, a
    statement timeout, a typo in the SQL and a genuinely missing table were one
    outcome, and the loudest of them was silent: an operator rolling back a live
    repair would read "nothing to undo", believe the rows were never tagged, and
    stop looking — while every duplicate stayed folded.

    Both drivers surface the SQLSTATE, and this reads either: asyncpg puts it on
    ``sqlstate``, psycopg2 on ``pgcode``, and SQLAlchemy wraps the driver error as
    ``.orig``. Anything we cannot positively identify as 42P01 is NOT an absence,
    which is the fail-closed direction: the caller aborts loudly rather than
    reporting a clean no-op it cannot support.
    """
    for candidate in (getattr(exc, "orig", None), exc):
        if candidate is None:
            continue
        code = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if code:
            return str(code) == _UNDEFINED_TABLE
    return False


async def remove_tags(session, plan, *, progress_every: int = 25):
    """Strip the sweep's tag from each row, ONE ROW PER TRANSACTION.

    Same rail as the sweep: `events` is write-hot, so a batch UPDATE rolls back
    on every row where a patient single-row write succeeds.

    Returns ``(written, failed_ids)``. An undo that silently leaves rows folded
    is worse than one that fails loudly — the operator believes the markets are
    back where they were and stops looking (gotcha #53).
    """
    from sqlalchemy import text

    written, failed = 0, []
    for index, row in enumerate(plan, start=1):
        tag = duplicate_tag(row.canonical_id)
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET event_tags = event_tags - :tag "
                        "WHERE id = :eid "
                        "  AND COALESCE(event_tags, '[]'::jsonb) "
                        "      @> CAST(:tag_array AS jsonb)"
                    ),
                    {
                        "tag": tag,
                        "tag_array": json.dumps([tag]),
                        "eid": row.event_id,
                    },
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {row.event_id} after 3 attempts: {exc}")
                    failed.append(row.event_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(plan)} processed, {written} untagged")
    return written, failed


async def run(*, apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as session:
        try:
            plan = (await session.execute(text(_PLAN_SQL))).all()
        except Exception as exc:  # noqa: BLE001 — classified immediately below
            await session.rollback()
            if not is_missing_backup_table(exc):
                # NOT an absence. Exit 2 rather than 1, so an operator can tell
                # "I could not read the backup" from "the undo ran and left rows
                # folded" (the exit 1 at the end of this function).
                print(f"\n❌ #5821 undo ABORTED — could not read {BAK_TABLE}.")
                print(f"   {type(exc).__name__}: {exc}")
                print(
                    "   This is NOT 'nothing to undo'. The tags may still be on "
                    "the rows and the fold may still be live. Fix the read and "
                    "re-run; do not treat this as a completed rollback."
                )
                sys.exit(2)
            print(
                f"No backup table {BAK_TABLE} — the sweep has not written here, "
                f"so there is nothing to undo."
            )
            return

        carrying = [
            r for r in plan if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]
        print("\n=== #5821 undo ===")
        print(
            json.dumps(
                {
                    "banked": len(plan),
                    "still_carrying_the_tag": len(carrying),
                    "already_clear": len(plan) - len(carrying),
                },
                indent=2,
            )
        )
        for row in carrying[:20]:
            print(f"  event {row.event_id}: drop duplicate-of:{row.canonical_id}")
        if len(carrying) > 20:
            print(f"  … and {len(carrying) - 20} more")

        if not carrying:
            print("\nNothing to undo — no banked row still carries the tag.")
            return
        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(carrying)} row(s) would go "
                f"back to holding their markets alone. Re-run with --apply."
            )
            return

        written, failed = await remove_tags(session, carrying)
        after = (await session.execute(text(_PLAN_SQL))).all()
        remaining = [
            r.event_id
            for r in after
            if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]

        print(f"\nCOMMITTED: {written} tag(s) removed.")
        if failed or remaining:
            print("\n❌ #5821 UNDO INCOMPLETE — some rows are still folded:")
            if failed:
                print(f"  - {len(failed)} exhausted their retries: {failed[:20]}")
            if remaining:
                print(f"  - {len(remaining)} still carry the tag: {remaining[:20]}")
            sys.exit(1)
        print(f"\n✅ #5821 undone — {written} row(s) hold their own markets again.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the undo")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
