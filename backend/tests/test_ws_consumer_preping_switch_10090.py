"""#10090 — the consumer engine's pre-ping is a setting, and set_lock says what it held.

`WS_CONSUMER_POOL_PRE_PING` (read once at import, default on) turns off the
pool's pre-ping on the socket consumers' engine only. On asyncpg the ping is
three round trips (BEGIN, ``;``, ROLLBACK) on every checkout, and a Kalshi price
phase checks out once, so it is three of the five round trips the phase's
`set_lock` span waits on. Off, a connection the server closed is found by the
phase's first statement instead: the phase rolls back and its prices stay
buffered for the next flush (`test_a_disconnect_on_the_first_statement_...`);
the real-Postgres half (`tests/integration/test_ws_consumer_preping_10090_pg.py`)
proves the round trips go, the invalidation and the reconnect.

The stats line splits `db.set_lock` by the consumer engine's own pool events:
`[checkout=… full_at_start=K/P connects=N connect=… set=…]`.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DBAPIError

import app.tasks.base as task_base
import app.tasks.ws_consumer_sessions as wcs
from app.tasks.kalshi_ws import _FlushTimings
from tests.test_kalshi_flush_wait_attribution_10090 import (  # noqa: F401 — fixtures
    _timings_read_the_loop_clock,
    _VirtualClockLoop,
    event_loop_policy,
    rig,
    tick,
)

BACKEND = Path(__file__).resolve().parents[1]
NAME = "WS_CONSUMER_POOL_PRE_PING"
UNREACHABLE_PG = "postgresql+asyncpg://u:p@db.invalid:5432/x"

pytestmark = pytest.mark.asyncio


def _parsed(monkeypatch, raw):
    monkeypatch.setenv(NAME, raw)
    return wcs._pre_ping_env(NAME, True)


# ------------------------------------------------------------ the setting ----


async def test_missing_or_blank_is_on_without_a_warning(monkeypatch, caplog):
    monkeypatch.delenv(NAME, raising=False)
    with caplog.at_level(logging.WARNING, logger=wcs.logger.name):
        assert wcs._pre_ping_env(NAME, True) is True
        assert _parsed(monkeypatch, "") is True
        assert _parsed(monkeypatch, "   ") is True
    assert not caplog.records


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", " yes ", "on"])
async def test_true_spellings(monkeypatch, raw):
    assert _parsed(monkeypatch, raw) is True


@pytest.mark.parametrize("raw", ["0", "false", "False", " no ", "OFF"])
async def test_false_spellings(monkeypatch, raw):
    assert _parsed(monkeypatch, raw) is False


@pytest.mark.parametrize("raw", ["maybe", "2", "f", "disable"])
async def test_invalid_is_on_with_one_warning(monkeypatch, caplog, raw):
    with caplog.at_level(logging.WARNING, logger=wcs.logger.name):
        assert _parsed(monkeypatch, raw) is True
    assert len(caplog.records) == 1
    assert "not a valid boolean" in caplog.records[0].getMessage()


def _imported(env_value):
    """The consumer, Celery and web engines' pre-ping as a fresh process sees them."""
    env = {k: v for k, v in os.environ.items() if k != NAME}
    if env_value is not None:
        env[NAME] = env_value
    env["DATABASE_URL"] = UNREACHABLE_PG
    code = (
        "import logging; logging.basicConfig(level=logging.INFO)\n"
        "import json, app.tasks.ws_consumer_sessions as w, app.tasks.base as b, "
        "app.services.database as d\n"
        "c = w._consumer_engine(); t = b._get_task_engine()\n"
        "print(json.dumps([w.CONSUMER_POOL_PRE_PING, c.sync_engine.pool._pre_ping, "
        "t.sync_engine.pool._pre_ping, d.engine.sync_engine.pool._pre_ping]))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1]), out.stderr


async def test_default_at_import_is_todays_engine():
    (setting, consumer, celery, web), _ = _imported(None)
    assert (setting, consumer, celery, web) == (True, True, True, True)


async def test_off_at_import_turns_off_the_consumer_engine_only():
    (setting, consumer, celery, web), stderr = _imported("0")
    assert setting is False and consumer is False
    assert celery is True and web is True  # never the Celery or web engines
    assert "consumer engine pool_pre_ping=False" in stderr


async def test_invalid_at_import_is_on_with_a_warning():
    (setting, consumer, *_), stderr = _imported("sometimes")
    assert setting is True and consumer is True
    assert f"{NAME}='sometimes'" in stderr


# ------------------------------------------ the factory call, default vs off ----


@pytest.fixture
def factory_calls(monkeypatch):
    monkeypatch.setattr(task_base, "DATABASE_URL", UNREACHABLE_PG)
    monkeypatch.setattr(wcs, "_PRE_PING_LOGGED", False)
    real = task_base._get_task_engine
    calls = []

    def recording(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(task_base, "_get_task_engine", recording)
    return calls


async def test_on_asks_the_factory_exactly_what_it_asked_before(
    monkeypatch, factory_calls,
):
    monkeypatch.setattr(wcs, "CONSUMER_POOL_PRE_PING", True)
    sessions = wcs.ConsumerSessions("t")
    engine = sessions._engine_here()
    try:
        assert factory_calls == [{"retain_full_pool": True}]
        pool = engine.sync_engine.pool
        assert pool._pre_ping is True and pool._recycle == 1800
        assert pool.size() == 5 and pool._max_overflow == 0
    finally:
        await sessions.aclose()


async def test_off_changes_only_the_pre_ping(monkeypatch, factory_calls):
    monkeypatch.setattr(wcs, "CONSUMER_POOL_PRE_PING", False)
    sessions = wcs.ConsumerSessions("t")
    engine = sessions._engine_here()
    try:
        assert factory_calls == [{"retain_full_pool": True, "pool_pre_ping": False}]
        pool = engine.sync_engine.pool
        assert pool._pre_ping is False
        assert pool._recycle == 1800  # unchanged
        assert pool.size() == 5 and pool._max_overflow == 0
    finally:
        await sessions.aclose()


async def test_one_start_line_per_process(monkeypatch, factory_calls, caplog):
    monkeypatch.setattr(wcs, "CONSUMER_POOL_PRE_PING", False)
    with caplog.at_level(logging.INFO, logger=wcs.logger.name):
        for label in ("kalshi", "polymarket", "kalshi"):
            sessions = wcs.ConsumerSessions(label)
            sessions._engine_here()
            await sessions.aclose()
    lines = [r.getMessage() for r in caplog.records if "pool_pre_ping=" in r.getMessage()]
    assert lines == [
        "ws_consumer_sessions: consumer engine pool_pre_ping=False "
        "(WS_CONSUMER_POOL_PRE_PING)"
    ]


# --------------------------------------------------------- the probe ----


class _Pool:
    def __init__(self, out, size=5, overflow=0):
        self.out, self._size, self._max_overflow = out, size, overflow

    def checkedout(self):
        return self.out

    def size(self):
        return self._size


def _engine(pool):
    return SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))


