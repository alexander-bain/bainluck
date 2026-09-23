"""CAL-P002 — repair settled events frozen on a NON-FINAL score.

Invariant: a settled event's stored score IS the game's final score. A violation
means the page shows a wrong final (we held ``BOS 3-1`` where the real final was
``6-3``) and every score-derived grade underneath it stands on a mid-game number.

🔴 TWO DEFECT CLASSES WITH OPPOSITE REMEDIES SHARE THIS RAIL (#1980, queue 380).
Read this before adding anything that writes.

A settled row that disagrees with ESPN can be wrong in TWO different fields, and
the fix for one is the corruption for the other:

* ``score_drifted`` — the row's ``espn_id`` is PROVEN to be its own game and the
  stored score is not that game's final. Remedy: this repair, ``apply=true``.
* ``espn_id_drifted`` — the ``espn_id`` is ITSELF the wrong field; it names a
  different game (usually the same series, one or two slate-days off — measured
  offsets of exactly ±15 and ±30 in ESPN id space). **A score repair here writes
  another game's final onto this row.** Measured 2026-08-19 over the 262 settled
  MLB rows of the last 32 days: 21 rows carry a drifted ``espn_id``, and for
  **8 of them the stored score is already CORRECT** — the score remedy would
  have corrupted a currently-correct score. Remedy: ``event-espn-id`` (attended,
  plan-hashed), never this rail.
* ``espn_id_unresolvable`` — the ``espn_id`` is simply ABSENT from our own
  slate and no single game on that slate is provably ours (a doubleheader, or a
  postponement). Gotcha #53: an empty read is not a fact. No remedy is proven;
  it is REPORTED, never guessed at, and never handed the score remedy.

Until queue 380 the rail computed the linkage classes and then **discarded them
silently**: ``espn_not_found`` was a bare counter with no ledger row at all, and
the sentinel's detector filtered the ledger to ``fix_score``. So the two classes
rendered identically — as nothing — while the failure text the sentinel prints
on every line was the SCORE remedy. Every disposition now lands in the ledger
with an explicit ``defect_class`` and its own ``remedy``, and no row that is not
``proven`` can reach a write.

WHY NOTHING ELSE FIXES THIS. Two rails write settled scores today and both have a
hole this repair fills:

* ``_corrected_final_score`` (``tasks/espn_sync.py``) refuses to write unless our
  stored total is **0** — deliberately, citing gotcha #21 ("a real non-zero stored
  score is NEVER overwritten"). A score frozen at a plausible ``3-2`` is therefore
  structurally uncorrectable by every existing path.
* ``backfill_missing_scores`` (``utils/espn_helpers.py``) is gated on
  ``home_score IS NULL`` and a 7-day window. Same blind spot.

The producer is the wall-clock staleness net (``espn_sync._transition_event_statuses_impl``
and ``odds_polling.detect_and_close_stale_events``): both close an event purely on
elapsed time, keep whatever score the last poll happened to have written, and then
grade ``win_probability_sources.final_result`` to 1.0/0.0 off that mid-game score.
So a frozen 3-2 in the 6th becomes a permanent "home team won".

CAL-P002's measured evidence (2026-08-05, identity-verified vs ESPN finals):

    closed  · NHL/NBA/MLB/WNBA     10 / 399  =  2.5%
    closed  · NCAA Baseball        43 / 388  = 11.1%
    completed · major, 2-9d old    19 /  70  = 27.1%   <- all MLB
    completed · major, 30-60d      43 / 199  = 21.6%   <- all MLB
    completed · major, 100-160d     6 / 200  =  3.0%

Two sub-classes, ONE fix (overwrite with the event's own ESPN final):
  A. frozen in-progress score — NBA ev12080353 held 45-56 (a halftime score) for a
     game ESPN finalled 87-109; MLB/NCAA rows frozen at 0-0.
  B. wrong-game score from the same series — ev15182558 (Giants@Brewers 7/29) held
     ``SF 2-8 MIL``, which is the final of the 7/28 game. Its ``espn_id`` and
     ``commence_time`` both correctly identify the 7/29 game; only the score is
     another game's. (Link-level series mislinkage stays #1466 scope; this repairs
     the score value, not the link.)

SAFETY RAILS (each one earned):
  * Writes ONLY when ESPN reports the game FINAL (``status == "post"``). Writing a
    non-final ESPN score is bug #980/#981 recurring.
  * TEAM-IDENTITY GUARD: our home/away must match ESPN's home/away for that
    ``espn_id`` before we trust its score. The CAL-P002 census found 3 NCAA-Baseball
    rows whose ``espn_id`` points at a different game entirely — repairing off those
    would import a wrong score, not remove one. Identity-blocked rows are reported,
    never written (they are an ``espn_id`` linkage defect, a different repair).
  * ``completed_at`` is derived from the last REAL post-commence snapshot (gotcha
    #22), never ``now()``, and never written if that would invert ``commence_time``
    (gotcha #46). No snapshot ⇒ left NULL and reported.
  * When a corrected score changes the winner, ``win_probability_sources`` is
    re-resolved through the EXISTING ``_apply_final_pm_win_prob`` helper (#1000
    shape-safe). This changes no weights and no blend math — it restamps a derived
    final that was computed from the wrong score.
  * Commits per (sport, date) group, so a 30s HTTP timeout leaves consistent,
    resumable progress. Walk the population with ``offset``, advancing by the
    returned ``next_offset`` until ``groups_remaining`` is 0.
  * Oldest-first by default (gotcha #41 — newest-first ordering never reaches the
    old tail).

REACHABILITY (CAL-P002B, 2026-08-07). As first shipped this repair was live but
uncallable on the cohorts that hold the defects, for two independent reasons:

  1. ``limit`` bounded the ESPN calls, not the scan. Every candidate row carried
     two correlated ``MAX()`` subqueries and the slice happened in Python
     afterwards, so cost tracked the whole population and any unscoped call H12'd
     at the 30s router wall (``limit=3`` and ``limit=25`` alike). The group
     selection now happens in SQL, before the work.
  2. It was not resumable. The group predicate is unchanged by the repair, so
     re-invoking returned the same oldest groups forever and ``groups_remaining``
     never fell. Progress now comes from an explicit ``offset`` cursor.
  3. (#7147, 2026-09-19) It banked no backup, so D51(b)'s "a repair that backs up
     first and ships a one-command restore may be applied by the owning lane"
     did not reach it, and its apply stayed attended-only — a walk of ~170
     groups in ``baseball_mlb`` alone that no attending human ever made. It now
     banks every row it is about to write, in that row's own transaction, and
     refuses any write it could not bank. See :data:`BAK_TABLE`.

    POST /api/admin/repairs/event-final-scores?apply=false                 # dry-run census
    POST /api/admin/repairs/event-final-scores?apply=true&offset=25        # next batch

    python3 scripts/restore_7147_event_final_scores.py --apply             # the undo

    python3 scripts/repair_event_final_scores.py                   # dry-run ledger
    python3 scripts/repair_event_final_scores.py --apply --offset 25

Heroku one-off (gotcha #48 — non-detached does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`). Prefer the endpoint.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Settled events that ESPN can adjudicate: terminal status, a stored score, an
# espn_id to look up, and old enough that "still being played" is not the answer.
#
# ONE definition, three consumers (group census, candidate fetch, after-census) so
# the bound and the work can never drift onto different populations.
_SETTLED_PREDICATE = """
      e.status IN ('closed', 'completed')
      AND e.espn_id IS NOT NULL
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.commence_time < NOW() - INTERVAL '2 days'
      AND s.key = ANY(:sport_keys)
"""

_GAME_DATE_EXPR = "(e.commence_time AT TIME ZONE 'America/New_York')::date"

# STEP 1 — the cheap bound. A plain GROUP BY over the settled predicate: no
# correlated subqueries, no per-row work. This is what `limit` slices, and it must
# run BEFORE anything expensive.
#
# WHY THIS SHAPE (the CAL-P002B defect): the first cut fetched every candidate row
# — each carrying two correlated MAX() subqueries against win_prob_snapshots and
# odds_snapshots — and only then sliced to `limit` groups in Python. So `limit`
# bounded the ESPN calls but not the scan, cost tracked the whole population at
# ~40ms/row, and every unscoped call H12'd at the 30s router wall (measured
# 2026-08-07: limit=3 and limit=25 alike). The two defect-heavy cohorts,
# baseball_mlb and baseball_ncaa, were exactly the ones too big to reach.
_GROUPS_SQL = f"""
    SELECT s.key AS sport_key,
           {_GAME_DATE_EXPR} AS game_date,
           COUNT(*) AS n
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
    GROUP BY 1, 2
