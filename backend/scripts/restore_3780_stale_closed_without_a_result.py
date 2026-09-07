"""#3780 — the one-command undo for the result-less-Final sweep (D51).

Reads `bak_3780_stale_closed_status` and writes each banked `old_status` AND
`old_completed_at` back onto the event they were banked from. Both columns,
because the repair wrote both — an undo that restored the status and left
`completed_at` cleared would leave the row in a state neither the repair nor
production ever produced.

    python3 scripts/restore_3780_stale_closed_without_a_result.py            # dry run
    python3 scripts/restore_3780_stale_closed_without_a_result.py --apply

Heroku one-off (gotcha #48 — detached, and PROJECT_PATH=backend puts scripts at
/app, so NO `cd backend`):

    heroku run:detached "python3 scripts/restore_3780_stale_closed_without_a_result.py --apply" -a bainluck

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
It does not restore a row whose status has moved on to something OTHER than the
`suspended` the repair wrote. `suspended` is settleable by design, so the whole
point of the repair is that ESPN or a venue may now report one of these matches
— and putting a banked `closed` back over a real `completed` would be the undo
causing exactly the damage it exists to reverse. Those rows are reported by id
and skipped.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the repair is idempotent precisely so the pair can be
exercised more than once.

🔴 `completed_at` IS BOUND AS A DATETIME, NEVER A STRING. asyncpg refuses a
`str` bound to a `timestamptz` — a repair that passes its review and deploys
having never executed a single write is a real failure mode in this repo. The
value comes back off the backup table as a datetime and is passed straight
through; nothing here formats it.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_3780_stale_closed_without_a_result import (  # noqa: E402
    BAK_TABLE,
    UNSETTLED_STATUS,
)

_PLAN_SQL = f"""
SELECT b.event_id, b.old_status, b.old_completed_at, e.status AS current_status
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


def restorable(row) -> bool:
    """Is this row still the one the repair left behind?

    Pure. True only when the row still holds the exact status the repair wrote.
    Anything else is newer information than the backup.
    """
    return row.current_status == UNSETTLED_STATUS


async def restore_rows(
    session, plan: list, *, progress_every: int = 500
) -> tuple[int, list[int]]:
    """Put each banked (status, completed_at) pair back, ONE ROW PER TRANSACTION.

    Same rail as the repair: `events` is write-hot, so a batch UPDATE or a short
    `lock_timeout` rolls back on every row where a patient single-row write
    succeeds.

    Returns ``(written, failed_ids)``. An undo that silently leaves rows
    unsettled is worse than one that fails loudly — the operator believes the
    change has been reversed and stops looking.
    """
    from sqlalchemy import text

    written = 0
    failed: list[int] = []
    for index, row in enumerate(plan, start=1):
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET status = :old_status, "
                        "completed_at = :old_completed_at "
                        "WHERE id = :eid AND status = :suspended"
                    ),
                    {
                        "old_status": row.old_status,
                        "old_completed_at": row.old_completed_at,
                        "suspended": UNSETTLED_STATUS,
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
            print(f"  … {index}/{len(plan)} processed, {written} restored")
    return written, failed


async def run(*, apply: bool) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            rows = (await session.execute(text(_PLAN_SQL))).all()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            print(f"REFUSING: cannot read {BAK_TABLE} ({exc}) — nothing to restore")
            sys.exit(1)

        plan = [r for r in rows if restorable(r)]
        moved_on = [r.event_id for r in rows if not restorable(r)]

        print(
            json.dumps(
                {
                    "banked": len(rows),
                    "restorable": len(plan),
                    "moved_on_and_skipped": len(moved_on),
                    "moved_on_examples": moved_on[:20],
                },
                indent=2,
            )
        )

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(plan)} row(s) would be put back "
                "to their banked status and completed_at. Re-run with --apply."
            )
            return

        written, failed = await restore_rows(session, plan)
        print(f"\nCOMMITTED: {written} row(s) restored.")

        if failed:
            print(
                f"\n❌ #3780 RESTORE INCOMPLETE — {len(failed)} row(s) exhausted "
                f"their retries and are still {UNSETTLED_STATUS!r}: "
                f"{failed[:20]}{' …' if len(failed) > 20 else ''}"
            )
            print("Re-running resumes from here; the backup table is not dropped.")
            sys.exit(1)

        print(f"\n✅ #3780 reversed. {BAK_TABLE} is kept so this can be re-run.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write the restore (default: dry run)"
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
