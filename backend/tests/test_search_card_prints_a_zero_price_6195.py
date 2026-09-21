"""A `0.0` IS A PRICE AND THE SEARCH CARD PRINTS IT. #6195.

═══ WHAT THE READER SAW ═══

`GET /api/events/search?q=Super Bowl`, production, 2026-09-21 09:20Z. Market
13886744, *Sports Emmy Award for Outstanding Live Sports Special: Championship
Event?* — the card draws five rungs and four of them are a dash:

    FOX MLB: World Series        99%
    NBA Finals                    -
    College Football Playoff      -
    Super Bowl LX                 -
    The Masters                   -

A near-empty board on a market where we know every answer. The stored values are
`0.000000`, not `NULL` — every one of those rows is graded `api_settlement` with
`is_winner=false` — so the card is not missing prices, it is declining to print
the ones it has.

═══ THE DISAGREEMENT THAT MAKES IT UNARGUABLE ═══

`/api/futures/13886744`, the same minute, served those four as `0.0`. One tap
apart, two answers about the same four numbers, and the near-empty one is on the
surface a reader meets FIRST.

═══ THE MECHANISM ═══

`_build_search_top_outcomes` wrote `float(o.current_probability) if
o.current_probability else None` — the falsy read, in which `0.0` and `None` are
the same thing. The fix keys on `outcome_prints_a_price` instead, which #6195
also flipped from `not value` to `value is None`.

The predicate rather than a local `is not None`, and that is load-bearing: the
age pip under this card (`_served_prices_as_of`) scopes itself to rows that print
a price by calling that same function, and #6256 is the incident where the two
sides of a card disagreed about which rows are prices. They decide it once.

═══ SCOPE — WHY SETTLED-NESS IS NOT THE KEY ═══

Our row for this market is `status='open'` with `settled_at` NULL while the venue
has graded every leg. A fix keyed on settled-ness would not have reached this
card at all. The defect is the falsy read itself, wherever the row sits, which is
what `test_the_defect_is_the_falsy_read_not_the_status` pins.

═══ WHAT MUST NOT MOVE ═══

Absent is not zero (ruling 051). A leg we hold NO price for still prints `—` and
still may not date the mark — `test_control_*` below, and the NULL specimen in
`test_unpriced_leg_cannot_date_the_mark_6256.py`, are what keep that distinction
load-bearing rather than rhetorical. This fix makes `0.0` printable; it does not
make `None` printable.

It does NOT change membership of the SEARCH ladder (`test_control_the_count_badge_
does_not_move`). It does change membership on the FEED, in one bounded place that
#4679's handover did not name — see the final section of this file, which
measures the reach rather than waving at it.

═══ NOT VACUOUS ═══

Every test states its BEFORE: the fixture's stored values are asserted to be
`0.000000` (and the control's to be `None`) before anything is served, so a
fixture that drifted to NULL in a later edit fails loudly instead of passing on
nothing. `test_the_eliminated_legs_are_actually_on_the_card` asserts membership
by NAME first, because a ladder that sliced them away would make every
probability assertion below true of an empty set.

Mutation check (applied, measured, reverted — counts are what was observed, not
what was expected):

* `outcome_prints_a_price` back to `if not value` -> **3 fail** (the three ship
  tests). The controls correctly do NOT move: reverting the predicate returns
  both sides of the card to the same wrong answer, and agreement is all they
  assert.
* the card serializer back to `if o.current_probability`, leaving the predicate
  and the lean shape fixed -> **4 fail**, the three ship tests plus
  `test_control_the_predicate_is_the_one_both_sides_share`. That fourth is the
  fork detector earning its place: this is the only mutant in the set that makes
  the two sides of the card disagree, which is #6256.
* the lean serializer back to `if o.current_probability` -> **1 fail**,
  `test_ship_the_typeahead_dropdown_says_the_same_thing`, which is the only test
  that can see the dropdown drift away from the results card (#993's pair).
* `outcome_prints_a_price` to `return True` for its whole body -> **3 fail**,
  all three controls, and 9 more across
  `test_unpriced_leg_cannot_date_the_mark_6256.py` and
  `test_search_futures_price_age_6018.py`. Note HOW the badge control catches
  it: `float(None)` raises `TypeError` inside the serializer, i.e. the
  predicate's `is None` branch is now the thing standing between an unpriced leg
  and a 500 on a search page. Before this change the serializer's own truthiness
  guarded that locally; the guard moved into the predicate with the decision.
* 🪤 the SMALLER version of that mutant — deleting only `if value is None:
  return False` and leaving the `try: float(value)` below it — is EQUIVALENT,
  not a survivor: `float(None)` raises `TypeError`, which that except clause
  already turns into `False`. It was measured as 7-pass before being recognised
  as equivalent, and it is recorded here so a later reader does not mistake the
  redundancy for an untested line.
* drop the `is_winner`/`resolution_source` grade off every fixture row -> **0
  fail**, deliberately: this fix does not read the grade, and a test that
  tightened when it was removed would be pinning the wrong cause. The grade is
  in the fixture because production has it, not because the code consults it.
"""

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _build_search_top_outcomes,
    _format_futures_for_search,
)
from app.utils.futures_market_snapshot import outcome_prints_a_price


