"""#7222 — a Kalshi midpoint the venue's own newest trade refutes is not served.

THE READER'S COMPLAINT, which every specimen below is taken from verbatim.
``/futures/55674185`` (*2027 CONCACAF Gold Cup Champion*, tier 1, the card
``q=gold cup`` returns) printed EIGHTEEN of twenty-three teams at the same 18%,
ranked 4 through 21 by nothing, over a single-winner column summing to 447% with
``prices_withheld: 0``. Bermuda was 18% to win the Gold Cup. Costa Rica —
three-time champion, beaten finalist in 2025 — sat at 2%, below Bermuda, Cuba
and Guyana.

The numbers in ``_GOLD_CUP`` are production rows read 2026-09-19 14:4xZ, not
invented fixtures, because the shape of the defect IS the argument: a served
price that is the exact midpoint of a spread nobody will trade inside, beside
that same leg's real recorded trade at one or two cents.

🔴 THE ISSUE'S OWN ACCOUNT OF THE MECHANISM WAS WRONG AND THIS FILE ENCODES THE
CORRECTION. #7222 was filed saying the two legs that came out right (Costa Rica,
Saudi Arabia) were rescued by a rail keyed on a strictly zero bid, and that the
eighteen escaped it "by one tick". They are not rescued by any rail: their bid is
0.00, so ``_kalshi_yes_probability`` rule 1 does not fire and rule 2 reads their
real 2c trade. The eighteen are broken because rule 1 calls a 1c/35c book TIGHT
(``_KALSHI_TIGHT_SPREAD_MAX`` is 0.50) and publishes its midpoint without ever
reaching the trade. ``test_costa_rica_is_not_rescued_by_a_zero_bid_rail`` pins
the correction so the wrong story cannot be re-derived from the issue text.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it:
- if the rule fired on the wide spread alone it would take Costa Rica, Saudi
  Arabia and the USA off the same board, so those are asserted SPARED by name
  from the same market;
- if the Kalshi arm treated a zero ``last_price`` as evidence the way the
  Polymarket arm does, it would blank every untraded Kalshi longshot against a
  trade that never happened — that inversion is its own class below;
- if the predicate widened but the route kept reading Polymarket's snapshots for
  a Kalshi market, every unit test here would pass and no reader would see any
  change, so the venue-keyed snapshot read is a route-level test, not a unit one.
"""

from types import SimpleNamespace

import pytest

from app.utils.feed_market_quality import EMPTY_BOOK_MAX_BID, FEED_PHANTOM_MIN_SPREAD
from app.utils.futures_unsupported_price import (
    MIDPOINT_TRADE_SOURCES,
    POLYMARKET_BOOKMAKER,
    midpoint_refuted_by_last_trade,
    needs_trade_disconfirmation,
)
from app.utils.kalshi_empty_book import KALSHI_BOOKMAKER

#: The grade every leg of market 55674185 carries. It is a RETRACTION, not a
#: verdict (#6876), and a bare ``resolution_source is not None`` test would have
#: disarmed this whole ship on its own specimen.
_RETRACTION = "ungradeable_result"

#: Market 55674185 as production served it at 14:4xZ on 2026-09-19:
#: (name, served probability, yes_bid, yes_ask, newest Kalshi snapshot's
#: last_price). The first four are the defect; the last three are the same
#: board's honest rows and are the control.
_GOLD_CUP = [
    ("Nicaragua", 0.185000, 0.0100, 0.3600, 0.0100),
    ("Suriname", 0.185000, 0.0100, 0.3600, 0.0100),
    ("Bermuda", 0.180000, 0.0100, 0.3500, 0.0200),
    ("Curacao", 0.180000, 0.0100, 0.3500, 0.0200),
]
_GOLD_CUP_HONEST = [
    ("Costa Rica", 0.020000, 0.0000, 0.3600, 0.0200),
    ("Saudi Arabia", 0.020000, 0.0000, 0.3600, 0.0200),
    ("USA", 0.490000, 0.3300, 0.6500, 0.3300),
]


def _refuted(
    source=KALSHI_BOOKMAKER,
    resolution_source=_RETRACTION,
    prob=0.180000,
    bid=0.0100,
    ask=0.3500,
    last_price=0.0200,
    has_trade_evidence=True,
):
    return midpoint_refuted_by_last_trade(
        source,
        resolution_source,
        prob,
        bid,
        ask,
        last_price,
        has_trade_evidence=has_trade_evidence,
    )


class TestTheProductionSpecimenIsRefused:
    @pytest.mark.parametrize("name,prob,bid,ask,last", _GOLD_CUP)
    def test_every_fabricated_gold_cup_leg_loses_its_number(
        self, name, prob, bid, ask, last
    ):
        assert _refuted(prob=prob, bid=bid, ask=ask, last_price=last) is True, (
            f"{name} serves {prob:.0%} as the midpoint of a {bid:.2f}/{ask:.2f} "
            f"book while its own newest trade is {last:.2f}"
        )

    def test_bermuda_is_the_headline_and_it_goes(self):
        """The one sentence the issue is titled with."""
        assert _refuted(prob=0.180000, bid=0.0100, ask=0.3500, last_price=0.0200)


