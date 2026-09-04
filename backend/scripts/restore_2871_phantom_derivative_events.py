"""#2871 — the D51 undo for `repair_2871_phantom_derivative_events.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and
ships a one-command restore may be applied UNATTENDED by the owning lane. This
file is that one command.

    heroku run:detached -a bainluck \
      "python3 scripts/restore_2871_phantom_derivative_events.py --apply"

WHAT IT PUTS BACK, in FK-safe order (parents before children, moves last):

  1. `events`   — re-inserts every row the repair deleted, with its original id.
     Ids are re-used, not re-allocated, so every child FK still resolves and the
     sequence is untouched (all of these ids sit far below `max(id)`).
  2. `events.away_team_name` + `events.win_probability_sources` — restores the
     pre-repair values on the Branch B survivors, which are renamed rather than
     deleted. These are the only two columns the repair writes to `events`, and
     it writes them in one transaction, so they are put back in one statement:
     restoring the name without the blend would leave a state the repair never
     produced. The blend is exact JSONB, not a re-derivation.
  3. `win_prob_snapshots`, `event_provider_anchors`, `line_movement_analyses` —
     re-inserts the deleted children. These have FKs to `events`, which is why
     step 1 has to come first.
  4. `futures_markets.event_id` — moves each market back to the event it came
     from, read off the `bak_2871_market_repoint` write-ahead ledger. Guarded on
     `event_id = new_event_id`: a market the matcher has since moved somewhere
     else on its own is LEFT ALONE rather than stomped. An undo that overwrites
     a later, unrelated decision is not an undo.

Idempotent and re-runnable: every step is a `WHERE NOT EXISTS` / equality-guarded
write, so a partial restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

NOT restored, deliberately: `futures_markets.updated_at`. The repair bumped it;
putting the old stamp back would misrepresent when the row was last written, and
nothing keys off it that the correct-but-late value breaks.

The `bak_2871_*` tables are NOT Alembic-managed. `alembic revision
--autogenerate` will propose DROPping them — that is expected and must be
deleted from the generated migration, not accepted. Drop them deliberately with
`--drop-backups` once the repair is trusted and this undo is no longer wanted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_PREFIX = "bak_2871_"

# Restored parents-first: each of these has an FK to `events`, so `events` has
# to be back before any of them can be.
CHILD_TABLES = (
    "win_prob_snapshots",
    "event_provider_anchors",
    "line_movement_analyses",
)


# The two `events` columns the repair writes, put back in one statement. Named
# as a template so the guard suite can execute the SHIPPED text against a
# seeded row and prove the JSON round-trips byte-for-byte, rather than merely
# reading it (CERT-880's second required test).
#
# `IS DISTINCT FROM` and not `<>`: the repair sets `win_probability_sources` to
# NULL, and `NULL <> '{"polymarket": ...}'` is NULL, not true — a `<>` here
# would silently restore nothing at all, which is the failure mode an undo can
# least afford.
RESTORE_EVENT_COLUMNS_SQL = """
UPDATE events e
SET away_team_name = b.away_team_name,
    win_probability_sources = b.win_probability_sources
FROM {bak} b
WHERE e.id = b.id
  AND (e.away_team_name <> b.away_team_name
       OR e.win_probability_sources IS DISTINCT FROM b.win_probability_sources)
