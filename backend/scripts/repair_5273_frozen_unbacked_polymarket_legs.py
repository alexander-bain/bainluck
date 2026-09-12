"""#5273 — retire the frozen Polymarket blend legs a DERIVATIVE market wrote.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15308654`, Warrington Town
FC vs. South Liverpool FC. The served payload, read 2026-09-12 ~21:4xZ:

    "win_probability_sources": {"polymarket": {"value": 0.085,
      "display_name": "Polymarket", "updated_at": "2026-09-09T20:15:16Z",
      "evidence_status": "unverified"}}

8.5% for the home side, and Polymarket is the ONLY key in the column, so 8.5% is
the number the site has for that match. It is not a wrong win probability — it is
a correct price for a different question. The row that wrote it recorded its own
name at write time:

    Warrington Town FC vs. South Liverpool FC - Exact Score

`- 1st Half Exact Score`, `- More Markets`, `: Both Teams to Score` are the other
spellings. 233 events are frozen in this shape.

── WHY THESE ARE FROZEN, WHICH IS THE WHOLE REASON A REPAIR IS NEEDED ──────────

The write side is CLOSED and this is the residue. All four writers of the
Polymarket leg gate on `admissible_as_blend_speaker` and stamp an `eligibility`
pointer beside the value — the matcher, the 120s poll, the WS lane, and
`backfill-wps`. Measured on production 2026-09-12 20:5xZ: 280 of 280
live-or-future Polymarket legs carry a pointer and are backed by a `moneyline`
market, and `future_and_no_pointer` is 0 in every readable status. No new prop
can land in the winner slot.

But a gate governs WRITES, and `_retire_unbacked_blend_source` (#5031/#5548) —
the path that RETRACTS a leg no admissible market can back — only ever arrives on
an event some selector hands it. `prediction_market_matching.py` selects
`["scheduled","live"]` (x3) and `["completed","closed"]` (x2). **`suspended`
appears nowhere in the file.** So a suspended event's leg has no writer on any
edge: the gate cannot refuse it (it was written before the gate), and the
retirement cannot reach it (nothing selects it). It simply stands, forever.

That is why the cohort is defined by STATUS rather than by age, and why the two
statuses are `suspended` and `scheduled` — the events no live writer visits. A
`closed` or `completed` event carrying a pointer-less leg is NOT in scope: the
completed-catchup selector does reach it, so the live path is already its owner
and a second writer racing it is how two repairs disagree. (Root cause routed to
lane1, whose file that selector is.)

── THE SCREEN IS THE EVENT'S OWN RECORDED PRODUCERS, AND IT IS UNANIMOUS ───────

🔴 DO NOT SCREEN ON "the event has no winner market today". That screen convicts
107 events and it is WRONG. A market's row is mutable: it can be renamed,
re-linked, or re-pointed onto a TWIN long after it wrote, so "what markets does
this event have now" judges a 2026-08-30 write by a 2026-09-12 fact.
`repair_5432_*`'s docstring is the standing proof (market 60383004, a genuine
moneyline whose `event_id` had moved to the duplicate event). Regraded on
write-time evidence those 107 split 30 convict / 3 ACQUIT / 74 undecidable — and
the 3 acquittals are three correctly-written legs a naive screen would have
destroyed.

So the evidence is what the producer RECORDED at write time, and the unit is the
event:

    win_prob_snapshots.game_state->>'market_name' -> live_blend._class_says_game_winner

and the test is UNANIMITY over every producer the event ever recorded, not the
nearest one in time. That choice is not caution, it is what the data supports.
Picking "the snapshot nearest the leg's `updated_at`" needs a tolerance, and the
gap distribution is bimodal (116 convictions within an hour of the leg write, 102
more than six hours away), so any tolerance is a judgement call that moves the
population by ~100 events. Unanimity needs no tolerance — and measured on
production 2026-09-12 21:3xZ, over all 783 distinct (event, producer) pairs in
the cohort:

    events recording at least one producer name          781
      every recorded producer REFUTED  (convict)         233
      every recorded producer admissible (acquit)        548
      MIXED — some admissible, some refuted                0

**Zero mixed.** 779 of 781 events recorded exactly one distinct producer name
ever. So "which snapshot wrote the leg" cannot change any verdict here, and the
tolerance question disappears rather than being answered.

── THE COHORT, measured on production 2026-09-12 21:3x-21:4xZ ──────────────────

    pointer-less Polymarket legs, suspended + scheduled       1,126
      CONVICT  — every recorded producer refuted                233
      ACQUIT   — a recorded producer is a game winner           548
      UNDECIDABLE — no producer recorded at all                 345

    the 233, in detail
      status                                     233 suspended, 0 scheduled
      commence_time in the future                              0
      Polymarket is the SOLE key in the column               231
      ... the other 2 hold only `statpal_injuries` metadata beside it, which is
      not a probability source, so all 233 lose their only PROBABILITY source.

FAIL-OPEN ON ABSENCE. The 345 undecidable rows have no recorded producer — the
older `{market_id, backfill: True}` snapshot shape, or no Polymarket snapshot at
all. That is NO EVIDENCE, not evidence of guilt. They are REPORTED by every run
and repaired by none (gotcha #53), so the residue is counted rather than silently
dropped. A whitespace-only name is the same case and is skipped before the
recognizer sees it — `"   "` is truthy, and a bare `if not name` would hand it to
a recognizer that answers "not a game winner" and convict on nothing at all.

── THE EMPTIED COLUMN IS THE INTENDED OUTCOME, NOT A REFUSAL ───────────────────

Retiring the leg on 231 of these events empties `win_probability_sources`
entirely, and that is correct. It is the settled doctrine and it is what the live
path already does everywhere it can reach: `_retire_unbacked_blend_source` calls
`prune_blend_source(wps, source, 0)` with no test for what else remains, and
#5432 acceptance 2 states the rule — a derivative-only group draws an honest
blank, never the best-looking prop. An abandoned fixture showing nothing is
strictly better than one showing an Exact Score price as the match winner.

This is the one place where this repair deliberately differs from
`repair_5432_*`, whose group-cost test refuses to empty an event's CHART. The
subjects are different: that repair deletes history rows and an empty chart is a
larger separate defect (#3612); this one retracts a live claim, and withdrawing a
false claim needs no replacement to be an improvement.

THE RULE IS CALLED, NEVER COPIED — twice over. `_class_says_game_winner` decides
guilt and `prune_blend_source` computes the new column value, both imported from
the modules the live writers use. The #1951 failure is a second copy that does
not throw when it disagrees, it just quietly answers differently. So the value
this script writes is bit-for-bit the value `_retire_unbacked_blend_source` would
have written had its selector ever reached the event, and
`test_repair_writes_what_the_live_retirement_writes_5273` pins exactly that.

WHAT IS NOT TOUCHED, each with another owner:

  * `futures_markets` / `futures_outcomes` — no market is retired or re-linked.
    The derivative books are real books and keep their prices.
  * `win_prob_snapshots` — the chart's history rail. `repair_5432_*` owns the
    derivative rows there; this script only READS them, as evidence.
  * any event whose recorded producer is a game winner, and any event that
    recorded no producer at all.
  * any event a live writer still visits (`closed`, `completed`, `live`), and
    any event whose `commence_time` is still in the future — refused at runtime
    rather than trusted from today's measurement, because a future event is the
    one case where a reader could be watching and a writer could be arriving.

RESTORE, one command (D51(b)):

    UPDATE events e
       SET win_probability_sources = b.win_probability_sources
      FROM bak_5273_blend_legs b
     WHERE b.event_id = e.id
       AND b.event_id IN (SELECT event_id FROM bak_5273_repair_manifest);

  The restore is only as honest as the backup, and #5595 is why the backup is
  checked by CONTENT rather than by id: a row staged in one session and changed
  before a later pass used to restore its stale value. Two windows, two
  mechanisms — `--backup` evicts and re-stages a drifted row before copying, and
  the UPDATE is a compare-and-swap on the whole backed-up value, so a row that
  moved after reconciliation is DECLINED rather than written. Every event this
  script changed has an exact backup, or it was not changed.

RUNTIME DDL, ATTENDED INVOCATION ONLY (standing notice 47(c)). The two
`CREATE TABLE IF NOT EXISTS backup_*` statements run only when a person invokes
`--backup`; nothing here runs on merge or on release, and this is not
migration-class. `--backup`/`--apply` refuse unless `HEROKU_APP_NAME` is
`bainluck-heavy`, so the write cannot be fired from a laptop pointed at
production with whatever happens to be checked out. A dry run only reads and runs
anywhere.

USAGE:

    python3 scripts/repair_5273_frozen_unbacked_polymarket_legs.py
    heroku run:detached -a bainluck-heavy \
        "python3 scripts/repair_5273_frozen_unbacked_polymarket_legs.py --backup"
    heroku run:detached -a bainluck-heavy \
        "python3 scripts/repair_5273_frozen_unbacked_polymarket_legs.py --backup --apply"

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later.
"""

