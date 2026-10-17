"""Guard tests for #2316: one builder per season-market discovery slot.

WHAT WAS MEASURED. Production 2026-10-17: the finished-event shape of the
season-market discovery query averaged 19.2 s and 23.7 s across its two
`pg_stat_statements` fingerprints (max 61.4 s), reading 83k-115k blocks from disk
per call. In the slow-event ring, 87 related-futures requests since
2026-10-16 23:00Z had a single statement over 5 s, and 27 of them started while
another one was already running: several readers of one sport missing the same
slot together, each running its own copy of a cold 1.9 GB scan.

🔴 THE LOAD-BEARING CHECK is
`test_two_concurrent_misses_in_one_sport_run_the_discovery_query_once`. It
drives the real `_build_related_futures` twice, concurrently, against sessions
that RECORD every statement, with the first build's discovery query held open
until the second build is waiting. It fails if the second build runs its own
scan, and that is the duplicate the ring recorded.

Its opposite arms are what stop it passing by never querying, or by waiting
forever:
  * `..._a_failed_holder_hands_the_build_to_the_waiter` — a holder that raises
    must release, and the waiter must run the query itself, promptly.
  * `..._different_sports_do_not_wait_for_each_other`.
  * `..._a_rejected_slot_rebuilds_instead_of_waiting` — the competition-scope
    re-check must still force a rebuild. The real-PG guard for that path
    (`test_contaminated_cached_ids_trigger_fenced_rediscovery`) runs with no
    Redis, so it cannot see the lease at all.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.utils import season_market_discovery as smd
from app.utils import single_flight
from tests.test_season_market_discovery_lat_p144 import (
    _build,
    _event,
    _RecordingSession,
    _tier_rows,
)


class _LeaseRedis:
    """In-memory Redis with the operations the cache AND the lease use.

    `set(nx=True)` refuses a held key, `eval` runs the compare-and-delete that
    `single_flight.RELEASE_IF_OWNER_LUA` performs, and `exists` answers whether
    a lease stands. TTLs are recorded, not enforced. The tests that need a
    lease to vanish delete it explicitly.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.gets = 0

    def get(self, k):
        self.gets += 1
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def exists(self, k):
        return 1 if k in self.store else 0

    def eval(self, script, numkeys, key, token):
        assert script == single_flight.RELEASE_IF_OWNER_LUA
        stored = self.store.get(key)
        if stored is not None and stored == (
            token.encode() if isinstance(token, str) else token
        ):
            del self.store[key]
            return 1
        return 0

    def pipeline(self):
        return _Pipe(self)


class _Pipe:
    """Just enough pipeline for `single_flight._record_skip`."""

    def __init__(self, rc):
        self.rc = rc
        self.ops = []

    def set(self, k, v, nx=False, ex=None):
        self.ops.append(lambda: self.rc.set(k, str(v), nx=nx, ex=ex))
        return self

    def incr(self, k):
        def _incr():
            cur = int(self.rc.store.get(k, b"0"))
            self.rc.store[k] = str(cur + 1).encode()

        self.ops.append(_incr)
        return self

    def execute(self):
        for op in self.ops:
            op()


class _Boom:
    """Every operation raises: the 'Redis is sick' case."""

    def __getattr__(self, name):
        def _raise(*a, **k):
            raise RuntimeError("redis down")

        return _raise


def _lease_key(sport_key="baseball_mlb", finished=True):
    return single_flight.lease_key(smd.build_task_name(sport_key, finished))


def _hold_lease_as_peer(rc, sport_key="baseball_mlb", finished=True):
    rc.set(_lease_key(sport_key, finished), "peer-token", nx=True, ex=75)


# ---------------------------------------------------------------------------
# claim_or_await, unit
# ---------------------------------------------------------------------------


def test_the_lease_is_per_slot_not_per_sport():
    """The live and finished shapes are different answers. One must never wait
    for the other, so they must never share a lease."""
    assert smd.build_task_name("baseball_mlb", True) != smd.build_task_name(
        "baseball_mlb", False
    )
    assert smd.build_task_name("baseball_mlb", True) != smd.build_task_name(
        "basketball_nba", True
    )


