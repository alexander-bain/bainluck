"""The #2693 twin fold, run on a clock instead of when a human remembers. #3811.

**SHIP: a twin that forms tonight is folded tonight.** Concretely — the US Open
men's semi-final page never again reaches match day with an empty markets
section while Kalshi's price for that exact match sits open in our database.
(Pillar: MATCHING · TRUTH.)

WHAT WAS ACTUALLY BROKEN, AND IT WAS NOT THE JUDGEMENT
══════════════════════════════════════════════════════
``proven_duplicates.folded_event_ids``, wired into ``_build_game_markets``,
works — verified on production. It is driven by exactly one input: the
``provenance:duplicate-of:<canonical>`` tag on the ghost row. That tag had two
writers, and on 2026-09-07 neither reached the match that mattered:

1. ``event_registry._proven_duplicates``, at row-creation time.
2. ``scripts/repair_2878_tennis_twin_ghosts.py`` — **a hand-run script. No
   Celery task, no beat entry, no runbook.**

So the fold was starved. Measured on the specimen, 34 hours before a Slam
semi-final::

    15306391  Shelton   / Alcaraz         tennis_atp           created 03:03Z  2 open Kalshi markets
    15306813  Ben Shelton / Carlos Alcaraz tennis_atp_us_open  created 04:35Z  0 markets

``/events/15306813`` rendered with no markets section at all. Running the sweep
by hand tagged it and the page immediately gained Kalshi's exact-score ladder.
**The judgement only ran when a human ran it.** This module is the clock.

WHY WRITER (1) CANNOT REACH THIS PAIR — confirmed on the specimen, not assumed
══════════════════════════════════════════════════════════════════════════════
``_proven_duplicates`` guards 1-3 are id-anchored (ruling 048 arm B) and guard 4
requires the candidate within ``_SAME_FIXTURE_MAX_SEPARATION`` (30 minutes). The
two rows above share **no** provider id — the ghost carries ``external_id``,
``espn_id`` and ``statpal_fixture_id`` all NULL while the canonical carries all
three — and their kickoffs are ``18:30`` against ``15:30``, **three hours** apart,
because the ghost's stamp is Kalshi's close time (gotcha #14). Both arms fail by
construction, and it fires only at ingest, so even a repaired predicate would
not reach the rows already in the table. A sweep is the fix, not a better guard.

WHY THIS IS A SWEEP AND NOT A REIMPLEMENTATION
═══════════════════════════════════════════════
Every helper below was LIFTED from ``scripts/repair_2878_tennis_twin_ghosts.py``
rather than rewritten, and that script now imports them from here. There is one
population query, one plan floor, one backup and one writer, with two callers —
the beat and the CLI. **Two matchers that disagree is the failure ruling 048
exists to end**, and a scheduled copy of a hand-run script is how you get one.

The judgement itself was already pure and already shared:
:func:`app.utils.tennis_twin_pairs.plan_twin_tags`. Nothing here re-decides
anything it says.

🔴 A LABEL, NEVER A MERGE
═════════════════════════
The only write is one element appended to ``events.event_tags``. No DELETE, no
``UPDATE futures_markets SET event_id``, no repoint. The tag has a shipped reader
and **no deleter anywhere in the codebase**, so the whole effect is "do not print
a second card" and ``scripts/restore_2878_tennis_twin_ghosts.py --apply`` takes
every tag back — including the ones this task writes, because it banks into the
same ``bak_2878_twin_ghost_tags`` table the restore reads. That reversibility is
what puts an unattended recurring write inside D51, and it is the whole reason
this is allowed to be scheduled at all.

THE CADENCE IS SIZED AGAINST THE RACE, NOT GUESSED
═══════════════════════════════════════════════════
The ghost is minted when a prediction market beats the Odds API to the fixture,
and nothing re-points the markets when the real row lands. So the harm window
opens when the SECOND row is created and closes when this sweep next runs: with
cadence T, a twin double-prints for at most T.

    measured race on the specimen         92 minutes (03:03Z → 04:35Z)
    Polymarket ingest (fastest generator) 1h
    Kalshi ingest                         2h
    chosen cadence                        30 min  (``crontab(minute="8,38")``)

A daily sweep would still have missed this match, and an hourly one only matches
the fastest thing that can mint a ghost — it would lag half a generation on
average. 30 minutes bounds the double-print at half the fastest ingest cycle. The
run is a ~1,500-row indexed read plus a pure in-memory plan and, in steady state,
zero writes, so the cost of the headroom is negligible. ``:08/:38`` sits clear of
``reconcile-unanchored-events`` (``:18/:48``) and ``merge-duplicate-events``
(``:00/:30``).

THE VERDICT CONTRACT — the two zeros are not the same zero
═══════════════════════════════════════════════════════════
Acceptance 5 of #3811: *"a sweep that silently tags nothing is exactly how this
went unnoticed"* (gotcha #53). But "wrote nothing" has two meanings that must not
share a verdict, and :func:`plan_refusal_reason` already draws the line — **the
floor is on the PLAN, not on the write**:

``complete``
    The plan reaches the population and every pair it can decide carries its
    label. In steady state this is the common run and it writes ZERO tags: the
    durable artifact is the label set, and it is on disk. Reading this as
    not-GREEN would trade one false GREEN for ninety-six false REDs a day.
``partial``
    Tags were written but a planned ghost is still untagged, or a row exhausted
    its retries. Real progress, unfinished run.
``failed``
    The plan fell outside the measured band — below the floor, above the
    ceiling, or empty outright — so the judgement has stopped reaching the
    population; or the population read itself raised, in which case ``measured``
    is ``false``. 🔴 **The band is asked on every run, including the quiet ones.**
    Whether anything was left to write does not enter into it: an empty plan has
    nothing outstanding too, and treating that as the idempotent re-run is the
    false GREEN CERT-2193 found.
``no_work``
    The window holds no tennis rows at all. Authoritative "I looked and there was
    nothing", never GREEN. Rare, and correct: a sweep over an empty population
    cannot vouch for anything.

Enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` from birth (#1884),
because this task's founding defect IS the false GREEN.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import timedelta

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.tennis_twin_pairs import (
    MAX_TWIN_SEPARATION,
    TwinRow,
    is_tournament_key,
    plan_twin_tags,
    row_has_settled_result,
    row_is_id_anchored,
)

#: D51 backup. Holds the ghost's `event_tags` exactly as they were before the
#: append, plus the canonical the tag names — so the undo can be surgical
#: (remove ONE element) rather than a clobber of the whole array.
#:
#: The same table the CLI banks into and the same one
#: `restore_2878_tennis_twin_ghosts.py` reads, so one restore command undoes
#: every tag regardless of which caller wrote it.
BAK_TABLE = "bak_2878_twin_ghost_tags"

#: The window the sweep reads. Wide enough to cover a Slam fortnight plus the
#: qualifying week before it; deliberately NOT the whole table, because the
#: block key is a global `(surname, surname)` pair with no time component and a
#: wider read is a wider chance of fusing two meetings between the same players.
DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_LOOKAHEAD_DAYS = 5

#: Sanity band on the PLAN, measured 2026-09-06 at 162 tags over 1,430 rows.
#: The floor exists because a repair that finds nothing and reports success is
#: the worst outcome there is.
#:
#: 🔴 **It is never waived.** It used to be skipped whenever every candidate was
#: already tagged — the idempotent re-run — and that waiver was the hole
#: CERT-2193 found: an empty plan over a live population also has nothing
#: outstanding, so it took the same exit and recorded GREEN forever. The
#: idempotent re-run does not need the waiver, because a healthy steady state
#: clears the floor on the size of its PLAN (167 on the specimen), not on the
#: size of its write.
MIN_EXPECTED_TAGS = 20
MAX_EXPECTED_TAGS = 600

_POPULATION_SQL = """
SELECT e.id,
       s.key                AS sport_key,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.home_score,
       e.away_score,
       e.external_id,
       e.espn_id,
       e.statpal_fixture_id,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'tennis%%'
   AND e.commence_time >= now() - make_interval(days => :lookback)
   AND e.commence_time <= now() + make_interval(days => :lookahead)
   AND e.status NOT IN ('voided', 'merged')
   AND e.id > :cursor
 ORDER BY e.id
 LIMIT :page
