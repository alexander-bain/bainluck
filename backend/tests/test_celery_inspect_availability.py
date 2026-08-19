"""LAT-P071: `/api/admin/celery-debug` must not be able to take production down.

THE INCIDENT, because a constant with no story attached gets tuned away.

2026-08-19 05:00–05:03Z. Two read-only samplers polled `/api/admin/celery-debug`
— one every 20s, one every 8s — while measuring the background queue. The entire
API went to HTTP 503 at the 30s H12 ceiling, `/api/health` included, for about
ten minutes. `heroku ps` reported the web dyno `up` throughout, with uptime
unbroken: it never crashed and never restarted. Killing the two pollers restored
p50 to **0.23s within 25 seconds**, four consecutive calls.

The cause is structural, not incidental. `celery_app.control.inspect(...)` is a
BROADCAST: it publishes to a control exchange and blocks until every worker
replies or the timeout expires. The handler made FOUR of them — ping, active,
registered, stats — inline, at `timeout=5`, inside an `async def`. So one request
could occupy the single uvicorn event loop for up to twenty seconds, and a poller
faster than that guaranteed the loop was never free.

Nothing about the endpoint looked dangerous. It is a read-only debug route with
no writes and no auth-destructive guard, which is exactly why it was one
auto-refreshing dashboard tab away from an outage.

These tests pin the three protections. Each one closes a different failure, so
each is asserted separately — a suite that only checks "it still returns JSON"
would let any of them be removed.
"""

import asyncio
import time
from unittest.mock import patch

import pytest

import app.routes.admin_celery as ac


class _SlowInspector:
    """Stands in for a celery inspect object whose broadcasts take real time."""

    calls = 0
    per_call_s = 0.05

    def __init__(self, **_kw):
        pass

    def _answer(self):
        type(self).calls += 1
        time.sleep(self.per_call_s)
        return {"celery@w1": {}}

    ping = active = reserved = registered = stats = property(
        lambda self: self._answer
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    ac._INSPECT_CACHE["at"] = 0.0
    ac._INSPECT_CACHE["data"] = None
    ac._INSPECT_LOCK = None
    _SlowInspector.calls = 0
    # Reset the DELAY too. Leaving it as class state let one test's 0.0 leak into
    # the loop-blocking test, which is half of why the first version of this file
    # survived four of five mutations.
    _SlowInspector.per_call_s = 0.0
    yield
    ac._INSPECT_CACHE["at"] = 0.0
    ac._INSPECT_CACHE["data"] = None
    ac._INSPECT_LOCK = None


def _patched():
    from unittest.mock import MagicMock
    fake_app = MagicMock()
    fake_app.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
    return patch.dict("sys.modules", {}), fake_app


def _run(coro):
    return asyncio.run(coro)


class TestOffTheEventLoop:
    def test_the_broadcasts_do_not_block_the_loop(self):
        # The load-bearing assertion, and the one the first version of this file
        # got WRONG. Counting ticks proves nothing: a blocked loop simply runs
        # all ten of them AFTER the block, so the count is 10 either way and the
        # mutation that put the broadcasts back on the loop survived.
        #
        # What distinguishes the two worlds is the GAP between consecutive ticks.
        # Off-loop, every tick lands ~10ms after the last. On-loop, exactly one
        # gap swallows the whole broadcast set.
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
        _SlowInspector.per_call_s = 0.08  # 5 broadcasts -> ~0.40s of blocking work

        ticks = []
        stop = False

        async def heartbeat():
            while not stop:
                ticks.append(time.perf_counter())
                await asyncio.sleep(0.01)

        async def main():
            with patch("app.tasks.celery_app", fake, create=True):
                hb = asyncio.create_task(heartbeat())
                # Let the heartbeat actually START before the snapshot begins.
                #
                # This `sleep` is the whole test. Without it the mutation
                # survived: an UNCONTENDED `asyncio.Lock` acquires on a fast path
                # without yielding, so `_inspect_snapshot` ran start-to-finish —
                # blocking call included — before the heartbeat task was ever
                # scheduled. The gap then landed BEFORE tick 0, where no
                # inter-tick measurement can see it.
                await asyncio.sleep(0.05)
                await ac._inspect_snapshot()
                hb.cancel()
                try:
                    await hb
                except asyncio.CancelledError:
                    pass

        _run(main())
        # THE COUNT, not the gap — measured both ways before choosing.
        #
        # An inter-tick GAP never forms: when the loop is blocked the heartbeat
        # simply does not tick during the block, and the heartbeat is cancelled
        # as soon as the snapshot returns, so there is no tick AFTER the stall to
        # be the far side of a gap. Probed directly with the mutation applied:
        #   off-loop  -> 44 ticks, max gap 0.024s
        #   on-loop   ->  5 ticks, max gap 0.011s
        # The gap assertion passed in BOTH worlds. The tick RATE separates them
        # by ~9x.
        #
        # ~0.40s of broadcast plus 0.05s of lead-in at a 0.01s tick is ~45 ticks
        # when the loop is free. 20 is a floor with a wide margin on a shared
        # machine, and still four times what a blocked loop produced.
        assert len(ticks) >= 20, (
            f"only {len(ticks)} heartbeat ticks during a ~0.40s broadcast — the "
            "event loop was blocked, so the broadcasts are running on it"
        )


class TestSingleFlight:
    def test_concurrent_callers_share_one_broadcast_set(self):
        # Without this, moving off-loop only relocates the pile-up into the
        # threadpool, where exhausting the default 40 threads stalls every other
        # route that needs one.
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
        _SlowInspector.per_call_s = 0.02

        async def main():
            with patch("app.tasks.celery_app", fake, create=True):
                return await asyncio.gather(*[ac._inspect_snapshot() for _ in range(6)])

        results = _run(main())
        assert len(results) == 6
        # 5 broadcasts for ONE snapshot, not 30 for six.
        assert _SlowInspector.calls == 5


class TestMemoisation:
    def test_a_poller_faster_than_the_ttl_gets_the_cache(self):
        # This is the protection that would actually have prevented the outage:
        # the load there was CADENCE, not concurrency.
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
        _SlowInspector.per_call_s = 0.0

        async def main():
            with patch("app.tasks.celery_app", fake, create=True):
                a = await ac._inspect_snapshot()
                b = await ac._inspect_snapshot()
                c = await ac._inspect_snapshot()
                return a, b, c

        a, b, c = _run(main())
        assert _SlowInspector.calls == 5, "second and third calls must not re-broadcast"
        assert a[1]["cached"] is False
        assert b[1]["cached"] is True and c[1]["cached"] is True

    def test_the_cache_state_is_disclosed_not_hidden(self):
        # A debug endpoint that silently serves a stale snapshot invites
        # conclusions about a moment that has passed. Age is reported so the
        # reader can decide, rather than being reassured by default.
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
        _SlowInspector.per_call_s = 0.0

        async def main():
            with patch("app.tasks.celery_app", fake, create=True):
                await ac._inspect_snapshot()
                ac._INSPECT_CACHE["at"] -= 1.0   # pretend a second has passed
                return await ac._inspect_snapshot()

        _snap, state = _run(main())
        assert state["cached"] is True
        assert state["age_s"] >= 1.0

    def test_the_ttl_is_short_enough_to_be_a_cache_and_not_a_freeze(self):
        # Asserted as a VALUE, not derived from the constant. The first version
        # aged the cache by `TTL + 1`, which self-adjusts — setting the TTL to a
        # billion seconds still "expired" and the mutation survived. A debug
        # endpoint frozen on a five-minute-old snapshot is a different lie from
        # a slow one, and only a literal bound catches it.
        assert 1.0 <= ac._INSPECT_TTL_S <= 30.0

    def test_an_expired_cache_re_broadcasts(self):
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)

        async def main():
            with patch("app.tasks.celery_app", fake, create=True):
                await ac._inspect_snapshot()
                ac._INSPECT_CACHE["at"] -= 31.0   # literal: past any sane TTL
                return await ac._inspect_snapshot()

        _snap, state = _run(main())
        assert state["cached"] is False
        assert _SlowInspector.calls == 10


