"""Tag the Polymarket container row as a duplicate, so its markets serve. #5821.

**SHIP: a match page stops hiding its spread and every total on a duplicate row
the page has already folded away.** (Pillar: MATCHING.)

This is the WRITE half. :mod:`app.utils.polymarket_container_twins` decides; this
module reads the window, banks the prior value and appends one element.

One element is appended to the duplicate's ``event_tags``::

    provenance:duplicate-of:<canonical event id>

which ``app.utils.proven_duplicates.folded_event_ids`` already turns into "serve
this row's markets on the canonical's page" inside ``_build_game_markets``. The
duplicate keeps its row, its id and its markets; nothing is merged, deleted or
repointed, and ``scripts/restore_5821_container_twin_tags.py --apply`` removes
exactly the element this wrote (D51).

WHY THIS IS THE REPAIR AND NOT THE ONE THE ISSUE FIRST PLANNED
═══════════════════════════════════════════════════════════════

CERT-2793 BLOCKed the forward fix for being forward-only and named this repair
``5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE``. The plan recorded on the issue on
2026-09-13 was to re-date ~4,760 rows from ``venue_game_start`` so that the
existing ``fold_twin_events`` key would group them.

**That is no longer the population and this sweep deliberately does not do it.**
Re-measured 2026-09-17: the pairs now share a commence instant exactly, the card
fold already collapses them, and ``/api/events/search`` returns one row. What
survives is the half a card fold cannot reach — the fold hides the card and
leaves the loser's markets on the loser. So the repair is a tag, not a
4,760-row rewrite of a time column during launch week.

THE VERDICT CONTRACT
════════════════════

The band sits on the POPULATION, never on the plan. The legacy split families
are a fixed backlog that this sweep drains and the forward fix
(``_polymarket_container_sibling_event_id``, ``d15f9b4d8``) stops refilling —
container rows minted fell from 85/day and 50/day on 09-12/13 to 0–2/day since.
So an empty plan is the HEALTHY end state here, and a plan floor would start
failing on exactly the day the ship is finished. ``markets_read`` is the floor
that proves the pass still reached its rows.

Refs #5821, #2693, CERT-2793.
"""

from __future__ import annotations

import asyncio
import json
import os

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.polymarket_container_twins import (
    ContainerMarket,
    ContainerRow,
    plan_container_tags,
)

#: D51 backup. Holds each duplicate's `event_tags` exactly as they were before
#: the append, plus the canonical the tag names, so the undo can remove ONE
#: element rather than clobber a shared multi-valued column.
#:
#: Its own table rather than the soccer or tennis sweep's, deliberately: sharing
#: one would make the repairs' undos inseparable, and "roll back the container
#: sweep" would silently restore every soccer ghost too.
BAK_TABLE = "bak_5821_container_twin_tags"

#: The window the sweep reads, in days either side of now.
#:
#: Symmetric, and both halves are load-bearing. The LOOKAHEAD carries the rows a
#: reader can still open — 60 of the 180 families measured on 2026-09-17 had not
#: kicked off. The LOOKBACK carries the rest: a split family does not heal when
#: the match ends, and a settled page that draws no totals is the same defect
#: with the same fix.
#:
#: Measured before it was chosen rather than argued: ±45 days reads 11,391
#: market rows over 1,845 events, which is one bounded SELECT of small tuples.
DEFAULT_LOOKBACK_DAYS = 45
DEFAULT_LOOKAHEAD_DAYS = 45

