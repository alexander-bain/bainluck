"""#7354 — repair settled rows frozen on a SWAPPED ESPN orientation.

A neutral-site game that settled before #7338 shipped is frozen showing the
losing team as the winner, and nothing in production can correct it.

    /events/15308929 — "Mountaineers 27 · Cavaliers 38", WON badge on the
    Cavaliers. West Virginia actually won 38-27.

WHAT THE DEFECT IS. ``match_event_to_espn`` arm 1 matches on ``espn_id`` alone,
which proves the same FIXTURE and says nothing about the SIDES. Everything
downstream then copies by ESPN's slot (``home_score = ee.home_score``), so on a
row whose home/away is the reverse of ESPN's — a neutral-site game, where
neither provider has a true home side to agree about — every score and the ESPN
probability leg land on the wrong team. #7338 (``orient_espn_event_to_row``)
stops that at the write path, going forward only.

WHY NOTHING ELSE FIXES THE ROWS ALREADY SETTLED.

* ``orient_espn_event_to_row`` sits above the score compare-and-write, so a
  swapped row IS corrected on a later poll — but only while the row is still
  selected, and ``_sync_espn_live_events`` admits completed rows only while
  ``commence_time >= now() - 6h`` (``tasks/espn_sync.py:1830``). Past that
  window nothing re-reads the row.
* ``_corrected_final_score`` only writes ESPN's final when our stored total is
  ``0``; a swapped row's total is the game's true total, so it is skipped.
* #7147's writer refusal (``c4e6070eb``, live) now blocks post-final score
  writes outright.

So every neutral-site row swapped before #7338 shipped is permanently wrong.

🔴 A ROW REPAIR ALONE IS INERT ON THE READER — THIS IS THE THIRD INSTANCE.
#7147 → #7315 → here: **the event row is the fallback beneath two observation
series, so a repair that writes only the row cannot move the page.** The hero
reads ``lastChartPoint?.homeScore ?? event?.home_score``
(``frontend/app/events/[id]/page.tsx:895``), and ``computeLastChartPoint``
falls through to the row only when BOTH series are null. Measured on the
specimen, neither is: ``espn_snapshots`` holds 102 rows and ``score_snapshots``
13, every one of them swapped, and no later poll can correct them (#922 skips
the ESPN snapshot append for completed events).

Worse, the row half ALONE makes the page contradict itself in a NEW way:
``hero_settled_result`` DOES read the row (``resolve_settled_hero``), so
flipping the row to 38/27 while the series still say 27/38 renders
*"Mountaineers 27 · WON · Cavaliers 38"* — the badge on the lower number.

Hence this rail writes up to four stores in ONE transaction per event:

    1. ``events.home_score`` / ``away_score``
    2. ``espn_snapshots.home_score`` / ``away_score``
                        / ``home_win_probability`` / ``away_win_probability``
    3. ``score_snapshots.home_score`` / ``away_score``
    4. the ESPN leg — ``win_prob_snapshots`` where ``source='espn'``,
       ``events.espn_win_prob_home``, ``win_probability_sources['espn']``

🔴 "UP TO" FOUR, AND EACH ONE IS JUDGED SEPARATELY — A ROW CAN BE HALF-HEALED.
#7338 released on 2026-09-20 while this rail was being written, and its live
sweep reached the specimen inside the 6h window: it corrected ``events`` to
38-27 and appended one correctly-oriented ``score_snapshots`` row, while
``espn_snapshots`` stayed frozen at 102 swapped rows and the ESPN probability
leg stayed at 0.0 for the side that won. That residual is what still renders
"Bigger Picture: Cavaliers" over a game West Virginia won.

The first cut of this rail had ONE global gate keyed on ``events.home_score``,
so it read that row as "not slot copied" and walked away from the half still on
the page — a repair windowed on the very column a partial repair had already
moved. So: the VERDICT decides membership (it is identity-keyed, and a partial
heal cannot move it), and each STORE then carries its own positive proof. No
store is written on another store's evidence.

MEASURED POPULATION (2026-09-19, this rail's own planner replayed over
production): **0 swapped verdicts in 985 settled rows carrying an ``espn_id``**
— 45 days, all older than 8h, every ESPN-adjudicable sport. There is no frozen
backlog. This rail exists for the residual above and for the next time a
neutral-site game settles outside the 6h window before a corrected poll reaches
it (ESPN dark, a bowl game, an international fixture).

THE JUDGE IS #7338's OWN, NEVER A SECOND IMPLEMENTATION. Membership is
:func:`espn_orientation_verdict` and nothing else. It has THREE values and only
a positive ``swapped`` may be written: ``aligned`` and ``unresolved`` are left
exactly as they are. ``unresolved`` means "we cannot read this row's names",
which is not evidence of a swap — guessing there would corrupt rows that are
correct today.

🔴 TWO DEFECTS WEAR THE SAME SYMPTOM AND HAVE OPPOSITE REMEDIES. A settled row
whose score disagrees with ESPN can be EITHER orientation-swapped (this rail) or
score-drifted / espn_id-drifted (#7147's rail, ``repair_event_final_scores``).
Applying the wrong one writes another game's final onto the row. They are told
apart by :data:`SLOT_COPY_PROOF`, applied per store: a store is only ever
written when it holds EXACTLY ESPN's values in ESPN's own slots. A store that
merely disagrees with ESPN is reported in ``series_notes`` and never touched
here — it belongs to the other rail.

WHAT IS DELIBERATELY NOT IN SCOPE (measured, not assumed — see #7354):

* **Props.** The issue's "settled props graded backwards" bullet is an
  inference from the swapped score, not a defect. Measured on the specimen, all
  302 graded outcomes carry ``resolution_source`` ``api_settlement`` (254),
  ``poly_total_score`` (34) or ``clob_authoritative`` (14) — the VENUE's own
  settlement, not our orientation. Kalshi grades "West Virginia" ``is_winner=
  True`` at p=1.0. And ESPN's scoring plays confirm Virginia genuinely scored
  the first touchdown, so "Virginia scores first TD: Won" is CORRECT. Scoring
  the first TD is not winning the game. No prop is repaired here.
* **The non-ESPN legs' post-final pin.** ``kalshi`` and ``polymarket`` are
  correctly oriented for the whole game (kalshi climbs 0.22 → 0.98 for the home
  side that won) and then take 3 rows each, 1-3 minutes after ``completed_at``,
  pinned to 0.01 / 0.001 — the losing side. That is a post-final pin reading the
  swapped score, a different mechanism with a different remedy, and it is inside
  #7147's 30-minute grace so its drop does not reach it. Reported by this rail
  (``post_final_pinned_rows``), never written. ``stat_model`` is score-derived
  and diverges mid-game for the same root cause; a model output computed from
  bad input cannot be honestly reconstructed, so it is reported too.

Both exclusions are counted in the ledger rather than dropped silently, because
a repair that quietly narrows its own population is how a defect survives its
own fix.

D51(b) SHAPE. Backup first, unconditional on ``--apply``; the bank and the write
land in one transaction, so there is no window in which a written row has no
banked row; any write whose bank cannot be verified is REFUSED. One-command
restore:

    python3 scripts/repair_7354_settled_orientation_swap.py                  # dry-run ledger
    python3 scripts/repair_7354_settled_orientation_swap.py --apply --limit 25
    python3 scripts/restore_7354_settled_orientation_swap.py --apply         # the undo

RUNTIME DDL, ATTENDED INVOCATION ONLY (ruling 47(c)). ``CREATE TABLE IF NOT
EXISTS bak_*`` inside a script that runs only when a person invokes it is
explicitly NOT migration-class. Nothing schedules this rail and nothing may.

Heroku one-off (gotcha #48 — non-detached does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`).
"""
import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.espn_helpers import (  # noqa: E402
    ESPN_ORIENTATION_ALIGNED,
    ESPN_ORIENTATION_SWAPPED,
    ESPN_ORIENTATION_UNRESOLVED,
    espn_orientation_verdict,
)

