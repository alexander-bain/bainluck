"""#11493 — an eliminated club's team page carries the grid's "out" verdict.

Production, 2026-10-23 07:44Z (main v5888): ``/api/teams/atlanta-braves`` led
with ``championship_path[0]`` = market 114584 "MLB World Series Champion 2026"
at 0.001 and no state — the page said CHAMPIONSHIP <1% — while
``/api/playoffs/mlb`` marked the same club ``championship: eliminated``. The
eliminated leg keeps trading at 0.001 until the venue grades the series, so no
price can say "out"; the verdict lives only in the grid build.

The page now reads that verdict from the grid's CACHED payload (never building
it — a cold build is ~12 s) and stamps it as ``state`` on each path step and on
each futures row whose market the decided column lists. Probabilities are left
untouched, so a client that has not learned ``state`` renders what it always
did; ux (web) and native (iOS) render it as out.

Fixtures are the production rows, verbatim where they matter: the Braves' grid
row (team_id 11626), the MLB columns' ``market_ids``, and the two futures rows
that could otherwise lead the page — 114584 (the title) and 206639 "MLB: 2026
NL Hank Aaron Winner", an award filed at market_tier 1.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.routes import teams as route
from app.utils import request_cache
from app.utils.request_cache import RedisResult, TIMEOUT

BRAVES = 11626
NOW = datetime(2026, 10, 23, 7, 44, tzinfo=timezone.utc)

#: `/api/playoffs/mlb` columns, 07:44Z (market_ids verbatim).
MLB_COLUMNS = [
    {"key": "make_playoffs", "market_ids": [266]},
    {"key": "division", "market_ids": [267, 268, 269, 271, 272, 273]},
    {"key": "pennant", "market_ids": [270, 274]},
    {"key": "championship", "market_ids": [1, 275, 114584]},
]


def _cells(**states):
    return {
        key: {"merged_probability": None, "sources": [], "trend_24h": None, "state": state}
        for key, state in states.items()
    }


def _grid(*rows, season="2026"):
    return {"league": "mlb", "season": season, "columns": MLB_COLUMNS, "teams": list(rows)}


#: The Braves' grid row as served: won the NL East, out in the NLCS.
BRAVES_ROW = {
    "name": "Atlanta Braves",
    "team_id": BRAVES,
    "cells": _cells(
        make_playoffs="won", division="won", pennant="eliminated", championship="eliminated"
    ),
}
#: A club still playing — its title cell is live.
BREWERS_ROW = {
    "name": "Milwaukee Brewers",
    "team_id": 10735,
    "cells": _cells(make_playoffs="won", division="won", pennant="won", championship="live"),
}


def _path():
    return [
        {
            "tier": 1,
            "label": "Championship",
            "market_name": "MLB World Series Champion 2026",
            "market_id": 114584,
            "probability": 0.001,
            "rank": 10,
            "movement": None,
            "season": "2026",
        }
    ]


def _futures():
    return [
        {"market_id": 114584, "market_name": "MLB World Series Champion 2026",
         "market_tier": 1, "probability": 0.001, "is_winner": False},
        {"market_id": 206639, "market_name": "MLB: 2026 NL Hank Aaron Winner",
         "market_tier": 1, "probability": 0.001, "is_winner": False},
        {"market_id": 55674290, "market_name": "Silver Slugger: NL Team",
         "market_tier": 5, "probability": 0.97, "is_winner": False},
    ]


def _stamp(grid, club_ids=(BRAVES,), season="2026", path=None, futures=None):
    path = _path() if path is None else path
    futures = _futures() if futures is None else futures
    route._stamp_grid_states(path, futures, route._grid_decided_columns(grid, club_ids, season))
    return path, futures


# ─── The production specimen ─────────────────────────────────────────────────


class TestTheBravesPageReadsOut:
    def test_the_title_step_carries_the_grids_eliminated(self):
        path, _ = _stamp(_grid(BREWERS_ROW, BRAVES_ROW))
        assert path[0]["state"] == "eliminated"

    def test_the_title_futures_row_carries_it_too(self):
        # web's `teamHeadline` falls back to `pickJourneyFuture(futures)` — that
        # fallback can reach the same 114584 row, so the row says out as well.
        _, futures = _stamp(_grid(BREWERS_ROW, BRAVES_ROW))
        by_id = {f["market_id"]: f for f in futures}
        assert by_id[114584]["state"] == "eliminated"

    def test_an_award_filed_at_tier_one_is_not_handed_the_titles_verdict(self):
        _, futures = _stamp(_grid(BREWERS_ROW, BRAVES_ROW))
        by_id = {f["market_id"]: f for f in futures}
        assert "state" not in by_id[206639]
        assert "state" not in by_id[55674290]

    def test_no_probability_moves(self):
        before_path, before_futures = _path(), _futures()
        path, futures = _stamp(_grid(BREWERS_ROW, BRAVES_ROW))
        for got, want in zip(path, before_path):
            assert got["probability"] == want["probability"]
        for got, want in zip(futures, before_futures):
            assert got["probability"] == want["probability"]
        # ...and nothing but `state` was added.
        assert {k: v for k, v in path[0].items() if k != "state"} == before_path[0]

    def test_a_club_still_playing_gets_no_state(self):
        path, futures = _stamp(_grid(BREWERS_ROW, BRAVES_ROW), club_ids=(10735,))
        assert "state" not in path[0]
        assert all("state" not in f for f in futures)


# ─── Strawman: the stamp is what makes the difference ────────────────────────


def test_strawman_without_the_stamp_the_page_still_reads_a_price():
    """The unrepaired payload, for contrast: a number and no verdict."""
    path, futures = _path(), _futures()
    assert path[0]["probability"] == 0.001 and "state" not in path[0]
    assert all("state" not in f for f in futures)


# ─── Fails to today's answer ─────────────────────────────────────────────────


class TestFailsOpen:
    def test_no_payload(self):
        path, futures = _stamp(None)
        assert "state" not in path[0] and all("state" not in f for f in futures)

    def test_a_previous_seasons_grid_never_marks_this_seasons_page(self):
        path, futures = _stamp(_grid(BRAVES_ROW, season="2025"))
        assert "state" not in path[0] and all("state" not in f for f in futures)

    def test_a_club_the_grid_does_not_hold(self):
        path, _ = _stamp(_grid(BREWERS_ROW))
        assert "state" not in path[0]

    def test_two_club_rows_that_disagree_decide_nothing(self):
        twin = copy.deepcopy(BRAVES_ROW)
        twin["team_id"] = 99999
        twin["cells"]["championship"]["state"] = "live"
        path, _ = _stamp(_grid(BRAVES_ROW, twin), club_ids=(BRAVES, 99999))
        assert "state" not in path[0]

    def test_two_club_rows_that_agree_decide(self):
        twin = copy.deepcopy(BRAVES_ROW)
        twin["team_id"] = 99999
        path, _ = _stamp(_grid(BRAVES_ROW, twin), club_ids=(BRAVES, 99999))
        assert path[0]["state"] == "eliminated"

    def test_a_tournament_registers_lost_reads_as_eliminated(self):
        row = copy.deepcopy(BRAVES_ROW)
        row["cells"]["championship"]["state"] = "lost"
        path, _ = _stamp(_grid(row))
        assert path[0]["state"] == "eliminated"


# ─── Which column answers a step ─────────────────────────────────────────────


class TestColumnForAStep:
    def test_a_step_whose_market_the_column_does_not_list_reads_its_tier(self):
        path = _path()
        path[0]["market_id"] = 424242  # a source the grid did not admit
        path, _ = _stamp(_grid(BRAVES_ROW), path=path, futures=[])
        assert path[0]["state"] == "eliminated"

    def test_mlb_tier_two_reads_the_pennant(self):
        step = {"tier": 2, "label": "NL Pennant", "market_id": 424242, "probability": 0.002}
        path, _ = _stamp(_grid(BRAVES_ROW), path=[step], futures=[])
        assert path[0]["state"] == "eliminated"

    def test_another_leagues_tier_two_reads_the_conference(self):
        grid = {
            "season": "2026-27",
            "columns": [{"key": "conference", "market_ids": [52755681]}],
            "teams": [{"team_id": 7, "cells": _cells(conference="eliminated")}],
        }
        step = {"tier": 2, "label": "Conference", "market_id": 424242, "probability": 0.0}
        path, _ = _stamp(grid, club_ids=(7,), season="2026-27", path=[step], futures=[])
        assert path[0]["state"] == "eliminated"

    def test_the_listing_column_outranks_the_tier(self):
        # 114584 is listed by `championship`; a won division must not answer it.
        path, _ = _stamp(_grid(BRAVES_ROW))
        assert path[0]["state"] == "eliminated"
        step = {"tier": 4, "label": "Division", "market_id": 272, "probability": 0.99}
        path, _ = _stamp(_grid(BRAVES_ROW), path=[step], futures=[])
        assert path[0]["state"] == "won"


# ─── The cache read never builds ─────────────────────────────────────────────


class _FakeRedis:
    def __init__(self, store, fail=False):
        self.store = store
        self.fail = fail
        self.reads: list[str] = []

    async def get(self, key):
        self.reads.append(key)
        if self.fail:
            raise ConnectionError("down")
        return self.store.get(key)


KEY = "bainluck:category:playoffs:mlb"


def _read(fake):
    async def _client():
        return fake

    with patch.object(request_cache, "get_shared_async_redis", _client), patch(
        "app.routes.playoffs.get_playoff_grid",
        side_effect=AssertionError("the team page must never build a grid"),
    ):
        return asyncio.run(route._read_cached_grid("mlb"))


class TestTheCacheRead:
    def test_the_fresh_key(self):
        fake = _FakeRedis({KEY: json.dumps(_grid(BRAVES_ROW))})
        assert _read(fake)["teams"][0]["team_id"] == BRAVES
        assert fake.reads == [KEY]

    def test_a_clean_miss_reads_the_stale_mirror(self):
        fake = _FakeRedis({f"{KEY}:stale": json.dumps(_grid(BRAVES_ROW))})
        assert _read(fake)["teams"][0]["team_id"] == BRAVES
        assert fake.reads == [KEY, f"{KEY}:stale"]

    def test_both_missing_is_none(self):
        assert _read(_FakeRedis({})) is None

    def test_an_error_stops_without_the_mirror(self):
        fake = _FakeRedis({}, fail=True)
        assert _read(fake) is None
        assert fake.reads == [KEY]

    def test_a_timeout_stops_without_the_mirror(self):
        fake = _FakeRedis({f"{KEY}:stale": json.dumps(_grid(BRAVES_ROW))})

        async def _timeout(factory, **kw):
            return RedisResult(TIMEOUT)

        with patch.object(request_cache, "bounded_redis_call", _timeout):
            assert _read(fake) is None

    def test_an_empty_or_error_payload_is_not_a_verdict(self):
        fake = _FakeRedis({
            KEY: json.dumps({"teams": [], "season": "2026"}),
            f"{KEY}:stale": json.dumps({"error": "timeout", "teams": [BRAVES_ROW]}),
        })
        assert _read(fake) is None


# ─── The route: the real `get_team`, stub sections, a real engine ────────────

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


class _Session:
    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _route_page(read):
    """`get_team` for the Braves, with the path, futures and grid read stubbed."""
    from app.models.models import Base, Sport, Team

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=1, key="baseball_mlb", name="MLB"))
        s.add(Team(id=BRAVES, sport_id=1, name="Atlanta Braves", slug="atlanta-braves-mlb"))
        s.commit()

    async def _path_stub(*a, **kw):
        return _path()

    async def _futures_stub(team_ids, db, limit=30, timings=None):
        return {"items": _futures()}

    with Session(eng) as s, patch.object(route, "_get_championship_path", _path_stub), patch(
        "app.routes.user._query_team_futures", _futures_stub
    ), patch.object(route, "_read_cached_grid", read):
        return asyncio.run(route.get_team("atlanta-braves-mlb", db=_Session(s)))


class TestTheRoute:
    def test_the_served_page_carries_out_on_the_step_and_the_title_row(self):
        async def _read(slug):
            assert slug == "mlb"
            return _grid(BREWERS_ROW, BRAVES_ROW)

        page = _route_page(_read)
        assert page["championship_path"][0]["state"] == "eliminated"
        assert page["championship_path"][0]["probability"] == 0.001
        by_id = {f["market_id"]: f for f in page["futures"]}
        assert by_id[114584]["state"] == "eliminated"
        assert "state" not in by_id[206639]

    def test_a_failing_read_costs_the_page_nothing(self):
        async def _boom(slug):
            raise RuntimeError("redis on fire")

        page = _route_page(_boom)
        assert page["team"]["id"] == BRAVES
        assert page["championship_path"] == _path()
        assert all("state" not in f for f in page["futures"])

    def test_a_cache_miss_is_todays_answer(self):
        async def _miss(slug):
            return None

        page = _route_page(_miss)
        assert page["championship_path"] == _path()
