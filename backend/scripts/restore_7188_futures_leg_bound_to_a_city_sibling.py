"""#7188 undo — put every leg `repair_7188_futures_leg_bound_to_a_city_sibling.py` moved back.

One command, D51:

    heroku run:detached -a bainluck -- python3 scripts/restore_7188_futures_leg_bound_to_a_city_sibling.py --apply

Restores from `backup_7188_futures_leg_city_sibling`, and only for rows that
STILL carry the value the repair wrote (``team_id = team_id_after``). A leg that
was re-bound by something else between the repair and the undo — the drain, a
venue re-ingest, a later repair — keeps its newer binding rather than being
clobbered back to a rival club's id. An undo that overwrites work it did not do
is not an undo.

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

from scripts.repair_7188_futures_leg_bound_to_a_city_sibling import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)

_RESTORE_SQL = f"""
UPDATE futures_outcomes fo
   SET team_id = b.team_id_before
  FROM {BACKUP_TABLE} b
 WHERE fo.id = b.outcome_id
   AND fo.team_id = b.team_id_after
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
        restorable = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} b "
                    "JOIN futures_outcomes fo ON fo.id = b.outcome_id "
                    "WHERE fo.team_id = b.team_id_after"
                )
            )
        ).scalar_one()
        print(f"{BACKUP_TABLE}: {banked} rows, {restorable} still carrying the repair")
        if not banked:
            print(
                "REFUSING: the backup table is empty, so there is nothing to "
                "restore and a silent success here would read as a completed undo."
            )
            return 2
        if banked and not restorable:
            print(
                "Nothing to do: every backed-up leg has since been re-bound by "
                "something else. Leaving them alone (see this file's header)."
            )
            return 0

        if not args.apply:
            print("plan only. Re-run with --apply.")
            return 0

        result = await s.execute(text(_RESTORE_SQL))
        await s.commit()
        print(f"restored: {result.rowcount} legs")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
