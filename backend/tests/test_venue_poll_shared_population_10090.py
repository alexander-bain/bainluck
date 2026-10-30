"""#10090 — the poll's population is read once per TTL for the whole fleet.

The first Polymarket switch-on (2026-10-30 21:29–21:41Z) ran 19 passes on 19
different worker-realtime children: ``--max-memory-per-child`` replaces a child
after about every pass, so the 300 s per-process cache never hit and the
population statement ran on every pass (pg_stat_statements: 19 calls, mean
4.2 s, max 19.9 s against its 20 s statement timeout). A read is now published
to Redis and any process takes it while it is fresh; a failed read's backoff
reuses the fleet's copy, not only the failing process's own.
"""

from __future__ import annotations

import types
import zlib
from contextlib import asynccontextmanager

import pytest

from app.tasks import venue_poll_30s as v

VENUE = "polymarket"
T0 = 50_000.0


class _Timeout(Exception):
    """Stands in for asyncpg's QueryCanceledError through SQLAlchemy."""


class _Redis:
    """Byte values with TTLs, like redis-py without decode_responses."""

    def __init__(self):
        self.kv: dict = {}
        self.ttls: dict = {}
        self.sets: list = []

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, ex=None):
        self.kv[key] = value
        self.ttls[key] = ex
        self.sets.append(key)

    def ttl(self, key):
        return self.ttls.get(key, -2) if key in self.kv else -2

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def expire(self, *_a):
        return True

    def delete(self, key):
        self.kv.pop(key, None)
        self.ttls.pop(key, None)

    def lapse_backoff(self):
        for key in [k for k in self.kv if k.endswith(":backoff")]:
            self.delete(key)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


ROWS = [(1, "9001", 11, "0xabc"), (1, "9001", 12, "0xabc_no"), (2, "9002", 21, "0xdef")]


class _Session:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.population_reads = 0

    async def execute(self, *_a, **_k):
        self.population_reads += 1
        if self.fail:
            raise _Timeout("canceling statement due to statement timeout")
        return _Rows(list(ROWS))

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _Clock:
    def __init__(self, at):
        self.at = at

    def time(self):
        return self.at

    def monotonic(self):
        return self.at


@pytest.fixture
def clock(monkeypatch):
    c = _Clock(T0)
    monkeypatch.setattr(v, "time", types.SimpleNamespace(time=c.time, monotonic=c.monotonic))
    return c


@pytest.fixture(autouse=True)
def redis(monkeypatch):
    monkeypatch.setattr(v, "_POPULATION", {})
    monkeypatch.setattr(v, "_POPULATION_RETRY_AT", {})
    monkeypatch.setattr(v, "_POPULATION_FAILS", {})
    monkeypatch.setattr(v, "polymarket_population_sql", lambda *_a, **_k: "SELECT pm /* open */")
    monkeypatch.setattr(v, "_polymarket_open_arm", lambda: True)
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "population_binds", lambda *_a, **_k: {})
    fake = _Redis()
    monkeypatch.setattr(v, "_redis", lambda: fake)
    return fake


def _new_process():
    """A replaced worker child: no module state, only Redis survives."""
    v._POPULATION.clear()
    v._POPULATION_RETRY_AT.clear()
    v._POPULATION_FAILS.clear()


def _keys(units):
    return [(u.key, sorted(u.legs.items())) for u in units]


@pytest.mark.asyncio
async def test_a_new_child_every_pass_reads_the_statement_once_per_ttl(clock):
    """The measured case: every 30 s tick on a fresh child."""
    session = _Session()
    first = None
    for i in range(10):  # 0 .. 270 s
        _new_process()
        clock.at = T0 + 30 * i
        stats: dict = {}
        units = await v.load_population(session, VENUE, now_mono=clock.at, stats=stats)
        first = first or _keys(units)
        assert _keys(units) == first
        if i:
            assert stats["population_shared"] is True
            assert stats["population_age_s"] == 30 * i
    assert session.population_reads == 1

    _new_process()
    clock.at = T0 + v.POPULATION_TTL_S + 1
    stats = {}
    await v.load_population(session, VENUE, now_mono=clock.at, stats=stats)
    assert session.population_reads == 2
    assert stats["population_cached"] is False and "population_shared" not in stats


@pytest.mark.asyncio
async def test_a_copy_read_under_another_socket_scope_is_never_taken(clock, monkeypatch):
    session = _Session()
    await v.load_population(session, VENUE, now_mono=clock.at, stats={})
    # The open arm turned off: tokened markets now belong to the poll.
    monkeypatch.setattr(v, "polymarket_population_sql", lambda *_a, **_k: "SELECT pm /* all */")
    _new_process()
    clock.at += 30
    stats: dict = {}
    await v.load_population(session, VENUE, now_mono=clock.at, stats=stats)
    assert session.population_reads == 2 and "population_shared" not in stats


