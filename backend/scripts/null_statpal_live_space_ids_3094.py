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
2026-09-07 alone would have added ~14. **If it has moved off 364, the mechanism
fix is incomplete and this repair waits** — clearing rows while a writer is
still refilling them is a loop, not a repair.

THE SCRIPT NOW ENFORCES THAT ITSELF (it used to only print it). Every mode
measures the population by the same predicate `--apply` clears on and prints a
`[precondition]` verdict; `--apply` and the dry run both REFUSE with exit 1 on
any count that is neither 364 nor 0. Zero is not a mismatch — it means the apply
has already run, and a re-run is a harmless no-op. `--rollback` is exempt,
because it is the way out of a bad state and must never be blocked by one.

A count that has FALLEN refuses too: a rise means the writer is still refilling,
a fall means something cleared rows this script never backed up, and neither is
a state this repair has measured. To proceed on a genuinely new number, re-measure,
find the writer, then say the number out loud with `--expect-population N` —
which exists so that the way past the guard is a stated measurement rather than
an edit to the guard.

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
about to touch — `event_id`, the column value, the JSONB value, a flag saying
whether the key was present, and a second flag saying whether the whole JSONB
column was NULL — in the same transaction as the writes, so there is no state in
which rows have moved and the backup has not. The backup table is left in place
afterwards on purpose: a backup deleted at the end of the run is a backup that
exists only while nothing has gone wrong yet.

**THE UNDO RUNS AGAINST THE STATE THE SCHEDULE PASS LEFT, NOT THE ONE THE APPLY
LEFT** (CERT-2147). Re-anchoring is the whole point of NULLing, so by the time
anyone rolls back, `_set_statpal_id` has probably written BOTH halves again with
a correct six-digit id. That makes three states the JSONB column can be in —
NULL, `{}`, or populated — and two facts that are easy to conflate: *the column
was NULL* and *the column had no key*. The restore therefore re-adds the key
only where the backup says there was one, SUBTRACTS it where there was not, and
collapses to NULL only where the column was NULL and nothing else is left. The
emptiness guard is what stops it destroying a key some other writer added in
between; that key is deliberately kept, and that is not a failed restore.

Every clause in the restore's predicate has a matching clause in
`COUNT_UNRESTORED` and vice versa. A post-condition that can report a shortfall
the predicate cannot act on is a restore that never converges, however often it
is run — CERT-2147's actual finding, and the trap each later fix here has to
avoid re-opening somewhere new.

The undo is a genuine undo and the round trip is executed, not argued:
`backend/tests/integration/test_null_statpal_live_space_3094_real_postgres.py`
seeds every shape against a real PostgreSQL, applies, re-anchors as the schedule
pass would, rolls back, and rolls back a second time to prove convergence. It is
two-armed: `test_the_preserving_else_arm_cannot_pass_this` executes the BLOCKED
statement and requires it to leave the row wrong, so a green run means the
repair was proved necessary rather than merely unopposed.

`--rollback` restores by `event_id`, which is a real primary key and is not
reused, so this script has none of the reused-BIGSERIAL hazard that CERT-847
found in the anchor re-key. It still asks the post-condition — *is every
backed-up row back verbatim?* — rather than trusting two rowcounts, because a
rowcount cannot see a row that was legitimately declined.

TWO WAYS THE BACKUP CAN FAIL TO COVER WHAT THE RUN CLEARS (CERT-2171 follow-ups)
--------------------------------------------------------------------------------
Both are silent, and both end in the same place: rows moved, and the undo does
not hold them. Neither is reachable from a clean first run, and that is exactly
why nothing would have noticed.

**1. The population is measured and cleared under two different snapshots.**
The precondition counts, and then `CLEAR_BOTH` clears. Under READ COMMITTED
those are two statements at two moments, so a writer refilling rows in between
gets a `FROZEN 364` verdict and a 374-row clear — the very loop the frozen count
exists to refuse, waved through by the guard that was supposed to stop it. Every
non-rollback mode therefore runs at **`REPEATABLE READ`**, so the census, the
precondition count, the backup and the clear all see ONE snapshot; and
`apply_clear` re-measures the population and refuses if it disagrees with the
number the verdict was computed from, so if the isolation is ever weakened again
the mismatch is loud rather than silent. A concurrent write to a targeted row
now aborts the UPDATE with a serialization failure, which is the correct
outcome: nothing is written, and the writer this repair waits on has announced
itself. `--rollback` stays at READ COMMITTED deliberately — it is the way OUT of
a bad state and must never be the thing a concurrent writer can block.