import argparse
import asyncio
import collections
import json
import os
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_5273_blend_legs"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited via #5221/#5246/#5432). A value backup records what a column held
#: and cannot record that this script is what changed it.
MANIFEST_TABLE = "bak_5273_repair_manifest"

#: The leg this repair judges, and the pointer whose ABSENCE defines the cohort.
#: Read from the shared module rather than retyped: a jsonb key census that
#: retypes its key from prose returns a confident zero.
SOURCE = "polymarket"

#: The statuses no live writer visits — see the module docstring. Deliberately
#: NOT "every status with a pointer-less leg": `closed`/`completed` are reached
#: by the completed-catchup selector, so the live path owns them.
IN_SCOPE_STATUSES = ("suspended", "scheduled")

#: The only app that may WRITE. Notice 47(c): runtime DDL is attended, and the
#: invocation is the attended step, so the script must be able to tell that it
#: IS the attended invocation rather than a laptop with production credentials.
PRODUCER_APP = "bainluck-heavy"

#: The sanity floor, ~80% of the 233-event plan measured on production
#: 2026-09-12 21:3xZ (see the module docstring's cohort table).
#:
#: Two causes present as a small plan — a broken filter and an already-drained
#: backlog — so the floor is paired with a DISCRIMINATOR rather than an
#: `--allow-small` override, which would let the first through wearing the
#: second's clothes (the #5246 lesson, where the discriminator existed and did
#: not reach the decision).
#:
#: No writer adds to this population: every writer of the leg now stamps an
#: eligibility pointer, so a newly written leg is not pointer-less. The plan can
#: still move a little as events change status INTO scope, which is why this is
#: a floor with a discriminator and not an equality assertion.
SANITY_FLOOR = 186

