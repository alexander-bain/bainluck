"""#2878 — the one-command undo for the tennis twin ghost tags (D51).

Reads `bak_2878_twin_ghost_tags` and removes, from each ghost, the ONE
`provenance:duplicate-of:<canonical>` element the repair appended. Every ghost
goes straight back to printing its own card.

    python3 scripts/restore_2878_tennis_twin_ghosts.py            # dry run
    python3 scripts/restore_2878_tennis_twin_ghosts.py --apply

Heroku one-off (gotcha #48 — `PROJECT_PATH=backend` puts scripts at /app, so NO
`cd backend`):

    heroku run:detached -a bainluck "python3 scripts/restore_2878_tennis_twin_ghosts.py --apply"

SURGICAL REMOVAL, NOT A RESTORE OF THE WHOLE ARRAY
──────────────────────────────────────────────────
The banked `old_tags` are printed and checked, but they are NOT written back.
`event_tags` is a shared multi-valued column — the enrichment pass adds
`audience:*` and `narrative:*` elements, the registry adds `provenance:*` ones —
so writing a banked array back would silently delete every tag anyone else has
added since. Instead this removes exactly the element the repair added, with
jsonb `-`, and leaves the rest of the array untouched. An undo that causes its
own damage is not an undo.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the repair is idempotent precisely so the pair can be
exercised more than once.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.anchor_channel import duplicate_tag  # noqa: E402
from scripts.repair_2878_tennis_twin_ghosts import BAK_TABLE  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id,
       b.canonical_id,
       b.old_tags,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS current_tags
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


async def remove_tags(session, plan, *, progress_every: int = 25):
    """Strip the repair's tag from each ghost, ONE ROW PER TRANSACTION.

    Same rail as the repair: `events` is write-hot, so a batch UPDATE or a short
    `lock_timeout` rolls back on every row where a patient single-row write
    succeeds.

    Returns ``(written, failed_ids)``. An undo that silently leaves rows hidden
    is worse than one that fails loudly — the operator believes the cards are
    back and stops looking.
    """
    from sqlalchemy import text

    written, failed = 0, []
    for index, row in enumerate(plan, start=1):
        tag = duplicate_tag(row.canonical_id)
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET event_tags = event_tags - :tag "
                        "WHERE id = :eid "
                        "  AND COALESCE(event_tags, '[]'::jsonb) "
                        "      @> CAST(:tag_array AS jsonb)"
                    ),
                    {
                        "tag": tag,
                        "tag_array": json.dumps([tag]),
                        "eid": row.event_id,
                    },
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
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(plan)} processed, {written} untagged")
    return written, failed


async def run(*, apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as session:
        try:
            plan = (await session.execute(text(_PLAN_SQL))).all()
        except Exception:
            await session.rollback()
            print(
                f"No backup table {BAK_TABLE} — the repair has not run here, so "
                f"there is nothing to undo."
            )
            return

        carrying = [
            r for r in plan if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]
        print("\n=== #2878 undo ===")
        print(
            json.dumps(
                {
                    "banked": len(plan),
                    "still_carrying_the_tag": len(carrying),
                    "already_clear": len(plan) - len(carrying),
                },
                indent=2,
            )
        )
        for row in carrying[:20]:
            print(f"  event {row.event_id}: drop duplicate-of:{row.canonical_id}")
        if len(carrying) > 20:
            print(f"  … and {len(carrying) - 20} more")

        if not carrying:
            print("\nNothing to undo — no banked row still carries the tag.")
            return
        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(carrying)} row(s) would start "
                f"printing again. Re-run with --apply."
            )
            return

        written, failed = await remove_tags(session, carrying)
        after = (await session.execute(text(_PLAN_SQL))).all()
        remaining = [
            r.event_id
            for r in after
            if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]

        print(f"\nCOMMITTED: {written} tag(s) removed.")
        if failed or remaining:
            print("\n❌ #2878 UNDO INCOMPLETE — some rows are still hidden:")
            if failed:
                print(f"  - {len(failed)} exhausted their retries: {failed[:20]}")
            if remaining:
                print(f"  - {len(remaining)} still carry the tag: {remaining[:20]}")
            sys.exit(1)
        print(f"\n✅ #2878 undone — {written} row(s) print their own card again.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the undo")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
