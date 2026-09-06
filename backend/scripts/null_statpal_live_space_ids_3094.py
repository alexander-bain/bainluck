#!/usr/bin/env python3
"""#3094 — clear the MLB StatPal ids that are in the LIVE id space, reversibly.

WHAT THIS DOES
--------------
`events.statpal_fixture_id` is supposed to hold the id from StatPal's *schedule*
space — the venue's `id`, six digits. For MLB, the *live* feed reports a
different id entirely (the venue's `stats_id`, ten digits), and until #3094
shipped the live pass wrote that value into the column. Production holds **364**
such rows, all `baseball_mlb`, all ten digits.

A ten-digit value in that column is not a bad id, it is an id in the wrong
space: it reads as authoritative and dereferences to nothing on every endpoint
that takes a schedule id. This script sets those rows back to "we do not know",
so the schedule pass can anchor them correctly and for free.

THE MECHANISM FIX MUST BE LIVE FIRST, AND THE COUNT IS HOW YOU KNOW
-------------------------------------------------------------------
#3094's mechanism (`_live_anchor_id`, `STATPAL_LIVE_ANCHOR_FIELD`) shipped in
v4238. The population has been FROZEN at 364 ever since; under the old code
2026-09-07 alone would have added ~14. **Re-read the count before applying (the
`--report` census does it). If it has moved off 364, the mechanism fix is
incomplete and this repair waits** — clearing rows while a writer is still
refilling them is a loop, not a repair.

WHY NULL, AND NOT A RE-KEY
--------------------------
Both writers are write-once guarded — `statpal_sync.py` L328 and L1198 both read
`and not _get_statpal_id(event)` — so a cleared row becomes *eligible* again and
the next schedule pass anchors it correctly, with no bespoke matcher in a place
that must not guess. NULL converges on the same end state as a re-key, one cycle
later.

The venue's schedule publishes both ids on the same row (`id` and `stats_id`),
so a re-key looks tempting. It is not:

  * **`stats_id` is not unique in the venue's own schedule.** Measured
    2026-09-06 against the live window: 141 rows carry a `stats_id` and 13 of
    those values each name TWO different six-digit `id`s. The venue's mapping is
    not a function, so an "exact" re-key would have to guess for those.
  * Only **2** of our 364 have their `stats_id` in the venue's current window at
    all, so a re-key on that key buys almost nothing anyway.

Re-keying costs a guess in the one place that must not guess, and buys two rows.

**NULL is self-correcting where a re-key is not.** The action asserts only "we do
not know this game's anchor id", which is true of every row it touches and
recoverable by the normal pass. That is why the selection below can be a shape
test without that being a D55 violation: D55 governs how an anchor KEY is
constructed (explicitly, never inferred from digit count), and this script
constructs no key. It only decides which rows to forget.

WHAT TO EXPECT — STATE THIS BEFORE RUNNING IT, A RISING 6-DIGIT COUNT PROVES NOTHING
-------------------------------------------------------------------------------------
Measured against the venue's live window on 2026-09-06 at 23:5xZ:

    10-digit MLB rows           364  ->  0
    6-digit MLB rows           1653  ->  ~1728   (+75, NOT +364)
    rows left NULL, correctly          ~289

**75**, not the 91 an earlier measurement gave: the venue's `season-schedule` is
a ~17-day ROLLING window (`01.09 -> 14.09`, 177 games today; it was
`31.08 -> 17.09`, 233 games, two days ago). It slid AND shrank, so the reachable
set decays by roughly a day per day. Every day this waits costs ~5-15 rows off
the back. The 75 match the venue exactly and unambiguously on
`(UTC datetime, home, away)` — **0** of them ambiguous, which is the measurement
that retires authority/016's "22 invented doubleheaders" (that was an artifact of
a *day* key; on a UTC day key 64/364 collide, on the exact datetime none do).

The ~289 that stay NULL are correct: a NULL is an honest "we do not know", and
is strictly better than the wrong-space id it replaces.

THE JSONB HALF — DO NOT SKIP IT
-------------------------------
`_get_statpal_id` (L1530) prefers the column and **falls back to
`win_probability_sources->>'statpal_fixture_id'`**. 21 of the 364 carry the id in
BOTH places. Clearing only the column would leave the getter still returning the
stale ten-digit id, so the write-once guard would still fire and those 21 rows
would never re-anchor — while the column read NULL and the row LOOKED repaired.
That is a worse state than not running at all, because it is invisible. This
script clears both, and the backup records which of the two the row actually had
so `--rollback` does not invent a JSONB key that was never there.

(Measured: 343 column-only, 21 column+JSONB, and **0** rows with a JSONB value
and no column — so the column is a superset and the population is exactly 364.)

THE RAIL
--------
TCP 5432 egress is blocked from an agent sandbox, so `pg:psql` cannot reach the
database. A detached one-off dyno runs inside Heroku's network:

    heroku run:detached -a bainluck -- python3 scripts/null_statpal_live_space_ids_3094.py --report
    heroku run:detached -a bainluck -- python3 scripts/null_statpal_live_space_ids_3094.py
    heroku run:detached -a bainluck -- python3 scripts/null_statpal_live_space_ids_3094.py --apply
    heroku run:detached -a bainluck -- python3 scripts/null_statpal_live_space_ids_3094.py --rollback

Default is a DRY RUN. Scripts live at `/app`, not `/app/backend` — a
`cd backend &&` prefix silently no-ops. Verify by census afterwards, never by the
dyno's stdout: a non-detached `heroku run` does not execute at all in the sandbox
(gotcha #48), and an empty stdout is not evidence of anything.

REVERSIBILITY (D51)
-------------------
`--apply` creates `events_statpal_live_space_backup_3094` holding every row it is
about to touch — `event_id`, the column value, and the JSONB value with a flag
saying whether the key was present — in the same transaction as the writes, so
there is no state in which rows have moved and the backup has not. The backup
table is left in place afterwards on purpose: a backup deleted at the end of the
run is a backup that exists only while nothing has gone wrong yet.

The undo is a genuine undo and the round trip is executed, not argued:
`backend/tests/integration/test_null_statpal_live_space_3094_real_postgres.py`
seeds all three shapes against a real PostgreSQL, applies, and rolls back.

`--rollback` restores by `event_id`, which is a real primary key and is not
reused, so this script has none of the reused-BIGSERIAL hazard that CERT-847
found in the anchor re-key. It still asks the post-condition — *is every
backed-up row back verbatim?* — rather than trusting two rowcounts, because a
rowcount cannot see a row that was legitimately declined.
"""