SQL = {
    # Stage 1. The cohort: a Polymarket leg with no eligibility pointer, on an
    # event no live writer visits. `commence_time` travels so the future-event
    # refusal is computed from the row rather than assumed from a measurement.
    "candidates": f"""
        SELECT e.id                      AS event_id,
               e.status                  AS status,
               e.commence_time           AS commence_time,
               e.commence_time > NOW()   AS still_future,
               e.win_probability_sources AS wps
          FROM events e
         WHERE e.win_probability_sources ? '{SOURCE}'
           AND NOT (e.win_probability_sources->'{SOURCE}' ? 'eligibility')
           AND e.status = ANY(CAST(:statuses AS text[]))
         ORDER BY e.id
    """,
    # Stage 2. Every producer name the event ever recorded — DISTINCT pairs, not
    # rows: the recognizer runs in Python and the verdict is a property of the
    # name. 783 pairs over a 1,126-event cohort, so this is a small scan.
    "recorded_producers": """
        SELECT DISTINCT w.event_id                   AS event_id,
                        w.game_state->>'market_name' AS market_name
          FROM win_prob_snapshots w
         WHERE w.source = :source
           AND w.event_id = ANY(CAST(:events AS int[]))
           AND w.game_state ? 'market_name'
    """,
    "bak_create": f"""
        CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
            event_id                integer PRIMARY KEY,
            win_probability_sources jsonb,
            staged_at               timestamptz NOT NULL DEFAULT NOW())
    """,
    "bak_copy": f"""
        INSERT INTO {BAK_TABLE} (event_id, win_probability_sources)
        SELECT e.id, e.win_probability_sources
          FROM events e
         WHERE e.id = ANY(CAST(:ids AS int[]))
           AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.event_id = e.id)
    """,
    "bak_missing": f"""
        SELECT count(*) FROM events e
         WHERE e.id = ANY(CAST(:ids AS int[]))
           AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.event_id = e.id)
    """,
    # #5595 — PRESENCE BY ID IS NOT COVERAGE. `bak_copy` skips any event already
    # staged, so a leg backed up in an earlier session and CHANGED since
    # reconciles clean by id while the stored value is a false record of what is
    # about to be replaced. The comparison is therefore on the VALUE.
    "bak_stale": f"""
        SELECT count(*) FROM events e
          JOIN {BAK_TABLE} b ON b.event_id = e.id
         WHERE e.id = ANY(CAST(:ids AS int[]))
           AND b.win_probability_sources IS DISTINCT FROM e.win_probability_sources
    """,
    # The repair, not merely the alarm: drop the divergent backup rows so the
    # ordinary `bak_copy` re-stages them from live. An event still carrying its
    # leg has not been repaired by any pass, so live is the truth the undo must
    # restore — refreshing loses nothing.
    "bak_evict_stale": f"""
        DELETE FROM {BAK_TABLE} b
         USING events e
         WHERE b.event_id = e.id
           AND e.id = ANY(CAST(:ids AS int[]))
           AND b.win_probability_sources IS DISTINCT FROM e.win_probability_sources
    """,
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run. A missing table yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    "man_create": f"""
        CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} (
            event_id   integer PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT NOW())
    """,
    "man_record": f"""
        INSERT INTO {MANIFEST_TABLE} (event_id, applied_at)
        VALUES (:event_id, :now)
        ON CONFLICT (event_id) DO UPDATE SET applied_at = EXCLUDED.applied_at
    """,
    # THE FORWARD WRITE, and it is a compare-and-swap on the whole backed-up
    # value. Three premises are re-checked at write time, each one a thing that
    # could have changed since the plan was computed:
    #
    #   * the leg is still there and still pointer-less — a writer that arrived
    #     in between has stamped it, and a stamped leg is not this repair's;
    #   * the column still matches its backup exactly — otherwise the undo that
    #     exists for this event is not a faithful copy of what we are replacing
    #     (#5595, second half: `reconcile_backup` reads without a lock and
    #     commits nothing, so a value can still move between the clean check and
    #     this write);
    #
    # A row failing any of them is DECLINED, not written, and counted as such —
    # which this script reports as the good case.
    "update": f"""
        UPDATE events e
           SET win_probability_sources = CAST(:new_wps AS jsonb)
         WHERE e.id = :event_id
           AND e.win_probability_sources ? '{SOURCE}'
           AND NOT (e.win_probability_sources->'{SOURCE}' ? 'eligibility')
           AND EXISTS (SELECT 1 FROM {BAK_TABLE} b
                        WHERE b.event_id = e.id
                          AND b.win_probability_sources
                              IS NOT DISTINCT FROM e.win_probability_sources)
        RETURNING e.id
    """,
}


