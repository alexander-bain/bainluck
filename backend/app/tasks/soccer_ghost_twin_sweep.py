"""#5896 — stop advertising a soccer match that was played two days ago.

**SHIP: on the La Liga page, Sevilla v Valencia stops appearing as tonight's
19:00 kick-off when it finished 1-0 on Wednesday.** (Pillar: MATCHING.)

Ten such rows were live on production on 2026-09-13 — four La Liga, four
Argentine Primera, one Segunda, one Brasileirao — each of them a second copy of
a fixture that had already been played, each dated at a round placeholder hour
on a later day, each carrying no score and no authority fixture id while the
real row carried both. The judgement that decides which of two rows is the ghost
is :mod:`app.utils.soccer_ghost_twins`; this module is the half that reads the
database and writes the label.

WHAT IT WRITES, AND WHY THAT IS THE WHOLE FIX
══════════════════════════════════════════════

One element appended to the ghost's ``event_tags``:
``provenance:duplicate-of:<canonical>``. That label already has a read side that
shipped and runs — :func:`app.utils.proven_duplicates.not_a_proven_duplicate`
sits on the league rails, the team rails, the search rails and the feed
candidate query, and :func:`~app.utils.proven_duplicates.folded_event_ids` folds
the ghost's markets onto the canonical inside ``_build_game_markets``. So the
sweep needs no new reader, no new column and no migration: it feeds an existing
rail that was starved of a writer for this class.

Nothing is merged, deleted or repointed. The ghost keeps its row, its id and its
markets; one predicate reverts the label; and the prior array is banked first
(D51), with a one-command undo in
``scripts/restore_5896_soccer_ghost_tags.py``.

WHY THE BAND IS ON THE POPULATION AND NOT ON THE PLAN
══════════════════════════════════════════════════════

Its tennis sibling (:mod:`app.tasks.tennis_twin_sweep`) refuses any plan below
twenty tags, because CERT-2193 found that an empty plan over a live population
reads exactly like "everything is already labelled" and had been recording GREEN
forever. That floor is right there and wrong here, and copying it would be the
most plausible mistake this module could make.

Soccer ghosts are EPISODIC, not continuous. Measured on production 2026-09-13:
ten pairs, all of them advertised for that same evening, and **zero in the
preceding thirty days**. A Slam fortnight always has twins; a Tuesday in
September may honestly have none. A plan floor would therefore refuse the
healthy quiet day and drown its own signal.

So the same question — *does the judgement still reach its population?* — is
asked of the READ instead: :data:`MIN_EXPECTED_ROWS` rows of soccer inside the
window, measured at 1,493 for -5d/+5d. A renamed sport key, a moved column or a
broken join collapses that number and the run refuses; an honestly quiet
matchday does not. The ceiling :data:`MAX_EXPECTED_TAGS` still guards the other
direction, where a pairing regression starts labelling real fixtures.

VERDICT CONTRACT
════════════════

``complete``
    The window was read, the band held, and every pair this sweep can decide
    carries its label — including the common case where it decided none.
``partial``
    Rows were planned and some of them do not carry the tag afterwards, read
    back from disk rather than inferred from ``rowcount``.
``failed``
    The band did not hold, the fold is not wired, or the population read raised
    (``measured: false``). Never a quiet zero.
``no_work``
    The window holds no soccer rows at all, or this was a dry run. An
    authoritative "I looked and there was nothing", never GREEN.

Enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` from birth (#1884
precedent), for the same reason its sibling is: the failure this task guards
against is a clean-looking zero.
"""

from __future__ import annotations

import asyncio
import inspect
import json

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.soccer_ghost_twins import (
    SoccerRow,
    plan_ghost_tags,
    row_has_final_score,
    row_is_fixture_anchored,
)

#: D51 backup. Holds each ghost's `event_tags` exactly as they were before the
#: append, plus the canonical the tag names, so the undo can remove ONE element
#: rather than clobber a shared multi-valued column.
#:
#: Its own table rather than the tennis sweep's `bak_2878_twin_ghost_tags`,
#: deliberately: sharing it would make the two repairs' undos inseparable, and
#: "roll back the soccer sweep" would silently restore every tennis ghost too.
BAK_TABLE = "bak_5896_soccer_ghost_tags"

#: The window the sweep reads. The ghost must be in the future to be a defect at
#: all, and its canonical sits at most `MAX_GHOST_LAG` (3 days) behind it, so a
#: -5d/+5d window covers the whole decidable population with margin. Wider is
#: not safer here: it is more rows for the same ten answers.
DEFAULT_LOOKBACK_DAYS = 5
DEFAULT_LOOKAHEAD_DAYS = 5

#: Non-vacuity floor, on the READ. Measured 2026-09-13 at 1,493 soccer rows in
#: the -5d/+5d window; the floor is set well below that because a genuinely thin
#: international break is a real state and must not read as a failure, while a
#: renamed sport key or a broken join collapses this to single digits.
MIN_EXPECTED_ROWS = 200

