"""#11251 — a championship grid's source markets are re-priced by id.

On 2026-10-19 the /playoffs/nfl Division column printed Jaguars 68% (P76 K61)
while Polymarket traded the AFC South at 69.5: seven of the eight Polymarket
division markets (2248388/89/91/92, 2279147/51/52) had not been written since
2026-10-16 16:37Z. No price path reached them. The sweep's value arm orders by
volume and its Polymarket wall ran out above them; the sunk-event rotation laps
far-dated rows about every 2.5 days. The grid is warmed hourly and nobody told
the sweep which markets it renders.

These tests pin the repair's two links:
1. the reader of a grid payload: every column's ``market_ids`` plus its
   headline ``market_id`` and the payload's ``championship_market_id``;
2. the producer: the hourly grid warm records those ids under
   ``playoffs:<slug>`` in the category-served hash the sweep's category-page
   arm already reads (#10320) — only for a grid it actually published, and
   never at the cost of the warm.
"""

from __future__ import annotations

import contextlib
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.utils import category_served_markets as csm


def _pcp_module():
    # `from app.tasks import precompute_category_pages` resolves to the Celery
    # TASK of that name, which shadows the module on the package.
    import importlib

    return importlib.import_module("app.tasks.precompute_category_pages")


#: The four columns `/api/playoffs/nfl` served at 2026-10-19 03:33Z, ids verbatim.
NFL_DIVISION_IDS = [
    53671, 53672, 53673, 53674, 53675, 53676, 53677, 53678,
    2248388, 2248389, 2248391, 2248392, 2248395, 2279147, 2279151, 2279152,
]
NFL_GRID = {
    "league": "nfl",
    "championship_market_id": 129037,
    "columns": [
        {"key": "make_playoffs", "market_id": 62679, "market_ids": [62679, 16630438]},
        {"key": "division", "market_id": 53675, "market_ids": NFL_DIVISION_IDS},
        {"key": "conference", "market_id": 129172,
         "market_ids": [31615, 31616, 129171, 129172]},
        {"key": "championship", "market_id": 129037,
         "market_ids": [40533, 86832, 129037]},
    ],
    # Cells carry source probabilities and no market id; team ids are not
    # market ids and must never be collected.
    "teams": [{"team_id": 564, "cells": {"division": {"sources": [
        {"source": "polymarket", "probability": 0.755}]}}}],
}


class _FakePipe:
    def __init__(self, store):
        self.store = store
        self.ops = []

    def hset(self, key, field, value):
        self.ops.append(("hset", key, field, value))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        for op in self.ops:
            if op[0] == "hset":
                self.store.setdefault(op[1], {})[op[2]] = op[3]
        self.ops = []


class _FakeRedis:
    def __init__(self):
        self.hashes: dict = {}
        self.strings: dict = {}

    def pipeline(self, transaction=True):
        return _FakePipe(self.hashes)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def setex(self, key, ttl, value):
        self.strings[key] = value


class _FakeCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


# --- 1. the reader -------------------------------------------------------------


class TestIdsInAGrid:
    def test_every_column_id_and_the_championship_id_deduped_in_order(self):
        ids = csm.market_ids_in_playoff_grid(NFL_GRID)
        expected = []
        for col in NFL_GRID["columns"]:
            for i in [col["market_id"], *col["market_ids"]]:
                if i not in expected:
                    expected.append(i)
        assert ids == expected
        # The specimen: the AFC South market frozen at 2026-10-16 16:37Z.
        assert 2248391 in ids
        assert set(NFL_DIVISION_IDS) <= set(ids)
        assert 564 not in ids  # a team id is not a market id

    def test_the_category_walker_cannot_read_this_shape(self):
        """Why the grid needs its own reader: `market_ids` is a list."""
        walked = csm.market_ids_in_category_payload(NFL_GRID)
        assert 2248391 not in walked
        assert 2248391 in csm.market_ids_in_playoff_grid(NFL_GRID)

    def test_bools_strings_zero_and_garbage_yield_nothing(self):
        payload = {
            "championship_market_id": True,
            "columns": [
                {"market_id": "2248391", "market_ids": [0, -4, False, "x", None, 7]},
                "not a column",
                {"market_ids": "not a list"},
            ],
        }
        assert csm.market_ids_in_playoff_grid(payload) == [7]
        for junk in (None, [], "grid", {"columns": "nope"}, {}):
            assert csm.market_ids_in_playoff_grid(junk) == []


