"""#8826 — a ladder whose leading rungs are one copied, untraded quote serves no card.

Production, 2026-09-26 14:00Z (7:00 AM PDT), page one, the *Fed & Rates* bundle:

    Fed funds rate after Dec 2027 meeting?
    Above 0.00%                                   80%

Kalshi ``KXFED-27DEC`` quotes bid 0.60 / ask 1.00 on every rung from 0.00% to
3.25%, 0 contracts in 24h. We store the midpoint, 0.80, on all fourteen, so the
card's three legs print 80% / 80% / 80% and the bundle row tells a reader there
is a 20% chance of zero rates.

Every assertion on the serializers is on their OUTPUT. The controls are the arms
that make the treatment mean something: each one breaks exactly one of the three
clauses and must still be served — a flat ladder that TRADED, an untraded ladder
that is NOT flat, and a race (not a ladder) whose top three tie on midpoints —
plus a healthy neighbour that survives the omitted card (gotcha #42).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.feed_market_quality import is_templated_flat_ladder
from app.utils.personalization import PersonalizationContext
from tests.test_card_and_page_share_the_withheld_set_7632 import (
    _serve_sports,
    _SportsBoard,
    _SportsLeg,
)
from tests.test_feed_score_futures_resilience import _Market, _mock_db, _Outcome

FED = 61461525
QUESTION = "Fed funds rate after Dec 2027 meeting?"
_RUNGS = [0.00, 0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]
_NAMES = [f"Above {v:.2f}%" for v in _RUNGS]
_IDS = [FED * 100 + i for i in range(len(_RUNGS))]

# The specimen's book, verbatim: bid 0.60 / ask 1.00, stored at its midpoint.
_TEMPLATE = [(0.80, 0.60, 1.00)] * len(_RUNGS)
# Control A — flat, but TRADED: a tight book whose price is not a wide midpoint.
_TRADED_FLAT = [(0.80, 0.79, 0.81)] * len(_RUNGS)
# Control B — untraded wide books, but the ladder FALLS: the card says something.
# Each rung is its own 0.30-wide book, priced at its midpoint, bid well above 5c.
_UNTRADED_FALLING = [
    (round(0.80 - 0.06 * i, 4), round(0.65 - 0.06 * i, 4), round(0.95 - 0.06 * i, 4))
    for i in range(len(_RUNGS))
]


def _rows(book, names=_NAMES):
    return [(n, p, b, a) for n, (p, b, a) in zip(names, book)]


class TestThePredicate:
    def test_the_specimen_is_templated(self):
        assert is_templated_flat_ladder(_rows(_TEMPLATE), QUESTION) is True

    def test_control_a_flat_ladder_that_traded_is_not(self):
        assert is_templated_flat_ladder(_rows(_TRADED_FLAT), QUESTION) is False

    def test_control_an_untraded_ladder_that_falls_is_not(self):
        assert is_templated_flat_ladder(_rows(_UNTRADED_FALLING), QUESTION) is False

    def test_control_a_race_whose_top_three_tie_on_midpoints_is_not(self):
        """Clause 1: a field of names is not a ladder, whatever its prices."""
        names = ["Candidate A", "Candidate B", "Candidate C", "Candidate D"]
        assert is_templated_flat_ladder(_rows(_TEMPLATE, names), QUESTION) is False

    def test_one_traded_rung_among_the_leading_three_spares_the_card(self):
        """Clause 3 is ALL of the leading rungs, not most of them."""
        book = list(_TEMPLATE)
        book[1] = (0.80, 0.79, 0.81)
        assert is_templated_flat_ladder(_rows(book), QUESTION) is False

    def test_one_leading_rung_printing_a_different_percent_spares_the_card(self):
        book = list(_TEMPLATE)
        book[2] = (0.75, 0.50, 1.00)  # a wide midpoint, but 75% ≠ 80%
        assert is_templated_flat_ladder(_rows(book), QUESTION) is False

    def test_only_the_leading_three_are_read(self):
        """The specimen's own tail (4.25% at 90%, 4.50% at 50%) must not spare it."""
        names = _NAMES + ["Above 4.25%", "Above 4.50%"]
        book = _TEMPLATE + [(0.90, 0.25, 1.00), (0.50, 0.50, 1.00)]
        assert is_templated_flat_ladder(_rows(book, names), QUESTION) is True

    def test_fewer_than_three_rungs_is_not_judged(self):
        assert (
            is_templated_flat_ladder(_rows(_TEMPLATE[:2], _NAMES[:2]), QUESTION)
            is False
        )

    def test_an_unpriced_leading_rung_is_not_judged(self):
        book = list(_TEMPLATE)
        book[0] = (None, 0.60, 1.00)
        assert is_templated_flat_ladder(_rows(book), QUESTION) is False


def _fed_discover(book, market_id=FED):
    m = _Market(market_id)
    m.name = QUESTION
    m.category = m.llm_sport_category = "economics"
    m.outcomes = [
        _Outcome(i, n, p, change=0.0, opening=p, yes_bid=b, yes_ask=a)
        for i, n, (p, b, a) in zip(_IDS, _NAMES, book)
    ]
    return m


async def _discover_ids(markets) -> list:
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed.withheld_price_outcome_ids_for_markets",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )
    return [i["data"]["id"] for i in items if i["type"] == "futures"]


class TestDiscoverServesNoCardForATemplatedLadder:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        assert await _discover_ids([_fed_discover(_TEMPLATE)]) == []

    @pytest.mark.asyncio
    async def test_control_the_same_ladder_traded_flat_is_served(self):
        """Without this arm the treatment passes on any change that drops the card."""
        assert await _discover_ids([_fed_discover(_TRADED_FLAT)]) == [FED]

    @pytest.mark.asyncio
    async def test_control_the_same_ladder_untraded_but_falling_is_served(self):
        assert await _discover_ids([_fed_discover(_UNTRADED_FALLING)]) == [FED]

    @pytest.mark.asyncio
    async def test_the_omitted_card_does_not_take_its_neighbour(self):
        assert await _discover_ids([_fed_discover(_TEMPLATE), _Market(1)]) == [1]


def _fed_sports(book):
    legs = []
    for i, n, (p, b, a) in zip(_IDS, _NAMES, book):
        leg = _SportsLeg(i, n, p)
        leg.current_yes_bid = b
        leg.current_yes_ask = a
        legs.append(leg)
    return _SportsBoard(FED, QUESTION, legs)


async def _sports_ids(markets) -> list:
    cards = await _serve_sports(markets, {})
    return [c["data"]["id"] for c in cards]


class TestSportsServesNoCardForATemplatedLadder:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        assert await _sports_ids([_fed_sports(_TEMPLATE)]) == []

    @pytest.mark.asyncio
    async def test_control_the_same_ladder_traded_flat_is_served(self):
        assert await _sports_ids([_fed_sports(_TRADED_FLAT)]) == [FED]

    @pytest.mark.asyncio
    async def test_control_the_same_ladder_untraded_but_falling_is_served(self):
        assert await _sports_ids([_fed_sports(_UNTRADED_FALLING)]) == [FED]
