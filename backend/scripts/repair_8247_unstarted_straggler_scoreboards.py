"""#8247 — return the 0-0 scoreboards the straggler pass wrote onto games nobody played.

THE SHIP: a game played in April stops printing a `0 — 0` hero. Today a reader
opening ``/events/15290171`` — Chicago White Sox @ Toronto Blue Jays, scheduled
for **2026-04-02** and POSTPONED, read nearly six months later — is shown:

    hero        0  —  0
    caption     "No result reported · last score 0-0"
    chart       an orange "Actual Score Diff" point

Before the #5501 release those two columns were NULL and none of it rendered.
This repair puts them back to NULL on the 13 rows that took one, and the page
returns to printing nothing where it knows nothing.

A blank reads as "we do not know". A `0-0` reads as a fact, and on a game that
was never played it is false — which is why this is worth a repair and not a
shrug: the defect is not a missing number, it is a wrong one.

------------------------------------------------------------------------------
THE TWO HALVES, AND WHY THIS ONE RUNS SECOND
------------------------------------------------------------------------------

The gate is ``espn_helpers.update_event_fields_from_espn`` (#8247, same branch):
``allow_unstarted`` grants settling and no longer grants the scoreboard. THIS
SCRIPT IS THE OTHER HALF, and the order is load-bearing — the straggler pass
runs on a schedule, so applying it before the gate is live just means the rows
re-fill on the next sweep. Re-running afterwards is safe and idempotent; the
pre-image is banked ``ON CONFLICT DO NOTHING`` so a second run can never
overwrite the true pre-image with the state the first run produced.

------------------------------------------------------------------------------
THE POPULATION, MEASURED AND PINNED
------------------------------------------------------------------------------

Production 2026-09-23 (read-only), every `scheduled` row carrying any live
state, grouped by shape:

    has_score  period       clock    rows
    True       'Postponed'  '0:00'     13   <- THIS REPAIR
    False      'Postponed'  "0'"        1
    False      'Postponed'  '0:00'      1

All 13 are MLB, all postponed, all exactly `0-0`, commence_time 2026-04-02 to
2026-07-28. :data:`EXPECTED` pins them BY ID, and each row is re-verified against
its banked shape at apply time — a row that has drifted is skipped and counted,
never written.

🔴 THE PREDICATE IS NOT THE POPULATION. The obvious sweep —
``status='scheduled' AND completed_at IS NULL AND home_score IS NOT NULL`` —
is the right shape today and the wrong thing to ship. A genuinely LIVE 0-0 game
mis-stamped `scheduled` is #5324's whole class, it is a real and recurring state,
and this predicate would blank its scoreboard mid-game. Pinning the ids is what
keeps a repair for 13 postponed games from becoming a rule about live ones.

The two score-less rows are deliberately OUT OF SCOPE. They prove
``period='Postponed'`` reaches `scheduled` rows by some path that never wrote a
score, so those two columns' pre-image is NOT mine to assert — see below.

------------------------------------------------------------------------------
WHY ONLY TWO COLUMNS COME BACK
------------------------------------------------------------------------------

The defect wrote four: `home_score`, `away_score`, `period` ('Postponed') and
`game_clock` ('0:00'). Only the two scores are returned here.

* The scores' pre-image is PROVEN NULL, by id. #5501's own after-check arm 4 —
  ``id IN (<the 328 banked ids>) AND status='scheduled' AND home_score IS NOT
  NULL`` — read **0** at 14:53Z pre-merge and 0 again at 15:22Z, and all 13 of
  these ids are in that banked set (13/13). The count went 0 → 7 → 12 → 13 after
  the release. Banking by id rather than by count is what makes that a pre-image
  and not an inference.
* `period`/`game_clock` have NO such proof: the two score-less rows above carry
  the identical 'Postponed' shape, so that value demonstrably arrives by a path
  this regression is not, and I would be guessing at what these 13 held before.
  Restoring a value you cannot evidence is not a repair, it is a second write.
  They are left alone, and they render nothing on their own.

Either way the *current* value is what justifies the write: `0-0` on a game that
was never played is false whatever preceded it, and NULL is the honest value.

------------------------------------------------------------------------------
HOW TO RUN IT (D51(b): backup first, one-command restore)
------------------------------------------------------------------------------

Dry run (default, writes nothing, prints the plan):

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_8247_unstarted_straggler_scoreboards.py

Apply, AFTER the #8247 gate is live on the app that runs the straggler pass:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_8247_unstarted_straggler_scoreboards.py --apply

The undo is one command:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_8247_unstarted_straggler_scoreboards.py --apply

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
# however the file is loaded (`python3 scripts/…` puts `scripts/` on the path for
# free; importing the file by its path — the guard test does — does not).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402

#: Only this app may run it. The repair writes production rows, and notice 47(c)
#: makes the attended invocation itself the gate that keeps the runtime DDL below
#: out of migration class.
PRODUCER_APP = "bainluck-heavy"

#: Pre-image lives here. Plain `backup_*`, created on demand under `--apply`.
BACKUP_TABLE = "backup_8247_unstarted_straggler_scoreboards"

#: The 13 rows, pinned by id and by the shape each one must still be in.
#: `(event_id, home_score, away_score)` — every one is 0-0, and the tuple is
#: asserted rather than assumed so a row that has since taken a REAL score (the
#: game was made up and played) is skipped instead of blanked.
EXPECTED: tuple[tuple[int, int, int], ...] = (
    (15290171, 0, 0),  # 2026-04-02  Chicago White Sox @ Toronto Blue Jays
    (15290172, 0, 0),  # 2026-04-04  Cleveland Guardians @ Chicago Cubs
    (15290173, 0, 0),  # 2026-04-25  New York Mets @ Colorado Rockies
    (15290174, 0, 0),  # 2026-04-29  Baltimore Orioles @ Houston Astros
    (15290177, 0, 0),  # 2026-05-05  St. Louis Cardinals @ Milwaukee Brewers
    (15290178, 0, 0),  # 2026-05-24  Cincinnati Reds @ St. Louis Cardinals
    (15290215, 0, 0),  # 2026-06-06  New York Yankees @ Boston Red Sox
    (15290351, 0, 0),  # 2026-07-10  Pittsburgh Pirates @ Milwaukee Brewers
    (15290359, 0, 0),  # 2026-07-17  Cleveland Guardians @ Pittsburgh Pirates
    (15290362, 0, 0),  # 2026-07-19  New York Yankees @ Los Angeles Dodgers
    (15290373, 0, 0),  # 2026-07-21  Boston Red Sox @ Baltimore Orioles
    (15290374, 0, 0),  # 2026-07-21  New York Yankees @ Pittsburgh Pirates
    (15290402, 0, 0),  # 2026-07-28  New York Mets @ Atlanta Braves
)

EXPECTED_BY_ID = {row[0]: row for row in EXPECTED}

#: ── THE SECOND TABLE THE BAD WRITE TOUCHED (CERT-3346's required repair) ──
#:
#: Clearing `events.home_score/away_score` clears the HERO and nothing else. The
#: chart is served by `GET /api/events/{id}/history`, which builds `score_history`
#: straight out of `score_snapshots` (`routes/events.py`, the `ScoreSnapshot`
#: select) — a different table this repair never touched. So the repair as first
#: written would have taken the false `0 — 0` off the hero and LEFT the false
#: orange point on the chart: the same untruth, one surface further down the page,
#: and harder to see because the hero now looks fixed.
#:
#: Measured on production 2026-09-23 16:52Z, and the served route confirms it:
#:
#:     GET /api/events/15290171/history
#:       score_history -> [{"timestamp": "2026-09-23T15:26:57...", 0, 0}]
#:
#: One point, 0-0, on a game played 2026-04-02.
#:
#: WHY THESE ROWS ARE PROVABLY FALSE, AND NOT BY A DATE LITERAL. Each snapshot
#: was captured between 15:24Z and 15:32Z on 2026-09-23 — from 56 to 173 DAYS
#: after its own game's `commence_time`. `score_snapshots` exists to track live
#: score progression; a live capture cannot lag the game it captures by two
#: months. That lag is the mechanism, so it is what the predicate below tests,
#: with the date pin only as the belt to its braces.
SNAPSHOT_BACKUP_TABLE = "backup_8247_unstarted_straggler_snapshots"

#: A snapshot whose capture lags its own game's start by less than this could be
#: a real live capture, and is never deleted however 0-0 it looks. The 13 below
#: clear it by a factor of fifty; the bar exists for the row that does not.
MIN_POST_GAME_LAG_HOURS = 24

#: Pinned BY SNAPSHOT ID, for the same reason the events are: the predicate is
#: not the population. `(snapshot_id, event_id, home_score, away_score)`.
EXPECTED_SNAPSHOTS: tuple[tuple[int, int, int, int], ...] = (
    (396619, 15290171, 0, 0),  # captured 15:26:57Z, game 2026-04-02, lag 173d
    (396620, 15290172, 0, 0),  # captured 15:26:57Z, game 2026-04-04, lag 171d
    (396614, 15290173, 0, 0),  # captured 15:25:56Z, game 2026-04-25, lag 150d
    (396615, 15290174, 0, 0),  # captured 15:25:56Z, game 2026-04-29, lag 146d
    (396618, 15290177, 0, 0),  # captured 15:25:56Z, game 2026-05-05, lag 140d
    (396621, 15290178, 0, 0),  # captured 15:26:57Z, game 2026-05-24, lag 121d
    (396607, 15290215, 0, 0),  # captured 15:24:56Z, game 2026-06-06, lag 108d
    (396671, 15290351, 0, 0),  # captured 15:29:57Z, game 2026-07-10, lag  74d
    (396678, 15290359, 0, 0),  # captured 15:29:57Z, game 2026-07-17, lag  67d
    (396680, 15290362, 0, 0),  # captured 15:30:57Z, game 2026-07-19, lag  66d
    (396699, 15290373, 0, 0),  # captured 15:30:57Z, game 2026-07-21, lag  63d
    (396700, 15290374, 0, 0),  # captured 15:30:57Z, game 2026-07-21, lag  63d
    (396724, 15290402, 0, 0),  # captured 15:32:57Z, game 2026-07-28, lag  56d
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

    PURE, and per-row: it is handed one row's current state and nothing about
    the batch. Every condition is a reason the 0-0 might NOT be the defect —
    a settled row, a row that moved off `scheduled`, or a row carrying a real
    score — and each of those is a row this repair must leave exactly alone.
    """
    expected = EXPECTED_BY_ID.get(row["id"])
    if expected is None:
        return "not in the pinned population"
    if row["status"] != "scheduled":
        return f"status moved to {row['status']!r} — no longer the defect shape"
    if row["completed_at"] is not None:
        return "row has since been settled — its score is now a result"
    if row["home_score"] is None and row["away_score"] is None:
        return "already repaired"
    if (row["home_score"], row["away_score"]) != (expected[1], expected[2]):
        return (
            f"score drifted to {row['home_score']}-{row['away_score']} "
            f"(banked {expected[1]}-{expected[2]}) — this may be a real result"
        )
    return None


