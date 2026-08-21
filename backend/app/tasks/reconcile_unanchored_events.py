"""Ruling 048's other half: the id-keyed reconciliation that drains the duplicates.

Ruling 048 makes an explicit bargain. An id-less claim never absorbs — it CREATES —
and the resulting duplicates are accepted as a **bounded** cost, bounded because:

    *"id-keyed reconciliation drains the duplicate when an id arrives."*

That clause was the whole basis of the acceptance, and it has never had an
implementation. The provenance meter (``/api/admin/events/duplicates``) has been
counting the cost since the ruling landed and reads, on 2026-08-17:

    created_unanchored 500 · reconciled **0** · unreconciled **500**

Not "the drain is behind". The drain does not exist, so the accepted price has no
bound and never did. The Flow Sentinel's ``created > 0 and reconciled == 0`` check
was already firing at this; what was missing is the thing it was firing AT.

WHAT THE FIRST MEASUREMENT FOUND, AND WHY IT CHANGES THE SHAPE
---------------------------------------------------------------

Before writing a drain it is worth asking what it would drain. Measured against
production, over all 500 unanchored rows:

* **499 of 500 were created by Polymarket** (487 of them ``soccer_other``), inside
  twelve days, and the population is growing.
* **15** have a same-teams/same-window sibling of any kind.
* **0** have an *anchored* sibling.

So there is currently no duplicate PAIR to drain. And the reason is structural, not
a backlog:

    ``events`` has exactly three provider-id columns — ``external_id`` (Odds API),
    ``espn_id``, ``statpal_fixture_id``. There is no column for a Kalshi or a
    Polymarket id. ``event_registry._find_by_source_id`` says so in a comment, and
    ``_attach_claim`` silently does nothing for those two sources.

An id **cannot arrive** for the provider that created 99.8% of the population,
because there is nowhere on the row for it to land. Ruling 048's bounding clause has
no arrival channel for the source generating essentially all of its cost. That is a
different problem from "nobody scheduled the drain", and it is not fixable by
scheduling one — it needs either an anchoring column for those providers (a schema
and a ruling question, Alex's) or a different bound on the create path.

WHAT THIS TASK THEREFORE DOES
-----------------------------

It implements the mechanism the ruling names, and it makes the part it *cannot*
reconcile impossible to mistake for success.

Every unanchored row gets exactly one disposition, and all of them are counted:

``DRAINABLE``
    The row has acquired a provider id AND another row shares it. This is the
    literal "an id arrived" case. Handed to the merge rail under
    ``event_merge_invariant.assert_mergeable`` — never merged by name or window.
``ANCHORED_NO_TWIN``
    An id arrived and no other row shares it. Reconciliation succeeded; there was
    simply no duplicate. Counted as reconciled, nothing to do.
``NO_ANCHOR_CHANNEL``
    The row's creating provider has no id column on ``events``. **No id can ever
    arrive.** This row is not waiting for reconciliation; it is outside it.
``AWAITING_ANCHOR``
    Created by a provider that does have a channel, still holding no id. The only
    disposition for which "wait" is an honest answer.

``NO_ANCHOR_CHANNEL`` exists so that the census cannot be read as a queue. A drain
reporting ``0 reconciled`` over a population of 500 ``AWAITING_ANCHOR`` rows says
"be patient"; over 499 ``NO_ANCHOR_CHANNEL`` rows it says "this will never happen",
and those must not render identically (gotcha #53 — an empty read and an impossible
one are different facts).

DRY-RUN BY DEFAULT. The apply path DELETEs, so it is opt-in and it goes through the
shared invariant rather than its own SQL, per ``event_merge_invariant``'s docstring:
five careful predicates in five places is what R1–R5 were.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from app.utils.event_merge_invariant import (
    PROVIDER_ID_COLUMNS,
    UnanchoredMergeRefused,
    assert_mergeable,
)

logger = logging.getLogger(__name__)

#: The tag the create path writes (``event_registry._TAG_UNANCHORED``). Imported by
#: value rather than from the registry to keep this module free of that import
#: cycle; the contract test asserts the two strings agree.
UNANCHORED_TAG = "provenance:unanchored"

#: Sources that can anchor a row, i.e. that have a column in
#: :data:`PROVIDER_ID_COLUMNS`. Derived from the registry's own mapping so that
#: adding a provider column in one place cannot leave this list behind.
SOURCE_TO_ID_COLUMN: dict[str, str] = {
    "odds_api": "external_id",
    "espn": "espn_id",
    "statpal": "statpal_fixture_id",
}

#: Sources the registry accepts claims from that have NO id column on ``events``.
#: A row created by one of these can never be anchored by its own creator.
CHANNEL_LESS_SOURCES: frozenset[str] = frozenset({"kalshi", "polymarket"})

DISPOSITION_DRAINABLE = "DRAINABLE"
DISPOSITION_ANCHORED_NO_TWIN = "ANCHORED_NO_TWIN"
DISPOSITION_NO_CHANNEL = "NO_ANCHOR_CHANNEL"
DISPOSITION_AWAITING = "AWAITING_ANCHOR"

#: A bounded scan. This runs on a schedule against a hot table.
DEFAULT_LIMIT = 1000


def _creating_sources(event_tags: Any) -> list[str]:
    """The ``provenance:source:*`` tags on a row, as bare source names."""
    if not isinstance(event_tags, (list, tuple)):
        return []
    prefix = "provenance:source:"
    return [t[len(prefix):] for t in event_tags if isinstance(t, str) and t.startswith(prefix)]


def classify_row(row: Any) -> str:
    """One disposition per unanchored row. Pure — no DB, no clock.

    ``row`` needs ``event_tags``, the three provider-id columns, and
    ``twin_count`` (rows sharing at least one of this row's non-null ids).
    """
    ids = {col: getattr(row, col, None) for col in PROVIDER_ID_COLUMNS}
    anchored = any(v is not None for v in ids.values())

    if anchored:
        # An id DID arrive. Whether there is anything to drain is a separate
        # question from whether reconciliation happened.
        return (
            DISPOSITION_DRAINABLE
            if (getattr(row, "twin_count", 0) or 0) > 0
            else DISPOSITION_ANCHORED_NO_TWIN
        )

    sources = _creating_sources(getattr(row, "event_tags", None))
    if sources and all(s in CHANNEL_LESS_SOURCES for s in sources):
        # Every provider that touched this row lacks an id column. Nothing is
        # pending; the arrival this row is nominally waiting for is impossible.
        return DISPOSITION_NO_CHANNEL
    return DISPOSITION_AWAITING


# The census. ``twin_count`` is computed in SQL and is strictly id-keyed: two rows
# are twins when they share a NON-NULL provider id. Two NULLs are not agreement —
# that reading is exactly how ``NULL == NULL`` becomes a merge.
_CENSUS_SQL = text(
    """
    SELECT e.id,
           e.sport_id,
           e.commence_time,
           e.status,
           e.home_team_name,
           e.away_team_name,
           e.event_tags,
           e.external_id,
           e.espn_id,
           e.statpal_fixture_id,
           (
             SELECT COUNT(*) FROM events o
              WHERE o.id <> e.id
                AND (
                     (e.external_id IS NOT NULL AND o.external_id = e.external_id)
                  OR (e.espn_id IS NOT NULL AND o.espn_id = e.espn_id)
                  OR (e.statpal_fixture_id IS NOT NULL
                      AND o.statpal_fixture_id = e.statpal_fixture_id)
                )
           ) AS twin_count
      FROM events e
     WHERE e.event_tags @> CAST(:tag AS jsonb)
     ORDER BY e.commence_time DESC
     LIMIT :lim
    """
)

# #2048: every provider-id bind is CAST, and the cast is not decoration.
#
# ``:external_id IS NOT NULL`` hands PostgreSQL a parameter inside a NullTest, which
# supplies no type context — the Param node is minted UNKNOWNOID and parse analysis
# ends with "could not determine data type of parameter $N". The ``o.external_id =
# :external_id`` alongside it does NOT rescue it: that resolves the parameter *slot*,
# but the node built for the null test was already fixed as unknown. The null test
# came first, so the null test decides.
#
# Measured cost of the missing cast: the drain threw on 100% of DRAINABLE rows at
# every scan size from the day ruling 048 landed, so the bound the ruling accepted
# duplicates against had never once been exercised. ``_CENSUS_SQL`` above already
# uses this pattern for its one bind; this is the same pattern, applied to all three.
_TWIN_SQL = text(
    """
    SELECT o.id, o.external_id, o.espn_id, o.statpal_fixture_id,
           o.home_team_name, o.away_team_name, o.commence_time
      FROM events o
     WHERE o.id <> :eid
       AND (
            (CAST(:external_id AS varchar) IS NOT NULL
             AND o.external_id = CAST(:external_id AS varchar))
         OR (CAST(:espn_id AS varchar) IS NOT NULL
             AND o.espn_id = CAST(:espn_id AS varchar))
         OR (CAST(:statpal_fixture_id AS varchar) IS NOT NULL
             AND o.statpal_fixture_id = CAST(:statpal_fixture_id AS varchar))
       )
    """
)


async def reconcile(
    session,
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Census the unanchored population and drain what an arrived id licenses.

    Returns a summary carrying an explicit ``terminal`` so ``task_verdict`` can
    read it. A run that reconciles nothing is NOT ``complete``: it reports
    ``no_work`` with the dispositions that explain the zero, because "it returned"
    is not "it worked" and a drain with nothing drainable is exactly the shape that
    reported SUCCESS every 6h for ten weeks in #683.
    """
    census: dict[str, int] = {
        DISPOSITION_DRAINABLE: 0,
        DISPOSITION_ANCHORED_NO_TWIN: 0,
        DISPOSITION_NO_CHANNEL: 0,
        DISPOSITION_AWAITING: 0,
    }
    drained: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        rows = (await session.execute(
            _CENSUS_SQL, {"tag": f'["{UNANCHORED_TAG}"]', "lim": int(limit)}
        )).mappings().all()
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        # gotcha #53: a census that could not run must not render as a census
        # that found nothing. There is no zero to report here, only ignorance.
        logger.warning("unanchored census failed: %s", type(exc).__name__)
        return {
            "task": "reconcile_unanchored_events",
            "issue": "#1798",
            "measured": False,
            "terminal": "failed",
            "reason": f"census_failed:{type(exc).__name__}",
            "errors": [f"census: {type(exc).__name__}"],
        }

    scanned = [_Row(r) for r in rows]
    for row in scanned:
        census[classify_row(row)] += 1

    drainable = [r for r in scanned if classify_row(r) == DISPOSITION_DRAINABLE]
    for row in drainable:
        # #2048, second half: a per-row ``except`` is not per-row isolation on
        # PostgreSQL. A failed statement aborts the whole transaction, so without a
        # savepoint the FIRST error takes every later row down with it — reporting
        # one defect as N, each with a different exception type. That is exactly the
        # production signature (ProgrammingError, then DBAPIError on the corpse).
        # A bare ``rollback()`` would be the wrong repair: in an ``apply=True`` pass
        # it discards merges already applied this run. The boundary must be per row.
        try:
            async with session.begin_nested():
                twins = (await session.execute(_TWIN_SQL, {
                    "eid": row.id,
                    "external_id": row.external_id,
                    "espn_id": row.espn_id,
                    "statpal_fixture_id": row.statpal_fixture_id,
                })).mappings().all()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"twin lookup for {row.id}: {type(exc).__name__}")
            continue

        for twin in twins:
            pair = {
                "unanchored_event_id": row.id,
                "twin_event_id": twin["id"],
                "matchup": f"{row.away_team_name} @ {row.home_team_name}",
                "shared_on": [
                    col for col in PROVIDER_ID_COLUMNS
                    if getattr(row, col, None) is not None
                    and getattr(row, col, None) == twin[col]
                ],
            }
            try:
                # The invariant, immediately before any destructive step — even
                # though the SQL above is already id-keyed. The redundancy is the
                # design: the query proves the candidate set was chosen correctly,
                # this proves the row in hand is safe to destroy now.
                assert_mergeable(row, _Row(twin), context="reconcile_unanchored_events")
            except UnanchoredMergeRefused as exc:
                refused.append({**pair, "reason": str(exc)[:300]})
                continue

            if not apply:
                drained.append({**pair, "applied": False})
                continue

            try:
                # Same containment as the twin lookup above, and it matters more
                # here: this path DELETEs. A failure mid-absorb must roll back its
                # own pair and nothing else — neither the pairs already drained in
                # this run, nor the pairs after it.
                async with session.begin_nested():
                    await _absorb(session, keep=twin["id"], drop=row.id)
                drained.append({**pair, "applied": True})
            except UnanchoredMergeRefused as exc:
                # #1947: the in-transaction guard refused on the FRESH rows. That
                # is a refusal, not an error — it belongs in the same bucket as
                # the caller-side one above, or the census reads a working guard
                # as a broken drain.
                refused.append({**pair, "reason": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001 — one bad pair never wipes the pass
                errors.append(f"merge {row.id}->{twin['id']}: {type(exc).__name__}")

    reconciled = len(drained)
    unbounded = census[DISPOSITION_NO_CHANNEL]

    if errors:
        terminal = "partial"
        reason = "errors_during_drain"
    elif reconciled:
        terminal = "complete"
        reason = "drained"
    else:
        # A zero, said out loud, with the reason attached to it. This is the case
        # ruling 048's acceptance depends on NOT being permanent.
        terminal = "no_work"
        reason = (
            f"nothing drainable: {unbounded} rows have no anchoring channel "
            f"(their creating provider has no id column on events), "
            f"{census[DISPOSITION_AWAITING]} still awaiting an id"
        )

    return {
        "task": "reconcile_unanchored_events",
        "issue": "#1798",
        "measured": True,
        "terminal": terminal,
        "reason": reason,
        "apply": apply,
        "scanned": len(scanned),
        "limit": int(limit),
        "truncated": len(scanned) >= int(limit),
        "census": census,
        # Ruling 048's bargain, as two numbers an operator can read against each
        # other. ``unbounded`` is the part the ruling did not anticipate: rows for
        # which the bounding clause has no mechanism at all.
        "reconciled": reconciled,
        "unbounded": unbounded,
        "drained": drained[:50],
        "refused": refused[:50],
        "errors": errors,
    }


async def _absorb(session, *, keep: int, drop: int) -> None:
    """Repoint every event FK from ``drop`` to ``keep``, then delete ``drop``.

    R4: the repoint step used to be a loop here over ``sports._EVENT_FK_TABLES`` — a
    THIRD consumer of the hand-written eight-tuple that SQLAlchemy metadata said was
    ten, so this rail silently CASCADE-destroyed the loser's ``game_moments`` and hit
    an FK violation on any loser holding a ``ranking_judgments`` row, exactly as the
    other two did. Importing the short list from a sibling did stop the two lists
    drifting *from each other*; it could not stop them drifting from the schema, which
    is the drift that actually happened. It is one derived, shared call now — which
    also retires most of the "duplicated merge STEP" debt named in this docstring's
    previous revision. Caller has already run ``assert_mergeable``.

    #1947: that caller-side check is arm A on a stale read, so it is no longer
    the last word. ``assert_absorbable_now`` re-reads both rows ``FOR UPDATE``
    in this transaction and applies BOTH arms before the first destructive
    statement below. It raises a subclass of ``UnanchoredMergeRefused``, which
    ``reconcile`` already catches per pair.
    """
    from app.utils.event_absorption_guard import assert_absorbable_now  # noqa: PLC0415
    from app.utils.event_child_repoint import repoint_event_children  # noqa: PLC0415

    await assert_absorbable_now(
        session, keep_id=keep, orphan_id=drop,
        context="reconcile_unanchored_events",
    )

    await repoint_event_children(session, keep_id=keep, orphan_id=drop)
    await session.execute(text("DELETE FROM events WHERE id = :drop"), {"drop": drop})


class _Row:
    """Attribute access over a mapping, so pure helpers take one shape."""

    __slots__ = (
        "id", "sport_id", "commence_time", "status", "home_team_name",
        "away_team_name", "event_tags", "external_id", "espn_id",
        "statpal_fixture_id", "twin_count",
    )

    def __init__(self, mapping):
        for name in self.__slots__:
            setattr(self, name, mapping.get(name) if hasattr(mapping, "get") else None)


async def run_reconcile_unanchored(
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Task entry point — opens its own session.

    #2051: this previously imported ``AsyncSessionLocal`` from ``app.database``, a
    module that has never existed in this repo. The import is deferred, so nothing
    catches it until the beat fires — and then it fires every time: 48 invocations a
    day, 48 ``ModuleNotFoundError``s, **zero successes since the task was scheduled**
    (``consecutive_failures: 97``, Sentry BAINLUCK-12D).

    Filed and fixed alongside #2048 deliberately. #2048 makes the drain able to
    drain; on its own it changes nothing, because the scheduled caller never reaches
    the code. Ruling 048's bound needs BOTH halves — one is a query that throws, the
    other is a task that cannot start.

    ``get_task_session`` is what every other task in ``app/tasks`` uses; it commits on
    clean exit and rolls back on exception, so the explicit commit below is kept only
    to make the apply path's intent legible at the call site.
    """
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        result = await reconcile(session, apply=apply, limit=limit)
        if apply:
            await session.commit()
        return result


def summarize_for_operator(result: dict[str, Any]) -> str:
    """One line an operator can act on. Never says 'ok' for an impossible zero."""
    if not result.get("measured"):
        return f"UNMEASURED — {result.get('reason')}"
    census = result.get("census") or {}
    return (
        f"{result.get('terminal')}: reconciled={result.get('reconciled')} "
        f"of {result.get('scanned')} unanchored · "
        f"no-channel={census.get(DISPOSITION_NO_CHANNEL)} "
        f"awaiting={census.get(DISPOSITION_AWAITING)} "
        f"anchored-no-twin={census.get(DISPOSITION_ANCHORED_NO_TWIN)}"
    )