class TestTheSameBoardsHonestRowsSurvive:
    """If the rule fired on the wide spread alone it would take these three, and
    the page would lose the only prices on it that are true."""

    @pytest.mark.parametrize("name,prob,bid,ask,last", _GOLD_CUP_HONEST)
    def test_the_honest_rows_keep_their_price(self, name, prob, bid, ask, last):
        assert (
            _refuted(prob=prob, bid=bid, ask=ask, last_price=last) is False
        ), f"{name} is priced from a real trade or a real two-sided book"

    def test_costa_rica_is_not_rescued_by_a_zero_bid_rail(self):
        """🔴 THE ISSUE'S MECHANISM, CORRECTED.

        #7222 says Costa Rica came out right because its bid is 0.00 and a rail
        keyed on a strictly zero bid caught it. Nothing caught it: it is spared
        here for the same reason it is spared everywhere, which is that 0.02 is
        not the midpoint of 0.00/0.36. Move its served price ONTO that midpoint,
        leaving the zero bid exactly where it is, and it is refused — so the
        zero bid is doing none of the work the issue credits it with.
        """
        assert (
            _refuted(prob=0.020000, bid=0.0000, ask=0.3600, last_price=0.0200) is False
        )
        assert (
            _refuted(prob=0.180000, bid=0.0000, ask=0.3600, last_price=0.0200) is True
        )

    def test_the_usa_keeps_a_midpoint_because_its_book_is_two_sided(self):
        """The USA row IS a midpoint of a 0.32-wide book — it fails only on the
        bid bound. Without that term the market's own favourite goes blank."""
        assert (
            needs_trade_disconfirmation(
                KALSHI_BOOKMAKER, _RETRACTION, 0.490000, 0.3300, 0.6500
            )
            is False
        )
        assert 0.6500 - 0.3300 >= FEED_PHANTOM_MIN_SPREAD
        assert 0.3300 > EMPTY_BOOK_MAX_BID


class TestTheZeroTradeInversion:
    """🔴 A zero ``last_price`` is evidence on Polymarket and is NOT evidence on
    Kalshi. Getting this backwards is the worst bug this arm could have: it would
    blank every untraded Kalshi longshot and cite a trade that never happened."""

    def test_an_untraded_kalshi_leg_keeps_its_price(self):
        """Same book as Bermuda, but the venue has never printed a trade —
        Kalshi quotes that as ``last_price 0``, which is why the writer's rule 2
        requires ``last_price > 0`` before it will read a trade at all."""
        assert _refuted(last_price=0.0) is False

    def test_the_screen_still_names_it_a_candidate(self):
        """The refusal is in the trade read, not the screen — so the day Kalshi
        starts distinguishing 'no trade' from 'traded at zero', one line moves."""
        assert (
            needs_trade_disconfirmation(
                KALSHI_BOOKMAKER, _RETRACTION, 0.180000, 0.0100, 0.3500
            )
            is True
        )

    def test_polymarket_keeps_reading_a_zero_trade_as_evidence(self):
        """#5876's 46 legs serving exactly 0.5000 off a 0.0/1.0 book. Unchanged
        by this ship, and asserted here because the Kalshi clause sits in the
        same function and a careless spelling would take them with it."""
        assert (
            _refuted(
                source=POLYMARKET_BOOKMAKER,
                resolution_source=None,
                prob=0.5,
                bid=0.0,
                ask=1.0,
                last_price=0.0,
            )
            is True
        )