"""

# STEP 2 — candidate rows for the SELECTED groups only. The unnest join makes the
# (sport, date) pair filter exact rather than a cross-product of the two arrays.
# CAST(... AS type[]) rather than `::type[]`: a bind param followed by a `::` cast
# is dropped by SQLAlchemy text() under asyncpg.
_CANDIDATE_SQL = f"""
    SELECT e.id AS event_id, e.espn_id, s.key AS sport_key, e.status AS ev_status,
           e.home_team_name, e.away_team_name, e.home_score, e.away_score,
           e.commence_time, e.completed_at,
           {_GAME_DATE_EXPR} AS game_date
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    JOIN unnest(CAST(:g_sports AS text[]), CAST(:g_dates AS date[]))
           AS g(sport_key, game_date)
      ON g.sport_key = s.key AND g.game_date = {_GAME_DATE_EXPR}
    WHERE {_SETTLED_PREDICATE}
    ORDER BY e.commence_time
"""

_POPULATION_SQL = f"""
    SELECT COUNT(*) AS n
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
"""

# STEP 3 — completed_at derivation, batched and lazy. This is the work that used to
# ride on EVERY candidate row as two correlated subqueries; only rows with a NULL
# completed_at need it, and they are the minority (CAL-P002 census: ~8%).
#
# Shared with the two staleness nets that PRODUCE the gap, so the producer and the
# repair can never disagree about what "when did this game end" means.
from app.utils.event_completion import (  # noqa: E402
    LAST_POST_COMMENCE_SNAPSHOT_SQL as _LAST_SNAPSHOT_SQL,
)

_FIX_SCORE_SQL = """
    UPDATE events SET home_score = :home_score, away_score = :away_score
    WHERE id = :event_id
"""

_FIX_COMPLETED_AT_SQL = """
    UPDATE events SET completed_at = :completed_at WHERE id = :event_id
"""

# ---------------------------------------------------------------------------
# D51(b) — the backup this rail shipped without, and what that cost (#7147)
# ---------------------------------------------------------------------------
#
# CAL-P002's apply pass was approved in August under ATTENDED capped-batch
# discipline (``app/tasks/repair_winner_field.py`` names it as the precedent for
# its own). D51(b) later made a general rule out of the narrower case: a data
# repair that BANKS A BACKUP FIRST and ships a one-command restore may be
# applied by the owning lane without waiting for a human. This rail could not
# take that door, because it banked nothing — so for six weeks the only way to
# run it was to find an attending human for a walk that is ~170 (sport, date)
# groups in baseball_mlb ALONE. Nobody ever did.
#
# MEASURED what that cost, production 2026-09-19: ``/events/15313231`` renders
# **St. Louis Cardinals 5 — 5 San Francisco Giants, FINAL**, three days after a
# game ESPN finalled 5-6. An MLB game cannot end level, and the impossible score
# propagates: the page's own "Margin: expected vs final" card reads **Tied**. The
# dry-run ledger for that slate classifies it ``score_drifted`` with the espn_id
# PROVEN — the remedy has been sitting one parameter away the whole time.
#
# So the backup is not a new safety rail bolted onto a trusted repair. It is the
# missing precondition of the rail's OWN documented door, and it is
# unconditional on ``apply``: there is no ``backup=false``, for the reason
# ``repair_winner_field``'s cap is a module constant and not a query param — a
# gate that can be dialled off mid-run is not a gate.
BAK_TABLE = "bak_7147_event_final_scores"

#: The one command D51(b) asks for, spelled once and returned in every result.
#: Detached, because a non-detached ``heroku run`` returns empty stdout that
#: reads like success (gotcha #48); no ``cd backend``, because PROJECT_PATH puts
#: scripts at /app.
UNDO_COMMAND = (
    'heroku run:detached -a bainluck '
    '"python3 scripts/restore_7147_event_final_scores.py --apply"'
)

#: WHAT THE ROW WAS, and WHAT WE WROTE, in one table (the CERT-2439 lesson that
#: #4923 carries in a second MANIFEST_TABLE). A backup alone can only tell a
#: restore "the live row differs from its backup" — which is equally true of a
#: row ESPN has legitimately corrected AGAIN since, and reverting that would be
#: the undo causing the damage it exists to reverse. The ``new_*`` columns are
#: the discriminator: the restore puts a row back only where it still holds
#: EXACTLY what this repair left on it.
#:
#: 🔴 EVERY RESTORED COLUMN IS BANKED ON BOTH SIDES (CERT-3141). The first cut
#: banked ``new_home_score``/``new_away_score`` and nothing else, so the undo's
#: compare-and-swap observed the SCORE while restoring four columns. Two ways
#: that reverts a newer, legitimate value:
#:
#: * a ``fix_completed_at_only`` repair never changes the score, so its banked
#:   ``new_*`` score IS the live score for all time — the CAS can never fail,
#:   and the undo would put the pre-repair ``completed_at`` (a NULL, on that
#:   branch) back over whatever production has since derived;
#: * a blend rewritten after the repair — ``backfill_winners``, a re-resolve,
#:   any later grade — leaves the score untouched, so the CAS passes and the
#:   undo overwrites the newer blend with the pre-repair one.
#:
#: So the ``new_*`` half is a full write manifest of the four columns, stamped
#: from the row itself AFTER the writes (:func:`stamp_written_state`), and the
#: undo compare-and-swaps on all four. A stamp that never ran leaves the two
#: new columns NULL against a non-NULL live value, so the CAS fails and the
#: restore refuses — the failure mode is "declines to undo", never "reverts
#: something it cannot account for".
#:
#: ON CONFLICT is deliberately SPLIT across the two halves. The ``old_*`` columns
#: keep their FIRST banked values — a row repaired, drifted and repaired again
#: must restore to what production held before we ever touched it, not to our
#: own previous write. The ``new_*`` columns take the LATEST, because a stale
#: "what we wrote" would make the restore's compare-and-swap miss.
_BAK_CREATE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
      event_id                      bigint PRIMARY KEY,
      old_home_score                integer,
      old_away_score                integer,
      old_completed_at              timestamptz,
      old_win_probability_sources   jsonb,
      new_home_score                integer,
      new_away_score                integer,
      new_completed_at              timestamptz,
      new_win_probability_sources   jsonb,
      banked_at                     timestamptz NOT NULL DEFAULT now(),
      applied_at                    timestamptz NOT NULL DEFAULT now())
"""

#: The two manifest columns CERT-3141 added, for a table an earlier run of this
#: script already created. ``IF NOT EXISTS`` on both halves, so this is a no-op
#: on a fresh table and the only repair a half-old one needs; without it the
#: stamp raises ``UndefinedColumn`` on exactly the databases that have been
#: repaired before.
_BAK_MIGRATE_SQL = [
    f"ALTER TABLE {BAK_TABLE} ADD COLUMN IF NOT EXISTS "
    f"new_completed_at timestamptz",
    f"ALTER TABLE {BAK_TABLE} ADD COLUMN IF NOT EXISTS "
    f"new_win_probability_sources jsonb",
]

_BAK_COPY_SQL = f"""
    INSERT INTO {BAK_TABLE} (
        event_id, old_home_score, old_away_score, old_completed_at,
        old_win_probability_sources, new_home_score, new_away_score)
    SELECT e.id, e.home_score, e.away_score, e.completed_at,
           e.win_probability_sources, :new_home_score, :new_away_score
      FROM events e
     WHERE e.id = :event_id
    ON CONFLICT (event_id) DO UPDATE SET
        new_home_score = EXCLUDED.new_home_score,
        new_away_score = EXCLUDED.new_away_score,
        applied_at     = now()
"""

#: THE WRITE MANIFEST (CERT-3141). Read back off the event row after this
#: event's writes and inside the same transaction, so it records what we
#: actually left behind on all four restorable columns — including the ones
#: this branch did not touch, whose "what we wrote" is "what was already
#: there". Reading the row is what makes the manifest complete without the
#: apply loop having to predict its own writes: the blend restamp is computed
#: by ``_apply_final_pm_win_prob`` deep inside the branch, and a manifest
#: assembled from the loop's local variables would have to be kept in step with
#: every future write this rail grows.
_BAK_STAMP_SQL = f"""
    UPDATE {BAK_TABLE} b
       SET new_home_score              = e.home_score,
           new_away_score              = e.away_score,
           new_completed_at            = e.completed_at,
           new_win_probability_sources = e.win_probability_sources
      FROM events e
     WHERE e.id = b.event_id
       AND b.event_id = :event_id
"""

