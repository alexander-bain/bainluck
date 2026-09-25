"""#8730 undo — put every team `repair_8730_phantom_clubs_filed_under_mls_epl.py` moved back.

One command, D51:

    heroku run:detached -a bainluck -- python3 scripts/restore_8730_phantom_clubs_filed_under_mls_epl.py --apply

Restores from `backup_8730_team_league`, and only for teams that STILL carry the
league the repair wrote (`sport_id = sport_id_after`). A team moved again by
something else between the repair and the undo — a fold, an operator, a later
repair — keeps its newer league rather than being clobbered back to MLS or EPL.
An undo that overwrites work it did not do is not an undo.

`restore_verdict` is the per-row rule; the UPDATE carries the same condition in
its WHERE, so the rule and the write cannot disagree about a row.

The app gate is IMPORTED from the repair rather than copied: a restore is a
production write in the opposite direction and earns the identical refusal.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_8730_phantom_clubs_filed_under_mls_epl import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)

RESTORE = "restore"
NO_OP = "no_op"
DIVERGED = "diverged"


def restore_verdict(bank_row: dict, live_sport_id) -> str:
    """What the undo does to one banked team. Pure.

    ``restore`` only when the live league is exactly the one the repair wrote;
    ``no_op`` when it already holds the pre-image (never written, or restored);
    ``diverged`` for anything else — including a team that no longer exists —
    which is left alone.
    """
    if live_sport_id is None:
        return DIVERGED
    if live_sport_id == bank_row["sport_id_after"]:
        return RESTORE
    if live_sport_id == bank_row["sport_id_before"]:
        return NO_OP
    return DIVERGED


_RESTORE_SQL = f"""
    UPDATE teams t
       SET sport_id = b.sport_id_before
      FROM {BACKUP_TABLE} b
     WHERE t.id = b.team_id
       AND t.sport_id = b.sport_id_after
"""

_RESTORABLE_SQL = f"""
SELECT count(*) FROM {BACKUP_TABLE} b
  JOIN teams t ON t.id = b.team_id AND t.sport_id = b.sport_id_after
"""


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        exists = (
            await s.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": BACKUP_TABLE})
        ).scalar_one()
        if not exists:
            print(f"REFUSING: {BACKUP_TABLE} does not exist, so there is nothing to restore.")
            return 2
        banked = (
            await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))
        ).scalar_one()
        restorable = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"{BACKUP_TABLE}: {banked} rows, {restorable} still carrying the repair")

        if not banked:
            print(
                "REFUSING: the backup table is empty, so a silent success here "
                "would read as a completed undo."
            )
            return 2
        if not restorable:
            print("Nothing to do: no banked team still carries the league the repair wrote.")
            return 0
        if not args.apply:
            print("plan only. Re-run with --apply.")
            return 0

        restored = (await s.execute(text(_RESTORE_SQL))).rowcount
        await s.commit()

        # Read back rather than trusting rowcount (gotcha #53).
        left = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"restored: {restored} teams; still carrying the repair: {left}")
        return 0 if left == 0 else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
