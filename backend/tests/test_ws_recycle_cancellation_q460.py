"""Q460 / CERT-491 — the planned subscription recycle must cost ZERO seconds.

WHY THIS FILE EXISTS. `test_ws_fast_lane_wiring.py` reads the recycle machinery
with AST and passed 54/54 while the recycle was broken end to end, because the
defect lived in the seam between three layers that no single-layer test crosses:

  service  `app/services/{kalshi,polymarket}_ws.py::run()` caught
           `asyncio.CancelledError` and RETURNED;
  consumer `app/tasks/{kalshi,polymarket}_ws.py` wrapped that in
           `asyncio.wait_for(..., SUBSCRIPTION_REFRESH_SECONDS)` and so never
           saw the `TimeoutError` a swallowed cancellation cannot produce —
           `stats["status"]` stayed unset instead of becoming `"resubscribe"`;
  runner   `run_kalshi_ws.py` therefore missed its `continue` and fell through
           to `await asyncio.sleep(10)`.

Ten dead seconds out of every ten minutes on the one stream this queue exists to
keep live — the branch's own ship, quietly undone. Every test below therefore
drives the REAL code of at least two layers; the fakes stop at the socket.
"""

import asyncio
from itertools import cycle

import pytest
import websockets

import app.services.kalshi_ws as kalshi_svc
import app.services.polymarket_ws as poly_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.polymarket_ws as poly_task
import run_kalshi_ws


# ---------------------------------------------------------------- fakes ----
# The only thing faked anywhere in this file is the socket itself. A connect
# that succeeds and then streams nothing is exactly the state a healthy,
# quiet market is in — which is when the recycle timer fires.


class _QuietSocket:
    """Connects, accepts subscriptions, then never yields a message."""

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


class _QuietConnect:
    async def __aenter__(self):
        return _QuietSocket()

    async def __aexit__(self, *_exc):
        return False


class _Stop(BaseException):
    """Breaks an intentionally-infinite runner loop.

    A `BaseException` on purpose: `run_kalshi_ws.py` catches `Exception` and
    retries, so an ordinary error would be absorbed by the code under test.
    """


def _install_quiet_socket(monkeypatch, stop_after: int | None = None):
    """Point both services' `websockets.connect` at a healthy, silent socket."""
    connects = {"n": 0}

    def _connect(*_a, **_kw):
        connects["n"] += 1
        if stop_after is not None and connects["n"] > stop_after:
            raise _Stop
        return _QuietConnect()

    monkeypatch.setattr(websockets, "connect", _connect)
    # Kalshi signs its handshake; no key material in the test environment.
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    return connects


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    """Replays a fixed, repeating sequence of row batches.

    Both consumers issue their slate queries in a fixed order, and the runner
    re-issues the whole sequence on every recycle — hence `cycle`.
    """

    def __init__(self, batches):
        self._batches = batches

    async def execute(self, _stmt):
        return _Result(next(self._batches))


def _install_slate(monkeypatch, batches):
    import app.tasks.base as task_base

    shared = cycle(batches)

    class _Ctx:
        async def __aenter__(self):
            return _Session(shared)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())


#: (external_id, market_id, event_id) then (outcome_ext, market_id, outcome_id)
KALSHI_SLATE = [
    [("KXNFLGAME-26AUG31SFLAR", 7, 900)],
    [("KXNFLGAME-26AUG31SFLAR-SF", 7, 71)],
]

#: rows, then (market_id, market_ext, metadata), then (outcome_id, mid, ext)
POLY_SLATE = [
    [(71, 7, "0xabc_yes", "0xabc", 900)],
    [(7, "0xabc", {"clob_token_ids": ["111", "222"]})],
    [(71, 7, "0xabc_yes")],
]


# ------------------------------------------------- layer 1: the service ----