#: Asked BEFORE the reconciliation that names the table in a subquery, because
#: that one raises UndefinedTable on a database that has never been backed up —
#: which is every database on the documented dry-run-first path (#4669). A
#: missing table yields an empty reconciliation, and ``backup_is_exact({})`` is
#: False, so the apply still refuses (gotcha #53).
_BAK_EXISTS_SQL = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

_BAK_MISSING_SQL = f"""
    SELECT count(*) FROM events e
     WHERE e.id = ANY(CAST(:event_ids AS bigint[]))
       AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.event_id = e.id)
"""

# ── THE SECOND HALF OF THE SHIP: THE SNAPSHOT THAT OUTRANKS THE FIX ──────────
#
# Repairing ``events.home_score`` does NOT change what a reader sees. The event
# page's hero prints ``lastChartPoint?.homeScore ?? event?.home_score``
# (``app/events/[id]/page.tsx``) — the event row is the FALLBACK BENEATH two
# observation series, and ``computeLastChartPoint`` ranks those two by their own
# clocks. So a ``score_snapshots`` row stamped after full time beats the
# corrected row forever.
#
# Measured on production 2026-09-19, after this repair applied cleanly to both
# rows in the MLB tail: ``events`` read the ESPN final (5-6 and 7-3) while
# bainluck.com/events/15313231 printed "5 – 5 · FINAL · TIED" and
# /events/15313146 printed "7 – 2". Both pages were photographed. The cause on
# both is one snapshot stamped ``2026-09-19 00:15:22.408164+00`` — three days
# after a 09-16 game ended — carrying the pre-repair score.
#
# Those rows are not observations. Nothing watched that game on 09-19; the
# writer re-read our own defective ``events`` row and banked it as a sighting.
# The StatPal arm compares against the LAST SNAPSHOT rather than the event row
# (``tasks/statpal_sync.py``), which is why exactly the drifted events got one
# and no others did: the poisoned population IS the defect population.
#
# So they are DELETED, not corrected. Rewriting one to the true final would
# manufacture a different lie — a claim that somebody observed this score three
# days late — and would still drag the Score Differential chart out to a flat
# line days past the whistle (Alex, 2026-09-14: charts are confined to the
# actual game duration).
SNAP_BAK_TABLE = "bak_7147_post_final_score_snapshots"

#: How long after ``completed_at`` a score observation is still plausibly the
#: game's own. NOT a round number chosen for comfort — the shape of the
#: population picks it. Bucketed over 5,030 completed events with snapshots in
#: the trailing 60 days (production, 2026-09-19), by the lag between an event's
#: LAST snapshot and its ``completed_at``, counting how many disagree with the
#: event's final score:
#:
#:     lag            events   disagree
#:     <= 1 min        4,487      69   (1.5%)  ← the normal tail of a live game
#:     1 min – 3 h       192       2   (1.0%)
#:     3 h – 12 h        141       7   (5.0%)
#:     12 h – 24 h       112      31   (27.7%)  ← regime change
#:     24 h – 3 d         87      24   (27.6%)
#:     3 d – 3.8 d        12      11   (91.7%)
#:
#: The disagreement rate is flat at ~1% for the first three hours and then
#: climbs by a factor of 28. Anything inside the flat region is a live game's
#: own last gasp; the climb is this defect. 30 minutes sits well inside the flat
#: region, so the grace never eats a legitimate observation, and it still
#: catches every row in the climb.
#:
#: The grace is a floor under the TIME test only. The remedy is additionally
#: gated on the snapshot DISAGREEING with an ESPN final this scan has already
#: proven belongs to this row, so a late-but-correct snapshot is never touched
#: however far past the whistle it lands.
POST_FINAL_SNAPSHOT_GRACE_MINUTES = 30

#: One row per deleted snapshot, keyed on the snapshot's own primary key so the
#: undo can put back exactly what was removed. There is no ``new_*`` manifest
#: here and the CERT-3141 argument does not apply: a DELETE leaves nothing for a
#: later writer to legitimately move on from, so "what we left behind" is
#: "absence". The undo's compare-and-swap is correspondingly the absence test —
#: re-insert only where no row holds that id — which is enforced by the primary
#: key itself rather than by a column comparison.
_SNAP_BAK_CREATE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {SNAP_BAK_TABLE} (
      snapshot_id  bigint PRIMARY KEY,
      event_id     bigint NOT NULL,
      captured_at  timestamptz NOT NULL,
      home_score   integer,
      away_score   integer,
      espn_final   text,
      banked_at    timestamptz NOT NULL DEFAULT now())
"""

_SNAP_BAK_COPY_SQL = f"""
    INSERT INTO {SNAP_BAK_TABLE} (
        snapshot_id, event_id, captured_at, home_score, away_score, espn_final)
    SELECT s.id, s.event_id, s.captured_at, s.home_score, s.away_score,
           :espn_final
      FROM score_snapshots s
     WHERE s.id = ANY(CAST(:snapshot_ids AS bigint[]))
    ON CONFLICT (snapshot_id) DO NOTHING
"""

#: Same reasoning as :data:`_BAK_MISSING_SQL`: asked as a count of rows about to
#: be deleted that have NO banked row. Zero, or the delete is refused.
_SNAP_BAK_MISSING_SQL = f"""
    SELECT count(*) FROM score_snapshots s
     WHERE s.id = ANY(CAST(:snapshot_ids AS bigint[]))
       AND NOT EXISTS (
           SELECT 1 FROM {SNAP_BAK_TABLE} b WHERE b.snapshot_id = s.id)
"""

_SNAP_DELETE_SQL = """
    DELETE FROM score_snapshots
     WHERE id = ANY(CAST(:snapshot_ids AS bigint[]))
"""

#: Candidate rows for the whole selected window, in one query. Only snapshots
#: past the grace are fetched; the score comparison happens per row in the loop,
#: because only there is ESPN's final for THAT row known and proven.
_POST_FINAL_SNAPSHOT_SQL = """
    SELECT s.id, s.event_id, s.captured_at, s.home_score, s.away_score
      FROM score_snapshots s
      JOIN events e ON e.id = s.event_id
     WHERE s.event_id = ANY(CAST(:event_ids AS bigint[]))
       AND e.completed_at IS NOT NULL
       AND s.captured_at > e.completed_at
                         + make_interval(mins => :grace_minutes)
     ORDER BY s.event_id, s.captured_at
"""

# Default group budget per invocation. Each group is ONE ESPN scoreboard call and
# the client sleeps 0.5s between requests, so this stays inside the 30s HTTP wall.
_GROUP_LIMIT = 25

# A count alone cannot bound wall-clock: a slow ESPN slate makes 25 groups overrun
# the 30s router wall even though 25 is usually comfortable. Check elapsed time
# BEFORE starting each group and stop early, reporting how far we actually got —
# bounding the loop boundary is only correct if the longest single uninterrupted
# op (one scoreboard fetch) fits in the margin. It does: ~1s against a 6s reserve.
_DEADLINE_SECONDS = 22.0
_GROUP_RESERVE_SECONDS = 6.0


def backup_is_exact(recon) -> bool:
    """The D51(b) gate: every row about to be written has a banked row, and
    something was actually checked.

    ``all()`` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and the apply proceeds with no undo (gotcha #53). Pure, so the
    gate can be exercised without a database.
    """
    return bool(recon) and all(n == 0 for n in recon.values())


async def bank_prior_state(session, event_id: int, new_home, new_away) -> None:
    """Copy this event's pre-repair score, completion time and blend into
    :data:`BAK_TABLE`, alongside the score we are about to write.

    Called INSIDE the group's transaction and BEFORE the group's writes, so the
    commit that lands a repair lands its undo with it: there is no window in
    which a written row has no banked row. ``CREATE TABLE IF NOT EXISTS`` runs
    once per invocation via :func:`ensure_backup_table`.

    ``old_win_probability_sources`` is banked even though only a winner FLIP
    rewrites it — a column the repair can write is a column the undo must be
    able to restore, and which rows flip is not known until ESPN answers.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_COPY_SQL), {
        "event_id": event_id,
        "new_home_score": new_home,
        "new_away_score": new_away,
    })


async def stamp_written_state(session, event_id: int) -> None:
    """Record what this event's row holds NOW into the backup's manifest half.

    Called AFTER the event's writes and inside the same transaction, so it reads
    our own uncommitted values. See :data:`_BAK_STAMP_SQL` for why the manifest
    is read back rather than assembled from the loop's variables.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_STAMP_SQL), {"event_id": event_id})


async def ensure_backup_table(session) -> None:
    """Runtime DDL, attended invocation only (ruling 47(c)).

    ``CREATE TABLE IF NOT EXISTS bak_*`` inside a repair that runs only when a
    person invokes it is explicitly NOT migration-class: the invocation is the
    attended step. Nothing schedules this rail, and nothing may — see the module
    docstring.

    The ``ADD COLUMN IF NOT EXISTS`` pair is the same class and is here for the
    same reason: a database that ran the pre-CERT-3141 version of this script
    holds the table WITHOUT its manifest columns, and that is the one case where
    the stamp would raise instead of banking.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_CREATE_SQL))
    for stmt in _BAK_MIGRATE_SQL:
        await session.execute(text(stmt))