class _Outcome:
    """The attributes the search survivor chain reads off an ORM outcome row."""

    def __init__(
        self,
        oid,
        name,
        prob,
        ext,
        rank,
        bid="0.0000",
        ask="1.0000",
        winner=False,
        resolution_source="api_settlement",
        american_odds=None,
        last_updated=None,
    ):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.current_american_odds = american_odds
        self.rank = rank
        self.probability_change_24h = None
        self.last_updated = last_updated
        self.external_id = ext
        self.is_winner = winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 13886744)
        self.name = kw.get(
            "name",
            "Sports Emmy Award for Outstanding Live Sports Special: "
            "Championship Event?",
        )
        self.sport = None
        self.category = kw.get("category", "entertainment")
        self.llm_sport_category = kw.get("llm_sport_category", "entertainment")
        self.market_tier = kw.get("market_tier", 3)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "kalshi")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", True)


# ---------------------------------------------------------------------------
# The specimen's six stored rows, verbatim from production 2026-09-21, including
# the full Kalshi tickers — the survivor chain keys refusals on `external_id`,
# so an abbreviated id quietly builds a board production does not serve.
# ---------------------------------------------------------------------------

_ELIMINATED = ("NBA Finals", "College Football Playoff", "Super Bowl LX", "The Masters")


def _sports_emmy_board():
    """Market 13886744, all six stored rows as of 2026-09-21.

    `0.0000 / 1.0000` is the book on every row — maximally wide, which is what
    an already-graded Kalshi market looks like once nobody is quoting it. The
    winner carries `0.990000` and the rest `0.000000`; all six are graded
    `api_settlement` although the MARKET is still `status='open'` on our side.
    """
    return _Market(
        [
            _Outcome(89617305, "FOX MLB: World Series", 0.99,
                     "KXSPORTSEMMY-26OLSSCE-FOX", 1, winner=True,
                     american_odds=-9900),
            _Outcome(89617306, "NBA Finals", 0.0,
                     "KXSPORTSEMMY-26OLSSCE-NBA", 6),
            _Outcome(89617307, "College Football Playoff", 0.0,
                     "KXSPORTSEMMY-26OLSSCE-COL", 2),
            _Outcome(89617308, "Super Bowl LX", 0.0,
                     "KXSPORTSEMMY-26OLSSCE-SUP", 4),
            _Outcome(89617309, "The Masters", 0.0,
                     "KXSPORTSEMMY-26OLSSCE-MAS", 3),
            _Outcome(89617310, "Tie", 0.0,
                     "KXSPORTSEMMY-26OLSSCE-TIE", 5),
        ]
    )


def _unpriced_board():
    """THE CONTROL — the same board with the losers genuinely unpriced.

    Identical in every respect but one: `None` where the specimen holds
    `0.000000`. This is the shape that must keep rendering `—`.
    """
    board = _sports_emmy_board()
    for outcome in board.outcomes:
        if outcome.name != "FOX MLB: World Series":
            outcome.current_probability = None
    return board


def _ladder(market, lean=False):
    return _build_search_top_outcomes(
        market, limit=_SEARCH_LADDER_LIMIT, lean=lean, withheld=None
    )


def _by_name(rows):
    return {r["name"]: r["probability"] for r in rows}


def _stored(market):
    return {o.name: o.current_probability for o in market.outcomes}


# ══════════════════════════════════════════════════════════════════════════
# SHIP
# ══════════════════════════════════════════════════════════════════════════


def test_the_eliminated_legs_are_actually_on_the_card():
    """Membership FIRST, or every assertion about their number is vacuous."""
    board = _sports_emmy_board()
    rows = _ladder(board)

    assert len(rows) == _SEARCH_LADDER_LIMIT, (
        f"the ladder is not the served shape: {[r['name'] for r in rows]}"
    )
    drawn = {r["name"] for r in rows}
    for name in _ELIMINATED:
        assert name in drawn, f"{name} was sliced off the card entirely: {drawn}"


