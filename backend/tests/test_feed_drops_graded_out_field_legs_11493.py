"""#11493 — the World Series card stops giving the eliminated Astros a 1% chance.

Production, 2026-10-23 10:44Z: ``/api/feed?tags=["sport:baseball"]`` served
polymarket 114584 "MLB World Series Champion 2026" (``status open``, field) as
Brewers 64% · Rays 37% · Houston Astros 1%. The card feeds Discover, the futures
page's "More baseball" rail and the app. The Astros row is stored
``is_winner false`` + ``resolution_source 'api_settlement'`` at 0.005; the two
clubs still playing carry ``resolution_source NULL``.

The grade is read by the production statement against real rows (sqlite, the
repo's `_AsyncShim` shape — no aiosqlite here), and both serializers run with
that reader wired in. Assertions are on the reader's ids and the served
``top_outcomes``, each treatment paired with a control that serves today's card.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesOutcome  # noqa: E402
from app.routes.feed import _score_futures, _score_sports_mode_futures  # noqa: E402
from app.utils import graded_out_field_legs as mod  # noqa: E402
from app.utils.personalization import PersonalizationContext  # noqa: E402
from tests.test_card_and_page_share_the_withheld_set_7632 import (  # noqa: E402
    _SportsBoard,
    _SportsLeg,
    _sports_db,
)
from tests.test_feed_score_futures_resilience import (  # noqa: E402
    _Market,
    _mock_db,
    _Outcome,
)

BOARD = 114584
NAME = "MLB World Series Champion 2026"

#: 114584's top legs as stored at 10:50Z: (id, name, price, is_winner, source).
_LEGS = [
    (1634478, "Milwaukee Brewers", 0.6395, False, None),
    (1634488, "Tampa Bay Rays", 0.3655, False, None),
    (1634474, "Houston Astros", 0.005, False, "api_settlement"),
    (1634486, "Arizona Diamondbacks", 0.005, False, "api_settlement"),
    (1634467, "New York Yankees", 0.004, False, "api_settlement"),
    (1634470, "San Diego Padres", 0.004, False, "api_settlement"),
]
#: Their stored openings. The Brewers' 0.0225 is load-bearing: a two-leg card
#: whose leader opened at 50%+ and has not moved is skipped as a foregone binary.
_OPENING = {
    1634478: 0.0225,
    1634488: 0.005,
    1634474: 0.0445,
    1634486: 0.0065,
    1634467: 0.075,
    1634470: 0.0515,
}
_OUT = {1634486, 1634474, 1634467, 1634470}
_OUT_NAMES = {n for i, n, *_ in _LEGS if i in _OUT}
_ALIVE = ["Milwaukee Brewers", "Tampa Bay Rays"]


class _AsyncShim:
    """Async surface over a real sync session; the statement is production's."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement):
        return self._s.execute(statement)


def _graded_db(legs=_LEGS):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FuturesOutcome.__table__])
    s = Session(engine, expire_on_commit=False)
    for leg_id, name, price, is_winner, source in legs:
        s.add(
            FuturesOutcome(
                id=leg_id,
                market_id=BOARD,
                external_id=f"pm-{leg_id}",
                name=name,
                current_probability=price,
                is_winner=is_winner,
                resolution_source=source,
            )
        )
    s.commit()
    return _AsyncShim(s)


def _with_source(source):
    return [(i, n, p, w, source if s else None) for i, n, p, w, s in _LEGS]


def _discover_board(*, status="open", market_type="field", legs=_LEGS):
    m = _Market(BOARD)
    m.name = NAME
    m.category = "championship"
    m.llm_sport_category = "baseball"
    m.status = status
    m.market_type = market_type
    # The cached path's leg: no `is_winner` / `resolution_source` attribute.
    m.outcomes = [_Outcome(i, n, p, opening=_OPENING[i]) for i, n, p, _w, _s in legs]
    return m


def _sports_board(*, market_type="field", legs=_LEGS):
    out = []
    for leg_id, name, price, is_winner, source in legs:
        leg = _SportsLeg(leg_id, name, price)
        leg.opening_probability = _OPENING[leg_id]
        leg.is_winner, leg.resolution_source = is_winner, source
        out.append(leg)
    board = _SportsBoard(BOARD, NAME, out)
    board.canonical_market_key = None
    board.llm_sport_category = "baseball"
    board.market_type = market_type
    return board


def _reader_on(graded):
    async def read(_db, markets):
        return await mod.graded_out_leg_ids_by_market(graded, markets)

    return read


def _todays_card(names):
    """Three legs, the third one a club the venue has graded out."""
    return names[:2] == _ALIVE and len(names) == 3 and names[2] in _OUT_NAMES


def _names(items):
    cards = [i for i in items if i["type"] == "futures" and i["data"]["id"] == BOARD]
    assert len(cards) == 1
    return [o["name"] for o in cards[0]["data"].get("top_outcomes") or []]


