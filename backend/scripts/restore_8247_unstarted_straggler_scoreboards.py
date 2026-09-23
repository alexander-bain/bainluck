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
    SNAPSHOT_BACKUP_TABLE,
    wrong_app_refusal,
)

__all__ = [
    "ALREADY_BACK",
    "BACKUP_TABLE",
    "DIVERGED",
    "NO_BACKUP",
    "PRODUCER_APP",
    "RESTORE",
    "SNAPSHOT_BACKUP_TABLE",
    "classify",
    "main",
    "restore_snapshots",
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


async def restore_snapshots(session, apply: bool) -> tuple[int, int, int]:
    """Put the deleted chart points back, under their ORIGINAL ids.

    Returns ``(to_restore, restored, already_back)``.

    Two things make this a real undo rather than a re-insert:

    * the original `id` goes back in explicitly. `score_snapshots.id` is what the
      history route orders on, so a point restored under a fresh id is a
      different row wearing the same values.
    * `ON CONFLICT (id) DO NOTHING`, so running the undo twice is a no-op and a
      row the repair never actually deleted is never duplicated.

    A missing bank table is not an error: it means the snapshot half never ran.
    """
    exists = await session.execute(
        text("SELECT to_regclass(:t)"), {"t": SNAPSHOT_BACKUP_TABLE}
    )
    if exists.scalar() is None:
        return (0, 0, 0)

    result = await session.execute(
        text(f"""
            SELECT b.snapshot_id, b.event_id, b.captured_at,
                   b.home_score, b.away_score,
                   (ss.id IS NOT NULL) AS still_present
              FROM {SNAPSHOT_BACKUP_TABLE} b
              LEFT JOIN score_snapshots ss ON ss.id = b.snapshot_id
             ORDER BY b.snapshot_id
        """)
    )
    rows = [dict(r) for r in result.mappings()]
    already_back = [r for r in rows if r["still_present"]]
    to_restore = [r for r in rows if not r["still_present"]]

    if not apply:
        return (len(to_restore), 0, len(already_back))

    restored = 0
    for row in to_restore:
        res = await session.execute(
            text("""
                INSERT INTO score_snapshots
                    (id, event_id, captured_at, home_score, away_score)
                VALUES (:sid, :eid, :cap, :home, :away)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "sid": row["snapshot_id"], "eid": row["event_id"],
                "cap": row["captured_at"], "home": row["home_score"],
                "away": row["away_score"],
            },
        )
        restored += res.rowcount or 0
    return (len(to_restore), restored, len(already_back))


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    async with get_task_session() as session:
        # BOTH banks are consulted before giving up. The repair creates them in
        # one transaction, but it creates the snapshot bank only when it has a
        # snapshot to delete — so "no event bank" does not imply "no chart points
        # to put back", and an early return on the event bank alone would make
        # the chart half of the undo silently unreachable.
        # `Result.scalar()` CONSUMES the result, so each of these is read exactly
        # once into a name. Reading `exists.scalar()` twice returns None the
        # second time and would report a present table as missing.
        event_bank = (
            await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE})
        ).scalar()
        snapshot_bank = (
            await session.execute(
                text("SELECT to_regclass(:t)"), {"t": SNAPSHOT_BACKUP_TABLE}
            )
        ).scalar()

        if event_bank is None and snapshot_bank is None:
            print(
                f"no backup table {BACKUP_TABLE} and no {SNAPSHOT_BACKUP_TABLE} "
                f"— the repair has not been applied, so there is nothing to undo."
            )
            return 0

        rows: list[dict] = []
        if event_bank is None:
            print(
                f"no {BACKUP_TABLE} — the hero half was never applied; "
                f"restoring chart points only."
            )
        else:
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

        snap_pending, _, snap_already = await restore_snapshots(session, apply=False)
        print(f"  chart points back: {snap_already}")
        print(f"  chart points due : {snap_pending}")

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

        # Same transaction as the hero rows, for the same reason the repair
        # deletes them in one: the page must never serve a restored hero over a
        # chart that has not come back yet.
        snap_due, snap_restored, _ = await restore_snapshots(session, apply=True)
        await session.commit()

        drift = len(buckets[RESTORE]) - written
        snap_drift = snap_due - snap_restored
        print(f"\n  rows restored    : {written}")
        print(f"  concurrent_drift : {drift}")
        print(f"  chart restored   : {snap_restored}")
        print(f"  chart drift      : {snap_drift}")
        return 0 if (drift == 0 and snap_drift == 0) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