class _RecordedMarket:
    """The producer a snapshot row RECORDED, shaped for the shared recognizer.

    `external_id` is None on purpose and it is inert here: the recognizer reads
    it only to spot a Kalshi `kx...` ticker (a `KXNBA2HSPREAD` title that looks
    like a bare matchup is really a spread), and every row this script can see is
    `source='polymarket'`, whose external ids are opaque numerics that match no
    branch. Pinned by `test_shim_external_id_is_inert_5273` so a future
    recognizer that DOES read a Polymarket id fails the guard instead of silently
    re-classifying the population.
    """

    __slots__ = ("name", "external_id")

    def __init__(self, name: Optional[str]) -> None:
        self.name = name
        self.external_id = None


def producer_is_game_winner(market_name: Optional[str]) -> bool:
    """Call the ONE shared admission rule on a recorded producer name.

    Imported inside the function so the module stays importable — and its pure
    helpers testable — without dragging the app's model layer into the process.
    """
    from app.utils.live_blend import _class_says_game_winner

    return _class_says_game_winner(_RecordedMarket(market_name))


def retired_leg_value(wps: Optional[dict]) -> tuple[dict, bool]:
    """The column value after retiring the leg — computed by the LIVE function.

    `prune_blend_source` is what `_retire_unbacked_blend_source` calls, with the
    same `remaining_linked=0`, so this repair cannot write a shape the live path
    would not have written. Re-implementing "pop the key" here would be a second
    copy of a one-line rule, which is exactly how the two drift when the rule
    grows a second clause.
    """
    from app.tasks.prediction_market_matching import prune_blend_source

    return prune_blend_source(wps, SOURCE, 0)