BAK_TABLE = "bak_7354_settled_orientation_swap"

#: The proof that separates an ORIENTATION SWAP from a SCORE DRIFT.
#:
#: A slot-copied row holds ESPN's two numbers in ESPN's own slots: our
#: ``home_score`` IS ``ee.home_score`` and our ``away_score`` IS
#: ``ee.away_score``, while our home side corresponds to ESPN's AWAY competitor.
#: That is a complete description of the write that produced the defect, and it
#: is falsifiable: if the stored pair is anything else, the row was not produced
#: by this write and this rail has no business rewriting it.
#:
#: Without this test the rail would "repair" every settled row whose score
#: merely disagrees with ESPN — which is #7147's ``score_drifted`` and
#: ``espn_id_drifted`` population, where the measured remedy is different and,
#: for 8 of 21 drifted rows in that census, the stored score is already CORRECT.
SLOT_COPY_PROOF = "stored score is ESPN's pair in ESPN's slots"

# Settled rows ESPN can still adjudicate. ONE definition, shared by the census
# and the candidate fetch so the bound and the work cannot drift apart.
_SETTLED_PREDICATE = """
      e.status IN ('closed', 'completed')
      AND e.espn_id IS NOT NULL
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.commence_time >= NOW() - make_interval(days => :since_days)
      AND (:sport_key IS NULL OR s.key = :sport_key)
"""

_POPULATION_SQL = f"""
    SELECT COUNT(*) FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
"""

#: Oldest-first WITHIN a floor (gotcha #41). Newest-first starves the old tail;
#: oldest-first with no floor spends the budget on rows ESPN may no longer
#: serve. ``since_days`` is the floor and the order is ascending inside it.
_CANDIDATE_SQL = f"""
    SELECT e.id, e.espn_id, s.key AS sport_key,
           e.home_team_name, e.away_team_name,
           e.home_team_normalized, e.away_team_normalized,
           e.home_team_alt_names, e.away_team_alt_names,
           e.home_score, e.away_score, e.espn_win_prob_home,
           e.commence_time, e.completed_at
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE {_SETTLED_PREDICATE}
    ORDER BY e.commence_time ASC, e.id ASC
    LIMIT :limit OFFSET :offset
"""

