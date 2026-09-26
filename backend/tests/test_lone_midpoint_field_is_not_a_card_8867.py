"""#8867 — a one-winner field whose ONLY price is a wide-book midpoint serves no card.

Production, 2026-09-26 16:40Z (9:40 AM PDT), Discover slot 13 at 390px:

    2027 Men's Rugby World Cup Winner
    80%  South Africa
    South Africa leads at 80%

Kalshi ``KXRUGBYWC-27``: South Africa bid 0.60 / ask 0.99, 312 contracts ever; the
other 23 teams have no bid, and we store no price for them. The 0.795 is one book's
midpoint and "leads" compares it with nothing.

Every serializer assertion is on OUTPUT. Each control breaks exactly one clause
and must still be served — the same lone leg on a tight book, the same field with
a second price, the same field the venue does not call exclusive — plus a healthy
neighbour that survives the omitted card (gotcha #42).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.feed_market_quality import is_lone_midpoint_field
from app.utils.personalization import PersonalizationContext
from tests.test_card_and_page_share_the_withheld_set_7632 import (
    _serve_sports,
    _SportsBoard,
    _SportsLeg,
)
from tests.test_feed_score_futures_resilience import _Market, _mock_db, _Outcome

RUGBY = 60473053
QUESTION = "2027 Men's Rugby World Cup Winner"
_NAMES = [
    "South Africa",
    "Ireland",
    "New Zealand",
    "France",
    "England",
    "Australia",
    "Argentina",
    "Scotland",
]
_IDS = [RUGBY * 100 + i for i in range(len(_NAMES))]
_UNPRICED = [(None, None, None)] * (len(_NAMES) - 1)

# The specimen's book, verbatim: bid 0.60 / ask 0.99, stored at its midpoint.
_SPECIMEN = [(0.795, 0.60, 0.99)] + _UNPRICED
# Control A — the same lone leg, but TRADED: a tight book, not a wide midpoint.
_TIGHT = [(0.795, 0.79, 0.80)] + _UNPRICED
# Control B — the same wide midpoint, but other teams are priced: a field. Two
# more, not one: a sports field with exactly two priced legs, a >=60% leader and
# no movement is `soft_settled_binary`'s, which would drop this control for a
# reason of its own.
_SECOND_PRICE = [
    (0.795, 0.60, 0.99),
    (0.12, 0.11, 0.13),
    (0.05, 0.04, 0.06),
] + _UNPRICED[2:]


class TestThePredicate:
    def test_the_specimen_is_a_lone_midpoint(self):
        assert is_lone_midpoint_field(_SPECIMEN, True) is True

    def test_a_tight_lone_leg_is_spared(self):
        assert is_lone_midpoint_field(_TIGHT, True) is False

    def test_a_second_price_is_spared(self):
        assert is_lone_midpoint_field(_SECOND_PRICE, True) is False

    @pytest.mark.parametrize("exclusive", [False, None])
    def test_a_field_not_known_exclusive_is_spared(self, exclusive):
        assert is_lone_midpoint_field(_SPECIMEN, exclusive) is False

    def test_a_one_leg_market_is_not_a_field(self):
        assert is_lone_midpoint_field(_SPECIMEN[:1], True) is False

    def test_a_zero_price_is_not_a_second_price(self):
        book = [(0.795, 0.60, 0.99), (0.0, 0.0, 0.03)] + _UNPRICED[1:]
        assert is_lone_midpoint_field(book, True) is True


def _rugby_discover(book, exclusive=True):
    m = _Market(RUGBY)
    m.name = QUESTION
    m.category = m.llm_sport_category = "rugby"
    m.mutually_exclusive = exclusive
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


class TestDiscoverServesNoCardForALoneMidpoint:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        assert await _discover_ids([_rugby_discover(_SPECIMEN)]) == []

    @pytest.mark.asyncio
    async def test_control_the_lone_leg_on_a_tight_book_is_served(self):
        """Without this arm the treatment passes on any change that drops the card."""
        assert await _discover_ids([_rugby_discover(_TIGHT)]) == [RUGBY]

    @pytest.mark.asyncio
    async def test_control_a_second_price_is_served(self):
        assert await _discover_ids([_rugby_discover(_SECOND_PRICE)]) == [RUGBY]

    @pytest.mark.asyncio
    async def test_control_a_field_not_called_exclusive_is_served(self):
        assert await _discover_ids([_rugby_discover(_SPECIMEN, None)]) == [RUGBY]

    @pytest.mark.asyncio
    async def test_the_omitted_card_does_not_take_its_neighbour(self):
        assert await _discover_ids([_rugby_discover(_SPECIMEN), _Market(1)]) == [1]


def _rugby_sports(book, exclusive=True):
    legs = []
    for i, n, (p, b, a) in zip(_IDS, _NAMES, book):
        leg = _SportsLeg(i, n, p)
        leg.current_yes_bid = b
        leg.current_yes_ask = a
        legs.append(leg)
    board = _SportsBoard(RUGBY, QUESTION, legs)
    board.mutually_exclusive = exclusive
    return board


async def _sports_ids(markets) -> list:
    cards = await _serve_sports(markets, {})
    return [c["data"]["id"] for c in cards]


class TestSportsServesNoCardForALoneMidpoint:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        assert await _sports_ids([_rugby_sports(_SPECIMEN)]) == []

    @pytest.mark.asyncio
    async def test_control_the_lone_leg_on_a_tight_book_is_served(self):
        assert await _sports_ids([_rugby_sports(_TIGHT)]) == [RUGBY]

    @pytest.mark.asyncio
    async def test_control_a_second_price_is_served(self):
        assert await _sports_ids([_rugby_sports(_SECOND_PRICE)]) == [RUGBY]

    @pytest.mark.asyncio
    async def test_control_a_field_not_called_exclusive_is_served(self):
        assert await _sports_ids([_rugby_sports(_SPECIMEN, None)]) == [RUGBY]
