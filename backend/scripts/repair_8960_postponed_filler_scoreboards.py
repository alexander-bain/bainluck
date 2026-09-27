"""#8960 — a match ESPN postponed stops printing "0 - 0" under its chart.

THE SHIP. ``/events/15315470`` (Crawley Town v Barnet), ``/events/15315471``
(Port Vale v Northampton Town) and ``/events/15314000`` (New York Red Bulls v
St. Louis City SC), phone and desktop, measured on production 2026-09-27 ~08:00Z:
the hero reads "Postponed" (ux's #8810 / PR #9025 is live) but the win-probability
card still prints a ``0 - 0`` score row under the chart, and the native clients
read the same stored score. None of the three matches was played.

------------------------------------------------------------------------------
WHY THE 0-0 IS PROVABLY FALSE
------------------------------------------------------------------------------

ESPN's own summary for each fixture, read 2026-09-27 ~08:05Z (notice 26):

    401881358  Crawley Town v Barnet            STATUS_POSTPONED  post  completed=false
    401881354  Port Vale v Northampton Town     STATUS_POSTPONED  post  completed=false
    761833     New York Red Bulls v St. Louis   STATUS_POSTPONED  post  completed=false

Each row is anchored to that id, is ``suspended``, and carries ``period =
'Postponed'`` — the authority's word, written by the ESPN live pass. ESPN
publishes ``"0"``-``"0"`` for a postponed fixture; that is filler, and #8960's
producer fix (``update_event_fields_from_espn``, ``_stoppage_scores_are_filler``)
now refuses it. That fix stops NEW writes; it cannot see the 0-0 already stored,
because it only compares an incoming score against the row.

HOW THE 0-0 GOT THERE. 15314000 passed through ``live`` at kickoff before the
#8960 hold existed. The two League Two rows had no ESPN anchor until #8943 went
live on 2026-09-27 01:50Z, so the Odds API scores feed — which stands down only
for a ``live`` row that HAS an ``espn_id`` (``clockless_write_defers_to_authority``)
— wrote its 0-0 minutes after each kickoff. All three are now anchored, so every
score writer that still reaches a ``suspended`` row either defers or refuses.

------------------------------------------------------------------------------
TWO TABLES, BECAUSE THE PAGE READS TWO
------------------------------------------------------------------------------

The hero reads ``events.home_score/away_score``; the score row under the chart
is ``score_history`` from ``GET /api/events/{id}/history``, built out of
``score_snapshots``. Each row has exactly ONE snapshot, 0-0, captured in the
kickoff window. Clearing one table without the other leaves the same untruth one
surface further down (the #8247 lesson, CERT-3346), so both are written in one
transaction, and a snapshot is deleted only when its event was repaired in the
same run.

------------------------------------------------------------------------------
HOW TO RUN IT (D51(b): backup first, one-command restore)
------------------------------------------------------------------------------

Dry run (default, writes nothing, prints the plan):

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_8960_postponed_filler_scoreboards.py

Apply:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_8960_postponed_filler_scoreboards.py --apply

The undo is one command:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_8960_postponed_filler_scoreboards.py --apply

Runtime DDL (``CREATE TABLE IF NOT EXISTS backup_*``), attended invocation only,
refuses to run anywhere but ``bainluck-heavy`` — notice 47(c), not migration
class. Nothing here runs on merge or on release.

Gotcha #48: ``heroku run`` without ``:detached`` fails silently in the sandbox —
use ``run:detached`` and verify the side effect afterwards with the verify query
this script prints.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the restore's sibling import resolves
# however the file is loaded (see the #8247 pair).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402

#: Only this app may run it — notice 47(c).
PRODUCER_APP = "bainluck-heavy"

BACKUP_TABLE = "backup_8960_postponed_filler_scoreboards"
SNAPSHOT_BACKUP_TABLE = "backup_8960_postponed_filler_snapshots"

#: The authority's stoppage words a row must still carry to be written. A row
#: whose period moved off these has been re-dated or resumed, and its score is
#: no longer evidenced as filler.
STOPPED_PERIODS = frozenset({"Postponed", "Canceled", "Cancelled"})

#: `(event_id, espn_id, home_score, away_score)`, pinned by id AND by the shape
#: each one must still be in, so a row that has since been played is skipped.
EXPECTED: tuple[tuple[int, str, int, int], ...] = (
    (15314000, "761833", 0, 0),     # 2026-09-26 23:30Z  NY Red Bulls v St. Louis City SC
    (15315470, "401881358", 0, 0),  # 2026-09-26 11:30Z  Crawley Town v Barnet
    (15315471, "401881354", 0, 0),  # 2026-09-26 14:00Z  Port Vale v Northampton Town
)
EXPECTED_BY_ID = {row[0]: row for row in EXPECTED}

#: `(snapshot_id, event_id, home_score, away_score)` — one per event, measured
#: 2026-09-27 ~08:00Z.
EXPECTED_SNAPSHOTS: tuple[tuple[int, int, int, int], ...] = (
    (400396, 15314000, 0, 0),  # captured 2026-09-26 23:30:27Z
    (398937, 15315470, 0, 0),  # captured 2026-09-26 13:59:55Z
    (398950, 15315471, 0, 0),  # captured 2026-09-26 14:04:59Z
)
EXPECTED_SNAPSHOTS_BY_ID = {row[0]: row for row in EXPECTED_SNAPSHOTS}


def wrong_app_refusal() -> str | None:
    """Return a refusal string when not running on :data:`PRODUCER_APP`."""
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def row_is_writable(row: dict) -> str | None:
    """Return None when this row may be written, else why it may not.

    PURE and per-row. Every refusal is a reason the 0-0 might NOT be filler: the
    row moved off `suspended`, settled, lost its anchor, lost the stoppage word,
    or carries a real score.
    """
    expected = EXPECTED_BY_ID.get(row["id"])
    if expected is None:
        return "not in the pinned population"
    if row["status"] != "suspended":
        return f"status moved to {row['status']!r} — no longer the defect shape"
    if row["completed_at"] is not None:
        return "row has since been settled — its score is now a result"
    if row["espn_id"] != expected[1]:
        return (
            f"espn_id is {row['espn_id']!r}, banked {expected[1]!r} — the "
            f"authority that postponed it is no longer this row's"
        )
    if row["period"] not in STOPPED_PERIODS:
        return (
            f"period is {row['period']!r} — the authority no longer reports "
            f"it stopped"
        )
    if row["home_score"] is None and row["away_score"] is None:
        return "already repaired"
    if (row["home_score"], row["away_score"]) != (expected[2], expected[3]):
        return (
            f"score drifted to {row['home_score']}-{row['away_score']} "
            f"(banked {expected[2]}-{expected[3]}) — this may be a real result"
        )
    return None


def snapshot_is_deletable(row: dict, repaired_event_ids: set[int]) -> str | None:
    """Return None when this snapshot may be deleted, else why it may not.

    Coupled to the event half: a snapshot goes only when its event was repaired
    in this same run, so hero and chart are corrected together or not at all.
    """
    expected = EXPECTED_SNAPSHOTS_BY_ID.get(row["id"])
    if expected is None:
        return "not in the pinned population"
    if row["event_id"] != expected[1]:
        return f"snapshot now belongs to event {row['event_id']}, banked {expected[1]}"
    if row["event_id"] not in repaired_event_ids:
        return (
            f"event {row['event_id']} was not repaired in this run — its 0-0 is "
            f"no longer evidenced as false"
        )
    if (row["home_score"], row["away_score"]) != (expected[2], expected[3]):
        return (
            f"score drifted to {row['home_score']}-{row['away_score']} "
            f"(banked {expected[2]}-{expected[3]})"
        )
    return None


async def bank_pre_image(session, writable: list[dict]) -> None:
    """Write the pre-image BEFORE the first UPDATE, or write nothing at all."""
    await session.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
                event_id         BIGINT PRIMARY KEY,
                prior_home_score INTEGER,
                prior_away_score INTEGER,
                banked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    for row in writable:
        # ON CONFLICT DO NOTHING: the FIRST pre-image is the true one.
        await session.execute(
            text(f"""
                INSERT INTO {BACKUP_TABLE}
                    (event_id, prior_home_score, prior_away_score)
                VALUES (:eid, :home, :away)
                ON CONFLICT (event_id) DO NOTHING
            """),
            {"eid": row["id"], "home": row["home_score"], "away": row["away_score"]},
        )


async def bank_snapshot_pre_image(session, deletable: list[dict]) -> None:
    """Bank whole snapshot rows, ORIGINAL ids included, before the first DELETE."""
    await session.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS {SNAPSHOT_BACKUP_TABLE} (
                snapshot_id BIGINT PRIMARY KEY,
                event_id    BIGINT NOT NULL,
                captured_at TIMESTAMPTZ NOT NULL,
                home_score  INTEGER NOT NULL,
                away_score  INTEGER NOT NULL,
                banked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    for row in deletable:
        await session.execute(
            text(f"""
                INSERT INTO {SNAPSHOT_BACKUP_TABLE}
                    (snapshot_id, event_id, captured_at, home_score, away_score)
                VALUES (:sid, :eid, :cap, :home, :away)
                ON CONFLICT (snapshot_id) DO NOTHING
            """),
            {
                "sid": row["id"], "eid": row["event_id"], "cap": row["captured_at"],
                "home": row["home_score"], "away": row["away_score"],
            },
        )


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    ids = ",".join(str(row[0]) for row in EXPECTED)
    async with get_task_session() as session:
        result = await session.execute(
            text(f"""
                SELECT id, status, completed_at, espn_id, period,
                       home_score, away_score,
                       home_team_name, away_team_name, commence_time
                  FROM events WHERE id IN ({ids}) ORDER BY commence_time
            """)
        )
        rows = [dict(r) for r in result.mappings()]

        writable: list[dict] = []
        skipped: list[tuple[int, str]] = []
        for row in rows:
            why = row_is_writable(row)
            if why is None:
                writable.append(row)
            else:
                skipped.append((row["id"], why))
        missing = sorted(set(EXPECTED_BY_ID) - {r["id"] for r in rows})

        repaired_event_ids = {row["id"] for row in writable}
        snap_result = await session.execute(
            text(f"""
                SELECT id, event_id, captured_at, home_score, away_score
                  FROM score_snapshots
                 WHERE event_id IN ({ids})
                 ORDER BY event_id, captured_at
            """)
        )
        snap_rows = [dict(r) for r in snap_result.mappings()]
        deletable: list[dict] = []
        snap_skipped: list[tuple[int, str]] = []
        for row in snap_rows:
            why = snapshot_is_deletable(row, repaired_event_ids)
            if why is None:
                deletable.append(row)
            else:
                snap_skipped.append((row["id"], why))
        snap_missing = sorted(
            set(EXPECTED_SNAPSHOTS_BY_ID) - {r["id"] for r in snap_rows}
        )

        # PIN FOR WRITES, CENSUS FOR VISIBILITY: the same shape outside the pin
        # is counted and printed, never written.
        unpinned = await session.execute(
            text(f"""
                SELECT id, espn_id, period, home_score, away_score FROM events
                 WHERE status = 'suspended' AND completed_at IS NULL
                   AND period IN ('Postponed', 'Canceled', 'Cancelled')
                   AND (home_score IS NOT NULL OR away_score IS NOT NULL)
                   AND id NOT IN ({ids})
                 ORDER BY id
            """)
        )
        strays = [dict(r) for r in unpinned.mappings()]

        print(f"#8960 — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  pinned              : {len(EXPECTED)}")
        print(f"  writable            : {len(writable)}")
        print(f"  skipped             : {len(skipped)}")
        print(f"  missing (no row)    : {len(missing)}{missing if missing else ''}")
        for row in writable:
            print(
                f"    {row['id']}  {row['commence_time']:%Y-%m-%d %H:%M}Z  "
                f"{row['home_team_name']} v {row['away_team_name']}  "
                f"{row['period']}  {row['home_score']}-{row['away_score']} -> NULL/NULL"
            )
        for eid, why in skipped:
            print(f"    SKIP {eid}: {why}")
        print(f"  snapshots pinned    : {len(EXPECTED_SNAPSHOTS)}")
        print(f"  snapshots deletable : {len(deletable)}")
        print(f"  snapshots skipped   : {len(snap_skipped)}")
        print(
            f"  snapshots missing   : {len(snap_missing)}"
            f"{snap_missing if snap_missing else ''}"
        )
        for row in deletable:
            print(
                f"    snapshot {row['id']}  event {row['event_id']}  "
                f"{row['home_score']}-{row['away_score']}  "
                f"captured {row['captured_at']:%Y-%m-%d %H:%M}Z -> DELETE"
            )
        for sid, why in snap_skipped:
            print(f"    SKIP snapshot {sid}: {why}")
        if strays:
            print(
                f"\n  ⚠️  {len(strays)} row(s) in the defect shape are NOT pinned "
                f"and will NOT be written:"
            )
            for row in strays:
                print(
                    f"    {row['id']}  espn_id={row['espn_id']}  {row['period']}  "
                    f"{row['home_score']}-{row['away_score']}"
                )
            print(
                "    Read each one at the venue before adding it to EXPECTED — "
                "do NOT widen this into a sweep."
            )

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0
        if not writable and not deletable:
            print("\nnothing to write.")
            return 0

        await bank_pre_image(session, writable)
        written = 0
        for row in writable:
            # Re-assert the defect shape in the WHERE clause, so a row a sync
            # pass changed between the SELECT and here is not written on a
            # stale read. Its absence is counted as drift.
            result = await session.execute(
                text("""
                    UPDATE events
                       SET home_score = NULL, away_score = NULL
                     WHERE id = :eid
                       AND status = 'suspended'
                       AND completed_at IS NULL
                       AND espn_id = :espn_id
                       AND period IN ('Postponed', 'Canceled', 'Cancelled')
                       AND home_score = :home
                       AND away_score = :away
                """),
                {
                    "eid": row["id"], "espn_id": row["espn_id"],
                    "home": row["home_score"], "away": row["away_score"],
                },
            )
            written += result.rowcount or 0

        # Same transaction as the hero rows: the page must never serve a blank
        # hero over a false chart row.
        await bank_snapshot_pre_image(session, deletable)
        deleted = 0
        for row in deletable:
            result = await session.execute(
                text("""
                    DELETE FROM score_snapshots
                     WHERE id = :sid
                       AND event_id = :eid
                       AND home_score = :home
                       AND away_score = :away
                """),
                {
                    "sid": row["id"], "eid": row["event_id"],
                    "home": row["home_score"], "away": row["away_score"],
                },
            )
            deleted += result.rowcount or 0

        await session.commit()

        drift = len(writable) - written
        snap_drift = len(deletable) - deleted
        print(f"\n  pre-image banked in : {BACKUP_TABLE}")
        print(f"  rows written        : {written}")
        print(f"  concurrent_drift    : {drift}")
        print(f"  snapshot bank       : {SNAPSHOT_BACKUP_TABLE}")
        print(f"  snapshots deleted   : {deleted}")
        print(f"  snapshot_drift      : {snap_drift}")
        print(
            f"\nverify hero : SELECT id, home_score, away_score FROM events "
            f"WHERE id IN ({ids});  -- expect NULL/NULL"
        )
        print(
            f"verify chart: SELECT count(*) FROM score_snapshots "
            f"WHERE event_id IN ({ids});  -- expect 0"
        )
        print(
            "undo: python3 scripts/restore_8960_postponed_filler_scoreboards.py --apply"
        )
        return 0 if (drift == 0 and snap_drift == 0) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