#: The LAST row of each observation series. A series is only swapped when its
#: last point is demonstrably in the swapped orientation — see
#: :func:`plan_orientation_repair`.
_LAST_ESPN_SNAPSHOT_SQL = """
    SELECT home_score, away_score FROM espn_snapshots
     WHERE event_id = :event_id AND home_score IS NOT NULL
     ORDER BY captured_at DESC LIMIT 1
"""

_LAST_SCORE_SNAPSHOT_SQL = """
    SELECT home_score, away_score FROM score_snapshots
     WHERE event_id = :event_id AND home_score IS NOT NULL
     ORDER BY captured_at DESC LIMIT 1
"""

#: Reported, never written — see the module docstring's scope note.
_POST_FINAL_PINNED_SQL = """
    SELECT w.source, COUNT(*) FROM win_prob_snapshots w
      JOIN events e ON e.id = w.event_id
     WHERE w.event_id = :event_id
       AND e.completed_at IS NOT NULL
       AND w.captured_at > e.completed_at
       AND w.source <> 'espn'
     GROUP BY w.source
"""

# ── D51(b): the backup ───────────────────────────────────────────────────────
#
# ``old_*`` keeps its FIRST banked value, so a row repaired twice restores to
# what production held before we ever touched it rather than to our own previous
# write. There is no ``new_*`` manifest for the series halves: they are swaps,
# and a swap is its own inverse, so "what we wrote" is recoverable from "what we
# found" plus the row count we banked.
_BAK_CREATE_SQL = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
      event_id                     bigint PRIMARY KEY,
      old_home_score               integer,
      old_away_score               integer,
      old_espn_win_prob_home       numeric,
      old_win_probability_sources  jsonb,
      new_home_score               integer,
      new_away_score               integer,
      new_espn_win_prob_home       numeric,
      new_win_probability_sources  jsonb,
      espn_snapshot_rows           integer NOT NULL DEFAULT 0,
      score_snapshot_rows          integer NOT NULL DEFAULT 0,
      espn_leg_rows                integer NOT NULL DEFAULT 0,
      banked_at                    timestamptz NOT NULL DEFAULT now(),
      applied_at                   timestamptz NOT NULL DEFAULT now())
"""

_BAK_COPY_SQL = f"""
    INSERT INTO {BAK_TABLE} (
        event_id, old_home_score, old_away_score, old_espn_win_prob_home,
        old_win_probability_sources, new_home_score, new_away_score,
        espn_snapshot_rows, score_snapshot_rows, espn_leg_rows)
    SELECT e.id, e.home_score, e.away_score, e.espn_win_prob_home,
           e.win_probability_sources, :new_home_score, :new_away_score,
           :espn_snapshot_rows, :score_snapshot_rows, :espn_leg_rows
      FROM events e
     WHERE e.id = :event_id
    ON CONFLICT (event_id) DO UPDATE SET
        new_home_score      = EXCLUDED.new_home_score,
        new_away_score      = EXCLUDED.new_away_score,
        espn_snapshot_rows  = EXCLUDED.espn_snapshot_rows,
        score_snapshot_rows = EXCLUDED.score_snapshot_rows,
        espn_leg_rows       = EXCLUDED.espn_leg_rows,
        applied_at          = now()
"""

#: THE WRITE MANIFEST (the CERT-3141 lesson, inherited from #7147's rail). Read
#: back OFF the event row after this event's writes and inside the same
#: transaction, so it records what we actually left behind on every restorable
#: column — including ones this plan did not touch, whose "what we wrote" is
#: "what was already there".
#:
#: Without it the undo would restore ``espn_win_prob_home`` and
#: ``win_probability_sources`` while observing only the score — a compare-and-
#: swap for one field and a blind overwrite for the other two. Both have a
#: routine newer-value case that is score-indistinguishable by construction: the
#: blend is rewritten by later legitimate passes (``backfill_winners``, a
#: re-resolve) without touching the score, so a score-only CAS passes and the
#: undo would replace the newer grade with the pre-repair one.
#: The score is stamped here too, and NOT taken from the plan's prediction.
#: A half-healed row is repaired WITHOUT its score being rewritten (#7338's
#: sweep got there first), so the plan's `new_home_score` is None on exactly
#: those rows while the live row holds a real value. Banking the prediction
#: would leave the undo comparing a real score against NULL, which never
#: matches, and the row could never be restored. Reading it back off the row
#: records what we actually left behind either way.
_BAK_STAMP_SQL = f"""
    UPDATE {BAK_TABLE} b
       SET new_home_score              = e.home_score,
           new_away_score              = e.away_score,
           new_espn_win_prob_home      = e.espn_win_prob_home,
           new_win_probability_sources = e.win_probability_sources
      FROM events e
     WHERE e.id = b.event_id AND b.event_id = :event_id
