"""#2993 — the D51 undo for `repair_2993_bracket_events.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and
ships a one-command restore may be applied UNATTENDED by the owning lane. This
file is that one command.

    heroku run:detached -a bainluck \
      "python3 scripts/restore_2993_bracket_events.py --apply"

WHAT IT PUTS BACK, in the order the foreign keys require:

  1. the deleted `events` rows, re-inserted from `bak_2993_bracket_events`
     WITH THEIR ORIGINAL ids — every child below points at those ids;
  2. their `event_provider_anchors` and `line_movement_analyses` children,
     which went with them (one CASCADE, one deleted explicitly);
  3. the renamed row's two name columns;
  4. `futures_markets.event_id` for all 32 unlinked markets, from
     `bak_2993_market_links`.

WHAT IT WILL NOT DO. Overwrite a row that has moved on since. A re-insert is
skipped when an event with that id already exists, a rename is only undone when
the CURRENT names are the ones the repair wrote, and a market is only re-linked
when its `event_id` is still NULL. Anything else is reported as DIVERGED and
left alone — an undo that stomps a later, unrelated decision is not an undo.

Idempotent and re-runnable: every guard makes a second run a no-op, and a
partial restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

The `bak_2993_*` tables are NOT Alembic-managed. `alembic revision
--autogenerate` will propose DROPping them — expected, and to be deleted from
the generated migration rather than accepted. Drop them deliberately with
`--drop-backups` once the repair is trusted and this undo is no longer wanted.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_EVENTS = "bak_2993_bracket_events"
BAK_LINKS = "bak_2993_market_links"


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
            await session.execute(
                text("SELECT to_regclass(:name)"), {"name": name}
            )
        ).scalar()
    )


async def restore_events(session, apply):
    """Re-insert deleted events and their children, by original id."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                f"SELECT event_id, action, event_row, lma_rows, anchor_rows, applied_names "
                f"FROM {BAK_EVENTS} ORDER BY event_id"
            )
        )
    ).all()

    report = {"reinserted": 0, "already_present": 0, "renamed_back": 0, "diverged": 0}

    for event_id, action, event_row, lma_rows, anchor_rows, applied in rows:
        current = (
            await session.execute(
                text(
                    "SELECT home_team_name, away_team_name FROM events WHERE id = :eid"
                ),
                {"eid": event_id},
            )
        ).first()

        if action == "rename":
            # Only undo a rename that is still exactly as the repair left it.
            if current is None or not applied or list(current) != [
                applied.get("home"), applied.get("away")
            ]:
                report["diverged"] += 1
                print(
                    f"  DIVERGED {event_id}: names are {current}, "
                    f"repair left {applied} — not touching it"
                )
                continue
            if apply:
                await session.execute(
                    text(
                        "UPDATE events SET home_team_name = :h, away_team_name = :a "
                        "WHERE id = :eid"
                    ),
                    {
                        "eid": event_id,
                        "h": event_row["home_team_name"],
                        "a": event_row["away_team_name"],
                    },
                )
            report["renamed_back"] += 1
            continue

        present = current is not None

        if present:
            report["already_present"] += 1
            continue

        if not apply:
            report["reinserted"] += 1
            continue

        # jsonb_populate_record rebuilds the row from the banked snapshot, so
        # this survives columns being added to `events` after the backup.
        await session.execute(
            text(
                "INSERT INTO events SELECT (jsonb_populate_record(NULL::events, :row)).*"
            ),
            {"row": event_row},
        )
        for child_rows, table in ((anchor_rows, "event_provider_anchors"),
                                  (lma_rows, "line_movement_analyses")):
            for child in child_rows or []:
                await session.execute(
                    text(
                        f"INSERT INTO {table} "
                        f"SELECT (jsonb_populate_record(NULL::{table}, :row)).* "
                        f"ON CONFLICT DO NOTHING"
                    ),
                    {"row": child},
                )
        report["reinserted"] += 1

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
            print("DRY RUN — nothing written. Re-run with --apply.")
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