class TestServiceLoopLetsTheRecycleThrough:
    """`wait_for` cancels the awaiting task; a service that swallows that
    cancellation makes `wait_for` return normally, and the caller cannot tell a
    planned recycle from a stream that simply ended."""

    async def test_kalshi_run_surfaces_a_timeout_to_its_caller(self, monkeypatch):
        _install_quiet_socket(monkeypatch)
        ws = kalshi_svc.KalshiWebSocket()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.run(market_tickers=["KX-A"]), timeout=0.05)

    async def test_polymarket_run_surfaces_a_timeout_to_its_caller(self, monkeypatch):
        _install_quiet_socket(monkeypatch)
        ws = poly_svc.PolymarketWebSocket()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.run(asset_ids=["111"]), timeout=0.05)

    @pytest.mark.parametrize(
        "make_ws, kwargs",
        [
            (lambda: kalshi_svc.KalshiWebSocket(), {"market_tickers": ["KX-A"]}),
            (lambda: poly_svc.PolymarketWebSocket(), {"asset_ids": ["111"]}),
        ],
    )
    async def test_the_timeout_fired_on_a_HEALTHY_socket(
        self, monkeypatch, make_ws, kwargs
    ):
        """Non-vacuity guard for the two tests above.

        `TimeoutError` would also be raised if the fake socket crashed and the
        service spent the whole window thrashing in its reconnect backoff — a
        green test measuring nothing. Exactly one connection, and no reconnect,
        proves the window elapsed on a live stream.
        """
        _install_quiet_socket(monkeypatch)
        ws = make_ws()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.run(**kwargs), timeout=0.05)

        assert ws.stats["reconnects"] == 1, ws.stats


# ------------------------------------------------ layer 2: the consumer ----


class TestConsumerReportsThePlannedRecycle:
    """Real consumer over the real service: the recycle must arrive at the
    runner NAMED, because the runner branches on that name."""

    async def test_kalshi_consumer_returns_resubscribe(self, monkeypatch):
        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")
        monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        _install_quiet_socket(monkeypatch)
        _install_slate(monkeypatch, KALSHI_SLATE)

        stats = await kalshi_task._run_kalshi_ws_consumer()

        assert stats["status"] == "resubscribe", stats

    async def test_polymarket_consumer_returns_resubscribe(self, monkeypatch):
        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        _install_quiet_socket(monkeypatch)
        _install_slate(monkeypatch, POLY_SLATE)

        stats = await poly_task._run_polymarket_ws_consumer()

        assert stats["status"] == "resubscribe", stats

    async def test_the_recycle_is_not_confused_with_an_empty_slate(self, monkeypatch):
        """`no_markets` and `resubscribe` take different runner branches — one
        sleeps 60s, the other must not sleep at all."""
        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")
        monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        _install_quiet_socket(monkeypatch)
        _install_slate(monkeypatch, [[]])

        stats = await kalshi_task._run_kalshi_ws_consumer()

        assert stats["status"] == "no_markets"


class TestShutdownIsNotSwallowed:
    """The mirror image: a REAL cancellation must keep travelling, or the runner
    relaunches a consumer the dyno is trying to stop."""

    @pytest.mark.parametrize(
        "make_ws, kwargs",
        [
            (lambda: kalshi_svc.KalshiWebSocket(), {"market_tickers": ["KX-A"]}),
            (lambda: poly_svc.PolymarketWebSocket(), {"asset_ids": ["111"]}),
        ],
    )
    async def test_cancelling_the_service_raises_cancelled(
        self, monkeypatch, make_ws, kwargs
    ):
        _install_quiet_socket(monkeypatch)
        ws = make_ws()
        task = asyncio.create_task(ws.run(**kwargs))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_cancelling_the_kalshi_consumer_raises_cancelled(self, monkeypatch):
        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")
        # Long window: the cancellation under test must be the OUTER one, not
        # the recycle timer.
        monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 600)
        _install_quiet_socket(monkeypatch)
        _install_slate(monkeypatch, KALSHI_SLATE)

        task = asyncio.create_task(kalshi_task._run_kalshi_ws_consumer())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


# -------------------------------------------------- layer 3: the runner ----