**2. A repeat apply clears rows the PRESERVED backup has never held.**
`CREATE TABLE IF NOT EXISTS` not refreshing the snapshot is the right rule and a
trap with a second edge. The empty-table case is guarded below; this is the
non-empty one. Say the apply ran and backed up its 364, and later a writer
refills ten rows — or an operator states the new number with
`--expect-population 10`. The table exists and is not empty, so the emptiness
guard passes, and those ten rows are cleared against a snapshot taken before
they were ever in this shape. `--rollback` would then restore 364 rows verbatim
and report a clean undo, while ten rows it never knew about stay cleared. So the
run counts its candidates that are ABSENT from the preserved backup and refuses
before writing if there are any. The remedy is never to drop the table — that
discards a real undo for the rows it does hold — but to undo first, or to
archive it under a dated name so both snapshots survive.
"""

from __future__ import annotations

import argparse
import os
import sys

BACKUP_TABLE = "events_statpal_live_space_backup_3094"

#: The frozen count from the header — the number of live-space rows that existed
#: once #3094's mechanism fix (v4238) stopped the writer refilling them.
#:
#: The header has always said "re-read the count before applying; if it has moved
#: off 364 the mechanism fix is incomplete and this repair waits". Until now that
#: was a sentence an operator had to obey, and `--apply` printed the measured
#: count and cleared whatever it found regardless. A precondition that only
#: prints is not a precondition: the run it exists to stop — clearing rows while
#: a writer is still refilling them, which is a loop and not a repair — is
#: exactly the run whose operator is least likely to be reading stdout, because a
#: detached dyno's stdout is not reliably readable from the sandbox at all
#: (gotcha #48). So the number is enforced here, and the exit code carries it.
EXPECTED_POPULATION = 364

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
#: `sources_was_null` records whether the whole JSONB column was NULL, which is
#: a THIRD state and not the same as "had no key". Subtracting a key from a
#: formerly-NULL column that the schedule pass has since populated leaves `{{}}`
#: — an empty object where the row held NULL. `_get_statpal_id` cannot tell the
#: difference, so nothing breaks, but it is not verbatim, and D51's grant is for
#: an undo rather than for an approximation of one.
CREATE_BACKUP = f"""
CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS
SELECT e.id AS event_id,
       e.statpal_fixture_id,
       COALESCE(e.win_probability_sources ? 'statpal_fixture_id', false)
           AS jsonb_had_key,
       e.win_probability_sources->>'statpal_fixture_id' AS jsonb_value,
       (e.win_probability_sources IS NULL) AS sources_was_null
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
                -- Subtract the key, and collapse to NULL only when the row held
                -- NULL before AND nothing else is left. A formerly-NULL column
                -- that the schedule pass populated would otherwise come back as
                -- `{{}}` — benign to `_get_statpal_id`, still not verbatim.
                -- Guarded on emptiness so a key some OTHER writer added between
                -- the apply and the undo is never destroyed by this arm.
                WHEN b.sources_was_null
                     AND (e.win_probability_sources - 'statpal_fixture_id')
                         IS NOT DISTINCT FROM '{{}}'::jsonb
                THEN NULL
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
        -- The bare-`{{}}` residue. Without this the row disagrees on nothing the
        -- clauses above can see — right column, no key, no value — so the
        -- restore declines and the empty object stays forever. Every predicate
        -- clause here must have a matching clause in `COUNT_UNRESTORED`, or the
        -- undo reports a shortfall it has no statement able to repair.
        OR (b.sources_was_null
            AND e.win_probability_sources IS NOT DISTINCT FROM '{{}}'::jsonb)
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
          -- The bare-`{{}}` residue, mirroring the restore's clause of the same
          -- name. Scoped to the EMPTY object on purpose: a formerly-NULL column
          -- that now holds real keys some other writer added is not this
          -- script's to undo, and demanding NULL there would be a shortfall no
          -- statement may repair — the non-convergence CERT-2147 found, in a
          -- new place.
          AND NOT (
              b.sources_was_null
              AND e.win_probability_sources IS NOT DISTINCT FROM '{{}}'::jsonb
          )
   )
