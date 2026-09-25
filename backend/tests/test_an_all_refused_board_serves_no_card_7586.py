"""#7586 — a board whose detail page refuses EVERY price leg serves no card.

Production, 2026-09-25 08:36Z (1:36 AM PDT), one specimen read on both surfaces:

    /api/feed (offset 50, index 29)  "New favorite: Valentin Vacherot (49%) now leads
                                      ATP Chengdu Winner" · Davidovich Fokina 39% ·
                                      Van de Zandschulp 39%
    /api/futures/62228710            prices_withheld: 16 of outcome_count: 16,
                                      every leg probability: null
    the page                         "No current prices for this market."

`_drop_withheld_price_legs` ended in `return survivors or outcomes`, so a board
with no survivors kept every leg: #7632's Seoul shape getting back in through
that one clause. The repair returns the empty list and both serializers skip
the card. Every assertion here is on a serializer's OUTPUT, the drop's return
value, or (the last class) WHERE the card leaves. A source-order check cannot
tell a live filter from a dead one (CERT-3330).

Controls, the arms that make the treatment mean something: 15 of 16 refused
keeps the one survivor; `None` (the arms never ran) keeps every leg; `[]` keeps
every leg; a settled board keeps every leg; and a healthy neighbour of the
omitted card is still served.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.feed import _drop_withheld_price_legs, _score_futures
from app.utils.personalization import PersonalizationContext
from tests.test_card_and_page_share_the_withheld_set_7632 import (
    _serve_sports,
    _SportsBoard,
    _SportsLeg,
)
from tests.test_feed_score_futures_resilience import _Market, _mock_db, _Outcome

CHENGDU = 62228710

#: Sixteen legs, like the specimen. The prices are shaped so the board is an
#: ordinary card when nothing is refused (the no-refusal control proves it):
#: a real leader, a sum just under 1, and names that are not placeholders.
_NAMES = [
    "Valentin Vacherot",
    "Alejandro Davidovich Fokina",
    "Botic van de Zandschulp",
    "Lorenzo Musetti",
    "Tommy Paul",
    "Sebastian Korda",
    "Alex Michelsen",
    "Learner Tien",
    "Jakub Mensik",
    "Arthur Fils",
    "Tomas Machac",
    "Brandon Nakashima",
    "Juncheng Shang",
    "Yibing Wu",
    "Zhizhen Zhang",
    "Marin Cilic",
]
_PRICES = [0.30, 0.20, 0.15, 0.10] + [0.02] * 12
_IDS = [CHENGDU * 100 + i for i in range(16)]
_ALL = set(_IDS)
_ALL_BUT_THIRD = _ALL - {_IDS[2]}  # Van de Zandschulp is the one the page prices


def _drop_market(withheld, status="open"):
    legs = [SimpleNamespace(id=i, name=n) for i, n in zip(_IDS, _NAMES)]
    market = SimpleNamespace(id=CHENGDU, status=status)
    market.withheld_outcome_ids = None if withheld is None else sorted(withheld)
    return market, legs


# ── the drop ─────────────────────────────────────────────────────────────────


class TestTheDrop:
    def test_sixteen_of_sixteen_refused_leaves_no_survivors(self):
        market, legs = _drop_market(_ALL)
        assert _drop_withheld_price_legs(market, legs) == []

    def test_control_fifteen_of_sixteen_keeps_the_one_the_page_prices(self):
        market, legs = _drop_market(_ALL_BUT_THIRD)
        assert [o.name for o in _drop_withheld_price_legs(market, legs)] == [
            "Botic van de Zandschulp"
        ]

    def test_control_none_means_the_arms_never_ran_and_drops_nothing(self):
        market, legs = _drop_market(None)
        assert _drop_withheld_price_legs(market, legs) == legs

    def test_control_an_empty_known_set_drops_nothing(self):
        market, legs = _drop_market(set())
        assert _drop_withheld_price_legs(market, legs) == legs

    def test_control_a_settled_board_keeps_every_leg(self):
        """A settled board is a RESULT, even with every id on the list."""
        market, legs = _drop_market(_ALL, status="completed")
        assert _drop_withheld_price_legs(market, legs) == legs


# ── Discover: `_score_futures`, withheld set carried by the snapshot builder ──


def _chengdu_discover(market_id=CHENGDU):
    m = _Market(market_id)
    m.name = "ATP Chengdu Winner"
    m.category = m.llm_sport_category = "tennis"
    m.outcomes = [
        _Outcome(i, n, p, change=0.0, opening=p)
        for i, n, p in zip(_IDS, _NAMES, _PRICES)
    ]
    return m


async def _discover_ids(markets, withheld_by_market) -> list:
    """Discover's serializer, with the builder's answer pinned.

    The set is handed to the REAL snapshot path (`to_plain(withheld_by_market=)`
    then `from_plain`), which is how production's carrier gets it. Stamping the
    attribute on the fixture would skip the half CERT-3330 was about.
    """
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed.withheld_price_outcome_ids_for_markets",
            new=AsyncMock(return_value=withheld_by_market),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db(markets), datetime.now(timezone.utc), None, PersonalizationContext()
        )
    return [i for i in items if i["type"] == "futures"]


def _names(card) -> list:
    return [o["name"] for o in card["data"].get("top_outcomes") or []]


class TestDiscoverServesNoCardForAnAllRefusedBoard:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        cards = await _discover_ids([_chengdu_discover()], {CHENGDU: set(_ALL)})
        assert [c["data"]["id"] for c in cards] == []

    @pytest.mark.asyncio
    async def test_control_the_same_board_is_served_when_nothing_is_refused(self):
        """Without this arm the treatment passes on any change that drops the card."""
        cards = await _discover_ids([_chengdu_discover()], {CHENGDU: set()})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert _names(cards[0])[0] == "Valentin Vacherot"

    @pytest.mark.asyncio
    async def test_control_fifteen_refused_serves_the_one_priced_leg(self):
        cards = await _discover_ids([_chengdu_discover()], {CHENGDU: set(_ALL_BUT_THIRD)})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert _names(cards[0]) == ["Botic van de Zandschulp"]

    @pytest.mark.asyncio
    async def test_control_a_board_the_builder_omitted_keeps_its_card(self):
        """Absent from the map = `None` = the arms never ran: served whole."""
        cards = await _discover_ids([_chengdu_discover()], {})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert "Valentin Vacherot" in _names(cards[0])

    @pytest.mark.asyncio
    async def test_the_omitted_card_does_not_take_its_neighbour(self):
        """Gotcha #42's shape: one board leaving never empties the pass."""
        cards = await _discover_ids(
            [_chengdu_discover(), _Market(1)], {CHENGDU: set(_ALL), 1: set()}
        )
        assert [c["data"]["id"] for c in cards] == [1]


