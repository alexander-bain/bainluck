"""THE SEARCH CARD'S COUNT BADGE NAMES THE BOARD THE READER WILL GET. #6585.

═══ WHAT THE READER SAW ═══

`/search?q=Stranger Things`, production 2026-09-19:

    ENTERTAINMENT  [Conference]                                       15
    New "Stranger Things" episode released by...?
        March 31, 2027      6%
        December 31, 2026   2.5%
        ...

One tap later, `/futures/114237` serves **12** outcomes. The badge is not
loosely defined and it is not a rounding: on the same 30 replayed reader
queries, 233 of 236 served futures cards agreed with their board exactly, and
the three that did not were all OVER-counting, every one by +2:

    112938  Who will Trump nominate as Fed Chair?      badge 27  board 25
    113427  What will Fed Rate hit before 2027?        badge 23  board 21
  56995845  Warsh out as Fed Chair by…?                badge  4  board  2

`Warsh out as Fed Chair by…?` is the one that shows how little the number meant:
it promised four answers and the board holds two.

═══ THE MECHANISM ═══

`_format_futures_for_search` built its two halves from two different lists.
`top_outcomes` came from `_search_surviving_legs` — the four pre-sort refusals
(Q480 duplicate conditions, #6524 unbacked legs, #4253 frozen near-certains,
#6676 empty-book phantoms) — while the count was taken from every outcome row
with only the placeholder filter applied. So the badge counted rows the ladder
beside it had already refused.

That is the drift `_search_surviving_legs` was extracted to prevent (#5516's
lift, #993's rule: the click-through has to match what search showed). It was
applied one function short of where it was needed.

**Q480 is the whole of it on all three specimens, and it is the same shape every
time.** A Polymarket parent stores the bare rung AND that same condition's
`_yes`/`_no` legs, named literally "Yes" and "No". The three ids are the one
condition wearing a SUFFIX — not three unrelated ids, and not one repeated id —
which is exactly what `_drop_duplicate_legs` keys on to collapse them for the
ladder. The count read them as two more answers. Read off production, market
56995845 (ids abbreviated, suffix verbatim):

    name               prob   bid    ask     external_id
    Yes                0.110  0.09   0.13    0x348f98e8…a880_yes  <- never shown
    No                 0.890  None   None    0x348f98e8…a880_no   <- never shown
    December 31, 2026  0.031  0.029  0.033   0x348f98e8…a880      <- the rung
    June 30, 2027      0.095  0.09   0.10    0xc159b8f7…15ea      <- the rung

Market 114237 adds one #6524 leg on top: `May 31` at probability 1.0 with an
EMPTY `external_id` — an unbacked rung, no venue id, so not a quote.

═══ WHAT THIS DIFF DOES NOT FIX, AND WHY THAT IS DELIBERATE ═══

Driving `_search_surviving_legs` on the specimens' real production rows lands
the new count exactly on the board's number for 114237 (12), 113427 (21) and
56995845 (2) — and leaves 112938 at 27 against the board's 25.

That residue is a DIFFERENT defect. `Rick Rieder` and `James Bullard` are each
stored twice under two distinct Polymarket condition ids — a live leg and a dead
twin at 0.000 / ask 0.0010. The detail route collapses those with
`drop_superseded_name_twins`; this path's dedup keys on `external_id`, so both
survive. Adding that drop here would change the served LADDER on an unmeasured
population rather than a count, so it is **#7180** and not this diff.

`TestTheNamedRemainder` below pinned that gap OPEN on purpose, so that closing
it could not happen silently.

**CLOSED 2026-09-19 by #7180**, and the pin did its job: that class now asserts
the closure instead, and the paragraph above is history rather than current
behaviour. `_search_surviving_legs` runs `drop_superseded_name_twins` — the same
helper, in the same chain position, as `_format_market_detail` — so market
112938 badges 25, and all six affected boards now equal the number
`/api/futures/{id}` serves. The measurement, the two boards whose LADDER moved
and the guards are in `test_search_card_drops_the_superseded_name_twin_7180.py`.

═══ NOT VACUOUS ═══

Every fixture below states its own BEFORE: each test asserts that the retired
formula — `len([o for o in market.outcomes if not placeholder(o.name)])` —
returns a DIFFERENT, larger number on that same fixture. A test that passes
because its fixture has nothing to drop is a test of nothing, and this file's
whole subject is a count that was too big.

Mutation check (run, not asserted — applied, measured, reverted): restoring the
old line
    real_count = len([o for o in market.outcomes
                      if not _is_placeholder_outcome_name(o.name)])
fails **8 of the 15** tests here (7 pass: the honest-board controls, the
withdrawal control, the prefix invariant and the pinned remainder, all of which
are true either way and are in this file to say so).
"""

