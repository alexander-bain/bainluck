"""#12529: the event page's Bigger Picture stops waiting on the season-market scan.

The slow-event ring names each slow request's slowest statement since #12546. In
the hour after that went live (Nov 10), the season-market discovery scan was the
slowest statement of six `/api/events/{id}/related-futures` reads: 12 s, 18.5 s,
21.6 s, 23.0 s, 29.5 s and 67.5 s. Each was a reader who found the slot expired
(it lives `TTL_FOUND` = 5 minutes) and waited for the whole scan.

A non-empty answer now also keeps a copy for `STALE_TTL`. When the slot has
expired, the reader is served the copy, and one background refresh, taken by
whoever wins the slot's build lease without waiting, runs the same
`_discover_season_market_ids` and republishes.

The route checks drive the real `_build_related_futures` against a session that
RECORDS every statement, so "served the copy" means the scan was not issued in
the request, not that a cache was merely read.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.routes import events as events_route
from app.utils import season_market_discovery as smd


class _FakeRedis:
    """get / setex / delete, plus the NX set and compare-and-delete a lease uses."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def delete(self, k):
        self.store.pop(k, None)

    def exists(self, k):
        return int(k in self.store)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        self.ttls[k] = ex
        return True

    def eval(self, _script, _n, key, token):
        held = self.store.get(key)
        if held is not None and held.decode() == token:
            del self.store[key]
            return 1
        return 0

    def pipeline(self):
        rc = self

        class _Pipe:
            def incr(self, *a, **k):
                return self

            def expire(self, *a, **k):
                return self

            def execute(self):
                return []

        return _Pipe()


# The real clock, offset only: the build asks `_event_is_really_finished` with
# `datetime.now()`, and an event three hours ahead of now is live on any date.
_NOW = datetime.now(timezone.utc)


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """Answers the short path through `_build_related_futures` and records SQL."""

    def __init__(self, event, tier_rows):
        self.event = event
        self.tier_rows = tier_rows
        self.statements: list[str] = []

    async def execute(self, stmt):
        sql = str(stmt)
        self.statements.append(sql)
        if "FROM events" in sql:
            return _Result(scalar=self.event)
        # Before the sports branch: a competition scope adds a `FROM sports`
        # subquery to the discovery statement itself.
        if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
            return _Result(rows=self.tier_rows)
        if "FROM sports" in sql:
            return _Result(rows=[SimpleNamespace(id=7)])
        return _Result(rows=[])

    @property
    def discovery_calls(self) -> int:
        return sum(
            1
            for s in self.statements
            if s.startswith("SELECT futures_markets.id, futures_markets.market_tier")
        )


def _event(sport_key: str, status: str = "scheduled"):
    return SimpleNamespace(
        id=101,
        sport=SimpleNamespace(id=7, key=sport_key),
        sport_id=7,
        status=status,
        home_team_name=None,
        away_team_name=None,
        commence_time=_NOW + timedelta(hours=3),
    )


def _tier_rows():
    return [SimpleNamespace(id=11, market_tier=1), SimpleNamespace(id=12, market_tier=2)]


async def _build(session, debug=False):
    return await events_route._build_related_futures(session.event.id, session, debug=debug)


@pytest.fixture
def scheduled(monkeypatch):
    """Records each refresh the route asks for instead of starting one."""
    calls = []

    def fake(db, sport_key, event_is_finished, base_season_filters):
        calls.append((sport_key, event_is_finished, len(base_season_filters)))
        return None

    monkeypatch.setattr(events_route, "_schedule_season_rebuild", fake)
    return calls


# ---------------------------------------------------------------------------
# The cache module
# ---------------------------------------------------------------------------


def test_a_non_empty_answer_keeps_a_stale_copy_for_stale_ttl():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [7, 8], rc=rc)
    assert rc.ttls[smd.cache_key("baseball_mlb", False)] == smd.TTL_FOUND
    assert rc.ttls[smd.stale_key("baseball_mlb", False)] == smd.STALE_TTL
    assert smd.read_stale("baseball_mlb", False, rc=rc) == [7, 8]
    assert smd.STALE_TTL > smd.TTL_FOUND


