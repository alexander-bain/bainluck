"""#9418 — a match that turns live mid-cycle is admitted to the socket in ~1.5 min.

Before: both WS consumers held one subscription for `SUBSCRIPTION_REFRESH_SECONDS`
(600 s in production), so an event that went live after the slate was read —
a suspended match resuming, a start moved earlier — streamed nothing for up to
ten minutes. After: each consumer re-reads its slate's live arm every 30 s and
ends the run early, through the existing recycle, when a live event is missing.

The four guards the directive names, each driven through the REAL consumer over
the REAL service (only the socket and the session are faked):

- a missing live event recycles, named as an admission;
- a complete subscription does not recycle, however often it is checked;
- the thrash floor holds — no early end before the floor;
- a failed reread never recycles.
"""

import asyncio
import time

import pytest
import websockets
from sqlalchemy.dialects import postgresql

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.polymarket_ws as poly_task
import app.tasks.ws_admission as admission


# ---------------------------------------------------------------- fakes ----


class _QuietSocket:
    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


class _QuietConnect:
    async def __aenter__(self):
        return _QuietSocket()

    async def __aexit__(self, *_exc):
        return False


def _install_quiet_socket(monkeypatch):
    connects = {"n": 0}

    def _connect(*_a, **_kw):
        connects["n"] += 1
        return _QuietConnect()

    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    return connects


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _install_session(monkeypatch, slate_batches, reread):
    """The slate's queries are answered in order; every later query is the
    admission reread, answered by `reread()` (which may raise).

    Routing by position, not by cycling, because the reread repeats every
    check: a cycling fake would hand the second reread the slate's first batch.
    """
    import app.tasks.base as task_base

    state = {"slate": list(slate_batches), "rereads": [], "reread_calls": 0}

    class _Session:
        async def execute(self, stmt):
            if state["slate"]:
                return _Result(state["slate"].pop(0))
            state["reread_calls"] += 1
            state["rereads"].append(stmt)
            return _Result([_reread_row(r) for r in reread()])

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
    return state


def _reread_row(r):
    """#9462 review: the reread is per market, beside the stored reading. A
    bare event id stands for one market with no reading — event 900's slate
    market 7 (mapped in both venues), any other event's unmapped market."""
    if isinstance(r, tuple):
        return r
    return (r, 7 if r == 900 else r * 10, None)


#: Event 900 is on the slate in both venues.
KALSHI_SLATE = [
    [("KXATPMATCH-26SEP28ANGJOH", 7, 900)],
    [("KXATPMATCH-26SEP28ANGJOH-ANG", 7, 71)],
]
POLY_SLATE = [
    [(71, 7, "0xabc_yes", "0xabc", 900)],
    [(7, "0xabc", {"clob_token_ids": ["111", "222"]})],
    [(71, 7, "0xabc_yes")],
]


def _kalshi(monkeypatch):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")
    return kalshi_task, kalshi_task._run_kalshi_ws_consumer, KALSHI_SLATE


def _poly(_monkeypatch):
    return poly_task, poly_task._run_polymarket_ws_consumer, POLY_SLATE


ARMS = pytest.mark.parametrize("arm", [_kalshi, _poly], ids=["kalshi", "polymarket"])


def _timing(monkeypatch, module, *, refresh, check, floor):
    monkeypatch.setattr(module, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", check)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", floor)


# ------------------------------------------------ the consumer, end to end ----


class TestAMissingLiveEventRecycles:
    @ARMS
    async def test_a_live_event_the_slate_missed_ends_the_run_early(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=30, check=0.01, floor=0)
        connects = _install_quiet_socket(monkeypatch)
        # 901 turned live after the slate was read.
        _install_session(monkeypatch, slate, lambda: [900, 901])

        started = time.monotonic()
        stats = await asyncio.wait_for(consumer(), timeout=5)

        assert stats["status"] == "resubscribe"
        assert stats["recycle_reason"] == "admission"
        assert stats["admitted_event_ids"] == [901]
        # Early, not the 30 s timer.
        assert time.monotonic() - started < 5
        assert connects["n"] >= 1

    @ARMS
    async def test_the_runner_takes_an_admission_recycle_without_the_backoff(
        self, monkeypatch, arm,
    ):
        """The runner's `continue` branches on `status == "resubscribe"` —
        an admission recycle must arrive under that name, not a new one the
        runner would treat as a crash (10 s sleep)."""
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=30, check=0.01, floor=0)
        _install_quiet_socket(monkeypatch)
        _install_session(monkeypatch, slate, lambda: [901])

        stats = await asyncio.wait_for(consumer(), timeout=5)

        assert stats["status"] == "resubscribe"


class TestACompleteSubscriptionDoesNotRecycle:
    @ARMS
    async def test_every_live_event_subscribed_runs_to_the_timer(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=0.3, check=0.01, floor=0)
        connects = _install_quiet_socket(monkeypatch)
        state = _install_session(monkeypatch, slate, lambda: [900])

        stats = await asyncio.wait_for(consumer(), timeout=5)

        assert stats["status"] == "resubscribe"
        assert "recycle_reason" not in stats
        # Non-vacuity: the reread really ran, many times, and was satisfied.
        assert state["reread_calls"] >= 5, state["reread_calls"]
        assert connects["n"] == 1

    @ARMS
    async def test_no_live_events_at_all_does_not_recycle(self, monkeypatch, arm):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=0.2, check=0.01, floor=0)
        _install_quiet_socket(monkeypatch)
        _install_session(monkeypatch, slate, lambda: [])

        stats = await asyncio.wait_for(consumer(), timeout=5)

        assert "recycle_reason" not in stats


