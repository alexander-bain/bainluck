"""#11493 — the Division Winner card stops printing an eliminated division at "<1%".

Production, 2026-10-23 07:17Z (main v5887): the Discover card "MLB 2026: World
Series Division Winner" (polymarket 63448360) read NL Central 63% · AL East 37%
· AL Central <1%. ``/api/playoffs/mlb`` marked all five AL Central clubs
``championship: eliminated``; the venue had graded NL East, AL West and NL
West ``is_winner false`` (no price, off the card) but not AL Central, which kept
its last quote of 0.0005.

Both feed serializers now read the grid's CACHED payload once per build and
drop a division leg whose every club is out, exactly as the graded divisions
already leave. Assertions are on the reader's output, the drop's output and the
two serializers' served ``top_outcomes`` — never on source text.

Fixtures are the production rows: the grid's (conference, division, title
state) counts at 08:01Z and the board's six legs at 08:15Z.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.feed import _score_futures, _score_sports_mode_futures
from app.utils import grid_out_division_legs as mod
from app.utils.personalization import PersonalizationContext
from app.utils.request_cache import MISS, OK, TIMEOUT, RedisResult
from tests.test_card_and_page_share_the_withheld_set_7632 import (
    _SportsBoard,
    _SportsLeg,
    _sports_db,
)
from tests.test_feed_score_futures_resilience import _Market, _mock_db, _Outcome

BOARD = 63448360
KEY = "baseball:MLB:division_winner:2026"
NAME = "MLB 2026: World Series Division Winner"

#: `/api/playoffs/mlb` at 08:01Z: (conference, division) → title states. Five
#: clubs per division; the Brewers (NL Central) and Rays (AL East) are live.
_AL, _NL = "American League", "National League"
_DIVISIONS = {
    (_NL, "Central"): ["live"] + ["eliminated"] * 4,
    (_AL, "East"): ["live"] + ["eliminated"] * 4,
    (_AL, "Central"): ["eliminated"] * 5,
    (_AL, "West"): ["eliminated"] * 5,
    (_NL, "East"): ["eliminated"] * 5,
    (_NL, "West"): ["eliminated"] * 5,
}


def _row(i, conference, division, state):
    return {
        "name": f"Club {i}",
        "team_id": 10000 + i,
        "conference": conference,
        "division": division,
        "cells": {
            "championship": {"merged_probability": None, "sources": [], "state": state}
        },
    }


def _grid(season="2026", extra=(), divisions=None):
    rows, i = [], 0
    for (conference, division), states in (divisions or _DIVISIONS).items():
        for state in states:
            rows.append(_row(i, conference, division, state))
            i += 1
    return {"league": "mlb", "season": season, "teams": rows + list(extra)}


#: The board's legs as served at 08:15Z: (name, price, opening). Graded legs
#: carry no price. The openings are load-bearing: with two priced survivors the
#: scorer's soft-settled two-way gate reads the leader's opening, and the served
#: board's (18%) is far from the 50% that gate needs.
_LEGS = [
    ("NL Central", 0.63, 0.18),
    ("AL East", 0.36, 0.24),
    ("AL Central", 0.0005, 0.13),
    ("NL East", None, 0.095),
    ("AL West", None, 0.06),
    ("NL West", None, 0.19),
]


# ── the reader ───────────────────────────────────────────────────────────────


class TestOutDivisionLabels:
    def test_the_production_grid_puts_four_divisions_out(self):
        assert mod.out_division_labels(_grid(), "2026") == {
            "al central",
            "al west",
            "nl east",
            "nl west",
        }

    def test_control_a_division_with_one_live_club_is_not_out(self):
        labels = mod.out_division_labels(_grid(), "2026")
        assert "nl central" not in labels and "al east" not in labels

    def test_the_registers_lost_counts_as_out(self):
        divisions = dict(_DIVISIONS)
        divisions[(_AL, "Central")] = ["lost"] * 2 + ["eliminated"] * 3
        assert "al central" in mod.out_division_labels(
            _grid(divisions=divisions), "2026"
        )

    def test_a_different_season_drops_nothing(self):
        assert mod.out_division_labels(_grid(season="2025"), "2026") == frozenset()

    def test_a_grid_with_no_season_drops_nothing(self):
        assert mod.out_division_labels(_grid(season=None), "2026") == frozenset()

    def test_a_live_club_with_no_division_drops_nothing(self):
        """It could sit in any division, so none can be called out."""
        stray = _row(99, _AL, None, "live")
        assert mod.out_division_labels(_grid(extra=[stray]), "2026") == frozenset()

    def test_control_an_out_club_with_no_division_is_ignored(self):
        stray = _row(99, None, None, "eliminated")
        assert "al central" in mod.out_division_labels(_grid(extra=[stray]), "2026")

    def test_every_division_out_is_a_broken_payload_and_drops_nothing(self):
        divisions = {k: ["eliminated"] * 5 for k in _DIVISIONS}
        assert (
            mod.out_division_labels(_grid(divisions=divisions), "2026") == frozenset()
        )

    def test_a_missing_payload_drops_nothing(self):
        assert mod.out_division_labels(None, "2026") == frozenset()


class TestWhichBoard:
    def _market(self, **kw):
        base = {
            "id": BOARD,
            "status": "open",
            "canonical_market_key": KEY,
            "name": NAME,
        }
        return SimpleNamespace(**{**base, **kw})

    def test_the_specimen_board_is_read(self):
        assert mod.division_of_champion_season(self._market()) == "2026"

    def test_a_per_division_board_is_not(self):
        m = self._market(
            canonical_market_key="hockey:NHL:division_winner:2026-27",
            name="NHL: 2026-27 Atlantic Division Winner",
        )
        assert mod.division_of_champion_season(m) is None

    def test_an_mlb_division_board_that_is_not_about_the_champion_is_not(self):
        m = self._market(name="AL East Division Winner")
        assert mod.division_of_champion_season(m) is None

    def test_a_settled_board_is_a_result_and_is_not(self):
        assert mod.division_of_champion_season(self._market(status="settled")) is None


class TestTheDrop:
    def test_the_out_label_leaves_case_and_space_insensitively(self):
        legs = [
            SimpleNamespace(name=n) for n in ("NL Central", " al  CENTRAL ", "AL East")
        ]
        kept = mod.drop_out_division_legs(legs, frozenset({"al central"}))
        assert [o.name for o in kept] == ["NL Central", "AL East"]

    def test_control_no_labels_keeps_the_same_list(self):
        legs = [SimpleNamespace(name="AL Central")]
        assert mod.drop_out_division_legs(legs, None) is legs


# ── cache-only read, fails open ──────────────────────────────────────────────


class _FakeRedis:
    def __init__(self, values):
        self.values = values
        self.asked = []

    async def get(self, key):
        self.asked.append(key)
        return self.values.get(key)


async def _read(values=None, results=None):
    client = _FakeRedis(values or {})

    async def bounded(factory, **_):
        if results is not None:
            return results.pop(0)
        value = await factory()
        return RedisResult(status=MISS if value is None else OK, value=value)

    with (
        patch(
            "app.utils.request_cache.get_shared_async_redis",
            new=AsyncMock(return_value=client),
        ),
        patch("app.utils.request_cache.bounded_redis_call", new=bounded),
    ):
        return await mod.read_cached_grid("mlb"), client.asked


class TestReadCachedGrid:
    KEY = "bainluck:category:playoffs:mlb"

    @pytest.mark.asyncio
    async def test_the_fresh_key_answers(self):
        payload, asked = await _read({self.KEY: json.dumps(_grid())})
        assert payload["season"] == "2026" and asked == [self.KEY]

    @pytest.mark.asyncio
    async def test_a_clean_miss_falls_to_the_stale_mirror(self):
        payload, asked = await _read({f"{self.KEY}:stale": json.dumps(_grid())})
        assert payload["season"] == "2026" and asked == [self.KEY, f"{self.KEY}:stale"]

    @pytest.mark.asyncio
    async def test_a_timeout_stops_at_once(self):
        payload, _ = await _read(results=[RedisResult(status=TIMEOUT)])
        assert payload is None

    @pytest.mark.asyncio
    async def test_an_empty_grid_is_not_usable(self):
        empty = json.dumps({"season": "2026", "teams": []})
        payload, _ = await _read({self.KEY: empty, f"{self.KEY}:stale": empty})
        assert payload is None


class TestOutLegsByMarket:
    @pytest.mark.asyncio
    async def test_a_pool_without_the_board_never_reads_redis(self):
        read = AsyncMock(return_value=_grid())
        with patch.object(mod, "read_cached_grid", new=read):
            assert await mod.out_legs_by_market([_Market(1)]) == {}
        read.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_reader_error_keeps_every_leg(self):
        with patch.object(
            mod, "read_cached_grid", new=AsyncMock(side_effect=RuntimeError)
        ):
            assert await mod.out_legs_by_market([_discover_board()]) == {}


# ── Discover and Sports serve the card without the out division ──────────────


def _discover_board():
    m = _Market(BOARD)
    m.name = NAME
    m.canonical_market_key = KEY
    m.category = "championship"
    m.llm_sport_category = "baseball"
    m.outcomes = [
        _Outcome(BOARD * 10 + i, n, p, opening=op) for i, (n, p, op) in enumerate(_LEGS)
    ]
    for o in m.outcomes:
        o.is_winner = False if o.current_probability is None else None
    return m


async def _discover_card(payload):
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
        patch.object(mod, "read_cached_grid", new=AsyncMock(return_value=payload)),
    ):
        items = await _score_futures(
            _mock_db([_discover_board()]),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )
    cards = [i for i in items if i["type"] == "futures" and i["data"]["id"] == BOARD]
    assert len(cards) == 1
    return [o["name"] for o in cards[0]["data"].get("top_outcomes") or []]


def _sports_board():
    legs = []
    for i, (n, p, op) in enumerate(_LEGS):
        leg = _SportsLeg(BOARD * 10 + i, n, p)
        leg.opening_probability = op
        leg.is_winner = False if p is None else None
        legs.append(leg)
    board = _SportsBoard(BOARD, NAME, legs)
    board.canonical_market_key = KEY
    board.llm_sport_category = "baseball"
    return board


async def _sports_card(payload):
    with (
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={KEY: 1}),
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
        patch.object(mod, "read_cached_grid", new=AsyncMock(return_value=payload)),
    ):
        items = await _score_sports_mode_futures(
            _sports_db([_sports_board()]),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )
    cards = [i for i in items if i["type"] == "futures" and i["data"]["id"] == BOARD]
    assert len(cards) == 1
    return [o["name"] for o in cards[0]["data"].get("top_outcomes") or []]


class TestDiscoverCard:
    @pytest.mark.asyncio
    async def test_the_out_division_is_not_on_the_card(self):
        names = await _discover_card(_grid())
        assert "AL Central" not in names
        assert names[:2] == ["NL Central", "AL East"]

    @pytest.mark.asyncio
    async def test_control_a_cache_miss_serves_todays_card(self):
        """Without this arm the treatment passes on any change that drops the leg."""
        assert "AL Central" in await _discover_card(None)

    @pytest.mark.asyncio
    async def test_control_last_seasons_grid_serves_todays_card(self):
        assert "AL Central" in await _discover_card(_grid(season="2025"))


class TestSportsCard:
    @pytest.mark.asyncio
    async def test_the_out_division_is_not_on_the_card(self):
        names = await _sports_card(_grid())
        assert "AL Central" not in names
        assert names[:2] == ["NL Central", "AL East"]

    @pytest.mark.asyncio
    async def test_control_a_cache_miss_serves_todays_card(self):
        assert "AL Central" in await _sports_card(None)
