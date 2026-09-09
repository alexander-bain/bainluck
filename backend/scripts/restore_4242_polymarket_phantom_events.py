"""#4242 part (b) — the D51 undo for `repair_4242_polymarket_phantom_events.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and
ships a one-command restore may be applied UNATTENDED by the owning lane. This
file is that one command.

    heroku run:detached -a bainluck \
      "python3 scripts/restore_4242_polymarket_phantom_events.py --apply"

WHAT IT PUTS BACK, in FK-safe order (parents before children):

  1. `events` — re-inserts every row the repair deleted, with its original id.
     Ids are re-used, not re-allocated, so every child FK still resolves and the
     sequence is untouched (all of these ids sit far below `max(id)`).
  2. `events.commence_time` + `events.status` — restores the pre-repair values
     on the RE-DATED holders, which are updated rather than deleted. These are
     the only two columns the repair writes to `events`, and it writes them in
     one statement, so they are put back in one statement: restoring the date
     without the status would leave a state the repair never produced.
  3. `win_prob_snapshots`, `event_provider_anchors`, `line_movement_analyses` —
     re-inserts the deleted children. Two of the three went by CASCADE, which is
     precisely why the repair backed them up: nothing in its own text names
     them, so nothing but the backup can find them again. All three have FKs to
     `events`, which is why step 1 has to come first.
  4. `event_id` on the PRESERVED children — puts back the rows the repair MOVED
     rather than deleted.

WHAT WAS MOVED, AND WHY STEP 4 EXISTS (changed under CERT-2357's named repair
`4242-DELETE-ONLY-PROVEN-DERIVED-ROWS`). The repair no longer deletes every
derived-looking child. A phantom carrying real substance — a foreign
(non-polymarket) curve sample, or a `line_movement` analysis that is not the
regenerable taxonomy cache — has that substance RE-POINTED onto the surviving
canonical event of its matchup before the phantom is deleted.

Those rows are therefore still live after the repair, under a different
`event_id`, and an undo that only re-inserted deleted rows would leave them
attached to the survivor forever. Step 4 restores `event_id` from the backup for
every backed-up child row that still exists live with a different parent. It is
an equality-guarded UPDATE, so it is idempotent like the rest, and it runs after
step 1 because the original parent has to be back before a child can point at it
again.

No MARKET is ever moved: a holder keeps the markets it already had, so
`futures_markets` is untouched. No ANCHOR is ever moved either — that is the
#2871 rule and the repair refuses it by construction — so neither table has a
re-point to unwind.

Idempotent and re-runnable: every step is a `WHERE NOT EXISTS` / equality-guarded
write, so a partial restore followed by a full one converges.

`--apply` is required. Without it this prints exactly what it would put back.

The `bak_4242_*` tables are NOT Alembic-managed. `alembic revision
--autogenerate` will propose DROPping them — that is expected and must be
deleted from the generated migration, not accepted. Drop them deliberately with
`--drop-backups` once the repair is trusted and this undo is no longer wanted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_PREFIX = "bak_4242_"

# Restored parents-first: each of these has an FK to `events`, so `events` has
# to be back before any of them can be.
CHILD_TABLES = (
    "win_prob_snapshots",
    "event_provider_anchors",
    "line_movement_analyses",
)


# The two `events` columns the repair writes, put back in one statement. Named
# as a template so the guard suite can execute the SHIPPED text against a seeded
# row and prove the round-trip, rather than merely reading it.
#
# `IS DISTINCT FROM` on both arms and not `<>`: a NULL on either side makes `<>`
# evaluate to NULL rather than true, and the row is then silently skipped —
# which is the failure mode an undo can least afford. `commence_time` is NOT
# NULL today; writing the safe form anyway costs nothing and survives a schema
# that stops being sure.
RESTORE_EVENT_COLUMNS_SQL = """
UPDATE events e
SET commence_time = b.commence_time,
    status = b.status
FROM {bak} b
WHERE e.id = b.id
  AND (e.commence_time IS DISTINCT FROM b.commence_time
       OR e.status IS DISTINCT FROM b.status)
