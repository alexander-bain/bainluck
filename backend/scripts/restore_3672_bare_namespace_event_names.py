"""#3672 — the D51 undo for `repair_3672_bare_namespace_event_names.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and
ships a one-command restore may be applied UNATTENDED by the owning lane. This
file is that one command.

    heroku run:detached -a bainluck \
      "python3 scripts/restore_3672_bare_namespace_event_names.py --apply"

WHAT IT PUTS BACK. `events.home_team_name` and `events.away_team_name`, from
`bak_3672_event_names`, for every event the repair renamed. Those two columns
are the only thing the repair ever wrote: nothing was deleted, no market moved,
no blend was touched, so there is no ordering problem and no FK to satisfy.

WHAT IT WILL NOT DO. Overwrite a row that has been renamed again since. Each
restore is guarded on the CURRENT value being the one the repair wrote; if
something else has moved the name on, the row is reported as DIVERGED and left
alone. An undo that stomps a later, unrelated decision is not an undo.

Idempotent and re-runnable: the guard makes a second run a no-op, and a partial
restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

`bak_3672_event_names` is NOT Alembic-managed. `alembic revision --autogenerate`
will propose DROPping it — expected, and to be deleted from the generated
migration rather than accepted. Drop it deliberately with `--drop-backups` once
the repair is trusted and this undo is no longer wanted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_3672_event_names"


def _session_factory():
    """The app's real async session factory — see the repair script's copy.

    Behind a named function so a test can substitute it AND prove the real one
    resolves. The #2947 pair shipped importing `app.database`, a module that has
    never existed, so both the repair and its undo died on import while every
    unit test passed against a fake session (CERT-903). That is worse in an undo
    than in a repair: D51 permits an UNATTENDED production write *because* a
    one-command undo exists, so an undo that cannot start retroactively removes
    the permission the repair was run under. Hence the run-level test.
    """
    from app.services.database import async_session_maker

    return async_session_maker


async def run(args):
    from sqlalchemy import text

    session_factory = _session_factory()

    async with session_factory() as session:
        exists = (
            await session.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{BAK_TABLE}"}
            )
        ).scalar_one()
        if not exists:
            print(f"{BAK_TABLE} does not exist — nothing to restore.")
            return 0

        if args.drop_backups:
            if not args.apply:
                print(f"DRY RUN — would DROP TABLE {BAK_TABLE}.")
                return 0
            await session.execute(text(f"DROP TABLE {BAK_TABLE}"))
            await session.commit()
            print(f"dropped {BAK_TABLE} — the #3672 repair is no longer undoable")
            return 0

        rows = (
            await session.execute(
                text(
                    f"SELECT b.event_id, b.home_team_name, b.away_team_name, "
                    f"       b.new_home_team_name, b.new_away_team_name, "
                    f"       e.home_team_name, e.away_team_name "
                    f"FROM {BAK_TABLE} b JOIN events e ON e.id = b.event_id "
                    f"ORDER BY b.event_id"
                )
            )
        ).all()

        already, diverged, todo = [], [], []
        for event_id, old_home, old_away, new_home, new_away, now_home, now_away in rows:
            if (now_home, now_away) == (old_home, old_away):
                already.append(event_id)
            elif (now_home, now_away) == (new_home, new_away):
                todo.append((event_id, old_home, old_away, now_home, now_away))
            else:
                diverged.append((event_id, now_home, now_away))

        print(f"backed up: {len(rows)}")
        print(f"  already at the pre-repair name: {len(already)}")
        print(f"  renamed again since, LEFT ALONE: {len(diverged)}")
        print(f"  TO RESTORE                     : {len(todo)}")
        for event_id, now_home, now_away in diverged[:20]:
            print(f"    DIVERGED {event_id}  now: {now_home} vs {now_away}")
        for event_id, old_home, old_away, now_home, now_away in todo[:10]:
            print(f"    {event_id}  {now_home} vs {now_away}\n         -> {old_home} vs {old_away}")

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
        help=f"DROP {BAK_TABLE} — makes the repair permanent and unundoable",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