"""

BACKUP_EXISTS = """
SELECT to_regclass(%s) IS NOT NULL
"""

#: How many rows THIS run would clear that the PRESERVED backup does not hold.
#:
#: Zero by construction on a first run — `CREATE_BACKUP` selects the same
#: population under the same snapshot — so any non-zero answer means the table
#: was left by an EARLIER run and does not cover what this one is about to
#: touch. Keyed on `event_id`, the same primary key `RESTORE` joins on, because
#: "the undo can find this row" is precisely the question being asked.
COUNT_UNCOVERED_BY_BACKUP = f"""
SELECT count(*)
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE {POPULATION}
   AND NOT EXISTS (
       SELECT 1 FROM {BACKUP_TABLE} b WHERE b.event_id = e.id
   )
"""

#: Every non-rollback mode runs here. See "TWO WAYS THE BACKUP CAN FAIL TO
#: COVER WHAT THE RUN CLEARS" above: under READ COMMITTED the precondition's
#: count and the UPDATE it gates are two snapshots, so the guard can pass on one
#: population while the write lands on another.
SNAPSHOT_ISOLATION = "REPEATABLE READ"

#: `--rollback` only. Named rather than left implicit: the exemption is a
#: decision, not an omission. A serialization failure aborts the transaction,
#: and aborting the undo is the one failure this script cannot afford — the
#: rollback must be able to run *while* the bad state it is undoing is being
#: written to.
ROLLBACK_ISOLATION = "READ COMMITTED"

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


def pin_isolation(conn, level: str) -> None:
    """Put every statement of this run on one snapshot (or deliberately not).

    Called before the first statement, because that is when a transaction's
    snapshot is taken and `set_session` refuses inside an open one. The
    `rollback()` first is what makes this safe to call on a connection a caller
    has already read from — nothing has been written yet at this point in any
    mode, so there is never anything to discard.

    Not wrapped in a try/except on purpose. A silently-degraded isolation level
    is the exact defect this exists to close: the guard would keep printing
    `FROZEN` while the clear ran on a population nobody measured.
    """
    conn.rollback()
    conn.set_session(isolation_level=level)


#: Counted by the SAME predicate `--apply` clears on, deliberately: a
#: precondition measured a different way from the write it gates is a
#: precondition about a different population. `census()` reports the column
#: shapes and is for a human; this is the number the refusal is computed from.
COUNT_POPULATION = f"""
SELECT count(*)
  FROM events e JOIN sports s ON s.id = e.sport_id
 WHERE {POPULATION}
