"""#9017 undo — put every field `repair_9017_foreign_espn_id.py` cleared back.

One command, D51:

    heroku run:detached -a bainluck -- python3 scripts/restore_9017_foreign_espn_id.py --apply

Column by column from `backup_9017_foreign_espn_id`, and only into a field that
still reads NULL: a row ESPN sync has re-enriched with its own club since the
repair keeps what it has now.

The app gate is imported from the repair, not copied.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS  # noqa: E402
from scripts.repair_9017_foreign_espn_id import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)

RESTORED_FIELDS = ("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)

_RESTORE_SQL = (
    "UPDATE teams t SET "
    + ", ".join(f"{f} = COALESCE(t.{f}, b.{f})" for f in RESTORED_FIELDS)
    + f" FROM {BACKUP_TABLE} b WHERE t.id = b.team_id"
)


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        banked = (
            await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))
        ).scalar_one()
        print(f"{BACKUP_TABLE}: {banked} rows")
        if not banked:
            print("REFUSING: the backup table is empty; nothing to restore.")
            return 2
        if not args.apply:
            print("plan only. Re-run with --apply.")
            return 0
        result = await s.execute(text(_RESTORE_SQL))
        await s.commit()
        print(f"restored: {result.rowcount} rows")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
