"""#8547 half 2 — the one-command undo for the MLB reschedule-ghost tags (D51).

Reads `bak_8547_mlb_reschedule_ghost_tags` and removes, from each ghost, the ONE
`provenance:duplicate-of:<canonical>` element the sweep appended (never writes a
banked array back — `event_tags` is shared, see the #5896 undo for why).

    python3 scripts/restore_8547_mlb_reschedule_ghost_tags.py            # dry run
    python3 scripts/restore_8547_mlb_reschedule_ghost_tags.py --apply

Heroku one-off (gotcha #48): no `cd backend`, never non-detached:

    heroku run:detached -a bainluck "python3 scripts/restore_8547_mlb_reschedule_ghost_tags.py --apply"

It does not drop the backup table, so the pair can be exercised more than once.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.tasks.mlb_reschedule_ghost_sweep import BAK_TABLE  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id,
       b.canonical_id,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS current_tags
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


async def remove_tags(session, plan):
    """Strip the sweep's tag from each ghost, one row per transaction."""
    from sqlalchemy import text

    written, failed = 0, []
    for row in plan:
        tag = duplicate_tag(row.canonical_id)
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET event_tags = event_tags - :tag "
                        "WHERE id = :eid "
                        "  AND COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)"
                    ),
                    {"tag": tag, "tag_array": json.dumps([tag]), "eid": row.event_id},
                )
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


def still_carrying(plan):
    return [r for r in plan if duplicate_tag(r.canonical_id) in (r.current_tags or "")]


async def run(*, apply: bool) -> int:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as session:
        try:
            plan = (await session.execute(text(_PLAN_SQL))).all()
        except Exception:
            await session.rollback()
            print(
                f"No backup table {BAK_TABLE} — the sweep has not written; nothing to undo."
            )
            return 0

        carrying = still_carrying(plan)
        print(
            json.dumps(
                {"banked": len(plan), "still_carrying_the_tag": len(carrying)}, indent=2
            )
        )
        for row in carrying[:20]:
            print(f"  event {row.event_id}: drop duplicate-of:{row.canonical_id}")
        if not carrying:
            print("Nothing to undo — no banked row still carries the tag.")
            return 0
        if not apply:
            print(
                f"DRY RUN — nothing written. {len(carrying)} row(s) would be listed again."
            )
            return 0

        written, failed = await remove_tags(session, carrying)
        remaining = [
            r.event_id
            for r in still_carrying((await session.execute(text(_PLAN_SQL))).all())
        ]
        print(f"COMMITTED: {written} tag(s) removed.")
        if failed or remaining:
            print(
                f"UNDO INCOMPLETE — failed={failed[:20]} still_tagged={remaining[:20]}"
            )
            return 1
        print(f"#8547 undone — {written} row(s) listed again.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the undo")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