from __future__ import annotations

import argparse
import os
import sys

BACKUP_TABLE = "events_statpal_live_space_backup_3094"

#: The population, stated once and shared by every statement below.
#:
#: Scoped to `baseball_mlb` because MLB is the only sport in
#: `STATPAL_LIVE_ANCHOR_FIELD` — the only sport whose live feed reports a
#: different id space at all. NBA's 141 seven-digit rows are a DIFFERENT
#: question and this script must not touch them.
#:
#: The shape test is `^[0-9]{10}$` exactly, not `length > 6`: the venue's
#: schedule ids are six digits (177/177 in today's window) and its `stats_id`
#: values are ten, and a row that is neither is something this script has not
#: measured and has no business forgetting.
POPULATION = """
    e.statpal_fixture_id ~ '^[0-9]{10}$'
    AND s.key = 'baseball_mlb'
"""

#: 🔴 `jsonb ? key` yields **NULL, not false**, when the column itself is NULL,
#: and `win_probability_sources` is nullable. Without the COALESCE,
#: `jsonb_had_key` is NULL for exactly those rows, and every later comparison
#: against it — `= b.jsonb_had_key` in the post-condition, `CASE WHEN
#: b.jsonb_had_key` in the restore — goes three-valued. The post-condition would
#: then report those rows as permanently unrestored after a restore that in fact
#: put them back perfectly, which is the specific way this script would lie
#: about its own undo. Store a real boolean.
CREATE_BACKUP = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS
SELECT e.id AS event_id,
       e.statpal_fixture_id,
       COALESCE(e.win_probability_sources ? 'statpal_fixture_id', false)
           AS jsonb_had_key,
       e.win_probability_sources->>'statpal_fixture_id' AS jsonb_value
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE {POPULATION}
"""

#: Both halves in ONE statement. They must not be separable: a run that cleared
#: the column and then failed before the JSONB would leave exactly the invisible
#: half-repaired state the docstring warns about.
CLEAR_BOTH = f"""
UPDATE events e
   SET statpal_fixture_id = NULL,
       win_probability_sources =
           CASE WHEN e.win_probability_sources ? 'statpal_fixture_id'
                THEN e.win_probability_sources - 'statpal_fixture_id'
                ELSE e.win_probability_sources
           END
  FROM sports s
 WHERE s.id = e.sport_id
   AND {POPULATION}
