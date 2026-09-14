"""#6215 undo — put every field `repair_6215_borrowed_espn_identity.py` cleared back.

One command, D51:

    heroku run:detached -a bainluck -- python3 backend/scripts/restore_6215_borrowed_espn_identity.py --apply

Restores from `backup_6215_borrowed_espn_identity`, row by row and column by
column, so a team whose identity was legitimately re-enriched between the repair
and the undo is not clobbered back to its borrowed values — the restore writes
only rows that still read NULL in the field it holds a value for.

The app gate is IMPORTED from the repair rather than copied. A restore is a
production write in the opposite direction and earns the identical refusal; two
copies of one gate is how they drift.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_6215_borrowed_espn_identity import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)

_RESTORE_SQL = f"""
UPDATE teams t
   SET abbreviation    = COALESCE(t.abbreviation, b.abbreviation),
       current_record  = COALESCE(t.current_record, b.current_record),
       location        = COALESCE(t.location, b.location),
       logo_url_small  = COALESCE(t.logo_url_small, b.logo_url_small),
       logo_url_large  = COALESCE(t.logo_url_large, b.logo_url_large),
       primary_color   = COALESCE(t.primary_color, b.primary_color),
       secondary_color = COALESCE(t.secondary_color, b.secondary_color),
       alternate_names = COALESCE(t.alternate_names, b.alternate_names)
  FROM {BACKUP_TABLE} b
 WHERE t.id = b.team_id
"""


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
            print(
                "REFUSING: the backup table is empty, so there is nothing to "
                "restore and a silent success here would read as a completed undo."
            )
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