async def reconcile_backup(session, event_ids: list) -> dict:
    """How many rows about to be written have NO banked row? Zero, or refuse.

    Returns a mapping so :func:`backup_is_exact` can tell "checked, all present"
    from "checked nothing" — the distinction gotcha #53 exists for.
    """
    from sqlalchemy import text

    if not event_ids:
        return {}
    if not bool((await session.execute(text(_BAK_EXISTS_SQL))).scalar_one()):
        return {}
    missing = (
        await session.execute(text(_BAK_MISSING_SQL), {"event_ids": list(event_ids)})
    ).scalar_one()
    return {"events": int(missing)}


def snapshot_contradicts_final(snap, espn_home, espn_away) -> bool:
    """True when a post-grace snapshot disagrees with ESPN's proven final.

    Pure, and deliberately the ONLY score test on this rail: the grace bounds
    *when* a row is eligible, this bounds *whether* it is wrong. A snapshot that
    lands a week late carrying the right final is a harmless duplicate of the
    truth and is left alone — the defect is a number that contradicts the
    result, not a row with an awkward timestamp.

    ``None`` on either ESPN side means we were never told the final, so nothing
    is contradicted and nothing is deleted. This mirrors
    :func:`score_is_stale`'s refusal to grade against an unknown.
    """
    if espn_home is None or espn_away is None:
        return False
    return (snap.home_score, snap.away_score) != (espn_home, espn_away)


async def ensure_snapshot_backup_table(session) -> None:
    """Runtime DDL for the snapshot bank, attended invocation only (47(c)).

    Same class and same licence as :func:`ensure_backup_table`; kept separate so
    a run that finds no snapshot defect creates no table it never uses.
    """
    from sqlalchemy import text

    await session.execute(text(_SNAP_BAK_CREATE_SQL))


async def bank_post_final_snapshots(session, snapshot_ids: list, espn_final: str) -> None:
    """Copy the rows about to be deleted into :data:`SNAP_BAK_TABLE`.

    Called INSIDE the group's transaction and BEFORE the delete, so the commit
    that removes a snapshot lands its undo with it. ``espn_final`` is banked as
    text alongside each row purely so a person reading the backup months later
    can see what the row was measured against without re-deriving it.
    """
    from sqlalchemy import text

    if not snapshot_ids:
        return
    await session.execute(text(_SNAP_BAK_COPY_SQL), {
        "snapshot_ids": list(snapshot_ids),
        "espn_final": espn_final,
    })


async def reconcile_snapshot_backup(session, snapshot_ids: list) -> dict:
    """How many rows about to be DELETED have no banked row? Zero, or refuse.

    Shaped to be read by the same :func:`backup_is_exact` as the event-row bank,
    including its empty-mapping refusal: a reconciliation that inspected nothing
    must not read as a clean pass (gotcha #53).
    """
    from sqlalchemy import text

    if not snapshot_ids:
        return {}
    missing = (
        await session.execute(
            text(_SNAP_BAK_MISSING_SQL), {"snapshot_ids": list(snapshot_ids)}
        )
    ).scalar_one()
    return {"snapshots": int(missing)}


def score_is_stale(our_home, our_away, espn_home, espn_away, espn_is_final: bool) -> bool:
    """True when a settled event's stored score disagrees with ESPN's FINAL.

    Deliberately the inverse of ``_corrected_final_score``'s "only when our total is
    0" rule: CAL-P002 proved the frozen-at-a-real-score case is the LARGER half of
    the defect (a frozen 3-2 is invisible to the total==0 test). ESPN's final is the
    authority for a settled game's score; a non-final ESPN reading never is.
    """
    if not espn_is_final:
        return False
    if espn_home is None or espn_away is None:
        return False
    if our_home is None or our_away is None:
        return False
    return (our_home, our_away) != (espn_home, espn_away)


def resolved_home_from_score(home_score: int, away_score: int) -> float:
    """The final win-prob a settled score implies (matches the staleness net)."""
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def _is_soccer(sport_key) -> bool:
    return bool(sport_key) and str(sport_key).startswith("soccer")


def _soccer_same_club_by_identity(ours, espn) -> bool:
    """One soccer club under two spellings, proven by IDENTITY — nothing looser.

    #8190: ``names_match("PSG", "Paris Saint-Germain")`` is False (no shared
    token, below the suffix floor), so a settled Marseille-vs-PSG row holding
    the correct id on the correct slate read as ``espn_id_drifted`` and was
    prescribed a linkage repair that would have CORRUPTED it.

    Two readings, and deliberately only two:

    * the two names are EQUAL after the soccer alias tables (the whole-name
      table is keyed on the full token tuple — a statement about one name);
    * one side is a one-token initialism of the other (``psg`` = p-s-g).

    NOT the subset tier of ``soccer_team_matches``. That tier elects
    ``Manchester`` -> ``Manchester United`` and ``Inter`` -> ``Inter Miami``
    (Codex's falsifier on the first candidate), which is harmless where the
    matcher pairs whole fixtures and wrong here, where a hit elects a REPAIR
    TARGET. A squad marker on one side only (``Paris Saint-Germain W``) refuses
    without a guard of its own: both readings compare the marker as a token, so
    it breaks the equality and adds a letter to the initials.
    """
    from app.utils.soccer_team_matching import (
        CLUB_FORM_TOKENS,
        _initials_match,
        club_alias_tokens,
    )

    a, b = club_alias_tokens(ours), club_alias_tokens(espn)
    if not (set(a) - CLUB_FORM_TOKENS) or not (set(b) - CLUB_FORM_TOKENS):
        return False
    return a == b or _initials_match(a, b) or _initials_match(b, a)


def _side_matches(ours, espn, predicate, sport_key) -> bool:
    """One side of the fixture: ``predicate``, or — soccer only — identity."""
    if predicate(ours or "", espn or ""):
        return True
    return _is_soccer(sport_key) and _soccer_same_club_by_identity(ours, espn)


def _identity_matches(our_home, our_away, espn_home, espn_away, *, sport_key=None) -> bool:
    """Does this ESPN game describe the SAME fixture as our event?

    Guards the case the census found: an ``espn_id`` pointing at a different game.
    Without this, "repair" would import a wrong score instead of removing one.

    Per side and in orientation: home against home, away against away. A soccer
    ``sport_key`` adds :func:`_soccer_same_club_by_identity` as a second reading
    of each side (#8190); every other sport, and ``None``, is the exact old
    predicate.
    """
    from app.utils.name_normalization import names_match

    if not (espn_home and espn_away):
        return False
    return _side_matches(our_home, espn_home, names_match, sport_key) and _side_matches(
        our_away, espn_away, names_match, sport_key
    )


def _espn_team_name(team) -> str:
    if team is None:
        return ""
    return team.display_name or team.name or team.short_name or ""


def espn_date_matches(our_game_date, espn_dt) -> bool:
    """Does this ESPN game fall on the SAME calendar day as our event?

    THE GUARD THAT TEAM IDENTITY CANNOT PROVIDE. In a playoff series the same two
    teams meet repeatedly, so ``_identity_matches`` passes on every game of the
    series — and CAL-P002 found events whose ``espn_id`` points at a DIFFERENT game
    of their own series:

        ev14861878  our 2026-06-09  ->  espn_id 401874173 is the 06-06 game
        ev14881094  our 2026-06-11  ->  espn_id 401874172 is the 06-04 game
        ev14792938  our 2026-05-27  ->  espn_id 401873385 is the 05-25 game
        ev14639101  our 2026-05-16  ->  espn_id 401871407 is the 05-12 game

    A simulated repair that trusted identity alone imported those neighbours'
    finals and RAISED the KXNHLSPREAD disagreement count 8 -> 14. The batched
    scoreboard-by-date fetch already makes this structurally impossible (a game on
    another date is simply absent from the slate we asked for), but that is a
    property of the fetch strategy, not of the write rule. Pin it here so a future
    per-event ``summary`` fallback cannot silently reintroduce the corruption.

    Both sides are normalized to US/Eastern — the same basis our ``game_date`` is
    computed on — so the comparison is symmetric, not a UTC/local mix.
    """
    if our_game_date is None or espn_dt is None:
        return False
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    dt = espn_dt
    if dt.tzinfo is None:
        from datetime import timezone as _tz

        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(et).date() == our_game_date