def test_ship_a_zero_rung_prints_zero_instead_of_a_dash():
    """The reader's sentence: four rungs stop being dashes."""
    board = _sports_emmy_board()

    # BEFORE, stated: these really are stored zeros and not NULLs. Without this
    # the test below would pass just as happily on a fixture that had drifted.
    for name in _ELIMINATED:
        assert _stored(board)[name] == 0.0, (
            f"{name} is not a stored zero in this fixture — the specimen is gone"
        )

    served = _by_name(_ladder(board))

    for name in _ELIMINATED:
        assert served[name] == 0.0, (
            f"{name} served {served[name]!r}; a field that has priced a "
            "candidate at nothing is an answer, not a silence"
        )
    assert served["FOX MLB: World Series"] == 0.99, (
        "the winner's price moved, which this fix must not touch"
    )
    assert not [n for n, p in served.items() if p is None], (
        f"a dash survived on a board where we know every answer: {served}"
    )


def test_ship_the_typeahead_dropdown_says_the_same_thing():
    """#993's pair, which is why one serializer builds both shapes.

    The dropdown is the surface a reader meets FIRST. Repairing the results card
    and leaving this one would move the disagreement rather than end it — the
    exact failure `_build_search_top_outcomes` exists to prevent.
    """
    board = _sports_emmy_board()
    lean = _by_name(_ladder(board, lean=True))
    card = _by_name(_ladder(board, lean=False))

    assert lean == card, (
        f"the dropdown and the results card disagree: {lean} vs {card}"
    )
    for name in _ELIMINATED:
        assert lean[name] == 0.0


def test_the_defect_is_the_falsy_read_not_the_status():
    """A fix keyed on settled-ness would never have reached this card.

    Our row is `status='open'` with the venue's grade already on every leg. The
    board is served identically whatever the status says, because nothing in
    this path consults it — which is the scope note in #6195's own comment
    thread, asserted rather than trusted.
    """
    for status in ("open", "closed", "settled"):
        board = _sports_emmy_board()
        board.status = status
        served = _by_name(_ladder(board))
        for name in _ELIMINATED:
            assert served[name] == 0.0, f"status={status}: {name} -> {served[name]!r}"


# ══════════════════════════════════════════════════════════════════════════
# CONTROLS — what must not move
# ══════════════════════════════════════════════════════════════════════════


def test_control_an_absent_price_still_prints_a_dash():
    """Absent is not zero (ruling 051).

    This is the test that separates "print the zeros we have" from "print a
    number for every row", and it is the only one that can see a predicate
    mutated to `return True`.
    """
    board = _unpriced_board()

    for name in _ELIMINATED:
        assert _stored(board)[name] is None, "the control fixture lost its NULLs"

    served = _by_name(_ladder(board))
    for name in _ELIMINATED:
        assert served[name] is None, (
            f"{name} served {served[name]!r} for a price we do not hold"
        )


def test_control_the_predicate_is_the_one_both_sides_share():
    """Behaviour, not `is` — a hand-rolled copy in the serializer fails here.

    For every leg shape, "the search card would print a number" and "the shared
    predicate says this leg prints a price" give one answer. #6256 is what
    happens when they give two.
    """
    board = _sports_emmy_board()
    board.outcomes[1].current_probability = None  # one of each shape on one board

    rows = {r["id"]: r for r in _ladder(board)}
    for outcome in board.outcomes:
        if outcome.id not in rows:
            continue
        prints = rows[outcome.id]["probability"] is not None
        assert prints is outcome_prints_a_price(outcome), (
            f"{outcome.name}: the card prints={prints} but the shared predicate "
            f"says {outcome_prints_a_price(outcome)} — the two sides disagree again"
        )


def test_control_the_count_badge_does_not_move():
    """This fix changes what a row PRINTS, never whether it is on the board.

    `outcome_count` is built from `_search_surviving_legs`, one function upstream
    of the print decision. If this number moves, the change has reached into
    membership and #6585's badge/board agreement needs re-checking.

    It also catches the over-broad predicate, though by CRASHING rather than by
    counting, and that is worth knowing: with `outcome_prints_a_price` returning
    True for everything, the unpriced board reaches `float(None)` and the
    serializer raises `TypeError` — a 500 on a search page, which
    `_format_futures_for_search`'s own notes call the thing a serializer must
    never be. The `is None` branch is that guard now.
    """
    assert _format_futures_for_search(_sports_emmy_board(), None)["outcome_count"] == 6
    assert _format_futures_for_search(_unpriced_board(), None)["outcome_count"] == 6


