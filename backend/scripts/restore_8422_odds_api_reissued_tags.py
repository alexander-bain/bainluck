"""#8422 — the undo for the Odds API re-issued-id tags (D51).

Reads `bak_8422_odds_api_reissued_tags` and removes, from each ghost row, the
ONE `provenance:duplicate-of:<canonical>` element the sweep appended — with
jsonb `-`, never by writing the banked array back (`event_tags` is shared; a
whole-array restore would delete every tag anyone added since).

🔴 RUNNING THIS ALONE IS NOT A ROLLBACK (#6786). The sweep runs `apply=True` at
:51 every hour and selects on the ABSENCE of the tag, so it would re-tag within
the hour. The sequence, on the app whose worker runs the `background` queue:

    1. heroku config:set REISSUED_TWIN_SWEEP_DISABLED=1 -a <app>
    2. after the next :51, /api/admin/celery/task-metrics/odds_api_reissued_twin_sweep
       must read `terminal: skipped` naming REISSUED_TWIN_SWEEP_DISABLED
    3. python3 scripts/restore_8422_odds_api_reissued_tags.py --apply
    4. heroku config:unset REISSUED_TWIN_SWEEP_DISABLED -a <app>   (to resume)

    python3 scripts/restore_8422_odds_api_reissued_tags.py                 # dry run
    python3 scripts/restore_8422_odds_api_reissued_tags.py --only 15313977 --apply

`--only` clears named rows and leaves every other banked row alone. An id with
no banked row ABORTS (exit 2) rather than narrowing the scope to nothing.
Exit 1 = the undo ran and some rows still carry the tag. The backup table is
never dropped.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.tasks.odds_api_reissued_twin_sweep import BAK_TABLE, lift_tags  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id, b.canonical_id,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS current_tags
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""


def parse_only(values) -> list[int] | None:
    if not values:
        return None
    ids = []
    for chunk in values:
        for part in chunk.split(","):
            if part.strip():
                ids.append(int(part.strip()))
    if not ids:
        raise ValueError("--only named no event ids")
    return sorted(set(ids))


def carrying(rows) -> list:
    return [r for r in rows if duplicate_tag(r.canonical_id) in (r.current_tags or "")]


async def run(*, apply: bool, only: list[int] | None) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        exists = (
            await session.execute(text("SELECT to_regclass(:t)"), {"t": BAK_TABLE})
        ).scalar()
        if not exists:
            if only is not None:
                print(f"❌ ABORTED — {BAK_TABLE} does not exist; none of {only} is banked.")
                return 2
            print(f"No {BAK_TABLE} — the sweep has never written, nothing to undo.")
            return 0

        plan = (await session.execute(text(_PLAN_SQL))).all()
        if only is not None:
            banked_ids = {r.event_id for r in plan}
            unknown = [i for i in only if i not in banked_ids]
            if unknown:
                print(f"❌ ABORTED — not banked by this sweep: {unknown[:20]}. Nothing written.")
                return 2
            plan = [r for r in plan if r.event_id in set(only)]

        todo = carrying(plan)
        print(json.dumps({"in_scope": len(plan), "still_tagged": len(todo)}, indent=2))
        for row in todo[:20]:
            print(f"  event {row.event_id}: drop duplicate-of:{row.canonical_id}")
        if not todo:
            print("Nothing to undo.")
            return 0
        if not apply:
            print(f"DRY RUN — {len(todo)} row(s) would be un-tagged. Re-run with --apply.")
            return 0

        lifted, failed = await lift_tags(session, {r.event_id: r.canonical_id for r in todo})
        scope = {r.event_id for r in todo}
        remaining = [
            r.event_id
            for r in carrying((await session.execute(text(_PLAN_SQL))).all())
            if r.event_id in scope
        ]
        print(f"COMMITTED: {lifted} tag(s) removed.")
        if failed or remaining:
            print(f"❌ UNDO INCOMPLETE — failed {failed[:20]}, still tagged {remaining[:20]}")
            return 1
        print(f"✅ #8422 undone for {lifted} row(s).")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the undo")
    parser.add_argument("--only", action="append", metavar="IDS",
                        help="comma-separated banked event ids to clear; repeatable")
    args = parser.parse_args()
    try:
        only = parse_only(args.only)
    except ValueError as bad_only:
        parser.error(str(bad_only))
        raise SystemExit(2) from None
    raise SystemExit(asyncio.run(run(apply=args.apply, only=only)))


if __name__ == "__main__":
    main()