"""


def count_population(cur) -> int:
    """How many rows `--apply` would clear, by the predicate it clears on."""
    cur.execute(COUNT_POPULATION)
    return cur.fetchone()[0]


def population_verdict(
    planned: int, *, expected: int = EXPECTED_POPULATION
) -> tuple[str, str]:
    """Classify the measured live-space population against the frozen count.

    Pure, and separated from the database on purpose: the refusal is the part of
    this script that must be provable without a live population to seed, and a
    guard that can only be tested by reproducing the failure it prevents tends
    not to be tested at all.

    Returns `(verdict, message)`. Three verdicts, and only `MOVED` refuses:

    ``FROZEN``
        The count is the one the mechanism fix froze. Proceed.
    ``ALREADY-APPLIED``
        Zero rows. The apply has run (or there was never anything to clear);
        re-running is a no-op and safe — `CLEAR_BOTH` matches nothing and
        `CREATE TABLE IF NOT EXISTS` deliberately does not refresh the snapshot.
    ``MOVED``
        Anything else. Note this refuses a count that has FALLEN as well as one
        that has risen: a rise means a writer is still refilling and the loop is
        live, but a fall means something cleared rows that this script did not
        back up, and neither number is a state this repair has measured. The
        header's rule is "if it has moved off 364", not "if it has grown".
    """
    if planned == expected:
        return (
            "FROZEN",
            f"{planned} live-space rows — the frozen count. Safe to apply.",
        )
    if planned == 0:
        return (
            "ALREADY-APPLIED",
            "0 live-space rows — nothing to clear. An --apply here is a no-op "
            "and will not refresh the existing backup.",
        )
    return (
        "MOVED",
        f"{planned} live-space rows, expected {expected}. The population has "
        f"MOVED OFF the frozen count, so #3094's mechanism fix is not holding "
        f"and clearing these rows would be a loop, not a repair. Re-measure, "
        f"find the writer, and only then re-run with "
        f"--expect-population {planned} to state the new number out loud.",
    )


def preserved_backup(cur) -> tuple[int, int] | None:
    """Read the backup an EARLIER run left behind, before this one writes.

    Returns `(rows, uncovered)` — how many rows the preserved table holds, and
    how many of THIS run's candidates it does not hold — or `None` when there is
    no backup table at all.

    Read before `CREATE_BACKUP` on purpose. Afterwards the two cases are
    indistinguishable: a table this run just created is full of exactly this
    run's rows, so it would answer `(planned, 0)` and the guards would have
    nothing to see. `None` is therefore the first-run answer and means "coverage
    is total by construction", not "unknown".
    """
    cur.execute(BACKUP_EXISTS, (BACKUP_TABLE,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE}")
    rows = cur.fetchone()[0]
    cur.execute(COUNT_UNCOVERED_BY_BACKUP)
    return rows, cur.fetchone()[0]


def refuse_unless_the_backup_covers_the_run(
    planned: int, preserved: tuple[int, int] | None
) -> None:
    """Refuse before the write when the undo would not cover what is cleared.

    Pure but for the raise, and called on the DRY RUN as well as the apply: a
    pre-flight that exits 0 for a run the apply will refuse has told the operator
    the opposite of what they asked.

    Two distinct failures, deliberately not collapsed into one message. They
    share a symptom — rows cleared that `--rollback` cannot restore — and have
    opposite remedies, and a guard that names the wrong remedy is worse than one
    that names none.
    """
    if preserved is None or not planned:
        return
    rows, uncovered = preserved

    if not rows:
        raise SystemExit(
            f"{BACKUP_TABLE} exists but holds 0 rows, while this run would "
            f"clear {planned}. The snapshot predates nothing and CREATE TABLE "
            f"IF NOT EXISTS will not refresh it, so the undo would restore "
            f"nothing. Drop the empty table and re-run: "
            f"DROP TABLE {BACKUP_TABLE};"
        )

    if uncovered:
        raise SystemExit(
            f"{uncovered} of the {planned} rows this run would clear are NOT in "
            f"{BACKUP_TABLE}, which holds {rows} rows from an earlier run. "
            f"CREATE TABLE IF NOT EXISTS deliberately does not refresh it, so "
            f"those {uncovered} would be cleared with no undo while --rollback "
            f"reported a clean restore of the {rows} it does hold. DO NOT DROP "
            f"THE TABLE — it is the real undo for those {rows}. Either roll back "
            f"first (--rollback) and re-measure, or archive the snapshot and let "
            f"this run take a fresh one: "
            f"ALTER TABLE {BACKUP_TABLE} RENAME TO {BACKUP_TABLE}_<yyyymmdd>;"
        )


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


def apply_clear(cur, *, dry_run: bool = False, gated_on: int | None = None) -> dict:
    """Clear both halves for every live-space MLB row. Returns what it did.

    Does not commit — the caller owns the transaction, which is what lets a test
    drive the same statements the dyno runs.

    `gated_on` is the population the caller's precondition verdict was computed
    from. The two counts are the same number under `SNAPSHOT_ISOLATION` and this
    check is then trivially satisfied — which is the point. It is what turns a
    later loss of that isolation from a silent widening of the clear into a
    refusal, and it costs one count. `None` means the caller is driving these
    statements directly (the round-trip tests) rather than through a gate.
    """
    cur.execute(f"""
        SELECT count(*),
               count(*) FILTER (WHERE e.win_probability_sources ? 'statpal_fixture_id')
          FROM events e JOIN sports s ON s.id = e.sport_id
         WHERE {POPULATION}
        """)
    planned, planned_jsonb = cur.fetchone()
    print(f"[plan] {planned} live-space MLB rows ({planned_jsonb} also in JSONB)")

    # The precondition and the write candidate must be ONE population. If they
    # are not, the verdict that let this run through was about a different set
    # of rows than the one about to be cleared, and no part of the output would
    # say so.
    if gated_on is not None and planned != gated_on:
        raise SystemExit(
            f"the precondition was computed on {gated_on} live-space rows and "
            f"this run would clear {planned}. The population MOVED between the "
            f"guard and the write, so the verdict that allowed this run is "
            f"about a different set of rows — which is the loop the frozen "
            f"count exists to refuse. Nothing was written. Re-run: at "
            f"{SNAPSHOT_ISOLATION} both numbers come from one snapshot, so a "
            f"disagreement here means the isolation is not in force."
        )

    # An earlier run's snapshot, read BEFORE this run creates or touches one.
    preserved = preserved_backup(cur)

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
        # The pre-flight answers the question the operator actually asked —
        # "will the apply run?" — so it refuses everything the apply refuses.
        refuse_unless_the_backup_covers_the_run(planned, preserved)
        return {
            "planned": planned,
            "planned_jsonb": planned_jsonb,
            "cleared": 0,
            "uncovered": 0 if preserved is None else preserved[1],
        }

    # BEFORE the first write, in the same transaction as the writes.
    # `IF NOT EXISTS` makes a re-run safe and deliberately does NOT refresh an
    # existing backup: the first run's snapshot is the one that predates every
    # change, and overwriting it with a half-repaired copy is how a backup stops
    # being an undo.
    cur.execute(CREATE_BACKUP)
    cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE}")
    backed_up = cur.fetchone()[0]
    print(f"[backup] {BACKUP_TABLE} holds {backed_up} rows")

    # The other side of "IF NOT EXISTS deliberately does not refresh": a backup
    # left behind by an EARLIER run may not cover what this one clears — because
    # it is empty, or because it predates rows a writer has since refilled.
    # Nothing else would notice either case: both statements succeed, the census
    # reads perfectly repaired, and D51's reversibility is gone silently. Refuse
    # before the write rather than discover it at rollback time, which is the
    # one moment the backup is needed and the one moment it is too late.
    refuse_unless_the_backup_covers_the_run(planned, preserved)

    cur.execute(CLEAR_BOTH)
    cleared = cur.rowcount or 0

    return {
        "planned": planned,
        "planned_jsonb": planned_jsonb,
        "backed_up": backed_up,
        "cleared": cleared,
        "uncovered": 0 if preserved is None else preserved[1],
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
    ap.add_argument(
        "--expect-population",
        type=int,
        default=EXPECTED_POPULATION,
        metavar="N",
        help=(
            f"the live-space count this run expects (default {EXPECTED_POPULATION}, "
            f"the frozen count). Override only after re-measuring and finding the "
            f"writer — it makes you state the new number out loud rather than "
            f"editing the guard out."
        ),
    )
    args = ap.parse_args()

    conn = _connect()
    pin_isolation(conn, ROLLBACK_ISOLATION if args.rollback else SNAPSHOT_ISOLATION)
    cur = conn.cursor()

    before = census(cur, "before")

    # Measured for every mode, including --report: an operator running the
    # census to decide whether to apply should get the verdict in the same
    # output, not have to compare a number to a docstring by eye.
    planned = count_population(cur)
    verdict, message = population_verdict(planned, expected=args.expect_population)
    print(f"[precondition] {verdict}: {message}")

    if args.report:
        conn.rollback()
        return 0

    # Refuses the DRY RUN too, and that is the point of putting it here. The dry
    # run is the operator's pre-flight; one that exits 0 for a run the apply will
    # refuse has told them the opposite of what they asked. `--rollback` is
    # exempt: it is the way OUT of a bad state, so a bad state must not block it.
    if verdict == "MOVED" and not args.rollback:
        conn.rollback()
        print("[precondition] REFUSED — nothing was written.")
        return 1

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

    # `gated_on` is the count the verdict above was computed from. Under
    # SNAPSHOT_ISOLATION it is the same snapshot the clear runs on; passing it
    # anyway is what makes that an assertion rather than an assumption.
    done = apply_clear(cur, dry_run=not args.apply, gated_on=planned)

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
