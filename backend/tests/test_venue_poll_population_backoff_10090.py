"""#10090 — a failed population read is never re-run by the next tick.

The population statement runs under a 20 s ``statement_timeout`` and the beat
fires every 30 s. Before this guard a timed-out read cached nothing and started
no backoff, so every tick, on any of worker-realtime's four processes, re-ran
the same 20 s statement for as long as the venue stayed on. Now a failure starts
a backoff shared by every process (Redis), with a process-local floor for when
Redis is unreadable; until it lapses the process's last population stands in,
or the venue sits the pass out. Both read ``partial``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.tasks import venue_poll_30s as v

VENUE = "polymarket"
T0 = 10_000.0


class _Timeout(Exception):
    """Stands in for asyncpg's QueryCanceledError through SQLAlchemy."""


class _Redis:
    """The backoff keys only; a key lives until the test lapses it."""

    def __init__(self):
        self.kv: dict = {}
        self.ttls: dict = {}

    def ttl(self, key):
        return self.ttls.get(key, -2)

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def expire(self, *_a):
        return True

    def set(self, key, value, ex=None):
        self.kv[key] = value
        self.ttls[key] = ex

    def delete(self, key):
        self.kv.pop(key, None)
        self.ttls.pop(key, None)

    def lapse(self):
        for key in [k for k in self.ttls if k.endswith(":backoff")]:
            self.ttls.pop(key)
            self.kv.pop(key, None)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    def __init__(self, *, fail):
        self.fail = fail
        self.population_reads = 0
        self.rollbacks = 0

    async def execute(self, *_a, **_k):
        self.population_reads += 1
        if self.fail:
            raise _Timeout("canceling statement due to statement timeout")
        return _Rows([(1, "9001", 11, "0xabc")])

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _wired(monkeypatch):
    monkeypatch.setattr(v, "_POPULATION", {})
    monkeypatch.setattr(v, "_POPULATION_RETRY_AT", {})
    monkeypatch.setattr(v, "polymarket_population_sql", lambda *_a, **_k: "SELECT 1")
    monkeypatch.setattr(v, "_polymarket_open_arm", lambda: True)
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "population_binds", lambda *_a, **_k: {})
    redis = _Redis()
    monkeypatch.setattr(v, "_redis", lambda: redis)
    return redis


def _stale_units():
    return [v.Unit("9001", {1: [(11, "0xabc")]})]


@pytest.mark.asyncio
async def test_a_failed_read_with_nothing_cached_backs_off_and_no_tick_reruns_it(_wired):
    session = _Session(fail=True)
    stats: dict = {"errors": []}
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=T0, stats=stats)
    assert stats["population_backoff_started_s"] == v.BACKOFF_BASE_S

    # The next ticks, on this process or another (the backoff is in Redis).
    for later in (T0 + 30, T0 + 31):
        v._POPULATION_RETRY_AT.clear()  # another process: only Redis holds it back
        with pytest.raises(v.PopulationBackoff):
            await v.load_population(session, VENUE, now_mono=later, stats={})
    assert session.population_reads == 1


@pytest.mark.asyncio
async def test_a_failed_read_reuses_the_last_population_on_a_clean_transaction(_wired):
    units = _stale_units()
    v._POPULATION[VENUE] = (T0 - v.POPULATION_TTL_S - 1, units)
    session = _Session(fail=True)
    stats: dict = {"errors": []}

    got = await v.load_population(session, VENUE, now_mono=T0, stats=stats)
    assert got is units
    assert stats["population_stale"] is True
    assert stats["errors"] and stats["errors"][0].startswith("population: ")
    assert session.rollbacks == 1  # the aborted transaction is not reused

    again: dict = {}
    assert await v.load_population(session, VENUE, now_mono=T0 + 30, stats=again) is units
    assert again["population_stale"] is True
    assert session.population_reads == 1


@pytest.mark.asyncio
async def test_unreadable_redis_still_holds_this_process_back(monkeypatch):
    def _down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(v, "_redis", _down)
    session = _Session(fail=True)
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=T0, stats={})
    with pytest.raises(v.PopulationBackoff):
        await v.load_population(session, VENUE, now_mono=T0 + v.BACKOFF_BASE_S - 1, stats={})
    assert session.population_reads == 1
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=T0 + v.BACKOFF_BASE_S + 1, stats={})
    assert session.population_reads == 2


@pytest.mark.asyncio
async def test_a_good_read_after_the_backoff_resets_it(_wired):
    session = _Session(fail=True)
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=T0, stats={})
    _wired.lapse()
    session.fail = False
    stats: dict = {}
    units = await v.load_population(
        session, VENUE, now_mono=T0 + v.BACKOFF_BASE_S + 1, stats=stats
    )
    assert [u.key for u in units] == ["9001"]
    assert stats["population_cached"] is False and "population_read_s" in stats
    assert not any(k.endswith("backoff_level") for k in _wired.kv)

    # A later failure starts again from the base, not from level 2.
    session.fail = True
    later: dict = {}
    v._POPULATION.clear()
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=T0 + 999, stats=later)
    assert later["population_backoff_started_s"] == v.BACKOFF_BASE_S


@pytest.mark.asyncio
async def test_a_fresh_population_touches_neither_redis_nor_the_database(monkeypatch):
    units = _stale_units()
    v._POPULATION[VENUE] = (T0, units)

    def _no_redis():
        raise AssertionError("a fresh population reads no backoff")

    monkeypatch.setattr(v, "_redis", _no_redis)
    session = _Session(fail=True)
    stats: dict = {}
    assert await v.load_population(session, VENUE, now_mono=T0 + 1, stats=stats) is units
    assert stats == {"population_cached": True}
    assert session.population_reads == 0


@pytest.mark.asyncio
async def test_the_pass_reads_error_then_population_backoff_as_partial(monkeypatch, _wired):
    session = _Session(fail=True)

    @asynccontextmanager
    async def _task_session(**_k):
        yield session

    class _Service:
        async def close(self):
            pass

    monkeypatch.setattr("app.tasks.base.get_task_session", _task_session)
    monkeypatch.setattr(v, "_new_service", lambda _venue: _Service())

    first = await v.poll_venue_prices([VENUE])
    assert first[VENUE]["stopped"] == "error"
    assert first[VENUE]["population_backoff_started_s"] == v.BACKOFF_BASE_S
    assert first["terminal"] == "failed"

    v._POPULATION_RETRY_AT.clear()  # the next tick lands on another process
    second = await v.poll_venue_prices([VENUE])
    assert second[VENUE]["stopped"] == "population_backoff"
    assert second["terminal"] == "partial"
    assert session.population_reads == 1