def snapshot_is_deletable(row: dict, repaired_event_ids: set[int]) -> str | None:
    """Return None when this snapshot may be deleted, else why it may not.

    PURE, and per-row. `row` carries the snapshot's own columns plus its event's
    `commence_time`, which is what makes the lag test possible without a second
    query.

    THE COUPLING IS THE POINT. A snapshot is deleted only when its EVENT was
    actually repaired in this same run. If the event was skipped — it took a
    real score, it settled, it left `scheduled` — then its 0-0 snapshot is no
    longer evidenced as false and this repair has no business touching it. That
    makes the two halves of the cleanup impossible to drift apart: the hero and
    the chart are corrected together or neither is.
    """
    expected = EXPECTED_SNAPSHOTS_BY_ID.get(row["id"])
    if expected is None:
        return "not in the pinned population"
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
    if row["commence_time"] is None:
        return "event has no commence_time — the lag test cannot be evaluated"
    lag_hours = (row["captured_at"] - row["commence_time"]).total_seconds() / 3600
    if lag_hours < MIN_POST_GAME_LAG_HOURS:
        return (
            f"captured {lag_hours:.1f}h after kickoff — inside the "
            f"{MIN_POST_GAME_LAG_HOURS}h window, so it may be a real live capture"
        )
    return None


