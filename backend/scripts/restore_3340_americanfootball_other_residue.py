"""#3340 — the one-command undo for the American Football residue void (D51).

Reads `bak_3340_af_other_status` and writes each banked `old_status` back onto
the event it was banked from. Nothing else moves: the repair flipped one column,
so the undo restores one column.

    python3 scripts/restore_3340_americanfootball_other_residue.py            # dry run
    python3 scripts/restore_3340_americanfootball_other_residue.py --apply

Heroku one-off (gotcha #48 — PROJECT_PATH=backend puts scripts at /app, so NO
`cd backend`):

    heroku run:detached "python3 scripts/restore_3340_americanfootball_other_residue.py --apply" -a bainluck

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
It does not restore a row whose status has moved on to something OTHER than the
`voided` the repair wrote. If a poller or a later repair has since given the row
a real status, that is newer information than the backup, and clobbering it with
a banked `scheduled` would be the undo causing the damage it exists to reverse.
Those rows are reported by id and skipped.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and #3340's repair is idempotent precisely so the pair can be
exercised more than once.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_3340_americanfootball_other_residue import (  # noqa: E402
    BAK_TABLE,
    VOID_STATUS,
)

_PLAN_SQL = f"""
SELECT b.event_id, b.old_status, e.status AS current_status
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


async def restore_rows(
    session, plan: list, *, progress_every: int = 250
) -> tuple[int, list[int]]:
    """Put each banked status back, ONE ROW PER TRANSACTION.

    Same rail as the repair: `events` is write-hot, so a batch UPDATE or a short
    `lock_timeout` rolls back on every row where a patient single-row write
    succeeds.

    Returns ``(written, failed_ids)``. An undo that silently leaves rows voided is
    worse than one that fails loudly — the operator believes the takedown has been
    reversed and stops looking.
    """
    from sqlalchemy import text

    written = 0
    failed: list[int] = []
    for index, entry in enumerate(plan, start=1):
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET status = :old "
                        "WHERE id = :eid AND status = :void"
                    ),
                    {
                        "old": entry["old_status"],
                        "eid": entry["event_id"],
                        "void": VOID_STATUS,
                    },
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {entry['event_id']} after 3 attempts: {exc}")
                    failed.append(entry["event_id"])
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(plan)} processed, {written} restored")
    return written, failed


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as session:
        exists = (
            await session.execute(text(f"SELECT to_regclass('{BAK_TABLE}')"))
        ).scalar()
        if not exists:
            print(f"No backup table {BAK_TABLE} — nothing to restore.")
            return

        rows = (await session.execute(text(_PLAN_SQL))).all()
        restorable = [
            {"event_id": r.event_id, "old_status": r.old_status}
            for r in rows
            if r.current_status == VOID_STATUS
        ]
        moved_on = [
            {
                "event_id": r.event_id,
                "banked": r.old_status,
                "current": r.current_status,
            }
            for r in rows
            if r.current_status != VOID_STATUS
        ]

        print(f"=== #3340 restore plan from {BAK_TABLE} ===")
        print(
            json.dumps(
                {
                    "banked": len(rows),
                    "restorable": len(restorable),
                    "skipped_status_moved_on": len(moved_on),
                },
                indent=2,
            )
        )
        if moved_on:
            print(
                f"\nSKIPPING {len(moved_on)} row(s) whose status is no longer "
                f"'{VOID_STATUS}' — newer information than the backup:"
            )
            for entry in moved_on[:20]:
                print(
                    f"  event {entry['event_id']}: banked {entry['banked']!r}, "
                    f"now {entry['current']!r}"
                )
            if len(moved_on) > 20:
                print(f"  … and {len(moved_on) - 20} more")

        if not restorable:
            print("\nNothing to restore.")
            return

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(restorable)} row(s) would be "
                f"restored to their banked status. Re-run with --apply."
            )
            return

        print(f"\nRESTORING {len(restorable)} rows, one transaction each …")
        written, failed = await restore_rows(session, restorable)
        print(f"\nCOMMITTED: {written} rows restored to their banked status.")
        print(f"The backup table {BAK_TABLE} is left in place deliberately.")

        # Same terminal rule as the repair: re-read the state rather than trusting
        # the loop's own count, and never report a clean undo over a short one.
        still_void = (
            await session.execute(
                text(
                    f"SELECT count(*) FROM {BAK_TABLE} b JOIN events e "
                    "ON e.id = b.event_id WHERE e.status = :void"
                ),
                {"void": VOID_STATUS},
            )
        ).scalar() or 0

        if failed or still_void:
            print("\n❌ RESTORE INCOMPLETE — the undo did NOT finish:")
            if failed:
                print(
                    f"  - {len(failed)} row(s) exhausted their retries: "
                    f"{failed[:20]}{' …' if len(failed) > 20 else ''}"
                )
            if still_void:
                print(f"  - {still_void} banked row(s) are still '{VOID_STATUS}'")
            print(
                "\nThe restored rows are durable, so re-running --apply resumes "
                "from here."
            )
            sys.exit(1)

        print(f"\n✅ every banked row is off '{VOID_STATUS}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write the restore (dry run otherwise)"
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
