"""#3251 — a lapping beat task takes an in-flight lease and stops stacking copies.

The defect: `poll_all_odds` is published every 30 s and takes ~118 s, so every
tick added a copy. Production, 2026-09-05: `realtime` 282 → 349 deep with 85
copies of one task queued against `--concurrency=4`, and
`prewarm_live_feed_shapes` (40 s beat, `expires=40`) silently discarded on
arrival for 131 minutes — no start, no failure, `health: healthy`, front page
13.3 s cold.

These gates hold the four properties the repair rests on:

* one copy at a time (the directive's "lease acquired -> second invocation skips")
* a lease that has gone (expired) lets the next tick run
* a body that raises still releases
* the release is compare-and-delete, so a holder whose lease already expired
  cannot delete its successor's
* Redis being down FAILS OPEN — the guard is never the reason ingestion stops
* a declined tick performs no work and records no start/duration, so the
  duration histogram `schedule-adherence` reads cannot be deflated by skips
"""

import pytest

from app.utils import single_flight as sf


# ---------------------------------------------------------------------------
# An in-memory Redis honest about the two verbs this guard turns on.
#
# `set(nx=True)` must answer None (not False) when it refuses — redis-py does,
# and a fake that answers True makes every gate below vacuous.
# ---------------------------------------------------------------------------
class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else str(v).encode()
        if ex is not None:
            self.ttls[k] = ex
        return True

    def incr(self, k):
        current = int(self.store.get(k, b"0"))
        self.store[k] = str(current + 1).encode()
        return current + 1

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, _script, _numkeys, key, arg):
        """The release-if-owner compare-and-delete, faithfully."""
        held = self.store.get(key)
        if held is not None and held.decode() == arg:
            del self.store[key]
            self.ttls.pop(key, None)
            return 1
        return 0

    def pipeline(self):
        return _FakePipeline(self)

    # Expiry is simulated by deleting the key, which is what expiry does. A gate
    # that sleeps is a gate that flakes.
    def expire_now(self, k):
        self.store.pop(k, None)
        self.ttls.pop(k, None)


class _FakePipeline:
    def __init__(self, rc):
        self.rc = rc
        self.ops = []

    def set(self, *a, **kw):
        self.ops.append(("set", a, kw))
        return self

    def incr(self, *a, **kw):
        self.ops.append(("incr", a, kw))
        return self

    def execute(self):
        return [getattr(self.rc, name)(*a, **kw) for name, a, kw in self.ops]


