"""#11931: Events-stage latency cuts (champ_probs prewarm, scheduled card projection cache, Pass-2 fallback empty cache).

Targets the three largest substages measured on unwarmed feed builds after #13184
(2026-11-20 7:43 AM PT):
1. `events.champ_probs` (2,518 ms cold) — proactive refresh inside the 2-minute
   Discover beat once the shared Redis slot reaches 150 s (half of the 300 s TTL).
2. `events.projections` (1,638 ms Sports Football / 991 ms Discover) — skip provably
   stale books (`captured_at < since`) in `books_needing_lines`, and add per-event
   L1 + Redis L2 caching for scheduled card projected pairs (never live cards, never
   `read_failed`).
3. `events.fallbacks` (1,964 ms Discover cold) — zero-staleness per-event L1 + Redis
   L2 negative cache for Pass-2 (`SNAPSHOT_FALLBACK_SQL`) when Pass 1 (`now - 3h`)
   runs fresh and overlaps `checked_at` (`since <= checked_at <= now`).
"""

from __future__ import annotations

import importlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pcp = importlib.import_module("app.tasks.precompute_category_pages")
from app.utils import card_projected_pair as cpp
from app.utils import championship_probs_cache as cpc
from app.utils import feed_snapshot_fallback as fsf
from app.utils import recent_line_readings as rl
from app.utils.odds_math import project_scores

T0 = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)


class _FakeRedis:
    def __init__(self, *, fail_get: bool = False, fail_set: bool = False):
        self.store: dict[str, bytes] = {}
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.mget_calls = 0
        self.set_calls = 0
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, key: str):
        if self.fail_get:
            raise ConnectionError("redis down")
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        if self.fail_set:
            raise ConnectionError("redis down")
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value.encode("utf-8") if isinstance(value, str) else value

    def mget(self, keys: list[str]):
        self.mget_calls += 1
        if self.fail_get:
            raise ConnectionError("redis down")
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
                    raise ConnectionError("redis down")
                for k, v in self._ops:
                    parent.store[k] = v.encode("utf-8") if isinstance(v, str) else v
                    parent.set_calls += 1

        return _Pipe()


def _snap(
    event_id: int,
    book: str,
    spread: float | None,
    total: float | None,
    *,
    minutes_before_t0: int = 15,
    home_prob: float = 0.65,
):
    ph = pa = None
    if spread is not None and total is not None:
        ph, pa = project_scores(spread, total)
    captured = T0 - timedelta(minutes=minutes_before_t0)
    return SimpleNamespace(
        id=event_id * 100 + minutes_before_t0,
        event_id=event_id,
        bookmaker=book,
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        home_spread=spread,
        over_under=total,
        projected_home_score=ph,
        projected_away_score=pa,
        captured_at=captured,
        valid_until=None,
    )


def _card(
    event_id: int,
    *,
    stored_status: str = "scheduled",
    served_status: str = "scheduled",
    sport_key: str = "americanfootball_nfl",
    commence_time: datetime = T0 + timedelta(hours=2),
) -> dict:
    return {
        "id": event_id,
        "stored_status": stored_status,
        "served_status": served_status,
        "commence_time": commence_time,
        "sport_key": sport_key,
        "live_boundary_at": commence_time,
        "period": None,
        "state_changed_at": None,
    }


class _CardAsyncSession(AsyncSession):
    def __init__(self, rows_by_event: dict[int, list], *, fail_recent: bool = False):
        self.rows_by_event = rows_by_event
        self.fail_recent = fail_recent
        self.savepoints = 0
        self.latest_calls = 0
        self.recent_calls = 0

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1

        class _SP:
            async def rollback(self):
                return None

        yield _SP()

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SET LOCAL"):
            return SimpleNamespace(all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []))
        if "want_lines" in sql:
            self.recent_calls += 1
            if self.fail_recent:
                raise RuntimeError("recent lines timeout")
            return SimpleNamespace(all=lambda: [])
        self.latest_calls += 1
        rows = [row for rows in self.rows_by_event.values() for row in rows]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


