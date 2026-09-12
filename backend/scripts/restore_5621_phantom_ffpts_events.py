"""#5621 — the one-command undo for `repair_5621_phantom_ffpts_events.py`.

D51(b) is what lets the owning lane apply that repair unattended: it writes a
backup first and ships a restore. This is the restore. It puts every column the
repair touched back to the value the backup recorded — `events.status`, and the
market's `llm_sport_category` / `sport_id` / `event_id` — for exactly the rows
in the backup tables and no others.

    python3 scripts/restore_5621_phantom_ffpts_events.py           # dry run
    python3 scripts/restore_5621_phantom_ffpts_events.py --apply

    heroku run:detached -a bainluck \
        "python3 scripts/restore_5621_phantom_ffpts_events.py --apply"

WHY IT JOINS RATHER THAN LOOPS. The backup holds the prior value per id, so the
restore is one UPDATE…FROM per table. A loop would restore partially if it died
halfway; a single statement either lands or does not.

IT IS IDEMPOTENT AND IT DOES NOT DROP THE BACKUP. Running it twice writes the
same values twice. The backup tables are left in place deliberately — a restore
that destroys its own evidence cannot be checked afterwards, and these two
tables are 16 rows each.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        present = (
            await s.execute(
                text(
                    "SELECT to_regclass('public.backup_5621_events') IS NOT NULL "
                    "AND to_regclass('public.backup_5621_markets') IS NOT NULL"
                )
            )
        ).scalar()
        if not present:
            print(
                "REFUSING: backup_5621_events / backup_5621_markets do not exist. "
                "There is nothing to restore from — the repair never ran with "
                "--backup on this database."
            )
            return 2

        n_e = (
            await s.execute(text("SELECT count(*) FROM backup_5621_events"))
        ).scalar()
        n_m = (
            await s.execute(text("SELECT count(*) FROM backup_5621_markets"))
        ).scalar()
        print(f"=== #5621 restore === backup holds {n_e} events, {n_m} markets")

        drift_e = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_5621_events b JOIN events e "
                    "ON e.id = b.id WHERE e.status IS DISTINCT FROM b.status"
                )
            )
        ).scalar()
        drift_m = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_5621_markets b "
                    "JOIN futures_markets f ON f.id = b.id "
                    "WHERE f.llm_sport_category IS DISTINCT FROM b.llm_sport_category "
                    "   OR f.sport_id IS DISTINCT FROM b.sport_id "
                    "   OR f.event_id IS DISTINCT FROM b.event_id"
                )
            )
        ).scalar()
        print(f"  rows currently differing from backup: {drift_e} events, {drift_m} markets")

        if not args.apply:
            print("\nDRY RUN — nothing written. --apply restores the values above.")
            return 0

        await s.execute(
            text(
                "UPDATE events e SET status = b.status "
                "FROM backup_5621_events b WHERE e.id = b.id"
            )
        )
        await s.execute(
            text(
                "UPDATE futures_markets f SET llm_sport_category = b.llm_sport_category, "
                "sport_id = b.sport_id, event_id = b.event_id "
                "FROM backup_5621_markets b WHERE f.id = b.id"
            )
        )
        await s.commit()
        print(f"\nRESTORED {n_e} events and {n_m} markets to their pre-repair values.")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