# ---------------------------------------------------------------------------
# THE SPLIT (#1980, queue 380) — one vocabulary, shared by this rail and the
# Flow Sentinel, so the guard and the repair can never disagree about which
# defect a row has or which remedy it is owed.
# ---------------------------------------------------------------------------
SCORE_DRIFTED = "score_drifted"
ESPN_ID_DRIFTED = "espn_id_drifted"
ESPN_ID_UNRESOLVABLE = "espn_id_unresolvable"
LINK_PROVEN = "proven"
#: The reader-facing class: the event row is right and the PAGE is still wrong,
#: because a score observation stamped after full time outranks it in the hero's
#: own ladder. Named as its own class rather than folded into ``score_drifted``
#: because it survives that one's remedy — a row can hold this defect with a
#: perfect score. See :data:`SNAP_BAK_TABLE` for the measurement.
POST_FINAL_SNAPSHOT = "post_final_snapshot"

#: class -> the ONLY remedy that class may be handed. Handing ``espn_id_drifted``
#: the score remedy is the corruption this split exists to make unrepresentable.
DEFECT_REMEDY = {
    SCORE_DRIFTED: (
        "POST /api/admin/repairs/event-final-scores?apply=true "
        "(score repair — the espn_id is proven correct for this row)"
    ),
    ESPN_ID_DRIFTED: (
        "LINKAGE repair, NOT a score repair: POST /api/admin/repairs/event-espn-id"
        "?probe=true (x3, >300s) then ?apply=false then attended "
        "?apply=true&plan_hash=... . Running the score repair on this row writes "
        "ANOTHER GAME'S final onto it"
    ),
    ESPN_ID_UNRESOLVABLE: (
        "NO remedy is proven — adjudicate by hand. The espn_id is absent from "
        "this row's own slate and no single game on that slate is provably ours "
        "(doubleheader / postponement). An empty read is not a fact (gotcha #53). "
        "Explicitly NOT the score repair"
    ),
    POST_FINAL_SNAPSHOT: (
        "SNAPSHOT repair, on score_snapshots and not on the event row: the same "
        "POST ...?apply=true deletes the contradicting post-full-time rows and "
        "banks them in bak_7147_post_final_score_snapshots. The event row may "
        "already be correct — this is the half the reader actually sees"
    ),
}


def measurement_coverage(
    *, groups_scanned: int, groups_total: int, events_scanned: int, population: int
) -> dict:
    """How much of the surface this run actually looked at — as data, not prose.

    ``mode`` is ``"full"`` only when every group was scanned. Otherwise it is
    ``"sampled"`` and carries the rate and the population, so a count derived
    from it cannot be quoted as a population by accident. This is the shape the
    Flow Sentinel renders into its title and its issue body.
    """
    full = groups_total > 0 and groups_scanned >= groups_total
    rate = round(groups_scanned / groups_total, 4) if groups_total else None
    return {
        "mode": "full" if full else "sampled",
        "groups_scanned": groups_scanned,
        "groups_total": groups_total,
        "group_sample_rate": rate,
        "events_scanned": events_scanned,
        "population": population,
        "event_sample_rate": (
            round(events_scanned / population, 4) if population else None
        ),
    }


def _nearest_by_start(commence_time, games):
    """The game of ``games`` whose start is closest to ``commence_time``.

    ``None`` when there is nothing to compare — a missing time cannot elect a
    winner, and pretending it can is how a doubleheader gets paired by luck.
    """
    if commence_time is None:
        return None
    dated = [g for g in games if getattr(g, "date", None) is not None]
    if not dated:
        return None
    from datetime import timezone as _tz

    def _delta(g):
        d = g.date
        if d.tzinfo is None:
            d = d.replace(tzinfo=_tz.utc)
        ct = commence_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=_tz.utc)
        return abs((d - ct).total_seconds())

    return min(dated, key=_delta)


def _names_match_strict(a: str, b: str) -> bool:
    """Exact-or-suffix name equality — ``names_match`` WITHOUT its fuzzy stage.

    WHY A SECOND, STRICTER PREDICATE EXISTS. ``names_match`` falls back to a
    >= 0.5 token-overlap score, and two teams that share a city clear it:

        names_match("New York Mets", "New York Yankees")        -> True
        names_match("Los Angeles Dodgers", "Los Angeles Angels") -> True

    So the rail's ``_identity_matches`` guard — the one whose whole job is to
    stop a score being imported off the wrong game — passes on a Mets row
    pointed at a Yankees game. ev15173316 is the live specimen (measured
    2026-08-19): our row is Dodgers @ METS on 2026-07-24, its ``espn_id``
    401816142 is Dodgers @ YANKEES on 2026-07-17. That is not a near miss, it is
    a different fixture, and the loose predicate cannot see it.

    ``_identity_matches`` is deliberately left alone — its tolerance is what lets
    "Bruins" match "Boston Bruins" and it guards a write that already works. This
    stricter predicate is used only to ELECT a target and to detect a
    same-city impostor, never to widen what may be written.
    """
    from app.utils.name_normalization import normalize_name

    na, nb = normalize_name(a or ""), normalize_name(b or "")
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    sw, lw = shorter.split(), longer.split()
    return len(shorter) >= 4 and len(sw) < len(lw) and lw[-len(sw):] == sw


def same_fixture_games(
    home_team_name, away_team_name, board, game_date=None, *, sport_key=None
) -> list:
    """Every game on the slate WE ALREADY FETCHED that is OUR fixture, strictly.

    This is the second signal gotcha #53 demands, and it costs nothing: the
    scoreboard for our own game date is already in hand, so "our espn_id is not
    on our slate" can be upgraded from an empty read into a PROVEN drift with a
    named target whenever exactly one game on that slate is our fixture.

    Strict on BOTH axes, because this elects a repair target:

    * names — ``_names_match_strict``, so a same-city sibling (Mets/Yankees) is
      never proposed as the game a row "actually is";
    * date — the caller's own ET game date, so a board that happens to carry more
      than one day cannot contribute a candidate from the wrong one.

    A soccer ``sport_key`` lets a side that fails the strict predicate pass on
    :func:`_soccer_same_club_by_identity` instead (#8190) — equality after the
    alias tables or an initialism, never a subset, so it stays strict enough to
    elect a target. Two identity-matched games on one slate are still two, and
    the callers still refuse to pick between them.
    """
    out = []
    for g in board or []:
        if game_date is not None and not espn_date_matches(
            game_date, getattr(g, "date", None)
        ):
            continue
        if _side_matches(
            home_team_name,
            _espn_team_name(getattr(g, "home_team", None)),
            _names_match_strict,
            sport_key,
        ) and _side_matches(
            away_team_name,
            _espn_team_name(getattr(g, "away_team", None)),
            _names_match_strict,
            sport_key,
        ):
            out.append(g)
    return out


