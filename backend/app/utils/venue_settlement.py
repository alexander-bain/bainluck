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

import re
from typing import Iterable, Optional, Sequence

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
#: props alone and get :data:`None` here. #6381's acceptance 4 then accepted
#: that as "settled without inventing a score"; since #7702 it is not — a
#: :data:`None` from BOTH namers publishes no settlement at all. Most of the
#: 370 are unaffected because :func:`choose_settled_winner` answers them.
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

    * **Nothing graded** — 370 of the 426 measured events. The caller falls
      through to :func:`choose_settled_winner`, which answers most of them;
      where it too declines, #7702 means the caller reports no settlement
      rather than a settlement with nothing in it.
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


#: The sentence a winner-only grade renders as. It is the score sentence with
#: the score removed, NOT a new register: the strings this field already
#: carries are ``Sevilla FC wins 1-0`` and ``Aryna Sabalenka wins 2-0``, so
#: ``Fiona Crawley wins`` is the same sentence about a venue that named a side
#: and no scoreline. Serving the bare participant name instead would render as
#: "Settled · Fiona Crawley", which does not say which of the two she is.
WINNER_SENTENCE = "{participant} wins"

#: The graded moneyline outcome that names NEITHER side because the match had
#: no winner. Normalised-exact, never a substring.
#:
#: 🔴 A DRAW IS A RESULT, AND REFUSING IT IS NOT THE SAME REFUSAL AS REFUSING A
#: PROP. :func:`_names_a_participant` answers ``None`` for ``Tie`` because a tie
#: is not one of the two sides — correctly, as a participant question. But the
#: caller reads that ``None`` as "the venue said nothing about the whole
#: contest", and on these rows the venue said the most definite thing it can
#: say. Measured on production 2026-09-19 over the scoreless ``live``/
#: ``suspended`` arm: 1,295 events hold a positive venue grade, 980 already
#: render a result, and of the 315 that do not, **8 are soccer matches whose
#: graded full-scope moneyline is the draw leg** — every one of them a Kalshi
#: three-way where the ``-TIE`` market is ``finalized``/``result=yes`` and both
#: side markets are ``result=no``. Those 8 pages say "Settled" and never say
#: what happened.
#:
#: The vocabulary is the venues' own and is deliberately only these two:
#: ``Tie`` is what Kalshi writes on its three-way soccer moneylines (8 legs) and
#: ``Draw`` is Polymarket's (1 leg). Nothing here is inferred from a price, from
#: a missing winner, or from "neither side was graded" — the draw leg itself
#: carries ``is_winner = true`` under :data:`VENUE_SETTLEMENT_SOURCE`, which is
#: the same warrant every other sentence in this module rests on.
DRAW_OUTCOME_NAMES = frozenset({"tie", "draw"})

#: What a graded draw renders as. "Settled · Draw", matching the register the
#: score path already publishes for the same event shape — a graded
#: ``Correct Score`` market on a drawn match sends ``Draw 0-0``, so this is that
#: sentence with the score removed, exactly as :data:`WINNER_SENTENCE` is.
DRAW_SENTENCE = "Draw"

#: An outcome name that is itself a MATCHUP rather than one side of one.
#:
#: 🔴 #4629's both-sides refusal below is defeated by TRUNCATION, and the
#: specimen is live. ``/events/15309330`` grades the outcome
#: ``US Open WTA (Doubles): Siniakova/Townsend vs Montgomery/Krue`` — the
#: venue's full-matchup name cut at 60 characters. It contains the home pair
#: and, because ``Krueger`` lost its last three letters, NOT the away pair — so
#: the both-sides guard never fires and the FIRST-NAMED side is reported as the
#: winner whoever actually won. Measured over the 778 admitted ``suspended``
#: events 2026-09-17: exactly one outcome name matches this, and it is that
#: row. Refusing it costs one event and closes the whole class.
#:
#: ``at`` and a bare ``v`` are deliberately NOT connectors here. They are in
#: the matchup grammar, and they are also words that appear inside real names;
#: this pattern runs on a name we are about to PRINT as a verdict, so it is
#: sized to the shape that actually occurs rather than to the grammar.
_OUTCOME_IS_A_MATCHUP_RE = re.compile(r"\S\s+(?:vs\.?|v\.|@)\s+\S", re.IGNORECASE)