def test_an_empty_answer_keeps_no_copy_so_a_sport_is_never_held_at_none():
    rc = _FakeRedis()
    smd.write("boxing_boxing", False, [], rc=rc)
    assert smd.stale_key("boxing_boxing", False) not in rc.store
    # Even a stored empty list never comes back from the stale read.
    rc.setex(smd.stale_key("boxing_boxing", False), 60, "[]")
    assert smd.read_stale("boxing_boxing", False, rc=rc) is None


def test_an_empty_build_deletes_the_copy_so_a_sport_whose_markets_are_gone_reads_empty():
    """Fable's required change on #12563: non-empty, then empty, then the fresh
    slot expires. That must read as a miss with no copy, as on master, not
    hand the old list back for six hours."""
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [7, 8], rc=rc)
    smd.write("baseball_mlb", False, [], rc=rc)
    rc.delete(smd.cache_key("baseball_mlb", False))
    assert smd.read("baseball_mlb", False, rc=rc) is None
    assert smd.read_stale("baseball_mlb", False, rc=rc) is None
    assert smd.stale_key("baseball_mlb", False) not in rc.store


def test_the_fresh_read_never_returns_the_stale_copy():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [7], rc=rc)
    rc.delete(smd.cache_key("baseball_mlb", False))  # the slot expires
    assert smd.read("baseball_mlb", False, rc=rc) is None
    assert smd.read_stale("baseball_mlb", False, rc=rc) == [7]


def test_the_copy_is_per_shape():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [7], rc=rc)
    assert smd.read_stale("baseball_mlb", True, rc=rc) is None


def test_try_claim_takes_a_free_lease_once_and_never_waits():
    rc = _FakeRedis()
    first = smd.try_claim("baseball_mlb", False, rc=rc)
    assert first is not None and first.token
    assert smd.try_claim("baseball_mlb", False, rc=rc) is None  # held: no wait, no copy
    assert smd.release_build(first, rc=rc) is True
    assert smd.try_claim("baseball_mlb", False, rc=rc) is not None


def test_a_refresh_lease_outlives_the_refresh_s_statement_timeout():
    """A refresh is over, done or cancelled by Postgres, before its lease can
    lapse, so a slow one never lets a second one start."""
    rc = _FakeRedis()
    lease = smd.try_claim("baseball_mlb", False, rc=rc)
    assert rc.ttls[lease.key] == smd.REFRESH_LEASE_TTL_SECONDS
    assert smd.REFRESH_STATEMENT_TIMEOUT_MS / 1000 < smd.REFRESH_LEASE_TTL_SECONDS
    assert smd.REFRESH_STATEMENT_TIMEOUT_MS / 1000 > 67.5  # the slowest scan measured


@pytest.mark.asyncio
async def test_a_bounded_scan_sets_its_timeout_before_the_scan_and_the_request_path_does_not():
    bounded = _RecordingSession(_event("baseball_mlb"), _tier_rows())
    assert await events_route._discover_season_market_ids(
        bounded, [], statement_timeout_ms=120_000
    ) == [11, 12]
    assert bounded.statements[0] == "SET LOCAL statement_timeout = 120000"
    assert bounded.discovery_calls == 1
    plain = _RecordingSession(_event("baseball_mlb"), _tier_rows())
    await events_route._discover_season_market_ids(plain, [])
    assert not any("statement_timeout" in s for s in plain.statements)


def test_try_claim_without_redis_is_none_not_a_fail_open_lease():
    """The stale reader already has ids. With no Redis it must NOT start a
    refresh: `acquire` fails open, and every reader would start one."""
    with patch.object(smd, "_client", lambda: None):
        assert smd.try_claim("baseball_mlb", False) is None


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_expired_slot_with_a_copy_is_served_without_the_scan(scheduled):
    """🔴 The load-bearing check: the reader who used to wait 12-67 s."""
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [11, 12], rc=rc)
    rc.delete(smd.cache_key("baseball_mlb", False))
    with patch.object(smd, "_client", lambda: rc):
        session = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(session)
    assert session.discovery_calls == 0, "the reader waited on the scan despite a copy"
    assert [c[:2] for c in scheduled] == [("baseball_mlb", False)]


@pytest.mark.asyncio
async def test_a_fresh_slot_starts_no_refresh(scheduled):
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [11, 12], rc=rc)
    with patch.object(smd, "_client", lambda: rc):
        session = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(session)
    assert session.discovery_calls == 0
    assert scheduled == []


