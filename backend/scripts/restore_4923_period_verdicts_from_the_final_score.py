"""#4923 — the one-command undo for `repair_4923_period_verdicts_from_the_final_score.py` (D51).

Puts `is_winner` and `resolution_source` back for every outcome **this repair
cleared and that is still ungraded**. Nothing else is touched: the repair writes
exactly two columns, so the restore writes exactly those two back.

    python3 scripts/restore_4923_period_verdicts_from_the_final_score.py            # plan only
    python3 scripts/restore_4923_period_verdicts_from_the_final_score.py --apply    # undo

    # #5023 — put back ONLY the 70 rows the first cohort wrongly matched on the
    # ticker's date suffix, leaving the 1,718 correct retractions in place:
    python3 scripts/restore_4923_period_verdicts_from_the_final_score.py \\
      --outside-declared-cohort --apply

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_4923_period_verdicts_from_the_final_score.py --apply"

IT JOINS THE MANIFEST TO THE BACKUP, AND THE MANIFEST IS THE AUTHORITY — the
CERT-2439 lesson, taken from #4586's restore rather than re-learned here. The
backup is a full row snapshot: it records what each outcome WAS and cannot
record that this script is what changed it. Restoring from the backup alone
means asking "does the live row differ from its backup?", which is also true of
a row the VENUE has graded since — and the undo would then replace Kalshi's own
`api_settlement` verdict with the invented `game_score` one this repair existed
to remove. The manifest holds one row per SUCCESSFUL clear, so it is the only
record of what this script actually did.

THE COMPARE-AND-SWAP IS "STILL UNGRADED", not "still NULL is_winner".
`resolution_source IS NULL` is the test, because that is the column every reader
of a grade gates on (`_settled_grade_fields`) and the one the repair cleared to
make the row re-gradable. An outcome that has since been graded by anyone is
REPORTED AND LEFT ALONE. That is not a failure and not a no-op: it is the undo
declining to overwrite a newer, better verdict, which is the only correct thing
it can do — and on this cohort it is the LIKELY case, because the whole point of
clearing was to let the venue's settlement land.

Leaves the backup and manifest tables in place: a restore that destroys the only
copy of the pre-repair state cannot be run twice, and the second run is the one
you need when the first was interrupted.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_4923_futures_outcomes"
MANIFEST_TABLE = "bak_4923_repair_manifest"

#: `--outside-declared-cohort` (#5023) — put back ONLY the rows the repair
#: should never have touched. The 2026-09-11 01:37Z run matched the period
#: grammar against the whole `external_id` instead of the series family, so 70
#: outcomes across 12 markets were cleared on the strength of a day-of-month
#: running into a club code (`KXMLSSPREAD-26APR22HOUSD` → `22H`). Those 70 held
#: CORRECT verdicts; the other 1,718 are the ship and must stay cleared.
#:
#: WHY THIS IS A PREDICATE AND NOT A LIST OF IDS. A hand-pasted id list is a
#: snapshot of one person's query and cannot be re-derived or reviewed; this
#: asks the manifest the same question the fixed cohort asks, so it stays
#: correct if the manifest grows and it is checkable by reading it. It is the
#: NEGATION of the repair's own (now family-anchored) cohort — the two files
#: must be read together, and a change to one without the other is a bug.
_SERIES = "split_part(fm.external_id, '-', 1)"
_DECLARED_COHORT = f"""(   {_SERIES} ~* '(^|[^H])[12]H[A-Z]*BTTS'
                        OR {_SERIES} ~* '(^|[^H])2H'
                        OR {_SERIES} ~* '[1-4]Q'
                        OR {_SERIES} ~* 'F[357](SPREAD|TOTAL)?$' )"""

#: Every outcome this repair cleared, with what the live row says NOW and what
#: the backup says it was. Reported in full rather than filtered in SQL, so the
#: rows that will be LEFT ALONE are visible in the plan instead of silently
#: absent from it.
_PLAN_SQL = f"""
SELECT m.outcome_id,
       b.is_winner            AS backup_is_winner,
       b.resolution_source    AS backup_resolution_source,
       f.is_winner            AS current_is_winner,
       f.resolution_source    AS current_resolution_source,
       f.name                 AS outcome_name,
       fm.external_id         AS ticker
  FROM {MANIFEST_TABLE} m
  JOIN {BAK_TABLE} b        ON b.id = m.outcome_id
  JOIN futures_outcomes f   ON f.id = m.outcome_id
  JOIN futures_markets fm   ON fm.id = f.market_id
 {{scope}}
 ORDER BY m.outcome_id
"""

#: The `--outside-declared-cohort` scope, substituted into `{scope}` above.
_OUTSIDE_SCOPE = f"WHERE NOT {_DECLARED_COHORT}"

#: The compare-and-swap. `resolution_source IS NULL` restores a row only while
#: it is still in the state the repair left it in. The backup's own
#: `resolution_source` is required to be the value the repair removed: a
#: hand-edited backup row cannot use this script to write an arbitrary grade.
_RESTORE_SQL = """
UPDATE futures_outcomes
   SET is_winner = :was_winner,
       resolution_source = :was_source
 WHERE id = :oid
   AND resolution_source IS NULL
   AND :was_source = 'game_score'
"""


async def run(args) -> None:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        exists = (
            await s.execute(text(f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL"))
        ).scalar_one()
        if not exists:
            print(f"{MANIFEST_TABLE} does not exist — this repair has never been "
                  f"applied, so there is nothing to undo.")
            return

        scope = _OUTSIDE_SCOPE if args.outside_declared_cohort else ""
        rows = (await s.execute(text(_PLAN_SQL.format(scope=scope)))).all()
        restorable = [r for r in rows if r.current_resolution_source is None]
        moved_on = [r for r in rows if r.current_resolution_source is not None]

        if args.outside_declared_cohort:
            print("SCOPE: only the manifest rows OUTSIDE the declared cohort — the "
                  "#5023 date-suffix false positives. The ship's own clears are "
                  "not in this plan and are not restorable by this invocation.")
        print(f"=== #4923 restore plan: {len(rows)} outcomes in the manifest ===")
        print(f"  still ungraded, will be restored : {len(restorable)}")
        print(f"  graded since, LEFT ALONE         : {len(moved_on)}")
        for r in moved_on[:10]:
            print(f"    {r.outcome_id:>10} now {r.current_resolution_source} "
                  f"win={r.current_is_winner} | {(r.outcome_name or '')[:40]}")
        if moved_on:
            print("  (those are the venue's own verdicts arriving — the repair "
                  "working, not failing.)")

        if not args.apply:
            print("\nDRY-RUN — no writes. Pass --apply to undo.")
            return

        restored = 0
        for r in restorable:
            res = await s.execute(text(_RESTORE_SQL), {
                "oid": int(r.outcome_id),
                "was_winner": r.backup_is_winner,
                "was_source": r.backup_resolution_source,
            })
            restored += 1 if (res.rowcount or 0) else 0
        await s.commit()
        print(f"\nCOMMITTED: restored {restored} of {len(restorable)} outcomes. "
              f"Backup and manifest left in place so this can be run again.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="write the pre-repair verdicts back (default is plan-only)")
    p.add_argument("--outside-declared-cohort", action="store_true",
                   help="restore ONLY the #5023 false positives — manifest rows "
                        "whose series family carries no period token at all")
    asyncio.run(run(p.parse_args()))