#: Ceiling on the PLAN, measured at 10. A pairing regression that starts
#: labelling real fixtures shows up here first, and a sweep is never the thing
#: that gets to decide it has found sixty times more duplicates than anyone has
#: ever measured.
MAX_EXPECTED_TAGS = 120

_POPULATION_SQL = """
SELECT e.id,
       s.key                AS sport_key,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.status,
       e.home_score,
       e.away_score,
       e.espn_id,
       e.statpal_fixture_id,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'soccer%%'
   AND e.commence_time >= now() - make_interval(days => :lookback)
   AND e.commence_time <= now() + make_interval(days => :lookahead)
   AND e.status NOT IN ('voided', 'merged')
   AND e.id > :cursor
 ORDER BY e.id
 LIMIT :page
"""


async def load_rows(session, *, lookback: int, lookahead: int, page: int = 2000):
    """Every soccer row in the window, paged by id.

    The cursor key IS the sort key, which is the only shape that cannot skip or
    repeat a row while the table is being written underneath the scan.
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


def build_plan(rows, *, now):
    """Copy every judgement input to a scalar, then run the pure planner.

    Scalars because the writer commits per row and a live ORM object read after
    a commit boundary lazy-loads in a sync context (gotcha #6) — and because a
    judgement that can reach the database is a judgement nobody can test.
    """
    snapshots = [
        SoccerRow(
            event_id=r.id,
            sport_key=r.sport_key,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            commence_time=r.commence_time,
            status=r.status,
            has_final_score=row_has_final_score(
                home_score=r.home_score, away_score=r.away_score
            ),
            is_fixture_anchored=row_is_fixture_anchored(
                espn_id=r.espn_id, statpal_fixture_id=r.statpal_fixture_id
            ),
        )
        for r in rows
    ]
    return plan_ghost_tags(snapshots, now=now)


def already_tagged_ids(rows) -> set[int]:
    """Rows already carrying SOME `duplicate-of` tag.

    Read off the serialised array with the same prefix the reader matches on, so
    writer and reader cannot drift. A row already labelled a duplicate of
    anything is left entirely alone: re-tagging it would be this sweep
    arbitrating between its own finding and someone else's.
    """
    return {r.id for r in rows if DUPLICATE_TAG_PREFIX in (r.tags_text or "")}


def band_refusal_reason(plan) -> str | None:
    """Why this plan must NOT be applied, or ``None`` if it is safe. Pure.

    🔴 **Asked on every run, including the quiet ones, and never waived by
    "there was nothing outstanding".** That waiver is the hole CERT-2193 found in
    the tennis sibling: an empty plan over a live population has nothing
    outstanding either, so the waiver hands a GREEN to exactly the regression the
    task exists to catch.

    What differs from the sibling is only WHICH number carries the floor. Here it
    is the population read, because an empty plan is the healthy majority state
    for this class — see the module docstring.
    """
    if plan.rows_considered < MIN_EXPECTED_ROWS:
        return (
            f"the window yielded only {plan.rows_considered} soccer row(s), below "
            f"the floor {MIN_EXPECTED_ROWS} — the judgement is not reaching its "
            f"population (a renamed sport key, a moved column, a broken join). "
            f"Re-measure before writing."
        )
    if len(plan.tags) > MAX_EXPECTED_TAGS:
        return (
            f"the plan labels {len(plan.tags)} row(s), above the ceiling "
            f"{MAX_EXPECTED_TAGS} — far beyond anything measured, which is what a "
            f"pairing regression looks like. Re-measure before writing."
        )
    return None


def fold_is_live() -> bool:
    """Does the event page fold a tagged ghost's markets onto its canonical?

    🔴 **The deploy-order guard, made mechanical** — inherited from the tennis
    sweep, where the lesson was learned: a ghost is not an empty row. Every one
    of the ten measured here carries markets the canonical may not (15298075
    holds eleven resolved Polymarket rows), so tagging while the read side is NOT
    folding does not remove a duplicate card, it moves prices out of reach.

    Source inspection rather than a live request, because the question is about
    THIS process's code and not about a round trip; it is also the check
    ``test_proven_duplicate_2263`` already pins the fold with, so the guard and
    its test read the same way. It cannot detect a fold that is wired but broken
    — that is what the end-to-end guard in that test file is for.
    """
    try:
        from app.routes.events import _build_game_markets

        return "folded_event_ids" in inspect.getsource(_build_game_markets)
    except Exception:  # noqa: BLE001 — unreadable source is "cannot prove it", i.e. no
        return False


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's CURRENT `event_tags` before anything is appended.

    ``ON CONFLICT DO NOTHING`` keeps the FIRST banked value, which is the
    pre-repair one: a re-run after a partial apply must not overwrite a clean
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


async def write_tags(session, tags, *, progress_every: int = 0):
    """Append the duplicate tag to each ghost, ONE ROW PER TRANSACTION.

    Core SQL with a server-side ``||``, never an ORM assignment: ``event_tags``
    is JSONB and gotcha #4 is that a JSONB ORM assignment can silently fail to
    persist, gotcha #5 that mixing the two styles in one session is where flush
    ordering bites. The ``NOT @>`` makes it idempotent in the DATABASE rather
    than in this process's memory, so a re-run cannot double-append.

    Single-row and patient rather than one batched UPDATE: ``events`` is
    write-hot and a batched write rolls back on every row where a patient
    single-row write succeeds.

    Returns ``(written, failed_ids)``. Failures are RETAINED, not merely printed:
    on a worker whose stdout nobody reads, a printed FAILED line that never
    reaches the caller is indistinguishable from a clean run (gotcha #53).
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


async def tagged_now(session, ghost_ids) -> set[int]:
    """Which of ``ghost_ids`` carry a `duplicate-of` tag, read back from disk.

    The post-write proof, and it re-reads rather than trusting ``rowcount``:
    :func:`write_tags` is idempotent in the database, so a row that was already
    tagged returns 0 and a row whose write silently did not land returns 0 too.
    Only a read tells those apart (gotcha #53).
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


async def run_soccer_ghost_twin_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
) -> dict:
    """One scheduled pass: read the window, plan, bank, tag. Returns the summary.

    ``apply`` defaults to TRUE. The apply path appends a reversible label with no
    deleter and banks the prior value first, which is exactly D51's shape; a
    dry-run schedule would measure the defect every half hour and leave the page
    advertising a game that finished on Wednesday.
    """
    from datetime import datetime, timezone

    from app.tasks.base import get_task_session

    summary: dict = {
        "task": "soccer_ghost_twin_sweep",
        "issue": "#5896",
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
                "rows_read": 0,
                "reason": (
                    f"no soccer rows in the window (-{lookback}d/+{lookahead}d), so "
                    f"this pass can vouch for nothing"
                ),
            }

        plan = build_plan(rows, now=datetime.now(timezone.utc))
        tagged = already_tagged_ids(rows)
        todo = [t for t in plan.tags if t.ghost_id not in tagged]
        folding = fold_is_live()

        summary.update(
            {
                "rows_read": len(rows),
                "blocks_examined": plan.blocks_examined,
                # Reported beside the first pass's, never folded into it: the two
                # keys reach different populations and a single total cannot say
                # which of them stopped reaching its own.
                "residual_blocks_examined": plan.residual_blocks_examined,
                "residual_pairs_found": plan.residual_tags,
                "pairs_found": len(plan.tags),
                "already_tagged": len(plan.tags) - len(todo),
                "tags_to_write": len(todo),
                "refusals": len(plan.refusals),
                "refusal_sample": list(plan.refusals[:20]),
                "fold_live": folding,
            }
        )

        blocked = band_refusal_reason(plan)
        if blocked:
            return {**summary, "terminal": "failed", "reason": blocked, "written": 0}

        if todo and not folding:
            # Never silent. The fold going missing is the one condition under
            # which this task must not do its main job, so it says so loudly
            # rather than reporting a clean small run (gotcha #53).
            return {
                **summary,
                "terminal": "failed",
                "written": 0,
                "reason": (
                    f"_build_game_markets no longer calls folded_event_ids, so "
                    f"{len(todo)} ghost(s) were NOT tagged — tagging without the "
                    f"fold moves their markets out of reach instead of removing a "
                    f"duplicate card"
                ),
            }

        if not todo:
            # The healthy majority state, and it must read GREEN: the population
            # floor above has already proved the judgement reached its rows.
            # Checked BEFORE `apply`, because with nothing to write the two modes
            # leave the database identical and a dry run has withheld nothing.
            return {
                **summary,
                "terminal": "complete",
                "written": 0,
                "banked": 0,
                "reason": (
                    f"every ghost this sweep can decide is already labelled "
                    f"({len(plan.tags)} in plan over {plan.rows_considered} row(s))"
                ),
            }

        if not apply:
            return {
                **summary,
                "terminal": "no_work",
                "written": 0,
                "reason": f"dry run — {len(todo)} tag(s) withheld",
            }

        current = {r.id: (r.tags_text or "[]") for r in rows}
        banked = await ensure_backup(session, todo, current)
        written, failed = await write_tags(session, todo)

        after_tagged = await tagged_now(session, [t.ghost_id for t in todo])
        still_untagged = [t.ghost_id for t in todo if t.ghost_id not in after_tagged]

        problems = []
        if failed:
            problems.append(
                f"{len(failed)} row(s) exhausted their retries: {failed[:20]}"
            )
        if still_untagged:
            problems.append(
                f"{len(still_untagged)} planned ghost(s) carry no tag after the run: "
                f"{still_untagged[:20]}"
            )

        return {
            **summary,
            "terminal": "partial" if problems else "complete",
            "written": written,
            "banked": banked,
            "failed_ids": failed[:20],
            "still_untagged": still_untagged[:20],
            "reason": (
                "; ".join(problems)
                if problems
                else f"{written} finished match(es) stopped being advertised as upcoming"
            ),
            "undo": "python3 scripts/restore_5896_soccer_ghost_tags.py --apply",
        }