class _FallbackAsyncSession(AsyncSession):
    def __init__(
        self,
        *,
        recent_rows: list[tuple[int, float]] | None = None,
        older_rows: list[tuple[int, float]] | None = None,
        recent_withdrawals: set[int] | list[int] | None = None,
    ):
        self.recent_rows = list(recent_rows or [])
        self.older_rows = list(older_rows or [])
        self.recent_withdrawals = set(recent_withdrawals or ())
        self.pass1_batches: list[list[int]] = []
        self.pass2_batches: list[list[int]] = []
        self.withdrawal_check_batches: list[list[int]] = []

    async def execute(self, statement, params=None):
        params = params or {}
        ids = list(params.get("ids") or [])
        if "since" in params:
            self.pass1_batches.append(ids)
            rows = [
                SimpleNamespace(event_id=eid, home_win_probability=prob)
                for eid, prob in self.recent_rows
                if eid in ids
            ]
        elif "withdrawals_since" in params:
            self.withdrawal_check_batches.append(ids)
            rows = [
                SimpleNamespace(event_id=eid)
                for eid in ids
                if eid in self.recent_withdrawals
            ]
        else:
            self.pass2_batches.append(ids)
            rows = [
                SimpleNamespace(event_id=eid, home_win_probability=prob)
                for eid, prob in self.older_rows
                if eid in ids
            ]
        return SimpleNamespace(all=lambda: rows)


# ── Cut 1: Championship probabilities proactive prewarm ──────────────────────


class TestChampionshipProbsPrewarm:
    def test_needs_prewarm_respects_half_ttl_without_relaxing_300s_bound(self):
        now = 10_000.0
        assert cpc.PREWARM_REFRESH_AFTER_S == 150
        assert cpc.TTL_SECONDS == 300

        empty = _FakeRedis()
        assert cpc.needs_prewarm(rc=empty, now=now) is True

        young = _FakeRedis()
        young.setex(cpc.CACHE_KEY, cpc.TTL_SECONDS, cpc.encode({1: 0.25}, now - 100))
        assert cpc.needs_prewarm(rc=young, now=now) is False
        assert cpc.read(rc=young, now=now) == ({1: 0.25}, now - 100)

        aging = _FakeRedis()
        aging.setex(cpc.CACHE_KEY, cpc.TTL_SECONDS, cpc.encode({1: 0.25}, now - 180))
        assert cpc.needs_prewarm(rc=aging, now=now) is True
        # Slot is still fresh for live readers until 300 s.
        assert cpc.read(rc=aging, now=now) == ({1: 0.25}, now - 180)

    @pytest.mark.asyncio
    async def test_prewarm_skips_db_when_fresh_and_refreshes_when_aging(self, monkeypatch):
        redis = _FakeRedis()
        db_calls = 0

        async def _fake_query(_db):
            nonlocal db_calls
            db_calls += 1
            return {10: 0.42, 20: 0.18}

        @asynccontextmanager
        async def _fake_session():
            yield object()

        monkeypatch.setattr("app.routes.feed._query_championship_probabilities", _fake_query)
        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)

        # Cold slot -> queries once and writes to Redis.
        res1 = await pcp._prewarm_championship_probabilities(rc=redis)
        assert res1["outcome"] == "ok"
        assert res1["teams"] == 2
        assert db_calls == 1
        assert len(redis.setex_calls) == 1

        # Fresh slot (<150 s old) -> skips DB completely.
        res2 = await pcp._prewarm_championship_probabilities(rc=redis)
        assert res2 == {"outcome": "fresh"}
        assert db_calls == 1

    @pytest.mark.asyncio
    async def test_candidate_base_beat_isolates_champ_probs_failure(self):
        async def _ok_base():
            return {"published": True}

        async def _boom_champ():
            raise RuntimeError("champ query timed out")

        async def _ok_feed():
            return 3

        with (
            patch.object(pcp, "_publish_discover_candidate_base", _ok_base),
            patch.object(pcp, "_prewarm_championship_probabilities", _boom_champ),
            patch.object(pcp, "_prewarm_discover_feed_responses", _ok_feed),
        ):
            res = await pcp._precompute_discover_candidate_base()

        assert res["candidate_base"] == {"published": True}
        assert res["champ_probs"] == "error"
        assert res["feed_prewarm"] == 3