def classify_espn_link(
    *,
    espn_id,
    commence_time,
    game_date,
    home_team_name,
    away_team_name,
    board,
    sport_key=None,
) -> tuple[str, object, str]:
    """Which FIELD is wrong — the score, or the ``espn_id`` that names the game?

    Returns ``(verdict, target_game_or_None, reason)`` where ``verdict`` is
    ``LINK_PROVEN`` / ``ESPN_ID_DRIFTED`` / ``ESPN_ID_UNRESOLVABLE``. Pure over an
    already-fetched slate, so it is unit-testable and adds ZERO network cost.

    Only ``LINK_PROVEN`` may proceed to a score comparison. Everything else is a
    linkage finding and is reported with the linkage remedy.

    ``sport_key`` enables the soccer identity reading (#8190); ``None`` keeps the
    exact legacy predicate.

    THE DOUBLEHEADER ARM IS NOT DECORATION. Both games of a doubleheader sit on
    the same slate with the same two teams, so ``espn_date_matches`` passes and
    ``_identity_matches`` passes on the WRONG sibling — the two guards this rail
    already had are structurally blind to it. Measured 2026-08-19: ev14788546 and
    ev15200380 (Cardinals @ Reds, 2026-08-17) both store ``commence_time``
    17:40Z while ev14788546's ``espn_id`` and score both belong to the 22:40Z
    game. One of the two fields drifted and this rail cannot tell which, so it
    says so instead of picking.
    """
    by_id = {str(g.espn_id): g for g in (board or []) if getattr(g, "espn_id", None) is not None}
    held = by_id.get(str(espn_id))
    sibs = same_fixture_games(
        home_team_name, away_team_name, board, game_date, sport_key=sport_key
    )

    if held is None:
        if len(sibs) == 1:
            return (
                ESPN_ID_DRIFTED,
                sibs[0],
                "espn_id is absent from this row's own slate while EXACTLY ONE "
                "game on that slate is our fixture — the id names another day's game",
            )
        if len(sibs) > 1:
            return (
                ESPN_ID_UNRESOLVABLE,
                None,
                f"espn_id is absent from this row's own slate and {len(sibs)} games "
                f"on it are our fixture (doubleheader) — no single target is proven",
            )
        return (
            ESPN_ID_UNRESOLVABLE,
            None,
            "espn_id is absent from this row's own slate and NO game on that slate "
            "is our fixture — a postponement or a slate gap reads exactly like a "
            "drift here, so nothing is claimed",
        )

    if not espn_date_matches(game_date, getattr(held, "date", None)):
        return (
            ESPN_ID_DRIFTED,
            sibs[0] if len(sibs) == 1 else None,
            "espn_id resolves to a game on a DIFFERENT date than this row's own",
        )

    if not _identity_matches(
        home_team_name,
        away_team_name,
        _espn_team_name(getattr(held, "home_team", None)),
        _espn_team_name(getattr(held, "away_team", None)),
        sport_key=sport_key,
    ):
        return (
            ESPN_ID_DRIFTED,
            sibs[0] if len(sibs) == 1 else None,
            "espn_id resolves to a DIFFERENT fixture on this row's own slate",
        )

    # THE SAME-CITY IMPOSTOR. ``_identity_matches`` just passed, but it accepts a
    # >= 0.5 token overlap, so a Mets row pointed at a Yankees game clears it.
    # Fires ONLY when the slate holds exactly one STRICT candidate and it is not
    # the id we hold — i.e. only when there is a demonstrably better answer. With
    # no strict alternative this stays silent and the loose match stands, so a
    # source with unusual naming still gets its score repaired.
    if len(sibs) == 1 and str(getattr(sibs[0], "espn_id", "")) != str(espn_id):
        return (
            ESPN_ID_DRIFTED,
            sibs[0],
            "espn_id resolves to a same-city IMPOSTOR fixture on this row's own "
            "slate (it clears the fuzzy name guard but a strictly-matching game "
            "on the same slate is a different id)",
        )

    if len(sibs) > 1:
        nearest = _nearest_by_start(commence_time, sibs)
        if nearest is not None and str(getattr(nearest, "espn_id", "")) != str(espn_id):
            return (
                ESPN_ID_UNRESOLVABLE,
                nearest,
                "doubleheader: this row's commence_time is nearest a DIFFERENT game "
                "of the same fixture, so either espn_id or commence_time drifted and "
                "this rail cannot tell which",
            )

    return (LINK_PROVEN, held, "")


