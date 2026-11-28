"""Tests for #12290: first search after a release does not rebuild cold worker caches inline.

Verifies:
1. ``warm_search_process_caches`` populates ``_ei_cache`` and ``_team_cache``
   (via Redis L2 when warm, else Postgres fallback + L2 write) so the very first
   ``_load_ei_percentiles`` and ``_build_team_lookup`` requests pay zero DB queries.
2. Sync Redis connection pool is warmed off-loop, and stale/missing
   ``search_suggestions`` schedules a non-blocking background refresh (never blocking
   startup), while a ``live`` slot schedules nothing.
3. DB errors, Redis errors, and timeouts all fail open cleanly without raising,
   preserving healthy sibling warm-ups.
4. ``startup_cache_warm_enabled`` honors ``STARTUP_CACHE_WARM`` overrides and
   ``DYNO`` default; ``main.lifespan`` invokes it when enabled and skips when disabled.
5. ``_fetch_futures_window`` routes ``outcome_arm`` through ``_search_sliced_window_rows``
   when ``slice_query`` is given and keeps the unsliced fallback when ``slice_query``
   is None or a full slice yields too few survivors.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import main as main_module
from app.routes import events as ev


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def unique(self):
        return self


class _CountingAsyncSession:
    def __init__(self, rows):
        self.rows = rows
        self.executes = 0

    async def execute(self, _stmt):
        self.executes += 1
        return _FakeResult(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


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


class _FakeSyncRedis:
    def __init__(self, *, fail_ping: bool = False):
        self.store: dict[str, object] = {}
        self.ping_calls = 0
        self.fail_ping = fail_ping

    def ping(self):
        self.ping_calls += 1
        if self.fail_ping:
            raise ConnectionError("redis unreachable")
        return True

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, value):
        self.store[key] = value
        return True


EI_ROWS = [("nba", 50, 2.0), ("nfl", 90, 4.5)]
STAMP = datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc)
TEAM_ROWS = [
    (_FakeTeamRow(1, "Los Angeles Lakers", "#552583", STAMP), "basketball_nba"),
    (_FakeTeamRow(2, "San Antonio Spurs", "#000000", STAMP), "basketball_nba"),
]


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    ev._ei_cache = {}
    ev._ei_cache_time = 0.0
    ev._team_cache = {}
    ev._team_cache_time = 0.0
    ev._STALE_REFRESH_INFLIGHT.clear()
    ev._STALE_REFRESH_TASKS.clear()
    monkeypatch.delenv("DYNO", raising=False)
    monkeypatch.delenv("STARTUP_CACHE_WARM", raising=False)
    yield
    ev._ei_cache = {}
    ev._ei_cache_time = 0.0
    ev._team_cache = {}
    ev._team_cache_time = 0.0
    ev._STALE_REFRESH_INFLIGHT.clear()
    ev._STALE_REFRESH_TASKS.clear()


class TestStartupCacheWarmup:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("team_l2_warm", [False, True])
    async def test_warm_search_process_caches_eliminates_first_request_db_reads(
        self, monkeypatch, team_l2_warm: bool
    ):
        ei_session = _CountingAsyncSession(EI_ROWS)
        team_session = _CountingAsyncSession(TEAM_ROWS)

        def _fake_session_maker():
            # First call is EI rebuild; second (if L2 cold) is team rebuild.
            # Route cleanly based on whether EI is already populated? No,
            # inspect SQL via wrapper session below.
            return _RouterSession()

        class _RouterSession:
            async def execute(self, stmt):
                sql = str(stmt)
                if "ei_percentiles" in sql:
                    return await ei_session.execute(stmt)
                return await team_session.execute(stmt)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

        fake_rc = _FakeSyncRedis()
        if team_l2_warm:
            snaps = [ev._snapshot_team(row, sport_key=sk) for row, sk in TEAM_ROWS]
            fake_rc.store[ev._TEAM_LOOKUP_L2_KEY] = ev._encode_team_snapshots_l2(
                snaps, datetime.now(timezone.utc).timestamp()
            )

        monkeypatch.setattr("app.services.database.async_session_maker", _fake_session_maker)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **_kw: fake_rc)
        monkeypatch.setattr(ev, "_team_lookup_l2_client", lambda: fake_rc)
        monkeypatch.setattr("app.utils.search_suggestions_cache.read", lambda: (None, "live"))

        scheduled: list[str] = []
        monkeypatch.setattr(
            ev,
            "_serve_stale_and_refresh",
            lambda name, _fn: scheduled.append(name) or True,
        )

        outcomes = await ev.warm_search_process_caches(timeout_seconds=2.0)

        assert outcomes["ei"] == "ok"
        assert outcomes["team"] == ("l2" if team_l2_warm else "db")
        assert outcomes["redis"] == "ok"
        assert outcomes["suggestions"] == "live"
        assert fake_rc.ping_calls == 1
        assert scheduled == []
        assert ei_session.executes == 1
        assert team_session.executes == (0 if team_l2_warm else 1)

        # Very first reader requests hit populated process caches with ZERO DB queries.
        req_db = _CountingAsyncSession([])
        got_ei = await ev._load_ei_percentiles(req_db)
        got_teams = await ev._build_team_lookup(req_db, ["Los Angeles Lakers"])
        assert req_db.executes == 0
        assert got_ei == {"nba": {50: 2.0}, "nfl": {90: 4.5}}
        assert got_teams["Los Angeles Lakers"].primary_color == "#552583"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sug_state", ["miss", "stale_ok"])
    async def test_suggestions_cold_or_stale_schedules_nonblocking_refresh(
        self, monkeypatch, sug_state: str
    ):
        class _RouterSession:
            async def execute(self, stmt):
                sql = str(stmt)
                return _FakeResult(EI_ROWS if "ei_percentiles" in sql else TEAM_ROWS)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

        fake_rc = _FakeSyncRedis()
        monkeypatch.setattr("app.services.database.async_session_maker", _RouterSession)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **_kw: fake_rc)
        monkeypatch.setattr(ev, "_team_lookup_l2_client", lambda: fake_rc)
        monkeypatch.setattr("app.utils.search_suggestions_cache.read", lambda: (None, sug_state))

        scheduled: list[tuple[str, object]] = []
        monkeypatch.setattr(
            ev,
            "_serve_stale_and_refresh",
            lambda name, fn: scheduled.append((name, fn)) or True,
        )

        outcomes = await ev.warm_search_process_caches(timeout_seconds=2.0)
        assert outcomes["suggestions"] == f"refresh:{sug_state}"
        assert scheduled == [("search_suggestions", ev._rebuild_search_suggestions)]

    @pytest.mark.asyncio
    async def test_partial_failure_and_timeout_fail_open_without_blocking(self, monkeypatch):
        async def _boom_ei():
            raise RuntimeError("ei query failed")

        async def _slow_team():
            await asyncio.sleep(0.5)
            return "db"

        monkeypatch.setattr(ev, "_rebuild_ei_percentiles", _boom_ei)
        monkeypatch.setattr(ev, "_warm_team_lookup_on_startup", _slow_team)
        monkeypatch.setattr(ev, "_ping_sync_redis_for_startup", lambda: "error")
        monkeypatch.setattr(ev, "_read_search_suggestions_state_for_startup", lambda: "error")

        outcomes = await ev.warm_search_process_caches(timeout_seconds=0.06)
        assert outcomes["ei"] == "error"
        assert outcomes["team"] == "timeout"
        assert outcomes["redis"] == "error"
        assert outcomes["suggestions"] == "error"

    def test_startup_cache_warm_enabled_flag_matrix(self, monkeypatch):
        assert ev.startup_cache_warm_enabled() is False
        monkeypatch.setenv("DYNO", "web.1")
        assert ev.startup_cache_warm_enabled() is True
        monkeypatch.setenv("STARTUP_CACHE_WARM", "false")
        assert ev.startup_cache_warm_enabled() is False
        monkeypatch.delenv("DYNO")
        monkeypatch.setenv("STARTUP_CACHE_WARM", "true")
        assert ev.startup_cache_warm_enabled() is True

    @pytest.mark.asyncio
    async def test_lifespan_calls_warm_when_enabled_and_skips_when_disabled(self, monkeypatch):
        warm_mock = AsyncMock(return_value={"ei": "ok"})
        monkeypatch.setattr(main_module, "init_db", AsyncMock())
        monkeypatch.setattr("app.utils.request_timing.install_request_db_timer", lambda _e: True)
        monkeypatch.setattr("app.utils.request_cache.get_shared_async_redis", AsyncMock())
        monkeypatch.setattr("app.utils.request_cache.close_shared_async_redis", AsyncMock())
        monkeypatch.setattr(
            "app.services.onboarding_team_aliases.refresh_onboarding_venue_aliases",
            AsyncMock(),
        )
        monkeypatch.setattr(ev, "warm_search_process_caches", warm_mock)

        monkeypatch.delenv("DYNO", raising=False)
        async with main_module.lifespan(main_module.app):
            pass
        warm_mock.assert_not_awaited()

        monkeypatch.setenv("DYNO", "web.1")
        async with main_module.lifespan(main_module.app):
            pass
        warm_mock.assert_awaited_once()


class TestOutcomeArmUsesSlicedWindow:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("fallback_to_full", [False, True])
    async def test_outcome_arm_uses_slice_query_and_falls_back_only_when_needed(
        self, monkeypatch, fallback_to_full: bool
    ):
        class _Row:
            def __init__(self, row_id: int, tier: int):
                self.id = row_id
                self.tier = tier

        async def _fake_apply(db, deadline=None, bound_ms=None):
            return None

        monkeypatch.setattr(ev, "_apply_search_statement_timeout", _fake_apply)

        ran: list[object] = []
        slice_cap = ev._SEARCH_OPEN_NOW_SLICE

        class _Savepoint:
            async def commit(self):
                return None

            async def rollback(self):
                return None

        class _DB:
            async def begin_nested(self):
                return _Savepoint()

            async def execute(self, stmt):
                ran.append(stmt)
                if stmt == ("SLICE", ("name",)):
                    return _FakeResult([1])
                if stmt == ("SLICE", ("outcome",)):
                    if fallback_to_full:
                        return _FakeResult(list(range(100, 100 + slice_cap)))
                    return _FakeResult([101, 102])
                if isinstance(stmt, tuple) and stmt[0] == "OVER_IDS":
                    if len(ran) >= 2 and ran[-2] == ("SLICE", ("name",)):
                        return _FakeResult([_Row(1, 0)])
                    if fallback_to_full:
                        # Only 3 survived _futures_game_already_played from full slice
                        return _FakeResult([_Row(101, 2), _Row(102, 2), _Row(103, 2)])
                    return _FakeResult([_Row(101, 2), _Row(102, 2)])
                if stmt == ("WINDOW", frozenset(["outcome"])) and fallback_to_full:
                    return _FakeResult([_Row(101, 2), _Row(102, 2), _Row(103, 2), _Row(104, 2)])
                raise AssertionError(f"Unexpected execution: {stmt!r}")

        class _FakeQuery(tuple):
            def limit(self, _n: int):
                return self

        def _window_query(candidate_filter):
            if isinstance(candidate_filter, frozenset):
                return _FakeQuery(("WINDOW", candidate_filter))
            # ``over_ids(slice_ids)`` passes ``FuturesMarket.id == any_(...)``.
            return _FakeQuery(("OVER_IDS", str(candidate_filter)))

        db = _DB()
        rows, state = await ev._fetch_futures_window(
            db,
            _window_query,
            lambda arms: frozenset(arms),
            ["name"],
            "outcome",
            ev.time.monotonic() + 30.0,
            slice_query=lambda arms: ("SLICE", tuple(arms)),
        )
        assert state == "merged"
        if not fallback_to_full:
            assert [r.id for r in rows] == [1, 101, 102]
            assert ("WINDOW", frozenset(["outcome"])) not in ran
            assert ("SLICE", ("outcome",)) in ran
        else:
            assert [r.id for r in rows] == [1, 101, 102, 103, 104]
            assert ("WINDOW", frozenset(["outcome"])) in ran
