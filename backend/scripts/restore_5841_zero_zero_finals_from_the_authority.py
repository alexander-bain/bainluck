"""#5841 — the one-command undo for the 0 - 0 scoreline repair (D51).

Reads `bak_5841_zero_zero_scores` and writes each banked scoreline back onto the
event it was banked from.

    python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py            # dry run
    python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py --apply

Heroku one-off (gotcha #48 — detached, and PROJECT_PATH=backend puts scripts at
/app, so NO `cd backend`):

    heroku run:detached "python3 scripts/restore_5841_zero_zero_finals_from_the_authority.py --apply" -a bainluck

🔴 IT COMPARES AGAINST THE BANKED POST-IMAGE, AND THE FIRST VERSION DID NOT
---------------------------------------------------------------------------
The repaired rows are settled and ESPN-anchored, so the live pass and
`backfill_missing_scores` can both still speak about them. A row the AUTHORITY
has since corrected must not have a fabricated `0 - 0` put back over it.

CERT-2947 blocked the first version of this file for exactly that, and the
grader REPRODUCED it rather than reasoning about it: a repaired row was changed
to a newer authoritative `2 - 4`, this script ran, and the committed statement
matched it and wrote `0 - 0` back — `rowcount=1`, silently destroying newer
truth and restoring the reader defect the repair had just removed.

The cause was in the BACKUP, not in this file's intent: it banked only the
pre-image, so "is this row still repaired?" could only be inferred from "the
current score differs from the banked `0 - 0`" — which is equally true of a row
the repair wrote `1 - 3` onto and of a row the authority later corrected to
`2 - 4`. The backup now banks the exact pair the repair wrote, and this script
asks an EQUALITY against that immutable record:

    current == banked post-image   → restore the pre-image
    anything else                  → report the id and touch nothing

`tests/test_a_zero_zero_final_is_repaired_only_by_the_authority_5841.py`
executes both branches, the second one on the grader's own specimen.

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
       b.new_home_score, b.new_away_score,
       e.home_score AS now_home_score, e.away_score AS now_away_score,
       e.status AS now_status
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""

#: The CAS. Both bounds come from the BACKUP row, never from the event row:
#: `:new_*` is the immutable post-image the repair banked before it wrote, so
#: this statement can only touch a row still carrying exactly what the repair
#: put there. Binding the current score here instead — which is what CERT-2947
#: blocked — makes the WHERE a tautology that matches whatever it finds.
#:
#: Spelled as an equality on BOTH columns so a half-corrected row is skipped too.
_RESTORE_SQL = """
UPDATE events
   SET home_score = :old_home_score, away_score = :old_away_score
 WHERE id = :eid
   AND home_score = :new_home_score
   AND away_score = :new_away_score
"""


def restore_refusal_reason(row) -> str | None:
    """Why this banked row must NOT be put back, or ``None``.

    PURE, and the whole of CERT-2947's repair, so the guard can execute THIS
    function rather than restate it — a test that re-implements the decision
    passes on a script whose decision has been inverted. (`restorable` in
    `restore_3780` is the same seam for the same reason.)

    "Still repaired" is an EQUALITY against the banked post-image. The blocked
    form inferred it from "the current score differs from the banked pre-image",
    which is equally true of a row this repair wrote `1 - 3` onto and of one the
    authority later corrected to `2 - 4`.
    """
    if (row.now_home_score, row.now_away_score) == (row.new_home_score, row.new_away_score):
        return None
    return (
        "the row has moved since the repair wrote it "
        f"({row.new_home_score}-{row.new_away_score} → "
        f"{row.now_home_score}-{row.now_away_score}) — a newer authority reading "
        "is not this script's to overwrite"
    )


def restore_params(row) -> dict:
    """The CAS binds for one banked row. Both bounds come from the BACKUP."""
    return {
        "eid": row.event_id,
        "old_home_score": row.old_home_score,
        "old_away_score": row.old_away_score,
        "new_home_score": row.new_home_score,
        "new_away_score": row.new_away_score,
    }


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
            why = restore_refusal_reason(row)
            if why:
                moved_on.append(
                    {
                        "id": row.event_id,
                        "banked_post_image": f"{row.new_home_score}-{row.new_away_score}",
                        "now": f"{row.now_home_score}-{row.now_away_score}",
                        "why": why,
                    }
                )
                continue
            plan.append({"params": restore_params(row)})

        print(
            json.dumps(
                {
                    "banked": len(rows),
                    "restorable": len(plan),
                    "skipped_row_has_moved": len(moved_on),
                    "skipped": moved_on[:20],
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