async def test_the_set_lock_split_reads_the_pool_events_on_the_flush_clock():
    """Queue wait 0.1, connect 0.2, then the SET 0.05; a second span on a
    pooled connection waits 0.03 and sets 0.02. `full_at_start` counts the
    span that began with all five slots out. Virtual clock: exact."""
    assert isinstance(asyncio.get_running_loop(), _VirtualClockLoop)
    pool = _Pool(out=5)
    t = _FlushTimings()
    token = wcs._SESSION_ENGINE.set(_engine(pool))
    try:
        async with t.waited("db"):
            async with t.waited("set_lock"):
                await asyncio.sleep(0.1)
                wcs._probe_connect_started()
                await asyncio.sleep(0.2)
                wcs._probe_connected()
                wcs._probe_checked_out()
                await asyncio.sleep(0.05)
        pool.out = 2
        async with t.waited("db"):
            async with t.waited("set_lock"):
                await asyncio.sleep(0.03)
                wcs._probe_checked_out()
                wcs._probe_checked_out()  # only the first hand-over counts
                await asyncio.sleep(0.02)
    finally:
        wcs._SESSION_ENGINE.reset(token)
    t.flushed(1.0)
    assert t.slowest_db["set_lock"] == pytest.approx(0.4)
    assert t.slowest_lock["checkout"] == pytest.approx(0.33)
    assert t.slowest_lock["set"] == pytest.approx(0.07)
    assert t.slowest_lock["connect"] == pytest.approx(0.2)
    assert (t.slowest_lock["full"], t.slowest_lock["spans"]) == (1, 2)
    assert t.slowest_lock["connects"] == 1
    assert (
        "db.set_lock=0.40s[checkout=0.33s full_at_start=1/2 connects=1 "
        "connect=0.20s set=0.07s] db.save=0.00s"
    ) in t.line()


async def test_no_pool_events_is_all_set_and_nothing_outside_a_span_lands():
    t = _FlushTimings()
    wcs._probe_connect_started()  # no span: recorded nowhere
    wcs._probe_connected()
    wcs._probe_checked_out()
    async with t.waited("set_lock"):
        await asyncio.sleep(0.05)
    t.flushed(0.05)
    assert t.slowest_lock == {
        "checkout": 0.0, "full": 0, "spans": 1, "connects": 0, "connect": 0.0,
        "set": pytest.approx(0.05),
    }


