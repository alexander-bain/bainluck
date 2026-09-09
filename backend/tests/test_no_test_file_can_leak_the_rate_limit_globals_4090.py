"""#4090 — a test file cannot hand its lowered rate limits to a stranger.

`app/utils/rate_limit.py` holds its entire configuration in module globals, and a
test that wants to reach a 60/minute ceiling in five requests has no way to do it
except to assign one. That is fine to DO and fatal to LEAVE: the next test in the
same pytest worker inherits the lowered ceiling and fails on a `429` it did
nothing to earn, in a file with no connection to rate limiting.

Three CI reds on 2026-09-08 (#4053, #4065, #4090) were this, and each one named a
file the diff never touched — `scripts/ci_shard.py` packs shards LPT-greedy over
the collected files, so adding ANY test file anywhere re-partitions every shard
and puts a fresh stranger downstream of the leak. The last one skipped a
production deploy. Both implicated files grew their own restore afterwards; this
is the class fix, in `tests/conftest.py`, so the next file does not have to know.

WHY SEVERAL TESTS HERE LOOK LIKE COPIES OF EACH OTHER, in `TestEveryTestStartsFromThePristineModule`:
this cannot be written as "test A pollutes, test B checks" — `pytest-randomly` is
installed, so there is no test B. Each case instead ASSERTS PRISTINE AT ENTRY and
THEN POLLUTES. With the conftest reset in place every ordering passes; with it
removed, whichever of them runs last is downstream of the others and fails. That
is what makes the guard order-independent, and it is why deleting the
"duplicates" would quietly disarm it.
"""

import types

import pytest
from starlette.testclient import TestClient

import app.utils.rate_limit as rate_limit_module

from .conftest import (
    _RATE_LIMIT_PRISTINE,
    _rate_limit_module_state,
    _restore_rate_limit_module_state,
)

#: The module-level names the snapshot deliberately does NOT carry: two `typing`
#: constructs, the `from __future__` feature flag and the module logger. None of
#: them is a knob, and none can be restored meaningfully by reassignment.
#:
#: Pinned as a SET rather than a count, and pinned on the EXCLUSIONS rather than
#: on the snapshot, on purpose. A new rate-limit knob of the ordinary shape (a
#: string, an int, a lazily-built singleton that starts as `None`) is picked up
#: by `_rate_limit_module_state` automatically and must not red this file. A new
#: global of a shape the snapshot cannot restore — a dict or a set, which a test
#: would mutate IN PLACE where rebinding the name cures nothing — is exactly the
#: case that needs a human, and it lands here.
EXPECTED_UNSNAPSHOTTED = {
    "Optional",
    "RequestResponseEndpoint",
    "annotations",
    "logger",
}

#: The knobs whose leak has actually cost us something, named so a future reader
#: sees the population rather than an abstraction. Asserted as a SUBSET — the
#: snapshot is expected to be wider than this list, never narrower.
KNOBS_WITH_A_HISTORY = (
    "ANON_RATE_LIMIT",  # #4053/#4065: lowered to 3/minute, left there
    "AUTH_RATE_LIMIT",
    "ADMIN_RATE_LIMIT",
    "TRUSTED_RATE_LIMIT",  # d70's half of the same pair
    "_ANON_MAX",
    "_RL_CHECK_TIMEOUT",  # assigned by test_rate_limit.py, restored by nobody
    "_async_rl_unavailable",  # a ONE-WAY latch; see the class below
    "_rate_limiter",  # the shared in-memory budget
    "_anon_limit",  # memoised off the strings, so a stale one outlives a fix
    "_auth_limit",
    "_admin_limit",
    "_trusted_limit",
    "_trusted_ip_cache",
    "_trusted_uid_resolver",
)


class TestTheSnapshotCoversWhatItClaimsTo:
    def test_every_knob_with_a_history_is_in_the_snapshot(self):
        missing = [n for n in KNOBS_WITH_A_HISTORY if n not in _RATE_LIMIT_PRISTINE]
        assert missing == [], (
            f"{missing} can be assigned by a test and is no longer restored between "
            "tests. Every name here has already cost a CI red or is one line of "
            "test code away from doing so."
        )

    def test_the_only_names_left_out_are_the_documented_non_knobs(self):
        # Imports, helpers and the middleware class are CODE, not state — a test
        # that rebound one would be monkeypatching, which pytest already undoes.
        # What is left after removing them is state, and state is what leaks.
        live = {
            name
            for name, value in vars(rate_limit_module).items()
            if not name.startswith("__")
            and not isinstance(value, (types.ModuleType, types.FunctionType, type))
        }
        unsnapshotted = live - set(_RATE_LIMIT_PRISTINE)
        assert unsnapshotted == EXPECTED_UNSNAPSHOTTED, (
            "`app.utils.rate_limit` grew a module-level global that the between-test "
            f"reset cannot restore: {sorted(unsnapshotted - EXPECTED_UNSNAPSHOTTED)}. "
            "If it is a scalar-shaped knob it should already be in the snapshot; if it "
            "is a mutable container, reassigning the name will NOT undo an in-place "
            "mutation and it needs its own reset. Decide, then update "
            "EXPECTED_UNSNAPSHOTTED."
        )

    def test_the_pristine_values_are_the_shipped_defaults(self):
        """The snapshot is only worth restoring if it is the real configuration.

        Captured at conftest import — before collection imports a test module —
        so this reads the values `app/utils/rate_limit.py` ships with, not an
        earlier file's override. Anchored on the four ceilings because those are
        the ones a reader can check against the module in one glance.
        """
        assert _RATE_LIMIT_PRISTINE["ANON_RATE_LIMIT"] == "60/minute"
        assert _RATE_LIMIT_PRISTINE["AUTH_RATE_LIMIT"] == "120/minute"
        assert _RATE_LIMIT_PRISTINE["ADMIN_RATE_LIMIT"] == "300/minute"
        assert _RATE_LIMIT_PRISTINE["TRUSTED_RATE_LIMIT"] == "600/minute"


