"""`poll_all_odds` stops stacking copies of itself on `worker-realtime` (#3251).

THE SHIP, in user terms: opening bainluck.com stops costing 4-24 seconds. The
chain is long but every link is measured — one task held 2.17 of the realtime
worker's 4 slots, the `realtime` queue reached 454 deep, and every
`prewarm_live_feed_shapes` message (40 s `expires` bound) was therefore already
stale when a worker reached it and was discarded, recording neither a start nor a
failure. The warm rail went 187 minutes without executing and the front page went
cold. The derivation and the production numbers are on
`ODDS_POLL_INFLIGHT_LEASE_TTL_S` in `app/tasks/config.py`.

WHY THE EXISTING GATE DOES NOT DO THIS. `should_poll_now()` compares `elapsed`
against `LIVE_POLL_INTERVAL`, where `elapsed` is measured from a clock
`update_poll_state` stamps when a pass FINISHES. While a pass is in flight the
stamp is frozen, so `elapsed` grows without bound and each delivery behind the
running copy is MORE likely to pass than the last. `test_the_cadence_gate_cannot
_see_a_running_copy` is the positive control that pins that, so none of the
lease tests below can pass vacuously against a gate that was already sufficient.
"""

import pytest

from app.tasks import config
from app.tasks.redis_state import (
    INFLIGHT_LEASE_PREFIX,
    LEASE_UNGATED,
    acquire_inflight_lease,
    release_inflight_lease,
)