"""

#: Asked BEFORE any statement that names the table in a subquery, because that
#: one raises UndefinedTable on a database that has never been backed up — which
#: is every database on the documented dry-run-first path. Gotcha #53: a missing
#: table must read as "no backup", never as an empty clean result.
_BAK_EXISTS_SQL = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

_BAK_MISSING_SQL = f"""
    SELECT COUNT(*) FROM events e
     WHERE e.id = :event_id
       AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.event_id = e.id)
"""

# ── the writes ───────────────────────────────────────────────────────────────
#
# Every one is an exchange of two columns evaluated atomically by Postgres, so
# none of them needs a temporary and none can half-apply. `updated_at` is
# deliberately NOT stamped: a repair that touches a rendered freshness column
# presents stale data as fresh.
_SWAP_EVENT_SCORE_SQL = """
    UPDATE events SET home_score = :home_score, away_score = :away_score
     WHERE id = :event_id
"""

_SWAP_ESPN_SNAPSHOTS_SQL = """
    UPDATE espn_snapshots
       SET home_score = away_score, away_score = home_score,
           home_win_probability = away_win_probability,
           away_win_probability = home_win_probability
     WHERE event_id = :event_id
"""

_SWAP_SCORE_SNAPSHOTS_SQL = """
    UPDATE score_snapshots
       SET home_score = away_score, away_score = home_score
     WHERE event_id = :event_id
"""

_SWAP_ESPN_LEG_SQL = """
    UPDATE win_prob_snapshots
       SET home_win_probability = away_win_probability,
           away_win_probability = home_win_probability
     WHERE event_id = :event_id AND source = 'espn'
"""

_SET_ESPN_WIN_PROB_SQL = """
    UPDATE events SET espn_win_prob_home = :value WHERE id = :event_id
"""

#: JSONB via Core ``update()``, never ORM attribute assignment (gotcha #4).
#: ``jsonb_set`` leaves every other leg and every other key of the ESPN leg
#: untouched, which a read-modify-write in Python would not guarantee against a
#: concurrent writer.
_COMPLEMENT_WPS_ESPN_SQL = """
    UPDATE events
       SET win_probability_sources = jsonb_set(
             win_probability_sources, '{espn,value}',
             to_jsonb(ROUND((1.0 - (win_probability_sources->'espn'->>'value')::numeric), 6)))
     WHERE id = :event_id
       AND jsonb_exists(win_probability_sources, 'espn')
       AND jsonb_typeof(win_probability_sources->'espn'->'value') = 'number'
