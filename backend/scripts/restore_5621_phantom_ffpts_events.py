"""#5621 — the one-command undo for `repair_5621_phantom_ffpts_events.py`.

D51(b) is what lets the owning lane apply that repair unattended: it writes a
backup first and ships a restore. This is the restore. It puts every column the
repair touched back to the value the backup recorded — `events.status`, and the
market's `llm_sport_category` / `sport_id` / `event_id` — for exactly the rows
in the backup tables and no others.

    python3 scripts/restore_5621_phantom_ffpts_events.py           # dry run
    python3 scripts/restore_5621_phantom_ffpts_events.py --apply

    heroku run:detached -a bainluck-heavy \
        "python3 scripts/restore_5621_phantom_ffpts_events.py --apply"

Run it on the same app the repair ran on (`bainluck-heavy`, the app the Kalshi
poller and the matcher actually run on — see that script's header and standing
notice 48), so the undo is taken against the deploy that produced the state.

WHY IT JOINS RATHER THAN LOOPS. The backup holds the prior value per id, so the
restore is one UPDATE…FROM per table. A loop would restore partially if it died
halfway; a single statement either lands or does not.

IT IS IDEMPOTENT AND IT DOES NOT DROP THE BACKUP. Running it twice writes the
same values twice. The backup tables are left in place deliberately — a restore
that destroys its own evidence cannot be checked afterwards, and these two
tables are 16 rows each.

IT COUNTS WHAT IT WROTE, AND A ROW THAT VANISHED IS NOT A ROW THAT AGREES. Both
numbers this prints used to be read off the backup: the success line was the
backup's row count, taken before the UPDATEs, and the drift line joined the
backup to `events`, so a row DELETED since the backup contributed nothing to
either — the undo would report restoring sixteen while writing fifteen, and the
dry run would report "0 differing" about a row it could no longer reach. Both
are the same mistake (gotcha #53: an absence is not agreement), and on an
attended undo that printed line is the entire verdict Alex gets.

IT DOES NOT CARRY THE REPAIR'S `HEROKU_APP_NAME` GATE, DELIBERATELY. The repair
refuses to WRITE anywhere but `bainluck-heavy` because an apply on the wrong
deploy is a new mistake. An undo is the opposite: refusing one leaves the
database in the state the operator is trying to leave. The `to_regclass` probe
below is the real scope test — no backup here means the repair never ran here.
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

        # The drift counts above are joins, so they can only speak about rows
        # that are still there. A backed-up id with no row left is unrestorable
        # and must be said out loud rather than folded into "0 differing".
        gone_e = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_5621_events b WHERE NOT EXISTS "
                    "(SELECT 1 FROM events e WHERE e.id = b.id)"
                )
            )
        ).scalar()
        gone_m = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_5621_markets b WHERE NOT EXISTS "
                    "(SELECT 1 FROM futures_markets f WHERE f.id = b.id)"
                )
            )
        ).scalar()
        # A market whose backed-up `event_id` names an event that has since been
        # deleted cannot have that link put back: `futures_markets_event_id_fkey`
        # would reject it and, being one statement, take the whole undo down with
        # it — every other row included. The repair itself is what makes this
        # reachable, because `--apply` sets `event_id = NULL`, which is exactly
        # the state that lets a delete rail (`prune_unanchored_duplicates`, aimed
        # at anchorless rows — which every row here is) remove the event without
        # the FK stopping it. So the link is the one thing this restore cannot
        # promise; the sport and category it still can, and those are the half a
        # reader sees.
        orphaned_m = (
            await s.execute(
                text(
                    "SELECT count(*) FROM backup_5621_markets b "
                    "JOIN futures_markets f ON f.id = b.id "
                    "WHERE b.event_id IS NOT NULL AND NOT EXISTS "
                    "(SELECT 1 FROM events e WHERE e.id = b.event_id)"
                )
            )
        ).scalar()
        print(
            f"  rows in the backup no longer present: {gone_e} events, {gone_m} markets"
        )
        print(
            f"  markets whose backed-up event is gone (link unrestorable): {orphaned_m}"
        )

        if not args.apply:
            print("\nDRY RUN — nothing written. --apply restores the values above.")
            return 0

        wrote_e = (
            await s.execute(
                text(
                    "UPDATE events e SET status = b.status "
                    "FROM backup_5621_events b WHERE e.id = b.id"
                )
            )
        ).rowcount
        wrote_m = (
            await s.execute(
                text(
                    "UPDATE futures_markets f SET llm_sport_category = b.llm_sport_category, "
                    "sport_id = b.sport_id, event_id = b.event_id "
                    "FROM backup_5621_markets b WHERE f.id = b.id "
                    "AND (b.event_id IS NULL OR EXISTS "
                    "     (SELECT 1 FROM events e WHERE e.id = b.event_id))"
                )
            )
        ).rowcount
        # The rows the statement above skipped still get everything that CAN be
        # put back. Restoring the sport and the category without the link is
        # what stops a vanished event turning the undo into all-or-nothing.
        relinked_m = (
            await s.execute(
                text(
                    "UPDATE futures_markets f SET llm_sport_category = b.llm_sport_category, "
                    "sport_id = b.sport_id "
                    "FROM backup_5621_markets b WHERE f.id = b.id "
                    "AND b.event_id IS NOT NULL AND NOT EXISTS "
                    "    (SELECT 1 FROM events e WHERE e.id = b.event_id)"
                )
            )
        ).rowcount
        await s.commit()
        # `wrote_*` is what the server reported updating, never `n_*`: the whole
        # point of the line is to tell the operator the undo happened.
        print(
            f"\nRESTORED {wrote_e} of {n_e} events and {wrote_m} of {n_m} markets "
            "to their pre-repair values."
        )
        if relinked_m:
            print(
                f"  {relinked_m} of those markets got their sport and category back "
                "but NOT their event link, because the event they pointed at has "
                "been deleted since the backup was taken."
            )
        if wrote_e != n_e or (wrote_m + relinked_m) != n_m:
            print(
                f"WARNING: {n_e - wrote_e} events and "
                f"{n_m - wrote_m - relinked_m} markets in the backup could not be "
                "restored at all because their rows are gone. The undo is "
                "INCOMPLETE — the backup tables are still here and hold the values "
                "those ids had before the repair."
            )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