class _RedisStringFake:
    """`SET NX EX`, `GET`, `EVAL` and TTL, in the respects this ship depends on.

    Written rather than mocked because every defect in this area has been a
    SEMANTIC one — a `MagicMock` returns whatever it is told and would happily
    report a key that is simultaneously set, unset and unexpiring. The three
    semantics the ship leans on are asserted directly by
    `TestTheFakeHasTheSemanticsTheGuardsRelyOn` before any guard uses them.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        #: Set to an exception to make the next command raise (Redis unreachable).
        self.raises: Exception | None = None
        self.set_calls: list[dict] = []

    def _check(self):
        if self.raises is not None:
            raise self.raises

    def set(self, key, value, nx=False, ex=None):
        self._check()
        self.set_calls.append({"key": key, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return None  # redis-py returns None, not False, when NX loses
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        else:
            # A SET with no expiry CLEARS any previous TTL. If the ship ever
            # reached here the key would be immortal — the CERT-1920 defect.
            self.ttls.pop(key, None)
        return True

    def get(self, key):
        self._check()
        return self.store.get(key)

    def delete(self, key):
        self._check()
        self.ttls.pop(key, None)
        return int(self.store.pop(key, None) is not None)

    def ttl(self, key):
        self._check()
        if key not in self.store:
            return -2  # no key
        return self.ttls.get(key, -1)  # -1 = live key, NO expiry

    def eval(self, script, numkeys, *args):
        """Only the compare-and-delete script is executed, and it is executed as
        Redis would: atomically, reading and deleting in one step."""
        self._check()
        assert numkeys == 1
        key, token = args[0], args[1]
        assert "get" in script and "del" in script
        if self.store.get(key) == token:
            return self.delete(key)
        return 0

    def expire_now(self, key):
        """The TTL running out."""
        self.store.pop(key, None)
        self.ttls.pop(key, None)


@pytest.fixture
def rc(monkeypatch):
    fake = _RedisStringFake()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
    return fake


KEY = INFLIGHT_LEASE_PREFIX + "poll_all_odds"
TTL = config.ODDS_POLL_INFLIGHT_LEASE_TTL_S


class TestTheFakeHasTheSemanticsTheGuardsRelyOn:
    """Assert the fake before leaning on it, so no guard below passes vacuously."""

    def test_set_nx_refuses_an_existing_key(self, rc):
        assert rc.set("k", "a", nx=True, ex=10) is True
        assert rc.set("k", "b", nx=True, ex=10) is None
        assert rc.get("k") == "a"

    def test_ttl_distinguishes_absent_from_unexpiring(self, rc):
        assert rc.ttl("k") == -2
        rc.set("k", "v", nx=True, ex=None)
        assert rc.ttl("k") == -1, "a key set without EX must read as immortal"
        rc.delete("k")
        rc.set("k", "v", nx=True, ex=5)
        assert rc.ttl("k") == 5

    def test_eval_compare_and_delete_is_token_scoped(self, rc):
        rc.set("k", "mine", nx=True, ex=10)
        assert rc.eval("get del", 1, "k", "theirs") == 0
        assert rc.get("k") == "mine"
        assert rc.eval("get del", 1, "k", "mine") == 1
        assert rc.get("k") is None


class TestTheLeaseBoundsConcurrency:
    def test_a_second_acquire_is_refused_while_the_first_holds(self, rc):
        first = acquire_inflight_lease("poll_all_odds", TTL)
        assert first is not None and first != LEASE_UNGATED

        second = acquire_inflight_lease("poll_all_odds", TTL)
        assert second is None, (
            "a second delivery acquired the lease while the first was still in "
            "flight — this is the pile-up the ship exists to stop"
        )

    def test_the_next_delivery_runs_once_the_holder_releases(self, rc):
        first = acquire_inflight_lease("poll_all_odds", TTL)
        assert release_inflight_lease("poll_all_odds", first) is True
        assert acquire_inflight_lease("poll_all_odds", TTL) not in (None, LEASE_UNGATED)

    def test_the_lease_never_exists_without_an_expiry(self, rc):
        """CERT-1920, applied. An immortal lease is not a cosmetic defect here —
        the lease nobody can release is the lease nobody can acquire, so it would
        disable odds ingestion permanently."""
        acquire_inflight_lease("poll_all_odds", TTL)
        assert rc.ttl(KEY) > 0, f"lease at TTL {rc.ttl(KEY)} — it can never expire"
        assert all(c["ex"] is not None and c["ex"] > 0 for c in rc.set_calls)
        assert all(c["nx"] is True for c in rc.set_calls)

    def test_a_lapsed_holder_cannot_release_its_successors_lease(self, rc):
        """The reason release is compare-and-delete rather than `DEL`."""
        stale = acquire_inflight_lease("poll_all_odds", TTL)
        rc.expire_now(KEY)  # the slow pass outran its own lease
        successor = acquire_inflight_lease("poll_all_odds", TTL)
        assert successor not in (None, LEASE_UNGATED)

        assert release_inflight_lease("poll_all_odds", stale) is False
        assert rc.get(KEY) is not None, (
            "the lapsed holder deleted the successor's lease on its way out — "
            "both copies now run holding nothing"
        )

    def test_a_non_positive_ttl_refuses_to_gate_rather_than_set_forever(self, rc):
        assert acquire_inflight_lease("poll_all_odds", 0) == LEASE_UNGATED
        assert rc.store == {}, "a zero TTL wrote an unexpiring lease"


class TestItFailsOpenWhenRedisIsDown:
    """Refusing to poll when the coordination store is down would turn a Redis
    blip into a total ingestion outage — strictly worse than the concurrency the
    lease bounds."""

    def test_acquire_returns_the_ungated_token(self, rc):
        rc.raises = RuntimeError("connection refused")
        assert acquire_inflight_lease("poll_all_odds", TTL) == LEASE_UNGATED

    def test_release_of_an_ungated_token_touches_nothing(self, rc):
        holder = acquire_inflight_lease("poll_all_odds", TTL)
        assert release_inflight_lease("poll_all_odds", LEASE_UNGATED) is False
        assert rc.get(KEY) is not None, (
            "an ungated pass deleted a real holder's lease on its way out"
        )
        assert release_inflight_lease("poll_all_odds", holder) is True

    def test_release_never_raises_out_of_a_finally(self, rc):
        holder = acquire_inflight_lease("poll_all_odds", TTL)
        rc.raises = RuntimeError("connection refused")
        assert release_inflight_lease("poll_all_odds", holder) is False


class TestTheTaskHonoursTheLease:
    """Drive the REAL task body, so the wiring is proved and not just the helper."""

    @staticmethod
    def _run(monkeypatch, rc, pass_impl):
        import app.tasks as tasks_mod

        monkeypatch.setattr(
            "app.tasks.redis_state.should_poll_now", lambda: (True, "live_games")
        )
        monkeypatch.setattr(tasks_mod, "_tracked_run", lambda label, coro: pass_impl())
        monkeypatch.setattr(
            "app.tasks.odds_polling._poll_all_odds", lambda: None, raising=False
        )
        return tasks_mod.poll_all_odds.run()

    def test_a_delivery_arriving_mid_pass_declines(self, rc, monkeypatch):
        held = acquire_inflight_lease("poll_all_odds", TTL)  # a pass is in flight
        out = self._run(monkeypatch, rc, lambda: {"polled": 1})
        assert out == {"skipped": True, "reason": "inflight"}
        assert rc.get(KEY) is not None
        assert release_inflight_lease("poll_all_odds", held) is True

    def test_a_completed_pass_releases_so_the_next_delivery_runs(self, rc, monkeypatch):
        out = self._run(monkeypatch, rc, lambda: {"polled": 1})
        assert out["polled"] == 1 and out["lease"] == "held"
        assert rc.get(KEY) is None, "the pass finished still holding its lease"

    def test_a_failing_pass_releases_too(self, rc, monkeypatch):
        def boom():
            raise RuntimeError("odds api down")

        with pytest.raises(Exception):
            self._run(monkeypatch, rc, boom)
        assert rc.get(KEY) is None, (
            "a pass that failed fast still held the worker's right to run for the "
            "whole TTL"
        )

    def test_an_ungated_pass_says_so_in_its_result(self, rc, monkeypatch):
        rc.raises = RuntimeError("connection refused")
        out = self._run(monkeypatch, rc, lambda: {"polled": 1})
        assert out["lease"] == "ungated"


class TestTheCadenceGateCannotDoThisJob:
    """The positive control. If this ever fails, the lease is redundant and the
    tests above are passing against a gate that was already sufficient."""

    def test_the_cadence_gate_grows_more_permissive_during_a_long_pass(self, monkeypatch):
        import time as _t

        from app.tasks import redis_state

        started = 1_000_000.0

        class _Hash:
            def hgetall(self, key):
                # `update_poll_state` stamps on COMPLETION, so during a pass this
                # value is frozen at the previous pass's finish.
                return {
                    b"last_poll_time": str(started).encode(),
                    b"unchanged_count": b"0",
                    b"has_live_games": b"true",
                }

        monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _Hash())

        # Three deliveries arriving 30s apart while one 132s pass runs.
        for offset in (30, 60, 90):
            monkeypatch.setattr(_t, "time", lambda o=offset: started + o)
            should_poll, reason = redis_state.should_poll_now()
            assert should_poll is True, (
                "the cadence gate declined a mid-pass delivery, which would make "
                "the lease redundant"
            )
            assert reason == "live_games"


class TestTheTtlDerivation:
    def test_every_term_is_declared(self):
        assert config.ODDS_POLL_INFLIGHT_LEASE_TTL_S == int(
            config.ODDS_POLL_MEASURED_MAX_PASS_SECONDS
            * config.ODDS_POLL_INFLIGHT_LEASE_MARGIN_MULTIPLE
        )

    def test_the_lease_outlives_the_worst_measured_pass(self):
        """A lease that expires during a normal pass provides no protection at
        exactly the moment protection matters."""
        assert (
            config.ODDS_POLL_INFLIGHT_LEASE_TTL_S
            > config.ODDS_POLL_MEASURED_MAX_PASS_SECONDS
        )

    def test_the_stale_p95_constant_is_not_reused_for_the_lease(self):
        """`SLOWEST_MEASURED_ODDS_PASS_SECONDS` is 16 (August). The pass measured
        131.8s max in September. Sizing the lease off the stale constant would
        expire it mid-pass on essentially every run."""
        assert (
            config.ODDS_POLL_INFLIGHT_LEASE_TTL_S
            > config.SLOWEST_MEASURED_ODDS_PASS_SECONDS * 4
        )

    def test_a_hard_killed_holder_cannot_pause_ingestion_for_long(self):
        """The bad direction, bounded. A SIGKILLed holder blocks until the TTL;
        keep that under the 300s worker-liveness window so a dyno cycle cannot
        leave odds dark longer than the worker generation it belonged to."""
        assert config.ODDS_POLL_INFLIGHT_LEASE_TTL_S < redis_liveness_ttl()


def redis_liveness_ttl() -> int:
    from app.tasks.redis_state import WORKER_LIVENESS_TTL

    return WORKER_LIVENESS_TTL
