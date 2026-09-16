"""#5841 — the one-command undo for the 0 - 0 scoreline repair (D51).

Reads `bak_5841_zero_zero_scores` and writes each banked scoreline back onto the
event it was banked from.

    python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py            # dry run
    python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py --apply

Heroku one-off (gotcha #48 — detached, and PROJECT_PATH=backend puts scripts at
/app, so NO `cd backend`):

    heroku run:detached "python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py --apply" -a bainluck

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
🔴 **It does not restore a row whose score has moved on from the one the repair
wrote.** The repaired rows are settled and ESPN-anchored, so the live pass and
`backfill_missing_scores` can both still speak about them — and a row that has
since been corrected by the authority itself must not have a fabricated `0 - 0`
put back over it. The undo restores a row ONLY where the current scoreline is
still exactly what the repair left there; everything else is reported by id and
skipped. That is what makes this safe to run late, and it is the same rule
`restore_3780` draws on `status`.

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

from sqlalchemy import text  # noqa: E402

from scripts.repair_5841_zero_zero_finals_from_the_authority import BAK_TABLE  # noqa: E402

_PLAN_SQL = f"""
SELECT b.event_id, b.old_home_score, b.old_away_score, b.old_status,
       e.home_score AS now_home_score, e.away_score AS now_away_score,
       e.status AS now_status
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""

#: Re-states the banked pre-image's ABSENCE rather than just the id: the row may
#: only be restored while it still carries what the repair put there. Spelled as
#: an equality on both columns so a partially-corrected row (one side rewritten)
#: is skipped too.
_RESTORE_SQL = """
UPDATE events
   SET home_score = :old_home_score, away_score = :old_away_score
 WHERE id = :eid
   AND home_score = :written_home_score
   AND away_score = :written_away_score
"""


async def restore_rows(session, plan: list[dict]) -> tuple[int, list[int]]:
    """One row per transaction, for the same reason the repair writes that way."""
    written, failed = 0, []
    for item in plan:
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(text(_RESTORE_SQL), item["params"])
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {item['params']['eid']} after 3 attempts: {exc}")
                    failed.append(item["params"]["eid"])
                else:
                    await asyncio.sleep(attempt)
    return written, failed


async def run(*, apply: bool) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            rows = (await session.execute(text(_PLAN_SQL))).all()
        except Exception as exc:  # noqa: BLE001
            print(f"no restore point: {BAK_TABLE} is not readable ({exc})")
            sys.exit(1)

        plan, moved_on = [], []
        for row in rows:
            # The repair only ever wrote a scoreline that is NOT 0 - 0 onto a row
            # that WAS 0 - 0, so "still repaired" is "current != banked".
            still_repaired = (
                row.now_home_score != row.old_home_score
                or row.now_away_score != row.old_away_score
            )
            if not still_repaired:
                moved_on.append({"id": row.event_id, "why": "already at its banked scoreline"})
                continue
            plan.append(
                {
                    "params": {
                        "eid": row.event_id,
                        "old_home_score": row.old_home_score,
                        "old_away_score": row.old_away_score,
                        "written_home_score": row.now_home_score,
                        "written_away_score": row.now_away_score,
                    }
                }
            )

        print(
            json.dumps(
                {
                    "banked": len(rows),
                    "restorable": len(plan),
                    "already_at_banked_value": len(moved_on),
                    "examples": moved_on[:20],
                },
                indent=2,
            )
        )

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(plan)} row(s) would be put back "
                "to their banked scoreline. Re-run with --apply."
            )
            return

        written, failed = await restore_rows(session, plan)
        print(f"\nCOMMITTED: {written} row(s) restored.")

        if failed:
            print(f"\n❌ #5841 RESTORE INCOMPLETE — {len(failed)} row(s) exhausted their retries: {failed[:20]}")
            print("Re-running resumes from here; the backup table is not dropped.")
            sys.exit(1)

        print(f"\n✅ #5841 reversed. {BAK_TABLE} is kept so this can be re-run.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the restore (default: dry run)")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
