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

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0

        if not writable:
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
        await session.commit()

        drift = len(writable) - written
        print(f"\n  pre-image banked in : {BACKUP_TABLE}")
        print(f"  rows written        : {written}")
        print(f"  concurrent_drift    : {drift}")
        print(
            "\nverify: SELECT count(*) FROM events WHERE status='scheduled' "
            "AND completed_at IS NULL AND home_score IS NOT NULL;  -- expect 0"
        )
        print(
            "undo: python3 scripts/restore_8247_unstarted_straggler_scoreboards.py --apply"
        )
        return 0 if drift == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
