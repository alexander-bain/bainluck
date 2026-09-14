"""Undo `repair_6126_candle_lone_ask_openings.py` — put the 99% openings back.

    heroku run:detached -a bainluck -- \
        python3 scripts/restore_6126_candle_lone_ask_openings.py --apply

IT IS IDEMPOTENT AND IT DOES NOT DROP THE BACKUP. Running it twice writes the
same two states twice; the tables stay so a third run is still possible.

IT DOES NOT CARRY THE REPAIR'S `tap_is_off` OR `HEROKU_APP_NAME` GATE,
DELIBERATELY. Those gates exist to stop a repair landing where the producer
would immediately re-mint it — an argument about writing the NEW state. An undo
writes the OLD state, and the moment you want an undo is the moment something
has gone wrong, which is the worst possible time to be refused by an interlock
that was protecting a different decision. It only needs the backup to exist.

WHAT IT RESTORES, in the mirror image of the repair's order:

  1. futures_odds_snapshots   re-INSERT every deleted row, original id and all
  2. futures_outcomes         opening_probability / opening_captured_at /
                              opening_source back to their backed-up values

The snapshot rows are re-inserted with their ORIGINAL primary keys. That is why
the repair backs up whole rows rather than just the ids it deleted: a re-insert
under a fresh id would leave every foreign reference and every `ON CONFLICT`
path pointing at a row that no longer exists, and the curve would be rebuilt
from a row the rest of the system had never seen.

`ON CONFLICT (id) DO NOTHING` on the re-insert: if a row is somehow already
back, that is the state we wanted and is not an error.

IT REPORTS WHAT IT COULD NOT DO. A backup row whose outcome has since been
deleted cannot be restored — the FK would refuse it. Those are counted and
named rather than swallowed, because "the undo ran" and "the undo worked" are
different claims (gotcha #53).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        present = (
            await s.execute(
                text(
                    "SELECT to_regclass('public.backup_6126_snapshots') IS NOT NULL, "
                    "       to_regclass('public.backup_6126_openings')  IS NOT NULL"
                )
            )
        ).fetchone()
        if not (present[0] and present[1]):
            print(
                "Nothing to restore: backup_6126_snapshots / backup_6126_openings "
                "do not both exist. The repair's --backup has not run here."
            )
            return 0

        n_snap = (
            await s.execute(text("SELECT count(*) FROM backup_6126_snapshots"))
        ).scalar()
        n_open = (
            await s.execute(text("SELECT count(*) FROM backup_6126_openings"))
        ).scalar()
        print(f"backup holds {n_snap} snapshot rows and {n_open} openings")

        # Rows whose outcome has since disappeared cannot come back; the FK
        # would refuse the insert and take the whole statement with it.
        orphan_snap = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_6126_snapshots b "
                    "LEFT JOIN futures_outcomes o ON o.id = b.outcome_id "
                    "WHERE o.id IS NULL"
                )
            )
        ).scalar()
        orphan_open = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_6126_openings b "
                    "LEFT JOIN futures_outcomes o ON o.id = b.id "
                    "WHERE o.id IS NULL"
                )
            )
        ).scalar()
        if orphan_snap or orphan_open:
            print(
                f"  {orphan_snap} snapshot rows and {orphan_open} openings name an "
                "outcome that no longer exists — they will be SKIPPED, not restored"
            )

        if not args.apply:
            print("\ndry run — nothing written (pass --apply)")
            return 0

        restored_snap = (
            await s.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (id, outcome_id, bookmaker, "
                    "probability, american_odds, yes_bid, yes_ask, last_price, "
                    "captured_at, reading_count, valid_until) "
                    "SELECT b.id, b.outcome_id, b.bookmaker, b.probability, "
                    "b.american_odds, b.yes_bid, b.yes_ask, b.last_price, "
                    "b.captured_at, b.reading_count, b.valid_until "
                    "FROM backup_6126_snapshots b "
                    "JOIN futures_outcomes o ON o.id = b.outcome_id "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )
        ).rowcount
        restored_open = (
            await s.execute(
                text(
                    "UPDATE futures_outcomes o SET "
                    "opening_probability = b.opening_probability, "
                    "opening_captured_at = b.opening_captured_at, "
                    "opening_source     = b.opening_source "
                    "FROM backup_6126_openings b WHERE o.id = b.id"
                )
            )
        ).rowcount
        await s.commit()

        print(
            f"\nrestored {restored_snap} snapshot rows "
            f"({n_snap - orphan_snap - restored_snap} already present) "
            f"and {restored_open} openings"
        )
        print("backup tables left in place — a second run is still possible")

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