class EventVerdict(NamedTuple):
    """One event's verdict and the evidence it rests on.

    `producers` travels with the verdict so a plan line can name what convicted
    an event without a second lookup — a repair whose output cannot be checked
    against the row it changed is a repair nobody can grade.
    """

    event_id: int
    verdict: str
    producers: tuple[str, ...]


CONVICT = "convict"
ACQUIT = "acquit"
MIXED = "mixed"
UNDECIDABLE = "undecidable"


def grade_events(candidate_ids, producer_rows) -> list[EventVerdict]:
    """Grade every candidate event on the producers it RECORDED, unanimously.

    Four verdicts and only one of them acts:

      * CONVICT     — at least one recorded producer, and every one is refused
                      by the shared gate. The leg cannot have been written by
                      anything but a derivative.
      * ACQUIT      — every recorded producer is a game winner.
      * MIXED       — the event recorded both kinds. Measured 0 on production,
                      and it is NOT convicted: with a genuine winner market among
                      the producers, "which one wrote the leg" becomes a question
                      this screen deliberately refuses to answer with a
                      timestamp. A non-zero MIXED count is a finding, reported.
      * UNDECIDABLE — no producer recorded at all. No evidence, so no verdict.

    A NULL, empty or WHITESPACE-ONLY name is not a recorded producer and is
    dropped before grading. 🔴 THE STRIP IS LOAD-BEARING: `"   "` is truthy in
    Python, so a bare `if not name` would hand a blank to the recognizer, which
    answers "not a game winner" — and the event would be CONVICTED on no
    evidence at all, the one direction this function exists to refuse.
    """
    by_event = collections.defaultdict(list)
    for row in producer_rows:
        entry = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        name = entry.get("market_name")
        if not name or not name.strip():
            continue
        by_event[int(entry["event_id"])].append(name)

    verdicts = []
    for event_id in candidate_ids:
        names = tuple(sorted(set(by_event.get(event_id, ()))))
        if not names:
            verdicts.append(EventVerdict(event_id, UNDECIDABLE, ()))
            continue
        refuted = [n for n in names if not producer_is_game_winner(n)]
        if len(refuted) == len(names):
            verdicts.append(EventVerdict(event_id, CONVICT, names))
        elif refuted:
            verdicts.append(EventVerdict(event_id, MIXED, names))
        else:
            verdicts.append(EventVerdict(event_id, ACQUIT, names))
    return verdicts


def refuse_future_events(verdicts, still_future) -> tuple[list, list]:
    """Split the convictions into (plannable, refused-because-future).

    Measured 0 on production, and computed at runtime anyway. A future event is
    the one case in this cohort where a reader could be watching the number and a
    live writer could be about to arrive — a scheduled event moves to `live` and
    the matcher's own selector picks it up — so the repair and the writer would
    be racing over one column. Refusing costs nothing: the live path is the right
    owner of an event it can actually reach.
    """
    plannable, refused = [], []
    for v in verdicts:
        (refused if still_future.get(v.event_id) else plannable).append(v)
    return plannable, refused