"""
# `jsonb_exists(col, 'espn')` and NOT the `?` operator: a bare `?` inside
# `text()` is claimed by the driver's own parameter syntax, so the operator form
# raises or silently mis-binds depending on the dialect. The function form is
# the same index-eligible test with no parser ambiguity.


#: plan action -> the counter it increments. A table rather than a chain, so a
#: new action that nobody counts is visible as a missing key instead of silently
#: landing in no bucket.
_ACTION_COUNTERS = {
    "skip_aligned": "aligned",
    "skip_unresolved": "unresolved",
    "skip_nothing_to_repair": "nothing_to_repair",
    "skip_espn_not_found": "espn_not_found",
    "skip_espn_not_final": "espn_not_final",
    "skip_espn_no_score": "espn_no_score",
}


@dataclass
class OrientationPlan:
    """What this rail will do to ONE event, and why — decided without a write.

    Pure data. :func:`plan_orientation_repair` builds it from the row, ESPN's
    answer and the two series' last points, so the whole disposition can be
    replayed over db-query output before anything is applied.
    """

    event_id: int
    sport_key: Optional[str] = None
    matchup: Optional[str] = None
    verdict: Optional[str] = None
    action: str = "skip"
    reason: str = ""
    stored_score: Optional[tuple] = None
    espn_score: Optional[tuple] = None
    new_home_score: Optional[int] = None
    new_away_score: Optional[int] = None
    new_espn_win_prob_home: Optional[float] = None
    swap_espn_snapshots: bool = False
    swap_score_snapshots: bool = False
    complement_espn_leg: bool = False
    series_notes: list = field(default_factory=list)

    @property
    def writes(self) -> bool:
        return self.action == "repair_orientation"


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def plan_orientation_repair(
    row, ee, last_espn_snapshot=None, last_score_snapshot=None
) -> OrientationPlan:
    """Decide ONE event's disposition. Pure — no I/O, no session, no clock.

    The gates, in the order they earn their place:

    1. **ESPN must say the game is over.** Writing a non-final ESPN score is
       bug #980/#981 recurring.
    2. **ESPN must give both numbers.** Gotcha #53 — an absent score is not a
       score of zero, and a missing half cannot be swapped into a whole.
    3. **The verdict must be a positive** ``swapped``. ``aligned`` is correct
       already; ``unresolved`` means we could not read the row's names, which is
       not evidence of anything. Neither is written.
    4. **The stored score must be ESPN's pair in ESPN's slots**
       (:data:`SLOT_COPY_PROOF`). This is what tells an orientation swap apart
       from #7147's score drift, whose remedy is the opposite one.

    The two series are gated SEPARATELY and per series, on the same principle: a
    series is swapped only if its own last point is demonstrably in the swapped
    orientation. A series that is already correct, or that disagrees with both
    orientations, is left alone and reported — swapping it on the strength of
    the event row's defect would be assuming the thing to be proven.
    """
    home_name = getattr(row, "home_team_name", None)
    away_name = getattr(row, "away_team_name", None)
    plan = OrientationPlan(
        event_id=getattr(row, "id", None),
        sport_key=getattr(row, "sport_key", None),
        matchup=f"{home_name} vs {away_name}",
        stored_score=(getattr(row, "home_score", None), getattr(row, "away_score", None)),
    )

    if ee is None:
        plan.action = "skip_espn_not_found"
        plan.reason = "ESPN did not serve this espn_id (gotcha #53: not a fact about the row)"
        return plan

    if getattr(ee, "status", None) != "post":
        plan.action = "skip_espn_not_final"
        plan.reason = f"ESPN status is {getattr(ee, 'status', None)!r}, not 'post'"
        return plan

    espn_home = _as_int(getattr(ee, "home_score", None))
    espn_away = _as_int(getattr(ee, "away_score", None))
    plan.espn_score = (espn_home, espn_away)
    if espn_home is None or espn_away is None:
        plan.action = "skip_espn_no_score"
        plan.reason = "ESPN served no usable final score"
        return plan

    plan.verdict = espn_orientation_verdict(row, ee)
    if plan.verdict == ESPN_ORIENTATION_ALIGNED:
        plan.action = "skip_aligned"
        plan.reason = "our home is ESPN's home — nothing to repair"
        return plan
    if plan.verdict != ESPN_ORIENTATION_SWAPPED:
        plan.action = "skip_unresolved"
        plan.reason = (
            "orientation UNRESOLVED — the row's names could not be read against "
            "ESPN's. Not evidence of a swap; never repaired."
        )
        return plan

    # 🔴 EACH STORE IS JUDGED ON ITS OWN, AND THE REASON IS MEASURED, NOT
    # THEORETICAL. #7338 released mid-build on 2026-09-20 and its live sweep
    # reached the specimen inside the 6h post-commence window: it corrected
    # `events.home_score` to 38-27 and appended one correctly-oriented
    # `score_snapshots` row — while `espn_snapshots` stayed frozen at 102
    # swapped rows (#922 skips the append for completed events) and the ESPN
    # probability leg stayed at 0.0 for the side that won. A rail gated on one
    # global test keyed on `events.home_score` reads that half-healed row as
    # "not slot copied" and walks away from the half still on the page. That is
    # a repair windowed on the very column a partial repair already moved.
    #
    # So the verdict decides MEMBERSHIP — it is identity-keyed and a partial
    # heal cannot move it — and each store then carries its own positive proof.
    # No store is ever written on another store's evidence, which is what keeps
    # #7147's boundary intact: a store that merely DISAGREES with ESPN is left
    # alone and reported.
    slot_pair = (espn_home, espn_away)
    true_pair = (espn_away, espn_home)

    stored_home = _as_int(getattr(row, "home_score", None))
    stored_away = _as_int(getattr(row, "away_score", None))
    if (stored_home, stored_away) == slot_pair:
        # Our home corresponds to ESPN's AWAY competitor, so ESPN's away score
        # is our home's. Written from ESPN rather than as a blind exchange of
        # our own two columns: the authority's number is the one we can defend.
        plan.new_home_score = espn_away
        plan.new_away_score = espn_home
    elif (stored_home, stored_away) == true_pair:
        plan.series_notes.append("events score: already correct, left alone")
    else:
        plan.series_notes.append(
            f"events score: stored {stored_home}-{stored_away} is neither ESPN's "
            f"slot pair nor the true pair — score/espn_id drift is #7147's rail, "
            f"left alone"
        )

    for label, last, attr in (
        ("espn_snapshots", last_espn_snapshot, "swap_espn_snapshots"),
        ("score_snapshots", last_score_snapshot, "swap_score_snapshots"),
    ):
        if last is None:
            plan.series_notes.append(f"{label}: no rows")
            continue
        pair = (_as_int(last[0]), _as_int(last[1]))
        if pair == slot_pair:
            setattr(plan, attr, True)
        elif pair == true_pair:
            plan.series_notes.append(f"{label}: already correct, left alone")
        else:
            plan.series_notes.append(
                f"{label}: last point {pair[0]}-{pair[1]} matches neither "
                f"orientation, left alone"
            )

    # The ESPN leg's own positive proof, mirroring the score's. A leg written by
    # the slot copy holds ESPN's HOME probability, so on a settled game it
    # agrees with ESPN's own home outcome: ~1 when ESPN's home won, ~0 when it
    # lost. Our home is ESPN's away, so that is exactly backwards for us and the
    # honest remedy is the complement — never a zeroing, and never applied to a
    # leg that is merely undecided.
    current = getattr(row, "espn_win_prob_home", None)
    value = None
    if current is not None:
        try:
            value = float(current)
        except (TypeError, ValueError):
            plan.series_notes.append("espn_win_prob_home unreadable, left alone")
    if value is not None:
        espn_home_won = espn_home > espn_away
        decisive = value <= 0.1 or value >= 0.9
        if decisive and (value >= 0.9) == espn_home_won:
            plan.complement_espn_leg = True
            plan.new_espn_win_prob_home = round(1.0 - value, 6)
        elif decisive:
            plan.series_notes.append(
                f"espn leg {value} already reads for the side that won, left alone")
        else:
            plan.series_notes.append(
                f"espn leg {value} is undecided on a settled game — not evidence "
                f"of an inversion, left alone")

    if (plan.new_home_score is not None or plan.swap_espn_snapshots
            or plan.swap_score_snapshots or plan.complement_espn_leg):
        plan.action = "repair_orientation"
        plan.reason = SLOT_COPY_PROOF
    else:
        plan.action = "skip_nothing_to_repair"
        plan.reason = (
            "orientation is SWAPPED but no store still holds ESPN's values in "
            "ESPN's slots — already repaired, or never slot-copied"
        )
    return plan


async def ensure_backup_table(session) -> None:
    """Runtime DDL, attended invocation only (ruling 47(c)).

    ``CREATE TABLE IF NOT EXISTS bak_*`` inside a repair that runs only when a
    person invokes it is explicitly NOT migration-class: the invocation is the
    attended step. Nothing schedules this rail.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_CREATE_SQL))