class TestNoInlineBroadcastsSurvive:
    def test_no_route_handler_calls_control_inspect_inline(self):
        # The guard that outlives this fix. A future handler that reintroduces an
        # inline broadcast reintroduces the outage, and it will look exactly as
        # harmless as this one did.
        import inspect as _inspect
        import re

        src = _inspect.getsource(ac)
        # Strip the one sanctioned site: the threadpool body inside
        # `_inspect_snapshot`.
        body = _inspect.getsource(ac._inspect_snapshot)
        remainder = src.replace(body, "")
        offenders = re.findall(r"control\.inspect\(", remainder)
        assert offenders == [], (
            "celery control.inspect() must only be called from inside "
            "_inspect_snapshot's threadpool body"
        )


class TestTheMemoCannotPermanentlyHideABrokenBroker:
    """LAT-P071b — caught by the FULL suite, not by review.

    A warm cache satisfied a request without making the call that would have
    failed, so `test_response_shape_on_inspect_error`'s contract — when the
    broker is down, SAY SO — was silently weakened to "…unless someone asked in
    the last five seconds". A 5s window of that is an acceptable price for the
    availability the memo buys, and `_cache` discloses it. Having no way out is
    not: an operator asking "are my workers alive" must be able to get an
    UNCACHED answer.
    """

    def _fake(self, raising=False):
        from unittest.mock import MagicMock
        fake = MagicMock()
        if raising:
            fake.control.inspect.side_effect = Exception("broker down")
        else:
            fake.control.inspect.side_effect = lambda **kw: _SlowInspector(**kw)
        return fake

    def test_a_warm_cache_does_mask_a_fresh_failure_within_the_ttl(self):
        # Asserted, not tolerated in silence. This is the cost of the memo, and a
        # test that pins it is what stops the cost growing unnoticed.
        async def main():
            with patch("app.tasks.celery_app", self._fake(), create=True):
                await ac._inspect_snapshot()
            with patch("app.tasks.celery_app", self._fake(raising=True), create=True):
                return await ac._inspect_snapshot()

        _snap, state = _run(main())
        assert state["cached"] is True

    def test_fresh_bypasses_the_memo_and_surfaces_the_failure(self):
        async def main():
            with patch("app.tasks.celery_app", self._fake(), create=True):
                await ac._inspect_snapshot()
            with patch("app.tasks.celery_app", self._fake(raising=True), create=True):
                return await ac._inspect_snapshot(fresh=True)

        with pytest.raises(Exception, match="broker down"):
            _run(main())

    def test_a_raising_call_writes_nothing_to_the_cache(self):
        # An error is not a snapshot. Caching one would turn a transient broker
        # blip into five seconds of guaranteed failure for every caller.
        async def main():
            with patch("app.tasks.celery_app", self._fake(raising=True), create=True):
                try:
                    await ac._inspect_snapshot()
                except Exception:
                    pass
            return ac._INSPECT_CACHE["data"]

        assert _run(main()) is None