# ── Sports mode: `_score_sports_mode_futures`, withheld set passed explicitly ─


def _chengdu_sports():
    return _SportsBoard(
        CHENGDU,
        "ATP Chengdu Winner",
        [_SportsLeg(i, n, p) for i, n, p in zip(_IDS, _NAMES, _PRICES)],
    )


class TestSportsServesNoCardForAnAllRefusedBoard:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_not_served(self):
        cards = await _serve_sports([_chengdu_sports()], {CHENGDU: set(_ALL)})
        assert [c["data"]["id"] for c in cards] == []

    @pytest.mark.asyncio
    async def test_control_the_same_board_is_served_when_nothing_is_refused(self):
        cards = await _serve_sports([_chengdu_sports()], {CHENGDU: set()})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert _names(cards[0])[0] == "Valentin Vacherot"

    @pytest.mark.asyncio
    async def test_control_fifteen_refused_serves_the_one_priced_leg(self):
        cards = await _serve_sports([_chengdu_sports()], {CHENGDU: set(_ALL_BUT_THIRD)})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert _names(cards[0]) == ["Botic van de Zandschulp"]

    @pytest.mark.asyncio
    async def test_control_a_board_the_builder_omitted_keeps_its_card(self):
        cards = await _serve_sports([_chengdu_sports()], {})
        assert [c["data"]["id"] for c in cards] == [CHENGDU]
        assert "Valentin Vacherot" in _names(cards[0])


# ── WHERE the card leaves: before the ranking, not by falling through it ─────


class TestTheCardLeavesBeforeTheRanking:
    """Without the serializers' `continue`, an emptied board still does not
    reach the feed: it falls through the leader pick and outcome list with
    nothing in them, and a late `if not probs_available` skip drops it in Sports
    mode (Discover has an equivalent late drop). Every output assertion above
    passes either way. Mutation-measured: removing either `continue` left all
    output tests green.

    The scope ruling (#7586, Codex comment 5829621819) asks for omission BEFORE
    leader, ranking and divisor construction, and never as a by-product of a
    later path. So these pin WHERE it leaves: `ladder_treatment_collapsed` is
    the first ranking step after the drop in both serializers, and an all-refused
    board must never reach it. The no-refusal control proves the spy sees this
    board when it is served.
    """

    @staticmethod
    def _spy():
        import app.routes.feed as feed_module

        real = feed_module.ladder_treatment_collapsed
        seen = []

        def spy(outcomes, name_fn, prob_fn, market_name, *a, **k):
            seen.append(market_name)
            return real(outcomes, name_fn, prob_fn, market_name, *a, **k)

        return seen, patch("app.routes.feed.ladder_treatment_collapsed", side_effect=spy)

    @pytest.mark.asyncio
    async def test_discover_never_ranks_an_all_refused_board(self):
        seen, p = self._spy()
        with p:
            await _discover_ids([_chengdu_discover()], {CHENGDU: set(_ALL)})
        assert "ATP Chengdu Winner" not in seen

    @pytest.mark.asyncio
    async def test_sports_never_ranks_an_all_refused_board(self):
        seen, p = self._spy()
        with p:
            await _serve_sports([_chengdu_sports()], {CHENGDU: set(_ALL)})
        assert "ATP Chengdu Winner" not in seen

    @pytest.mark.asyncio
    async def test_control_the_spy_sees_the_board_when_it_is_served(self):
        seen, p = self._spy()
        with p:
            await _discover_ids([_chengdu_discover()], {CHENGDU: set()})
            await _serve_sports([_chengdu_sports()], {CHENGDU: set()})
        assert seen.count("ATP Chengdu Winner") == 2
