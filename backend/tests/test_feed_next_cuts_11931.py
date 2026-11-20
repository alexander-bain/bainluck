"""Regression and SQL-shape tests for #11931 next cuts:

1. `discover_game_reason.annotate_game_signals`:
   - `_load_team_moves` filters on `FuturesMarket.max_movement_24h >= TEAM_MOVE_POINTS`
     (refreshed every 10 minutes by `update_max_movement`, so a post-final jump
     can be picked up up to 10 minutes later) so Postgres probes
     `ix_fo_market_movement` by `market_id` instead of scanning all open markets
     under write contention.
   - Real PostgreSQL AsyncSessions bound each read inside a SAVEPOINT with
     `SET LOCAL statement_timeout = '1000ms'` and let timeouts propagate so
     `feed.py` logs the warning and `_pic.get_or_build` never caches an empty
     answer for a failed read.
2. `graded_out_field_legs.graded_out_leg_ids_by_market`:
   - Discover's `FuturesOutcomeSnapshot` rows carry `is_winner` + `resolution_source`
     from `OUTCOME_LOAD_ONLY_EXTRA` and skip the redundant DB round trip.
3. `feed._score_events`:
   - Settled events whose hero is already `settled` skip dead `read_snapshot_fallbacks`
     scans of `win_prob_snapshots`.
4. `feed._score_sports_mode_futures`:
   - Withheld-independent stale/expired sports markets are skipped before calling
     `withheld_price_outcome_ids_for_markets`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes import feed as feed_mod
from app.utils import discover_game_reason as game_reason
from app.utils import futures_market_snapshot as fms
from app.utils import graded_out_field_legs as gofl
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
        return SimpleNamespace(
            all=lambda: list(self._rows),
            unique=lambda: SimpleNamespace(all=lambda: list(self._rows)),
        )


class _RecordingAsyncSession(AsyncSession):
    def __init__(self, replies: list[list], *, postgres_dialect: bool = False, fail_query: bool = False):
        self._replies = list(replies)
        self.statements: list = []
        self.savepoints_opened = 0
        self.savepoints_rolled_back = 0
        self._fail_query = fail_query
        if postgres_dialect:
            self.sync_session = SimpleNamespace(
                bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
            )

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints_opened += 1
        session = self

        class _SP:
            async def rollback(self):
                session.savepoints_rolled_back += 1

        yield _SP()

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        sql_text = str(statement)
        if "SET LOCAL statement_timeout" in sql_text:
            return _FakeResult([])
        if self._fail_query:
            raise TimeoutError("canceling statement due to statement timeout")
        rows = self._replies.pop(0) if self._replies else []
        return _FakeResult(rows)


class TestDiscoverGameReasonMaxMovementAndTimeout:
    def setup_method(self):
        pic.clear_shared_builds()

    def teardown_method(self):
        pic.clear_shared_builds()

    @pytest.mark.asyncio
    async def test_team_moves_filters_on_max_movement_24h_superset(self):
        db = _RecordingAsyncSession(
            replies=[[(42, "Yes", 0.35, 0.12, 99, "Team A wins title?")]]
        )
        items = [
            {
                "type": "event",
                "data": {
                    "id": 2001,
                    "status": "completed",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "home_team_data": {"team_id": 42},
                    "away_team_data": {"team_id": 43},
                },
            }
        ]
        await game_reason.annotate_game_signals(db, items, FIXED_NOW)
        assert len(db.statements) == 1
        sql = _compile_pg(db.statements[0])
        assert "max_movement_24h is not null" in sql
        assert f"max_movement_24h >= {game_reason.TEAM_MOVE_POINTS}" in sql
        assert items[0][game_reason.SIGNALS_KEY]["team_moves"][0]["market_id"] == 99

    @pytest.mark.asyncio
    async def test_postgres_session_uses_savepoint_timeout_and_propagates_without_caching(self):
        db = _RecordingAsyncSession(replies=[], postgres_dialect=True, fail_query=True)
        items = [
            {
                "type": "event",
                "data": {
                    "id": 2002,
                    "status": "completed",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "home_team_data": {"team_id": 42},
                    "away_team_data": {"team_id": 43},
                },
            }
        ]
        with pytest.raises(TimeoutError, match="statement timeout"):
            await game_reason.annotate_game_signals(db, items, FIXED_NOW)
        assert db.savepoints_opened == 1
        assert any("SET LOCAL statement_timeout = '1000ms'" in str(s) for s in db.statements)
        assert game_reason.SIGNALS_KEY not in items[0]
        # Verify the timed-out read was NOT cached as an empty answer: a subsequent
        # healthy read in the same time bucket still queries the DB and populates signals.
        db_ok = _RecordingAsyncSession(
            replies=[[(42, "Yes", 0.35, 0.12, 99, "Team A wins title?")]],
            postgres_dialect=True,
        )
        await game_reason.annotate_game_signals(db_ok, items, FIXED_NOW)
        assert db_ok.savepoints_opened == 1
        assert items[0][game_reason.SIGNALS_KEY]["team_moves"][0]["market_id"] == 99

    @pytest.mark.asyncio
    async def test_postgres_session_rolls_back_savepoint_on_success(self):
        db = _RecordingAsyncSession(
            replies=[[(42, "Yes", 0.35, 0.12, 99, "Team A wins title?")]],
            postgres_dialect=True,
        )
        items = [
            {
                "type": "event",
                "data": {
                    "id": 2003,
                    "status": "completed",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "home_team_data": {"team_id": 42},
                    "away_team_data": {"team_id": 43},
                },
            }
        ]
        await game_reason.annotate_game_signals(db, items, FIXED_NOW)
        assert db.savepoints_opened == 1
        assert db.savepoints_rolled_back == 1
        assert items[0][game_reason.SIGNALS_KEY]["team_moves"][0]["market_id"] == 99


class TestGradedOutLegsSnapshotFastPath:
    @pytest.mark.asyncio
    async def test_futures_outcome_snapshot_skips_db_query(self):
        class _RefusesDB:
            async def execute(self, stmt):  # pragma: no cover
                raise AssertionError("snapshot rows carry loaded grades; must not query DB")

        out_graded = SimpleNamespace(
            id=501,
            name="Eliminated Team",
            team_id=None,
            external_id="o501",
            current_probability=0.005,
            opening_probability=0.10,
            probability_change_24h=-0.095,
            rank=10,
            rank_change_24h=None,
            current_yes_bid=0.0,
            current_yes_ask=0.01,
            opening_captured_at=FIXED_NOW - timedelta(days=3),
            last_updated=FIXED_NOW - timedelta(minutes=5),
            is_winner=False,
            resolution_source="api_settlement",
            volume_24h=0,
            volume_24h_at=None,
        )
        out_alive = SimpleNamespace(
            id=502,
            name="Contender Team",
            team_id=None,
            external_id="o502",
            current_probability=0.008,
            opening_probability=0.02,
            probability_change_24h=-0.012,
            rank=9,
            rank_change_24h=None,
            current_yes_bid=0.005,
            current_yes_ask=0.01,
            opening_captured_at=FIXED_NOW - timedelta(days=3),
            last_updated=FIXED_NOW - timedelta(minutes=5),
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=FIXED_NOW - timedelta(minutes=5),
        )
        raw_market = SimpleNamespace(
            id=101,
            name="2026 Championship Winner",
            source="kalshi",
            external_id="KXCHAMP",
            sport_id=1,
            category="sports",
            llm_sport_category="football",
            market_tier=1,
            market_type="field",
            status="open",
            canonical_market_key=None,
            group_id=None,
            group_type=None,
            image_url=None,
            image_width=None,
            image_height=None,
            hook_description=None,
            hook_generated_at=None,
            hook_leader_at_generation=None,
            market_metadata={},
            curation_score_adj=0,
            volume_24h=10000,
            resolution_date=FIXED_NOW + timedelta(days=30),
            commence_time=None,
            updated_at=FIXED_NOW,
            created_at=FIXED_NOW - timedelta(days=10),
            outcomes=[out_graded, out_alive],
            sport=SimpleNamespace(key="americanfootball_nfl", name="NFL"),
        )
        # Round-trip through the real Discover snapshot codec
        rebuilt = fms.from_plain(fms.to_plain([raw_market], withheld_by_market={101: set()}))
        assert len(rebuilt) == 1
        assert isinstance(rebuilt[0].outcomes[0], fms.FuturesOutcomeSnapshot)

        result = await gofl.graded_out_leg_ids_by_market(_RefusesDB(), rebuilt)
        assert result == {101: frozenset({501})}


class TestSettledEventsSkipSnapshotFallback:
    @pytest.mark.asyncio
    async def test_completed_event_with_final_score_does_not_call_snapshot_fallbacks(self, monkeypatch):
        from app.utils import feed_snapshot_fallback as fsf

        fallback_calls = []

        async def _spy_fallback(db, ids, *, now):
            fallback_calls.append(list(ids))
            return {}

        monkeypatch.setattr(fsf, "read_snapshot_fallbacks", _spy_fallback)
        monkeypatch.setattr(fsf, "read_snapshot_fallback_artifact", _spy_fallback)

        from app.models.models import Event, Sport

        sport = Sport(id=1, key="basketball_ncaab", name="NCAAB")
        settled_event = Event(
            id=9001,
            external_id="ev-9001",
            sport_id=1,
            home_team_name="Duke Blue Devils",
            away_team_name="UNC Tar Heels",
            home_team_id=10,
            away_team_id=11,
            commence_time=FIXED_NOW - timedelta(hours=3),
            status="completed",
            home_score=82,
            away_score=74,
            opening_home_probability=None,
            opening_away_probability=None,
            opening_home_spread=None,
            opening_over_under=None,
            opening_favorite=None,
            win_probability_sources={},
            raw_ei=None,
            event_tags=[],
            llm_importance=None,
            period="Final",
            game_clock=None,
            broadcast_info=None,
            completed_at=FIXED_NOW - timedelta(hours=1),
        )
        settled_event.sport = sport
        unsettled_event = Event(
            id=9002,
            external_id="ev-9002",
            sport_id=1,
            home_team_name="Kansas Jayhawks",
            away_team_name="Houston Cougars",
            home_team_id=12,
            away_team_id=13,
            commence_time=FIXED_NOW + timedelta(hours=3),
            status="scheduled",
            home_score=None,
            away_score=None,
            opening_home_probability=None,
            opening_away_probability=None,
            opening_home_spread=None,
            opening_over_under=None,
            opening_favorite=None,
            win_probability_sources={},
            raw_ei=None,
            event_tags=[],
            llm_importance=None,
            period=None,
            game_clock=None,
            broadcast_info=None,
            completed_at=None,
        )
        unsettled_event.sport = sport

        # Reply 1: candidate events query; Reply 2+: empty optional reads
        db = _RecordingAsyncSession(
            replies=[[settled_event, unsettled_event], [], [], [], [], []]
        )

        async def _no_champ(db_):
            return {}

        monkeypatch.setattr(feed_mod, "_get_championship_probabilities", _no_champ)
        monkeypatch.setattr(feed_mod, "_attach_card_projected_pairs", lambda *a, **k: _noop())
        monkeypatch.setattr(feed_mod, "_attach_pregame_projections", lambda *a, **k: _noop())

        async def _noop():
            return None

        await feed_mod._score_events(
            db,
            FIXED_NOW,
            sport_filter=None,
            ctx=feed_mod.PersonalizationContext(),
            sports_mode=True,
            share_scored_events=False,
        )
        # Settled event 9001 skipped; unsettled control event 9002 still queried.
        assert fallback_calls == [[9002]]


class TestSportsFuturesPreFilterBeforeWithheld:
    @pytest.mark.asyncio
    async def test_stale_and_expired_markets_dropped_before_withheld_read(self, monkeypatch):
        seen_withheld_market_ids = []

        async def _spy_withheld(db, markets):
            seen_withheld_market_ids.extend(m.id for m in markets)
            return {m.id: set() for m in markets}

        async def _empty_counts(db, keys):
            return {}

        async def _empty_teams(db, outcomes):
            return {}

        async def _empty_out_legs(markets):
            return {}

        async def _empty_graded(db, markets):
            return {}

        monkeypatch.setattr(feed_mod, "withheld_price_outcome_ids_for_markets", _spy_withheld)
        monkeypatch.setattr(feed_mod, "_get_canonical_source_counts", _empty_counts)
        monkeypatch.setattr(feed_mod, "_team_names_by_id", _empty_teams)
        monkeypatch.setattr(feed_mod, "out_legs_by_market", _empty_out_legs)
        monkeypatch.setattr(feed_mod, "graded_out_leg_ids_by_market", _empty_graded)

        from app.utils import sports_market_metadata_reuse as smr

        def _make_market(mid, *, res_dt, updated_at, change_24h, last_updated):
            o1 = SimpleNamespace(
                id=mid * 10 + 1,
                name="Team A",
                team_id=None,
                external_id=f"o-{mid}-1",
                current_probability=0.55,
                opening_probability=0.50,
                probability_change_24h=change_24h,
                rank=1,
                rank_change_24h=None,
                current_yes_bid=0.54,
                current_yes_ask=0.56,
                last_updated=last_updated,
                is_winner=None,
                resolution_source=None,
                volume_24h=500,
                volume_24h_at=last_updated,
            )
            o2 = SimpleNamespace(
                id=mid * 10 + 2,
                name="Team B",
                team_id=None,
                external_id=f"o-{mid}-2",
                current_probability=0.45,
                opening_probability=0.50,
                probability_change_24h=change_24h,
                rank=2,
                rank_change_24h=None,
                current_yes_bid=0.44,
                current_yes_ask=0.46,
                last_updated=last_updated,
                is_winner=None,
                resolution_source=None,
                volume_24h=500,
                volume_24h_at=last_updated,
            )
            return SimpleNamespace(
                id=mid,
                name=f"Market {mid}",
                source="kalshi",
                external_id=f"KX-{mid}",
                sport_id=1,
                category="sports",
                llm_sport_category="football",
                market_tier=1,
                market_type="championship",
                status="open",
                canonical_market_key=None,
                group_id=None,
                group_type=None,
                image_url=None,
                image_width=None,
                image_height=None,
                hook_description=None,
                hook_generated_at=None,
                hook_leader_at_generation=None,
                market_metadata={},
                curation_score_adj=0,
                volume_24h=1000,
                resolution_date=res_dt,
                commence_time=None,
                updated_at=updated_at,
                created_at=FIXED_NOW - timedelta(days=10),
                outcomes=[o1, o2],
                sport=SimpleNamespace(key="americanfootball_nfl", name="NFL"),
            )

        active = _make_market(
            1,
            res_dt=FIXED_NOW + timedelta(days=20),
            updated_at=FIXED_NOW - timedelta(hours=1),
            change_24h=0.05,
            last_updated=FIXED_NOW - timedelta(minutes=10),
        )
        expired = _make_market(
            2,
            res_dt=FIXED_NOW - timedelta(hours=2),
            updated_at=FIXED_NOW - timedelta(hours=1),
            change_24h=0.05,
            last_updated=FIXED_NOW - timedelta(minutes=10),
        )
        stale_unmoved = _make_market(
            3,
            res_dt=FIXED_NOW + timedelta(days=20),
            updated_at=FIXED_NOW - timedelta(days=5),
            change_24h=0.0,
            last_updated=FIXED_NOW - timedelta(minutes=10),
        )
        stale_but_moved = _make_market(
            4,
            res_dt=FIXED_NOW + timedelta(days=20),
            updated_at=FIXED_NOW - timedelta(days=5),
            change_24h=0.04,
            last_updated=FIXED_NOW - timedelta(minutes=10),
        )
        stopped_polling = _make_market(
            5,
            res_dt=FIXED_NOW + timedelta(days=20),
            updated_at=FIXED_NOW - timedelta(days=20),
            change_24h=0.04,
            last_updated=FIXED_NOW - timedelta(days=20),
        )

        async def _fake_load(db, ids):
            return [active, expired, stale_unmoved, stale_but_moved, stopped_polling]

        monkeypatch.setattr(smr, "load_sports_markets", _fake_load)

        db = _RecordingAsyncSession(replies=[[1, 2, 3, 4, 5]])
        await feed_mod._score_sports_mode_futures(
            db,
            FIXED_NOW,
            sport_filter="football",
            ctx=feed_mod.PersonalizationContext(),
            share_inputs=False,
        )
        assert seen_withheld_market_ids == [1, 4]