async def bank_prior_state(session, plan: OrientationPlan, counts: dict) -> None:
    """Copy this event's pre-repair state into :data:`BAK_TABLE`.

    Called INSIDE the event's transaction and BEFORE its writes, so the commit
    that lands a repair lands its undo with it: there is no window in which a
    written row has no banked row.

    ``old_win_probability_sources`` is banked whether or not this plan
    complements the ESPN leg — a column the rail CAN write is a column the undo
    must be able to restore.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_COPY_SQL), {
        "event_id": plan.event_id,
        "new_home_score": plan.new_home_score,
        "new_away_score": plan.new_away_score,
        "espn_snapshot_rows": counts.get("espn_snapshots", 0),
        "score_snapshot_rows": counts.get("score_snapshots", 0),
        "espn_leg_rows": counts.get("espn_leg", 0),
    })


async def backup_is_verified(session, event_id: int) -> bool:
    """Is there a banked row for this event? Asked AFTER banking, BEFORE writing.

    Explicitly checks the table's existence first, so a database with no backup
    table answers False rather than raising UndefinedTable — and False refuses
    the write, which is the safe direction (gotcha #53).
    """
    from sqlalchemy import text

    exists = (await session.execute(text(_BAK_EXISTS_SQL))).scalar()
    if not exists:
        return False
    missing = (await session.execute(
        text(_BAK_MISSING_SQL), {"event_id": event_id})).scalar()
    return missing == 0


async def apply_plan(session, plan: OrientationPlan) -> dict:
    """Write ONE event's repair. Caller owns the transaction boundary."""
    from sqlalchemy import text

    written = {}
    # Only when the score itself was proven slot-copied. A half-healed row whose
    # score #7338 already corrected must not have it rewritten from a plan that
    # deliberately left `new_home_score` unset.
    if plan.new_home_score is not None:
        await session.execute(text(_SWAP_EVENT_SCORE_SQL), {
            "event_id": plan.event_id,
            "home_score": plan.new_home_score,
            "away_score": plan.new_away_score,
        })
        written["events"] = 1

    if plan.swap_espn_snapshots:
        r = await session.execute(
            text(_SWAP_ESPN_SNAPSHOTS_SQL), {"event_id": plan.event_id})
        written["espn_snapshots"] = r.rowcount or 0
    if plan.swap_score_snapshots:
        r = await session.execute(
            text(_SWAP_SCORE_SNAPSHOTS_SQL), {"event_id": plan.event_id})
        written["score_snapshots"] = r.rowcount or 0
    if plan.complement_espn_leg:
        r = await session.execute(
            text(_SWAP_ESPN_LEG_SQL), {"event_id": plan.event_id})
        written["espn_leg"] = r.rowcount or 0
        if plan.new_espn_win_prob_home is not None:
            await session.execute(text(_SET_ESPN_WIN_PROB_SQL), {
                "event_id": plan.event_id,
                "value": plan.new_espn_win_prob_home,
            })
        await session.execute(
            text(_COMPLEMENT_WPS_ESPN_SQL), {"event_id": plan.event_id})
    await stamp_written_state(session, plan.event_id)
    return written


async def stamp_written_state(session, event_id: int) -> None:
    """Record what this event's row holds NOW into the backup's manifest half.

    Called AFTER the event's writes and inside the same transaction, so it reads
    our own uncommitted values. See :data:`_BAK_STAMP_SQL` for why the manifest
    is read back off the row rather than assembled from the caller's locals.
    """
    from sqlalchemy import text

    await session.execute(text(_BAK_STAMP_SQL), {"event_id": event_id})


async def _row_counts(session, plan: OrientationPlan) -> dict:
    """Row counts for the series THIS PLAN will swap, and zero for the rest.

    🔴 The counts are the undo's instruction sheet, so they must describe the
    writes rather than the tables. Counting every row of every series would tell
    the restore to un-swap a series this plan deliberately left alone — which on
    a half-healed row is the series that is already CORRECT, so the undo would
    introduce the defect the repair exists to remove.
    """
    from sqlalchemy import text

    wanted = {
        "espn_snapshots": ("espn_snapshots", "", plan.swap_espn_snapshots),
        "score_snapshots": ("score_snapshots", "", plan.swap_score_snapshots),
        "espn_leg": ("win_prob_snapshots", " AND source = 'espn'",
                     plan.complement_espn_leg),
    }
    out = {}
    for key, (table, extra, will_write) in wanted.items():
        if not will_write:
            out[key] = 0
            continue
        out[key] = (await session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE event_id = :e{extra}"),
            {"e": plan.event_id})).scalar() or 0
    return out


