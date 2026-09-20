"""#7501 undo — take back every slug the fill wrote.

One command, D51:

    heroku run:detached -a bainluck -- python3 scripts/restore_7501_clubs_without_a_slug_have_no_page.py --apply

Restores from ``backup_7501_team_slug_fill``, and only for clubs that STILL
carry the value the fill wrote (``teams.slug = b.slug_after``). A club re-slugged
by something else in the interval keeps its newer slug rather than being
clobbered back to NULL; an undo that overwrites work it did not do is not an
undo.

🔴 THIS REVERSES THE SHIP, WHICH IS THE POINT AND ALSO THE WARNING.
Every row it touches goes back to having NO team page — that is precisely the
state #7501 exists to end. It is here because D51(b) requires a one-command way
back from an unattended production write, not because there is a plausible
reason to want it. If a *particular* club got a wrong-looking slug, fix that
club; do not run this.

It also covers the beat. ``backfill-team-slugs`` writes into the same bank
whenever the table exists (created by the repair script's ``--backup``), so once
a person has run that step the undo reaches the beat's rows too. Rows the beat
wrote BEFORE the bank existed are not in it and are not reversible here — the
repair script's header says so, and the counts printed below say which case you
are in.

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

from app.tasks.team_slug_backfill import BANK_TABLE  # noqa: E402
from scripts.repair_7501_clubs_without_a_slug_have_no_page import (  # noqa: E402
    wrong_app_refusal,
)

_RESTORE_SQL = f"""
UPDATE teams t
   SET slug = NULL
  FROM {BANK_TABLE} b
 WHERE t.id = b.team_id
   AND t.slug = b.slug_after
"""

_RESTORABLE_SQL = f"""
SELECT count(*) FROM {BANK_TABLE} b
  JOIN teams t ON t.id = b.team_id
 WHERE t.slug = b.slug_after
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
            await s.execute(text(f"SELECT to_regclass('{BANK_TABLE}')"))
        ).scalar_one()
        if exists is None:
            print(
                f"REFUSING: {BANK_TABLE} does not exist, so nothing was ever "
                "banked and a silent success here would read as a completed "
                "undo. Run the repair's --backup step before its --apply."
            )
            return 2

        banked = (
            await s.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
        ).scalar_one()
        restorable = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"{BANK_TABLE}: {banked} rows, {restorable} still carrying the fill")

        if not banked:
            print(
                "REFUSING: the bank is empty. Either the fill never ran, or it "
                "ran before --backup created the table — in which case its rows "
                "are not recorded anywhere and this script cannot reach them."
            )
            return 2
        if not restorable:
            print(
                "Nothing to do: no banked club still carries the slug the fill "
                "wrote. They were re-slugged by something else, or already "
                "restored. Leaving them alone (see this file's header)."
            )
            return 0

        if not args.apply:
            print("plan only. Re-run with --apply.")
            return 0

        result = await s.execute(text(_RESTORE_SQL))
        await s.commit()

        # Read back rather than trusting rowcount (hot-list #53).
        left = (await s.execute(text(_RESTORABLE_SQL))).scalar_one()
        print(f"restored: {result.rowcount} clubs; still carrying the fill: {left}")
        return 0 if left == 0 else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
