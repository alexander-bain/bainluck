"""#11931 — Discover feed and warmer hot-path speedups.

Production `web.1` and `worker-realtime.1` traces (Nov 18, 2026) showed three
principal-independent bottlenecks dominating non-sports `/api/feed` builds
(~9.6 s cold Discover) and starving `prewarm_live_feed_shapes` past its 20 s
budget:

1. ``container_discovery._discovery_sql(by_events=True)`` only pre-filtered
   ``hub`` when ``by_markets=True`` (Search), so Discover's 20-game lookup
   scanned every published container and market edge before filtering in
   ``HAVING``, timing out at 250 ms and blocking ``db.rollback()`` for 2-10 s.
2. ``feed_collections.add_feed_collections`` relied solely on
   ``asyncio.wait_for`` without a Postgres ``SET LOCAL statement_timeout``
   inside a savepoint.
3. ``discover_game_reason.annotate_game_signals`` (~2.5 s) and
   ``graded_out_field_legs.graded_out_leg_ids_by_market`` (~1.6 s) re-ran
   principal-independent database reads on every Discover / Sports miss.

This suite pins all four fixes, parity, cross-worker Redis sharing, and
kill-switch behavior.
"""

from __future__ import annotations

import copy
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.feed import _rank_key
from app.services import container_discovery as discovery
from app.utils import discover_game_reason as game_reason
from app.utils import feed_collections
from app.utils import graded_out_field_legs as graded_out
from app.utils import principal_independent_cache as pic

NOW = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)


class _FakeRedis:
    def __init__(self):
        self.stored: dict[str, object] = {}

    async def set(self, key, value, ex=None):
        self.stored[key] = value
        return True

    async def get(self, key):
        return self.stored.get(key)


class _RecordingAsyncSession(AsyncSession):
    """Lightweight AsyncSession subclass that records SQL without a real DB."""

    is_active = True

    def __init__(self, replies=None, initial_statement_timeout="30s"):
        self._replies = list(replies or [])
        self._initial_statement_timeout = initial_statement_timeout
        self.statements: list[str] = []
        self.statement_params: list[dict | None] = []
        self.savepoints = 0
        self.rolled_back = 0

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1
        yield self

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.statement_params.append(dict(params) if isinstance(params, dict) else None)
        if "current_setting('statement_timeout')" in sql:
            timeout = self._initial_statement_timeout
            return SimpleNamespace(all=lambda: [], fetchall=lambda: [], scalar=lambda: timeout)
        if "set_config('statement_timeout'" in sql:
            return SimpleNamespace(all=lambda: [], fetchall=lambda: [], scalar=lambda: None)
        rows = self._replies.pop(0) if self._replies else []
        return SimpleNamespace(all=lambda: rows, fetchall=lambda: rows)

    async def rollback(self):
        self.rolled_back += 1