def _names_a_participant(
    outcome_name: Optional[str],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Optional[str]:
    """Which of this event's two sides does the graded outcome name? (#6739)

    Returns OUR spelling of that participant, not the venue's, because the
    sentence is rendered beside our own team names.

    🔴 EQUALITY WAS THE FIRST DRAFT AND IT REFUSED THE SPECIMEN THAT MOTIVATED
    THE SHIP. ``/events/15313807`` stores ``home_team_name = 'Crawley'`` while
    the venue grades ``'Fiona Crawley'`` — our row carries the surname and
    Polymarket carries the full name. Replayed over the ``suspended`` arm, an
    exact test found 265 events and every one of them was a boxing or tennis
    row where the two spellings happen to agree; the whole ITF population —
    the class #6739 was filed about — was invisible to it. So the test is
    :func:`~app.utils.prediction_market_matching._fuzzy_team_match`, which is
    the SAME primitive the blend orients its moneyline leg with on these exact
    rows. A second containment rule written here is the #1951 drift failure.

    🔴 AN OUTCOME THAT MATCHES BOTH SIDES NAMES NEITHER (#4629, inherited with
    the primitive). ``_fuzzy_team_match`` is a containment test, so
    Polymarket's full-matchup outcome name — ``Fiona Crawley vs. Naiktha
    Bains`` — reaches both. Skipping is the honest failure: a name that
    genuinely reaches both sides is a name this module cannot orient, and two
    players sharing a surname is the shape that makes that real rather than
    hypothetical.

    ``None`` for anything that is not one of the two sides. A moneyline market
    whose graded outcome is ``Yes``, ``Over 21.5`` or a third party is a market
    this module has no standing to read a match winner out of.
    """
    from app.utils.prediction_market_matching import _fuzzy_team_match

    name = (outcome_name or "").strip()
    if not name or _OUTCOME_IS_A_MATCHUP_RE.search(name):
        return None
    home = (home_team_name or "").strip()
    away = (away_team_name or "").strip()
    matches_home = bool(home) and _fuzzy_team_match(name, home)
    matches_away = bool(away) and _fuzzy_team_match(name, away)
    if matches_home and matches_away:
        return None
    if matches_home:
        return home
    if matches_away:
        return away
    return None


def choose_settled_winner(
    graded_markets: Iterable[tuple[Optional[str], Optional[str], Optional[str]]],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Optional[str]:
    """What the venue graded about the WHOLE match, as a sentence.

    That is a side winning on all but eight of the rows it answers, which is
    why it is named for the winner; since 2026-09-19 it is also ``"Draw"``,
    because a three-way moneyline has three verdicts and the third one is a
    result too (:data:`DRAW_OUTCOME_NAMES`).

    #6739's producer half, and the fallback under :func:`choose_settled_score`:
    56 of the 426 measured events grade a full-scope SCORE market, and the
    other 370 "are graded on props alone" — which is true of the score
    vocabulary and is NOT true of the moneyline. Measured on production
    2026-09-17 over the ``suspended`` arm: 1,121 events hold a positive venue
    grade, 305 of them grade an outcome that names one of the two sides, and
    **265 of those name it on a market this function admits** — 11 of the 305
    carry a score-shaped market at all, so this is very nearly all new. The
    reader-visible change is that a settled page stops saying only "Settled"
    with a 89%–11% chart under it and says which player won.

    🔴 THE MARKET TEST IS :func:`~app.utils.game_market_class.classify_game_market_class`
    AND IT IS NOT A CONVENIENCE. A graded outcome naming a participant is NOT
    evidence of a match winner — it is the shape of every set, map, half and
    handicap book the venue writes. Replayed over the 773 stored
    participant-named grades in that population:

        ==================================  =====  ==========================
        market shape                        grades verdict
        ==================================  =====  ==========================
        ``Set Handicap: A (-1.5) vs B (+1.5)``  286 refused (``spread``)
        ``Set 1 Winner: A vs B``                150 refused (``other``)
        ``Set 2 Winner: A vs B``                  9 refused (``other``)
        ``A vs. B: Map 1|2|3``                   18 refused (``other``)
        ``Game Spread: A (-3.5) vs B (+3.5)``    11 refused (``spread``)
        ``A vs B`` / ``M15 Monastir: A vs B``   265 ADMITTED (``moneyline``)
        ==================================  =====  ==========================

    Every one of those refusals is a page that would have been told the set-1
    winner won the match. The recognizer is the one #5698 and #5743 were
    written against for exactly this class, it is source-agnostic, and it
    imports only stdlib — so this module reusing it is the #1951 rule (one
    classifier, never a second copy), not a shortcut.

    ``None`` ON DISAGREEMENT, the same refusal :func:`choose_settled_score`
    makes and for the same reason. Measured: 0 of the 305 events grade two
    different sides as the match winner today, which is why the refusal is
    written before a specimen exists rather than after. A duplicate event pair
    or a mutually-exclusive market with two winners would put two winners on
    one row, and picking one by sort order is how a deterministic tiebreak
    becomes a confident wrong answer.

    ``graded_markets`` is ``(market_name, market_external_id, outcome_name)``
    because the recognizer's ticker branch needs the id: a ``KXNBA2HSPREAD``
    ticker under a bare-matchup title is a spread, and the name alone cannot
    say so.

    🔴 A GRADED DRAW IS THE THIRD VERDICT, AND IT COMPETES IN THE SAME
    DISAGREEMENT TEST (:data:`DRAW_OUTCOME_NAMES`). The set now holds SENTENCES
    rather than participants so that "the venue graded Tie" and "the venue
    graded Sturm Graz" land in one set and refuse each other — on a three-way
    moneyline those are contradictory claims about one match, and a draw
    admitted on a separate path would have been published beside a winner
    instead of refusing with one. The formatting moved inside the loop for that
    reason alone; for every row that has no draw leg the set is the same set of
    the same size and the answer is byte-identical.

    The draw test is checked BEFORE the participant test, and the order is not
    arbitrary: it is the only order under which a venue that named a side
    called ``Tie`` would still be read as that side rather than as a draw. No
    such side exists in the measured population (0 of 4,804 graded legs), which
    is why the precedence is stated here rather than defended by a guard.
    """
    from app.utils.game_market_class import classify_game_market_class

    verdicts = set()
    for market_name, market_external_id, outcome_name in graded_markets:
        if (
            classify_game_market_class(market_name or "", market_external_id)
            != "moneyline"
        ):
            continue
        if _normalise_segment(outcome_name or "") in DRAW_OUTCOME_NAMES:
            verdicts.add(DRAW_SENTENCE)
            continue
        participant = _names_a_participant(
            outcome_name, home_team_name, away_team_name
        )
        if participant is not None:
            verdicts.add(WINNER_SENTENCE.format(participant=participant))
    if len(verdicts) != 1:
        return None
    return next(iter(verdicts))


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


#: What a row this module has nothing to say about is told: a PRESENT pair of
#: keys saying "no venue result to show". Different from the keys being ABSENT,
#: which is what a failed read must produce — there the surface keeps whatever
#: it said before this module existed rather than being handed a confident
#: ``False`` nobody established.
#:
#: #7702 WIDENED WHAT REACHES IT, and the widening is why the line above no
#: longer says "no positive venue grade". It is now also the answer for a row
#: that HAS a positive grade which :func:`settlement_from_graded_rows` declines
#: to state — see that function. The key's meaning to every consumer is "is
#: there a venue result to print", and for both of those rows the answer is no.
NO_VENUE_GRADE: dict = {"venue_settled": False, "venue_settled_result": None}


def settlement_from_graded_rows(
    graded: Sequence[tuple[Optional[str], Optional[str], Optional[str]]],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> dict:
    """The two keys a surface serves, from this event's positive venue grades.

    ``graded`` is ``(market_name, market_external_id, outcome_name)`` per
    winning leg, which is the shape :func:`choose_settled_winner` needs and the
    shape both readers' queries already produce.

    🔴 THIS FUNCTION IS THE POLICY, AND THE POLICY IS THE ORDER (#6739).
    SCORE FIRST, WINNER SECOND. A full-scope score already names the winner —
    "Aryna Sabalenka wins 2-0" — so the winner sentence is strictly the same
    statement with the score dropped. Asking for the winner first would replace
    56 richer strings with poorer ones; ``or`` reaches it only where the score
    vocabulary has nothing, which is 265 of the 305 side-graded ``suspended``
    rows measured 2026-09-17.

    It lives here, pure, because it now has TWO readers — the event detail
    route asks it per event and the league rails ask it per rail (#6739's
    second half, ``venue_settlement_reader``). Their QUERIES legitimately
    differ: a batch has to carry the grouping key and a single read does not.
    Their ANSWER may not, and an order copied into two files is the #1951 drift
    this repo keeps paying for. One order, one place, two callers.

    🔴 THE PAIR IS CO-TRUE (#7702). ``venue_settled`` is ``True`` exactly when
    ``venue_settled_result`` names something. It USED to be keyed on ``graded``
    being non-empty while the result was keyed on the far stricter question
    "did a namer admit any of these legs" — two standards over one set of rows,
    and where they disagreed only the claim survived.

    What that published, measured on production 2026-09-21 by running THIS
    function over the graded legs of events with a positive grade and no score:
    **19 of 45 sampled events with kickoff 3–30 days ago** (population 1,705)
    got ``venue_settled: True`` with a null result. ``/events/15310805`` was the
    whole hero — the word "Settled", two team names, and nothing else; and not
    even the "No price" line, because #6438 suppresses that on the stated
    grounds that "the settled pill in this same card already carries the
    result". The two rules compose into a page that asserts a settlement and
    then names none.

    This REVERSES #6381's Acceptance 4 ("settled without inventing a result is
    sufficient"), deliberately and on evidence. That acceptance was true for the
    event page as it stood and has since been inherited by surfaces it was not
    written for: #6438 took away the hero's fallback on the strength of the
    pill, and #7070/#7092 put the pill onto league-rail and events-list cards
    where it is the ENTIRE card. Against that, Alex's standing ruling — settled
    means settled, heroes show winners and cards show results — outranks an
    implementation acceptance inside one issue.

    🔴 NOT A LOOSENING AND NOT A REGRESSION OF #7070. Every refusal in
    :func:`choose_settled_winner` and :func:`choose_settled_score` is untouched
    and is still what produces the ``None``; this only stops us captioning that
    refusal as a result. No row that names a winner or a score today loses one —
    #6739's moneyline-graded and score-graded events are byte-identical, which
    ``TestANamedResultIsUnchanged`` pins, and the mixed row (a derivative grade
    BESIDE an admitted moneyline) still publishes its winner because the new arm
    reads the ANSWER and not the legs.
    """
    if not graded:
        return dict(NO_VENUE_GRADE)
    result = choose_settled_score(
        outcome_name
        for market_name, _market_external_id, outcome_name in graded
        if is_full_scope_score_market(market_name)
    ) or choose_settled_winner(graded, home_team_name, away_team_name)
    if not result:
        return dict(NO_VENUE_GRADE)
    return {"venue_settled": True, "venue_settled_result": result}