"""

#: Undo. Keyed on `event_id`, a primary key that is never reused, so unlike the
#: anchor re-key (CERT-847) there is no resurrection arm and no reused-key
#: hazard. The JSONB key is re-added ONLY where the backup says it was there —
#: writing it unconditionally would hand 343 rows a key they never had, which is
#: a mutation wearing a restore's clothes.
#:
#: The guard tests BOTH halves, not just the column. A guard reading only
#: `statpal_fixture_id IS DISTINCT FROM ...` skips any row whose column already
#: matches while its JSONB key is still missing — the restore declines, no error,
#: and the row lands in `COUNT_UNRESTORED` as an unexplained shortfall. That
#: state is not reachable from a clean apply, but the guard must not be the
#: reason a partial restore cannot be finished by re-running the undo.
#:
#: 🔴 THE `ELSE` ARM REMOVES THE KEY. IT MUST NOT PRESERVE IT (CERT-2147).
#:
#: The undo does not run against the state the apply left; it runs against the
#: state the SCHEDULE PASS left, and that pass is the entire point of NULLing.
#: On a re-anchor `_set_statpal_id` writes BOTH halves — the column AND a fresh
#: six-digit JSONB key. So a column-only row (343 of the 364, the majority) is
#: backed up with `jsonb_had_key = false`, gets a JSONB key it never had from the
#: re-anchor, and an `ELSE e.win_probability_sources` then RESTORES THE OLD
#: COLUMN WHILE KEEPING THE NEW KEY. The row ends holding a ten-digit column and
#: a six-digit JSONB key — a state that existed at no point in its history, and
#: one `_get_statpal_id` resolves to the ten-digit value while the row looks
#: half-repaired to anything reading the JSONB.
#:
#: Worse, it could not be fixed by running the undo again: the predicate fired
#: forever (presence still disagreed with the backup) and the `ELSE` preserved
#: the key every time. A restore that cannot converge is not a restore, and D51's
#: unattended grant is written against one that is.
#:
#: So `ELSE` subtracts the key, which is what "the backup says this row had no
#: JSONB key" actually means. `NULL - 'key'` is NULL, so a row with no
#: `win_probability_sources` at all stays untouched.
RESTORE = f"""
UPDATE events e
   SET statpal_fixture_id = b.statpal_fixture_id,
       win_probability_sources =
           CASE WHEN b.jsonb_had_key
                THEN jsonb_set(
                         COALESCE(e.win_probability_sources, '{{}}'::jsonb),
                         '{{statpal_fixture_id}}',
                         to_jsonb(b.jsonb_value)
                     )
                ELSE e.win_probability_sources - 'statpal_fixture_id'
           END
  FROM {BACKUP_TABLE} b
 WHERE e.id = b.event_id
   AND (
        e.statpal_fixture_id IS DISTINCT FROM b.statpal_fixture_id
        OR COALESCE(e.win_probability_sources ? 'statpal_fixture_id', false)
           IS DISTINCT FROM b.jsonb_had_key
        -- The VALUE, not just its presence (CERT-2147). A re-anchored row whose
        -- backup also had a key disagrees on neither the column nor the
        -- presence — both sides have one — while holding the schedule pass's
        -- six-digit id where the backup holds the ten-digit one. Presence alone
        -- cannot see that, and it is the 21-row case.
        OR e.win_probability_sources->>'statpal_fixture_id'
           IS DISTINCT FROM b.jsonb_value
   )
