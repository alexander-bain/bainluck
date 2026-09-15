"""Does the venue's own grade already answer a page that says "No result reported"?

#6381, the producer half of a notice-46 pair (consumer: ux, hero sentence +
refresh countdown). Nothing here writes, infers a winner, or touches
``Event.status``. It answers one question about a row we ALREADY hold and lets
the surface decide the sentence.

THE DEFECT
----------

Measured on production 2026-09-15: ``/events/15310639`` (Liverpool FC v Fulham
FC, a tier-1 primetime fixture) served ``status: scheduled``, both scores
``null``, a ticking refresh countdown and the hero chip **"No result reported"**
— while one screen below, on the same payload, its own markets read::

    Liverpool FC vs Fulham FC: Correct Score        Draw 0-0        Won
    Liverpool FC vs Fulham FC: First Team to Score  No Goal         Won

graded ``is_winner = true, resolution_source = 'api_settlement'`` on
2026-09-12. **The page denies having a result while drawing the moment the
result arrived.** 426 ``scheduled`` rows were in that state, and ≥411 of them
have no completed counterpart anywhere in the database — the venue grade we
already hold is the only result those rows will ever have.

WHY THE FIX IS NOT IN ``started_without_result``
------------------------------------------------

The obvious change — teach that predicate to consult the grades — is the wrong
one, and both of its docstrings say so at length
(:func:`app.utils.event_completion.started_without_result`):

    🔴 IT IS A RAIL QUESTION, NOT AN OUTCOME ONE … this asks whether the row's
    own clock ran out, not whether anybody played, scored or watched.

It is the #3211 predicate that rescued 171 US Open matches from being on
NEITHER league rail. A row it stops claiming falls out of the recent rail and
back into the both-rails hole, so narrowing it would un-rescue them.

The gap is one layer up. The predicate is rail membership; the sentence it
renders — "No result reported" — is an OUTCOME claim, and nothing on that path
ever asked whether we hold a venue grade. ``event_completion.py`` names the
collision without resolving it ("To a reader those are the same sentence").
This module is the missing question, asked additively beside that predicate
rather than inside it.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.utils.event_completion import EVENT_SUSPENDED

#: The only ``futures_outcomes.resolution_source`` this module will read a
#: result out of: the venue stated the settlement itself.
#:
#: Narrow ON PURPOSE, and widening it is a measurement, not a preference.
#: ``leaderboard``, ``game_score`` and the inference tiers are all derived from
#: something we computed; ``api_settlement`` is the one rung where the answer
#: came from the house that took the bets. The whole warrant for publishing
#: over a page that currently says "no result" is that this source is stronger
#: than the silence it replaces.
VENUE_SETTLEMENT_SOURCE = "api_settlement"

#: Market names — normalised, per colon-delimited segment — whose graded
#: outcome names the FULL-CONTEST score.
#:
#: Both are measured vocabulary, not guesses (production 2026-09-15, the 426-row
#: population): ``correct score`` on 11 events (soccer, ``Draw 0-0`` /
#: ``Sevilla FC wins 1-0``) and ``exact match score`` on 45 (tennis,
#: ``Aryna Sabalenka wins 2-0``). 56 events of 426; the other 370 are graded on
#: props alone and get :data:`None` here, which acceptance 4 of #6381 accepts
#: ("showing *settled* without inventing a score is sufficient").
FULL_SCOPE_SCORE_MARKETS = frozenset({"correct score", "exact match score"})


def _normalise_segment(segment: str) -> str:
    """Lowercase, collapse internal whitespace, strip. Nothing else."""
    return " ".join(segment.lower().split())


def is_full_scope_score_market(market_name: Optional[str]) -> bool:
    """Does this market's graded outcome name the score of the WHOLE contest?

    🔴 SEGMENT-EXACT, NOT A SUBSTRING, AND THE TWO TRAPS ARE BOTH LIVE ON THE
    SPECIMEN EVENTS THEMSELVES. ``/api/events/15310639`` carries all three of::

        Liverpool FC vs Fulham FC: Correct Score            ✅ Draw 0-0
        Liverpool FC vs Fulham FC: 1st Half Correct Score   ❌ Draw 1H 0-0
        Liverpool FC vs Fulham FC: First Team to Score      ❌ No Goal

    A substring test on "correct score" reads the half-time score as the
    full-time score — the exact class ``backfill_winners`` records at its
    ``1st Half Correct Score`` note — and a substring test on "score" adopts
    "First Team to Score", which is not a score at all. Ten and eight events in
    the measured population carry those two respectively, so both are
    populations rather than hypotheticals.

    Every colon-delimited segment is tested rather than only the last, so the
    answer does not depend on whether the venue writes
    ``Liverpool FC vs Fulham FC: Correct Score`` or ``Correct Score: Liverpool
    FC vs Fulham FC``. That widening is free precisely BECAUSE the membership
    test is exact: a segment either is the market name or it is not.
    """
    if not market_name:
        return False
    return any(
        _normalise_segment(segment) in FULL_SCOPE_SCORE_MARKETS
        for segment in market_name.split(":")
    )


def choose_settled_score(graded_outcome_names: Iterable[Optional[str]]) -> Optional[str]:
    """The one score the venue named, or ``None`` if it did not name exactly one.

    ``None`` on disagreement, deliberately and in both directions:

    * **Nothing graded** — 370 of the 426 measured events. The caller still
      reports the event settled; it just has no score to show.
    * **Two different names** — zero specimens today (measured: 56 events, 56
      graded rows, 0 disagreements), which is exactly why the refusal is
      written now rather than after one appears. A duplicate event pair or a
      mutually-exclusive market with two winners would put two scores on one
      row, and picking one of them by sort order is how a deterministic
      tiebreak becomes a confident wrong answer.

    Blank and whitespace-only names are dropped rather than served: a
    zero-length score is not a score, and it would read to the consumer as a
    present value.
    """
    distinct = {
        name.strip() for name in graded_outcome_names if name and name.strip()
    }
    if len(distinct) != 1:
        return None
    return next(iter(distinct))


def venue_settlement_is_askable(
    response: dict,
    *,
    live_claim_is_unbacked: bool,
) -> bool:
    """Will this payload render the no-result sentence? Then ask; otherwise do not.

    THE SCOPE IS THE HARM, NOT THE ISSUE'S OWN SAMPLE. #6381 measured 426
    ``scheduled`` rows, but "No result reported" is
    ``frontend/lib/eventState.hasNoReportedResult``, which is
    ``isSuspendedStatus(status) || startedWithoutResult(...)`` — and the detail
    page adds a third arm through ``hasNoReportedResultForShare``, a ``live``
    row whose price is pinned (#5077). Measured on production 2026-09-15, rows
    holding a positive venue grade with no result of their own:

        ======================  =======
        suspended                   889
        scheduled (this issue)      426
        live                          8
        ======================  =======

    Scoping to the issue's own sample would have shipped the fix to a third of
    its own class and left the larger half — ``suspended`` — printing the same
    sentence over the same grades. A guard that pins one component while its
    siblings keep the bug is the standing failure this avoids.

    ``closed`` is NOT in scope and that is a decision, not an oversight. 1,370
    scoreless ``closed`` rows hold venue grades, but ``closed`` is a finished
    status on every surface — the page calls it over and prints a Final, so it
    does not make the claim this key exists to refute. That population is its
    own defect (a Final with no score) and belongs to its own issue.

    THE FIRST TEST IS THAT WE HOLD NO RESULT OF OUR OWN — A SCORE. A row with
    one has a better answer than the venue's grade already, and publishing a
    second invites a page to choose between them. ``retired`` statuses never
    reach here: the route 410s them earlier.

    🔴 ``completed_at`` IS DELIBERATELY NOT A GATE, AND IT WAS ONE FOR AN HOUR.
    It looks like the same test as the score and it is not: it records when we
    NOTICED, shows a reader nothing, and none of the three arms above consults
    it — ``hasNoReportedResult`` is keyed on status and the clock alone. So the
    only rows it could ever have refused are stuck-status rows that acquired a
    timestamp without a score, and those still print "No result reported",
    which is precisely the sentence this key exists to contradict. It survived
    a mutation sweep because it is inert (measured 2026-09-15: 0 of the 1,323
    in-scope rows carry one), and an inert guard that can only ever narrow is
    how a ship quietly loses a population. Do not re-add it.

    🔴 IT READS THE RESPONSE DICT, NOT THE ROW, AND THAT IS THE POINT. Every
    input is a value the page is ABOUT TO BE SERVED — ``status`` after
    :func:`served_event_status` has downgraded a premature ``live``,
    ``started_without_result`` exactly as published — so this key cannot
    disagree with the keys beside it about what the page is about to say. That
    is the #6057 one-clock rule applied to state rather than to time, and
    taking the dict rather than four unpacked arguments is what stops a caller
    and its guard test from mirroring the unpacking differently.
    """
    if response.get("home_score") is not None or response.get("away_score") is not None:
        return False
    if response.get("started_without_result"):
        return True
    status = (response.get("status") or "").strip().lower()
    if status == EVENT_SUSPENDED:
        return True
    return status == "live" and live_claim_is_unbacked