@pytest.mark.asyncio
async def test_a_failed_read_on_a_fresh_child_reuses_the_fleet_copy_inside_the_backoff(
    clock, redis
):
    good = _Session()
    await v.load_population(good, VENUE, now_mono=clock.at, stats={})
    want = _keys(v._POPULATION[VENUE][1])

    # 400 s later the copy is past fresh; a fresh child's read fails.
    _new_process()
    clock.at = T0 + 400
    bad = _Session(fail=True)
    stats: dict = {}
    with pytest.raises(_Timeout):  # the failing pass still reads `stopped: error`
        await v.load_population(bad, VENUE, now_mono=clock.at, stats=stats)
    assert "population_stale" not in stats

    # The next tick lands on yet another fresh child: the fleet copy stands in.
    _new_process()
    clock.at += 30
    again: dict = {}
    units = await v.load_population(bad, VENUE, now_mono=clock.at, stats=again)
    assert again["population_stale"] is True and _keys(units) == want
    assert bad.population_reads == 1


@pytest.mark.asyncio
async def test_the_newest_stand_in_wins_inside_the_backoff(clock, redis):
    """A process's own older copy never shadows a newer fleet copy."""
    session = _Session()
    await v.load_population(session, VENUE, now_mono=clock.at, stats={})
    v._POPULATION[VENUE] = (clock.at - 1_000, [v.Unit("old", {9: [(99, "0xold")]})])
    clock.at += 400
    session.fail = True
    with pytest.raises(_Timeout):
        await v.load_population(session, VENUE, now_mono=clock.at, stats={})
    clock.at += 30
    units = await v.load_population(session, VENUE, now_mono=clock.at, stats={})
    assert [u.key for u in units] == ["9001", "9002"]


@pytest.mark.asyncio
async def test_a_process_copy_taken_from_the_fleet_expires_with_it(clock):
    session = _Session()
    await v.load_population(session, VENUE, now_mono=clock.at, stats={})
    _new_process()
    clock.at = T0 + v.POPULATION_TTL_S - 10  # takes a copy 290 s old
    stats: dict = {}
    await v.load_population(session, VENUE, now_mono=clock.at, stats=stats)
    assert stats["population_shared"] is True
    clock.at += 20  # the copy is now 310 s old, here as in Redis
    later: dict = {}
    await v.load_population(session, VENUE, now_mono=clock.at, stats=later)
    assert "population_cached" in later and later["population_cached"] is False
    assert session.population_reads == 2


@pytest.mark.asyncio
async def test_the_published_copy_is_compressed_tagged_and_kept_an_hour(clock, redis):
    await v.load_population(_Session(), VENUE, now_mono=clock.at, stats={})
    key = f"{v._KEY_PREFIX}:{VENUE}:population"
    assert redis.ttls[key] == v.POPULATION_SHARED_TTL_S
    doc = v._loads(zlib.decompress(redis.kv[key]))
    assert doc["read_at"] == T0
    assert doc["tag"] == v._population_tag("SELECT pm /* open */")
    assert [tuple(r) for r in doc["rows"]] == ROWS


@pytest.mark.asyncio
async def test_unreadable_or_malformed_redis_reads_the_database(clock, monkeypatch, redis):
    redis.kv[f"{v._KEY_PREFIX}:{VENUE}:population"] = b"not zlib"
    session = _Session()
    assert _keys(await v.load_population(session, VENUE, now_mono=clock.at, stats={}))
    assert session.population_reads == 1

    def _down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(v, "_redis", _down)
    _new_process()
    clock.at += 30
    assert _keys(await v.load_population(session, VENUE, now_mono=clock.at, stats={}))
    assert session.population_reads == 2


@pytest.mark.asyncio
async def test_every_polymarket_pass_says_which_instrument_ran(clock, monkeypatch):
    session = _Session()

    @asynccontextmanager
    async def _task_session(**_k):
        yield session

    class _Service:
        async def close(self):
            pass

    async def _db_clock(_s):
        import datetime as dt

        return dt.datetime.fromtimestamp(clock.at, dt.timezone.utc)

    async def _fetch(*_a, **_k):
        return {}

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("app.tasks.base.get_task_session", _task_session)
    monkeypatch.setattr("app.tasks.venue_poll_pm_clob.pm_source", lambda: "gamma")
    monkeypatch.setattr(v, "_new_service", lambda _venue: _Service())
    monkeypatch.setattr(v, "db_clock", _db_clock)
    monkeypatch.setattr(v, "_fetch_group", _fetch)
    monkeypatch.setattr(v, "_write_group", _noop)
    monkeypatch.setattr(v, "read_cursor", lambda _n: None)
    monkeypatch.setattr(v, "write_cursor", lambda *_a: None)

    out = await v.poll_venue_prices([VENUE])
    assert out[VENUE]["pm_source"] == "gamma"
    assert "clob_stopped" not in out[VENUE]