@pytest.mark.asyncio
async def test_with_no_copy_the_reader_builds_as_before_and_leaves_one(scheduled):
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        session = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(session)
    assert session.discovery_calls == 1
    assert scheduled == []
    assert smd.read_stale("baseball_mlb", False, rc=rc) == [11, 12]


@pytest.mark.asyncio
async def test_debug_never_reads_the_copy(scheduled):
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [999], rc=rc)
    rc.delete(smd.cache_key("baseball_mlb", False))
    with patch.object(smd, "_client", lambda: rc):
        session = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(session, debug=True)
    assert session.discovery_calls == 1
    assert scheduled == []


@pytest.mark.asyncio
async def test_a_copy_the_competition_scope_rejects_is_rebuilt_in_the_request(scheduled):
    """The copy gets the same #10319 re-check as a fresh slot: a contaminated
    copy is rebuilt here, and no refresh is scheduled for it."""
    rc = _FakeRedis()
    smd.write("soccer_italy_serie_a_women", False, [11, 12], rc=rc)
    rc.delete(smd.cache_key("soccer_italy_serie_a_women", False))
    with patch.object(smd, "_client", lambda: rc):
        # The recording session answers the scope re-check with no rows, so
        # the copy's ids fail it.
        session = _RecordingSession(_event("soccer_italy_serie_a_women"), _tier_rows())
        await _build(session)
    assert session.discovery_calls == 1
    assert scheduled == []


# ---------------------------------------------------------------------------
# The refresh itself
# ---------------------------------------------------------------------------


def _db():
    """A session-like object bound to a real (never connected) async engine."""
    engine = create_async_engine("postgresql+asyncpg://u:p@localhost:1/x", pool_size=5)
    return SimpleNamespace(bind=engine)


@pytest.mark.asyncio
async def test_the_refresh_republishes_through_the_shared_scan_and_releases(monkeypatch):
    rc = _FakeRedis()
    seen = []

    async def fake_scan(db, filters, statement_timeout_ms=None):
        seen.append(list(filters))
        timeouts.append(statement_timeout_ms)
        return [21, 22]

    timeouts = []

    monkeypatch.setattr(events_route, "_discover_season_market_ids", fake_scan)
    with patch.object(smd, "_client", lambda: rc):
        task = events_route._schedule_season_rebuild(_db(), "baseball_mlb", False, ["f1", "f2"])
        assert task is not None
        # A second reader while it runs starts nothing.
        assert events_route._schedule_season_rebuild(_db(), "baseball_mlb", False, ["f1"]) is None
        await task
    assert seen == [["f1", "f2"]]
    assert timeouts == [smd.REFRESH_STATEMENT_TIMEOUT_MS]
    assert smd.read("baseball_mlb", False, rc=rc) == [21, 22]
    assert smd.read_stale("baseball_mlb", False, rc=rc) == [21, 22]
    assert smd.try_claim("baseball_mlb", False, rc=rc) is not None, "lease was not released"


@pytest.mark.asyncio
async def test_a_failed_refresh_releases_the_lease_and_keeps_the_copy(monkeypatch):
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [11], rc=rc)
    rc.delete(smd.cache_key("baseball_mlb", False))

    async def boom(db, filters, statement_timeout_ms=None):
        raise RuntimeError("statement timeout")

    monkeypatch.setattr(events_route, "_discover_season_market_ids", boom)
    with patch.object(smd, "_client", lambda: rc):
        task = events_route._schedule_season_rebuild(_db(), "baseball_mlb", False, [])
        await asyncio.gather(task, return_exceptions=True)
    assert smd.read_stale("baseball_mlb", False, rc=rc) == [11]
    assert smd.try_claim("baseball_mlb", False, rc=rc) is not None, "lease was not released"


def test_a_full_pool_starts_no_refresh(monkeypatch):
    rc = _FakeRedis()
    db = _db()
    monkeypatch.setattr(type(db.bind.pool), "checkedout", lambda self: 5)
    with patch.object(smd, "_client", lambda: rc):
        assert events_route._schedule_season_rebuild(db, "baseball_mlb", False, []) is None
    assert smd.try_claim("baseball_mlb", False, rc=rc) is not None, "a skipped refresh took the lease"


def test_a_session_without_an_async_engine_starts_no_refresh():
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        assert events_route._schedule_season_rebuild(
            SimpleNamespace(), "baseball_mlb", False, []
        ) is None