@pytest.fixture(autouse=True)
def _clean_shared_cache(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    for env_name in (
        "FEED_SHARED_BUILD_TTL_S",
        "FEED_SHARED_BUILD_TTL_S_DISCOVER_GAME_FAST_MOVES",
        "FEED_SHARED_BUILD_TTL_S_DISCOVER_GAME_TEAM_MOVES",
        "FEED_SHARED_BUILD_TTL_S_GRADED_OUT_FIELD_LEGS",
    ):
        monkeypatch.delenv(env_name, raising=False)
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


class TestContainerDiscoveryEventPreFilter:
    def test_events_only_sql_prefilters_hub_by_event_ids_only(self):
        sql = discovery._discovery_sql(
            by_slug=False,
            by_prefix=False,
            by_season=False,
            by_events=True,
            by_markets=False,
        )
        assert "member_edge.child_type = 'event' AND member_edge.child_id = ANY(:event_ids)" in sql
        assert ":market_ids" not in sql
        assert "event_ids" in text(sql)._bindparams
        assert "market_ids" not in text(sql)._bindparams

    def test_markets_only_sql_prefilters_hub_by_market_ids_only(self):
        sql = discovery._discovery_sql(
            by_slug=False,
            by_prefix=False,
            by_season=False,
            by_events=False,
            by_markets=True,
        )
        assert "member_edge.child_type = 'market' AND member_edge.child_id = ANY(:market_ids)" in sql
        assert ":event_ids" not in sql

    def test_events_and_markets_sql_prefilters_both(self):
        sql = discovery._discovery_sql(
            by_slug=False,
            by_prefix=False,
            by_season=False,
            by_events=True,
            by_markets=True,
        )
        assert "member_edge.child_type = 'event' AND member_edge.child_id = ANY(:event_ids)" in sql
        assert "member_edge.child_type = 'market' AND member_edge.child_id = ANY(:market_ids)" in sql


class TestFeedCollectionsStatementTimeout:
    @pytest.mark.asyncio
    async def test_async_session_sets_local_statement_timeout_in_savepoint(self, monkeypatch):
        db = _RecordingAsyncSession()
        card = {
            "id": 70,
            "name": "NFL 2026 Week 5",
            "slug": "nfl-2026-week-5",
            "matched_event_ids": [501],
        }
        monkeypatch.setattr(
            discovery,
            "discover_collections",
            AsyncMock(return_value=SimpleNamespace(collections=[card])),
        )
        items = [{"type": "event", "score": 50, "_rank_score": 50, "_sort_time": 1, "data": {"id": 501}}]
        result = await feed_collections.add_feed_collections(
            db, items, rank_key=_rank_key, budget_seconds=0.25
        )
        assert db.savepoints == 1
        assert db.statements == [
            "SELECT current_setting('statement_timeout')",
            "SELECT set_config('statement_timeout', :val, true)",
            "SELECT set_config('statement_timeout', :val, true)",
        ]
        assert db.statement_params == [None, {"val": "250ms"}, {"val": "30s"}]
        assert db.rolled_back == 0
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_async_session_failure_rolls_back_only_savepoint(self, monkeypatch):
        db = _RecordingAsyncSession()
        monkeypatch.setattr(
            discovery,
            "discover_collections",
            AsyncMock(side_effect=RuntimeError("statement timeout")),
        )
        items = [{"type": "event", "score": 50, "_rank_score": 50, "_sort_time": 1, "data": {"id": 501}}]
        result = await feed_collections.add_feed_collections(
            db, items, rank_key=_rank_key, budget_seconds=0.2
        )
        assert result is items
        assert db.savepoints == 1
        # On error, no restore runs inside the aborted savepoint; savepoint rollback reverts it.
        assert db.statements == [
            "SELECT current_setting('statement_timeout')",
            "SELECT set_config('statement_timeout', :val, true)",
        ]
        assert db.statement_params == [None, {"val": "200ms"}]
        assert db.rolled_back == 0


class TestDiscoverGameSignalsSharedCache:
    @staticmethod
    def _sample_items():
        return [
            {
                "type": "event",
                "data": {
                    "id": 1001,
                    "status": "live",
                    "home_team": "Boston Celtics",
                    "away_team": "Miami Heat",
                    "win_probability_sources": {"espn": {"value": 0.68}},
                },
            },
            {
                "type": "event",
                "data": {
                    "id": 1002,
                    "status": "completed",
                    "home_team": "Detroit Lions",
                    "away_team": "Green Bay Packers",
                    "home_team_data": {"team_id": 42},
                    "away_team_data": {"team_id": 43},
                },
            },
        ]

    @pytest.mark.asyncio
    async def test_shared_across_calls_and_cross_worker_redis(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
        monkeypatch.setattr(pic, "_shared_redis_client", AsyncMock(return_value=fake_redis))

        db1 = _RecordingAsyncSession(
            replies=[
                [(1001, "espn", 0.50)],
                [(42, "Yes", 0.35, 0.12, 99, "Lions win NFC?")],
            ]
        )
        items1 = self._sample_items()
        await game_reason.annotate_game_signals(db1, items1, NOW)
        assert len(db1.statements) == 2
        assert items1[0][game_reason.SIGNALS_KEY]["fast_move"]["delta"] == pytest.approx(0.18)
        assert items1[1][game_reason.SIGNALS_KEY]["team_moves"][0]["market_id"] == 99

        # Second worker (cleared L1, warm L2 Redis) with updated live prob executes 0 SQL
        pic.clear_shared_builds()
        db2 = _RecordingAsyncSession(replies=[])
        items2 = copy.deepcopy(self._sample_items())
        items2[0]["data"]["win_probability_sources"]["espn"]["value"] = 0.72
        await game_reason.annotate_game_signals(db2, items2, NOW)
        assert len(db2.statements) == 0
        # Live delta reflects item2's own fresh probability against the cached 15m-ago snapshot
        assert items2[0][game_reason.SIGNALS_KEY]["fast_move"]["delta"] == pytest.approx(0.22)
        assert items2[1][game_reason.SIGNALS_KEY]["team_moves"] == items1[1][game_reason.SIGNALS_KEY]["team_moves"]

    @pytest.mark.asyncio
    async def test_kill_switch_disables_sharing(self, monkeypatch):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
        db = _RecordingAsyncSession(
            replies=[
                [(1001, "espn", 0.50)],
                [(42, "Yes", 0.35, 0.12, 99, "Lions win NFC?")],
                [(1001, "espn", 0.50)],
                [(42, "Yes", 0.35, 0.12, 99, "Lions win NFC?")],
            ]
        )
        await game_reason.annotate_game_signals(db, self._sample_items(), NOW)
        await game_reason.annotate_game_signals(db, self._sample_items(), NOW)
        assert len(db.statements) == 4


class TestGradedOutFieldLegsSharedCache:
    @staticmethod
    def _sample_markets():
        leg_a = SimpleNamespace(id=5001, current_probability=0.01)
        leg_b = SimpleNamespace(id=5002, current_probability=0.65)
        leg_c = SimpleNamespace(id=5003, current_probability=0.02)
        m = SimpleNamespace(id=800, status="open", market_type="field", outcomes=[leg_a, leg_b, leg_c])
        return [m]

    @pytest.mark.asyncio
    async def test_shared_across_calls_and_cross_worker_redis(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
        monkeypatch.setattr(pic, "_shared_redis_client", AsyncMock(return_value=fake_redis))

        markets = self._sample_markets()
        db1 = _RecordingAsyncSession(replies=[[(5001,), (5003,)]])
        first = await graded_out.graded_out_leg_ids_by_market(db1, markets)
        assert first == {800: frozenset({5001, 5003})}
        assert len(db1.statements) == 1

        # Second worker (empty L1, warm L2 Redis) executes 0 SQL and returns exact match
        pic.clear_shared_builds()
        db2 = _RecordingAsyncSession(replies=[])
        second = await graded_out.graded_out_leg_ids_by_market(db2, markets)
        assert second == first
        assert len(db2.statements) == 0

    @pytest.mark.asyncio
    async def test_kill_switch_disables_sharing(self, monkeypatch):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
        markets = self._sample_markets()
        db = _RecordingAsyncSession(replies=[[(5001,)], [(5001,)]])
        assert await graded_out.graded_out_leg_ids_by_market(db, markets) == {800: frozenset({5001})}
        assert await graded_out.graded_out_leg_ids_by_market(db, markets) == {800: frozenset({5001})}
        assert len(db.statements) == 2
