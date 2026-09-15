"""May the Gamma winner backfill CREATE the champion leg it cannot find? (#6110)

THE DEFECT THIS EXISTS FOR. Polymarket's Vuelta a España 2026 field (our market
``58675941``, Gamma event ``815313``) settled on 09/14 with 30 riders stored,
every one of them correctly a loser, and **no champion at all**. The page led
with "Tadej Pogacar RESOLVED" over a first row reading "Tadej Pogacar · Lost ·
0% · Settled", because the hero falls back to the highest probability when no
outcome carries ``is_winner``.

The winning leg was dropped at ingest (#6110 fixes that forward) and **nothing
downstream can put it back**, because every recovery rail we own re-grades rows
that already exist:

* ``_backfill_polymarket_winners_from_api`` (Phase 3) matches each Gamma
  sub-market to an outcome by ``condition_id`` and ``UPDATE``\\s it — a leg we
  never stored matches nothing, so the champion is silently skipped while its
  70 fellow legs are graded;
* ``clob_resolve`` re-resolves the ``all_losers``/``pass2_loser`` cohort from
  the CLOB, and it too can only write rows that are there;
* ``_sync_polymarket_resolved_status`` selects ``status != 'resolved'``, and
  these markets are already resolved.

So the one leg that can be missing — the winner, which is exactly the leg the
ingest filter mistook for a reserved slot — is the one leg no rail can recover.
``all_losers`` then grades the whole field down and says so out loud in the
column: "the winning outcome isn't in our DB".

**This module holds the decision to create it, and nothing else.** It is pure:
no session, no network, no clock. The rail that owns the writes asks it one
question per candidate leg and gets back a verdict plus the name to store, so
the rule can be read, tested and argued about without a database.

WHY CREATING A ROW IS ALLOWED HERE AT ALL. Minting an outcome is a heavier act
than grading one, and the refusals below are the price of it. What makes it
defensible is that the venue has already settled the leg: ``outcomePrices[0]``
at a terminal 1.0 on a ``closed`` leg is not a quote we are interpreting, it is
the result Polymarket published. We are storing an answer, not guessing one.

WHERE IT REFUSES, AND WHY EACH ONE IS THERE

``REFUSED_NOT_CLOSED``
    **The venue has not finished with this leg.** Added by the CERT-2893 repair
    ``6110-MINT-ONLY-A-VENUE-CLOSED-LEG``: the first version of this module
    asked only about price, and the grader's exact-SHA counterexample inserted
    an OPEN leg quoted at 0.96 as ``is_winner=True`` — a runaway favourite
    crowned mid-race. That is the #6110 defect running backwards, and it is
    worse than the one being repaired: the original lost a champion, this
    invents one.

    Nothing in the selection can stand in for the flag. The rail selects on OUR
    ``futures_markets.status = 'resolved'``, which is local bookkeeping and can
    be written from an elapsed ``resolution_date`` with no winner evidence
    behind it at all; ``outcomePrices[0]`` on an open leg is a QUOTE, and a
    quote at 0.96 is a market's opinion, not a result. ``closed`` is the venue's
    own statement that the leg is settled and its price has stopped being a
    price — the same discriminator #6110's forward half is keyed on in
    ``_is_placeholder_outcome``, which is where this rule should have come from
    in the first place.

    It fails CLOSED: absent, ``None``, ``False`` or unparseable all refuse. A
    mint is a creation, so "the venue did not say" must never read as "the venue
    said yes". Measured on the specimen (Gamma ``/events?id=815313``,
    2026-09-15): all 71 legs carry ``closed: true`` as a native JSON boolean and
    the winning leg is one of them, so the positive arm is not paid for by this.

``REFUSED_NOT_TERMINAL``
    The leg is not at the venue's terminal price. Grading uses 0.90; creation
    uses :data:`MINT_TERMINAL_PRICE` (0.95, the same envelope
    ``polymarket_settlement_scan.TERMINAL_PRICE_EPSILON`` draws), because a row
    that does not exist yet has no other evidence behind it. A leg between the
    two thresholds is left for the rail to grade if it is already stored, and
    never minted.

``REFUSED_ANONYMOUS_SLOT``
    Polymarket pre-creates empty slots named "Player AD" before a field is
    announced (#953). :func:`is_anonymous_slot` carries the same two patterns
    as ``app.tasks.polymarket._is_placeholder_outcome``, deliberately verbatim
    — ``test_polymarket_champion_leg_minted_6110`` asserts the two agree over a
    shared corpus, so the copy cannot drift into a second opinion.

``REFUSED_UNNAMED``
    No ``groupItemTitle``. The sibling label helper (``_leg_label``) will fall
    back to parsing the question, and that is right for a row being priced —
    but a mint has no existing name to preserve, and a champion stored under a
    guessed label is worse on the page than a champion stored under none. We
    only create a row the venue itself named.

``REFUSED_FIELD_HAS_WINNER``
    The market already crowns someone. A single-winner partition has exactly
    one champion, so a second is a corruption, not a repair — and this rail
    must never be the thing that produces the two-winner shape #999 was filed
    for.

``REFUSED_NOT_A_FIELD``
    Fewer than :data:`MIN_FIELD_LEGS` outcomes stored. This fills a hole in a
    field we already hold; it does not populate an empty or two-legged market,
    where "the winner is missing" is far more likely to mean "this row is not
    the market you think it is".

``REFUSED_ALREADY_HELD``
    We already store that condition id on this market. Then it is the grading
    rail's row, not ours — and if it is somehow ungraded, the ``UPDATE`` above
    us is the correct instrument.

``REFUSED_NAME_TOO_LONG``
    ``futures_outcomes.name`` is ``String(300)``. An over-long title is refused
    here rather than truncated at the database, because the alternative is a
    ``DataError`` raised inside a loop over an event's 71 legs, which costs the
    whole batch its other work (gotcha #42). A refusal is a counted fact; a
    crash is a run that reports nothing.
"""