# ── Cut 2: books_needing_lines + scheduled card projected-pair cache ─────────


class TestScheduledCardProjectionCache:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        cpp.clear_card_projection_cache()
        monkeypatch.delenv(cpp.CARD_PROJECTION_CACHE_ENV, raising=False)
        monkeypatch.setenv(cpp.CARD_PROJECTION_CACHE_SHARED_ENV, "0")
        monkeypatch.setattr(rl, "_utcnow", lambda: T0)
        yield
        cpp.clear_card_projection_cache()

    def test_books_needing_lines_skips_books_older_than_since(self):
        since = T0 - rl.PROJECTION_LINES_BOUND
        latest = {
            1: [
                _snap(1, "draftkings", None, None, minutes_before_t0=10),   # recent -> keep
                _snap(1, "fanduel", None, None, minutes_before_t0=120),     # older than 90m -> skip
                _snap(1, "betmgm", -3.5, 45.0, minutes_before_t0=5),        # already has lines -> skip
                SimpleNamespace(bookmaker="caesars", home_spread=None, over_under=None, captured_at=None),
            ]
        }
        assert rl.books_needing_lines(latest, since=since) == [
            (1, "caesars"),
            (1, "draftkings"),
        ]
        # Without `since`, backward-compatible behavior includes fanduel too.
        assert rl.books_needing_lines(latest) == [
            (1, "caesars"),
            (1, "draftkings"),
            (1, "fanduel"),
        ]

    @pytest.mark.asyncio
    async def test_scheduled_card_hits_l1_and_skips_savepoint_on_second_read(self):
        rows = {
            101: [
                _snap(101, "draftkings", -7.0, 50.0),
                _snap(101, "fanduel", -7.0, 50.0),
            ],
            102: [],  # absent card (no snapshots) should also cache cleanly
        }
        db = _CardAsyncSession(rows)
        cards = [_card(101), _card(102)]

        first = await cpp.read_card_projected_pairs_bounded(db, cards, timeout_ms=1500)
        assert 101 in first and 102 not in first
        assert first[101]["projected_home_score"] == 28.5
        assert first[101]["projected_away_score"] == 21.5
        assert db.savepoints == 1
        assert db.latest_calls == 1

        # Second call hits L1 for both 101 (present) and 102 (absent) -> 0 DB work.
        second = await cpp.read_card_projected_pairs_bounded(db, cards, timeout_ms=1500)
        assert second == first
        assert db.savepoints == 1
        assert db.latest_calls == 1

    @pytest.mark.asyncio
    async def test_live_cards_never_use_scheduled_cache(self):
        rows = {
            201: [
                _snap(201, "draftkings", -3.0, 44.0, minutes_before_t0=5),
                _snap(201, "fanduel", -3.0, 44.0, minutes_before_t0=5),
            ]
        }
        db = _CardAsyncSession(rows)

        # Warm the cache while scheduled.
        sched = [_card(201, stored_status="scheduled", served_status="scheduled")]
        await cpp.read_card_projected_pairs_bounded(db, sched, timeout_ms=1500)
        assert db.latest_calls == 1

        # Transition to live -> MUST bypass cache and query DB fresh every time.
        live = [
            _card(
                201,
                stored_status="live",
                served_status="live",
                commence_time=T0 - timedelta(minutes=30),
            )
        ]
        await cpp.read_card_projected_pairs_bounded(db, live, timeout_ms=1500)
        await cpp.read_card_projected_pairs_bounded(db, live, timeout_ms=1500)
        assert db.latest_calls == 3

    @pytest.mark.asyncio
    async def test_read_failed_is_never_cached(self):
        rows = {
            301: [_snap(301, "draftkings", None, None, minutes_before_t0=10)],
        }
        failing_db = _CardAsyncSession(rows, fail_recent=True)
        cards = [_card(301)]

        first = await cpp.read_card_projected_pairs_bounded(failing_db, cards, timeout_ms=1500)
        assert first == {301: {"projection_unavailable": rl.READ_FAILED}}

        # Next call must NOT serve cached read_failed; it retries DB.
        healthy_db = _CardAsyncSession(
            {301: [_snap(301, "draftkings", -4.0, 48.0, minutes_before_t0=5)]}
        )
        second = await cpp.read_card_projected_pairs_bounded(healthy_db, cards, timeout_ms=1500)
        assert healthy_db.latest_calls == 1
        assert second[301]["projected_home_score"] == 26.0

    @pytest.mark.asyncio
    async def test_l2_redis_shares_across_workers_and_fails_open(self, monkeypatch):
        monkeypatch.setenv(cpp.CARD_PROJECTION_CACHE_SHARED_ENV, "1")
        redis = _FakeRedis()
        monkeypatch.setattr(cpp, "_card_l2_redis_client", lambda: redis)

        rows = {401: [_snap(401, "draftkings", -6.0, 46.0)]}
        db1 = _CardAsyncSession(rows)
        first = await cpp.read_card_projected_pairs_bounded(db1, [_card(401)], timeout_ms=1500)
        assert db1.latest_calls == 1
        assert redis.set_calls == 1

        # Simulate a second cold worker (empty L1, warm L2).
        cpp.clear_card_projection_cache()
        db2 = _CardAsyncSession(rows)
        second = await cpp.read_card_projected_pairs_bounded(db2, [_card(401)], timeout_ms=1500)
        assert second == first
        assert db2.latest_calls == 0
        assert db2.savepoints == 0

        # Redis failure degrades cleanly to Postgres.
        cpp.clear_card_projection_cache()
        monkeypatch.setattr(cpp, "_card_l2_redis_client", lambda: _FakeRedis(fail_get=True, fail_set=True))
        db3 = _CardAsyncSession(rows)
        third = await cpp.read_card_projected_pairs_bounded(db3, [_card(401)], timeout_ms=1500)
        assert third == first
        assert db3.latest_calls == 1

    @pytest.mark.asyncio
    async def test_kill_switch_and_zero_timeout_respected(self, monkeypatch):
        monkeypatch.setenv(cpp.CARD_PROJECTION_CACHE_ENV, "0")
        rows = {501: [_snap(501, "draftkings", -2.0, 42.0)]}
        db = _CardAsyncSession(rows)
        await cpp.read_card_projected_pairs_bounded(db, [_card(501)], timeout_ms=1500)
        await cpp.read_card_projected_pairs_bounded(db, [_card(501)], timeout_ms=1500)
        assert db.latest_calls == 2

        # Zero timeout never touches DB or Redis.
        monkeypatch.setenv(cpp.CARD_PROJECTION_CACHE_ENV, "1")
        db_zero = _CardAsyncSession(rows)
        assert await cpp.read_card_projected_pairs_bounded(db_zero, [_card(501)], timeout_ms=0) == {}
        assert db_zero.savepoints == 0

    @pytest.mark.asyncio
    async def test_monkeypatched_reader_bypasses_cache_inside_savepoint(self, monkeypatch):
        rows = {601: [_snap(601, "draftkings", -3.5, 47.0)]}
        db = _CardAsyncSession(rows)
        # Warm cache first.
        await cpp.read_card_projected_pairs_bounded(db, [_card(601)], timeout_ms=1500)
        assert db.savepoints == 1

        called = []

        async def _custom_reader(session, cards):
            called.append([c["id"] for c in cards])
            raise RuntimeError("simulated statement timeout")

        monkeypatch.setattr(cpp, "read_card_projected_pairs", _custom_reader)
        with pytest.raises(RuntimeError, match="simulated statement timeout"):
            await cpp.read_card_projected_pairs_bounded(db, [_card(601)], timeout_ms=100)
        assert called == [[601]]
        assert db.savepoints == 2


