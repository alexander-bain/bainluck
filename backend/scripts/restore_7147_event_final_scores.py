"""#7147 — the one-command undo for the CAL-P002 settled-final-score repair (D51).

Reads `bak_7147_event_final_scores` and writes each banked `old_home_score`,
`old_away_score`, `old_completed_at` AND `old_win_probability_sources` back onto
the event they were banked from. All four columns, because the repair writes all
four: an undo that restored the score and left the blend graded off the repaired
one would leave the row in a state neither the repair nor production ever
produced (the #3780 lesson, same table, same argument).

    python3 scripts/restore_7147_event_final_scores.py            # dry run
    python3 scripts/restore_7147_event_final_scores.py --apply

Heroku one-off (gotcha #48 — non-detached returns empty stdout that reads like
success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_7147_event_final_scores.py --apply"

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
🔴 It does not restore a row whose score has moved on from the one the repair
wrote. This is the CERT-2439 lesson and on THIS cohort it is not theoretical:
the whole population is rows ESPN can adjudicate, and ESPN correcting its own
final again — a scoring change, a protest, a resumed game — is the outcome the
repair exists to let through. An undo keyed on "the live row differs from its
backup" would systematically revert the authority's newer, better score back to
the frozen mid-game number this repair removed. So the compare-and-swap is on
`new_home_score`/`new_away_score` — what WE wrote — not on difference. Rows that
moved on are reported by id and skipped.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the repair is idempotent precisely so the pair can be
exercised more than once.

🔴 `completed_at` IS BOUND AS A DATETIME AND THE BLEND AS JSON, NEVER AS
STRINGS. asyncpg refuses a `str` bound to `timestamptz`, and a dict bound to
`jsonb` needs the same care every other restore in this directory takes
(`tests/test_restore_jsonb_bind_contract.py` is the standing guard for the
second half). Both values come back off the backup table in the right type and
are passed straight through; nothing here formats either.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_event_final_scores import BAK_TABLE  # noqa: E402

#: The banked row beside the live one, so `restorable` can compare what we wrote
#: against what the row holds NOW. Both halves come from the plan — the restore
#: never re-reads the event during the write, because a second read is a second
#: moment and the compare-and-swap in `_RESTORE_SQL` is what closes that race
#: for real.
_PLAN_SQL = f"""
SELECT b.event_id,
       b.old_home_score,
       b.old_away_score,
       b.old_completed_at,
       b.old_win_probability_sources,
       b.new_home_score,
       b.new_away_score,
       e.home_score AS current_home_score,
       e.away_score AS current_away_score
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""

#: The write, and it is a compare-and-swap on the score the repair wrote. The
#: WHERE is the safety: if anything re-scored the row between the plan and the
#: write — which on this cohort means ESPN corrected itself again — the
#: statement no-ops instead of reverting a fresher, better final.
_RESTORE_SQL = """
UPDATE events
   SET home_score = :old_home_score,
       away_score = :old_away_score,
       completed_at = :old_completed_at,
       win_probability_sources = :old_win_probability_sources
 WHERE id = :event_id
   AND home_score IS NOT DISTINCT FROM :new_home_score
   AND away_score IS NOT DISTINCT FROM :new_away_score
"""


def restorable(row) -> bool:
    """Is this row still the one the repair left behind?

    Pure. True only when the live score is still EXACTLY the score the repair
    wrote. Anything else is newer information than the backup, and newer
    information wins — see the docstring's CERT-2439 note.

    `IS NOT DISTINCT FROM` in the statement and `==` here agree on NULL because
    a banked `new_*` is never NULL in practice (the repair only writes a score
    it read from ESPN); the pure form is kept simple deliberately so the test
    reads as the rule rather than as a transcription of the SQL.
    """
    return (
        row.current_home_score == row.new_home_score
        and row.current_away_score == row.new_away_score
    )


async def restore_rows(session, plan: list, *, progress_every: int = 500):
    """Put each banked row back, ONE ROW PER TRANSACTION.

    Deliberately not a batch UPDATE: `events` is write-hot (constant poller and
    backfill locks), and a batched one-off rolls the whole thing back on the
    first contended row. Slow is the point (#3780's measured lesson on this
    exact table).

    Returns `(restored, skipped_ids)`.
    """
    from sqlalchemy import text

    restored, skipped = 0, []
    for n, row in enumerate(plan, start=1):
        if not restorable(row):
            skipped.append(row.event_id)
            continue
        result = await session.execute(text(_RESTORE_SQL), {
            "event_id": row.event_id,
            "old_home_score": row.old_home_score,
            "old_away_score": row.old_away_score,
            "old_completed_at": row.old_completed_at,
            "old_win_probability_sources": row.old_win_probability_sources,
            "new_home_score": row.new_home_score,
            "new_away_score": row.new_away_score,
        })
        if (result.rowcount or 0) == 0:
            # The CAS lost to a concurrent write between the plan and now. Not
            # an error — it is the guard doing its job — but it must be VISIBLE,
            # or a restore that silently changed nothing reads as a clean run.
            skipped.append(row.event_id)
        else:
            restored += 1
        await session.commit()
        if progress_every and n % progress_every == 0:
            print(f"  ... {n}/{len(plan)} considered, {restored} restored")
    return restored, skipped


async def run(args) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        exists = (
            await s.execute(text(f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"))
        ).scalar_one()
        if not exists:
            # Gotcha #53: an empty read is not a fact. "Never backed up" and
            # "backed up, nothing to restore" are different answers and the
            # operator needs to be told which one this is.
            print(f"{BAK_TABLE} does not exist — this repair has never been "
                  f"applied on this database. Nothing to restore.")
            return

        plan = (await s.execute(text(_PLAN_SQL))).all()
        movable = [r for r in plan if restorable(r)]
        print(f"=== #7147 restore: {len(plan)} banked row(s), "
              f"{len(movable)} still holding the score the repair wrote ===")
        for r in plan[:20]:
            mark = "restore" if restorable(r) else "SKIP (moved on)"
            print(f"  {r.event_id}: {r.new_home_score}-{r.new_away_score} "
                  f"→ {r.old_home_score}-{r.old_away_score}   "
                  f"[now {r.current_home_score}-{r.current_away_score}] {mark}")
        if len(plan) > 20:
            print(f"  ... and {len(plan) - 20} more")

        if not args.apply:
            print("\nDRY RUN — no writes. Re-run with --apply to restore.")
            return

        restored, skipped = await restore_rows(s, plan)
        print(f"\nRESTORED {restored} row(s); skipped {len(skipped)}")
        if skipped:
            print("skipped (a newer score than the repair's is on the row): "
                  + ", ".join(str(i) for i in skipped[:50]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="write the banked values back (default: dry run)")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
