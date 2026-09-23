"""#8132 — the D51(b) undo for `repair_8132_fabricated_win.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command, and the permission is conditional on it working:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_8132_fabricated_win.py --apply

WHAT IT PUTS BACK. ``futures_outcomes.is_winner`` and ``resolution_source`` for
the legs named in :data:`~repair_8132_fabricated_win.BACKUP_TABLE`, from the
pre-image that table banked before the first UPDATE. Those two columns are the
only thing the repair ever wrote: no price moved, no market row, no capture,
nothing was deleted. So there is no ordering problem and no FK to satisfy.

⚠️ WHAT RESTORING MEANS HERE, SAID PLAINLY. It puts back the fabricated WINS —
it re-creates the defect #8132 describes, where 56 settled legs print "Won" and
46 of them print it at 95-99% against their own venue's finalized ``no``. That is
the correct behaviour for an undo and it is the whole point of D51's backup-first
bargain, but it means this script rolls back a TRUTH repair. Run it because the
repair went wrong, not because the repair is finished.

WHAT IT WILL NOT DO. Overwrite a row that has moved again since. Every restore is
compare-and-set on the EXACT state the repair wrote (``is_winner = false`` AND
``resolution_source`` = the target it stamped); anything else is reported
``DIVERGED`` and left alone. An undo that stomps a later, unrelated decision is
not an undo — and here the likeliest later decision is a legitimate one, because
a repaired leg is precisely a leg some grader may since have settled properly.

Nor will it invent a value: a leg with no backup row is ``NO_BACKUP``, not "guess
what it used to be". The repair banks the pre-image before its first write and
uses ``ON CONFLICT DO NOTHING``, so the banked row is always the ORIGINAL state
even across repeated runs.

Idempotent and re-runnable: the compare-and-set makes a second run a no-op
(``ALREADY_BACK``).

The backup table is NOT Alembic-managed. ``alembic revision --autogenerate`` will
propose DROPping it — expected, and to be deleted from the generated migration
rather than accepted. Drop it deliberately once the repair is trusted and this
undo is no longer wanted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the sibling import below resolves however
# the file is loaded. Running `python3 scripts/restore_….py` puts `scripts/` on
# the path for free; importing the file by its path (the guard test does) does
# not, and the difference is an ImportError nobody sees until CI.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402
from repair_8132_fabricated_win import (  # noqa: E402
    BACKUP_TABLE,
    PRODUCER_APP,
    wrong_app_refusal,
)

__all__ = [
    "ALREADY_BACK",
    "BACKUP_TABLE",
    "DIVERGED",
    "NO_BACKUP",
    "PRODUCER_APP",
    "RESTORE",
    "main",
    "run",
]

#: Verdicts.
RESTORE = "RESTORE"
ALREADY_BACK = "ALREADY_BACK"
DIVERGED = "DIVERGED"
NO_BACKUP = "NO_BACKUP"


async def backup_exists(session) -> bool:
    """False when the repair never ran (or its table was dropped)."""
    got = await session.execute(
        text("SELECT to_regclass(:name)"), {"name": BACKUP_TABLE}
    )
    return got.scalar() is not None


async def run(apply: bool) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2

    async with get_task_session() as session:
        if not await backup_exists(session):
            print(
                f"NO_BACKUP: {BACKUP_TABLE} does not exist — the repair has not "
                "run on this database, so there is nothing to undo."
            )
            return 2

        rows = (
            await session.execute(
                text(f"""
                    SELECT b.outcome_id, b.ticker, b.prior_is_winner,
                           b.prior_source, b.target_source,
                           fo.is_winner AS now_winner,
                           COALESCE(fo.resolution_source, '') AS now_source
                    FROM {BACKUP_TABLE} b
                    LEFT JOIN futures_outcomes fo ON fo.id = b.outcome_id
                    ORDER BY b.outcome_id
                """)
            )
        ).all()

        plan: list[dict] = []
        for oid, ticker, prior_winner, prior_source, target, now_w, now_s in rows:
            if now_w is None:
                verdict, why = NO_BACKUP, "outcome row is gone"
            elif now_w is prior_winner and now_s == prior_source:
                verdict, why = ALREADY_BACK, ""
            elif now_w is False and now_s == target:
                verdict, why = RESTORE, ""
            else:
                verdict, why = (
                    DIVERGED,
                    f"row moved since the repair: ({now_w}, {now_s!r}) is neither "
                    f"the repair's write ({False}, {target!r}) nor the pre-image "
                    f"({prior_winner}, {prior_source!r})",
                )
            plan.append(
                {
                    "outcome_id": oid,
                    "ticker": ticker,
                    "prior_winner": prior_winner,
                    "prior_source": prior_source,
                    "target": target,
                    "verdict": verdict,
                    "why": why,
                }
            )

        summary: dict[str, int] = {}
        for row in plan:
            summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1

        print(f"#8132 restore — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  banked rows : {len(plan)}")
        for verdict in (RESTORE, ALREADY_BACK, DIVERGED, NO_BACKUP):
            print(f"  {verdict:<14} : {summary.get(verdict, 0)}")
        for row in plan:
            if row["verdict"] in (DIVERGED, NO_BACKUP):
                print(f"    {row['verdict']} {row['outcome_id']} {row['ticker']} {row['why']}")

        restorable = [r for r in plan if r["verdict"] == RESTORE]
        if not apply:
            print(f"\ndry run — nothing written. {len(restorable)} row(s) would be put back.")
            return 0

        written = 0
        drift = 0
        for row in restorable:
            result = await session.execute(
                text("""
                    UPDATE futures_outcomes
                    SET is_winner = :prior_winner,
                        resolution_source = :prior_source,
                        last_updated = NOW()
                    WHERE id = :oid
                      AND is_winner IS FALSE
                      AND COALESCE(resolution_source, '') = :target
                """),
                {
                    "oid": row["outcome_id"],
                    "prior_winner": row["prior_winner"],
                    "prior_source": row["prior_source"],
                    "target": row["target"],
                },
            )
            if result.rowcount == 1:
                written += 1
            else:
                drift += 1
        await session.commit()

        print(f"\n  rows restored    : {written}")
        print(f"  concurrent_drift : {drift}")
        return 0 if drift == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write (default: dry run)"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
