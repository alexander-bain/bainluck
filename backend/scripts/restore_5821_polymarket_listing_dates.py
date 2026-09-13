"""#5821 — the one-command undo for `repair_5821_polymarket_listing_dates.py`.

D51 is what makes that repair applicable at all: it backs up first and ships a
restore. This is the restore. It puts `events.commence_time` back to the value
`backup_5821_event_dates` recorded, for exactly the rows in that table and no
others. The repair writes ONE column, so the undo restores one column.

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

THE DRIFT LINE IS THE POINT, NOT DECORATION. It counts rows whose clock is not
the backed-up value, which after an apply is every row the repair moved. Read it
BEFORE `--apply`: a count far below the repair's own `APPLIED` number means
something else has been writing these clocks since, and restoring would then be
reverting that writer as well.
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
        print(f"=== #5821 restore === backup holds {n} event clocks")

        drift = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} b JOIN events e "
                    "ON e.id = b.id "
                    "WHERE e.commence_time IS DISTINCT FROM b.commence_time"
                )
            )
        ).scalar()
        print(f"  rows currently differing from the backup: {drift}")

        if not args.apply:
            print("\nDRY RUN — nothing written. --apply restores the clocks above.")
            return 0

        await s.execute(
            text(
                "UPDATE events e SET commence_time = b.commence_time "
                f"FROM {BACKUP_TABLE} b WHERE e.id = b.id"
            )
        )
        await s.commit()
        print(f"\nRESTORED {n} event clocks to their pre-repair values.")
        return 0


def main():
    p = argparse.ArgumentParser(description="#5821 listing-date repair undo")
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