"""


async def _exists(session, table):
    from sqlalchemy import text
    return bool((await session.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}
    )).scalar())


async def _shared_columns(session, live, bak):
    """Columns present in BOTH the live table and its backup, live order.

    `INSERT INTO events SELECT b.*` is positional, so it breaks the moment a
    migration adds a column to `events` after the backup was taken — which is
    exactly the situation an undo run days later is in. Naming the intersection
    keeps the restore working across a schema change, and any column added since
    the backup simply takes its default.
    """
    from sqlalchemy import text
    rows = (await session.execute(text("""
        SELECT a.column_name FROM information_schema.columns a
        WHERE a.table_name = :live
          AND EXISTS (SELECT 1 FROM information_schema.columns b
                      WHERE b.table_name = :bak AND b.column_name = a.column_name)
        ORDER BY a.ordinal_position
    """), {"live": live, "bak": bak})).scalars().all()
    if not rows:
        raise RuntimeError(f"no shared columns between {live} and {bak} — refusing to restore")
    return ", ".join(f'"{c}"' for c in rows)


async def _count_missing(session, src, bak):
    """Backed-up rows that are absent from the live table — i.e. what step N would put back."""
    from sqlalchemy import text
    return (await session.execute(text(
        f"SELECT COUNT(*) FROM {bak} b "
        f"WHERE NOT EXISTS (SELECT 1 FROM {src} s WHERE s.id = b.id)"
    ))).scalar() or 0


async def run(apply, drop_backups):
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        tables = ["events", *CHILD_TABLES]
        missing_bak = [t for t in tables if not await _exists(s, BAK_PREFIX + t)]
        if missing_bak:
            print(f"❌ no backup to restore from — missing "
                  f"{', '.join(BAK_PREFIX + t for t in missing_bak)}. "
                  f"Nothing to do (and nothing was done).")
            return

        print("=== #2871 restore — what would be put back ===")
        plan = {}
        for t in tables:
            plan[t] = await _count_missing(s, t, BAK_PREFIX + t)
            print(f"  {t:>24}: {plan[t]:>7} rows re-inserted")

        renamed = (await s.execute(text(f"""
            SELECT COUNT(*) FROM {BAK_PREFIX}events b
            JOIN events e ON e.id = b.id
            WHERE e.away_team_name <> b.away_team_name
               OR e.win_probability_sources IS DISTINCT FROM b.win_probability_sources
        """))).scalar() or 0
        print(f"  {'events name + blend':>24}: {renamed:>7} rows reverted")

        repoint = 0
        if await _exists(s, BAK_PREFIX + "market_repoint"):
            repoint = (await s.execute(text(f"""
                SELECT COUNT(*) FROM {BAK_PREFIX}market_repoint r
                JOIN futures_markets f ON f.id = r.market_id
                WHERE f.event_id = r.new_event_id AND r.old_event_id <> r.new_event_id
            """))).scalar() or 0
        print(f"  {'futures_markets.event_id':>24}: {repoint:>7} markets moved back")

        if not apply:
            print("\nDRY-RUN — no writes. Pass --apply to restore.")
            return

        # 1. events, with their original ids.
        cols = await _shared_columns(s, "events", BAK_PREFIX + "events")
        n = (await s.execute(text(f"""
            INSERT INTO events ({cols})
            SELECT {cols} FROM {BAK_PREFIX}events b
            WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.id = b.id)
        """))).rowcount or 0
        await s.commit()
        print(f"\nrestored {n} events")

        # 2. the two columns the repair wrote, restored together — the rename
        #    and the blend clear are applied in one transaction, so putting one
        #    back without the other would leave a state the repair never
        #    produced.
        n = (await s.execute(text(RESTORE_EVENT_COLUMNS_SQL.format(
            bak=BAK_PREFIX + "events")))).rowcount or 0
        await s.commit()
        print(f"reverted {n} away_team_name / win_probability_sources writes")

        # 3. children, now that their parents are back.
        for t in CHILD_TABLES:
            cols = await _shared_columns(s, t, BAK_PREFIX + t)
            n = (await s.execute(text(f"""
                INSERT INTO {t} ({cols})
                SELECT {cols} FROM {BAK_PREFIX}{t} b
                WHERE NOT EXISTS (SELECT 1 FROM {t} s WHERE s.id = b.id)
            """))).rowcount or 0
            await s.commit()
            print(f"restored {n} {t}")

        # 4. markets back where they came from — but only the ones still sitting
        #    where the repair put them.
        if await _exists(s, BAK_PREFIX + "market_repoint"):
            n = (await s.execute(text(f"""
                UPDATE futures_markets f SET event_id = r.old_event_id, updated_at = NOW()
                FROM {BAK_PREFIX}market_repoint r
                WHERE f.id = r.market_id
                  AND f.event_id = r.new_event_id
                  AND r.old_event_id <> r.new_event_id
            """))).rowcount or 0
            await s.commit()
            print(f"moved {n} futures_markets back")

        if drop_backups:
            for t in [*tables, "market_repoint"]:
                await s.execute(text(f"DROP TABLE IF EXISTS {BAK_PREFIX}{t}"))
            await s.commit()
            print("dropped all bak_2871_* tables")

        print("\n✅ restore complete.")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="actually restore")
    p.add_argument("--drop-backups", action="store_true",
                   help="DROP the bak_2871_* tables after restoring (or on their own)")
    a = p.parse_args()
    asyncio.run(run(a.apply, a.drop_backups))


if __name__ == "__main__":
    main()