"""


async def load_rows(session, *, lookback: int, lookahead: int, page: int = 2000):
    """Every tennis row in the window, paged by id.

    Paged because the read is a plain cursor scan and `db-query`-shaped single
    reads cap out; the cursor key IS the sort key, which is the only shape that
    cannot skip or repeat a row.
    """
    from sqlalchemy import text

    out, cursor = [], 0
    while True:
        rows = (
            await session.execute(
                text(_POPULATION_SQL),
                {
                    "lookback": lookback,
                    "lookahead": lookahead,
                    "cursor": cursor,
                    "page": page,
                },
            )
        ).all()
        out.extend(rows)
        if len(rows) < page:
            return out
        cursor = rows[-1].id


def build_plan(rows, *, max_separation: timedelta = MAX_TWIN_SEPARATION):
    """Turn database rows into the pure planner's inputs and run it.

    Every field the judgement reads is copied to a scalar here. `events` is
    write-hot and the writer commits per row, so a live ORM object read after a
    commit boundary would lazy-load in a sync context (gotcha #6) — and a
    judgement that reads the database is a judgement nobody can test.
    """
    snapshots = [
        TwinRow(
            event_id=r.id,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            sport_key=r.sport_key,
            is_tournament_keyed=is_tournament_key(r.sport_key),
            has_settled_result=row_has_settled_result(
                home_score=r.home_score, away_score=r.away_score
            ),
            is_id_anchored=row_is_id_anchored(
                external_id=r.external_id,
                espn_id=r.espn_id,
                statpal_fixture_id=r.statpal_fixture_id,
            ),
        )
        for r in rows
    ]
    return plan_twin_tags(
        snapshots,
        commence_times={r.id: r.commence_time for r in rows},
        max_separation=max_separation,
    )


def already_tagged_ids(rows) -> set[int]:
    """Ghosts that already carry SOME `duplicate-of` tag.

    Read off the serialised array with the same prefix the reader matches on, so
    the writer and the reader cannot drift. A row already labelled a duplicate of
    anything is left entirely alone — re-tagging it would be this sweep
    arbitrating between its own finding and an existing one.
    """
    return {r.id for r in rows if DUPLICATE_TAG_PREFIX in (r.tags_text or "")}


def plan_refusal_reason(plan, *, untagged: int) -> str | None:
    """Why this plan must NOT be applied, or ``None`` if it is safe. Pure.

    🔴 **The floor is on the PLAN, not on the write.** It used to be on
    ``untagged``, and that was right exactly once — on the first run, when the
    two numbers were the same. The moment 162 labels existed, the floor started
    reading every legitimate incremental run as a failure: the six unplayed US
    Open quarter-finals of 2026-09-07 are a plan of 167 tags of which 6 are new,
    and a floor of 20 on the delta refuses that and exits 1.

    The question the floor exists to ask is "does the judgement still reach this
    population?", and the answer to that is the size of the PLAN. How much of
    the plan is already on disk is a fact about previous runs, not about whether
    this one is sane. ``untagged`` keeps only its one honest job: telling an
    idempotent no-op apart from a real write.

    That distinction is load-bearing on a 30-minute clock in a way it never was
    for a hand-run script: nearly every scheduled run has ``untagged == 0``, so a
    floor on the write would refuse the healthy steady state ninety-six times a
    day.

    🔴 **THE BAND IS ASKED FIRST, AND ``untagged`` NEVER BYPASSES IT** (CERT-2193,
    repair ``TWIN-SWEEP-NONVACUOUS-PLAN-FLOOR-3811``). This function used to
    return ``None`` the instant ``untagged == 0``, before looking at the plan at
    all. That read as "everything is already labelled", but it is also what an
    EMPTY plan over a live population looks like: no tags planned means nothing
    outstanding means the guard waved it through, and
    :func:`run_tennis_twin_sweep` then took its ``not todo`` exit and returned
    ``terminal: complete``. A planner regression — a renamed sport key, a moved
    name column — would therefore have recorded GREEN on every one of ninety-six
    daily runs while every newly formed twin went untagged and double-printed.
    That is this task's founding defect wearing the costume of its own guard,
    which is why the task is in ``ENFORCED_TASKS`` at all.

    So the band is now unconditional and ``untagged`` keeps no veto — only a
    voice in the message, where it tells an operator whether work was stranded
    by the refusal or whether the run merely looked quiet.
    """
    outstanding = (
        f"{untagged} candidate(s) still untagged"
        if untagged
        else "nothing was outstanding, which is exactly how this used to read GREEN"
    )

    if not plan.tags:
        return (
            f"the plan decides NO pair at all across {plan.rows_considered} "
            f"tennis row(s) in {plan.blocks_examined} block(s) — {outstanding}. A "
            f"sweep that labels nothing has not shown that it still reaches its "
            f"population, so it cannot vouch for the fold. Re-measure before "
            f"writing."
        )
    if len(plan.tags) < MIN_EXPECTED_TAGS:
        return (
            f"the plan decides only {len(plan.tags)} pair(s), below the floor "
            f"{MIN_EXPECTED_TAGS} — {outstanding}. Either the population has "
            f"moved or the judgement has stopped reaching it. Re-measure before "
            f"writing."
        )
    if len(plan.tags) > MAX_EXPECTED_TAGS:
        return (
            f"the plan writes {len(plan.tags)} tags, above the ceiling "
            f"{MAX_EXPECTED_TAGS} — the population is far beyond what was "
            f"measured; re-measure before writing."
        )
    return None


def fold_is_live() -> bool:
    """Does the event page actually fold a tagged ghost's markets onto its canonical?

    🔴 **The deploy-order guard from the repair script's docstring, made
    mechanical.** An unplayed ghost is usually the row holding the prices —
    Andreeva/Potapova was 13 markets on the ghost against **0** on its canonical.
    So tagging an unplayed ghost while the read side is NOT folding does not
    remove a duplicate card, it removes the only card with prices on it.

    For the hand-run script that check was a human curling
    ``/api/events/<canonical>/game-markets`` before ``--apply``. A task on a
    30-minute clock has nobody to do that, so it is asserted here every run:
    the unplayed arm is dropped if ``_build_game_markets`` has stopped calling
    the fold.

    Source inspection rather than a live request because the question is about
    THIS process's code, not about a round trip — and it is the same check
    ``test_proven_duplicate_2263`` already pins the fold with, so the guard and
    its test read the same way. It cannot detect a fold that is wired but
    broken; that is what the end-to-end guard in
    ``test_proven_duplicate_2263.py`` is for.
    """
    try:
        from app.routes.events import _build_game_markets

        return "folded_event_ids" in inspect.getsource(_build_game_markets)
    except Exception:  # noqa: BLE001 — unreadable source is "cannot prove it", i.e. no
        return False


def unplayed_ghost_ids(plan, rows) -> set[int]:
    """The ghosts in ``plan`` whose match has not been played yet.

    The unplayed arm is the one gated on :func:`fold_is_live`, and the plan does
    not label its own arms — ``TwinTag.reason`` records the orientation, not the
    evidence. It is recovered here from the same field ``classify_pair`` split
    on: a pair is the unplayed arm exactly when the CANONICAL carries no final
    score, because a ghost never carries one on either arm.
    """
    settled = {
        r.id
        for r in rows
        if row_has_settled_result(home_score=r.home_score, away_score=r.away_score)
    }
    return {t.ghost_id for t in plan.tags if t.canonical_id not in settled}


async def tagged_now(session, ghost_ids) -> set[int]:
    """Which of ``ghost_ids`` carry a ``duplicate-of`` tag, read back from disk.

    The post-write proof, and it re-reads rather than trusting ``rowcount``:
    ``write_tags`` is idempotent in the DATABASE (``NOT @>``), so a row that was
    already tagged returns ``rowcount`` 0 and a row whose write silently did not
    land returns 0 too. Only a read tells those apart (gotcha #53).

    Targeted at the ids just written instead of re-running the window scan —
    ``todo`` is a handful of rows in steady state and the window is ~1,500, so
    verifying by re-reading everything would triple the run's cost to learn
    something about five rows.
    """
    from sqlalchemy import text

    if not ghost_ids:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT id FROM events "
                " WHERE id = ANY(:ids) "
                "   AND CAST(COALESCE(event_tags, '[]'::jsonb) AS text) LIKE :pat"
            ),
            {"ids": list(ghost_ids), "pat": f"%{DUPLICATE_TAG_PREFIX}%"},
        )
    ).all()
    return {r.id for r in rows}


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's CURRENT `event_tags` before anything is appended.

    `ON CONFLICT DO NOTHING` keeps the FIRST banked value, which is the
    pre-repair one — a re-run after a partial apply must not overwrite a clean
    banked array with one that already carries the tag we wrote.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  canonical_id bigint NOT NULL,"
            "  old_tags text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = 0
    for tag in tags:
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, canonical_id, old_tags) "
                "VALUES (:eid, :cid, :old) ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": tag.ghost_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.ghost_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def write_tags(session, tags, *, progress_every: int = 25):
    """Append the duplicate tag to each ghost, ONE ROW PER TRANSACTION.

    Core SQL with a server-side `||`, never an ORM assignment: `event_tags` is
    JSONB and gotcha #4 is that a JSONB ORM assignment can silently fail to
    persist, gotcha #5 that mixing the two styles in one session is where flush
    ordering bites. The `NOT @>` makes it idempotent in the DATABASE rather than
    in this process's memory, so a re-run cannot double-append.

    Single-row and patient rather than one batched UPDATE: `events` is write-hot
    (constant poller and backfill locks) and a batched write rolls back on every
    row where a patient single-row write succeeds.

    Returns ``(written, failed_ids)``. Failures are RETAINED, not just printed —
    on a detached dyno whose stdout nobody reads, a printed FAILED line that does
    not reach the caller is indistinguishable from a clean run (gotcha #53).
    """
    from sqlalchemy import text

    written, failed = 0, []
    for index, tag in enumerate(tags, start=1):
        payload = json.dumps([duplicate_tag(tag.canonical_id)])
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events "
                        "SET event_tags = COALESCE(event_tags, '[]'::jsonb) "
                        "                 || CAST(:tag_array AS jsonb) "
                        "WHERE id = :eid "
                        "  AND NOT COALESCE(event_tags, '[]'::jsonb) "
                        "          @> CAST(:tag_array AS jsonb)"
                    ),
                    {"tag_array": payload, "eid": tag.ghost_id},
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {tag.ghost_id} after 3 attempts: {exc}")
                    failed.append(tag.ghost_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(tags)} processed, {written} tagged")
    return written, failed


async def run_tennis_twin_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
) -> dict:
    """One scheduled pass: read the window, plan, bank, tag. Returns the summary.

    ``apply`` defaults to TRUE, unlike ``reconcile_unanchored_events``, and the
    difference is the one ruling 048 turns on: that task's apply path DELETEs, so
    it stays dry until Alex rules. This one appends a reversible label with no
    deleter and banks the prior value first, which is exactly D51's shape. A
    dry-run schedule would tag nothing and leave the page broken — i.e. it would
    ship the measurement and not the fix, which is what CLAUDE.md's first section
    forbids.
    """
    from app.tasks.base import get_task_session

    summary: dict = {
        "task": "tennis_twin_sweep",
        "issue": "#3811",
        "fold": "#2693",
        "apply": apply,
        "measured": True,
        "lookback_days": lookback,
        "lookahead_days": lookahead,
    }

    async with get_task_session() as session:
        try:
            rows = await load_rows(session, lookback=lookback, lookahead=lookahead)
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        if not rows:
            return {
                **summary,
                "terminal": "no_work",
                "reason": (
                    f"no tennis rows in the window (-{lookback}d/+{lookahead}d), so "
                    f"this pass can vouch for nothing"
                ),
                "rows_read": 0,
            }

        plan = build_plan(rows)
        tagged = already_tagged_ids(rows)
        todo = [t for t in plan.tags if t.ghost_id not in tagged]

        # 🔴 The deploy-order guard. Only the UNPLAYED arm depends on the fold,
        # so a missing fold drops those tags and keeps the settled ones — the
        # settled arm shipped and ran before the fold existed.
        folding = fold_is_live()
        withheld: list[int] = []
        if not folding:
            unplayed = unplayed_ghost_ids(plan, rows)
            withheld = sorted(t.ghost_id for t in todo if t.ghost_id in unplayed)
            todo = [t for t in todo if t.ghost_id not in unplayed]

        summary.update(
            {
                "rows_read": len(rows),
                "blocks_examined": plan.blocks_examined,
                "pairs_found": len(plan.tags),
                "already_tagged": len(plan.tags) - len(todo) - len(withheld),
                "tags_to_write": len(todo),
                "refusals": len(plan.refusals),
                "refusal_sample": list(plan.refusals[:20]),
                "fold_live": folding,
                "withheld_unplayed": withheld[:20],
            }
        )

        blocked = plan_refusal_reason(plan, untagged=len(todo) + len(withheld))
        if blocked:
            return {**summary, "terminal": "failed", "reason": blocked, "written": 0}

        if withheld:
            # Never silent: the fold going missing is the one condition under
            # which this task must not do its main job, so it says so loudly
            # rather than reporting a clean small run (gotcha #53).
            return {
                **summary,
                "terminal": "failed",
                "reason": (
                    f"_build_game_markets no longer calls folded_event_ids, so "
                    f"{len(withheld)} unplayed ghost(s) were NOT tagged — tagging "
                    f"them without the fold would remove the only card with prices"
                ),
                "written": 0,
            }

        if not todo:
            # The healthy steady state, and it must read GREEN. The artifact this
            # task exists to produce — every decidable pair carrying its label —
            # is on disk; see the module docstring's verdict contract. Checked
            # BEFORE `apply`, because with nothing to write the two modes leave
            # the database in the identical state and a dry run has withheld
            # nothing.
            return {
                **summary,
                "terminal": "complete",
                "reason": (
                    f"every pair this sweep can decide is already labelled "
                    f"({len(plan.tags)} in plan)"
                ),
                "written": 0,
                "banked": 0,
            }

        if not apply:
            return {
                **summary,
                "terminal": "no_work",
                "reason": f"dry run — {len(todo)} tag(s) withheld",
                "written": 0,
            }

        current = {r.id: (r.tags_text or "[]") for r in rows}
        banked = await ensure_backup(session, todo, current)
        written, failed = await write_tags(session, todo, progress_every=0)

        after_tagged = await tagged_now(session, [t.ghost_id for t in todo])
        still_untagged = [t.ghost_id for t in todo if t.ghost_id not in after_tagged]

        problems = []
        if failed:
            problems.append(f"{len(failed)} row(s) exhausted their retries: {failed[:20]}")
        if still_untagged:
            problems.append(
                f"{len(still_untagged)} planned ghost(s) carry no tag after the run: "
                f"{still_untagged[:20]}"
            )

        return {
            **summary,
            "terminal": "partial" if problems else "complete",
            "reason": (
                "; ".join(problems)
                if problems
                else f"{written} ghost(s) now fold onto their canonical"
            ),
            "written": written,
            "banked": banked,
            "failed_ids": failed[:20],
            "still_untagged": still_untagged[:20],
            "undo": "python3 scripts/restore_2878_tennis_twin_ghosts.py --apply",
        }