"""

#: The POST-CONDITION, not a rowcount: how many backed-up rows are still not
#: present verbatim once the restore has run — column AND JSONB, including the
#: "key was absent and must stay absent" case.
#:
#: Every comparison is NULL-safe on purpose. `statpal_fixture_id` is NULL for
#: every row this script has just cleared, `jsonb_value` is NULL for the 343
#: column-only rows, and `win_probability_sources` is itself nullable — so a `=`
#: anywhere here yields NULL rather than true, the EXISTS finds nothing, and the
#: script reports a total failure to restore immediately after a perfect one.
#: `IS NOT DISTINCT FROM` for the two nullable values, COALESCE for the boolean.
COUNT_UNRESTORED = f"""
SELECT count(*) FROM {BACKUP_TABLE} b
 WHERE NOT EXISTS (
       SELECT 1 FROM events e
        WHERE e.id = b.event_id
          AND e.statpal_fixture_id IS NOT DISTINCT FROM b.statpal_fixture_id
          AND COALESCE(e.win_probability_sources ? 'statpal_fixture_id', false)
              = b.jsonb_had_key
          AND e.win_probability_sources->>'statpal_fixture_id'
              IS NOT DISTINCT FROM b.jsonb_value
   )
"""

BACKUP_EXISTS = """
SELECT to_regclass(%s) IS NOT NULL
"""

#: The census is the guard, not decoration. `live_space` is the number that must
#: read 364 before an apply and 0 after; `schedule_space` is the number whose
#: RISE is the repair's only positive evidence — and it must rise by ~75, not by
#: ~364. A 6-digit count that merely goes up proves nothing.
CENSUS = """
SELECT CASE
         WHEN e.statpal_fixture_id ~ '^[0-9]{10}$' THEN 'live_space (10-digit)'
         WHEN e.statpal_fixture_id ~ '^[0-9]{6}$'  THEN 'schedule_space (6-digit)'
         WHEN e.statpal_fixture_id IS NULL         THEN 'null'
         ELSE 'other: ' || e.statpal_fixture_id
       END AS shape,
       count(*)
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = 'baseball_mlb'
   AND (e.statpal_fixture_id IS NOT NULL
        OR e.win_probability_sources ? 'statpal_fixture_id')
 GROUP BY 1 ORDER BY 1
"""

#: The JSONB fallback is the half that hides. Reported separately and by name so
#: an operator can see it go to zero rather than infer it from the column.
CENSUS_JSONB = """
SELECT count(*)
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = 'baseball_mlb'
   AND e.win_probability_sources->>'statpal_fixture_id' ~ '^[0-9]{10}$'