def test_the_lease_outlives_the_slowest_recorded_discovery():
    """61.4 s is the slowest discovery in production (2026-10-17). A lease that
    expired sooner would let a second scan start under a live holder."""
    assert smd.BUILD_LEASE_TTL_SECONDS > 61.4


@pytest.mark.asyncio
async def test_a_free_slot_is_claimed_and_the_claim_is_released():
    rc = _LeaseRedis()
    ids, lease = await smd.claim_or_await("baseball_mlb", True, rc=rc)
    assert ids is None
    assert lease is not None and lease.acquired and lease.token
    assert rc.exists(_lease_key()) == 1
    assert rc.ttls[_lease_key()] == smd.BUILD_LEASE_TTL_SECONDS
    assert smd.release_build(lease, rc=rc) is True
    assert rc.exists(_lease_key()) == 0


@pytest.mark.asyncio
async def test_a_waiter_gets_the_peer_s_answer_and_never_claims():
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc)
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)
        if len(sleeps) == 3:
            smd.write("baseball_mlb", True, [11, 12], rc=rc)

    ids, lease = await smd.claim_or_await("baseball_mlb", True, rc=rc, sleep=_sleep)
    assert ids == [11, 12]
    assert lease is None
    assert sleeps == [smd.PEER_POLL_SECONDS] * 3
    # The peer's lease is untouched: a waiter never releases what it never held.
    assert rc.store[_lease_key()] == b"peer-token"


@pytest.mark.asyncio
async def test_a_peer_s_empty_answer_is_an_answer_not_a_miss():
    """Gotcha #53: `[]` is the boxing case, where the scan is all cost and no
    rows. Reading it as a miss would send the waiter into its own scan."""
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc)

    async def _sleep(s):
        smd.write("baseball_mlb", True, [], rc=rc)

    ids, lease = await smd.claim_or_await("baseball_mlb", True, rc=rc, sleep=_sleep)
    assert ids == []
    assert lease is None


@pytest.mark.asyncio
async def test_a_holder_that_ends_without_publishing_hands_over_the_build():
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc)

    async def _sleep(s):
        # The holder failed: its `finally` released, nothing was written.
        rc.store.pop(_lease_key(), None)

    ids, lease = await smd.claim_or_await("baseball_mlb", True, rc=rc, sleep=_sleep)
    assert ids is None
    assert lease is not None and lease.acquired
    assert rc.store[_lease_key()] == lease.token.encode()


@pytest.mark.asyncio
async def test_an_answer_published_between_the_miss_and_the_claim_is_used():
    """The holder can publish and release between the route's read and this
    claim. The re-read after the claim saves a whole scan, and the claim must
    not be left behind."""
    rc = _LeaseRedis()
    smd.write("baseball_mlb", True, [7], rc=rc)
    ids, lease = await smd.claim_or_await("baseball_mlb", True, rc=rc)
    assert ids == [7]
    assert lease is None
    assert rc.exists(_lease_key()) == 0


@pytest.mark.asyncio
async def test_the_wait_is_bounded_by_the_lease_ttl():
    """A holder SIGKILLed mid-query skips its `finally`. Its lease stands until
    the TTL, and the waiter must stop waiting by then and run the query."""
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc)
    now = [1000.0]

    async def _sleep(s):
        now[0] += s

    ids, lease = await smd.claim_or_await(
        "baseball_mlb", True, rc=rc, sleep=_sleep, clock=lambda: now[0]
    )
    assert (ids, lease) == (None, None)
    assert 1000.0 + smd.BUILD_LEASE_TTL_SECONDS <= now[0]
    assert now[0] <= 1000.0 + smd.BUILD_LEASE_TTL_SECONDS + smd.PEER_POLL_SECONDS


@pytest.mark.asyncio
async def test_no_redis_fails_open():
    with patch.object(smd, "_client", lambda: None):
        assert await smd.claim_or_await("baseball_mlb", True) == (None, None)


@pytest.mark.asyncio
async def test_a_sick_redis_fails_open():
    assert await smd.claim_or_await("baseball_mlb", True, rc=_Boom()) == (None, None)


@pytest.mark.asyncio
async def test_a_lease_that_vanishes_into_a_sick_redis_fails_open():
    """A peer's lease was readable, then Redis broke: run the query, don't spin."""
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc)

    def _broken(k):
        raise RuntimeError("redis down")

    rc.exists = _broken
    assert await smd.claim_or_await("baseball_mlb", True, rc=rc) == (None, None)