async def test_a_concurrent_tasks_pool_events_never_land_in_this_span():
    """A refresher or stamp task checks out on the same engine while this
    flush's span is open: its own context, so its events are not this span's."""
    t = _FlushTimings()
    span_open, other_done = asyncio.Event(), asyncio.Event()

    async def other_task():
        await span_open.wait()
        wcs._probe_connect_started()
        await asyncio.sleep(0.01)
        wcs._probe_connected()
        wcs._probe_checked_out()
        other_done.set()

    task = asyncio.create_task(other_task())  # started before the span, as they are
    async with t.waited("set_lock"):
        span_open.set()
        await other_done.wait()
        await asyncio.sleep(0.02)
    await task
    t.flushed(0.1)
    assert t.slowest_lock["connects"] == 0 and t.slowest_lock["checkout"] == 0.0


@pytest.mark.parametrize("out,overflow,full", [(5, 0, True), (4, 0, False),
                                               (5, 2, False), (7, 2, True),
                                               (50, -1, False)])
async def test_full_means_every_permitted_slot_is_out(out, overflow, full):
    assert wcs._pool_full(_Pool(out, overflow=overflow)) is full


async def test_the_split_stays_with_the_slowest_flush():
    t = _FlushTimings()
    async with t.waited("set_lock"):
        wcs._probe_checked_out()
        await asyncio.sleep(0.2)
    t.flushed(2.0)
    async with t.waited("set_lock"):
        await asyncio.sleep(0.05)
        wcs._probe_checked_out()
    t.flushed(1.0)  # shorter: not the minute's slowest
    assert t.slowest_lock["set"] == pytest.approx(0.2)
    assert t.slowest_lock["checkout"] == 0.0
    t.reset()
    assert t.slowest_lock is None and t.line().endswith(" slowest -")


async def test_a_session_engine_marks_only_its_own_body():
    """`ConsumerSessions.session()` names its engine to the probe for its
    body alone; outside it `full_at_start` is never read from a stale pool."""
    seen = []

    class _Ctx:
        async def __aenter__(self):
            seen.append(wcs._SESSION_ENGINE.get())
            return SimpleNamespace()

        async def __aexit__(self, *_e):
            return False

    sessions = wcs.ConsumerSessions("t")
    marker = object()
    sessions._engine = marker
    sessions._loop = asyncio.get_running_loop()
    sessions._pid = os.getpid()
    original = task_base.get_task_session
    task_base.get_task_session = lambda **_kw: _Ctx()
    try:
        async with sessions.session():
            assert wcs._SESSION_ENGINE.get() is marker
    finally:
        task_base.get_task_session = original
        sessions._disposed = True  # the marker is not an engine
    assert seen == [marker] and wcs._SESSION_ENGINE.get() is None


async def test_a_probe_that_cannot_install_never_stops_the_engine(monkeypatch, caplog):
    engine = SimpleNamespace(sync_engine=object())  # no events on this target
    monkeypatch.setattr(task_base, "_get_task_engine", lambda **_kw: engine)
    with caplog.at_level(logging.WARNING, logger=wcs.logger.name):
        assert wcs._consumer_engine() is engine
    assert any("checkout probe not installed" in r.getMessage() for r in caplog.records)


# ------------------------------- a disconnect on the phase's first statement ----


class _Closed(Exception):
    """What asyncpg raises on a connection the server closed."""


async def test_a_disconnect_on_the_first_statement_rolls_back_and_keeps_the_prices():
    """Pre-ping off: the phase's SET is the first statement on a dead
    connection. SQLAlchemy raises it as a DBAPIError with the connection
    invalidated. The phase commits nothing, publishes nothing, writes no
    price; both prices stay buffered and the next flush writes them."""
    failures = [
        DBAPIError("SELECT set_config('lock_timeout', $1, true)", None,
                   _Closed("connection is closed"), connection_invalidated=True),
    ]

    async def first_statement():
        if failures:
            raise failures.pop(0)

    commits = []
    r = rig(games=1, set_lock=first_statement, on_commit=lambda: commits.append(1))
    published = []
    original_publish = r.refresher.publish_market_changes

    async def publish(session):
        published.append(session)
        return await original_publish(session)

    r.refresher.publish_market_changes = publish
    tick(r, 0)
    await r.flush()
    assert set(r.buffer) == {0, 1}
    assert r.stats["errors"] == 1 and r.stats["requeued"] == 2
    assert r.stats["price_updates"] == 0
    assert commits == [] and published == []
    await r.flush()
    assert not r.buffer and r.stats["price_updates"] == 2 and commits == [1]
    if r.prices.stamping is not None:
        await asyncio.wait({r.prices.stamping})