def backup_is_exact(recon) -> bool:
    """The D51 gate: every planned event has a backup, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


class SmallPlanVerdict(NamedTuple):
    """A small plan's diagnosis AND what it means for `--apply`.

    Two facts, deliberately not collapsed into one string: #5246 shipped this
    discriminator as a bare message while the caller tested `if small:`, so both
    causes refused `--apply` identically and the discriminator only ever changed
    the wording of the refusal. It cost that repair a session.
    """

    blocks_apply: bool
    message: str


def explain_small_plan(plan_count: int, manifest_rows: int) -> SmallPlanVerdict:
    """Why is the plan below the floor — a broken filter, or a drained backlog?

    The manifest is the discriminator, because only a successful forward write
    puts an event in it. Fail-closed stays the default: an unrecognised shape
    would have to be added here deliberately, as a blocking one.
    """
    if plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(blocks_apply=False, message="")
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(
            blocks_apply=False,
            message=(
                f"ALREADY APPLIED — {manifest_rows} events are in "
                f"{MANIFEST_TABLE} and {plan_count} remain, which together clear "
                f"the floor of {SANITY_FLOOR}. This is a drained backlog, not a "
                f"broken filter, so --apply proceeds."
            ),
        )
    return SmallPlanVerdict(
        blocks_apply=True,
        message=(
            f"FILTER BROKE — only {plan_count} events are plannable and "
            f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} "
            f"of an expected {SANITY_FLOOR}+ are accounted for. Either the "
            f"cohort query stopped matching or the recognizer moved. Do NOT "
            f"lower the floor; find the events."
        ),
    )


def wrong_app_refusal(args) -> Optional[str]:
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere — locally, on either app. A write
    must be the attended invocation standing notice 47(c) describes, and the only
    thing that distinguishes an attended `heroku run:detached` from a laptop
    holding production credentials is which dyno it is on.

    `HEROKU_APP_NAME` is populated by the `runtime-dyno-metadata` lab, enabled on
    both `bainluck` and `bainluck-heavy`. Unset means not a dyno at all, which is
    precisely the case this gate exists to stop, so it refuses too rather than
    falling through.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. This script "
        f"creates its backup tables at runtime and rewrites a served column, so "
        f"the invocation IS the attended step (standing notice 47(c)) and it "
        f"happens on one named app. Re-run with `heroku run:detached -a "
        f"{PRODUCER_APP} \"python3 scripts/{os.path.basename(__file__)} ...\"`."
    )


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def backup(session, ids) -> int:
    """Stage the undo, refreshing any value that drifted since an earlier pass.

    Returns the number of stale backup rows evicted and re-staged (#5595), so the
    caller can say so out loud rather than silently repairing.
    """
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    refreshed = 0
    for chunk in _chunks(ids, 5000):
        # Evict BEFORE copying: `bak_copy` skips events already present, so a
        # divergent value would otherwise never be re-staged. Ordering is the
        # whole fix.
        refreshed += int(
            (
                await session.execute(text(SQL["bak_evict_stale"]), {"ids": chunk})
            ).rowcount
            or 0
        )
        await session.execute(text(SQL["bak_copy"]), {"ids": chunk})
    await session.commit()
    return refreshed


async def reconcile_backup(session, ids) -> dict:
    """Does the backup cover every planned event, by VALUE and not just by id?

    Two keys, deliberately not summed: `missing` means no backup row exists,
    `stale` means one exists and disagrees with the live column. They have
    different causes and the second is the #5595 defect, so collapsing them into
    one count would hide which one fired.
    """
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = stale = 0
    for chunk in _chunks(ids, 5000):
        missing += int(
            (await session.execute(text(SQL["bak_missing"]), {"ids": chunk})).scalar_one()
        )
        stale += int(
            (await session.execute(text(SQL["bak_stale"]), {"ids": chunk})).scalar_one()
        )
    return {"events": missing, "stale_backup_rows": stale}


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return

    async with get_task_session() as s:
        candidates = (
            await s.execute(
                text(SQL["candidates"]), {"statuses": list(IN_SCOPE_STATUSES)}
            )
        ).fetchall()
        rows = [dict(c._mapping) for c in candidates]
        ids = [int(r["event_id"]) for r in rows]
        wps_by_event = {int(r["event_id"]): r["wps"] for r in rows}
        future_by_event = {int(r["event_id"]): bool(r["still_future"]) for r in rows}
        by_status = collections.Counter(r["status"] for r in rows)

        print(f"pointer-less {SOURCE} legs, {'/'.join(IN_SCOPE_STATUSES)} : "
              f"{len(ids)}  ({dict(by_status)})")
        if not ids:
            print("\nnothing in scope — nothing to plan.")
            return

        producers = []
        for chunk in _chunks(ids, 5000):
            producers += (
                await s.execute(
                    text(SQL["recorded_producers"]),
                    {"events": chunk, "source": SOURCE},
                )
            ).fetchall()

        verdicts = grade_events(ids, producers)
        tally = collections.Counter(v.verdict for v in verdicts)
        print(f"  CONVICT     : {tally[CONVICT]}  (every recorded producer refused)")
        print(f"  ACQUIT      : {tally[ACQUIT]}  (a recorded producer is a winner)")
        print(f"  MIXED       : {tally[MIXED]}  (both kinds recorded — never planned)")
        print(f"  UNDECIDABLE : {tally[UNDECIDABLE]}  (no producer recorded, "
              f"fail-open, never planned)")

        convicted = [v for v in verdicts if v.verdict == CONVICT]
        plannable, future = refuse_future_events(convicted, future_by_event)

        plan = []
        for v in plannable:
            new_wps, changed = retired_leg_value(wps_by_event[v.event_id])
            if changed:
                plan.append((v, new_wps))
        plan_ids = [v.event_id for v, _ in plan]

        if args.limit:
            plan = plan[: args.limit]
            plan_ids = plan_ids[: args.limit]

        print(f"\nRETIRE : {len(plan_ids)} events")
        print(f"REFUSE : {len(future)} events (commence_time is still in the "
              f"future — the live writer is their owner)")
        for v, new_wps in plan[:5]:
            print(f"   e.g. {v.event_id}: {v.producers[0]!r} -> "
                  f"{sorted(new_wps) or 'no sources left'}")

        manifest_rows = await manifest_count(s)
        small = explain_small_plan(len(plan_ids), manifest_rows)
        if small.message:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"   {small.message}")

        if not args.backup and not args.apply:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return

        if not plan_ids:
            print("\nnothing to do.")
            return

        if args.backup:
            refreshed = await backup(s, plan_ids)
            print(f"\nbacked up {len(plan_ids)} events into {BAK_TABLE}")
            if refreshed:
                print(f"  refreshed {refreshed} stale backup rows that had drifted "
                      f"since an earlier pass (#5595) — restoring them would have "
                      f"written a stale column value")

        recon = await reconcile_backup(s, plan_ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned event.")
            return

        if not args.apply:
            print("\nbackup staged — re-run with --apply to write.")
            return

        if small.blocks_apply:
            print("REFUSING --apply: plan is below the sanity floor (see above).")
            return

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = 0
        for v, new_wps in plan:
            done = (
                await s.execute(
                    text(SQL["update"]),
                    {"event_id": v.event_id, "new_wps": json.dumps(new_wps)},
                )
            ).fetchall()
            if done:
                await s.execute(
                    text(SQL["man_record"]), {"event_id": v.event_id, "now": now}
                )
                applied += 1
        await s.commit()
        declined = len(plan_ids) - applied
        print(f"\napplied {applied}, declined {declined} "
              f"(a decline means the event moved under us — the good case)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="copy every planned event's column into the backup table")
    p.add_argument("--apply", action="store_true",
                   help="retire the legs (requires an exact backup)")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    p.add_argument("--dry-run", action="store_true",
                   help="alias for the default plan-only mode; reads nothing else")
    args = p.parse_args()
    if args.dry_run:
        args.backup = args.apply = False
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
