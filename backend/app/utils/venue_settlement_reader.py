"""The venue's grade for a RAIL of events at once — #6739's second half.

WHY THIS MODULE EXISTS, AND WHY IT IS NOT THE DETAIL ROUTE'S QUERY MOVED
------------------------------------------------------------------------

``venue_settlement.py`` is the policy and imports no database. ``events.py``
holds the one-event read behind ``/api/events/{id}``. The league rails need the
same ANSWER for a rail of rows, and there were two ways to get it: move the
detail route's query here and have it ask for a list of one, or share what the
two reads genuinely have in common and let each keep its own SELECT.

The first was built first and the test suite refused it: seven existing guards
across ``test_venue_settled_winner_6739.py`` and ``test_venue_settled_payload_6381.py``
mock the read at its row shape, and a batch read has to carry a grouping key a
single read does not. Needing to rewrite seven green guards is evidence about
the boundary, not a chore — the QUERIES are legitimately different questions.
What may never differ is the answer, so the two things that ARE shared are
shared outright:

* :func:`~app.utils.venue_settlement.settlement_from_graded_rows` — the ORDER
  (score first, winner second), which is the actual policy.
* :func:`venue_grade_filters` — the positive-grades-only WHERE, which is the
  actual safety rule.

Neither exists twice. Only the column list differs, which is the one thing that
should.

THE DEFECT THE BATCH FORM WAS BUILT FOR
---------------------------------------

Measured on production 2026-09-18 23:5xZ through the routes themselves — each
league payload's own ``unreported_games`` rail against each of those rows' own
detail payload:

    ==========================  ==========  =====================
    league                      rail rows   detail holds a winner
    ==========================  ==========  =====================
    ``tennis_atp``                       6                      6
    ``tennis_wta``                       6                      5
    ``boxing_boxing``                    6                      6
    ``soccer_other``                     6                      0
    ``mma_mixed_martial_arts``           6                      0
    ``baseball_npb``                     6                      0
    ``icehockey_liiga``                  6                      0
    **total**                       **42**                 **17**
    ==========================  ==========  =====================

Every one of those 17 cards reads **"No result reported · Sep 18"** on
``/sports/<league>`` while the match's own page, one tap away, reads
**"Settled · Schoolkate wins"**. The list route never asked the question the
detail route already answers. Same row, same second, two answers — and the one
the reader meets first is the one that denies having a result.

The four leagues at 0 are the honest half of that table: the sentence appears
where the venue graded and nowhere else.

WHAT THIS MODULE DOES NOT DO
----------------------------

It does not write, does not touch ``Event.status``, and does not decide what a
card says. It reports the side the venue graded on the market the shared
recognizer calls the moneyline, or it reports nothing. Every refusal that stops
it inferring a winner from a price, a closed book, a set or "the other one must
have lost" lives in :mod:`app.utils.venue_settlement` and is inherited whole.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from sqlalchemy import select

from app.models.models import FuturesMarket, FuturesOutcome
from app.utils.venue_settlement import (
    VENUE_SETTLEMENT_SOURCE,
    settlement_from_graded_rows,
)

logger = logging.getLogger(__name__)


def venue_grade_filters():
    """The WHERE that makes a graded leg admissible, for every reader of it.

    🔴 POSITIVE GRADES ONLY — ``is_winner IS TRUE``, never a count of graded
    legs and never a loss. A graded loss decides the other side only when some
    leg of that market WON: on a voided market every leg reads as a loss, and a
    reader handed "the other one must have won" gets a fabricated 100%. This is
    also what keeps the #1868 / #3617 class out — those are mass
    ``is_winner=FALSE`` grades stamped on games nobody played, and a filter that
    only ever reads ``TRUE`` cannot see them.

    ``is_(True)`` and not ``== True``: the column is nullable, and NULL means
    "nobody graded this", which is a third answer rather than a false one.

    A tuple rather than prose in two files. The rule is two lines long, which is
    exactly the size of rule that gets retyped slightly differently and then
    disagrees with itself for a year.
    """
    return (
        FuturesOutcome.is_winner.is_(True),
        FuturesOutcome.resolution_source == VENUE_SETTLEMENT_SOURCE,
    )


async def venue_settlements_for_events(db, events: Sequence) -> dict[int, dict]:
    """``{event_id: {"venue_settled": …, "venue_settled_result": …}}``.

    ``events`` is any sequence of rows carrying ``id``, ``home_team_name`` and
    ``away_team_name`` — the team names because
    :func:`~app.utils.venue_settlement.choose_settled_winner` reports OUR
    spelling of the side, not the venue's.

    🔴 AN EMPTY DICT IS A REFUSAL, NOT "NOBODY IS GRADED". On a failed read
    every caller leaves its rows exactly as it found them: a card that said "No
    result reported" before keeps saying it, rather than being handed a
    confident ``venue_settled: False`` this module did not establish. That is
    the same refusal ``events.py`` makes by returning ``None``, and it is why a
    miss is a MISSING KEY at every layer above rather than a present ``False``.

    THE ``IN`` LIST IS BOUNDED BY THE CALLER, AND THAT IS CHECKED RATHER THAN
    ASSUMED. The league rails are capped at ``UPCOMING_GAMES_LIMIT``,
    ``RESULTS_LIMIT`` and ``UNREPORTED_LIMIT``, and the gate above this call
    admits only rows carrying no score — so the set is a few dozen ids at worst.
    No ``LIMIT`` on the rows for the same reason the detail read has none:
    truncating would drop the one market whose name carries the score, and the
    per-event count is measured (max 84, p99 20, mean 3.2 across the 1,344 rows
    that can reach the detail form).
    """
    by_id: dict[int, object] = {}
    for event in events:
        event_id = getattr(event, "id", None)
        if event_id is not None:
            by_id[int(event_id)] = event
    if not by_id:
        return {}

    try:
        rows = (
            await db.execute(
                select(
                    FuturesMarket.event_id,
                    FuturesMarket.name,
                    FuturesMarket.external_id,
                    FuturesOutcome.name,
                )
                .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
                .where(
                    FuturesMarket.event_id.in_(list(by_id)),
                    *venue_grade_filters(),
                )
            )
        ).all()
    except Exception:
        # A refusal, not a default — see the docstring. Logged, because a rail
        # that silently stops carrying the sentence is indistinguishable from a
        # slate nobody graded.
        logger.exception(
            "venue settlement read failed for %d event(s); the rails keep "
            "whatever their cards said before",
            len(by_id),
        )
        return {}

    graded_by_event: dict[int, list[tuple]] = {}
    for event_id, market_name, market_external_id, outcome_name in rows:
        graded_by_event.setdefault(int(event_id), []).append(
            (market_name, market_external_id, outcome_name)
        )

    return {
        event_id: settlement_from_graded_rows(
            graded_by_event.get(event_id, []),
            getattr(event, "home_team_name", None),
            getattr(event, "away_team_name", None),
        )
        for event_id, event in by_id.items()
    }


def askable_briefs(
    briefs: Iterable[dict], started_without_result_by_id: dict
) -> list[dict]:
    """The rows on a LIST payload that are about to print "No result reported".

    Kept here beside the reader so a rail cannot ask the venue a question the
    detail page would refuse to ask. The gate itself is
    :func:`~app.utils.venue_settlement.venue_settlement_is_askable`, unchanged,
    reading the same dict of values-about-to-be-served; this supplies only the
    one input a list brief does not carry.

    🔴 ``live_claim_is_unbacked`` IS ALWAYS ``False`` HERE, AND THAT IS A
    NARROWER SCOPE STATED RATHER THAN A RULE QUIETLY WIDENED. The detail
    route's third arm — a ``live`` row whose price is pinned (#5077) — is
    computed from a flatness read the list payload does not perform. A rail row
    in that state keeps today's card. It does not get the same answer from a
    weaker input.
    """
    from app.utils.venue_settlement import venue_settlement_is_askable

    out = []
    for brief in briefs:
        brief_id = brief.get("id")
        if brief_id is None:
            continue
        gate = dict(brief)
        gate["started_without_result"] = bool(
            started_without_result_by_id.get(int(brief_id))
        )
        if venue_settlement_is_askable(gate, live_claim_is_unbacked=False):
            out.append(brief)
    return out
