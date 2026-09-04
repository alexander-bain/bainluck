"""#3026 — the D51 undo for `repair_3026_question_events.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and
ships a one-command restore may be applied UNATTENDED by the owning lane. This
file is that one command.

    heroku run:detached -a bainluck \
      "python3 scripts/restore_3026_question_events.py --apply"

WHAT IT PUTS BACK, in the order the foreign keys require:

  1. the deleted `events` rows, re-inserted from `bak_3026_question_events`
     WITH THEIR ORIGINAL ids — every child below points at those ids;
  2. their CASCADE children, banked by table name before the row went:
     `event_provider_anchors`, `win_prob_snapshots`, `espn_snapshots`,
     `game_moments` — so the win-probability series comes back too, not just
     the row that carried it;
  3. their `line_movement_analyses`, which the repair deleted explicitly;
  4. `futures_markets.event_id` for all 104 unlinked markets, from
     `bak_3026_market_links`.

WHAT IT WILL NOT DO. Overwrite a row that has moved on since. A re-insert is
skipped when an event with that id already exists, and a market is only
re-linked when its `event_id` is still NULL; anything else is reported as
DIVERGED and left alone. An undo that stomps a later, unrelated decision is not
an undo.

WHY THE DRY RUN UNDER-REPORTS `relinked`, and why that is correct rather than a
bug. `restore_links` re-points a market only when the event it belongs to
exists. In a dry run the events have not been re-inserted yet, so every market
whose event is still deleted counts as `missing_event`. Under `--apply` the
inserts land first in the same session and those markets re-link. #2993's undo
behaves identically and was left alone for the same reason.

Idempotent and re-runnable: every guard makes a second run a no-op, and a
partial restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

The `bak_3026_*` tables are NOT Alembic-managed. `alembic revision
--autogenerate` will propose DROPping them — expected, and to be deleted from
the generated migration rather than accepted. Drop them deliberately with
`--drop-backups` once the repair is trusted and this undo is no longer wanted.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_EVENTS = "bak_3026_question_events"
BAK_LINKS = "bak_3026_market_links"

# Only these tables may be re-inserted from the banked `cascade_rows` object.
# The key comes out of a jsonb document, so it is checked against this tuple
# before it is ever interpolated into SQL.
RESTORABLE_CASCADE_TABLES = (
    "event_provider_anchors",
    "win_prob_snapshots",
    "espn_snapshots",
    "game_moments",
)


def _session_factory():
    """The app's real async session factory — see the repair script's copy.

    #2947's pair shipped importing `app.database`, a module that has never
    existed, so the one command D51 leans on could not have run (CERT-903).
    """
    from app.services.database import async_session_maker

    return async_session_maker


async def _table_exists(session, name):
    from sqlalchemy import text

    return bool(
        (
            await session.execute(text("SELECT to_regclass(:name)"), {"name": name})
        ).scalar()
    )


async def restore_events(session, apply):
    """Re-insert deleted events and every child that went with them."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                f"SELECT event_id, why, event_row, lma_rows, cascade_rows "
                f"FROM {BAK_EVENTS} ORDER BY event_id"
            )
        )
    ).all()

    report = {"reinserted": 0, "already_present": 0, "children_reinserted": 0}

    for event_id, _why, event_row, lma_rows, cascade_rows in rows:
        present = (
            await session.execute(
                text("SELECT 1 FROM events WHERE id = :eid"), {"eid": event_id}
            )
        ).scalar()
        if present:
            report["already_present"] += 1
            continue

        report["reinserted"] += 1
        children = list(("line_movement_analyses", child) for child in (lma_rows or []))
        for table in RESTORABLE_CASCADE_TABLES:
            for child in (cascade_rows or {}).get(table) or []:
                children.append((table, child))
        report["children_reinserted"] += len(children)

        if not apply:
            continue

        # jsonb_populate_record rebuilds the row from the banked snapshot, so
        # this survives columns being added to the table after the backup.
        await session.execute(
            text("INSERT INTO events SELECT (jsonb_populate_record(NULL::events, :row)).*"),
            {"row": event_row},
        )
        for table, child in children:
            await session.execute(
                text(
                    f"INSERT INTO {table} "
                    f"SELECT (jsonb_populate_record(NULL::{table}, :row)).* "
                    f"ON CONFLICT DO NOTHING"
                ),
                {"row": child},
            )

    return report


async def restore_links(session, apply):
    """Re-point the unlinked markets, but only those still unlinked."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(f"SELECT market_id, old_event_id FROM {BAK_LINKS} ORDER BY market_id")
        )
    ).all()

    report = {"relinked": 0, "diverged": 0, "missing_event": 0}
    for market_id, old_event_id in rows:
        current = (
            await session.execute(
                text("SELECT event_id FROM futures_markets WHERE id = :mid"),
                {"mid": market_id},
            )
        ).first()
        if current is None:
            report["diverged"] += 1
            continue
        if current[0] is not None:
            if current[0] != old_event_id:
                report["diverged"] += 1
                print(
                    f"  DIVERGED market {market_id}: now on event {current[0]}, "
                    f"not re-pointing to {old_event_id}"
                )
            continue
        exists = (
            await session.execute(
                text("SELECT 1 FROM events WHERE id = :eid"), {"eid": old_event_id}
            )
        ).scalar()
        if not exists:
            report["missing_event"] += 1
            continue
        if apply:
            await session.execute(
                text(
                    "UPDATE futures_markets SET event_id = :eid "
                    "WHERE id = :mid AND event_id IS NULL"
                ),
                {"eid": old_event_id, "mid": market_id},
            )
        report["relinked"] += 1
    return report


async def run(args):
    from sqlalchemy import text

    session_factory = _session_factory()
    async with session_factory() as session:
        for table in (BAK_EVENTS, BAK_LINKS):
            if not await _table_exists(session, table):
                print(f"NOTHING TO RESTORE: {table} does not exist")
                return 1

        if args.drop_backups:
            if not args.apply:
                print("--drop-backups needs --apply")
                return 2
            await session.execute(text(f"DROP TABLE {BAK_EVENTS}"))
            await session.execute(text(f"DROP TABLE {BAK_LINKS}"))
            await session.commit()
            print("DROPPED both backup tables")
            return 0

        events_report = await restore_events(session, args.apply)
        links_report = await restore_links(session, args.apply)
        if args.apply:
            await session.commit()

        print({"events": events_report, "markets": links_report})
        if not args.apply:
            print(
                "DRY RUN — nothing written. Re-run with --apply. "
                "`missing_event` counts markets whose event has not been "
                "re-inserted yet; under --apply they re-link."
            )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="write the restore")
    p.add_argument(
        "--drop-backups",
        action="store_true",
        help="drop the backup tables once the repair is trusted",
    )
    sys.exit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
