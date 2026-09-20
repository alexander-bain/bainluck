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
🔴 It does not restore a row that has moved on from the state the repair left.
This is the CERT-2439 lesson and on THIS cohort it is not theoretical: the whole
population is rows ESPN can adjudicate, and ESPN correcting its own final again
— a scoring change, a protest, a resumed game — is the outcome the repair exists
to let through. An undo keyed on "the live row differs from its backup" would
systematically revert the authority's newer, better score back to the frozen
mid-game number this repair removed. So the compare-and-swap is on the `new_*`
manifest — what WE left behind — not on difference. Rows that moved on are
reported by id and skipped.

🔴 THE COMPARE-AND-SWAP COVERS ALL FOUR RESTORED COLUMNS, NOT THE SCORE
(CERT-3141). Restoring four columns while observing two is not a compare-and-
swap, it is a compare-and-swap for one field and a blind overwrite for the rest,
and both blind fields have a routine newer-value case:

* the repair's `fix_completed_at_only` branch never changes the score, so the
  banked `new_*` score equals the live score forever — the score CAS can never
  fail on those rows, and the undo would put a pre-repair NULL `completed_at`
  back over a value production has since derived;
* the blend is rewritten by later legitimate passes (`backfill_winners`, a
  re-resolve) without touching the score, so a score-only CAS passes and the
  undo replaces the newer grade with the pre-repair one.

Both are score-indistinguishable by construction, so no amount of care about the
score can see them. `completed_at` and `win_probability_sources` are therefore in
the manifest and in the WHERE.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the repair is idempotent precisely so the pair can be
exercised more than once.

🔴 NOTHING BUT THE EVENT ID IS BOUND. Both the values written and the values
compared come out of the backup table by column reference in one `UPDATE ...
FROM`, so no `timestamptz` and no `jsonb` ever round-trips through a bind
parameter. That is not only tidier — it is the only form that WORKS here. A
jsonb column read through `text()` comes back as a dict (SQLAlchemy registers
`json.loads` as the asyncpg decoder), and handing that dict back to an untyped
bind reaches `_jsonb_encoder(str_value)`, which calls `.encode()` on it:
`AttributeError`, on the first row with a banked blend. That is CERT-932's
defect. `tests/test_restore_jsonb_bind_contract.py` guards the restores that
rebuild whole rows from a banked snapshot by typing the bind; this one sidesteps
the class entirely by never leaving the database. (That guard finds its subjects
by scanning for the call they share, so spelling the call's name in this prose
would enlist a script that makes no such call — hence the circumlocution.)
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_event_final_scores import BAK_TABLE, SNAP_BAK_TABLE  # noqa: E402

#: THE SNAPSHOT HALF'S PLAN. A deleted row's undo is an INSERT, so the
#: compare-and-swap that guards the event-row half has no analogue here: there
#: are no "columns that moved on" because there is no row to move. What replaces
#: it is the absence test — put the row back only where nothing holds its id —
#: and that is the primary key's job, expressed as ``ON CONFLICT DO NOTHING``.
#:
#: The FK to ``events`` is checked in the plan rather than left to raise: an
#: event deleted since the repair would abort the insert, and one row that
#: cannot come back must not take the rest of the restore down with it.
_SNAP_PLAN_SQL = f"""
SELECT b.snapshot_id,
       b.event_id,
       b.captured_at,
       b.home_score,
       b.away_score,
       b.espn_final,
       EXISTS (SELECT 1 FROM score_snapshots s
                WHERE s.id = b.snapshot_id)   AS already_present,
       EXISTS (SELECT 1 FROM events e
                WHERE e.id = b.event_id)      AS event_exists
  FROM {SNAP_BAK_TABLE} b
 ORDER BY b.event_id, b.captured_at
"""

#: Re-insert with the ORIGINAL primary key, so a second run of the undo is a
#: no-op rather than a second copy of every snapshot. Safe against the identity
#: sequence: these ids were issued before the delete, so the sequence is already
#: past them.
_SNAP_RESTORE_SQL = f"""
INSERT INTO score_snapshots (id, event_id, captured_at, home_score, away_score)
SELECT b.snapshot_id, b.event_id, b.captured_at, b.home_score, b.away_score
  FROM {SNAP_BAK_TABLE} b
 WHERE b.snapshot_id = :snapshot_id
   AND EXISTS (SELECT 1 FROM events e WHERE e.id = b.event_id)
ON CONFLICT (id) DO NOTHING
"""