def _slow_get_redis(seconds_per_get, now):
    """A healthy-looking Redis whose GET takes `seconds_per_get` on the
    injected clock: slow, never raising."""
    rc = _LeaseRedis()
    real_get = rc.get

    def _get(k):
        now[0] += seconds_per_get
        return real_get(k)

    rc.get = _get
    return rc


@pytest.mark.asyncio
async def test_a_slow_redis_stops_the_wait_instead_of_stalling_the_loop():
    """lane1b R1 on #11197: each poll is synchronous, so a Redis that answers
    in 100 ms without erroring would block the worker's event loop for most of
    every second of the holder's scan. One slow poll ends the wait: run the
    query here, sleep never, and leave the peer's lease alone."""
    now = [1000.0]
    rc = _slow_get_redis(0.1, now)
    _hold_lease_as_peer(rc)
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)
        now[0] += s

    ids, lease = await smd.claim_or_await(
        "baseball_mlb", True, rc=rc, sleep=_sleep, clock=lambda: now[0]
    )
    assert (ids, lease) == (None, None)
    assert sleeps == []
    assert rc.store[_lease_key()] == b"peer-token"


@pytest.mark.asyncio
async def test_a_slow_redis_never_attempts_a_takeover_claim():
    """lane1b's surviving mutant on #11197: the budget check placed after the
    `not held` break still passed the test above, because there the peer's
    lease stands. Here the peer ends without publishing during the slow GET,
    so EXISTS says nothing is held: a slow poll must still fail open rather
    than go round and take the lease over through the same slow Redis."""
    now = [1000.0]
    rc = _slow_get_redis(0.1, now)
    _hold_lease_as_peer(rc)
    slow_get = rc.get

    def _get_then_peer_quits(k):
        rc.store.pop(_lease_key(), None)
        return slow_get(k)

    rc.get = _get_then_peer_quits
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)
        now[0] += s

    ids, lease = await smd.claim_or_await(
        "baseball_mlb", True, rc=rc, sleep=_sleep, clock=lambda: now[0]
    )
    assert (ids, lease) == (None, None)
    assert sleeps == []
    assert rc.exists(_lease_key()) == 0


@pytest.mark.asyncio
async def test_a_fast_redis_keeps_waiting_for_the_peer():
    """The control for the test above: the same rig with polls well inside the
    budget keeps waiting and takes the peer's answer, so the budget is not
    what ends every wait."""
    now = [1000.0]
    rc = _slow_get_redis(smd.POLL_REDIS_BUDGET_SECONDS / 5, now)
    _hold_lease_as_peer(rc)
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)
        now[0] += s
        if len(sleeps) == 3:
            rc.setex(smd.cache_key("baseball_mlb", True), 300, "[7, 8]")

    ids, lease = await smd.claim_or_await(
        "baseball_mlb", True, rc=rc, sleep=_sleep, clock=lambda: now[0]
    )
    assert (ids, lease) == ([7, 8], None)
    assert sleeps == [smd.PEER_POLL_SECONDS] * 3


def test_the_poll_budget_is_far_under_the_poll_interval():
    """Over budget, a waiter's sync Redis time would be a large share of the
    loop; the budget keeps it under a fifth of each poll interval."""
    assert 0 < smd.POLL_REDIS_BUDGET_SECONDS <= smd.PEER_POLL_SECONDS / 5


def test_release_of_no_lease_is_a_no_op():
    assert smd.release_build(None) is False


# ---------------------------------------------------------------------------
# The real build, concurrently
# ---------------------------------------------------------------------------


class _GatedSession(_RecordingSession):
    """A `_RecordingSession` whose discovery query blocks until `gate` opens,
    or raises instead of answering when `fail` is set."""

    def __init__(self, event, tier_rows, gate: asyncio.Event, fail=False):
        super().__init__(event, tier_rows)
        self.gate = gate
        self.fail = fail
        self.discovery_started = asyncio.Event()

    async def execute(self, stmt):
        sql = str(stmt)
        if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
            self.statements.append(sql)
            self.discovery_started.set()
            await self.gate.wait()
            if self.fail:
                raise RuntimeError("statement failed")
            from tests.test_season_market_discovery_lat_p144 import _Result

            return _Result(rows=self.tier_rows)
        return await super().execute(stmt)