async def repair(
    session,
    apply: bool,
    limit: int = _GROUP_LIMIT,
    sport: str | None = None,
    newest_first: bool = False,
    offset: int = 0,
    deadline_seconds: float = _DEADLINE_SECONDS,
) -> dict:
    """Session-taking core (shared by the CLI and POST /api/admin/repairs/
    event-final-scores). Commits per group when ``apply``; returns a
    before/after census plus a per-event ledger.

    ``limit`` bounds (sport, date) GROUPS — one ESPN scoreboard call each — not
    events. ``offset`` skips that many groups in the SAME deterministic order.

    WHY ``offset`` EXISTS. The original contract was "re-invoke while
    ``groups_remaining > 0``", which could never terminate: the group predicate is
    *unchanged by the repair* (a corrected score is still a settled event with a
    score and an espn_id), so ``ordered[:limit]`` returned the SAME oldest groups
    on every call and ``groups_remaining`` never fell. The rail could only ever
    have touched the first batch. Progress has to come from an explicit cursor,
    not from the work shrinking its own candidate set. Drive it with
    ``next_offset`` — which accounts for an early deadline stop, so it is correct
    even when fewer than ``limit`` groups were scanned.
    """
    import time

    from sqlalchemy import text

    from app.services.espn_api import get_espn_service
    from app.utils.sport_keys import ESPN_SPORT_MAPPING

    s = session
    started = time.monotonic()
    # Gate on the mapping the rest of the ESPN pipeline uses, so this repair never
    # attempts a fetch the other tasks would not make.
    sport_keys = sorted(ESPN_SPORT_MAPPING)
    if sport:
        sport_keys = [k for k in sport_keys if k == sport]
        if not sport_keys:
            return {
                "repair": "event-final-scores",
                "applied": False,
                "error": f"sport '{sport}' is not in ESPN_SPORT_MAPPING",
                "available": sorted(ESPN_SPORT_MAPPING),
            }

    # STEP 1 — bound first. One cheap GROUP BY gives both the census denominator
    # and the orderable group list, so `population` costs no extra scan.
    group_rows = (await s.execute(text(_GROUPS_SQL), {"sport_keys": sport_keys})).all()
    population = sum(int(g.n) for g in group_rows)
    ordered = sorted(
        ((g.sport_key, g.game_date) for g in group_rows),
        key=lambda k: (k[1], k[0]),
        reverse=bool(newest_first),
    )
    offset = max(0, int(offset))
    selected = ordered[offset : offset + max(0, int(limit))]

    # STEP 2 — fetch rows for the SELECTED groups only.
    rows = []
    if selected:
        rows = (await s.execute(text(_CANDIDATE_SQL), {
            "sport_keys": sport_keys,
            "g_sports": [k[0] for k in selected],
            "g_dates": [k[1] for k in selected],
        })).all()

    # Group by (sport_key, ET game date): one ESPN scoreboard call covers a slate.
    groups: dict[tuple[str, object], list] = {}
    for r in rows:
        groups.setdefault((r.sport_key, r.game_date), []).append(r)

    # STEP 3 — completed_at derivation, only for the rows that lack one.
    gap_ids = [r.event_id for r in rows if r.completed_at is None]
    last_snap: dict[int, object] = {}
    if gap_ids:
        last_snap = {
            row.event_id: row.last_snap
            for row in (await s.execute(
                text(_LAST_SNAPSHOT_SQL), {"event_ids": gap_ids}
            )).all()
        }

    # STEP 3b — post-full-time snapshot candidates for the selected window, in
    # one query. Fetched for rows that HAVE a completed_at (the opposite set to
    # STEP 3, which serves the rows that lack one), since the grace is measured
    # from it. Only the time test runs here; whether a candidate is actually
    # wrong is decided per row in the loop, against the ESPN final proven there.
    dated_ids = [r.event_id for r in rows if r.completed_at is not None]
    post_final_snaps: dict[int, list] = {}
    if dated_ids:
        for row in (await s.execute(text(_POST_FINAL_SNAPSHOT_SQL), {
            "event_ids": dated_ids,
            "grace_minutes": POST_FINAL_SNAPSHOT_GRACE_MINUTES,
        })).all():
            post_final_snaps.setdefault(row.event_id, []).append(row)

    espn = get_espn_service()
    stats = {
        "events_scanned": 0,
        "espn_not_found": 0,
        "espn_not_final": 0,
        "date_blocked": 0,
        "identity_blocked": 0,
        "doubleheader_ambiguous": 0,
        # THE SPLIT (#1980). `score_defects` is the score class ONLY; the two
        # linkage classes are counted separately because their remedies are
        # opposite. Never sum them into one headline.
        "espn_id_drifted": 0,
        "espn_id_drifted_with_target": 0,
        "espn_id_unresolvable": 0,
        "score_defects": 0,
        "completed_at_gaps": 0,
        "scores_repaired": 0,
        "completed_at_repaired": 0,
        "blend_repaired": 0,
        "winner_flips": 0,
        # D51(b), #7147. Counted and reported even when it is 0, because "no row
        # was refused" and "the gate never ran" are the two readings of a silent
        # rail and only one of them is safe.
        "backup_refused": 0,
        # THE READER-FACING HALF (#7147). A third class, counted apart from the
        # two above for the same reason they are counted apart from each other:
        # the remedy is different (a DELETE on another table) and summing them
        # into one headline would hide which half of the ship actually moved.
        # ``post_final_snapshot_defects`` counts EVENTS, the two beside it count
        # ROWS — an event can carry more than one poisoned snapshot.
        "post_final_snapshot_defects": 0,
        "post_final_snapshots_dropped": 0,
        "snapshot_backup_refused": 0,
    }
    ledger: list[dict] = []
    groups_scanned = 0
    stopped_on_deadline = False

    if apply:
        # Once per invocation, before any group: the table has to exist before
        # the first bank, and IF NOT EXISTS makes the second call free.
        await ensure_backup_table(s)
        await ensure_snapshot_backup_table(s)
        await s.commit()

    for sport_key, game_date in selected:
        if time.monotonic() - started > deadline_seconds - _GROUP_RESERVE_SECONDS:
            # Stop cleanly with a truthful cursor rather than being cut off
            # mid-group by the router. Already-committed groups stand.
            stopped_on_deadline = True
            break
        groups_scanned += 1
        bucket = groups.get((sport_key, game_date)) or []
        try:
            board = await espn.get_scoreboard(sport_key, game_date.strftime("%Y%m%d"))
        except Exception as exc:  # a dead slate must not kill the whole batch
            ledger.append({
                "sport_key": sport_key, "date": game_date.isoformat(),
                "action": "skip_scoreboard_error", "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        if board is None:
            # AUTHORITY DARK (lane1/045). Every verdict below reads a row's
            # ABSENCE from this board as evidence (`skip_espn_id_off_slate`,
            # and the score comparison that follows a proven link). A board we
            # never received says nothing about any row in the bucket, so the
            # whole group is skipped and named in the ledger.
            ledger.append({
                "sport_key": sport_key, "date": game_date.isoformat(),
                "action": "skip_authority_dark", "events": len(bucket),
            })
            continue
        by_id = {str(e.espn_id): e for e in board if e.espn_id is not None}

        group_writes = 0
        for r in bucket:
            stats["events_scanned"] += 1

            # WHICH FIELD IS WRONG — asked BEFORE any score comparison, because a
            # score comparison against an id that is not this row's game is not a
            # measurement, it is the corruption. Nothing below `LINK_PROVEN` can
            # reach a write; every branch lands in the ledger with its class and
            # its own remedy, so the silent skip is structurally gone.
            verdict, target, reason = classify_espn_link(
                espn_id=r.espn_id,
                commence_time=r.commence_time,
                game_date=r.game_date,
                home_team_name=r.home_team_name,
                away_team_name=r.away_team_name,
                board=board,
                sport_key=sport_key,
            )
            if verdict != LINK_PROVEN:
                held = by_id.get(str(r.espn_id))
                if held is None:
                    stats["espn_not_found"] += 1
                    action = "skip_espn_id_off_slate"
                elif not espn_date_matches(r.game_date, held.date):
                    stats["date_blocked"] += 1
                    action = "skip_espn_id_wrong_date"
                elif not _identity_matches(
                    r.home_team_name, r.away_team_name,
                    _espn_team_name(held.home_team), _espn_team_name(held.away_team),
                    sport_key=sport_key,
                ):
                    stats["identity_blocked"] += 1
                    action = "skip_identity_mismatch"
                else:
                    stats["doubleheader_ambiguous"] += 1
                    action = "skip_doubleheader_ambiguous"
                stats[verdict] += 1
                entry = {
                    "event_id": r.event_id, "sport_key": sport_key,
                    "status": r.ev_status, "espn_id": r.espn_id,
                    "matchup": f"{r.home_team_name} vs {r.away_team_name}",
                    "commence_time": (
                        r.commence_time.isoformat() if r.commence_time else None
                    ),
                    "our_date": r.game_date.isoformat() if r.game_date else None,
                    "stored_score": f"{r.home_score}-{r.away_score}",
                    "action": action,
                    "defect_class": verdict,
                    "reason": reason,
                    "remedy": DEFECT_REMEDY[verdict],
                }
                if held is not None:
                    entry["espn_for_stored_id"] = (
                        f"{_espn_team_name(held.away_team)} @ "
                        f"{_espn_team_name(held.home_team)} "
                        f"{held.away_score}-{held.home_score}"
                    )
                    entry["espn_date"] = held.date.isoformat() if held.date else None
                if target is not None:
                    entry["proposed_espn_id"] = str(target.espn_id)
                    entry["proposed_espn_final"] = (
                        f"{target.home_score}-{target.away_score}"
                    )
                    entry["proposed_espn_start"] = (
                        target.date.isoformat() if target.date else None
                    )
                    if verdict == ESPN_ID_DRIFTED:
                        stats["espn_id_drifted_with_target"] += 1
                ledger.append(entry)
                continue

            ee = target
            is_final = ee.status == "post"
            if not is_final:
                stats["espn_not_final"] += 1
                continue

            stale = score_is_stale(
                r.home_score, r.away_score, ee.home_score, ee.away_score, is_final
            )
            needs_completed_at = r.completed_at is None

            # The third class, decided here because this is the first point at
            # which ESPN's final is PROVEN to be this row's own — the same
            # licence the score remedy runs on. A row can carry this defect with
            # a perfectly correct ``events`` score: repairing the event row is
            # what LEAVES it in that state, so the early exit below has to see
            # this class or the reader-facing half is unreachable on exactly the
            # rows this repair just fixed.
            post_final = [
                sn for sn in post_final_snaps.get(r.event_id, ())
                if snapshot_contradicts_final(sn, ee.home_score, ee.away_score)
            ]

            if not stale and not needs_completed_at and not post_final:
                continue

            entry = {
                "event_id": r.event_id, "sport_key": sport_key,
                "status": r.ev_status, "espn_id": r.espn_id,
                "matchup": f"{r.home_team_name} vs {r.away_team_name}",
                "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            }

            new_completed_at = None
            if needs_completed_at:
                stats["completed_at_gaps"] += 1
                # Same rule the producers now use (gotcha #22/#46) — one helper,
                # so a fix on one side cannot leave the other behind.
                from app.utils.event_completion import derive_completed_at

                cand = derive_completed_at(
                    last_snap.get(r.event_id), r.commence_time
                )
                if cand is not None:
                    new_completed_at = cand
                    entry["new_completed_at"] = cand.isoformat()
                else:
                    entry["completed_at_action"] = "skip_no_post_commence_snapshot"

            if stale:
                stats["score_defects"] += 1
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                entry.update({
                    "stored_score": f"{r.home_score}-{r.away_score}",
                    "espn_final": f"{ee.home_score}-{ee.away_score}",
                    "winner_flip": old_res != new_res,
                    "action": "fix_score",
                    # The espn_id was PROVEN this row's own game above, which is
                    # the entire licence for the score remedy on this line.
                    "defect_class": SCORE_DRIFTED,
                    "remedy": DEFECT_REMEDY[SCORE_DRIFTED],
                })
                if old_res != new_res:
                    stats["winner_flips"] += 1
            else:
                # A row can reach here on the completed_at gap, on the snapshot
                # class, or on both. Naming the snapshot case explicitly matters
                # because "fix_completed_at_only" is a claim that the score
                # series was left alone, and on this branch that is false.
                entry["action"] = (
                    "fix_completed_at_only" if needs_completed_at
                    else "drop_post_final_snapshots"
                )

            if post_final:
                stats["post_final_snapshot_defects"] += 1
                entry["post_final_snapshots"] = [
                    {
                        "snapshot_id": sn.id,
                        "captured_at": sn.captured_at.isoformat(),
                        "score": f"{sn.home_score}-{sn.away_score}",
                        "minutes_after_final": round(
                            (sn.captured_at - r.completed_at).total_seconds() / 60.0, 1
                        ) if r.completed_at else None,
                    }
                    for sn in post_final
                ]
                entry["espn_final"] = f"{ee.home_score}-{ee.away_score}"
                entry["snapshot_defect_class"] = POST_FINAL_SNAPSHOT
                entry["snapshot_remedy"] = DEFECT_REMEDY[POST_FINAL_SNAPSHOT]

            ledger.append(entry)

            if not apply:
                continue

            # ── THE SNAPSHOT HALF ────────────────────────────────────────────
            # Its own bank and its own compare-and-swap, deliberately NOT routed
            # through the event-row gate below. The two write different tables
            # with different undos, and sharing one refusal counter would make
            # "the event row had no backup" and "the snapshot rows had none"
            # indistinguishable in the only place a person reads afterwards.
            # Runs FIRST so that a snapshot-only row — the shape this repair's
            # own score fix creates — never reaches the event-row bank, which
            # would bank a row it is not about to write.
            if post_final:
                snap_ids = [sn.id for sn in post_final]
                await bank_post_final_snapshots(
                    s, snap_ids, f"{ee.home_score}-{ee.away_score}"
                )
                snap_recon = await reconcile_snapshot_backup(s, snap_ids)
                if not backup_is_exact(snap_recon):
                    stats["snapshot_backup_refused"] += 1
                    entry["snapshot_action"] = "skip_backup_not_banked"
                    entry["snapshot_remedy"] = (
                        "no undo could be banked for these snapshots, so none "
                        "were deleted — investigate before re-running"
                    )
                else:
                    await s.execute(
                        text(_SNAP_DELETE_SQL), {"snapshot_ids": snap_ids}
                    )
                    stats["post_final_snapshots_dropped"] += len(snap_ids)
                    group_writes += 1

            # A row whose ONLY defect was the snapshot class has nothing to write
            # on the event row, so it stops here — before a bank that would
            # record a "repair" of a row this pass never touched.
            if not stale and not needs_completed_at:
                continue

            # D51(b) — BANK BEFORE WRITE, in this group's own transaction, so
            # the commit that lands a repair lands its undo with it (#7147).
            # The reconciliation is not ceremony: it is the only thing that can
            # tell an INSERT that banked a row from one whose WHERE matched no
            # event at all, and a write with no banked row has no undo.
            await bank_prior_state(
                s, r.event_id,
                ee.home_score if stale else r.home_score,
                ee.away_score if stale else r.away_score,
            )
            recon = await reconcile_backup(s, [r.event_id])
            if not backup_is_exact(recon):
                stats["backup_refused"] += 1
                entry["action"] = "skip_backup_not_banked"
                entry["remedy"] = (
                    "no undo could be banked for this row, so nothing was "
                    "written — investigate before re-running"
                )
                continue

            if stale:
                await s.execute(text(_FIX_SCORE_SQL), {
                    "event_id": r.event_id,
                    "home_score": ee.home_score,
                    "away_score": ee.away_score,
                })
                stats["scores_repaired"] += 1
                group_writes += 1

                # The staleness net already graded the blend off the WRONG score.
                # Restamp it from the corrected one via the existing shape-safe
                # helper (#1000) — no weight or blend-math change.
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                if old_res != new_res:
                    from sqlalchemy import select, update as sql_update

                    from app.models.models import Event
                    from app.tasks.espn_sync import _apply_final_pm_win_prob

                    cur = (await s.execute(
                        select(Event.win_probability_sources).where(Event.id == r.event_id)
                    )).scalar_one_or_none()
                    if cur and "final_result" in (cur or {}):
                        await s.execute(
                            sql_update(Event)
                            .where(Event.id == r.event_id)
                            .values(
                                win_probability_sources=_apply_final_pm_win_prob(cur, new_res)
                            )
                        )
                        stats["blend_repaired"] += 1

            if new_completed_at is not None:
                await s.execute(text(_FIX_COMPLETED_AT_SQL), {
                    "event_id": r.event_id, "completed_at": new_completed_at,
                })
                stats["completed_at_repaired"] += 1
                group_writes += 1

            # THE MANIFEST, LAST (CERT-3141). Every write this event was going
            # to get has happened, so the row now IS what the undo must compare
            # against. Unconditional: a branch that wrote nothing still banks
            # "nothing changed", which is what makes the undo's CAS able to tell
            # "still ours" from "moved on" on a completed_at-only repair.
            await stamp_written_state(s, r.event_id)

        if apply and group_writes:
            # Commit per group: a timeout leaves consistent, resumable progress.
            await s.commit()

    after = (await s.execute(text(_POPULATION_SQL), {"sport_keys": sport_keys})).one().n
    next_offset = offset + groups_scanned
    return {
        "repair": "event-final-scores",
        "applied": bool(apply),
        "population": population,
        "population_after": after,
        "groups_total": len(ordered),
        "groups_offset": offset,
        "groups_scanned": groups_scanned,
        "groups_remaining": max(0, len(ordered) - next_offset),
        "next_offset": next_offset,
        "stopped_on_deadline": stopped_on_deadline,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "order": "newest_first" if newest_first else "oldest_first",
        "sport": sport or "all_espn_mapped",
        # THE UNDO, IN THE RESULT (D51(b), #7147). An undo an operator has to go
        # and look up is one they will quote from memory at the moment they are
        # least able to — so the rail hands back the exact command beside the
        # writes it just made. Stated on a dry run too: the whole point is that
        # it can be read BEFORE anything is applied.
        "undo": UNDO_COMMAND,
        **stats,
        "defect_rate_scanned": (
            round(stats["score_defects"] / stats["events_scanned"], 4)
            if stats["events_scanned"] else None
        ),
        # COVERAGE, STATED (#1980, queue 380). Every count above is over
        # `events_scanned`, which is a SAMPLE of `population` whenever
        # `groups_remaining > 0`. A reader who cannot see the denominator reads
        # the sample count as the population — the nightly guard reported a
        # specific integer over 0.6% of its surface for weeks. Emitting the
        # coverage next to the counts makes that misreading unavailable.
        "coverage": measurement_coverage(
            groups_scanned=groups_scanned,
            groups_total=len(ordered),
            events_scanned=stats["events_scanned"],
            population=population,
        ),
        "ledger": ledger,
    }


async def run(apply: bool, limit: int, sport: str | None, offset: int = 0) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, limit=limit, sport=sport, offset=offset)

    print(f"=== CAL-P002 event-final-scores ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"population={res['population']} groups={res['groups_scanned']}"
          f"@offset {res['groups_offset']}/{res['groups_total']} "
          f"(remaining {res['groups_remaining']}, next_offset {res['next_offset']})")
    cov = res["coverage"]
    print(f"COVERAGE {cov['mode'].upper()}: {cov['events_scanned']} of "
          f"{cov['population']} events ({cov['groups_scanned']}/{cov['groups_total']} "
          f"groups) — every count below is over the SCANNED set, not the population")
    print(f"scanned={res['events_scanned']} score_defects={res['score_defects']} "
          f"winner_flips={res['winner_flips']} completed_at_gaps={res['completed_at_gaps']}")
    print(f"espn_id_drifted={res['espn_id_drifted']} "
          f"(with a proven target: {res['espn_id_drifted_with_target']}) "
          f"espn_id_unresolvable={res['espn_id_unresolvable']}")
    print(f"identity_blocked={res['identity_blocked']} date_blocked={res['date_blocked']} "
          f"doubleheader_ambiguous={res['doubleheader_ambiguous']} "
          f"not_final={res['espn_not_final']} not_found={res['espn_not_found']}")
    print(f"post_final_snapshot_defects={res['post_final_snapshot_defects']} "
          f"(events) dropped={res['post_final_snapshots_dropped']} (rows) "
          f"refused={res['snapshot_backup_refused']}")
    # The snapshot class prints on its own list for the same reason the linkage
    # class does: it is a different table, a different undo, and a row can appear
    # here with a perfectly correct score.
    for e in res["ledger"][:200]:
        for sn in e.get("post_final_snapshots") or ():
            print(f"  [post_final_snapshot] ev{e['event_id']} [{e['sport_key']}] "
                  f"{e['matchup']}: snapshot {sn['score']} at {sn['captured_at']} "
                  f"({sn['minutes_after_final']}m after full time) "
                  f"vs final {e.get('espn_final')}")
    for e in res["ledger"][:40]:
        if e.get("action") == "fix_score":
            print(f"  [score_drifted] ev{e['event_id']} [{e['sport_key']}] {e['matchup']}: "
                  f"{e['stored_score']} -> {e['espn_final']}"
                  + ("  *WINNER FLIP*" if e.get("winner_flip") else ""))
    # The linkage class prints SEPARATELY and never under the score heading —
    # two remedies, two lists. Printing them together is how the wrong one gets
    # applied.
    for e in res["ledger"][:200]:
        if e.get("defect_class") in (ESPN_ID_DRIFTED, ESPN_ID_UNRESOLVABLE):
            tgt = e.get("proposed_espn_id")
            print(f"  [{e['defect_class']}] ev{e['event_id']} [{e['sport_key']}] "
                  f"{e['matchup']} espn_id={e['espn_id']}"
                  + (f" -> proposed {tgt}" if tgt else " -> NO PROVEN TARGET")
                  + f"  ({e.get('reason')})")
    if res["espn_id_drifted"] or res["espn_id_unresolvable"]:
        print("\nNOTE: the linkage rows above are NOT repairable by this rail. "
              "Use event-espn-id (attended). A score repair on them writes another "
              "game's final onto the row.")
    if apply:
        print(f"\nCOMMITTED scores={res['scores_repaired']} "
              f"completed_at={res['completed_at_repaired']} blend={res['blend_repaired']} "
              f"post_final_snapshots_dropped={res['post_final_snapshots_dropped']}")
        if res["groups_remaining"]:
            print(f"Re-run with --offset {res['next_offset']} "
                  f"({res['groups_remaining']} groups remaining).")
    else:
        print("\nDRY-RUN — pass --apply to commit.")


if __name__ == "__main__":
    _limit = _GROUP_LIMIT
    _sport = None
    _offset = 0
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            _limit = int(sys.argv[i + 1])
        if a == "--sport" and i + 1 < len(sys.argv):
            _sport = sys.argv[i + 1]
        if a == "--offset" and i + 1 < len(sys.argv):
            _offset = int(sys.argv[i + 1])
    asyncio.run(run("--apply" in sys.argv, _limit, _sport, _offset))