class TestTheMeasuredExclusions:
    """Each bound, exercised at the value that makes it load-bearing."""

    def test_a_real_longshot_with_a_tight_book_is_spared(self):
        """The issue's last acceptance bullet. A genuine 1c bid against a 3c ask
        is a real price; it is the SPREAD that separates it from the Gold Cup."""
        assert _refuted(prob=0.02, bid=0.0100, ask=0.0300, last_price=0.0100) is False

    def test_a_two_sided_book_above_the_bid_bound_is_spared(self):
        """The 2,129 legs deliberately left out of scope: real money on both
        sides, and their mean trade sits ABOVE their mean served midpoint."""
        assert _refuted(prob=0.575, bid=0.4500, ask=0.7000, last_price=0.6100) is False

    def test_the_bid_bound_is_the_shipped_constant_and_is_inclusive(self):
        """``EMPTY_BOOK_MAX_BID`` is imported, never restated — the issue asks
        for one named constant shared across rails, not a threshold per module.
        Asserted at the boundary in both directions."""
        at = needs_trade_disconfirmation(
            KALSHI_BOOKMAKER,
            None,
            (EMPTY_BOOK_MAX_BID + 0.60) / 2,
            EMPTY_BOOK_MAX_BID,
            0.60,
        )
        over = needs_trade_disconfirmation(
            KALSHI_BOOKMAKER,
            None,
            (EMPTY_BOOK_MAX_BID + 0.01 + 0.60) / 2,
            EMPTY_BOOK_MAX_BID + 0.01,
            0.60,
        )
        assert (at, over) == (True, False)

    def test_a_graded_kalshi_row_keeps_its_settlement_value(self):
        """A real verdict is a settlement value, not a quote (#4788/#5549/#5820)."""
        assert _refuted(resolution_source="api_settlement") is False

    def test_a_retraction_does_not_disarm_the_arm(self):
        """#6876's lesson, one arm over. All twenty-three Gold Cup legs carry
        ``ungradeable_result``; a bare ``is not None`` grade test would have made
        this entire ship inert on its own specimen."""
        assert _refuted(resolution_source=_RETRACTION) is True
        assert _refuted(resolution_source=None) is True

    def test_a_missing_bid_is_not_a_zero_bid(self):
        """``_is_ask_only_book``'s rule, restated for the same reason it exists
        there: ``None`` means the poller recorded no book, and this arm must not
        claim to know anything about those rows. ``is_fabricated_midpoint`` would
        coalesce them into a 0.0/1.0 book; requiring both columns keeps that
        inert on the Kalshi side."""
        assert _refuted(bid=None, ask=0.3500) is False
        assert _refuted(bid=0.0100, ask=None) is False

    def test_a_trade_that_agrees_with_the_midpoint_spares_it(self):
        """The rule is 'the trade disagrees', never 'the book is wide'."""
        assert (
            _refuted(prob=0.180000, bid=0.0100, ask=0.3500, last_price=0.1800) is False
        )

    def test_absent_trade_evidence_fails_open(self):
        """Gotcha #53: we never recorded a trade is not evidence that none exists."""
        assert _refuted(has_trade_evidence=False) is False
        assert _refuted(last_price=None) is False

    def test_a_third_venue_is_out_of_scope(self):
        """Only Kalshi and Polymarket writers record a ``last_price`` at all."""
        assert _refuted(source="odds_api") is False
        assert MIDPOINT_TRADE_SOURCES == {KALSHI_BOOKMAKER, POLYMARKET_BOOKMAKER}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.rows)


def _market(outcomes, source=KALSHI_BOOKMAKER):
    return SimpleNamespace(id=55674185, source=source, outcomes=outcomes)


def _outcome(id, prob, bid, ask, resolution_source=_RETRACTION):
    return SimpleNamespace(
        id=id,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
    )


@pytest.mark.asyncio
class TestTheRouteReadsTheRightVenuesTrades:
    """🔴 THE INERT-FIX TRAP, AND IT IS THE MOST LIKELY WAY TO SHIP #7222 BROKEN.

    Both snapshot queries in ``_refuted_midpoint_outcome_ids`` named
    ``POLYMARKET_BOOKMAKER`` as a literal. Widening the predicate alone would
    produce Kalshi candidates, look for their trades among Polymarket's
    snapshots, find none, fail open, and serve every one of them unchanged —
    every unit test above green and not one reader-visible byte moved.
    """

    async def test_a_kalshi_market_reads_kalshi_snapshots(self):
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0200)])
        assert await _refuted_midpoint_outcome_ids(
            db, _market([_outcome(1, 0.180000, 0.0100, 0.3500)])
        ) == {1}

        compiled = db.statements[0].compile()
        assert str(compiled).count("bookmaker = :bookmaker") == 2, (
            "both the newest-snapshot subquery and the price read must carry the "
            f"term, or the outer half reads every venue. Got: {compiled}"
        )
        bound = [v for k, v in compiled.params.items() if k.startswith("bookmaker")]
        assert bound and set(bound) == {KALSHI_BOOKMAKER}, (
            "the venue is bound as a parameter, so the compiled SQL is identical "
            f"whichever venue is read — only the VALUE catches it. Got: {bound}"
        )

    async def test_the_venue_comes_from_the_market_not_from_a_literal(self):
        """The same outcome shape under a Polymarket market must bind the other
        venue. A single hardcoded spelling passes the test above and fails this."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0200)])
        await _refuted_midpoint_outcome_ids(
            db,
            _market(
                [_outcome(1, 0.180000, 0.0100, 0.3500, resolution_source=None)],
                source=POLYMARKET_BOOKMAKER,
            ),
        )
        bound = [
            v
            for k, v in db.statements[0].compile().params.items()
            if k.startswith("bookmaker")
        ]
        assert set(bound) == {POLYMARKET_BOOKMAKER}

    async def test_a_market_from_a_third_venue_costs_no_query(self):
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0200)])
        assert (
            await _refuted_midpoint_outcome_ids(
                db, _market([_outcome(1, 0.180000, 0.0100, 0.3500)], source="odds_api")
            )
            == set()
        )
        assert db.statements == []

    async def test_the_honest_rows_survive_the_route_too(self):
        """The whole board through the route, not one leg through the predicate:
        four refused, three kept, which is the page the reader gets."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        outcomes, rows = [], []
        for i, (_name, prob, bid, ask, last) in enumerate(_GOLD_CUP + _GOLD_CUP_HONEST):
            outcomes.append(_outcome(i, prob, bid, ask))
            rows.append((i, last))
        db = _FakeSession(rows=rows)
        assert await _refuted_midpoint_outcome_ids(db, _market(outcomes)) == {
            0,
            1,
            2,
            3,
        }
