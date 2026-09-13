"""#5982 undo — put every repaired event back on the competition it held.

One command, and it is the whole reason the repair may be applied without Alex
at the keyboard (D51(b)):

    heroku run:detached -a bainluck-heavy -- \
        python3 scripts/restore_5982_laliga2_events_under_la_liga.py --apply

It restores from `backup_5982_event_sports`, which holds each event's `sport_id`
as it stood the moment `--backup` ran. It is not "set them back to La Liga": the
recorded value is replayed per row, so a row that was somewhere else entirely
goes back to somewhere else entirely.

Rows already restored (`restored_at IS NOT NULL`) are skipped, so a second run
is a no-op rather than a second write. Without `--apply` it prints what it would
do and writes nothing.

The wrong-app refusal is IMPORTED from the repair rather than re-spelled: a
restore is a production write in the opposite direction and earns the identical
gate, and two constants for one decision is how a runbook and its program start
to disagree.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the sibling import below resolves however
# the file is loaded. Running `python3 scripts/restore_….py` puts `scripts/` on
# the path for free; importing the file by its path (the guard test does) does
# not, and the difference is an ImportError nobody sees until CI.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repair_5982_laliga2_events_under_la_liga import (  # noqa: E402
    BACKUP_TABLE,
    PRODUCER_APP,
    wrong_app_refusal,
)

__all__ = ["BACKUP_TABLE", "PRODUCER_APP", "main", "run"]


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        exists = (
            await s.execute(
                text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
            )
        ).scalar()
        if not exists:
            print(
                f"Nothing to restore: {BACKUP_TABLE} does not exist, so the "
                "repair never ran on this database."
            )
            return 0

        pending = (
            await s.execute(
                text(
                    "SELECT b.event_id, b.sport_id AS was, e.sport_id AS now_is, "
                    "       e.home_team_name, e.away_team_name "
                    f"  FROM {BACKUP_TABLE} b "
                    "  JOIN events e ON e.id = b.event_id "
                    " WHERE b.restored_at IS NULL "
                    " ORDER BY b.event_id"
                )
            )
        ).all()

        print(f"=== #5982 undo — from {BACKUP_TABLE} ===")
        if not pending:
            print("Nothing to restore — every recorded row is already restored.")
            return 0

        for r in pending:
            moved = "" if r.was == r.now_is else f"  (currently {r.now_is})"
            print(
                f"  {r.event_id}  {r.home_team_name} v {r.away_team_name}  "
                f"-> sport_id {r.was}{moved}"
            )
        print()

        if not args.apply:
            print(f"DRY RUN — nothing written. {len(pending)} row(s) would restore.")
            return 0

        result = await s.execute(
            text(
                "UPDATE events e SET sport_id = b.sport_id "
                f"  FROM {BACKUP_TABLE} b "
                " WHERE b.event_id = e.id AND b.restored_at IS NULL"
            )
        )
        await s.execute(
            text(
                f"UPDATE {BACKUP_TABLE} SET restored_at = now() "
                " WHERE restored_at IS NULL"
            )
        )
        await s.commit()
        print(f"RESTORED: {result.rowcount} event(s) put back on their recorded sport.")
        return 0


def main():
    p = argparse.ArgumentParser(description="#5982 repair undo")
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