"""


def _connect():
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is unset — this must run on a Heroku dyno.")
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )
    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = False
    return conn


def census(cur, label: str) -> dict:
    """Print the shape census and return it, so a caller can assert on it."""
    cur.execute(CENSUS)
    shapes = {shape: n for shape, n in cur.fetchall()}
    for shape in sorted(shapes):
        print(f"[{label}] {shape}: {shapes[shape]}")
    cur.execute(CENSUS_JSONB)
    jsonb_live = cur.fetchone()[0]
    print(f"[{label}] jsonb fallback still in live space: {jsonb_live}")
    shapes["_jsonb_live_space"] = jsonb_live
    return shapes


def apply_clear(cur, *, dry_run: bool = False) -> dict:
    """Clear both halves for every live-space MLB row. Returns what it did.

    Does not commit — the caller owns the transaction, which is what lets a test
    drive the same statements the dyno runs.
    """
    cur.execute(f"""
        SELECT count(*),
               count(*) FILTER (WHERE e.win_probability_sources ? 'statpal_fixture_id')
          FROM events e JOIN sports s ON s.id = e.sport_id
         WHERE {POPULATION}
        """)
    planned, planned_jsonb = cur.fetchone()
    print(f"[plan] {planned} live-space MLB rows ({planned_jsonb} also in JSONB)")

    if dry_run:
        cur.execute(f"""
            SELECT e.id, e.statpal_fixture_id, e.status,
                   (e.win_probability_sources ? 'statpal_fixture_id')
              FROM events e JOIN sports s ON s.id = e.sport_id
             WHERE {POPULATION}
             ORDER BY e.commence_time DESC LIMIT 10
            """)
        for event_id, fid, status, in_jsonb in cur.fetchall():
            both = " +jsonb" if in_jsonb else ""
            print(f"[dry-run] event {event_id} ({status}): {fid} -> NULL{both}")
        return {"planned": planned, "planned_jsonb": planned_jsonb, "cleared": 0}

    # BEFORE the first write, in the same transaction as the writes.
    # `IF NOT EXISTS` makes a re-run safe and deliberately does NOT refresh an
    # existing backup: the first run's snapshot is the one that predates every
    # change, and overwriting it with a half-repaired copy is how a backup stops
    # being an undo.
    cur.execute(CREATE_BACKUP)
    cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE}")
    backed_up = cur.fetchone()[0]
    print(f"[backup] {BACKUP_TABLE} holds {backed_up} rows")

    cur.execute(CLEAR_BOTH)
    cleared = cur.rowcount or 0

    return {
        "planned": planned,
        "planned_jsonb": planned_jsonb,
        "backed_up": backed_up,
        "cleared": cleared,
    }


def rollback_clear(cur) -> dict:
    """Undo an `--apply`. Returns what it did. Does not commit."""
    cur.execute(BACKUP_EXISTS, (BACKUP_TABLE,))
    row = cur.fetchone()
    if not row or not row[0]:
        raise SystemExit(
            f"{BACKUP_TABLE} does not exist — there is nothing to roll back to. "
            f"An --apply creates it; a rollback without one would report a "
            f"successful restore of zero rows."
        )

    cur.execute(RESTORE)
    restored = cur.rowcount or 0

    # Asked AFTER the write, and it is the only claim worth making.
    cur.execute(COUNT_UNRESTORED)
    unrestored = cur.fetchone()[0]

    return {"restored": restored, "unrestored": unrestored}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument(
        "--rollback", action="store_true", help=f"restore from {BACKUP_TABLE}"
    )
    ap.add_argument("--report", action="store_true", help="census only, change nothing")
    args = ap.parse_args()

    conn = _connect()
    cur = conn.cursor()

    before = census(cur, "before")
    if args.report:
        conn.rollback()
        return 0

    if args.rollback:
        done = rollback_clear(cur)
        # COMMIT EVEN ON A PARTIAL RESTORE. Rolling the transaction back would
        # discard the rows that DID come back and leave strictly more damage
        # than it repaired; the rows are in the backup either way.
        conn.commit()
        print(f"[rollback] restored {done['restored']} rows from {BACKUP_TABLE}")
        census(cur, "after")
        if done["unrestored"]:
            print(
                f"[rollback] WARNING: {done['unrestored']} backed-up row(s) are "
                f"still NOT present verbatim. This is a PARTIAL restore. Do not "
                f"treat it as an undo; the rows are in {BACKUP_TABLE}."
            )
            # NON-ZERO, and this is the half of CERT-2147 that the SQL fix alone
            # does not answer. A partial restore that exits 0 is indistinguishable
            # from a clean undo to anything that reads the status rather than the
            # stdout — and the stdout of a detached dyno is not reliably readable
            # from the sandbox at all (gotcha #48), so the exit code is the only
            # signal an operator is certain to get. `1` is a result: the undo ran
            # and did not fully succeed.
            return 1
        print("[rollback] every backed-up row is present verbatim.")
        return 0

    done = apply_clear(cur, dry_run=not args.apply)

    if not args.apply:
        conn.rollback()
        print("[dry-run] nothing written. Re-run with --apply.")
        return 0

    conn.commit()
    print(f"[apply] cleared {done['cleared']} rows (column + JSONB)")
    after = census(cur, "after")

    # The repair's own acceptance test, run here rather than left to an
    # operator's eye: the live space must be empty, both halves.
    left = after.get("live_space (10-digit)", 0)
    left_jsonb = after.get("_jsonb_live_space", 0)
    if left or left_jsonb:
        print(
            f"[apply] WARNING: {left} column and {left_jsonb} JSONB live-space "
            f"rows remain. Expected 0 and 0."
        )
    else:
        print("[apply] live space is empty, column and JSONB.")
    print(
        f"[apply] schedule_space was "
        f"{before.get('schedule_space (6-digit)', 0)}, now "
        f"{after.get('schedule_space (6-digit)', 0)} — it should rise by ~75 over "
        f"the following schedule passes, NOT by {done['cleared']}."
    )
    print(
        "[undo]  heroku run:detached -a bainluck -- python3 "
        "scripts/null_statpal_live_space_ids_3094.py --rollback"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