"""


# Step 4. `event_id` is the ONLY column the repair rewrites on a child row, so it
# is the only one put back. Guarded with `IS DISTINCT FROM` for the same reason
# the events restore is: a NULL on either side makes `<>` evaluate to NULL and
# the row is silently skipped, which is what an undo can least afford.
#
# The join is on `id`, not on `event_id` — after a re-point the two disagree by
# definition, and joining on the thing that changed would match nothing and
# report a clean zero (gotcha #53: a zero-yield undo step must not read as a
# successful one).
RESTORE_CHILD_PARENT_SQL = """
UPDATE {tbl} c
SET event_id = b.event_id
FROM {bak} b
WHERE c.id = b.id
  AND c.event_id IS DISTINCT FROM b.event_id
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
        raise RuntimeError(
            f"no shared columns between {live} and {bak} — refusing to restore")
    return ", ".join(f'"{c}"' for c in rows)


async def _count_missing(session, src, bak):
    """Backed-up rows absent from the live table — i.e. what this step puts back."""
    from sqlalchemy import text
    return (await session.execute(text(
        f"SELECT count(*) FROM {bak} b "
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

        print("=== #4242 restore — what would be put back ===")
        for t in tables:
            print(f"  {t:>24}: {await _count_missing(s, t, BAK_PREFIX + t):>7} "
                  f"rows re-inserted")

        redated = (await s.execute(text(f"""
            SELECT count(*) FROM {BAK_PREFIX}events b
            JOIN events e ON e.id = b.id
            WHERE e.commence_time IS DISTINCT FROM b.commence_time
               OR e.status IS DISTINCT FROM b.status
        """))).scalar() or 0
        print(f"  {'events date + status':>24}: {redated:>7} rows reverted")

        for t in CHILD_TABLES:
            moved = (await s.execute(text(f"""
                SELECT count(*) FROM {BAK_PREFIX}{t} b
                JOIN {t} c ON c.id = b.id
                WHERE c.event_id IS DISTINCT FROM b.event_id
            """))).scalar() or 0
            print(f"  {t + ' event_id':>24}: {moved:>7} re-points undone")

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

        # 2. the two columns the repair wrote, restored together — it writes them
        #    in one statement, so putting one back without the other would leave
        #    a state the repair never produced.
        n = (await s.execute(text(RESTORE_EVENT_COLUMNS_SQL.format(
            bak=BAK_PREFIX + "events")))).rowcount or 0
        await s.commit()
        print(f"reverted {n} commence_time / status writes")

        # 3. children, now that their parents are back. Two of the three were
        #    deleted by CASCADE and are nowhere in the repair's own text — the
        #    backup is the only record they existed.
        for t in CHILD_TABLES:
            cols = await _shared_columns(s, t, BAK_PREFIX + t)
            n = (await s.execute(text(f"""
                INSERT INTO {t} ({cols})
                SELECT {cols} FROM {BAK_PREFIX}{t} b
                WHERE NOT EXISTS (SELECT 1 FROM {t} s WHERE s.id = b.id)
            """))).rowcount or 0
            await s.commit()
            print(f"restored {n} {t}")

        # 4. the re-points. A PRESERVED child was moved, not deleted, so it is
        #    already live under the survivor's id and step 3 skipped it (its `id`
        #    exists). This is the step that puts it back on its own parent, and
        #    it runs last because step 1 has to have re-created that parent.
        for t in CHILD_TABLES:
            n = (await s.execute(text(RESTORE_CHILD_PARENT_SQL.format(
                tbl=t, bak=BAK_PREFIX + t)))).rowcount or 0
            await s.commit()
            print(f"un-re-pointed {n} {t}")

        if drop_backups:
            for t in tables:
                await s.execute(text(f"DROP TABLE IF EXISTS {BAK_PREFIX}{t}"))
            await s.commit()
            print("dropped all bak_4242_* tables")

        print("\n✅ restore complete.")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="actually restore")
    p.add_argument("--drop-backups", action="store_true",
                   help="DROP the bak_4242_* tables after restoring (or on their own)")
    a = p.parse_args()
    asyncio.run(run(a.apply, a.drop_backups))


if __name__ == "__main__":
    main()