class TestTheResetIsWiredIntoEveryTest:
    def test_the_fixture_is_autouse(self, request):
        """Not decoration: `autouse=True` is the whole delivery mechanism.

        Read off this test's own fixture closure, so it is the real wiring for a
        file that never asks for the fixture by name — which is every file the
        leak has ever hit.
        """
        assert "_reset_rate_limit_module_state" in request.fixturenames

    def test_the_restore_puts_back_a_polluted_module(self):
        """Execute the real restore against a deliberately wrecked module."""
        rate_limit_module.ANON_RATE_LIMIT = "3/minute"
        rate_limit_module._ANON_MAX = 3
        rate_limit_module._RL_CHECK_TIMEOUT = 0.01
        rate_limit_module._anon_limit = object()
        rate_limit_module._rate_limiter = object()
        rate_limit_module._async_rl_unavailable = True
        rate_limit_module._trusted_ip_cache = ("1.2.3.4", frozenset({"1.2.3.4"}))
        rate_limit_module._trusted_uid_resolver = lambda _token: "someone"

        _restore_rate_limit_module_state()

        assert _rate_limit_module_state() == _RATE_LIMIT_PRISTINE


class TestEveryTestStartsFromThePristineModule:
    """Order-independent: each case checks, then wrecks. See the module docstring.

    `_async_rl_unavailable` is the one worth spelling out. It is a ONE-WAY latch —
    `_get_async_rl_redis` returns `None` forever once it is set — and
    `tests/test_rate_limit.py` was measured leaving it `True` (it is `False` at
    import). Every test that ran after it in that worker exercised the in-memory
    fallback instead of the async-redis path it meant to test, and nothing in a
    pass or a failure would have said so. A leaked ceiling gives you a wrong red;
    this one gives you a wrong GREEN.
    """

    def _check_then_wreck(self):
        assert rate_limit_module.ANON_RATE_LIMIT == "60/minute", (
            "this test inherited a lowered anonymous ceiling from whatever ran "
            "before it — the conftest reset is not restoring between tests."
        )
        assert rate_limit_module._ANON_MAX == 60
        assert rate_limit_module._RL_CHECK_TIMEOUT == 0.6
        assert rate_limit_module._async_rl_unavailable is False, (
            "the async-redis latch arrived already set, so this test would have "
            "silently measured the memory fallback."
        )
        assert rate_limit_module._rate_limiter is None
        assert rate_limit_module._anon_limit is None

        rate_limit_module.ANON_RATE_LIMIT = "3/minute"
        rate_limit_module._ANON_MAX = 3
        rate_limit_module._RL_CHECK_TIMEOUT = 0.01
        rate_limit_module._async_rl_unavailable = True
        rate_limit_module._anon_limit = object()
        rate_limit_module._rate_limiter = object()

    def test_first_polluter(self):
        self._check_then_wreck()

    def test_second_polluter(self):
        self._check_then_wreck()

    def test_third_polluter(self):
        self._check_then_wreck()


def _app_behind_the_real_middleware():
    """A minimal app carrying the real middleware at its SHIPPED ceilings.

    Deliberately not `test_rate_limit.py`'s `_make_test_app`, which lowers the
    ceiling to make a limit reachable — the budget half of #4090 is only visible
    at the 60/minute the site actually runs.
    """
    from fastapi import FastAPI

    from app.utils.rate_limit import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/events/1")
    async def event_detail():
        return {"event": 1}

    return app


class TestTheAnonymousBudgetIsNotSpentAcrossTests:
    """The mechanism #4090 was filed on: 60/minute is per PROCESS, not per test.

    Two cases, 40 requests each, one shared client address. 80 > 60, so if the
    limiter survived a test boundary the second one to run would be throttled —
    whichever that is. Restoring `_rate_limiter` to `None` between tests drops the
    in-memory budget with it.
    """

    def _spend_forty(self):
        with TestClient(_app_behind_the_real_middleware()) as client:
            codes = [client.get("/api/events/1").status_code for _ in range(40)]
        assert 429 not in codes, (
            "an earlier test's requests were still counted against this one's "
            f"60/minute budget: {codes.count(429)} of 40 were throttled."
        )
        assert set(codes) == {200}

    def test_forty_requests_from_one_test(self):
        self._spend_forty()

    def test_forty_more_from_another(self):
        self._spend_forty()


@pytest.mark.parametrize("knob", KNOBS_WITH_A_HISTORY)
def test_each_knob_with_a_history_arrives_pristine(knob):
    """Per-knob so a failure names the knob rather than the tuple."""
    assert getattr(rate_limit_module, knob) == _RATE_LIMIT_PRISTINE[knob]
