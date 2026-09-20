"""#7410 undo — put every side `repair_7410_promoted_clubs_absent_from_their_league.py` moved back.

One command, D51:

    heroku run:detached -a bainluck -- python3 scripts/restore_7410_promoted_clubs_absent_from_their_league.py --apply

Restores from `backup_7410_promoted_club_binding`, and only for sides that STILL
carry the value the repair wrote (`<side>_team_id = team_id_after`). A side
re-bound by something else between the repair and the undo — the ESPN sync at a
later kickoff, a rerun of the #1798 rail, another repair — keeps its newer
binding rather than being clobbered back to Manchester City's id. An undo that
overwrites work it did not do is not an undo.

🔴 THE MINTED CLUBS ARE NOT DELETED, AND THAT IS THE UNDO BEING HONEST.
The repair creates `Coventry City` and `Hull City` under `soccer_epl` from
ESPN's own directory. Those rows are CORRECT — both clubs were promoted and
play in that league — and the ESPN sync would have created them itself at the
11 October kickoff. Undoing the bindings is undoing a decision; deleting the
clubs would be destroying data that is independently right, and a team row can
have picked up other references (identity mappings, favourites, another event's
FK) in the interval. So the undo restores the ten bindings and leaves the two
clubs standing. If they must also go, that is a separate, by-name, attended
deletion — not something a one-command restore should do while nobody is
reading.

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

from scripts.repair_7410_promoted_clubs_absent_from_their_league import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)

#: One statement per side. The `side` column decides which FK moves, so the two
#: cannot be folded into one UPDATE — and a row whose `side` is neither is left
#: alone rather than silently matching nothing useful.
_RESTORE_SQL = {
    "home": f"""
        UPDATE events e
           SET home_team_id = b.team_id_before
          FROM {BACKUP_TABLE} b
         WHERE e.id = b.event_id
           AND b.side = 'home'
           AND e.home_team_id = b.team_id_after
    """,
    "away": f"""
        UPDATE events e
           SET away_team_id = b.team_id_before
          FROM {BACKUP_TABLE} b
         WHERE e.id = b.event_id
           AND b.side = 'away'
           AND e.away_team_id = b.team_id_after
    """,
}

_RESTORABLE_SQL = f"""
SELECT count(*) FROM {BACKUP_TABLE} b
  JOIN events e ON e.id = b.event_id
 WHERE (b.side = 'home' AND e.home_team_id = b.team_id_after)
    OR (b.side = 'away' AND e.away_team_id = b.team_id_after)
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
        restorable = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"{BACKUP_TABLE}: {banked} rows, {restorable} still carrying the repair")

        if not banked:
            print(
                "REFUSING: the backup table is empty, so there is nothing to "
                "restore and a silent success here would read as a completed undo."
            )
            return 2
        if not restorable:
            print(
                "Nothing to do: every backed-up side has since been re-bound by "
                "something else. Leaving them alone (see this file's header)."
            )
            return 0

        if not args.apply:
            print("plan only. Re-run with --apply.")
            return 0

        restored = 0
        for side in ("home", "away"):
            result = await s.execute(text(_RESTORE_SQL[side]))
            restored += result.rowcount
        await s.commit()

        # Read back rather than trusting rowcount (gotcha #53).
        left = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"restored: {restored} sides; still carrying the repair: {left}")
        return 0 if left == 0 else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