async def repair(session, apply: bool, limit: int = 50, sport: Optional[str] = None,
                 offset: int = 0, since_days: int = 60) -> dict:
    """Scan a bounded slice of settled rows and repair the swapped ones."""
    from sqlalchemy import text
    from app.services.espn_api import ESPNAPIService

    params = {"sport_key": sport, "since_days": since_days}
    population = (await session.execute(text(_POPULATION_SQL), params)).scalar() or 0
    rows = (await session.execute(
        text(_CANDIDATE_SQL), {**params, "limit": limit, "offset": offset})).mappings().all()

    if apply:
        await ensure_backup_table(session)
        await session.commit()

    res = {
        "population": population, "offset": offset, "limit": limit,
        "since_days": since_days, "sport": sport,
        "scanned": len(rows), "next_offset": offset + len(rows),
        "remaining": max(0, population - (offset + len(rows))),
        "swapped": 0, "repaired": 0, "aligned": 0, "unresolved": 0,
        "nothing_to_repair": 0, "espn_not_found": 0, "espn_not_final": 0,
        "espn_no_score": 0, "backup_refused": 0,
        "errors": 0, "error_rows": [],
        "rows_written": {"events": 0, "espn_snapshots": 0,
                         "score_snapshots": 0, "espn_leg": 0},
        "post_final_pinned_rows": {},
        "ledger": [],
    }

    client = ESPNAPIService()
    try:
        for row in rows:
            try:
                await _scan_one(session, client, row, res, apply)
            except Exception as exc:  # noqa: BLE001 - one row must not end the pass
                # Gotcha #42: one bad item must never wipe the pass. A resumable
                # rail is worse than useless if a single unreachable espn_id or a
                # single constraint violation costs the other 49 rows their scan
                # AND leaves the offset cursor unadvanced, so the next invocation
                # re-reads the same poison row forever.
                await session.rollback()
                res["errors"] += 1
                res["error_rows"].append(f"ev{row['id']}: {type(exc).__name__}: {exc}")
    finally:
        close = getattr(client, "close", None)
        if close:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe

    return res


async def _scan_one(session, client, row, res: dict, apply: bool) -> None:
    """Plan and, when applying, repair ONE row.

    Raises on its own row; :func:`repair` isolates it so one unreachable
    ``espn_id`` or one constraint violation cannot end the pass.
    """
    from sqlalchemy import text

    # A plain object rather than the RowMapping: `espn_orientation_verdict`
    # reads by getattr and a mapping would answer UNRESOLVED for every row.
    proj = type("Row", (), dict(row))()
    ee = await client.get_event(row["sport_key"], str(row["espn_id"]))

    last_espn = (await session.execute(
        text(_LAST_ESPN_SNAPSHOT_SQL), {"event_id": row["id"]})).first()
    last_score = (await session.execute(
        text(_LAST_SCORE_SNAPSHOT_SQL), {"event_id": row["id"]})).first()

    plan = plan_orientation_repair(proj, ee, last_espn, last_score)

    key = _ACTION_COUNTERS.get(plan.action)
    if key:
        res[key] += 1
    if plan.verdict == ESPN_ORIENTATION_SWAPPED:
        res["swapped"] += 1

    if not plan.writes:
        # A skip is only worth a ledger line when it is a judgement a reader
        # might dispute. `aligned` is the overwhelming majority and says nothing.
        if plan.verdict in (ESPN_ORIENTATION_SWAPPED, ESPN_ORIENTATION_UNRESOLVED):
            res["ledger"].append(plan)
        return

    pinned = (await session.execute(
        text(_POST_FINAL_PINNED_SQL), {"event_id": row["id"]})).all()
    for src, n in pinned:
        res["post_final_pinned_rows"][src] = \
            res["post_final_pinned_rows"].get(src, 0) + n

    res["ledger"].append(plan)
    if not apply:
        return

    counts = await _row_counts(session, plan)
    await bank_prior_state(session, plan, counts)
    if not await backup_is_verified(session, plan.event_id):
        # No bank, no write. The rollback drops the half-written bank with it,
        # so the next invocation sees this row exactly as it found it.
        await session.rollback()
        res["backup_refused"] += 1
        return
    written = await apply_plan(session, plan)
    await session.commit()
    res["repaired"] += 1
    for k, v in written.items():
        res["rows_written"][k] = res["rows_written"].get(k, 0) + v


