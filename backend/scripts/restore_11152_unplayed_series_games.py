"""#11152 — the one-command undo for retired unplayed series games (D51).

Reads `bak_11152_unplayed_series_games` and, for each banked row that is STILL
`voided` and still carries the sweep's
`provenance:unplayed-series-game:espn:<id>` element, puts the banked status back
and removes that one element (never writes a banked tag array back —
`event_tags` is shared). A row anything else has changed since is left alone.

    python3 scripts/restore_11152_unplayed_series_games.py            # dry run
    python3 scripts/restore_11152_unplayed_series_games.py --apply

Heroku one-off (gotcha #48): no `cd backend`, never non-detached:

    heroku run:detached -a bainluck "python3 scripts/restore_11152_unplayed_series_games.py --apply"

It does not drop the backup table, so the pair can be exercised more than once.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.unplayed_series_game_sweep import BAK_TABLE  # noqa: E402
from app.utils.unplayed_series_games import retirement_tag  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id,
       b.clinching_espn_id,
       b.old_status,
       e.status AS current_status,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS current_tags
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""

_RESTORE_SQL = """
UPDATE events
   SET status = :old_status,
       event_tags = event_tags - :tag
 WHERE id = :eid
   AND status = 'voided'
   AND COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)
"""


def still_retired(plan):
    return [
        r
        for r in plan
        if r.current_status == "voided"
        and retirement_tag(r.clinching_espn_id) in (r.current_tags or "")
    ]


async def restore_rows(session, rows):
    """Put each row back, one row per transaction."""
    from sqlalchemy import text

    written, failed = 0, []
    for row in rows:
        tag = retirement_tag(row.clinching_espn_id)
        params = {
            "old_status": row.old_status,
            "tag": tag,
            "tag_array": json.dumps([tag]),
            "eid": row.event_id,
        }
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(text(_RESTORE_SQL), params)
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {row.event_id} after 3 attempts: {exc}")
                    failed.append(row.event_id)
                else:
                    await asyncio.sleep(attempt)
    return written, failed


async def run(*, apply: bool) -> int:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as session:
        try:
            plan = (await session.execute(text(_PLAN_SQL))).all()
        except Exception:
            await session.rollback()
            print(f"No backup table {BAK_TABLE} — nothing was retired; nothing to undo.")
            return 0

        retired = still_retired(plan)
        print(json.dumps({"banked": len(plan), "still_retired": len(retired)}, indent=2))
        for row in retired[:20]:
            print(f"  event {row.event_id}: voided -> {row.old_status}")
        if not retired:
            print("Nothing to undo — no banked row is still retired by this sweep.")
            return 0
        if not apply:
            print(f"DRY RUN — nothing written. {len(retired)} row(s) would be listed again.")
            return 0

        written, failed = await restore_rows(session, retired)
        remaining = [
            r.event_id for r in still_retired((await session.execute(text(_PLAN_SQL))).all())
        ]
        print(f"COMMITTED: {written} row(s) restored.")
        if failed or remaining:
            print(f"UNDO INCOMPLETE — failed={failed[:20]} still_retired={remaining[:20]}")
            return 1
        print(f"#11152 undone — {written} row(s) listed again.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the undo")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
