"""#5821 — the one-command undo for `repair_5821_polymarket_listing_dates.py`.

D51 is what makes that repair applicable at all: it backs up first and ships a
restore. This is the restore. It puts `commence_time` and `status` back to the
values `backup_5821_event_dates` recorded — the repair writes two columns, so
the undo restores two.

🔴 IT REVERTS THE RECEIPT, NOT THE PLAN (`5821-RESTORE-ONLY-SUCCESSFUL-CAS`).
The backup knows what every IN-SCOPE row held; only the apply knows which rows
its compare-and-set actually landed on, and it records that by stamping
`applied_commence_time` / `applied_status` on the backup row in the same
transaction as the write. This restore touches only rows carrying those stamps,
and does so by compare-and-set against them. So a row the apply SKIPPED — one
that moved between the read and the write — is left alone here instead of being
"restored" to a value nobody overwrote, and a row some other writer has moved
SINCE the apply is reported as drift rather than silently rolled back.

    python3 scripts/restore_5821_polymarket_listing_dates.py           # dry run
    python3 scripts/restore_5821_polymarket_listing_dates.py --apply

    heroku run:detached -a bainluck-heavy \
        "python3 scripts/restore_5821_polymarket_listing_dates.py --apply"

Run it on the same app the repair ran on (`bainluck-heavy` — the MATCHER, the
task that mints these rows, is in HEAVY_TASKS; see that script's header and
standing notice 48), so the undo is taken against the deploy that produced the
state.

WHY IT JOINS RATHER THAN LOOPS. The backup holds the prior clock per id, so the
restore is one `UPDATE … FROM`. A loop would restore partially if it died
halfway; a single statement either lands or does not.

IT IS IDEMPOTENT AND IT DOES NOT DROP THE BACKUP. Running it twice writes the
same values twice. The table is left in place deliberately — a restore that
destroys its own evidence cannot be checked afterwards.

THE NUMBERS ARE THE POINT, NOT DECORATION. `receipted` is how many rows the
apply actually wrote; `restorable` is how many of those still hold exactly what
it wrote. Read them BEFORE `--apply`: `restorable` below `receipted` means
something else has moved those rows since, and the difference is the count this
undo will decline to touch.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_TABLE = "backup_5821_event_dates"


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        present = (
            await s.execute(
                text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
            )
        ).scalar()
        if not present:
            print(
                f"REFUSING: {BACKUP_TABLE} does not exist. There is nothing to "
                "restore from — the repair never ran with --backup on this "
                "database."
            )
            return 2

        n = (await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))).scalar()
        receipted = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} "
                    "WHERE applied_commence_time IS NOT NULL"
                )
            )
        ).scalar()
        restorable = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} b JOIN events e "
                    "ON e.id = b.id "
                    "WHERE b.applied_commence_time IS NOT NULL "
                    "AND e.commence_time IS NOT DISTINCT FROM b.applied_commence_time "
                    "AND e.status IS NOT DISTINCT FROM b.applied_status"
                )
            )
        ).scalar()
        print(
            f"=== #5821 restore === backup holds {n} rows; "
            f"receipted (actually written by the apply) {receipted}; "
            f"restorable (still holding what the apply wrote) {restorable}"
        )
        if receipted and restorable < receipted:
            print(
                f"  NOTE: {receipted - restorable} receipted row(s) have moved "
                "since the apply. This undo will NOT touch them — reverting a "
                "value somebody else wrote is not a restore."
            )

        if not args.apply:
            print(
                f"\nDRY RUN — nothing written. --apply would restore "
                f"{restorable} row(s)."
            )
            return 0

        result = await s.execute(
            text(
                "UPDATE events e SET commence_time = b.commence_time, "
                "status = b.status "
                f"FROM {BACKUP_TABLE} b WHERE e.id = b.id "
                "AND b.applied_commence_time IS NOT NULL "
                "AND e.commence_time IS NOT DISTINCT FROM b.applied_commence_time "
                "AND e.status IS NOT DISTINCT FROM b.applied_status"
            )
        )
        await s.commit()
        print(
            f"\nRESTORED {result.rowcount} row(s) to their pre-repair clock and "
            f"status. {receipted - result.rowcount} receipted row(s) were left "
            "alone because they no longer hold what the apply wrote."
        )
        return 0


def main():
    p = argparse.ArgumentParser(description="#5821 listing-date repair undo")
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