async def run(apply: bool, limit: int, sport: Optional[str], offset: int,
              since_days: int) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, limit=limit, sport=sport, offset=offset,
                           since_days=since_days)

    print(f"=== #7354 settled orientation swap ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"population={res['population']} (settled, espn_id, last {res['since_days']}d"
          + (f", sport={res['sport']}" if res["sport"] else "") + ")")
    print(f"COVERAGE: scanned {res['scanned']} of {res['population']} "
          f"at offset {res['offset']} — every count below is over the SCANNED "
          f"set, not the population (remaining {res['remaining']}, "
          f"next_offset {res['next_offset']})")
    print(f"swapped={res['swapped']} repairable={sum(1 for p in res['ledger'] if p.writes)} "
          f"aligned={res['aligned']} unresolved={res['unresolved']} "
          f"nothing_to_repair={res['nothing_to_repair']}")
    print(f"espn_not_found={res['espn_not_found']} "
          f"espn_not_final={res['espn_not_final']} espn_no_score={res['espn_no_score']}")

    for p in res["ledger"][:60]:
        if p.writes:
            score = (f"{p.stored_score[0]}-{p.stored_score[1]} -> "
                     f"{p.new_home_score}-{p.new_away_score}"
                     if p.new_home_score is not None else
                     f"score {p.stored_score[0]}-{p.stored_score[1]} left as-is")
            print(f"  [repair] ev{p.event_id} [{p.sport_key}] {p.matchup}: {score}"
                  f"  espn_snapshots={'swap' if p.swap_espn_snapshots else 'no'}"
                  f" score_snapshots={'swap' if p.swap_score_snapshots else 'no'}"
                  f" espn_leg={'complement' if p.complement_espn_leg else 'no'}")
            for n in p.series_notes:
                print(f"      note: {n}")
        else:
            print(f"  [{p.action}] ev{p.event_id} [{p.sport_key}] {p.matchup}: {p.reason}")

    if res["post_final_pinned_rows"]:
        print("\nREPORTED, NOT REPAIRED — post-final pinned probability rows on the "
              "repaired events (a different mechanism; see the module docstring "
              "and #7354):")
        for src, n in sorted(res["post_final_pinned_rows"].items()):
            print(f"  {src}: {n} rows captured after completed_at")

    if res["errors"]:
        # Loud, and never folded into a skip bucket: a row that RAISED was not
        # judged, and reporting it as "aligned" would be the rail lying about
        # its own coverage.
        print(f"\n🔴 {res['errors']} row(s) RAISED and were not judged "
              f"(the pass continued — gotcha #42):")
        for line in res["error_rows"][:20]:
            print(f"  {line}")

    if apply:
        print(f"\nCOMMITTED events={res['repaired']} "
              f"rows: {res['rows_written']} backup_refused={res['backup_refused']}")
        print(f"UNDO: python3 scripts/restore_7354_settled_orientation_swap.py --apply")
        if res["remaining"]:
            print(f"Re-run with --offset {res['next_offset']} "
                  f"({res['remaining']} rows remaining).")
    else:
        print("\nDRY-RUN — pass --apply to commit.")


USAGE = """repair_7354_settled_orientation_swap — settled ESPN orientation swaps

  --apply             commit (default is a dry-run ledger that writes nothing)
  --limit N           rows to scan this invocation (default 50)
  --offset N          resume cursor; advance by the printed next_offset
  --since-days N      floor on commence_time (default 60) — oldest-first inside it
  --sport KEY         restrict to one sport key
  --help              print this and exit without opening a database

Only a positive `swapped` verdict whose stored score is ESPN's pair in ESPN's
own slots is ever written. Undo:

  python3 scripts/restore_7354_settled_orientation_swap.py --apply
"""

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        sys.exit(0)
    _limit, _offset, _since, _sport = 50, 0, 60, None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            _limit = int(sys.argv[i + 1])
        if a == "--offset" and i + 1 < len(sys.argv):
            _offset = int(sys.argv[i + 1])
        if a == "--since-days" and i + 1 < len(sys.argv):
            _since = int(sys.argv[i + 1])
        if a == "--sport" and i + 1 < len(sys.argv):
            _sport = sys.argv[i + 1]
    asyncio.run(run("--apply" in sys.argv, _limit, _sport, _offset, _since))
