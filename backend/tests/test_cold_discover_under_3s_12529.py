"""#12529 — Cold Discover build < 3s & eliminate projected-pairs statement timeouts.

Pins all four root-cause fixes:
1. `card_projected_pair.read_card_projected_pairs_bounded` chunks >25 uncached
   cards (live first, then scheduled), caches completed chunks immediately, raises
   scheduled TTL to 180s across the 120s beat, and degrades cleanly on partial
   timeouts without discarding completed chunks.
2. `principal_independent_cache.get_or_build` exempts `LIVENESS_INERT_NAMESPACES`
   (`market_load`) from the ambient warm-rail `bind_max_shared_age` clamp while
   still honoring explicit `max_age_s` and still clamping counted namespaces.
3. `routes/events._build_team_lookup` / `_rebuild_team_lookup` share a compact,
   non-stacking-TTL compressed Redis L2 snapshot across cold workers and fail
   open cleanly when Redis is unavailable or corrupt.
4. `ladder_monotonicity` and `feed_market_quality` memoize pure hot paths and
   preserve exact market classification behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes import events as ev
from app.utils import card_projected_pair as cpp
from app.utils import feed_market_quality as fmq
from app.utils import ladder_monotonicity as lm
from app.utils import principal_independent_cache as pic
from app.utils.odds_math import project_scores


T0 = datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)


class _FakeSyncRedis:
    def __init__(self, *, fail_get: bool = False, fail_set: bool = False):
        self.store: dict[str, bytes] = {}
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.set_calls = 0
        self.setex_calls: list[tuple[str, int, bytes | str]] = []

    def get(self, key: str):
        if self.fail_get:
            raise ConnectionError("redis get down")
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value):
        if self.fail_set:
            raise ConnectionError("redis setex down")
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value.encode("utf-8") if isinstance(value, str) else value

    def mget(self, keys: list[str]):
        if self.fail_get:
            raise ConnectionError("redis mget down")
        return [self.store.get(k) for k in keys]

    def pipeline(self, transaction: bool = False):
        parent = self

        class _Pipe:
            def __init__(self):
                self._ops: list[tuple[str, str]] = []

            def set(self, key: str, value: str, ex=None):
                self._ops.append((key, value))

            def execute(self):
                if parent.fail_set:
                    raise ConnectionError("redis pipeline down")
                for k, v in self._ops:
                    parent.store[k] = v.encode("utf-8") if isinstance(v, str) else v
                    parent.set_calls += 1

        return _Pipe()


def _card(
    event_id: int,
    *,
    stored_status: str = "scheduled",
    served_status: str = "scheduled",
    sport_key: str = "basketball_nba",
) -> dict:
    commence = (
        T0 - timedelta(minutes=30)
        if stored_status == "live"
        else T0 + timedelta(hours=3)
    )
    return {
        "id": event_id,
        "stored_status": stored_status,
        "served_status": served_status,
        "commence_time": commence,
        "sport_key": sport_key,
        "live_boundary_at": commence,
        "period": "2Q" if stored_status == "live" else None,
        "state_changed_at": T0 - timedelta(minutes=2) if stored_status == "live" else None,
    }


def _snap(event_id: int, *, minutes_ago: int = 2) -> SimpleNamespace:
    ph, pa = project_scores(-4.5, 220.5)
    ts = T0 - timedelta(minutes=minutes_ago)
    return SimpleNamespace(
        id=event_id * 10 + 1,
        event_id=event_id,
        bookmaker="draftkings",
        home_win_probability=0.62,
        away_win_probability=0.38,
        home_spread=-4.5,
        over_under=220.5,
        projected_home_score=ph,
        projected_away_score=pa,
        captured_at=ts,
        valid_until=ts,
    )


class _ChunkTrackingSession(AsyncSession):
    def __init__(self, fail_batch_indices: set[int] | None = None):
        self.fail_batch_indices = fail_batch_indices or set()
        self.batch_wanted_ids: list[list[int]] = []
        self.timeouts: list[str] = []
        self.savepoints = 0
        self.rollbacks = 0
        self._batch_cursor = 0

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1
        session = self

        class _SP:
            async def rollback(self):
                session.rollbacks += 1

        try:
            yield _SP()
        except BaseException:
            session.rollbacks += 1
            raise


class TestChunkedBoundedProjectedPairs:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        cpp.clear_card_projection_cache()
        monkeypatch.delenv(cpp.CARD_PROJECTION_CACHE_ENV, raising=False)
        monkeypatch.setenv(cpp.CARD_PROJECTION_CACHE_SHARED_ENV, "1")
        yield
        cpp.clear_card_projection_cache()

    @pytest.mark.asyncio
    async def test_chunks_live_first_caches_completed_batches_and_survives_partial_timeout(
        self, monkeypatch
    ):
        assert cpp.CARD_PROJECTION_BATCH_SIZE == 25
        assert cpp.CARD_PROJECTION_CACHE_TTL_SECONDS == 180

        fake_redis = _FakeSyncRedis()
        monkeypatch.setattr(cpp, "_card_l2_redis_client", lambda: fake_redis)

        # Put 55 scheduled cards FIRST and 5 live cards LAST; chunking must still put live first.
        sched_cards = [_card(1000 + i) for i in range(55)]
        live_cards = [
            _card(9000 + i, stored_status="live", served_status="live")
            for i in range(5)
        ]
        all_cards = sched_cards + live_cards
        live_ids = [c["id"] for c in live_cards]

        db = _ChunkTrackingSession(fail_batch_indices={2})
        observed_batches: list[list[int]] = []

        async def _fake_execute(stmt, *_a, **_kw):
            sql = str(stmt)
            if sql.startswith("SET LOCAL statement_timeout"):
                db.timeouts.append(sql)
            return SimpleNamespace()

        db.execute = _fake_execute  # type: ignore[method-assign]

        async def _fake_uncached(_db, wanted: dict[int, dict]):
            idx = len(observed_batches)
            ids = list(wanted.keys())
            observed_batches.append(ids)
            if idx in db.fail_batch_indices:
                raise TimeoutError("simulated statement_timeout on batch 3")
            pairs = {
                eid: {
                    "projected_home_score": 112.5,
                    "projected_away_score": 108.0,
                    "projection_captured_at": T0.isoformat(),
                    "projection_bookmaker_count": 1,
                }
                for eid in ids
            }
            return pairs, set()

        monkeypatch.setattr(cpp, "_read_card_projected_pairs_uncached", _fake_uncached)

        pairs = await cpp.read_card_projected_pairs_bounded(db, all_cards, timeout_ms=1500)

        # Batch sizes: 25, 25, 10 (third failed cleanly -> 50 cards kept: 5 live + 45 scheduled)
        assert [len(b) for b in observed_batches] == [25, 25, 10]
        assert observed_batches[0][:5] == live_ids
        assert db.timeouts[0] == f"SET LOCAL statement_timeout = '{cpp.CARD_PROJECTION_READ_CAP_MS}ms'"
        assert len(db.timeouts) == 3
        assert db.savepoints == 3
        assert db.rollbacks == 3
        assert len(pairs) == 50
        for eid in live_ids:
            assert eid in pairs

        # All 45 completed scheduled cards (20 in batch 0 + 25 in batch 1) are already in L2!
        # Live cards and failed batch 2 cards must NOT be in L2.
        assert fake_redis.set_calls == 45
        for eid in live_ids:
            assert f"card_proj:v1:{eid}:live:live:basketball_nba" not in fake_redis.store

        # Second call (even after clearing L1!) hits L2 for the 45 scheduled cards and ONLY
        # queries the 5 live cards + 10 remaining scheduled cards = 15 cards in ONE savepoint.
        cpp.clear_card_projection_cache()
        observed_batches.clear()
        db2 = _ChunkTrackingSession()
        db2.execute = _fake_execute  # type: ignore[method-assign]
        db.fail_batch_indices.clear()

        pairs2 = await cpp.read_card_projected_pairs_bounded(db2, all_cards, timeout_ms=1500)
        assert len(observed_batches) == 1
        assert len(observed_batches[0]) == 15
        assert observed_batches[0][:5] == live_ids
        assert len(pairs2) == 60

    @pytest.mark.asyncio
    async def test_stops_before_second_chunk_when_wall_budget_exhausted(self, monkeypatch):
        cards = [_card(2000 + i) for i in range(40)]
        db = _ChunkTrackingSession()

        async def _noop_execute(*_a, **_kw):
            return SimpleNamespace()

        db.execute = _noop_execute  # type: ignore[method-assign]
        observed: list[list[int]] = []

        now_holder = [1000.0]
        monkeypatch.setattr(cpp.time, "monotonic", lambda: now_holder[0])

        async def _slow_first_batch(_db, wanted):
            observed.append(list(wanted.keys()))
            now_holder[0] += 1.48  # leaves 20ms < CARD_PROJECTION_MIN_READ_MS (50ms)
            return {eid: {"projected_home_score": 24.0, "projected_away_score": 21.0} for eid in wanted}, set()

        monkeypatch.setattr(cpp, "_read_card_projected_pairs_uncached", _slow_first_batch)

        out = await cpp.read_card_projected_pairs_bounded(db, cards, timeout_ms=1500)
        assert len(observed) == 1
        assert len(out) == 25


class TestLivenessInertAmbientBoundExemption:
    @pytest.fixture(autouse=True)
    def _clean(self):
        pic.clear_shared_builds()
        pic.bind_max_shared_age(None)
        yield
        pic.clear_shared_builds()
        pic.bind_max_shared_age(None)

    @pytest.mark.asyncio
    async def test_warm_rail_reuses_liveness_inert_market_load_beyond_10s_while_clamping_counted_ns(
        self, monkeypatch
    ):
        import inspect
        from app.routes import feed as feed_route

        src = inspect.getsource(feed_route._score_futures)
        assert 'max_age_s=_pic.shared_build_ttl_s("market_load")' in src

        clock_now = [1000.0]
        monkeypatch.setattr(pic, "_read_cross_worker", lambda *a, **k: asyncio.sleep(0, result=(False, None, 0.0)))
        monkeypatch.setattr(pic, "_publish_cross_worker", lambda *a, **k: asyncio.sleep(0))

        ml_builds = 0
        c_builds = 0

        async def _build_ml():
            nonlocal ml_builds
            ml_builds += 1
            return {"markets": ["m1"], "v": ml_builds}

        async def _build_concepts():
            nonlocal c_builds
            c_builds += 1
            return [{"slug": "masters", "v": c_builds}]

        with pic.max_shared_age_scope(10.0):
            r1 = await pic.get_or_build(
                "market_load",
                ("market_load", 1),
                _build_ml,
                max_age_s=pic.shared_build_ttl_s("market_load"),
                clock=lambda: clock_now[0],
            )
            c1 = await pic.get_or_build(
                "concepts", ("concepts", 1), _build_concepts, ttl_s=30.0, clock=lambda: clock_now[0]
            )
            assert ml_builds == 1 and c_builds == 1

            clock_now[0] = 1042.0  # 42s old: >10s ambient warm-rail bound, <120s market_load TTL
            r2 = await pic.get_or_build(
                "market_load",
                ("market_load", 1),
                _build_ml,
                max_age_s=pic.shared_build_ttl_s("market_load"),
                clock=lambda: clock_now[0],
            )
            c2 = await pic.get_or_build(
                "concepts", ("concepts", 1), _build_concepts, ttl_s=30.0, clock=lambda: clock_now[0]
            )

            assert r2 == r1 and ml_builds == 1, "market_load must be reused across 40s warm-rail passes"
            assert c_builds == 2 and c2 != c1, "counted namespace concepts must still obey 10s warm-rail bound"


class _FakeTeamRow:
    def __init__(self, tid: int, name: str, color: str, updated_at: datetime):
        self.id = tid
        self.sport_id = 1
        self.sport_key = "basketball_nba"
        self.name = name
        self.slug = name.lower().replace(" ", "-")
        self.abbreviation = name[:3].upper()
        self.primary_color = color
        self.secondary_color = "#FFFFFF"
        self.logo_url_small = f"https://example.test/{tid}.png"
        self.logo_url_large = f"https://example.test/{tid}L.png"
        self.current_record = "12-4"
        self.alternate_names = [f"{name} Alt"]
        self.standings_data = {"wins": 12, "losses": 4, "league_rank": 1}
        self.standings_updated_at = updated_at
        self.season_stats = {"ppg": 115.2}
        self.espn_id = str(tid)


class _FakeTeamDB:
    def __init__(self, rows):
        self.rows = rows
        self.executes = 0

    async def execute(self, _stmt):
        self.executes += 1
        return SimpleNamespace(all=lambda: list(self.rows))


class TestTeamLookupSharedL2:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        ev._team_cache = {}
        ev._team_cache_time = 0.0
        ev._STALE_REFRESH_INFLIGHT.clear()
        ev._STALE_REFRESH_TASKS.clear()
        monkeypatch.delenv(ev._TEAM_LOOKUP_L2_ENABLED_ENV, raising=False)
        yield
        ev._team_cache = {}
        ev._team_cache_time = 0.0

    @pytest.mark.asyncio
    async def test_cold_worker_reuses_l2_with_inherited_ttl_and_fails_open(self, monkeypatch):
        fake_redis = _FakeSyncRedis()
        monkeypatch.setattr(ev, "_team_lookup_l2_client", lambda: fake_redis)

        stamp = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
        rows = [
            (_FakeTeamRow(1, "Boston Celtics", "#007A33", stamp), "basketball_nba"),
            (_FakeTeamRow(2, "Denver Nuggets", "#0E2240", stamp), "basketball_nba"),
        ]
        db1 = _FakeTeamDB(rows)

        # Cold process 1 queries DB and writes compact compressed L2 blob
        res1 = await ev._build_team_lookup(db1, ["Boston Celtics"])
        assert db1.executes == 1
        assert len(fake_redis.setex_calls) == 1
        assert res1["Boston Celtics"].primary_color == "#007A33"
        assert res1["Boston Celtics"].standings_updated_at == stamp
        assert isinstance(res1["Boston Celtics"], ev.TeamSnapshot)

        # Simulate cold ForkPoolWorker 2 (empty L1, warm L2)
        ev._team_cache = {}
        ev._team_cache_time = 0.0
        db2 = _FakeTeamDB(rows)
        res2 = await ev._build_team_lookup(db2, ["Denver Nuggets", "Boston Celtics"])
        assert db2.executes == 0
        assert res2["Denver Nuggets"].primary_color == "#0E2240"
        assert res2["Denver Nuggets"].standings_data == {"wins": 12, "losses": 4, "league_rank": 1}
        assert res2["Boston Celtics"].standings_updated_at == stamp

        # Non-stacking TTL: a 301s-old L2 entry is refused -> falls back to Postgres
        ev._team_cache = {}
        ev._team_cache_time = 0.0
        stale_blob = ev._encode_team_snapshots_l2(
            [ev._snapshot_team(r[0], sport_key=r[1]) for r in rows],
            time.time() - (ev._TEAM_CACHE_TTL + 1),
        )
        assert ev._decode_team_snapshots_l2(stale_blob) is None

        # Corrupt L2 bytes -> fail open to Postgres cleanly
        ev._team_cache = {}
        ev._team_cache_time = 0.0
        fake_redis.store[ev._TEAM_LOOKUP_L2_KEY] = b"corrupt-payload"
        db3 = _FakeTeamDB(rows)
        res3 = await ev._build_team_lookup(db3, ["Boston Celtics"])
        assert db3.executes == 1
        assert res3["Boston Celtics"].primary_color == "#007A33"

        # Redis failure -> fail open cleanly
        ev._team_cache = {}
        ev._team_cache_time = 0.0
        monkeypatch.setattr(ev, "_team_lookup_l2_client", lambda: _FakeSyncRedis(fail_get=True, fail_set=True))
        db4 = _FakeTeamDB(rows)
        res4 = await ev._build_team_lookup(db4, ["Boston Celtics"])
        assert db4.executes == 1
        assert res4["Boston Celtics"].primary_color == "#007A33"


class TestScoringLoopOptimizationsPreserveExactBehavior:
    def test_ladder_monotonicity_lru_cache_matches_across_calls(self):
        lm.question_ladder_direction.cache_clear()
        lm.question_ladder_date_word.cache_clear()
        lm._cumulative_leg_parts.cache_clear()

        assert lm.question_ladder_direction("NVIDIA closes above ___?") == "dec"
        assert lm.question_ladder_direction("NVIDIA closes above ___?") == "dec"
        assert lm.question_ladder_date_word("OpenAI IPO by...?") == "by"
        assert lm.question_ladder_date_word("OpenAI IPO by...?") == "by"
        assert lm._cumulative_leg_parts("Before October 31, 2026", dates=True) == (
            lm._cumulative_leg_parts("Before October 31, 2026", dates=True)
        )
        assert lm.question_ladder_direction.cache_info().hits >= 1
        assert lm.question_ladder_date_word.cache_info().hits >= 1
        assert lm._cumulative_leg_parts.cache_info().hits >= 1

    def test_feed_market_quality_precompiled_regex_parity(self):
        fmq._normalized_text.cache_clear()
        assert fmq._normalized_text("#1 Netflix show on Dec 31, 2026 https://x.test/a") == (
            "<rankone> netflix show on <month> <num> <num>"
        )
        q_mayor = fmq.classify_market_quality("NYC mayoral election winner?", "politics", ["A", "B"])
        assert q_mayor.story_key == "story:regional_us_elections"
        assert "regional_us_election" in q_mayor.reasons

        q_turnout = fmq.classify_market_quality("US Presidential Election Turnout 2028", "politics", ["Over 65%"])
        assert "margin_turnout_excluded" not in q_turnout.reasons

        q_foreign_turnout = fmq.classify_market_quality("Zambia Presidential Election Turnout", "politics", ["Over 65%"])
        assert "margin_turnout_excluded" in q_foreign_turnout.reasons