#: Non-vacuity floor on the population this pass READ, below which the run is
#: `failed` rather than "nothing to do" (CERT-3030).
#:
#: WHICH FLOOR, and why it is on the read rather than on the plan. The two
#: sibling sweeps make opposite choices and the comment in `task_verdict` says
#: why: `tennis_twin_sweep` floors the PLAN, `soccer_ghost_twin_sweep` floors
#: the POPULATION because soccer ghosts are episodic and a plan floor "would
#: have made this task red on most days and taught everyone to ignore it".
#:
#: This sweep is the soccer shape, for a stronger reason than episodicity: its
#: backlog DRAINS. Once the ~173 families are tagged, every later pass plans
#: zero for the rest of time, so a plan floor would be red permanently after
#: the first success. What must stay distinguishable here is "the join went
#: dark / the window read nothing" from "every family is already labelled" —
#: and only the read can tell those apart.
#:
#: WHY 500. Measured, twice, a week apart on the same window: 11,391 markets /
#: 1,845 events (2026-09-17, when the window constants above were chosen) and
#: 11,410 / 1,852 (2026-09-17 re-read for this repair). The floor sits ~23x
#: below a population that moved 0.2% between reads, so no seasonal trough
#: reaches it, while a read that lost its join or its source filter lands far
#: underneath. It is a broken-read detector, not a dip detector.
MIN_MARKETS_FLOOR = 500


async def load_rows(session, *, lookback: int, lookahead: int):
    """Every Polymarket market carrying both venue signals, plus its row's ids.

    Returns ``(markets, rows, current_tags)``.

    Markets with no ``venue_game_start`` are not read at all. One of the two
    venue signals is missing, the key cannot be formed, and the judgement would
    skip them anyway — leaving them in the read would only make the population
    floor below look healthier than the evidence is.

    🔴 The `Event` ORM rows are loaded as well as the market tuples, solely so
    that ``twin_identity_rank`` — the SERVING layer's own survivor election —
    can be computed per row and handed to the judgement. It is imported, never
    re-spelled: a sweep that picked its own winner would tag the row the fold
    then elects, suppress it, and send the reader to the worse of the two.
    """
    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload

    from app.models.models import Event
    from app.utils.event_twin_fold import twin_identity_rank

    result = await session.execute(
        text(
            "SELECT fm.event_id, fm.name, "
            "       fm.market_metadata->>'venue_game_start' AS vgs, "
            "       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text "
            "FROM futures_markets fm "
            "JOIN events e ON e.id = fm.event_id "
            "WHERE fm.source = 'polymarket' "
            "  AND fm.market_metadata->>'venue_game_start' IS NOT NULL "
            # `make_interval(days => <int>)`, never a bind cast to interval
            # carrying the string "45 days". The runtime driver is asyncpg: it
            # infers the parameter's type from the cast, then expects a
            # `timedelta` and calls `.days` on whatever it got. This task died
            # in 251ms on its population read, hourly, writing nothing —
            # measured 2026-09-18 05:27:00Z, `invalid input for query argument
            # $1`. psycopg2 would have interpolated it and never noticed, which
            # is why no gate caught it. `make_interval` is the house idiom (~20
            # call sites, `polymarket.py` among them). The class guard written
            # for this fix immediately found a SECOND live instance —
            # `reconcile_unanchored_events`, whose census had raised the same
            # DataError 383 consecutive times — so the guard is the deliverable
            # here at least as much as the one-line binding change.
            "  AND e.commence_time BETWEEN "
            "        now() - make_interval(days => :lookback) "
            "    AND now() + make_interval(days => :lookahead)"
        ),
        {"lookback": int(lookback), "lookahead": int(lookahead)},
    )

    markets: list[ContainerMarket] = []
    starts: dict[int, set[str]] = {}
    current_tags: dict[int, str] = {}

    for row in result:
        markets.append(
            ContainerMarket(
                event_id=row.event_id, name=row.name or "", venue_game_start=row.vgs
            )
        )
        starts.setdefault(row.event_id, set()).add(row.vgs)
        current_tags[row.event_id] = row.tags_text or "[]"

    # `selectinload(Event.sport)` is REQUIRED, not an optimisation: the
    # election's second-to-last rung prefers a row that NAMES ITS LEAGUE over a
    # `*_other` catch-all (#2866), so it reads `event.sport`. Lazy-loading that
    # from an async session raises, and an unloaded one would silently change
    # the election — the hazard `loaded_sport_key` documents from the other side.
    event_rows = (
        (
            await session.execute(
                select(Event)
                .where(Event.id.in_(list(current_tags)))
                .options(selectinload(Event.sport))
            )
        )
        .scalars()
        .all()
    )

    rows = {
        event.id: ContainerRow(
            event_id=event.id,
            espn_id=event.espn_id,
            statpal_fixture_id=event.statpal_fixture_id,
            venue_game_starts=frozenset(starts.get(event.id, ())),
            identity_rank=tuple(twin_identity_rank(event)),
        )
        for event in event_rows
    }
    return markets, rows, current_tags