class TestTheThrashFloorHolds:
    @ARMS
    async def test_a_missing_event_waits_for_the_floor(self, monkeypatch, arm):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=30, check=0.01, floor=0.4)
        _install_quiet_socket(monkeypatch)
        state = _install_session(monkeypatch, slate, lambda: [900, 901])

        started = time.monotonic()
        stats = await asyncio.wait_for(consumer(), timeout=5)
        elapsed = time.monotonic() - started

        assert stats["recycle_reason"] == "admission"
        assert elapsed >= 0.4, elapsed
        # The missing event was SEEN well before the floor and held back.
        assert state["reread_calls"] >= 5, state["reread_calls"]

    async def test_the_watcher_never_returns_before_the_floor(self):
        now = {"t": 0.0}
        calls = {"n": 0}

        async def load():
            calls["n"] += 1
            now["t"] += 10  # each check is 10 s later
            return {901}

        missing = await asyncio.wait_for(
            admission.watch_for_unadmitted_live_events(
                load, [900], arm="t", started_at=0.0,
                check_seconds=0, min_recycle_seconds=60,
                clock=lambda: now["t"],
            ),
            timeout=2,
        )

        assert missing == frozenset({901})
        assert now["t"] >= 60
        assert calls["n"] == 6  # 10 baseline, 20..50 held, 60 returns

    def test_production_defaults_bound_admission_to_about_ninety_seconds(self):
        assert admission.ADMISSION_CHECK_SECONDS == 30
        assert admission.ADMISSION_MIN_RECYCLE_SECONDS == 60
        assert (
            admission.ADMISSION_CHECK_SECONDS
            + admission.ADMISSION_MIN_RECYCLE_SECONDS
        ) <= 90


class TestAFailedRereadNeverRecycles:
    @ARMS
    async def test_a_reread_that_raises_keeps_the_subscription(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=0.3, check=0.01, floor=0)
        connects = _install_quiet_socket(monkeypatch)

        def _boom():
            raise RuntimeError("db down")

        state = _install_session(monkeypatch, slate, _boom)

        stats = await asyncio.wait_for(consumer(), timeout=5)

        assert stats["status"] == "resubscribe"
        assert "recycle_reason" not in stats
        assert state["reread_calls"] >= 5
        assert connects["n"] == 1

    async def test_a_failure_then_a_missing_event_still_recycles(self):
        """A failed reread is skipped, not fatal to the watcher — and the
        baseline is the first reread that SUCCEEDS."""
        answers = iter([RuntimeError("blip"), set(), {901}])

        async def load():
            a = next(answers)
            if isinstance(a, Exception):
                raise a
            return a

        missing = await asyncio.wait_for(
            admission.watch_for_unadmitted_live_events(
                load, [900], arm="t", started_at=0.0,
                check_seconds=0, min_recycle_seconds=0,
            ),
            timeout=2,
        )
        assert missing == frozenset({901})


# ------------------------------------------------- the reread's shape ----


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )
    )


class TestTheRereadIsTheSlatesLiveArm:
    """The reread must be a SUBSET of the slate's live arm, or an event it
    names can never be admitted and the floor becomes a once-a-minute loop."""

    @ARMS
    async def test_the_reread_selects_live_linked_events_of_its_own_venue(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = arm(monkeypatch)
        _timing(monkeypatch, module, refresh=0.1, check=0.01, floor=0)
        _install_quiet_socket(monkeypatch)
        state = _install_session(monkeypatch, slate, lambda: [900])

        await asyncio.wait_for(consumer(), timeout=5)

        assert state["rereads"], "the reread never ran"
        sql = _sql(state["rereads"][0])
        venue = "kalshi" if module is kalshi_task else "polymarket"
        assert f"futures_markets.source = '{venue}'" in sql
        assert "events.status = 'live'" in sql
        assert "futures_markets.event_id IS NOT NULL" in sql
        assert "scheduled" not in sql

    async def test_the_polymarket_reread_skips_settled_markets_like_the_slate(
        self, monkeypatch,
    ):
        _timing(monkeypatch, poly_task, refresh=0.1, check=0.01, floor=0)
        _install_quiet_socket(monkeypatch)
        state = _install_session(monkeypatch, POLY_SLATE, lambda: [900])

        await asyncio.wait_for(poly_task._run_polymarket_ws_consumer(), timeout=5)

        sql = _sql(state["rereads"][0])
        assert _sql_fragment(poly_task._slate_market_filter()) in sql
        # And it joins outcomes, as the slate does, so an outcome-less market
        # the slate cannot return is not named either.
        assert "FROM futures_outcomes" in sql


def _sql_fragment(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )
    )


# ------------------------------------------------ run_until_admission ----


class TestRunUntilAdmission:
    async def test_the_socket_is_cancelled_when_the_watcher_names_an_event(self):
        cancelled = asyncio.Event()

        async def run():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def watch():
            return frozenset({901})

        assert await admission.run_until_admission(run(), watch()) == frozenset({901})
        assert cancelled.is_set()

    async def test_a_socket_error_propagates_as_before(self):
        async def run():
            raise ValueError("socket")

        async def watch():
            await asyncio.sleep(3600)

        with pytest.raises(ValueError):
            await admission.run_until_admission(run(), watch())

    async def test_a_broken_watcher_leaves_the_socket_running(self):
        async def run():
            await asyncio.sleep(0.05)
            return "ended"

        async def watch():
            raise RuntimeError("watcher bug")

        assert await admission.run_until_admission(run(), watch()) is None

    async def test_the_timer_cancels_both_socket_and_watcher(self):
        seen = set()

        async def run():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                seen.add("run")
                raise

        async def watch():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                seen.add("watch")
                raise

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                admission.run_until_admission(run(), watch()), timeout=0.05,
            )
        assert seen == {"run", "watch"}