@pytest.fixture
def rc(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(sf, "_client", lambda: fake)
    return fake


TASK = "app.tasks.poll_all_odds"
KEY = sf.LEASE_KEY_PREFIX + TASK


# ---------------------------------------------------------------------------
# The lease itself
# ---------------------------------------------------------------------------
def test_a_second_invocation_skips_while_the_first_still_holds_the_lease(rc):
    first = sf.acquire(TASK)
    assert first.acquired and first.reason == "acquired"

    second = sf.acquire(TASK)
    assert second.acquired is False
    assert second.reason == "already_running"
    assert second.token is None


def test_an_expired_lease_lets_the_next_tick_run(rc):
    held = sf.acquire(TASK)
    assert held.acquired
    assert sf.acquire(TASK).acquired is False

    rc.expire_now(KEY)  # the TTL elapses; the holder was hard killed past its finally

    after = sf.acquire(TASK)
    assert after.acquired is True
    assert after.reason == "acquired"


def test_the_lease_is_released_when_the_body_raises(rc):
    with pytest.raises(RuntimeError):
        with sf.single_flight(TASK) as lease:
            assert lease.acquired
            raise RuntimeError("the poll blew up")

    assert KEY not in rc.store
    assert sf.acquire(TASK).acquired is True


def test_the_lease_is_released_on_the_normal_path(rc):
    with sf.single_flight(TASK) as lease:
        assert lease.acquired
        assert KEY in rc.store
    assert KEY not in rc.store


def test_one_lease_costs_one_redis_client(monkeypatch):
    """`get_redis_client()` builds a fresh client AND pool per call, and these
    tasks fire every 30-120 s. Acquire and release share one."""
    fake = _FakeRedis()
    calls = []

    def _counting():
        calls.append(1)
        return fake

    monkeypatch.setattr(sf, "_client", _counting)
    with sf.single_flight(TASK):
        pass
    assert len(calls) == 1


def test_a_holder_whose_lease_expired_cannot_delete_its_successors(rc):
    """The #1678 defect, written as a gate.

    An unconditional `delete` in a `finally` is how a stale holder admitted a
    second concurrent copy. Release is compare-and-delete: a token that no
    longer owns the key removes nothing.
    """
    stale = sf.acquire(TASK)
    rc.expire_now(KEY)
    successor = sf.acquire(TASK)
    assert successor.acquired

    assert sf.release(stale) is False          # removed nothing
    assert rc.store.get(KEY) == successor.token.encode()   # still the successor's
    assert sf.acquire(TASK).acquired is False  # and it still excludes a third


def test_release_is_a_no_op_for_a_lease_that_was_never_held(rc):
    refused = sf.acquire(TASK)  # noqa: F841 — first one takes it
    declined = sf.acquire(TASK)
    assert declined.acquired is False
    assert sf.release(declined) is False
    assert KEY in rc.store  # the real holder keeps it


# ---------------------------------------------------------------------------
# Fail open — the guard is never the reason ingestion stops
# ---------------------------------------------------------------------------
def test_no_redis_client_runs_the_work_anyway(monkeypatch):
    monkeypatch.setattr(sf, "_client", lambda: None)
    lease = sf.acquire(TASK)
    assert lease.acquired is True
    assert lease.reason == "redis_unavailable"
    assert lease.token is None
    assert sf.release(lease) is False  # nothing to release, and it must not try


def test_a_raising_redis_runs_the_work_anyway(monkeypatch):
    class _Exploding(_FakeRedis):
        def set(self, *a, **kw):
            raise RuntimeError("redis is down")

    monkeypatch.setattr(sf, "_client", lambda: _Exploding())
    lease = sf.acquire(TASK)
    assert lease.acquired is True
    assert lease.reason == "redis_unavailable"


def test_a_release_that_cannot_run_leaves_the_lease_to_expire(monkeypatch):
    """Fails CLOSED: one delayed tick beats handing the key to a second copy."""

    fake = _FakeRedis()
    lease = None

    class _EvalDown(_FakeRedis):
        def eval(self, *a, **kw):
            raise RuntimeError("redis is down")

    monkeypatch.setattr(sf, "_client", lambda: fake)
    lease = sf.acquire(TASK)
    assert lease.acquired

    monkeypatch.setattr(sf, "_client", lambda: _EvalDown())
    assert sf.release(lease) is False
    assert KEY in fake.store  # left standing, to go by TTL


# ---------------------------------------------------------------------------
# The skipped tick: harmless, and visible
# ---------------------------------------------------------------------------
def test_a_skipped_tick_is_not_a_failure_shape(rc):
    sf.acquire(TASK)
    declined = sf.acquire(TASK)
    summary = declined.skipped_result()

    assert summary["skipped"] is True
    assert summary["reason"] == "already_running"
    assert summary["task"] == TASK
    # No terminal/status key: `task_verdict` must not read a decline as an
    # incomplete or failed run and move a health counter for it.
    assert "terminal" not in summary
    assert "status" not in summary


def test_a_skipped_tick_does_not_classify_as_an_authoritative_verdict(rc):
    from app.utils.task_verdict import verdict_for

    sf.acquire(TASK)
    summary = sf.acquire(TASK).skipped_result()
    verdict = verdict_for("poll_odds", summary)
    assert verdict.authoritative is False


def test_skips_are_counted_so_production_can_prove_the_guard_fired(rc):
    counter = sf.skip_counter_key(TASK)
    sf.acquire(TASK)
    assert counter not in rc.store  # an ACQUIRE is not a skip

    sf.acquire(TASK)
    sf.acquire(TASK)
    assert int(rc.store[counter]) == 2
    assert rc.ttls[counter] == sf.SKIP_COUNTER_TTL_SECONDS


def test_the_counter_window_is_not_extended_by_every_skip(rc):
    """`set(nx=True)` seeds the window once; `incr` must not re-arm the TTL."""
    counter = sf.skip_counter_key(TASK)
    sf.acquire(TASK)
    sf.acquire(TASK)
    rc.ttls[counter] = 10  # pretend 24h-10s have passed
    sf.acquire(TASK)
    assert rc.ttls[counter] == 10


# ---------------------------------------------------------------------------
# POSITIVE CONTROL: the cadence gate could not have done this job
#
# Every gate above stubs `should_poll_now()` to (True, "test"). That is correct
# — they are testing the lease — but it means none of them would notice if the
# cadence gate had been sufficient all along, and the whole repair were
# redundant. This section pins the gate's INADEQUACY, so `poll_all_odds`'s
# docstring claim ("it stamps its clock when a pass FINISHES, so while a pass is
# running it says yes to every delivery") is enforced rather than asserted.
#
# Credit: latency/167 measured this and handed it over (#3251, 2026-09-05).
# ---------------------------------------------------------------------------
class _FakeStateRedis:
    """Just the one verb `should_poll_now` turns on, with redis-py's byte keys."""

    def __init__(self, last_poll_time: float, live: bool = True):
        self.state = {
            b"last_poll_time": str(last_poll_time).encode(),
            b"unchanged_count": b"0",
            b"has_live_games": b"true" if live else b"false",
        }

    def hgetall(self, _key):
        return self.state


def _gate_at(monkeypatch, now: float, last_poll_time: float, live: bool = True):
    """Ask `should_poll_now()` what it says at wall-clock `now`."""
    from app.tasks import redis_state

    monkeypatch.setattr(
        redis_state, "get_redis_client", lambda: _FakeStateRedis(last_poll_time, live)
    )
    monkeypatch.setattr(redis_state.time, "time", lambda: now)
    return redis_state.should_poll_now()


def test_the_cadence_gate_grows_more_permissive_during_a_long_pass(monkeypatch):
    """Three deliveries 30 s apart while one 132 s pass runs. ALL THREE pass.

    `update_poll_state` stamps `last_poll_time` when a pass FINISHES, so while a
    pass is in flight the stamp is frozen and each delivery behind the running
    copy reads an ever-LARGER `elapsed`. The gate is monotonically MORE
    permissive the longer the pile-up lasts, which is the opposite of shedding.
    """
    from app.tasks.config import LIVE_POLL_INTERVAL

    pass_started = 1_000_000.0
    # The stamp is from the PREVIOUS pass's completion, i.e. when this one began.
    elapsed_seen = []
    for delivery in (30.0, 60.0, 90.0):
        should_poll, reason = _gate_at(
            monkeypatch, now=pass_started + delivery, last_poll_time=pass_started
        )
        assert should_poll is True, (
            f"delivery at +{delivery}s was shed by the cadence gate; if this "
            f"fails the gate now sheds pile-up and the lease may be redundant"
        )
        assert reason == "live_games"
        elapsed_seen.append(delivery)

    # Monotonically increasing `elapsed` against a FIXED threshold: no value of
    # LIVE_POLL_INTERVAL rescues this, because the pass outlives any of them.
    assert elapsed_seen == sorted(elapsed_seen)
    assert elapsed_seen[0] >= LIVE_POLL_INTERVAL


def test_no_threshold_value_lets_the_cadence_gate_shed_a_lapping_pass(monkeypatch):
    """Even the SLOWEST adaptive interval admits every delivery behind a lap.

    A pass that runs longer than its own gate interval means the next delivery
    always reads `elapsed >= interval`. Tested at the most conservative setting
    the adaptive ladder can reach, so the conclusion is not a property of the
    live-games branch alone.
    """
    from app.tasks.config import SLOW_POLL_INTERVAL

    pass_started = 2_000_000.0
    # A pass one second longer than the slowest interval the ladder can choose.
    for delivery in (SLOW_POLL_INTERVAL + 1, SLOW_POLL_INTERVAL * 2):
        should_poll, _ = _gate_at(
            monkeypatch,
            now=pass_started + delivery,
            last_poll_time=pass_started,
            live=False,
        )
        assert should_poll is True


def test_the_lease_sheds_exactly_what_the_cadence_gate_admits(monkeypatch, rc):
    """The two gates in series: cadence says RUN, the lease still declines.

    This is the join the repair rests on. With the cadence gate answering
    honestly (not stubbed), a delivery arriving behind an in-flight copy is
    admitted by the gate and refused by the lease.
    """
    import app.tasks as tasks_mod
    import app.tasks.odds_polling as odds_polling

    pass_started = 3_000_000.0
    calls = []
    monkeypatch.setattr(
        odds_polling, "_poll_all_odds", lambda *a, **kw: calls.append(1) or {"ran": True}
    )
    monkeypatch.setattr(tasks_mod, "_tracked_run", lambda _label, result: result)

    # The cadence gate, answering for real, admits this delivery.
    should_poll, reason = _gate_at(
        monkeypatch, now=pass_started + 90.0, last_poll_time=pass_started
    )
    assert (should_poll, reason) == (True, "live_games")

    # The lease, held by the copy still in flight, refuses it.
    held = sf.acquire(TASK)
    assert held.acquired
    declined = tasks_mod.poll_all_odds()
    assert declined["skipped"] is True
    assert declined["reason"] == "already_running"
    assert calls == [], "the cadence gate admitted it; only the lease shed it"


# ---------------------------------------------------------------------------
# The TTL is the runtime's bound, not a transcribed p95
# ---------------------------------------------------------------------------
def test_the_lease_ttl_outlives_celerys_hard_kill_bound():
    """A SIGKILL lands AT `task_time_limit` and reaches no `finally`, so the
    lease must still be held then — otherwise a second copy starts while the
    first is being killed, and both bill The Odds API for the same tick."""
    from app.tasks import celery_app

    assert (
        sf.CELERY_HARD_TASK_TIME_LIMIT_SECONDS == celery_app.conf.task_time_limit
    ), "the mirrored kill bound drifted from celery's own conf"
    assert sf.DEFAULT_LEASE_TTL_SECONDS > celery_app.conf.task_time_limit


def test_the_lease_is_written_with_that_ttl(rc):
    sf.acquire(TASK)
    assert rc.ttls[KEY] == sf.DEFAULT_LEASE_TTL_SECONDS


# ---------------------------------------------------------------------------
# The four lapping tasks are actually wired to it
#
# Behavioural, not a source grep: each task is invoked twice with its own
# implementation stubbed, and the second invocation must decline WITHOUT
# reaching the implementation.
# ---------------------------------------------------------------------------
def _lapping_tasks():
    import app.tasks as tasks_mod
    import app.tasks.datagolf as datagolf
    import app.tasks.espn_sync as espn_sync
    import app.tasks.odds_polling as odds_polling
    import app.tasks.prediction_market_matching as pmm

    return [
        ("app.tasks.poll_all_odds", tasks_mod.poll_all_odds, odds_polling, "_poll_all_odds"),
        ("app.tasks.sync_espn_live_events", tasks_mod.sync_espn_live_events, espn_sync, "_sync_espn_live_events"),
        ("app.tasks.poll_live_prediction_markets", tasks_mod.poll_live_prediction_markets, pmm, "_poll_live_prediction_market_prices"),
        ("app.tasks.poll_datagolf_inplay", tasks_mod.poll_datagolf_inplay, datagolf, "_poll_datagolf_inplay"),
    ]


@pytest.mark.parametrize(
    "name,task,impl_module,impl_attr",
    _lapping_tasks(),
    ids=[t[0] for t in _lapping_tasks()],
)
def test_a_lapping_task_runs_once_and_declines_the_overlapping_delivery(
    monkeypatch, rc, name, task, impl_module, impl_attr
):
    import app.tasks as tasks_mod

    calls = []

    def _impl(*a, **kw):
        calls.append(name)
        return {"ran": True}

    monkeypatch.setattr(impl_module, impl_attr, _impl)
    # `_tracked_run` is the recording boundary; stub it so the gate exercises the
    # lease and nothing touches the real metrics rail.
    monkeypatch.setattr(tasks_mod, "_tracked_run", lambda _label, result: result)
    monkeypatch.setattr(
        "app.tasks.redis_state.should_poll_now", lambda: (True, "test")
    )

    # Hold the lease as if a previous copy were still in flight.
    held = sf.acquire(name)
    assert held.acquired

    declined = task()
    assert declined["skipped"] is True
    assert declined["reason"] == "already_running"
    assert calls == [], "a declined delivery must not do the work"

    # Release it; the next delivery runs for real.
    assert sf.release(held) is True
    ran = task()
    assert calls == [name]
    assert ran.get("ran") is True or ran.get("skipped") is not True