from app.routes.events import (
    _SEARCH_LADDER_LIMIT,
    _format_futures_for_search,
    _futures_card_has_no_answer,
    _is_placeholder_outcome_name,
    _search_surviving_legs,
)


class _Outcome:
    """The attributes the search builder reads off an ORM outcome row."""

    def __init__(self, oid, name="Leg", prob=None, bid=None, ask=None, ext=None,
                 winner=False, resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}" if ext is None else ext
        self.is_winner = winner
        # #7180 reads this column through `drop_superseded_name_twins`. Default
        # None = the venue has not answered this leg, which is what every fixture
        # in this file means: a settled row is spelled out where it is intended.
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 114237)
        self.name = kw.get("name", 'New "Stranger Things" episode released by...? ')
        self.sport = None
        self.category = kw.get("category", "entertainment")
        self.llm_sport_category = "entertainment"
        self.market_tier = kw.get("market_tier", 2)
        self.market_type = None
        self.status = kw.get("status", "open")
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", False)


def _retired_formula(market):
    """What this line counted before #6585. The BEFORE every test compares to."""
    return len([o for o in market.outcomes
                if not _is_placeholder_outcome_name(o.name)])


def _badge(market, withheld=None):
    return _format_futures_for_search(market, withheld)["outcome_count"]


# ---------------------------------------------------------------------------
# Production-valued fixtures.
# ---------------------------------------------------------------------------

#: Market 56995845's two real Polymarket condition ids, read off production
#: 2026-09-19. The `_yes`/`_no` SUFFIX is the whole mechanism — the bare rung and
#: its own Yes/No legs are one condition wearing three rows, and
#: `_drop_duplicate_legs` collapses them by stripping that suffix. A fixture that
#: gave all three the identical id would not reproduce the defect at all.
_COND_DEC = "0x348f98e8ce6dcba76c4cd149701cec47e203b3978d73bc1fb03cffd69095a880"
_COND_JUN = "0xc159b8f7eb457df1803d7fff5e35e0952dbe42ddb6f459e5f28c086c0bb715ea"


