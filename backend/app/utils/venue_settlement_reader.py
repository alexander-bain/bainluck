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
from app.utils.event_completion import started_without_result
from app.utils.lifecycle import served_event_status
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


async def attach_venue_settlement(db, events: Sequence, briefs: list[dict], now) -> None:
    """Put the venue's own verdict on the LIST cards that deny having one.

    #6739 wrote this for the league rails; #7092 gave it a second caller and
    that is why it lives here rather than in either route. The rails
    (``/api/leagues/{sport_key}``) and the events list (``/api/events``, and
    the search results beside it) draw THE SAME CARD — notice 35, one card
    family everywhere — so a row that reads "Settled · Mikrut wins" on one of
    them and "No result reported" on another is the identical defect #6739
    exists to remove, merely relocated from detail-vs-list to list-vs-list.

    🔴 THE GATE INPUT IS RECOMPUTED HERE RATHER THAN READ OFF THE BRIEF,
    BECAUSE ONE OF THE TWO CALLERS DOES NOT HAVE IT. ``/api/events`` publishes
    ``started_without_result`` on every card (``events.py``'s
    ``_format_event``); the league rails' ``_format_game_brief`` does not carry
    it at all. A shared function may therefore not read it off the brief, and
    the caller that HAS it does not get to skip the computation — otherwise the
    two surfaces would answer the same row from two different derivations.

    They would in fact agree, and that was checked rather than assumed, because
    the two derivations are not the same expression: ``_format_event`` computes
    the flag from the RAW ``event.status`` while publishing the SERVED one, and
    :func:`~app.utils.event_completion.started_without_result` answers False for
    anything that is not literally ``"scheduled"``. So the question is whether a
    premature-``live`` row can be published ``status: "scheduled"`` beside
    ``started_without_result: false`` and be askable. It cannot, and the reason
    is structural rather than statistical:
    :func:`~app.utils.lifecycle.served_event_status` downgrades a ``live`` row
    only when ``live_start_satisfied`` is False, which is exactly the three
    cases ``start > now``, ``start is None``, and the comparison raising — and
    ``started_without_result`` answers False for all three (it needs
    ``start < now - UPCOMING_GRACE``, and returns False on a None or an
    uncomparable time). The divergence is unreachable, not merely rare;
    production 2026-09-19 agrees at 0 of 457 rows on the unfiltered list, which
    is a consistency check on that argument and not the argument itself.

    ``TestBothDerivationsOfTheGateInputAgree`` pins it, so a future change to
    either function that opens the gap is a red test rather than two surfaces
    quietly disagreeing about one row — which is the defect #6739 exists to
    remove.

    🔴 THE BRIEFS ARE MATCHED TO THEIR ROWS BY ID, NEVER BY POSITION. A
    formatter drops a row it cannot format (gotcha #42), so the two lists are
    the same length only on a page where nothing went wrong — and the page
    where something went wrong is the one where a positional zip would put
    Schoolkate's result on Mikrut's card. There is no correct wrong answer
    here: a card that names the loser is worse than a card that names nobody.

    Mutates the briefs in place and returns nothing: the keys are an ADDITION
    to the shared event card's contract (ruling 047 — extend the contract,
    never fork the card), under the names ``/api/events/{id}`` has served since
    #6381, so a second reader has nothing new to learn.
    """
    by_id: dict[int, object] = {}
    for event in events:
        event_id = getattr(event, "id", None)
        if event_id is not None:
            by_id[int(event_id)] = event

    started = {
        event_id: started_without_result(
            served_event_status(
                getattr(event, "status", None),
                getattr(event, "commence_time", None),
                now,
            ),
            getattr(event, "commence_time", None),
            now,
        )
        for event_id, event in by_id.items()
    }

    candidates = askable_briefs(briefs, started)
    if not candidates:
        # THE ORDINARY PAGE PAYS NOTHING. Every row with a score, and every
        # scheduled row still ahead of its own kickoff, is refused by the gate
        # before any query is issued — so a league mid-slate and a 457-row
        # unfiltered list alike issue zero extra statements, and only a page
        # actually carrying an ungraded-looking finished match issues one.
        #
        # This is what makes the read sized by the GATE rather than by the
        # page. Measured on production 2026-09-19: `/api/events?limit=500`
        # served 457 rows of which 31 were askable, and those 31 ids returned
        # 5 rows in 9.7 ms.
        return

    settlements = await venue_settlements_for_events(
        db,
        [
            by_id[int(brief["id"])]
            for brief in candidates
            if int(brief["id"]) in by_id
        ],
    )
    for brief in candidates:
        settlement = settlements.get(int(brief["id"]))
        if settlement is not None:
            brief.update(settlement)
