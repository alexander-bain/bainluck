"""#11931: L1 + L2 Redis caching for immutable settled pregame projections.

Production observation: ``GET /api/feed?limit=50&mode=sports&sport=basketball``
spent 4,043 ms in ``events`` because ``read_pregame_projections`` ran the
recursive CTE over 94 finished events, hit ``QueryCanceledError``, and dropped
every pregame projection. Once a game is finished, its pre-start
``odds_snapshots`` are immutable, so caching settled answers eliminates the
repeated query and stops the timeouts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import pregame_projection as pp

T0 = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.mget_calls = 0
        self.set_calls = 0

    def mget(self, keys):
        self.mget_calls += 1
        return [self.store.get(k) for k in keys]

    def pipeline(self, transaction=False):
        parent = self

        class _Pipe:
            def __init__(self):
                self._ops: list[tuple[str, str]] = []

            def set(self, key, value, ex=None):
                self._ops.append((key, value))

            def execute(self):
                for k, v in self._ops:
                    parent.store[k] = v.encode("utf-8") if isinstance(v, str) else v
                    parent.set_calls += 1

        return _Pipe()


class _FakeAsyncSession(AsyncSession):
    def __init__(self, rows_by_event: dict[int, list], *, fail: bool = False):
        self.rows_by_event = rows_by_event
        self.fail = fail
        self.queried_id_batches: list[list[int]] = []

    async def begin_nested(self):
        class _Savepoint:
            async def rollback(self):
                return None

        return _Savepoint()

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SET LOCAL"):
            return SimpleNamespace(all=lambda: [])
        ids = list((params or {}).get("ids", []))
        self.queried_id_batches.append(ids)
        if self.fail:
            raise RuntimeError("canceling statement due to statement timeout")
        out = []
        for eid in ids:
            out.extend(self.rows_by_event.get(eid, []))
        return SimpleNamespace(all=lambda: out)


def _settled_event(event_id: int, *, sport_key: str = "basketball_nba", status: str = "completed"):
    return SimpleNamespace(
        id=event_id,
        status=status,
        commence_time=T0,
        commence_time_source="odds_api",
        event_tags=[],
        sport=SimpleNamespace(key=sport_key),
        home_score=110,
        away_score=102,
        period="Final",
        box_score_data=None,
    )


def _snapshot_row(event_id: int, bookmaker: str, *, spread: float, total: float, mins_before: int = 15):
    home_proj = round((total - spread) / 2.0, 2)
    away_proj = round((total + spread) / 2.0, 2)
    return SimpleNamespace(
        id=event_id * 10 + mins_before,
        event_id=event_id,
        bookmaker=bookmaker,
        captured_at=T0 - timedelta(minutes=mins_before),
        home_win_probability=0.62,
        away_win_probability=0.38,
        home_spread=spread,
        over_under=total,
        projected_home_score=home_proj,
        projected_away_score=away_proj,
    )


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    pp.clear_pregame_projection_cache()
    monkeypatch.delenv(pp.PREGAME_PROJECTION_CACHE_ENV, raising=False)
    monkeypatch.setenv(pp.PREGAME_PROJECTION_CACHE_SHARED_ENV, "0")
    yield
    pp.clear_pregame_projection_cache()


class TestSettledPregameProjectionCache:
    @pytest.mark.asyncio
    async def test_l1_hit_skips_postgres_and_deep_copies(self):
        ev = _settled_event(501)
        db = _FakeAsyncSession({501: [_snapshot_row(501, "fanduel", spread=-4.0, total=220.0)]})

        first = await pp.read_pregame_projections(db, [ev], lambda e: e.sport.key)
        assert db.queried_id_batches == [[501]]
        assert pp.PROJECTION_KEY in first[501]

        # Mutate returned dict to prove L1 isolation.
        first[501][pp.PROJECTION_KEY]["projected_home_score"] = 999.0

        second = await pp.read_pregame_projections(db, [ev], lambda e: e.sport.key)
        assert db.queried_id_batches == [[501]]  # Zero new DB queries.
        assert second[501][pp.PROJECTION_KEY]["projected_home_score"] == 112.0

    @pytest.mark.asyncio
    async def test_partial_hit_queries_only_missing_events(self):
        ev1 = _settled_event(601)
        ev2 = _settled_event(602)
        db = _FakeAsyncSession(
            {
                601: [_snapshot_row(601, "fanduel", spread=-4.0, total=220.0)],
                602: [_snapshot_row(602, "draftkings", spread=-2.0, total=210.0)],
            }
        )

        await pp.read_pregame_projections(db, [ev1], lambda e: e.sport.key)
        assert db.queried_id_batches == [[601]]

        both = await pp.read_pregame_projections(db, [ev1, ev2], lambda e: e.sport.key)
        assert db.queried_id_batches == [[601], [602]]
        assert both[601][pp.PROJECTION_KEY]["projected_home_score"] == 112.0
        assert both[602][pp.PROJECTION_KEY]["projected_home_score"] == 106.0

    @pytest.mark.asyncio
    async def test_cross_worker_redis_l2_shares_settled_answers(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setenv(pp.PREGAME_PROJECTION_CACHE_SHARED_ENV, "1")
        monkeypatch.setattr(pp, "_l2_redis_client", lambda: fake_redis)

        ev = _settled_event(701)
        db1 = _FakeAsyncSession({701: [_snapshot_row(701, "fanduel", spread=-6.0, total=216.0)]})
        ans1 = await pp.read_pregame_projections(db1, [ev], lambda e: e.sport.key)
        assert db1.queried_id_batches == [[701]]
        assert fake_redis.set_calls == 1

        # Simulate a second worker with empty L1.
        pp.clear_pregame_projection_cache()
        db2 = _FakeAsyncSession({})
        ans2 = await pp.read_pregame_projections(db2, [ev], lambda e: e.sport.key)
        assert db2.queried_id_batches == []
        assert ans2 == ans1

    @pytest.mark.asyncio
    async def test_read_failure_is_never_cached(self):
        ev = _settled_event(801)
        failing_db = _FakeAsyncSession({}, fail=True)
        failed = await pp.read_pregame_projections(failing_db, [ev], lambda e: e.sport.key)
        assert failed[801] == {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED}

        healthy_db = _FakeAsyncSession({801: [_snapshot_row(801, "fanduel", spread=-4.0, total=220.0)]})
        recovered = await pp.read_pregame_projections(healthy_db, [ev], lambda e: e.sport.key)
        assert healthy_db.queried_id_batches == [[801]]
        assert pp.PROJECTION_KEY in recovered[801]

    @pytest.mark.asyncio
    async def test_live_detail_and_kill_switch_bypass_cache(self, monkeypatch):
        ev = _settled_event(901)
        db = _FakeAsyncSession({901: [_snapshot_row(901, "fanduel", spread=-4.0, total=220.0)]})
        await pp.read_pregame_projections(db, [ev], lambda e: e.sport.key)
        assert db.queried_id_batches == [[901]]

        # live_detail=True always reads fresh.
        await pp.read_pregame_projections(db, [ev], lambda e: e.sport.key, live_detail=True)
        assert db.queried_id_batches == [[901], [901]]

        # Kill switch bypasses L1 too.
        monkeypatch.setenv(pp.PREGAME_PROJECTION_CACHE_ENV, "0")
        await pp.read_pregame_projections(db, [ev], lambda e: e.sport.key)
        assert db.queried_id_batches == [[901], [901], [901]]

    @pytest.mark.asyncio
    async def test_zero_budget_serves_l1_without_redis_or_db_round_trips(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setenv(pp.PREGAME_PROJECTION_CACHE_SHARED_ENV, "1")
        monkeypatch.setattr(pp, "_l2_redis_client", lambda: fake_redis)

        ev1 = _settled_event(1001)
        ev2 = _settled_event(1002)
        db = _FakeAsyncSession({1001: [_snapshot_row(1001, "fanduel", spread=-4.0, total=220.0)]})
        await pp.read_pregame_projections(db, [ev1], lambda e: e.sport.key)
        mgets_before = fake_redis.mget_calls

        ans = await pp.read_pregame_projections(
            db, [ev1, ev2], lambda e: e.sport.key, timeout_ms=0
        )
        assert fake_redis.mget_calls == mgets_before
        assert db.queried_id_batches == [[1001]]
        assert pp.PROJECTION_KEY in ans[1001]
        assert ans[1002] == {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED}