#: Market 112938 (*Who will Trump nominate as Fed Chair?*), the five rows that
#: matter, read off production 2026-09-19 with their real condition ids, prices,
#: books, grades and `resolution_source`. Two candidates are each stored TWICE —
#: a live leg (`resolution_source` NULL) and a dead twin graded a loss at
#: 0.000000 on an ask of 0.0010. The ids DIFFER, which is why the external_id
#: dedup cannot fold them and #6585 left this card over-counting; #7180 folds
#: them on the settled-loss correspondence instead.
def _fed_chair_superseded_twins():
    return _Market(
        [
            _Outcome(1626332, "Kevin Warsh", 1.0, bid=0.999, ask=1.0,
                     ext="0x61b66d02793b4a68ab0cc25be60d65f517fe18c7d654041281bb130341244fcc",
                     winner=True, resolution_source="api_settlement"),
            _Outcome(1626333, "Rick Rieder", 0.075, bid=None, ask=0.15,
                     ext="0xb9e50edb73f13ebddb16bc35e65e96d4b7e3883964ce085203ee95a2c6fc0e69"),
            _Outcome(1626340, "Rick Rieder", 0.0, bid=None, ask=0.001,
                     ext="0xbd603617895e199d4042781ee55a7a9614af3130ca8e90d257424ca246f66197",
                     resolution_source="api_settlement"),
            _Outcome(1626334, "James Bullard", 0.038, bid=0.02, ask=0.056,
                     ext="0x83a36918851b6c074f1df8cd657d5cba6af1a9ba37e9ad86858b3f7fde617af2"),
            _Outcome(1626350, "James Bullard", 0.0, bid=None, ask=0.001,
                     ext="0x582c62c350aac2720711abeb30b16c41c5cdc9b342bfa30da380b6ea6bdeb1ac",
                     resolution_source="api_settlement"),
        ],
        id=112938,
        name="Who will Trump nominate as Fed Chair?",
    )


def _q480_yes_no_twins():
    """Market 56995845 (*Warsh out as Fed Chair by…?*), exactly as stored.

    Four rows, two conditions. The reader was promised 4 answers and the board
    holds the 2 bare rungs.
    """
    return _Market(
        [
            _Outcome(1, "Yes", 0.11, bid=0.09, ask=0.13, ext=_COND_DEC + "_yes"),
            _Outcome(2, "No", 0.89, bid=None, ask=None, ext=_COND_DEC + "_no"),
            _Outcome(3, "June 30, 2027", 0.095, bid=0.09, ask=0.10, ext=_COND_JUN),
            _Outcome(4, "December 31, 2026", 0.031, bid=0.029, ask=0.033,
                     ext=_COND_DEC),
        ],
        id=56995845,
        name="Warsh out as Fed Chair by…?",
    )


def _unbacked_leg_board():
    """Market 114237's #6524 rung: probability 1.0 on an EMPTY external_id."""
    return _Market(
        [
            _Outcome(1, "March 31, 2027", 0.06, bid=0.04, ask=0.08),
            _Outcome(2, "December 31, 2026", 0.025, bid=0.02, ask=0.03),
            _Outcome(3, "February 28", 0.002, bid=0.001, ask=0.004),
            _Outcome(4, "May 31", 1.0, bid=0.0, ask=1.0, ext=""),
        ]
    )


def _healthy_board():
    """A board with nothing to refuse. The control: its badge must not move."""
    return _Market(
        [
            _Outcome(1, "Kevin Warsh", 0.41, bid=0.39, ask=0.43),
            _Outcome(2, "Christopher Waller", 0.22, bid=0.20, ask=0.24),
            _Outcome(3, "Kevin Hassett", 0.18, bid=0.16, ask=0.20),
            _Outcome(4, "Michelle Bowman", 0.11, bid=0.09, ask=0.13),
            _Outcome(5, "Rick Rieder", 0.075, bid=0.06, ask=0.09),
            _Outcome(6, "James Bullard", 0.038, bid=0.02, ask=0.056),
        ],
        id=112938,
        name="Who will Trump nominate as Fed Chair?",
    )


# ---------------------------------------------------------------------------
# 1. The specimen, in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_the_fixture_really_does_carry_legs_the_ladder_refuses(self):
        """NOT VACUOUS: the gap is stated on the fixture, not assumed."""
        m = _q480_yes_no_twins()
        assert _retired_formula(m) == 4, "fixture must reproduce the badge's 4"
        assert len(_search_surviving_legs(m)) == 2, (
            "fixture must reproduce the board's 2 — if this is not 2 the test "
            "below proves nothing about #6585"
        )

    def test_the_badge_now_names_the_board_and_not_the_rows_behind_it(self):
        m = _q480_yes_no_twins()
        assert _badge(m) == 2, (
            "`Warsh out as Fed Chair by…?` promised four answers and the board "
            "holds two"
        )

    def test_the_two_legs_it_stopped_counting_are_the_ones_it_never_showed(self):
        """The count and the ladder must be talking about the same legs."""
        m = _q480_yes_no_twins()
        card = _format_futures_for_search(m)
        shown = {o["name"] for o in card["top_outcomes"]}
        assert "Yes" not in shown and "No" not in shown, (
            "precondition: the ladder already refuses these"
        )
        assert card["outcome_count"] == len(card["top_outcomes"]) == 2