#: The banked row beside the live one, so the dry run can show which rows the
#: undo would move and which it will decline. Every restored column appears on
#: both sides, because the plan's job is to preview the compare-and-swap and a
#: preview that compares fewer columns than the write would promise restores the
#: write then refuses.
_PLAN_SQL = f"""
SELECT b.event_id,
       b.old_home_score,
       b.old_away_score,
       b.old_completed_at,
       b.old_win_probability_sources,
       b.new_home_score,
       b.new_away_score,
       b.new_completed_at,
       b.new_win_probability_sources,
       e.home_score AS current_home_score,
       e.away_score AS current_away_score,
       e.completed_at AS current_completed_at,
       e.win_probability_sources AS current_win_probability_sources
  FROM {BAK_TABLE} b
  JOIN events e ON e.id = b.event_id
 ORDER BY b.event_id
"""

#: The write, and it is a compare-and-swap over EVERY column it restores. Values
#: and comparands alike come from the joined backup row, so the statement binds
#: nothing but the id (see the module docstring's bind note) and the read of the
#: live row happens inside the UPDATE — one moment, not two. If anything has
#: changed the score, the completion time or the blend since the repair, the
#: statement no-ops instead of reverting it.
_RESTORE_SQL = f"""
UPDATE events e
   SET home_score = b.old_home_score,
       away_score = b.old_away_score,
       completed_at = b.old_completed_at,
       win_probability_sources = b.old_win_probability_sources
  FROM {BAK_TABLE} b
 WHERE b.event_id = :event_id
   AND e.id = b.event_id
   AND e.home_score IS NOT DISTINCT FROM b.new_home_score
   AND e.away_score IS NOT DISTINCT FROM b.new_away_score
   AND e.completed_at IS NOT DISTINCT FROM b.new_completed_at
   AND e.win_probability_sources IS NOT DISTINCT FROM b.new_win_probability_sources
"""

#: The four columns the undo restores, each paired with the manifest value that
#: licenses restoring it. ONE list, read by the pure gate and asserted against
#: the statement's own SET clause by the guard — so a fifth restored column
#: cannot be added without either joining the comparison or failing the test.
RESTORED_COLUMNS = (
    "home_score",
    "away_score",
    "completed_at",
    "win_probability_sources",
)


def restorable(row) -> bool:
    """Is this row still the one the repair left behind?

    Pure, and true only when EVERY column the undo would write still holds what
    the repair left on it. Anything else is newer information than the backup,
    and newer information wins — see the docstring's CERT-2439 note.

    Score alone is not enough and cannot be made enough: the repair has a branch
    that writes only `completed_at`, and on those rows the banked and live scores
    agree by construction for as long as the row exists (CERT-3141).

    `IS NOT DISTINCT FROM` in the statement and `==` here agree on NULL for the
    scalar columns. The blend is compared as the dict SQLAlchemy's asyncpg
    decoder hands back, which is key-order-insensitive like `jsonb` equality; the
    statement is the authority either way, and a disagreement can only make this
    preview optimistic — the write still refuses.
    """
    return not moved_columns(row)


def moved_columns(row) -> list:
    """Which restored columns no longer hold what the repair left, BY NAME.

    The dry run's whole job is to tell an operator what the undo will and will
    not do, and "SKIP (moved on)" over a printed score is actively misleading on
    the two columns the score cannot speak for: a row skipped because its blend
    was re-graded reads as a skip on a score that is plainly unchanged. Naming
    the column costs one list comprehension.
    """
    return [
        column
        for column in RESTORED_COLUMNS
        if getattr(row, f"current_{column}") != getattr(row, f"new_{column}")
    ]


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
        result = await session.execute(
            text(_RESTORE_SQL), {"event_id": row.event_id}
        )
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