def _finished(sport_key="baseball_mlb", event_id=101):
    from datetime import timedelta

    from tests.test_season_market_discovery_lat_p144 import _NOW

    ev = _event(sport_key, status="completed")
    ev.id = event_id
    ev.commence_time = _NOW - timedelta(hours=4)
    return ev


async def _until_waiting(rc, polls_before=2):
    """Let the second build reach its poll loop: it has read the slot at least
    `polls_before` times while the lease is held."""
    start = rc.gets
    for _ in range(500):
        if rc.gets - start >= polls_before:
            return
        await asyncio.sleep(0.001)
    raise AssertionError("the second build never started waiting")


@pytest.mark.asyncio
async def test_two_concurrent_misses_in_one_sport_run_the_discovery_query_once():
    """🔴 The load-bearing check: two finished events, one sport, both miss
    together, and ONE scan runs."""
    rc = _LeaseRedis()
    gate = asyncio.Event()
    first = _GatedSession(_finished(event_id=101), _tier_rows(), gate)
    second = _RecordingSession(_finished(event_id=202), _tier_rows())
    with patch.object(smd, "_client", lambda: rc), patch.object(
        smd, "PEER_POLL_SECONDS", 0.001
    ):
        t1 = asyncio.create_task(_build(first))
        await asyncio.wait_for(first.discovery_started.wait(), 2)
        t2 = asyncio.create_task(_build(second))
        await _until_waiting(rc)
        assert not t2.done(), "the second build did not wait for the first"
        gate.set()
        await asyncio.wait_for(asyncio.gather(t1, t2), 5)

    assert first.discovery_calls == 1
    assert second.discovery_calls == 0, (
        "the second reader ran its own copy of the sport-wide scan"
    )
    assert smd.read("baseball_mlb", True, rc=rc) == [11, 12]
    assert rc.exists(_lease_key()) == 0, "the holder left its lease behind"


@pytest.mark.asyncio
async def test_a_failed_holder_hands_the_build_to_the_waiter():
    """The holder's scan raises. Its `finally` must release, and the waiter
    must run the scan itself well inside the lease TTL, not after it."""
    rc = _LeaseRedis()
    gate = asyncio.Event()
    first = _GatedSession(_finished(event_id=101), _tier_rows(), gate, fail=True)
    second = _RecordingSession(_finished(event_id=202), _tier_rows())
    with patch.object(smd, "_client", lambda: rc), patch.object(
        smd, "PEER_POLL_SECONDS", 0.001
    ):
        t1 = asyncio.create_task(_build(first))
        await asyncio.wait_for(first.discovery_started.wait(), 2)
        t2 = asyncio.create_task(_build(second))
        await _until_waiting(rc)
        gate.set()
        with pytest.raises(RuntimeError, match="statement failed"):
            await asyncio.wait_for(t1, 5)
        await asyncio.wait_for(t2, 5)

    assert second.discovery_calls == 1, "the waiter never took over the build"
    assert smd.read("baseball_mlb", True, rc=rc) == [11, 12]
    assert rc.exists(_lease_key()) == 0


@pytest.mark.asyncio
async def test_a_cancelled_holder_releases_its_lease():
    """A reader that disconnects mid-scan is cancelled; `finally` still runs."""
    rc = _LeaseRedis()
    gate = asyncio.Event()
    first = _GatedSession(_finished(event_id=101), _tier_rows(), gate)
    with patch.object(smd, "_client", lambda: rc):
        t1 = asyncio.create_task(_build(first))
        await asyncio.wait_for(first.discovery_started.wait(), 2)
        assert rc.exists(_lease_key()) == 1
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
    assert rc.exists(_lease_key()) == 0


@pytest.mark.asyncio
async def test_different_sports_do_not_wait_for_each_other():
    rc = _LeaseRedis()
    gate = asyncio.Event()
    first = _GatedSession(_finished("baseball_mlb"), _tier_rows(), gate)
    other = _RecordingSession(_finished("basketball_nba", 202), _tier_rows())
    with patch.object(smd, "_client", lambda: rc):
        t1 = asyncio.create_task(_build(first))
        await asyncio.wait_for(first.discovery_started.wait(), 2)
        # Completes while baseball's scan is still held open.
        await asyncio.wait_for(_build(other), 2)
        assert other.discovery_calls == 1
        gate.set()
        await asyncio.wait_for(t1, 5)


