"""Exactly one rail owns every Polymarket market shape, and says so. Pure.

CAL-P065, closing #1912. The defect is not that a grader was wrong; it is that
two graders were each correct about their own half and nobody owned the seam.

``_backfill_polymarket_winners_from_api`` (the Gamma rail) drops every market
whose ``external_id`` starts with ``0x``, because Gamma's ``GET /markets/{id}``
takes a numeric id and answers ``422`` to a condition_id. That is true, and the
skip is right. What it wrote next is the bug::

    # They are the CLOB rail's cohort (clob_resolve, binding mapper spec)
    # — counted here, owned there.

**Owned there by whom.** ``clob_resolve_drain``'s scheduled invocation passes no
cohort, so ``_load_cohort`` selects ``_COHORT_DROPPED``, whose
``HAVING bool_or(fo.resolution_source = ANY('pass2_loser','all_losers'))`` over
a market with all-NULL sources evaluates to NULL — never TRUE. The receiving
rail could not select the handed-off population if it tried. 9,748 markets per
run were handed to a cohort predicate that excludes them by construction, and
both rails reported ``health: healthy`` while it happened.

So the handoff was a DISCARD wearing a delegation's clothes, and gotcha #53 is
why nothing noticed: "I gave these away" and "there were none" produced the same
counter, the same green field, and the same silence.

What this module provides
-------------------------
1. **A total ownership map.** :func:`owner_of` answers for every shape a
   Polymarket row can take. There is no default branch that means "somebody
   else" — a shape with no owner is :data:`SHAPE_UNRECOGNISED`, which is a
   REPORTED state, not a silent drop.
2. **Accounting, separated from work.** A rail OWNS a shape when it is the
   designated grader; it ACCOUNTS for that shape when its returned summary
   carries the backlog it is sitting on. :func:`orphaned_shapes` names any
   shape whose owner does neither. That function returning non-empty IS the
   ownership hole, and a test asserts it is empty.
3. **The terminal each rail owes.** :func:`gamma_terminal` and
   :func:`clob_terminal` turn a rail's own counters into the terminal that
   ``app/utils/task_verdict.py`` consumes, so a run that gave its work away or
   wrote nothing against a five-figure backlog reads NOT-GREEN. Neither rail
   emitted a terminal before this, which is why enrolling them in
   ``ENFORCED_TASKS`` alone would have changed nothing: a summary with no
   terminal classifies as the non-authoritative legacy unknown, and a
   non-authoritative unknown does not block success.

Deliberately NOT here: whether a rail should WRITE. Selection and accounting are
cheap and safe; the 25,264-market never-graded backfill is an attended apply
bound to a reviewed ``ApplyPlan``. This module makes the debt visible. It does
not license paying it.

Pure: no DB, no Redis, no network, no clock. Safe to import from tasks and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

#: ``external_id`` is a CLOB ``condition_id`` (``0x`` + hex). Gamma's
#: ``GET /markets/{id}`` answers 422 for these — measured against production
#: 2026-08-07 (CAL-P003) — so they are addressable ONLY on the CLOB endpoint.
SHAPE_CONDITION_ID = "condition_id"

#: The market carries ``market_metadata->>'polymarket_event_id'``, so the Gamma
#: rail can reach it via ``GET /events/{event_id}``, which returns settlement
#: prices for every nested sub-market at once.
SHAPE_GAMMA_EVENT = "gamma_event"

#: A bare Gamma market id (numeric, or a slug the Gamma endpoint accepts).
SHAPE_GAMMA_MARKET = "gamma_market"

#: No usable identifier at all. Has no owner ON PURPOSE — see
#: :func:`owner_of`. This is the one shape that may answer ``None``, and it is
#: counted and reported rather than skipped.
SHAPE_UNRECOGNISED = "unrecognised"

#: Every shape the classifier can produce. Iterated by the totality tests, so a
#: new shape that nobody assigned an owner to fails a test rather than falling
#: through a dict lookup at runtime.
SHAPES: tuple[str, ...] = (
    SHAPE_CONDITION_ID,
    SHAPE_GAMMA_EVENT,
    SHAPE_GAMMA_MARKET,
    SHAPE_UNRECOGNISED,
)

# ---------------------------------------------------------------------------
# Rails
# ---------------------------------------------------------------------------

#: ``app.tasks.clob_resolve_drain`` — task-metrics label ``clob_resolve_drain``.
RAIL_CLOB = "clob_resolve_drain"

#: ``app.tasks.backfill_polymarket_winners`` — task-metrics label
#: ``polymarket_winners``. Note the names differ; the label is what the health
#: surface and :data:`task_verdict.ENFORCED_TASKS` key on.
RAIL_GAMMA = "polymarket_winners"

RAILS: tuple[str, ...] = (RAIL_CLOB, RAIL_GAMMA)

#: The registry. EXACTLY ONE owner per shape — the invariant the whole module
#: exists to state. ``SHAPE_UNRECOGNISED`` is absent deliberately: a row we
#: cannot identify has no grader, and pretending otherwise is how a discard
#: becomes invisible.
OWNER_BY_SHAPE: Mapping[str, str] = {
    SHAPE_CONDITION_ID: RAIL_CLOB,
    SHAPE_GAMMA_EVENT: RAIL_GAMMA,
    SHAPE_GAMMA_MARKET: RAIL_GAMMA,
}

#: Shapes each rail ACCOUNTS for in its returned summary — i.e. reports a
#: backlog number for, so an operator can see what it is sitting on.
#:
#: This is not the same as "fetches every run", and conflating the two is what
#: made the hole invisible. The CLOB drain works a bounded page per run and
#: always will; what it owes is a truthful statement of the population behind
#: that page. Before CAL-P065 it reported neither, and
#: :func:`orphaned_shapes` returned ``('condition_id',)``.
ACCOUNTED_SHAPES: Mapping[str, frozenset[str]] = {
    RAIL_CLOB: frozenset({SHAPE_CONDITION_ID}),
    RAIL_GAMMA: frozenset({SHAPE_GAMMA_EVENT, SHAPE_GAMMA_MARKET}),
}


def market_shape(external_id: Any, poly_event_id: Any = None) -> str:
    """Classify one Polymarket row. Total — always returns a member of
    :data:`SHAPES`, never raises, never returns ``None``.

    ``poly_event_id`` is checked FIRST because it is what the Gamma rail
    actually routes on: a market with an event id is fetched by event even when
    its own ``external_id`` is a condition_id, and the event response carries
    the settlement prices for every nested sub-market. Reversing the order
    would hand event-linked markets to the CLOB rail and re-create the hole
    facing the other way.
    """
    if isinstance(poly_event_id, str) and poly_event_id.strip():
        return SHAPE_GAMMA_EVENT
    ext = external_id if isinstance(external_id, str) else ""
    ext = ext.strip()
    if not ext:
        return SHAPE_UNRECOGNISED
    if ext.lower().startswith("0x"):
        return SHAPE_CONDITION_ID
    return SHAPE_GAMMA_MARKET


def owner_of_shape(shape: str) -> str | None:
    """The one rail responsible for ``shape``, or ``None`` for an unrecognised
    row. ``None`` means "nobody can grade this", which is a finding."""
    return OWNER_BY_SHAPE.get(shape)


def owner_of(external_id: Any, poly_event_id: Any = None) -> str | None:
    return owner_of_shape(market_shape(external_id, poly_event_id))


def owns(rail: str, external_id: Any, poly_event_id: Any = None) -> bool:
    return owner_of(external_id, poly_event_id) == rail


def orphaned_shapes() -> tuple[str, ...]:
    """Shapes with a declared owner that the owner does not account for.

    Non-empty means a rail is being handed work it will never report on — the
    #1912 hole, as a computable property rather than an anecdote. On master
    before CAL-P065 this returned ``('condition_id',)``.
    """
    return tuple(
        shape
        for shape, rail in sorted(OWNER_BY_SHAPE.items())
        if shape not in ACCOUNTED_SHAPES.get(rail, frozenset())
    )


# ---------------------------------------------------------------------------
# The handoff, as a verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Handoff:
    """Work one rail declined and named an owner for.

    The ``to`` field is why this type exists. ``unsupported_lookup: 9748`` is a
    number; ``Handoff(to='clob_resolve_drain', count=9748)`` is an accusation
    that can be checked — and :func:`gamma_terminal` checks it, by refusing to
    call a run complete that gave its work away.
    """

    to: str | None
    shape: str
    count: int
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "shape": self.shape,
            "count": int(self.count),
            "reason": self.reason,
            # An owner-less handoff is not a handoff. Named in the payload so
            # it is legible on the health surface without re-deriving it.
            "orphaned": self.to is None,
        }


def handoff_payload(handoffs: Iterable[Handoff]) -> dict[str, Any]:
    """The handoff block a rail puts in its returned summary."""
    items = list(handoffs)
    return {
        "total": sum(int(h.count) for h in items),
        "orphaned": sum(int(h.count) for h in items if h.to is None),
        "by_owner": {
            rail: sum(int(h.count) for h in items if h.to == rail)
            for rail in sorted({h.to for h in items if h.to})
        },
        "items": [h.as_payload() for h in items],
    }


# --- terminals --------------------------------------------------------------
#
# Both functions return ``(terminal, reason)`` in the vocabulary
# ``app/utils/task_verdict.py`` already reads. They do not decide health; they
# state what the run proved, and the verdict contract does the rest.

_T_COMPLETE = "complete"
_T_PARTIAL = "partial"
_T_FAILED = "failed"


def gamma_terminal(
    *,
    markets_checked: int,
    handed_off: int,
    orphaned: int,
    errors: Iterable[Any] = (),
) -> tuple[str, str]:
    """What the Gamma rail's run proved.

    A run that handed work to another rail did not finish that work, whatever
    it did with the rest. That is ``partial`` by the verdict module's own
    definition — "real, visible progress that is not a finished run" — and it
    is the entire point: 252 checked against 9,748 handed off has been reading
    GREEN, and under this it cannot.

    An ORPHANED handoff is stronger than partial. Nobody can grade those rows,
    so the run is not merely unfinished; it has identified work with no owner,
    which is a defect in the registry and must be loud.
    """
    if any(True for _ in errors):
        return _T_PARTIAL, "complete_with:errors"
    if orphaned > 0:
        return _T_FAILED, f"handoff:orphaned={orphaned}"
    if handed_off > 0:
        return _T_PARTIAL, f"handoff:{handed_off}_to_another_rail"
    if markets_checked <= 0:
        # Distinguishing "nothing to do" from "did nothing" needs a second
        # signal (gotcha #53), and this rail has none. Do not claim complete.
        return _T_PARTIAL, "checked_zero"
    return _T_COMPLETE, "no_handoff"


def clob_terminal(
    *,
    examined: int,
    owned_backlog: int | None,
    written: int,
    cursor_reset: bool,
    errors: Iterable[Any] = (),
) -> tuple[str, str]:
    """What the CLOB rail's run proved.

    ``owned_backlog`` is the count of markets this rail OWNS and has not
    graded — both cohorts, not just the one this page worked. ``None`` means
    the census did not run, which is an ABSENT measurement and never a clean
    zero (gotcha #54): it cannot be read as "nothing left".

    ``complete`` therefore requires the backlog to be empty AND the walk to
    have wrapped. A resumable drain returning ``partial`` forever against a
    five-figure backlog is behaving as designed and reading honestly — which is
    the difference between this and the ten weeks of green that gotcha #53
    records.
    """
    if any(True for _ in errors):
        return _T_PARTIAL, "complete_with:errors"
    if owned_backlog is None:
        return _T_PARTIAL, "backlog_unmeasured"
    if owned_backlog > 0:
        return _T_PARTIAL, f"owned_backlog={owned_backlog}"
    if examined <= 0 and not cursor_reset:
        return _T_PARTIAL, "examined_zero"
    if written <= 0 and examined > 0 and not cursor_reset:
        # Everything examined landed in void / a non-writing tier. Honest, but
        # it is not proof the rail is working.
        return _T_PARTIAL, f"examined={examined}_wrote_0"
    return _T_COMPLETE, "backlog_drained"