# ---------------------------------------------------------------------------
# 2. Each refusal is counted out — one test per population.
# ---------------------------------------------------------------------------


class TestEveryRefusalTheLadderMakesIsCountedOut:
    def test_q480_duplicate_condition_legs(self):
        m = _q480_yes_no_twins()
        assert _retired_formula(m) == 4
        assert _badge(m) == 2

    def test_6524_a_leg_with_no_venue_id_is_not_an_answer(self):
        m = _unbacked_leg_board()
        assert _retired_formula(m) == 4, "the unbacked `May 31` was counted"
        assert _badge(m) == 3, "and is not an answer the board will offer"

    def test_6676_an_empty_book_phantom_is_not_an_answer(self):
        """A ~0.50 midpoint quoted on 0.01/0.99 bounds nothing."""
        m = _Market(
            [
                _Outcome(1, "Anthropic", 0.45, bid=0.43, ask=0.47),
                _Outcome(2, "OpenAI", 0.505, bid=0.01, ask=0.99),
                _Outcome(3, "Google", 0.505, bid=0.01, ask=0.99),
            ],
            name="Which company has the best AI model on LiveBench (Coding)?",
        )
        assert _retired_formula(m) == 3
        assert _badge(m) == 1

    def test_4253_a_single_winner_field_cannot_have_five_winners(self):
        """Frozen near-certains on an exclusive board (`?q=Dancing with the Stars`)."""
        m = _Market(
            [
                _Outcome(1, "Contestant 22", 1.0, bid=0.99, ask=1.0),
                _Outcome(2, "Contestant 16", 1.0, bid=0.99, ask=1.0),
                _Outcome(3, "Contestant 33", 1.0, bid=0.99, ask=1.0),
                _Outcome(4, "Real Contender", 0.55, bid=0.53, ask=0.57),
                _Outcome(5, "Other Contender", 0.45, bid=0.43, ask=0.47),
            ],
            id=12764689,
            name="Dancing with the Stars winner",
            mutually_exclusive=True,
        )
        assert _retired_formula(m) == 5
        assert _badge(m) < 5, (
            "a board that cannot have three 100% winners must not promise five "
            "answers"
        )


# ---------------------------------------------------------------------------
# 3. The contract, stated once, so a later drop inherits it for free.
# ---------------------------------------------------------------------------


class TestTheBadgeNamesTheLadderItSitsOn:
    def test_the_count_is_the_survivor_universe_on_every_fixture(self):
        """The invariant #6585 buys: add a fifth refusal and the badge follows it.

        This is the test that makes the next drop safe. #6524 widened this gap by
        exactly one when it shipped, because the count was computed from a list
        nobody thought to move.
        """
        for build in (_q480_yes_no_twins, _unbacked_leg_board, _healthy_board):
            m = build()
            assert _badge(m) == len(_search_surviving_legs(m)), build.__name__

    def test_the_ladder_is_a_prefix_of_what_the_badge_counts(self):
        """A card may show fewer legs than it counts; it may never show more."""
        for build in (_q480_yes_no_twins, _unbacked_leg_board, _healthy_board):
            m = build()
            card = _format_futures_for_search(m)
            assert len(card["top_outcomes"]) <= card["outcome_count"], build.__name__
            assert len(card["top_outcomes"]) <= _SEARCH_LADDER_LIMIT

    def test_a_withheld_price_is_still_an_answer_and_is_still_counted(self):
        """#6993 nulls a leg's PRICE; it does not remove the leg from the board."""
        m = _healthy_board()
        withheld = {2}
        assert _badge(m, withheld) == _badge(m) == 6, (
            "withholding a price must not shrink the board the reader is promised"
        )