from __future__ import annotations

import re

#: A leg at or beyond this is the venue's published result rather than a quote,
#: and only such a leg may be CREATED. Deliberately stricter than the 0.90 the
#: grading path uses: grading has a stored row and an ingest history behind it,
#: a mint has neither. Same envelope as
#: ``polymarket_settlement_scan.TERMINAL_PRICE_EPSILON`` (1 - 0.05).
MINT_TERMINAL_PRICE = 0.95

#: How many outcomes a market must already hold before a missing champion is
#: read as a hole in a field rather than as a market we have misidentified.
MIN_FIELD_LEGS = 3

#: Polymarket's reserved-slot naming, verbatim from
#: ``app.tasks.polymarket._is_placeholder_outcome``. One OR MORE uppercase
#: letters: the venue switches to two-letter suffixes ("Player AD") once a field
#: passes 26 slots, and the original single-letter form missed those (#953).
ANONYMOUS_SLOT_TITLE_RE = re.compile(r"^Player\s+[A-Z]+$")
ANONYMOUS_SLOT_QUESTION_RE = re.compile(r"\bPlayer\s+[A-Z]+\b")

#: ``futures_outcomes.name`` is ``String(300)``; see the docstring's
#: ``REFUSED_NAME_TOO_LONG`` clause for why this is a refusal and not a slice.
MAX_NAME_LEN = 300

MINTED = "minted"
REFUSED_NOT_CLOSED = "refused_not_closed"
REFUSED_NOT_TERMINAL = "refused_not_terminal"
REFUSED_ANONYMOUS_SLOT = "refused_anonymous_slot"
REFUSED_UNNAMED = "refused_unnamed"
REFUSED_FIELD_HAS_WINNER = "refused_field_has_winner"
REFUSED_NOT_A_FIELD = "refused_not_a_field"
REFUSED_ALREADY_HELD = "refused_already_held"
REFUSED_NAME_TOO_LONG = "refused_name_too_long"