async def bank_snapshot_pre_image(session, deletable: list[dict]) -> None:
    """Bank whole snapshot rows BEFORE the first DELETE, ids included.

    The id is banked as a plain column, not as the backup table's own primary
    key, so the restore can put the row back under its ORIGINAL id — a restored
    chart point that arrives with a new id is a different row wearing the same
    values, and `score_snapshots.id` is what the server orders and dedups on.
    """
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
        # ON CONFLICT DO NOTHING for the same reason the event bank uses it: the
        # FIRST pre-image is the true one.
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
        # ON CONFLICT DO NOTHING: the FIRST pre-image is the true one. A second
        # run must never overwrite it with the state the first run produced —
        # that would quietly make the undo a no-op.
        await session.execute(
            text(f"""
                INSERT INTO {BACKUP_TABLE}
                    (event_id, prior_home_score, prior_away_score)
                VALUES (:eid, :home, :away)
                ON CONFLICT (event_id) DO NOTHING
            """),
            {"eid": row["id"], "home": row["home_score"], "away": row["away_score"]},
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
                SELECT id, status, completed_at, home_score, away_score,
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

        # PIN FOR WRITES, CENSUS FOR VISIBILITY. The pin above is what keeps
        # this repair off a live 0-0 mis-stamped `scheduled`, and it is also a
        # snapshot that can go stale: the gate stops NEW rows taking a
        # scoreboard, but any that landed between the measurement and the gate
        # going live are not in it. Silently ignoring them would leave the
        # operator's verify query returning a number nobody can explain, which
        # is the failure mode a pinned population invites. So the shape is
        # counted — read-only, never written — and reported by id.
        unpinned = await session.execute(
            text(f"""
                SELECT id, home_score, away_score FROM events
                 WHERE status = 'scheduled' AND completed_at IS NULL
                   AND (home_score IS NOT NULL OR away_score IS NOT NULL)
                   AND id NOT IN ({ids})
                 ORDER BY id
            """)
        )
        strays = [dict(r) for r in unpinned.mappings()]

        # ── THE CHART'S HALF (CERT-3346) ──
        # Read on the pinned EVENT ids, not on the pinned snapshot ids, so that
        # a false snapshot this population gained after 16:52Z is SEEN by the
        # census below instead of falling silently outside both reads.
        repaired_event_ids = {row["id"] for row in writable}
        snap_result = await session.execute(
            text(f"""
                SELECT ss.id, ss.event_id, ss.captured_at,
                       ss.home_score, ss.away_score, e.commence_time
                  FROM score_snapshots ss
                  JOIN events e ON e.id = ss.event_id
                 WHERE ss.event_id IN ({ids})
                 ORDER BY ss.event_id, ss.captured_at
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

        print(f"#8247 — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  pinned              : {len(EXPECTED)}")
        print(f"  writable            : {len(writable)}")
        print(f"  skipped (drifted)   : {len(skipped)}")
        print(f"  missing (no row)    : {len(missing)}{missing if missing else ''}")
        for row in writable:
            print(
                f"    {row['id']}  {row['commence_time']:%Y-%m-%d}  "
                f"{row['away_team_name']} @ {row['home_team_name']}  "
                f"{row['home_score']}-{row['away_score']} -> NULL/NULL"
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
            lag_days = (row["captured_at"] - row["commence_time"]).days
            print(
                f"    snapshot {row['id']}  event {row['event_id']}  "
                f"{row['home_score']}-{row['away_score']}  "
                f"captured {row['captured_at']:%Y-%m-%d %H:%M}Z, "
                f"{lag_days}d after kickoff -> DELETE"
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
                    f"    {row['id']}  {row['home_score']}-{row['away_score']}"
                )
            print(
                "    Each is either a row that took a scoreboard after the "
                "population was measured\n"
                "    (2026-09-23) or a genuinely LIVE game mis-stamped "
                "`scheduled` (#5324's class).\n"
                "    Tell them apart at the venue before adding any id to "
                "EXPECTED — do NOT widen\n"
                "    this into a sweep."
            )

        # Same census discipline for the chart's half: a snapshot in the defect
        # SHAPE — 0-0, captured more than a day after its own game started —
        # that is not pinned is reported and never written. Measured 0 outside
        # the pin at 16:52Z; the read exists so a later operator finds out when
        # that stops being true, instead of the pin going quietly stale.
        snap_unpinned = await session.execute(
            text(f"""
                SELECT ss.id, ss.event_id, ss.captured_at, e.commence_time
                  FROM score_snapshots ss
                  JOIN events e ON e.id = ss.event_id
                 WHERE ss.home_score = 0 AND ss.away_score = 0
                   AND ss.captured_at > e.commence_time
                                        + make_interval(hours => {MIN_POST_GAME_LAG_HOURS})
                   AND e.status = 'scheduled'
                   AND e.completed_at IS NULL
                   AND ss.event_id NOT IN ({ids})
                 ORDER BY ss.id
            """)
        )
        snap_strays = [dict(r) for r in snap_unpinned.mappings()]
        if snap_strays:
            print(
                f"\n  ⚠️  {len(snap_strays)} snapshot(s) in the defect shape are "
                f"NOT pinned and will NOT be deleted:"
            )
            for row in snap_strays:
                print(f"    snapshot {row['id']}  event {row['event_id']}")
            print(
                "    Evidence each one at the venue before adding it to "
                "EXPECTED_SNAPSHOTS.\n"
                "    Do NOT widen this into a sweep."
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
            # Re-assert the defect shape IN THE WHERE CLAUSE, so a row the
            # straggler pass changed between the SELECT above and this UPDATE is
            # not written on a stale read. Its absence is counted as drift.
            result = await session.execute(
                text("""
                    UPDATE events
                       SET home_score = NULL, away_score = NULL
                     WHERE id = :eid
                       AND status = 'scheduled'
                       AND completed_at IS NULL
                       AND home_score = :home
                       AND away_score = :away
                """),
                {"eid": row["id"], "home": row["home_score"], "away": row["away_score"]},
            )
            written += result.rowcount or 0

        # The chart's half, in the SAME transaction as the hero's. A commit
        # between them is a window in which the page serves a blank hero over a
        # false chart point — the two surfaces disagreeing is worse than either
        # being wrong, and a reader who reloads inside it sees exactly that.
        await bank_snapshot_pre_image(session, deletable)
        deleted = 0
        for row in deletable:
            # Re-assert the defect shape in the WHERE clause, same as the event
            # UPDATE: a snapshot that changed between the SELECT and here is not
            # deleted on a stale read, and its absence is counted as drift.
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
            "\nverify hero : SELECT count(*) FROM events WHERE status='scheduled' "
            "AND completed_at IS NULL AND home_score IS NOT NULL;  -- expect 0"
        )
        print(
            "verify chart: curl -s $BAINLUCK_API/api/events/15290171/history "
            "| python3 -c \"import json,sys; "
            "print(json.load(sys.stdin)['score_history'])\"  -- expect []"
        )
        print(
            "undo: python3 scripts/restore_8247_unstarted_straggler_scoreboards.py --apply"
        )
        return 0 if (drift == 0 and snap_drift == 0) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