class _AsyncioShim:
    """`run_kalshi_ws.asyncio` with a recording `sleep`. Scoped to the module
    under test so nothing else in the loop is affected."""

    def __init__(self):
        self.sleeps: list[float] = []

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, delay, *args, **kwargs):
        self.sleeps.append(delay)
        return await asyncio.sleep(0)


class TestRunnerPaysNoBackoffForARecycle:
    async def test_kalshi_recycle_never_sleeps(self, monkeypatch):
        shim = _AsyncioShim()
        monkeypatch.setattr(run_kalshi_ws, "asyncio", shim)
        calls = {"n": 0}

        async def _consumer():
            calls["n"] += 1
            if calls["n"] > 3:
                raise _Stop
            return {"status": "resubscribe"}

        monkeypatch.setattr(kalshi_task, "_run_kalshi_ws_consumer", _consumer)

        with pytest.raises(_Stop):
            await run_kalshi_ws.run_kalshi()

        assert shim.sleeps == [], f"planned recycle paid a backoff: {shim.sleeps}"

    async def test_polymarket_recycle_never_sleeps(self, monkeypatch):
        shim = _AsyncioShim()
        monkeypatch.setattr(run_kalshi_ws, "asyncio", shim)
        calls = {"n": 0}

        async def _consumer():
            calls["n"] += 1
            if calls["n"] > 3:
                raise _Stop
            return {"status": "resubscribe"}

        monkeypatch.setattr(poly_task, "_run_polymarket_ws_consumer", _consumer)

        with pytest.raises(_Stop):
            await run_kalshi_ws.run_polymarket()

        assert shim.sleeps == [], f"planned recycle paid a backoff: {shim.sleeps}"

    async def test_a_real_crash_STILL_takes_the_backoff(self, monkeypatch):
        """Non-vacuity guard for the two tests above: an empty sleep list must
        mean "the recycle branch fired", not "this shim records nothing"."""
        shim = _AsyncioShim()
        monkeypatch.setattr(run_kalshi_ws, "asyncio", shim)
        calls = {"n": 0}

        async def _consumer():
            calls["n"] += 1
            if calls["n"] > 2:
                raise _Stop
            raise RuntimeError("socket exploded")

        monkeypatch.setattr(kalshi_task, "_run_kalshi_ws_consumer", _consumer)

        with pytest.raises(_Stop):
            await run_kalshi_ws.run_kalshi()

        assert shim.sleeps == [10, 10], shim.sleeps


# ------------------------------------------------- all three, end to end ----


class TestTheWholeStackRecyclesForFree:
    """The test the cert asked for. Real service + real consumer + real runner;
    only the socket and the slate query are faked. This is the one that would
    have caught CERT-491, and the only one here that no single layer can pass
    on its own.
    """

    async def test_kalshi_recycles_repeatedly_without_a_single_backoff(
        self, monkeypatch
    ):
        monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
        monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-pem")
        monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        connects = _install_quiet_socket(monkeypatch, stop_after=3)
        _install_slate(monkeypatch, KALSHI_SLATE)
        shim = _AsyncioShim()
        monkeypatch.setattr(run_kalshi_ws, "asyncio", shim)

        with pytest.raises(_Stop):
            await run_kalshi_ws.run_kalshi()

        assert connects["n"] == 4, "the runner must re-read the slate each cycle"
        assert shim.sleeps == [], (
            f"three planned recycles cost {sum(shim.sleeps)}s of dead air"
        )

    async def test_polymarket_recycles_repeatedly_without_a_single_backoff(
        self, monkeypatch
    ):
        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        connects = _install_quiet_socket(monkeypatch, stop_after=3)
        _install_slate(monkeypatch, POLY_SLATE)
        shim = _AsyncioShim()
        monkeypatch.setattr(run_kalshi_ws, "asyncio", shim)

        with pytest.raises(_Stop):
            await run_kalshi_ws.run_polymarket()

        assert connects["n"] == 4
        assert shim.sleeps == [], (
            f"three planned recycles cost {sum(shim.sleeps)}s of dead air"
        )