#: Every verdict this module can return, so a counter map can be built from the
#: module rather than from a caller's memory of it.
VERDICTS = (
    MINTED,
    REFUSED_NOT_CLOSED,
    REFUSED_NOT_TERMINAL,
    REFUSED_ANONYMOUS_SLOT,
    REFUSED_UNNAMED,
    REFUSED_FIELD_HAS_WINNER,
    REFUSED_NOT_A_FIELD,
    REFUSED_ALREADY_HELD,
    REFUSED_NAME_TOO_LONG,
)


def is_anonymous_slot(group_item_title: str | None, question: str | None) -> bool:
    """Is this leg one of Polymarket's pre-created, unnamed reserved slots?

    The title test is anchored and the question test is not, exactly as the
    ingest filter has them: a slot's own title IS "Player AD", while a question
    carries it mid-sentence ("Will Player AD win the …?").
    """
    name = (group_item_title or question or "").strip()
    if ANONYMOUS_SLOT_TITLE_RE.match(name):
        return True
    return bool(ANONYMOUS_SLOT_QUESTION_RE.search(question or ""))


def venue_has_closed_the_leg(closed) -> bool:
    """Has Polymarket itself declared this sub-market finished?

    The Gamma payload sends ``closed`` as a native JSON boolean (measured over
    all 71 legs of event ``815313`` on 2026-09-15), and the string form is
    accepted only because the same field is sent as ``"true"``/``"false"`` on
    Gamma's QUERY side (``polymarket_api`` writes ``params["closed"] =
    str(closed).lower()``), so a future caller reading it back off a filtered
    response is not a surprise.

    Everything else is False, deliberately and without a guess: ``None``,
    absent, ``0``, ``1``, ``"yes"``, an object. A truthiness test would read the
    string ``"false"`` as closed, which is the exact shape of the bug this
    function exists to prevent — and for a CREATE, an unreadable flag must cost
    us a refusal we can count, never a row we cannot unwrite.
    """
    if closed is True:
        return True
    if isinstance(closed, str):
        return closed.strip().lower() == "true"
    return False


def mint_verdict(
    *,
    venue_closed,
    price: float | None,
    group_item_title: str | None,
    question: str | None,
    stored_legs: int,
    stored_winners: int,
    leg_already_held: bool,
) -> tuple[str, str | None]:
    """Should this settled Gamma leg be stored as the market's champion?

    Returns ``(verdict, name)``. ``name`` is non-``None`` only for
    :data:`MINTED`, and is the venue's own ``groupItemTitle`` — never a derived
    or parsed label.

    The order of the tests is not arbitrary. ``leg_already_held`` comes first
    because it is the one condition under which the caller has a better
    instrument than this one; the venue-side tests come next, so a refusal
    names what the venue said rather than what our table looks like; the
    field-shape tests come last, because they are the ones a reader will want
    to see attached to a market id.

    ``venue_closed`` leads the venue-side tests and is a REQUIRED keyword with
    no default. That is the point of it: a default would let the next call site
    inherit the CERT-2893 defect by saying nothing, and "the caller forgot" and
    "the venue settled it" would arrive here as the same argument. A price is
    only a result on a leg the venue has closed, so asking about the price of an
    open leg is asking the wrong question — hence this test runs before it, and
    an open 0.96 is reported as ``REFUSED_NOT_CLOSED`` rather than as a
    threshold miss it would clear.
    """
    if leg_already_held:
        return REFUSED_ALREADY_HELD, None

    if not venue_has_closed_the_leg(venue_closed):
        return REFUSED_NOT_CLOSED, None

    if price is None or price < MINT_TERMINAL_PRICE:
        return REFUSED_NOT_TERMINAL, None

    if is_anonymous_slot(group_item_title, question):
        return REFUSED_ANONYMOUS_SLOT, None

    name = (group_item_title or "").strip()
    if not name:
        return REFUSED_UNNAMED, None

    if len(name) > MAX_NAME_LEN:
        return REFUSED_NAME_TOO_LONG, None

    if stored_winners > 0:
        return REFUSED_FIELD_HAS_WINNER, None

    if stored_legs < MIN_FIELD_LEGS:
        return REFUSED_NOT_A_FIELD, None

    return MINTED, name