# ── Cut 3: Pass-2 snapshot fallback negative cache ───────────────────────────


class TestSnapshotFallbackEmptyCache:
    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        fsf.clear_snapshot_fallback_empty_cache()
        monkeypatch.delenv(fsf.SNAPSHOT_FALLBACK_EMPTY_CACHE_ENV, raising=False)
        monkeypatch.setenv(fsf.SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENV, "0")
        yield
        fsf.clear_snapshot_fallback_empty_cache()

    @pytest.mark.asyncio
    async def test_proven_empty_events_skip_pass2_while_pass1_still_catches_new_readings(self):
        # Event 10 is empty; Event 20 has a historical (>3h) reading.
        db1 = _FallbackAsyncSession(recent_rows=[], older_rows=[(20, 0.61)])
        ans1 = await fsf.read_snapshot_fallbacks(db1, [10, 20], now=T0)
        assert ans1 == {20: 0.61}
        assert db1.pass1_batches == [[10, 20]]
        assert db1.pass2_batches == [[10, 20]]

        # 2 minutes later (#13573): Pass 1 runs fresh for both; Pass 2 skips BOTH
        # empty (10) AND positive >3h (20) after checking bounded recent withdrawals for 20.
        t1 = T0 + timedelta(minutes=2)
        db2 = _FallbackAsyncSession(recent_rows=[], older_rows=[(20, 0.61)])
        ans2 = await fsf.read_snapshot_fallbacks(db2, [10, 20], now=t1)
        assert ans2 == {20: 0.61}
        assert db2.pass1_batches == [[10, 20]]
        assert db2.withdrawal_check_batches == [[20]]
        assert db2.pass2_batches == []

        # 3 minutes later: a brand-new reading arrives for event 10 -> Pass 1 catches it
        # IMMEDIATELY (zero staleness!).
        t2 = T0 + timedelta(minutes=3)
        db3 = _FallbackAsyncSession(recent_rows=[(10, 0.77)], older_rows=[])
        ans3 = await fsf.read_snapshot_fallbacks(db3, [10], now=t2)
        assert ans3 == {10: 0.77}
        assert db3.pass1_batches == [[10]]
        assert db3.withdrawal_check_batches == []
        assert db3.pass2_batches == []

    @pytest.mark.asyncio
    async def test_recent_withdrawal_invalidates_cached_positive_pass2_hit(self):
        """#13573: a cached >3h Pass-2 price MUST invalidate on a fresh withdrawal in [since, now]."""
        db1 = _FallbackAsyncSession(recent_rows=[], older_rows=[(77, 0.68)])
        assert await fsf.read_snapshot_fallbacks(db1, [77], now=T0) == {77: 0.68}
        assert db1.pass2_batches == [[77]]

        # Warm hit with no withdrawal in [since, now] skips Pass 2 and serves cached 0.68.
        db2 = _FallbackAsyncSession(recent_rows=[], older_rows=[(77, 0.68)])
        assert await fsf.read_snapshot_fallbacks(db2, [77], now=T0 + timedelta(minutes=1)) == {77: 0.68}
        assert db2.withdrawal_check_batches == [[77]]
        assert db2.pass2_batches == []

        # Withdrawal arrives in [since, now] -> invalidates 0.68 and re-runs Pass 2 fresh (now 0.35 or empty).
        db3 = _FallbackAsyncSession(
            recent_rows=[],
            older_rows=[(77, 0.35)],
            recent_withdrawals={77},
        )
        ans3 = await fsf.read_snapshot_fallbacks(db3, [77], now=T0 + timedelta(minutes=2))
        assert ans3 == {77: 0.35}
        assert db3.withdrawal_check_batches == [[77]]
        assert db3.pass2_batches == [[77]]

    @pytest.mark.asyncio
    async def test_l2_redis_shares_positive_and_empty_pass2_across_workers(self, monkeypatch):
        """#13573: Redis L2 preserves Decimal vs float and skips Pass 2 on cold workers."""
        from decimal import Decimal

        monkeypatch.setenv(fsf.SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENV, "1")
        redis = _FakeRedis()
        monkeypatch.setattr(fsf, "_empty_l2_redis_client", lambda: redis)

        db1 = _FallbackAsyncSession(older_rows=[(88, Decimal("0.4250"))])
        assert await fsf.read_snapshot_fallbacks(db1, [88, 89], now=T0) == {88: Decimal("0.4250")}
        assert db1.pass2_batches == [[88, 89]]

        fsf.clear_snapshot_fallback_empty_cache()
        db2 = _FallbackAsyncSession(older_rows=[(88, Decimal("0.4250"))])
        ans2 = await fsf.read_snapshot_fallbacks(db2, [88, 89], now=T0 + timedelta(minutes=1))
        assert ans2 == {88: Decimal("0.4250")}
        assert isinstance(ans2[88], Decimal)
        assert db2.withdrawal_check_batches == [[88]]
        assert db2.pass2_batches == []

    @pytest.mark.asyncio
    async def test_gap_past_recent_window_or_earlier_clock_rechecks_pass2(self):
        db1 = _FallbackAsyncSession()
        assert await fsf.read_snapshot_fallbacks(db1, [30], now=T0) == {}
        assert db1.pass2_batches == [[30]]

        # Past the 3-hour window (gap between checked_at and new `since`) -> MUST run Pass 2.
        db_late = _FallbackAsyncSession()
        await fsf.read_snapshot_fallbacks(
            db_late, [30], now=T0 + fsf.SNAPSHOT_FALLBACK_RECENT_WINDOW + timedelta(seconds=1)
        )
        assert db_late.pass2_batches == [[30]]

        # Earlier clock (`now < checked_at`) -> MUST run Pass 2.
        db_early = _FallbackAsyncSession()
        await fsf.read_snapshot_fallbacks(db_early, [30], now=T0 - timedelta(seconds=1))
        assert db_early.pass2_batches == [[30]]

    @pytest.mark.asyncio
    async def test_l2_redis_shares_proven_empty_across_workers_and_kill_switch_works(self, monkeypatch):
        monkeypatch.setenv(fsf.SNAPSHOT_FALLBACK_EMPTY_CACHE_SHARED_ENV, "1")
        redis = _FakeRedis()
        monkeypatch.setattr(fsf, "_empty_l2_redis_client", lambda: redis)

        db1 = _FallbackAsyncSession()
        await fsf.read_snapshot_fallbacks(db1, [40, 41], now=T0)
        assert db1.pass2_batches == [[40, 41]]
        assert redis.set_calls == 2

        # Cold worker reads L2 and skips Pass 2 completely.
        fsf.clear_snapshot_fallback_empty_cache()
        db2 = _FallbackAsyncSession()
        await fsf.read_snapshot_fallbacks(db2, [40, 41], now=T0 + timedelta(minutes=1))
        assert db2.pass1_batches == [[40, 41]]
        assert db2.pass2_batches == []

        # Kill switch disables caching completely.
        monkeypatch.setenv(fsf.SNAPSHOT_FALLBACK_EMPTY_CACHE_ENV, "0")
        db3 = _FallbackAsyncSession()
        await fsf.read_snapshot_fallbacks(db3, [40, 41], now=T0 + timedelta(minutes=2))
        assert db3.pass2_batches == [[40, 41]]
