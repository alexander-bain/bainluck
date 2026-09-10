"""#4586 — the one-command undo for `repair_4586_stranded_voided_event_markets.py` (D51).

Puts `futures_markets.event_id` back to the value the backup table recorded, for
every row the repair moved. Nothing else is touched: the repair writes exactly
one column, so the restore reads exactly one column back.

    python3 scripts/restore_4586_stranded_voided_event_markets.py            # plan only
    python3 scripts/restore_4586_stranded_voided_event_markets.py --apply    # undo

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_4586_stranded_voided_event_markets.py --apply"

SCOPED TO ROWS THAT ACTUALLY MOVED. The `IS DISTINCT FROM` clause means a row
whose live `event_id` already equals its backup value is not rewritten, so this
is idempotent and a partial `--limit` run restores only its own half.

THE RECEIPTS ARE NOT ROLLED BACK, DELIBERATELY. `market_link_changes` is an
append-only history of what happened, and the repair moving a link and the
restore moving it back are two things that happened. Deleting the first would
make the table lie about the past in order to make the present look tidy — the
exact property LINKLOSS-03 exists to prevent. A restore appends its own rows on
the next matcher pass; it does not edit history.

Leaves the backup table in place: a restore that destroys the only copy of the
pre-repair state cannot be run twice, and the second run is the one you need
when the first was interrupted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_4586_futures_markets"

_PLAN_SQL = f"""
SELECT f.id, f.event_id AS current_event_id, b.event_id AS backup_event_id
  FROM futures_markets f
  JOIN {BAK_TABLE} b ON b.id = f.id
 WHERE f.event_id IS DISTINCT FROM b.event_id
 ORDER BY f.id
"""

_RESTORE_SQL = f"""
UPDATE futures_markets f
   SET event_id = b.event_id, updated_at = NOW()
  FROM {BAK_TABLE} b
 WHERE b.id = f.id
   AND f.event_id IS DISTINCT FROM b.event_id
"""

_TABLE_EXISTS_SQL = "SELECT to_regclass(:t) IS NOT NULL"


async def run(apply: bool) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        exists = (
            await s.execute(text(_TABLE_EXISTS_SQL), {"t": BAK_TABLE})
        ).scalar_one()
        if not exists:
            # Absence is not "nothing to do" — it is "this cannot be answered"
            # (gotcha #53). Saying so is the whole point.
            print(f"❌ {BAK_TABLE} does not exist — the repair never ran its "
                  f"--backup, so there is nothing to restore FROM. This is not "
                  f"a clean no-op; investigate before assuming the data is fine.")
            return

        rows = (await s.execute(text(_PLAN_SQL))).all()
        print(f"=== #4586 restore plan: {len(rows)} rows differ from the backup ===")
        for r in rows:
            print(f"  market {r.id}: {r.current_event_id} → {r.backup_event_id}")

        if not rows:
            print("\nNothing to restore — every backed-up row already matches "
                  "its backup value (idempotent no-op).")
            return

        if not apply:
            print("\nDRY-RUN — no writes. Pass --apply to put these back.")
            return

        n = (await s.execute(text(_RESTORE_SQL))).rowcount or 0
        await s.commit()
        print(f"\nCOMMITTED: restored {n} markets to their pre-repair event_id.")

        left = (await s.execute(text(_PLAN_SQL))).all()
        print(f"POST-RESTORE: {len(left)} rows still differ (target: 0).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="commit the restore")
    asyncio.run(run(p.parse_args().apply))