async def _discover_card(board, graded):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.routes.feed.withheld_price_outcome_ids_for_markets",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
        patch("app.routes.feed.out_legs_by_market", new=AsyncMock(return_value={})),
        patch("app.routes.feed.graded_out_leg_ids_by_market", new=_reader_on(graded)),
    ):
        items = await _score_futures(
            _mock_db([board]),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )
    return _names(items)


async def _sports_card(board, graded):
    with (
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.feed._team_names_by_id", new=AsyncMock(return_value={})),
        patch(
            "app.routes.feed.withheld_price_outcome_ids_for_markets",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
        patch("app.routes.feed.out_legs_by_market", new=AsyncMock(return_value={})),
        patch("app.routes.feed.graded_out_leg_ids_by_market", new=_reader_on(graded)),
    ):
        items = await _score_sports_mode_futures(
            _sports_db([board]),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )
    return _names(items)


# ── the reader ───────────────────────────────────────────────────────────────


def _read(board, graded):
    return asyncio.run(mod.graded_out_leg_ids_by_market(graded, [board]))


class TestTheReader:
    def test_the_authoritatively_graded_legs_are_out(self):
        assert _read(_discover_board(), _graded_db()) == {BOARD: frozenset(_OUT)}

    def test_a_defaulted_false_is_not_a_grade(self):
        assert _read(_discover_board(), _graded_db(_with_source(None))) == {}

    def test_a_graded_winner_is_not_out(self):
        legs = [(i, n, p, True if s else w, s) for i, n, p, w, s in _LEGS]
        assert _read(_discover_board(legs=legs), _graded_db(legs)) == {}

    def test_the_retraction_is_not_a_grade(self):
        graded = _graded_db(_with_source("ungradeable_result"))
        assert _read(_discover_board(), graded) == {}

    def test_a_guess_is_not_a_grade(self):
        assert _read(_discover_board(), _graded_db(_with_source("llm_guess"))) == {}

    def test_a_live_contender_keeps_its_price(self):
        legs = [(i, n, 0.25 if s else p, w, s) for i, n, p, w, s in _LEGS]
        assert _read(_discover_board(legs=legs), _graded_db(legs)) == {}

    def test_only_an_open_board(self):
        assert _read(_discover_board(status="resolved"), _graded_db()) == {}

    def test_only_a_field(self):
        assert _read(_discover_board(market_type="claim"), _graded_db()) == {}
        assert _read(_discover_board(market_type=None), _graded_db()) == {}

    def test_a_pool_wider_than_one_select_is_read_whole(self):
        with patch.object(mod, "CHUNK", 1):
            assert _read(_discover_board(), _graded_db()) == {BOARD: frozenset(_OUT)}

    def test_a_failed_read_drops_nothing(self):
        broken = AsyncMock()
        broken.execute = AsyncMock(side_effect=RuntimeError("db gone"))
        assert _read(_discover_board(), broken) == {}


class TestTheDrop:
    def test_drops_the_out_ids(self):
        legs = _discover_board().outcomes
        kept = mod.drop_graded_out_legs(legs, frozenset(_OUT))
        assert [o.name for o in kept] == _ALIVE

    def test_nothing_to_drop_is_identity(self):
        legs = _discover_board().outcomes
        assert mod.drop_graded_out_legs(legs, None) is legs
        assert mod.drop_graded_out_legs(legs, frozenset()) is legs

    def test_a_verdict_that_empties_the_card_keeps_every_leg(self):
        legs = _discover_board().outcomes
        every = frozenset(o.id for o in legs)
        assert mod.drop_graded_out_legs(legs, every) is legs


# ── Discover (cached legs, no grade on them) and Sports serve the live card ──


class TestDiscoverCard:
    @pytest.mark.asyncio
    async def test_the_astros_are_not_on_the_card(self):
        assert await _discover_card(_discover_board(), _graded_db()) == _ALIVE

    @pytest.mark.asyncio
    async def test_control_ungraded_legs_serve_todays_card(self):
        """Without this arm the treatment passes on any change that drops the leg."""
        names = await _discover_card(_discover_board(), _graded_db(_with_source(None)))
        assert _todays_card(names), names

    @pytest.mark.asyncio
    async def test_control_a_non_field_board_serves_todays_card(self):
        names = await _discover_card(_discover_board(market_type=None), _graded_db())
        assert _todays_card(names), names


class TestSportsCard:
    @pytest.mark.asyncio
    async def test_the_astros_are_not_on_the_card(self):
        assert await _sports_card(_sports_board(), _graded_db()) == _ALIVE

    @pytest.mark.asyncio
    async def test_control_ungraded_legs_serve_todays_card(self):
        names = await _sports_card(_sports_board(), _graded_db(_with_source(None)))
        assert _todays_card(names), names