# ---------------------------------------------------------------------------
# 4. The controls: honest boards do not move, withdrawal does not change.
# ---------------------------------------------------------------------------


class TestHonestBoardsDoNotMove:
    def test_a_board_with_nothing_to_refuse_keeps_its_number(self):
        m = _healthy_board()
        assert _retired_formula(m) == 6
        assert _badge(m) == 6, "this fix must cost an honest board nothing"

    def test_the_233_of_236_that_already_agreed_are_the_common_case(self):
        """Direction check: this change can only ever shrink a count, never grow it."""
        for build in (_q480_yes_no_twins, _unbacked_leg_board, _healthy_board):
            m = build()
            assert _badge(m) <= _retired_formula(m), build.__name__

    def test_withdrawal_is_untouched_because_it_never_read_this_count(self):
        """`_futures_card_has_no_answer` reads the market, not the badge (#5516)."""
        wholly_unpriced = _Market([_Outcome(1, "A"), _Outcome(2, "B")])
        assert _futures_card_has_no_answer(wholly_unpriced) is True
        assert _futures_card_has_no_answer(_healthy_board()) is False


# ---------------------------------------------------------------------------
# 5. The remainder, pinned OPEN on purpose.
# ---------------------------------------------------------------------------


class TestTheNamedRemainder:
    """CLOSED by #7180 on 2026-09-19. This class now pins the closure.

    It used to assert the opposite — that market 112938 still badged 27 against
    its board's 25 — and it said in terms that a failure meant the remainder had
    moved, not that something broke. It moved: `_search_surviving_legs` now runs
    `drop_superseded_name_twins`, the same helper and the same chain position the
    detail route has used since #6508, so the twin no longer reaches either half
    of this card.
    """

    def test_the_superseded_twin_no_longer_counts_and_that_was_7180(self):
        m = _fed_chair_superseded_twins()
        names = [o.name for o in _search_surviving_legs(m)]
        assert names.count("Rick Rieder") == 1, (
            "the dead twin is a graded LOSS beside a live id-anchored sibling — "
            "#7180 drops it here exactly as the detail route does"
        )
        assert names.count("James Bullard") == 1
        assert _badge(m) == len(_search_surviving_legs(m)), (
            "#6585's contract is unchanged: the badge names the ladder's own "
            "universe, whatever that universe turns out to be"
        )

    def test_the_badge_now_lands_on_the_number_the_board_serves(self):
        """The whole point of both issues, on the card that carried the residue.

        `_retired_formula` is 5 on this fixture and #6585 alone left it at 5 (the
        two twins carry distinct condition ids, so the external_id dedup cannot
        see them). The board serves 3.
        """
        m = _fed_chair_superseded_twins()
        assert _retired_formula(m) == 5
        assert _badge(m) == 3


# ---------------------------------------------------------------------------
# 6. The fix is where it claims to be.
# ---------------------------------------------------------------------------


class TestTheFixIsAtTheSeamAndNotACopyOfIt:
    def test_the_count_calls_the_shared_survivor_function(self):
        """Guards against someone re-inlining the filter chain at the call site.

        A copy would pass every test above on the day it was written and then
        drift the first time a refusal is added to `_search_surviving_legs` —
        which is the exact failure #6585 is.
        """
        import inspect

        src = inspect.getsource(_format_futures_for_search)
        body = src.split('"""', 2)[-1]
        assert "_search_surviving_legs(market)" in body
        assert "_is_placeholder_outcome_name(o.name)" not in body, (
            "the retired formula must not survive anywhere in this formatter"
        )