def already_tagged_ids(current_tags: dict[int, str]) -> set[int]:
    """Which rows already carry SOME `duplicate-of` tag.

    A row already proven a duplicate of something is left entirely alone. It is
    not re-judged and it is not given a second canonical — two ``duplicate-of``
    elements on one row is a state no consumer has a rule for, and this sweep
    must never be the thing that creates it.
    """
    return {
        event_id
        for event_id, tags in current_tags.items()
        if DUPLICATE_TAG_PREFIX in (tags or "")
    }


def fold_is_live() -> bool:
    """Is ``_build_game_markets`` still the consumer that makes this pay?

    The tag is inert on its own: it suppresses a card that ``fold_twin_events``
    already suppresses, and the ENTIRE user-visible effect of this sweep is that
    ``folded_event_ids`` serves the duplicate's markets on the canonical's page.
    If that call is ever removed, this sweep keeps writing tags and quietly
    delivers nothing — the exact shape of a repair that passes its own mechanism
    and ships no ship. The same guard the tennis and soccer sweeps carry, for
    the same reason.
    """
    import inspect

    try:
        from app.routes.events import folded_market_read_filters

        return "folded_event_ids" in inspect.getsource(folded_market_read_filters)
    except Exception:  # noqa: BLE001 — unreadable source is not proof it is live
        return False


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each duplicate's CURRENT `event_tags` before anything is appended.

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
                "eid": tag.duplicate_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.duplicate_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def write_tags(session, tags, *, progress_every: int = 0):
    """Append the duplicate tag to each row, ONE ROW PER TRANSACTION.

    Core SQL with a server-side ``||``, never an ORM assignment: ``event_tags``
    is JSONB and gotcha #4 is that a JSONB ORM assignment can silently fail to
    persist. The ``NOT @>`` makes it idempotent in the DATABASE rather than in
    this process's memory, so a re-run cannot double-append.

    Returns ``(written, failed_ids)``. Failures are RETAINED, not merely
    printed: on a worker whose stdout nobody reads, a printed FAILED line that
    never reaches the caller is indistinguishable from a clean run (gotcha #53).
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
                    {"tag_array": payload, "eid": tag.duplicate_id},
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {tag.duplicate_id} after 3 attempts: {exc}")
                    failed.append(tag.duplicate_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(tags)} processed, {written} tagged")
    return written, failed


async def tagged_now(session, duplicate_ids) -> set[int]:
    """Which of ``duplicate_ids`` carry a `duplicate-of` tag, read back from disk.

    The post-write proof, and it re-reads rather than trusting ``rowcount``:
    :func:`write_tags` is idempotent in the database, so a row that was already
    tagged returns 0 and a row whose write silently did not land returns 0 too.
    Only a read tells those apart (gotcha #53).
    """
    from sqlalchemy import text

    if not duplicate_ids:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT id FROM events "
                "WHERE id = ANY(:ids) "
                "  AND CAST(COALESCE(event_tags, '[]'::jsonb) AS text) LIKE :pat"
            ),
            {"ids": list(duplicate_ids), "pat": f"%{DUPLICATE_TAG_PREFIX}%"},
        )
    ).all()
    return {r.id for r in rows}


#: The operator's stop switch, and the reason the undo needs one at all.
#:
#: 🔴 **THE RESTORE SCRIPT ALONE IS NOT A ROLLBACK.** It removes the tags; this
#: beat runs `apply=True` at :27 every hour, and the planner selects on the
#: ABSENCE of the tag — so a rollback with the schedule still live is undone by
#: the next pass, within the hour, silently. Raised in #6786's review. An undo
#: that the system reverses is not an undo, so the rollback is a SEQUENCE:
#: stop, verify the stop, then restore.
#:
#: ANY NON-EMPTY VALUE DISABLES, deliberately. The obvious spelling — a truthy
#: set like {"1","true","yes"} — has a silent failure that matters more here
#: than tidiness: an operator halting a live repair who types `ture` or `TRUE `
#: would get a variable that is set, looks set, and does nothing, and the next
#: pass would re-tag every row they had just restored. Setting this at all is an
#: explicit act; nobody sets it by accident. Unset or empty is the normal state
#: and is what ships.
CONTAINER_TWIN_SWEEP_DISABLED_ENV = "CONTAINER_TWIN_SWEEP_DISABLED"


def sweep_is_disabled() -> bool:
    """Has an operator stood this sweep down? Pure apart from the environment.

    See :data:`CONTAINER_TWIN_SWEEP_DISABLED_ENV` for why any non-empty value
    counts. Whitespace-only is treated as unset, because `heroku config:set X=""`
    and a stray space are the same intent.
    """
    return bool(os.getenv(CONTAINER_TWIN_SWEEP_DISABLED_ENV, "").strip())


async def run_polymarket_container_twin_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
) -> dict:
    """One scheduled pass: read the window, plan, bank, tag. Returns the summary.

    ``apply`` defaults to TRUE, for the reason its two siblings do: this appends
    a reversible label with no deleter and banks the prior value first, which is
    exactly D51's shape. A dry-run schedule would measure the defect every hour
    and leave the page drawing no spread and no total.
    """
    from app.tasks.base import get_task_session

    summary: dict = {
        "task": "polymarket_container_twin_sweep",
        "issue": "#5821",
        "fold": "#2693",
        "apply": apply,
        "measured": True,
        "lookback_days": lookback,
        "lookahead_days": lookahead,
    }

    # THE STOP, BEFORE THE DATABASE IS TOUCHED AT ALL. A stood-down pass opens no
    # session, reads no window and banks nothing, so an operator mid-rollback is
    # not racing a reader.
    #
    # `skipped`, never `complete`: a sweep that has been switched off has proved
    # nothing about the population and must not vouch for the task's health. It
    # is in `_TERMINAL_NO_WORK`, so it classifies as an authoritative UNKNOWN —
    # not green, not red — which is exactly what "somebody turned this off" is.
    # Its own reason string, not the floor's or the fold's, because the receipt
    # is what the rollback procedure reads to confirm the stop took effect.
    if sweep_is_disabled():
        return {
            **summary,
            "measured": False,
            "terminal": "skipped",
            "tagged": 0,
            "disabled": True,
            "reason": (
                f"stood down: {CONTAINER_TWIN_SWEEP_DISABLED_ENV} is set. No "
                f"population was read and nothing was written. Unset it to "
                f"resume; while it is set this beat cannot re-tag rows that "
                f"scripts/restore_5821_container_twin_tags.py has removed"
            ),
        }

    async with get_task_session() as session:
        try:
            markets, rows, current_tags = await load_rows(
                session, lookback=lookback, lookahead=lookahead
            )
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        # The non-vacuity floor, BEFORE any judgement. A read that lost its
        # join, its source filter or its window returns few rows and no plan,
        # which is indistinguishable from a drained backlog from the outside —
        # and a drained backlog is this sweep's permanent steady state, so
        # without this the two zeros mean opposite things and read the same.
        if len(markets) < MIN_MARKETS_FLOOR:
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "markets_read": len(markets),
                "floor": MIN_MARKETS_FLOOR,
                "reason": (
                    f"population floor: read {len(markets)} Polymarket markets "
                    f"carrying venue_game_start in the window "
                    f"(-{lookback}d/+{lookahead}d), below the floor of "
                    f"{MIN_MARKETS_FLOOR}. This pass could not look, which is "
                    f"not the same as having nothing to do"
                ),
            }

        plan = plan_container_tags(markets, rows)
        tagged = already_tagged_ids(current_tags)
        todo = [t for t in plan.tags if t.duplicate_id not in tagged]
        folding = fold_is_live()

        summary.update(
            {
                "markets_read": len(markets),
                "rows_read": plan.rows_considered,
                "keys_examined": plan.keys_examined,
                # Beside the total and never folded into it: a join that stops
                # attaching markets takes THIS to zero while `keys_examined`
                # stays healthy, and only the pair says which half went dark.
                "split_keys_examined": plan.split_keys_examined,
                "pairs_found": len(plan.tags),
                "refusals": len(plan.refusals),
                "refusal_samples": plan.refusals[:10],
                "already_tagged": len(plan.tags) - len(todo),
                "to_tag": len(todo),
                # The consumer check, reported whether or not there is work: a
                # sweep whose fold has been removed writes tags that deliver
                # nothing, and that must be visible on a quiet day too.
                "fold_live": folding,
            }
        )

        # REFUSE BEFORE WRITING when the consumer is gone (CERT-3030). This was
        # previously reported in the summary and not acted on, which is the
        # weaker half of the same idea: a sweep whose fold has been removed
        # would go on appending tags that deliver nothing to a reader, and each
        # such pass would have banked a row and read healthy. The tag is inert
        # without `folded_event_ids`, so writing it is not a partial win.
        #
        # It is checked here rather than at the top so a quiet pass still
        # reports `fold_live` on a day with no work — the signal has to be
        # visible BEFORE the fold breaks, not only once there is a write to
        # refuse.
        if todo and not folding:
            return {
                **summary,
                "terminal": "failed",
                "tagged": 0,
                "reason": (
                    f"refusing to write {len(todo)} tag(s): `folded_event_ids` "
                    f"is no longer read by `folded_market_read_filters`, so the "
                    f"tag would suppress a card and deliver no markets to the "
                    f"canonical page. The consumer is the whole ship"
                ),
            }

        if not todo:
            # `complete`, NOT `no_work` — and the distinction is the reason
            # enrolment helps here at all. This backlog DRAINS: after the first
            # successful pass every family in the window is labelled and every
            # later pass plans zero, forever. `no_work` classifies as an
            # authoritative UNKNOWN, so the steady state would never read GREEN
            # and the task would be permanently not-green for being healthy —
            # the "ninety-six false REDs" the tennis sibling's comment warns
            # about. The floor above is what keeps this honest: we only reach
            # here having READ a healthy population.
            return {
                **summary,
                "terminal": "complete",
                "tagged": 0,
                "reason": (
                    "every split family in the window is already tagged — the "
                    "healthy end state for a drained backlog"
                ),
            }

        if not apply:
            # A dry run deliberately banks nothing, so it cannot vouch for the
            # task's health. `no_work` is the honest terminal (authoritative
            # unknown); the previous `planned` was not in the vocabulary at all
            # and classified as `unrecognised`.
            return {**summary, "terminal": "no_work", "tagged": 0, "planned": len(todo)}

        banked = await ensure_backup(session, todo, current_tags)
        written, failed = await write_tags(session, todo, progress_every=50)
        confirmed = await tagged_now(session, [t.duplicate_id for t in todo])

        # EVERY PLANNED TAG MUST BE CONFIRMED ON DISK (CERT-3030). `written` is
        # a sum of rowcounts and `confirmed` is a read-back, and only the second
        # survives a commit that did not stick. A shortfall in either direction
        # is `partial`: the run did some of what it planned, and saying
        # `complete` would let the receipt advance on a pass that half-worked.
        missing = sorted({t.duplicate_id for t in todo} - confirmed)
        if failed or missing:
            terminal = "partial"
        else:
            terminal = "complete"

        return {
            **summary,
            "terminal": terminal,
            "banked": banked,
            "planned": len(todo),
            "tagged": written,
            # Read back from disk, not `rowcount`. See `tagged_now`.
            "confirmed_on_disk": len(confirmed),
            "unconfirmed_count": len(missing),
            "unconfirmed": missing[:20],
            # `errors`, not `failed`: `_ERROR_COLLECTIONS` in `task_verdict` is
            # ("errors", "failed_chunks", "failed_phases"), so a key called
            # `failed` is invisible to `_has_damage`. The terminal above already
            # refuses `complete` on damage; naming it the contract's own name
            # means the contract ALSO downgrades a `complete` we got wrong,
            # rather than trusting this function to be the only guard.
            "errors": failed[:20],
            "failed_count": len(failed),
        }