# --- 2. the producer -----------------------------------------------------------


async def _warm(rc, grid_payload, leagues=("nfl",)):
    pcp = _pcp_module()
    grid = AsyncMock(return_value=grid_payload)
    with patch.object(pcp, "GRID_WARM_LEAGUES", list(leagues)), \
            patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
            patch("app.tasks.base.get_task_session", return_value=_FakeCM()), \
            patch.object(pcp, "_warm_season_answers", AsyncMock(return_value=None)), \
            patch("app.routes.playoffs.get_playoff_grid", grid):
        return await pcp._precompute_grids()


class TestTheGridWarmRecordsWhatItPublished:
    @pytest.mark.asyncio
    async def test_a_published_grid_records_its_market_ids(self):
        rc = _FakeRedis()
        warmed = await _warm(rc, NFL_GRID)

        assert warmed == ["nfl"]
        assert "bainluck:category:playoffs:nfl" in rc.strings
        entry = json.loads(rc.hashes[csm.CATEGORY_SERVED_MARKET_IDS_KEY]["playoffs:nfl"])
        assert entry["ids"] == csm.market_ids_in_playoff_grid(NFL_GRID)
        assert 2248391 in entry["ids"]

    @pytest.mark.asyncio
    async def test_the_sweeps_reader_sees_the_grid_beside_the_category_pages(self):
        rc = _FakeRedis()
        csm.record_category_served_market_ids(rc, "politics", [113061])
        await _warm(rc, NFL_GRID)

        with patch("app.tasks.redis_state.get_redis_client", lambda **_kw: rc):
            served = csm.category_served_market_ids()

        assert served.read_ok and served.pages == 2
        assert 113061 in served.ids
        assert set(NFL_DIVISION_IDS) <= set(served.ids)

    @pytest.mark.asyncio
    async def test_an_unusable_build_records_nothing(self):
        """The warm keeps last-good on an empty build; it must not publish ids
        for a grid it did not publish either. The old entry ages out instead."""
        rc = _FakeRedis()
        warmed = await _warm(rc, {"teams": [], "columns": []})

        assert warmed == []
        assert "playoffs:nfl" not in rc.hashes.get(csm.CATEGORY_SERVED_MARKET_IDS_KEY, {})

    @pytest.mark.asyncio
    async def test_a_failed_record_does_not_cost_the_league_its_warm(self):
        rc = _FakeRedis()
        rc.pipeline = lambda transaction=True: (_ for _ in ()).throw(
            ConnectionError("pipeline down")
        )
        warmed = await _warm(rc, NFL_GRID)

        assert warmed == ["nfl"]
        assert "bainluck:category:playoffs:nfl" in rc.strings
        assert "bainluck:category:playoffs:nfl:stale" in rc.strings

    @pytest.mark.asyncio
    async def test_a_raising_reader_does_not_cost_the_league_its_warm(self):
        rc = _FakeRedis()
        with patch(
            "app.utils.category_served_markets.market_ids_in_playoff_grid",
            side_effect=RuntimeError("boom"),
        ):
            warmed = await _warm(rc, NFL_GRID)
        assert warmed == ["nfl"]
        assert "bainluck:category:playoffs:nfl" in rc.strings
        assert "playoffs:nfl" not in rc.hashes.get(csm.CATEGORY_SERVED_MARKET_IDS_KEY, {})

    def test_the_page_name_is_namespaced_away_from_the_category_pages(self):
        assert csm.PLAYOFF_GRID_PAGE_PREFIX == "playoffs:"
        for page in ("politics", "economics", "entertainment", "weather"):
            assert not page.startswith(csm.PLAYOFF_GRID_PAGE_PREFIX)
