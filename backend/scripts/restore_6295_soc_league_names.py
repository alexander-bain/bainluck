"""#6295 — the D51(b) undo for `repair_6295_soc_league_names.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command, and the permission is conditional on it working:

    heroku run:detached -a bainluck-heavy -- \
        python3 scripts/restore_6295_soc_league_names.py --apply

WHAT IT PUTS BACK. `events.home_team_name` and `events.away_team_name`, from
`backup_6295_event_names`, for every event the repair renamed. Those two columns
are the only thing the repair ever wrote: no market moved, no blend was touched,
nothing was deleted, so there is no ordering problem and no FK to satisfy.

WHAT IT WILL NOT DO. Overwrite a row that has been renamed AGAIN since. Each
restore is guarded on the current value being the one the repair wrote; anything
else is reported `DIVERGED` and left alone. An undo that stomps a later,
unrelated decision is not an undo.

Idempotent and re-runnable: the guard makes a second run a no-op, and a partial
restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

`backup_6295_event_names` is NOT Alembic-managed. `alembic revision
--autogenerate` will propose DROPping it — expected, and to be deleted from the
generated migration rather than accepted. Drop it deliberately with
`--drop-backups` once the repair is trusted and this undo is no longer wanted.
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

from repair_6295_soc_league_names import (  # noqa: E402
    BACKUP_TABLE,
    PRODUCER_APP,
    wrong_app_refusal,
)

__all__ = ["BACKUP_TABLE", "PRODUCER_APP", "main", "run"]


def _session_factory():
    """The app's real async session factory — see the repair script's copy.

    Behind a named function so a test can substitute it AND prove the real one
    resolves. The #2947 pair shipped importing `app.database`, a module that has
    never existed, so both the repair and its undo died on import while every
    unit test passed against a fake session (CERT-903). That is worse in an undo
    than in a repair: D51 permits an unattended production write BECAUSE a
    one-command undo exists, so an undo that cannot start retroactively removes
    the permission the repair was run under.
    """
    from app.services.database import async_session_maker

    return async_session_maker


async def run(args) -> int:
    from sqlalchemy import text

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    session_factory = _session_factory()

    async with session_factory() as session:
        exists = (
            await session.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{BACKUP_TABLE}"}
            )
        ).scalar_one()
        if not exists:
            print(f"{BACKUP_TABLE} does not exist — nothing to restore.")
            return 0

        if args.drop_backups:
            if not args.apply:
                print(f"DRY RUN — would DROP TABLE {BACKUP_TABLE}.")
                return 0
            await session.execute(text(f"DROP TABLE {BACKUP_TABLE}"))
            await session.commit()
            print(f"dropped {BACKUP_TABLE} — the #6295 repair is no longer undoable")
            return 0

        rows = (
            await session.execute(
                text(
                    "SELECT b.event_id, b.home_team_name, b.away_team_name, "
                    "       b.new_home_team_name, b.new_away_team_name, "
                    "       e.home_team_name, e.away_team_name "
                    f"FROM {BACKUP_TABLE} b JOIN events e ON e.id = b.event_id "
                    "ORDER BY b.event_id"
                )
            )
        ).all()

        already, diverged, todo = [], [], []
        for (
            event_id,
            old_home,
            old_away,
            new_home,
            new_away,
            now_home,
            now_away,
        ) in rows:
            if (now_home, now_away) == (old_home, old_away):
                already.append(event_id)
            elif (now_home, now_away) == (new_home, new_away):
                todo.append((event_id, old_home, old_away, now_home, now_away))
            else:
                diverged.append((event_id, now_home, now_away))

        print(f"backed up: {len(rows)}")
        print(f"  already at the pre-repair name : {len(already)}")
        print(f"  renamed again since, LEFT ALONE: {len(diverged)}")
        print(f"  TO RESTORE                     : {len(todo)}")
        for event_id, now_home, now_away in diverged:
            print(f"    DIVERGED {event_id}  now: {now_home} vs {now_away}")
        for event_id, old_home, old_away, now_home, now_away in todo:
            print(
                f"    {event_id}  {now_home} vs {now_away}"
                f"\n         -> {old_home} vs {old_away}"
            )

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --apply.")
            return 0

        written = 0
        for event_id, old_home, old_away, now_home, now_away in todo:
            result = await session.execute(
                text(
                    "UPDATE events SET home_team_name = :oh, away_team_name = :oa "
                    "WHERE id = :eid AND home_team_name = :nh AND away_team_name = :na"
                ),
                {
                    "eid": event_id,
                    "oh": old_home,
                    "oa": old_away,
                    "nh": now_home,
                    "na": now_away,
                },
            )
            written += result.rowcount or 0
        await session.commit()
        print(f"RESTORED: {written} events (planned {len(todo)})")
        return 0 if written == len(todo) else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    p.add_argument(
        "--drop-backups",
        action="store_true",
        help=f"DROP {BACKUP_TABLE} — makes the repair permanent and unundoable",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