@pytest.mark.asyncio
async def test_a_live_event_does_not_wait_for_a_finished_build():
    rc = _LeaseRedis()
    gate = asyncio.Event()
    first = _GatedSession(_finished("baseball_mlb"), _tier_rows(), gate)
    live = _RecordingSession(_event("baseball_mlb"), _tier_rows())
    live.event.id = 202
    with patch.object(smd, "_client", lambda: rc):
        t1 = asyncio.create_task(_build(first))
        await asyncio.wait_for(first.discovery_started.wait(), 2)
        await asyncio.wait_for(_build(live), 2)
        assert live.discovery_calls == 1
        gate.set()
        await asyncio.wait_for(t1, 5)


@pytest.mark.asyncio
async def test_a_debug_build_neither_waits_nor_claims():
    """Debug must see the uncached truth: it runs its own scan even while a
    peer holds the lease, and it must not take the lease from normal readers."""
    rc = _LeaseRedis()
    _hold_lease_as_peer(rc, finished=False)
    dbg = _RecordingSession(_event("baseball_mlb"), _tier_rows())
    with patch.object(smd, "_client", lambda: rc):
        await asyncio.wait_for(_build(dbg, debug=True), 2)
    assert dbg.discovery_calls == 1
    assert rc.store[_lease_key(finished=False)] == b"peer-token"


@pytest.mark.asyncio
async def test_a_rejected_slot_rebuilds_instead_of_waiting():
    """The competition-scope re-check rejects a cached slot holding a row the
    scope refuses. That reader must rebuild. Sending it through
    `claim_or_await` would re-read the slot and hand the rejected ids straight
    back, so the scan would never run.
    """
    from app.utils.serie_a_femminile_context import SPORT_KEY

    class _ScopeSession(_RecordingSession):
        # This sport's scope is a subquery on `sports`, so the parent's
        # `FROM sports` branch would answer the discovery query. Answer the
        # discovery query first, and the scope re-check with no rows.
        async def execute(self, stmt):
            sql = str(stmt)
            if sql.startswith("SELECT futures_markets.id, futures_markets.market_tier"):
                self.statements.append(sql)
                from tests.test_season_market_discovery_lat_p144 import _Result

                return _Result(rows=self.tier_rows)
            if sql.startswith("SELECT futures_markets.id \nFROM futures_markets"):
                self.statements.append(sql)
                from tests.test_season_market_discovery_lat_p144 import _Result

                return _Result(rows=[])
            return await super().execute(stmt)

    rc = _LeaseRedis()
    smd.write(SPORT_KEY, False, [500, 501], rc=rc)
    session = _ScopeSession(_event(SPORT_KEY), _tier_rows())
    with patch.object(smd, "_client", lambda: rc):
        await asyncio.wait_for(_build(session), 2)
    # The scope re-check answered no rows, so the slot was rejected and the
    # build had to run its own scan.
    assert any(
        s.startswith("SELECT futures_markets.id \nFROM futures_markets")
        for s in session.statements
    ), "the scope re-check never ran, so this test proves nothing"
    assert session.discovery_calls == 1
    assert smd.read(SPORT_KEY, False, rc=rc) == [11, 12]


@pytest.mark.asyncio
async def test_a_dead_redis_leaves_concurrent_builds_working():
    """Fail open: with no lease available, both builds run, as before #2316."""
    a = _RecordingSession(_finished(event_id=101), _tier_rows())
    b = _RecordingSession(_finished(event_id=202), _tier_rows())
    with patch.object(smd, "_client", lambda: _Boom()):
        await asyncio.wait_for(asyncio.gather(_build(a), _build(b)), 5)
    assert a.discovery_calls == 1
    assert b.discovery_calls == 1


def test_the_lease_rides_the_shared_single_flight_namespace():
    """Readable through `/api/admin/redis-read` under the same prefix as every
    other in-flight lease, and its skip counter proves in production that a
    waiter waited."""
    assert _lease_key().startswith(single_flight.LEASE_KEY_PREFIX)
