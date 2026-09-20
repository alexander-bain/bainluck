"""#7429 — the one-command undo for `repair_7429_kalshi_count_leg_labels.py` (D51).

Puts back the `E<n>` label on every outcome **this repair renamed and that is
still exactly as the repair left it**. Nothing else is touched: the repair
writes one column, so the restore writes that one column back.

    python3 scripts/restore_7429_kalshi_count_leg_labels.py          # plan only
    python3 scripts/restore_7429_kalshi_count_leg_labels.py --apply  # undo

    heroku run:detached -a bainluck-heavy \\
      "python3 scripts/restore_7429_kalshi_count_leg_labels.py --apply"

IT RESTORES ON A COMPARE-AND-SWAP AGAINST `set_name`, NOT ON A DIFF AGAINST THE
SNAPSHOT, and the difference is the whole point (repair_6919's lesson,
CERT-2439's block, inherited here rather than re-learned). `backup_7429_outcome_names`
records both halves: `name` is what the row was, `set_name` is what the repair
wrote. An undo keyed on "does this row differ from its backup?" would be true
for a row this repair renamed AND for one `_poll_kalshi_markets` renamed
afterwards on its own terms — and that second case is not hypothetical here,
because the forward fix (#7429) is live on the producer and writes `name` on
every upsert it reaches. Such a row is REPORTED AND LEFT ALONE. That is not a
failure and not a no-op: it is the undo declining to overwrite a newer
decision, which is the only correct thing it can do.

Note which direction this undo runs in. The repair replaces a ticker fragment
with the number the venue corroborated, so restoring puts the WRONG label back
on the page. That is what an undo is for, and it is why it is a separate
attended command rather than anything automatic.

Leaves the backup table in place: a restore that destroys the only record of
the pre-repair state cannot be run twice, and the second run is the one you
need when the first was interrupted.

Runtime DDL: none. This script only reads the backup table and updates
`futures_outcomes.name`. Attended invocation only (notice 47(c)).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PRODUCER_APP = "bainluck-heavy"
BACKUP_TABLE = "backup_7429_outcome_names"

#: The compare-and-swap, evaluated in SQL so the plan prints exactly what
#: `--apply` would act on. `o.name IS NOT DISTINCT FROM b.set_name` is the
#: swap: a row whose name has moved off the repair's value since is excluded
#: from `restorable` and lands in `moved_on`.
_PLAN_SQL = f"""
SELECT b.id,
       o.external_id,
       b.name      AS restore_to,
       b.set_name  AS repair_wrote,
       o.name      AS current_name
  FROM {BACKUP_TABLE} b
  JOIN futures_outcomes o ON o.id = b.id
 ORDER BY o.external_id
"""


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    Same gate and same reason as the repair: `app.tasks.poll_kalshi_markets`
    is in `HEAVY_TASKS`, so the rows this touches are written by what is
    deployed to the heavy app. Unset means a laptop pointed at the production
    database, which refuses rather than falling through. A plan-only run reads
    nothing but the backup table and runs anywhere.
    """
    if not args.apply:
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. Re-run "
        f"with `heroku run:detached -a {PRODUCER_APP}`."
    )


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        exists = (
            await s.execute(
                text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE}
            )
        ).scalar()
        if exists is None:
            print(
                f"no {BACKUP_TABLE} table — the repair never took a backup on "
                "this database, so there is nothing to undo."
            )
            return 0

        rows = (await s.execute(text(_PLAN_SQL))).all()
        restorable = [r for r in rows if r.current_name == r.repair_wrote]
        moved_on = [r for r in rows if r.current_name != r.repair_wrote]

        print(f"=== plan ({len(rows)} rows in {BACKUP_TABLE}) ===")
        print(f"  restorable (still as the repair left it)  {len(restorable)}")
        print(f"  moved on   (left alone)                   {len(moved_on)}")
        for r in restorable[: args.show]:
            print(
                f"    RESTORE  {r.external_id:<44} "
                f"{r.current_name!r} -> {r.restore_to!r}"
            )
        for r in moved_on[: args.show]:
            print(
                f"    SKIP     {r.external_id:<44} now {r.current_name!r}, "
                f"repair wrote {r.repair_wrote!r}"
            )

        if not restorable:
            print("\nnothing to restore")
            return 0

        if not args.apply:
            print("\nplan only — nothing written")
            return 0

        print("\n=== apply ===")
        for r in restorable:
            await s.execute(
                text(
                    "UPDATE futures_outcomes SET name = :old "
                    "WHERE id = :id AND name = :wrote"
                ),
                {"old": r.restore_to, "id": r.id, "wrote": r.repair_wrote},
            )
        await s.commit()
        print(f"  restored {len(restorable)} names")

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="write the undo")
    p.add_argument("--show", type=int, default=10, help="specimen lines to print")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