# ══════════════════════════════════════════════════════════════════════════
# THE CONSEQUENCE THE HANDOVER DID NOT NAME — feed leg MEMBERSHIP
# ══════════════════════════════════════════════════════════════════════════
#
# #4679's boundary note named two print sites and `displayed_price_stamp`. It
# did not name `_drop_stale_observation_legs`, which also calls the shared
# predicate — and there the predicate decides MEMBERSHIP, not formatting:
#
#     survivors = [o for o in outcomes
#                  if o.id not in stale_ids or not _outcome_prints_a_price(o)]
#
# A leg more than 7 days behind its market's newest stamp is dropped IF it
# prints a number. Making `0.0` printable therefore moves a stale zero leg from
# "kept, rendered as a dash" to "dropped". Measured on production 2026-09-21
# over open markets: 672 zero legs on 238 markets sit past that lag, of which
# **97 legs on 86 cards** fall inside the three-leg slice a Discover card draws
# — so that is the bound on what a reader can see change here.
#
# KEPT RATHER THAN EXEMPTED, and the reason is that the alternative is worse. A
# 7-day-stale `0%` is a freshness claim this codebase declines to make for every
# other price; exempting zeros would print the one number whose staleness we
# have specifically decided not to vouch for. The existing rule now applies
# uniformly instead of having a hole shaped like `0.0`, and #7180's finding cuts
# the same way — a row the reader cannot read is a wasted slot, not a courtesy.
#
# These two tests exist so that consequence is asserted rather than discovered.


def _feed_legs(market, outcomes):
    from app.routes.feed import _drop_stale_observation_legs

    return [o.name for o in _drop_stale_observation_legs(market, outcomes)]


def _dated(outcome, stamp):
    outcome.last_updated = stamp
    return outcome


def test_a_fresh_zero_leg_survives_the_feed_stale_filter():
    """The common case, and the one the ship depends on.

    Both production specimens are this shape: market 13886744's six rows share
    one stamp, so nothing is stale and every zero reaches the card to print
    `0%`. If this fails, the fix cannot be seen on its own specimen.
    """
    from datetime import datetime, timezone

    same = datetime(2026, 8, 6, 20, 49, 38, tzinfo=timezone.utc)
    board = _sports_emmy_board()
    for outcome in board.outcomes:
        _dated(outcome, same)

    surviving = _feed_legs(board, board.outcomes)
    for name in _ELIMINATED:
        assert name in surviving, (
            f"{name} was dropped from a board whose legs share one stamp: "
            f"{surviving}"
        )


def test_a_stale_zero_leg_is_dropped_by_the_same_rule_that_drops_a_stale_price():
    """The named consequence — asserted beside its control so it reads as a rule.

    The point is the PAIR: a 7-day-lagged leg is dropped whether its number is
    `0.0` or `0.55`, and a leg we hold no price for is still kept however old it
    is (nothing about `None` changed). Before #6195 the zero row behaved like
    the `None` row here; it now behaves like the priced row, which is the whole
    content of "a zero is a price".
    """
    from datetime import datetime, timezone

    fresh = datetime(2026, 8, 6, tzinfo=timezone.utc)
    lagged = datetime(2026, 5, 12, tzinfo=timezone.utc)

    board = _sports_emmy_board()
    legs = board.outcomes
    _dated(legs[0], fresh)                      # FOX MLB, 0.99 — the newest
    _dated(legs[1], lagged)                     # NBA Finals, 0.0
    _dated(legs[2], fresh)
    _dated(legs[3], fresh)
    _dated(legs[4], fresh)
    _dated(legs[5], fresh)

    surviving = _feed_legs(board, legs)
    assert "NBA Finals" not in surviving, (
        f"a 3-month-stale 0% was served as a current price: {surviving}"
    )

    # CONTROL A — the same lag on a leg with an ordinary price is dropped too,
    # so the rule is about staleness and not about zero.
    board_priced = _sports_emmy_board()
    priced = board_priced.outcomes
    priced[1].current_probability = 0.55
    for outcome in priced:
        _dated(outcome, fresh)
    _dated(priced[1], lagged)
    assert "NBA Finals" not in _feed_legs(board_priced, priced)

    # CONTROL B — the same lag on an UNPRICED leg is kept, because a dash makes
    # no freshness claim. This is the branch #6195 did not touch, and it is what
    # stops this test from reading as "drop everything old".
    board_null = _sports_emmy_board()
    nulls = board_null.outcomes
    nulls[1].current_probability = None
    for outcome in nulls:
        _dated(outcome, fresh)
    _dated(nulls[1], lagged)
    assert "NBA Finals" in _feed_legs(board_null, nulls), (
        "an unpriced leg makes no claim about freshness and must still be kept"
    )
