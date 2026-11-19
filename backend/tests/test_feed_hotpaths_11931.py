"""Regression & SQL-shape guards for #11931 feed hot-path optimizations.

Covers four zero-schema-change speedups on cold Discover, Sports pill, and
Category browse builds:

1. ``discover_game_reason.annotate_game_signals``: sargable range predicate on
   ``probability_change_24h`` (matches ``ix_fo_market_movement``) + fleet-wide
   shared cache key so personalized/dismissed subsets share one entry.
2. ``feed._score_events`` with ``sport_filter``: resolves matching ``Sport.id``
   rows first and pushes ``Event.sport_id IN (...)`` (short-circuiting when no
   sport matches).
3. ``feed._score_sports_mode_futures`` with ``sport_filter``: uses exact
   ``llm_sport_category = '<cat>'`` equality for canonical sports pills (hitting
   ``ix_fm_feed_open_sports``) while keeping ``external_id ILIKE`` fallback for
   league keys like ``nfl``/``nba``.
4. ``feed._compute_ordered_candidate_ids`` with ``category_filter``: skips
   mathematically disjoint candidate pools (3 fewer DB round trips on non-sports
   categories; 5-6 fewer on sports categories) while keeping ``pool_counts``
   keys and ``_discover_candidate_pool_specs`` unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes import feed as feed_mod
from app.utils import discover_game_reason as game_reason
from app.utils import principal_independent_cache as pic

FIXED_NOW = datetime(2025, 1, 15, 18, 0, 0, tzinfo=timezone.utc)


def _compile_pg(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _RecordingAsyncSession(AsyncSession):
    """Minimal AsyncSession subclass that records executed SQLAlchemy statements."""

    def __init__(self, replies: list[list]):
        self._replies = list(replies)
        self.statements: list = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        rows = self._replies.pop(0) if self._replies else []
        return _FakeResult(rows)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ex: int | None = None):
        self.store[key] = value
        return True


class TestDiscoverGameTeamMovesHotPath:
    def setup_method(self):
        pic.clear_shared_builds()

    def teardown_method(self):
        pic.clear_shared_builds()

    @pytest.mark.asyncio
    async def test_sargable_movement_predicate_and_fleet_wide_sharing(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
        monkeypatch.setattr(
            pic, "_shared_redis_client", AsyncMock(return_value=fake_redis)
        )

        # DB returns moves for two teams (42 and 77).
        db1 = _RecordingAsyncSession(
            replies=[
                [
                    (42, "Yes", 0.35, 0.12, 99, "Team A wins title?"),
                    (77, "Yes", 0.22, -0.09, 100, "Team B makes playoffs?"),
                ]
            ]
        )
        reader_a_items = [
            {
                "type": "event",
                "data": {
                    "id": 2001,
                    "status": "completed",
                    "home_team": "Team A",
                    "away_team": "Team C",
                    "home_team_data": {"team_id": 42},
                    "away_team_data": {"team_id": 43},
                },
            }
        ]
        await game_reason.annotate_game_signals(db1, reader_a_items, FIXED_NOW)
        assert len(db1.statements) == 1

        sql = _compile_pg(db1.statements[0])
        # Sargable range predicate matching ix_fo_market_movement (no ABS(...))
        assert "abs(" not in sql
        assert "probability_change_24h is not null" in sql
        assert f"probability_change_24h >= {game_reason.TEAM_MOVE_POINTS}" in sql
        assert f"probability_change_24h <= -{game_reason.TEAM_MOVE_POINTS}" in sql
        assert "team_id is not null" in sql

        # Reader A gets only Team 42's move
        moves_a = reader_a_items[0][game_reason.SIGNALS_KEY]["team_moves"]
        assert [m["market_id"] for m in moves_a] == [99]

        # Reader B (different finished-event team set, cold L1, warm L2 Redis)
        # reuses the exact same fleet-wide cache entry with 0 SQL.
        pic.clear_shared_builds()
        db2 = _RecordingAsyncSession(replies=[])
        reader_b_items = [
            {
                "type": "event",
                "data": {
                    "id": 2002,
                    "status": "completed",
                    "home_team": "Team B",
                    "away_team": "Team D",
                    "home_team_data": {"team_id": 77},
                    "away_team_data": {"team_id": 78},
                },
            }
        ]
        await game_reason.annotate_game_signals(db2, reader_b_items, FIXED_NOW)
        assert len(db2.statements) == 0
        moves_b = reader_b_items[0][game_reason.SIGNALS_KEY]["team_moves"]
        assert [m["market_id"] for m in moves_b] == [100]


class TestSportFilterEventResolution:
    @pytest.mark.asyncio
    async def test_unknown_sport_filter_short_circuits_before_events_scan(self):
        db = _RecordingAsyncSession(replies=[[]])
        items = await feed_mod._score_events(
            db,
            FIXED_NOW,
            sport_filter="nonexistent_sport_xyz",
            ctx=feed_mod.PersonalizationContext(),
            sports_mode=True,
            share_scored_events=False,
        )
        assert items == []
        # Only the tiny `sports` table lookup ran; no `events` table query fired.
        assert len(db.statements) == 1
        sql = _compile_pg(db.statements[0])
        assert "from sports" in sql
        assert "from events" not in sql

    @pytest.mark.asyncio
    async def test_matching_sport_filter_pushes_event_sport_id_in(self):
        # Reply 1: matching sport IDs; Reply 2: empty candidate event IDs.
        db = _RecordingAsyncSession(replies=[[7, 8], []])
        items = await feed_mod._score_events(
            db,
            FIXED_NOW,
            sport_filter="baseball",
            ctx=feed_mod.PersonalizationContext(),
            sports_mode=True,
            share_scored_events=False,
        )
        assert items == []
        assert len(db.statements) == 2
        sport_sql = _compile_pg(db.statements[0])
        events_sql = _compile_pg(db.statements[1])
        assert "from sports" in sport_sql
        assert "events.sport_id in (7, 8)" in events_sql
        assert "sports.key ilike" not in events_sql


class TestSportsModeFuturesSportFilter:
    @pytest.mark.asyncio
    async def test_canonical_sport_pill_uses_exact_category_equality(self):
        db = _RecordingAsyncSession(replies=[[]])
        items = await feed_mod._score_sports_mode_futures(
            db,
            FIXED_NOW,
            sport_filter="football",
            ctx=feed_mod.PersonalizationContext(),
            share_inputs=False,
        )
        assert items == []
        assert len(db.statements) == 1
        sql = _compile_pg(db.statements[0])
        assert "llm_sport_category = 'football'" in sql
        assert "external_id ilike" not in sql

    @pytest.mark.asyncio
    async def test_league_key_sport_filter_keeps_external_id_ilike(self):
        db = _RecordingAsyncSession(replies=[[]])
        items = await feed_mod._score_sports_mode_futures(
            db,
            FIXED_NOW,
            sport_filter="nfl",
            ctx=feed_mod.PersonalizationContext(),
            share_inputs=False,
        )
        assert items == []
        assert len(db.statements) == 1
        sql = _compile_pg(db.statements[0])
        assert "external_id ilike '%%nfl%%'" in sql or "external_id ilike '%nfl%'" in sql

    @pytest.mark.asyncio
    async def test_partial_substring_keeps_both_matched_categories_and_external_id(self):
        db = _RecordingAsyncSession(replies=[[]])
        items = await feed_mod._score_sports_mode_futures(
            db,
            FIXED_NOW,
            sport_filter="ball",
            ctx=feed_mod.PersonalizationContext(),
            share_inputs=False,
        )
        assert items == []
        assert len(db.statements) == 1
        sql = _compile_pg(db.statements[0])
        assert "llm_sport_category in (" in sql
        assert "'football'" in sql
        assert "'basketball'" in sql
        assert "'baseball'" in sql
        assert "external_id ilike" in sql


class TestCategoryBrowsePoolPruning:
    @pytest.mark.parametrize(
        ("category", "expected_skipped"),
        [
            (None, set()),
            ("politics", {"sports", "sports_postseason", "sports_editorial_recall"}),
            ("economics", {"sports", "sports_postseason", "sports_editorial_recall"}),
            (
                "tennis",
                {
                    "sports_postseason",
                    "nonsports_volume",
                    "nonsports_movement",
                    "nonsports_enriched",
                    "nonsports_editorial_recall",
                    "nonsports_timely",
                },
            ),
            (
                "basketball",
                {
                    "nonsports_volume",
                    "nonsports_movement",
                    "nonsports_enriched",
                    "nonsports_editorial_recall",
                    "nonsports_timely",
                },
            ),
        ],
    )
    def test_pool_disjoint_from_category(self, category, expected_skipped):
        all_pools = (
            "sports",
            "sports_postseason",
            "sports_editorial_recall",
            "nonsports_volume",
            "nonsports_movement",
            "nonsports_enriched",
            "nonsports_editorial_recall",
            "nonsports_timely",
        )
        actual_skipped = {
            p for p in all_pools if feed_mod._pool_disjoint_from_category(p, category)
        }
        assert actual_skipped == expected_skipped

    @pytest.mark.asyncio
    async def test_compute_ordered_candidate_ids_skips_disjoint_pools(self, monkeypatch):
        monkeypatch.setattr(
            feed_mod,
            "_external_curator_recall_market_ids",
            AsyncMock(return_value=[]),
        )
        # Only the 5 nonsports_* pools should execute for category="politics".
        db = _RecordingAsyncSession(replies=[[101], [102], [], [101, 103], []])
        market_ids, pool_counts, curator_ids = (
            await feed_mod._compute_ordered_candidate_ids(
                db,
                FIXED_NOW,
                sport_filter=None,
                category_filter="politics",
            )
        )
        assert len(db.statements) == 5
        assert market_ids == [101, 102, 103]
        assert curator_ids == []
        # Provenance keys remain complete with 0 for skipped pools.
        assert pool_counts["sports"] == 0
        assert pool_counts["sports_postseason"] == 0
        assert pool_counts["sports_editorial_recall"] == 0
        assert pool_counts["nonsports_volume"] == 1
        assert pool_counts["deduped"] == 3
