"""#8247 — the D51(b) undo for `repair_8247_unstarted_straggler_scoreboards.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command, and the permission is conditional on it working:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_8247_unstarted_straggler_scoreboards.py --apply

WHAT IT PUTS BACK. ``events.home_score`` and ``events.away_score`` for the rows
named in :data:`~repair_8247_unstarted_straggler_scoreboards.BACKUP_TABLE`, from
the pre-image banked before the first UPDATE. Those two columns are the only
thing the repair ever wrote — no status moved, no `completed_at`, no `period`, no
`game_clock`, nothing was deleted — so there is no ordering problem and no FK to
satisfy.

⚠️ WHAT RESTORING MEANS HERE, SAID PLAINLY. It puts the `0-0` scoreboards back —
it re-creates the defect #8247 describes, where ``/events/15290171`` prints a
`0 — 0` hero and an "Actual Score Diff" point for a game that was postponed in
April and never played. That is the correct behaviour for an undo and it is the
whole point of D51's backup-first bargain, but it means this script rolls back a
TRUTH repair. Run it because the repair went wrong, not because it is finished.

WHAT IT WILL NOT DO. Overwrite a row that has moved again since. Every restore is
compare-and-set on the EXACT state the repair left (``home_score IS NULL AND
away_score IS NULL``, still `scheduled`, still unsettled); anything else is
reported ``DIVERGED`` and left alone. An undo that stomps a later, unrelated
decision is not an undo — and here the likeliest later decision is a legitimate
one, because a postponed game can be made up and played, at which point the row
takes a REAL score that must survive this script.

Nor will it invent a value: a row with no backup row is ``NO_BACKUP``, not "guess
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
from repair_8247_unstarted_straggler_scoreboards import (  # noqa: E402
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
    "classify",
    "main",
    "run",
]

#: Verdicts.
RESTORE = "RESTORE"
ALREADY_BACK = "ALREADY_BACK"
DIVERGED = "DIVERGED"
NO_BACKUP = "NO_BACKUP"


def classify(row: dict) -> str:
    """What this row has earned, from its CURRENT state against the pre-image.

    PURE, so the whole policy is testable without a database. `row` carries the
    banked pre-image and the live columns side by side.
    """
    if row.get("prior_home_score") is None and row.get("prior_away_score") is None:
        # Both NULL in the bank means the repair never had anything to undo for
        # this row; it is indistinguishable from the repaired state and putting
        # NULL back is a no-op either way.
        return ALREADY_BACK
    if row["status"] != "scheduled" or row["completed_at"] is not None:
        return DIVERGED
    if (row["home_score"], row["away_score"]) == (
        row["prior_home_score"], row["prior_away_score"]
    ):
        return ALREADY_BACK
    if row["home_score"] is not None or row["away_score"] is not None:
        # The row took a score that is not the one the repair removed — a real
        # result for a made-up game. Never overwrite that with a banked 0-0.
        return DIVERGED
    return RESTORE


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    async with get_task_session() as session:
        exists = await session.execute(
            text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE}
        )
        if exists.scalar() is None:
            print(
                f"no backup table {BACKUP_TABLE} — the repair has not been "
                f"applied, so there is nothing to undo."
            )
            return 0

        result = await session.execute(
            text(f"""
                SELECT b.event_id AS id,
                       b.prior_home_score, b.prior_away_score,
                       e.status, e.completed_at, e.home_score, e.away_score
                  FROM {BACKUP_TABLE} b
                  JOIN events e ON e.id = b.event_id
                 ORDER BY b.event_id
            """)
        )
        rows = [dict(r) for r in result.mappings()]

        buckets: dict[str, list[dict]] = {
            RESTORE: [], ALREADY_BACK: [], DIVERGED: [], NO_BACKUP: [],
        }
        for row in rows:
            buckets[classify(row)].append(row)

        print(f"#8247 restore — {'APPLY' if apply else 'DRY RUN'}")
        for verdict in (RESTORE, ALREADY_BACK, DIVERGED, NO_BACKUP):
            print(f"  {verdict:<13}: {len(buckets[verdict])}")
        for row in buckets[DIVERGED]:
            print(
                f"    DIVERGED {row['id']}: now status={row['status']!r} "
                f"score={row['home_score']}-{row['away_score']} — left alone"
            )

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0

        written = 0
        for row in buckets[RESTORE]:
            # Compare-and-set on the state the repair left, so a row that moved
            # between the SELECT above and this UPDATE is not stomped.
            result = await session.execute(
                text("""
                    UPDATE events
                       SET home_score = :home, away_score = :away
                     WHERE id = :eid
                       AND status = 'scheduled'
                       AND completed_at IS NULL
                       AND home_score IS NULL
                       AND away_score IS NULL
                """),
                {
                    "eid": row["id"],
                    "home": row["prior_home_score"],
                    "away": row["prior_away_score"],
                },
            )
            written += result.rowcount or 0
        await session.commit()

        drift = len(buckets[RESTORE]) - written
        print(f"\n  rows restored    : {written}")
        print(f"  concurrent_drift : {drift}")
        return 0 if drift == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