async def restore_snapshots(session, plan: list):
    """Put each banked snapshot back, one row per transaction.

    Same single-row commit discipline as :func:`restore_rows` and for the same
    measured reason (#3780): a batched write over a contended table rolls the
    whole restore back on the first busy row.

    Returns ``(restored, skipped)`` where a skip is a row that is already
    present (a second run, or one the repair never actually deleted) or whose
    event has since been removed.
    """
    from sqlalchemy import text

    restored, skipped = 0, []
    for row in plan:
        if row.already_present or not row.event_exists:
            skipped.append(row.snapshot_id)
            continue
        result = await session.execute(
            text(_SNAP_RESTORE_SQL), {"snapshot_id": row.snapshot_id}
        )
        if (result.rowcount or 0) == 0:
            # Lost to a concurrent insert on the same id between plan and write.
            # Visible, for the same reason the event-row half makes it visible:
            # a restore that silently changed nothing reads as a clean run.
            skipped.append(row.snapshot_id)
        else:
            restored += 1
        await session.commit()
    return restored, skipped


async def run(args) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        # The two banks are asked for INDEPENDENTLY. A database can hold either
        # without the other — a run that found only snapshot defects creates no
        # event-row table, and every database repaired before this half shipped
        # holds the event-row table alone. Returning early on the first missing
        # one would make the undo silently decline to restore the other.
        exists = (
            await s.execute(text(f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"))
        ).scalar_one()
        snap_exists = (
            await s.execute(
                text(f"SELECT to_regclass('{SNAP_BAK_TABLE}') IS NOT NULL")
            )
        ).scalar_one()
        if not exists and not snap_exists:
            # Gotcha #53: an empty read is not a fact. "Never backed up" and
            # "backed up, nothing to restore" are different answers and the
            # operator needs to be told which one this is.
            print(f"Neither {BAK_TABLE} nor {SNAP_BAK_TABLE} exists — this "
                  f"repair has never been applied on this database. Nothing "
                  f"to restore.")
            return

        plan = (await s.execute(text(_PLAN_SQL))).all() if exists else []
        snap_plan = (
            (await s.execute(text(_SNAP_PLAN_SQL))).all() if snap_exists else []
        )

        movable = [r for r in plan if restorable(r)]
        print(f"=== #7147 restore: {len(plan)} banked row(s), "
              f"{len(movable)} still holding everything the repair wrote ===")
        for r in plan[:20]:
            moved = moved_columns(r)
            mark = "restore" if not moved else f"SKIP (moved on: {', '.join(moved)})"
            print(f"  {r.event_id}: {r.new_home_score}-{r.new_away_score} "
                  f"→ {r.old_home_score}-{r.old_away_score}   "
                  f"[now {r.current_home_score}-{r.current_away_score}] {mark}")
        if len(plan) > 20:
            print(f"  ... and {len(plan) - 20} more")

        snap_movable = [
            r for r in snap_plan if not r.already_present and r.event_exists
        ]
        print(f"\n=== #7147 snapshot restore: {len(snap_plan)} banked "
              f"snapshot(s), {len(snap_movable)} still absent and re-insertable "
              f"===")
        for r in snap_plan[:20]:
            if r.already_present:
                mark = "SKIP (already present)"
            elif not r.event_exists:
                mark = "SKIP (event no longer exists)"
            else:
                mark = "re-insert"
            print(f"  ev{r.event_id} snap{r.snapshot_id}: "
                  f"{r.home_score}-{r.away_score} at {r.captured_at} "
                  f"(final was {r.espn_final}) {mark}")
        if len(snap_plan) > 20:
            print(f"  ... and {len(snap_plan) - 20} more")

        if not args.apply:
            print("\nDRY RUN — no writes. Re-run with --apply to restore.")
            return

        restored, skipped = await restore_rows(s, plan)
        print(f"\nRESTORED {restored} row(s); skipped {len(skipped)}")
        if skipped:
            print("skipped (the score, the completion time or the blend has "
                  "moved on from what the repair wrote): "
                  + ", ".join(str(i) for i in skipped[:50]))

        snap_restored, snap_skipped = await restore_snapshots(s, snap_plan)
        print(f"RE-INSERTED {snap_restored} snapshot(s); "
              f"skipped {len(snap_skipped)}")
        if snap_skipped:
            print("skipped (already present, or the event is gone): "
                  + ", ".join(str(i) for i in snap_skipped[:50]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="write the banked values back (default: dry run)")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
