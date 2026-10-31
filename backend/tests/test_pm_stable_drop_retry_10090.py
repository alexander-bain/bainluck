"""#10090: a stable game socket that dies abruptly re-dials from a 0.25 s base.

Production 2026-10-30 (Argon, Part A): 408 of 410 peak game-socket drops were
"no close frame received or sent", ~77 % of them after a connection that had
held at least STABLE_CONNECTION_SECONDS, and disconnect-to-resubscribe was
p50 1.12-1.23 s — mostly the reset backoff's U[0.5, 1.0] sleep. That ONE sleep
now draws from U[0.125, 0.25]; the backoff state, every other close kind, the
initial connect and cancellation are unchanged. These drive the REAL
`_run_one` loop with a fake clock and scripted sockets.
"""

import asyncio
import json
import logging
import sys

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from app.services import polymarket_ws as poly_svc
from tests.test_pm_repeat_skip_10090 import assert_handled, callbacks, handled_once, quote


class _Stop(BaseException):
    """Not an Exception, so `_run_one`'s reconnect loop cannot swallow it."""


class _Loop:
    def __init__(self, shim):
        self._shim = shim

    def time(self):
        return self._shim.t

    def __getattr__(self, name):
        return getattr(asyncio.get_running_loop(), name)


class _Shim:
    """`asyncio` for the client module: sleeps advance a fake clock."""

    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def __getattr__(self, name):
        return getattr(asyncio, name)

    def get_running_loop(self):
        return _Loop(self)

    async def sleep(self, delay, *a, **kw):
        if _redial_sleep():
            self.sleeps.append(delay)
            self.t += delay
        return await asyncio.sleep(0)


def _redial_sleep() -> bool:
    """Called from `_run_one`'s loop, not the heartbeat or a coverage/yield."""
    caller = sys._getframe(2).f_code
    return caller.co_name == "_run_one" and caller.co_filename == poly_svc.__file__


def _abrupt():
    return ConnectionClosedError(None, None)


def _closed_by_venue(code=1013, reason="slow consumer"):
    return ConnectionClosedError(Close(code, reason), None)


def _closed_by_us():
    return ConnectionClosedError(None, Close(1000, ""))


class _Socket:
    """Lives ``lives`` fake seconds after its frames, then ends with ``ends``."""

    def __init__(self, shim, lives, ends=None, frames=()):
        self._shim, self._lives, self._ends, self._frames = shim, lives, ends, frames

    async def send(self, _payload):
        return None

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield frame
            self._shim.t += self._lives
            if self._ends is not None:
                raise self._ends

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _script(monkeypatch, attempts, jitter=1.0):
    """``attempts``: per dial, ``(lives, ends)`` or an exception the dial raises."""
    shim = _Shim()
    dials = iter(attempts)

    def connect(*_a, **_kw):
        step = next(dials, None)
        if step is None:
            raise _Stop
        if isinstance(step, BaseException):
            raise step
        return _Socket(shim, *step)

    monkeypatch.setattr(websockets, "connect", connect)
    monkeypatch.setattr(poly_svc.random, "random", lambda: jitter)
    monkeypatch.setattr(poly_svc, "asyncio", shim)
    return shim


async def _run(base=poly_svc.PM_WS_STABLE_RETRY_BASE_DEFAULT_S):
    with pytest.raises(_Stop):
        await poly_svc.PolymarketWebSocket(stable_drop_retry_base=base).run(
            asset_ids=["1"]
        )


STABLE = poly_svc.STABLE_CONNECTION_SECONDS


class TestOneShortRetry:
    async def test_a_stable_socket_dropped_with_no_close_frame_redials_from_a_quarter(
        self, monkeypatch
    ):
        shim = _script(monkeypatch, [(STABLE, _abrupt())] * 3)
        await _run()
        assert shim.sleeps == [0.25, 0.25, 0.25]

    async def test_it_is_still_jittered(self, monkeypatch):
        shim = _script(monkeypatch, [(STABLE, _abrupt())], jitter=0.0)
        await _run()
        assert shim.sleeps == [0.125]

    async def test_the_backoff_state_is_untouched_so_an_unstable_drop_escalates(
        self, monkeypatch
    ):
        # Today: 1, 2, 4 after a stable drop then two quick ones. Only the
        # first sleep moves; the next failure still waits 2 then 4.
        shim = _script(
            monkeypatch,
            [(STABLE, _abrupt()), (1.0, _abrupt()), (1.0, _abrupt())],
        )
        await _run()
        assert shim.sleeps == [0.25, 2.0, 4.0]

    async def test_a_stable_drop_after_escalation_resets_and_retries_short(
        self, monkeypatch
    ):
        shim = _script(
            monkeypatch,
            [(1.0, _abrupt()), (1.0, _abrupt()), (STABLE, _abrupt()), (1.0, _abrupt())],
        )
        await _run()
        assert shim.sleeps == [1.0, 2.0, 0.25, 2.0]


class TestEverythingElseIsTodays:
    async def test_an_unstable_abrupt_drop(self, monkeypatch):
        shim = _script(monkeypatch, [(STABLE - 0.5, _abrupt())] * 3)
        await _run()
        assert shim.sleeps == [1.0, 2.0, 4.0]

    async def test_a_failed_initial_connect(self, monkeypatch):
        shim = _script(monkeypatch, [OSError("refused")] * 3)
        await _run()
        assert shim.sleeps == [1.0, 2.0, 4.0]

    async def test_a_clean_close_keeps_its_floor(self, monkeypatch):
        shim = _script(monkeypatch, [(STABLE, None), (STABLE, None)])
        await _run()
        assert shim.sleeps == [1.0, 1.0]

    async def test_a_received_1013_or_any_close_code(self, monkeypatch):
        shim = _script(
            monkeypatch,
            [(STABLE, _closed_by_venue()), (STABLE, _closed_by_venue(1011, "")),
             (STABLE, _closed_by_us())],
        )
        await _run()
        assert shim.sleeps == [1.0, 1.0, 1.0]

    async def test_another_exception_on_a_stable_socket(self, monkeypatch):
        shim = _script(monkeypatch, [(STABLE, OSError("reset"))])
        await _run()
        assert shim.sleeps == [1.0]

    async def test_a_client_that_did_not_opt_in(self, monkeypatch):
        # The open-contract and shadow clients are built without the base.
        shim = _script(monkeypatch, [(STABLE, _abrupt())] * 2)
        await _run(base=None)
        assert shim.sleeps == [1.0, 1.0]

    async def test_switch_one_is_todays_sleep_exactly(self, monkeypatch):
        monkeypatch.setenv("PM_WS_STABLE_RETRY_BASE_S", "1")
        for jitter in (0.0, 0.37, 1.0):
            shim = _script(monkeypatch, [(STABLE, _abrupt()), (1.0, _abrupt())], jitter)
            await _run(base=poly_svc.stable_drop_retry_base_seconds())
            today = _script(monkeypatch, [(STABLE, _abrupt()), (1.0, _abrupt())], jitter)
            await _run(base=None)
            assert shim.sleeps == today.sleeps


class TestCancellation:
    async def test_cancelled_during_the_short_sleep_does_not_redial(self, monkeypatch):
        shim = _Shim()
        dials = {"n": 0}
        sleeping = asyncio.Event()
        release = asyncio.Event()

        async def sleep(delay, *a, **kw):
            if not _redial_sleep():
                return await asyncio.sleep(0)
            shim.sleeps.append(delay)
            sleeping.set()
            await release.wait()  # held until cancelled

        shim.sleep = sleep

        def connect(*_a, **_kw):
            dials["n"] += 1
            return _Socket(shim, STABLE, _abrupt())

        monkeypatch.setattr(websockets, "connect", connect)
        monkeypatch.setattr(poly_svc.random, "random", lambda: 1.0)
        monkeypatch.setattr(poly_svc, "asyncio", shim)
        client = poly_svc.PolymarketWebSocket(stable_drop_retry_base=0.25)
        task = asyncio.ensure_future(client.run(asset_ids=["1"]))
        await asyncio.wait_for(sleeping.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert shim.sleeps == [0.25]
        assert dials["n"] == 1
        assert client.stats["shards_connected"] == 0

    async def test_cancelled_while_connected_raises_and_never_sleeps(self, monkeypatch):
        shim = _Shim()
        connected = asyncio.Event()

        class _Holds(_Socket):
            def __aiter__(self):
                async def gen():
                    connected.set()
                    await asyncio.Event().wait()
                    yield  # pragma: no cover

                return gen()

        monkeypatch.setattr(websockets, "connect", lambda *a, **kw: _Holds(shim, 0))
        monkeypatch.setattr(poly_svc, "asyncio", shim)
        client = poly_svc.PolymarketWebSocket(stable_drop_retry_base=0.25)
        task = asyncio.ensure_future(client.run(asset_ids=["1"]))
        await asyncio.wait_for(connected.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert shim.sleeps == []

    async def test_a_catalog_replacement_during_the_short_sleep_joins_the_shard(
        self, monkeypatch
    ):
        # `run_refreshable` restarts a socket by cancelling its task; one
        # caught in the short retry sleep stops there, and its tokens re-dial
        # on the replacement socket.
        shim = _Shim()
        dialled: list[int] = []
        sleeping = asyncio.Event()

        async def sleep(delay, *a, **kw):
            if not _redial_sleep():
                return await asyncio.sleep(0)
            shim.sleeps.append(delay)
            sleeping.set()
            await asyncio.Event().wait()

        shim.sleep = sleep

        class _HoldOpen(_Socket):
            def __aiter__(self):
                async def gen():
                    await asyncio.Event().wait()
                    yield  # pragma: no cover

                return gen()

        def connect(*_a, **_kw):
            dialled.append(len(dialled))
            if len(dialled) == 1:
                return _Socket(shim, STABLE, _abrupt())
            return _HoldOpen(shim, 0)

        monkeypatch.setattr(websockets, "connect", connect)
        monkeypatch.setattr(poly_svc.random, "random", lambda: 1.0)
        monkeypatch.setattr(poly_svc, "asyncio", shim)
        client = poly_svc.PolymarketWebSocket(stable_drop_retry_base=0.25)
        task = asyncio.ensure_future(client.run_refreshable(["1"]))
        await asyncio.wait_for(sleeping.wait(), 2)
        # The catalog empties the socket (repack) and adds a new token.
        client.update_asset_ids(["2"])
        for _ in range(50):
            await asyncio.sleep(0)
            if len(dialled) >= 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert shim.sleeps == [0.25]
        assert len(dialled) == 2


class TestTheLog:
    async def test_the_warning_names_the_base_so_the_readout_can_split_the_cases(
        self, monkeypatch, caplog
    ):
        _script(monkeypatch, [(STABLE, _abrupt()), (1.0, _abrupt())])
        with caplog.at_level(logging.WARNING, logger=poly_svc.logger.name):
            await _run()
        lines = [r.getMessage() for r in caplog.records if "disconnected" in r.getMessage()]
        assert lines[0].endswith("reconnecting in 0.2s (base 0.25s)")
        assert "no close frame received or sent" in lines[0]
        assert lines[1].endswith("reconnecting in 2.0s (base 2.00s)")


class TestSwitch:
    def test_reads_seconds_default_quarter_junk_is_todays(self, monkeypatch, caplog):
        read = poly_svc.stable_drop_retry_base_seconds
        monkeypatch.delenv("PM_WS_STABLE_RETRY_BASE_S", raising=False)
        assert read() == 0.25
        for raw, want in (("", 0.25), ("  ", 0.25), ("0.1", 0.1), ("1", 1.0),
                          ("2", 1.0), ("0", 1.0), ("-1", 1.0), ("nan", 1.0),
                          ("inf", 1.0)):
            monkeypatch.setenv("PM_WS_STABLE_RETRY_BASE_S", raw)
            assert read() == want, raw
        monkeypatch.setenv("PM_WS_STABLE_RETRY_BASE_S", "fast")
        with caplog.at_level(logging.WARNING, logger=poly_svc.logger.name):
            assert read() == 1.0
        assert "not a number" in caplog.text

    def test_the_game_client_opts_in_and_the_open_client_does_not(self):
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "app/tasks/polymarket_ws.py"
        text = src.read_text()
        game = text.index("ws = PolymarketWebSocket(\n        price_book_snapshots=")
        assert "stable_drop_retry_base=stable_drop_retry_base_seconds()" in (
            text[game : game + 300]
        )
        assert text.count("stable_drop_retry_base=") == 1


# ------------------------------------------- the 250 ms repeat window ----


class TestAReconnectInsideTheRepeatWindow:
    """The short retry lands the catch-up snapshot inside PM_WS_REPEAT_SKIP_MS
    of the last quote handled before the drop. The snapshot is still priced."""

    async def test_the_reconnect_snapshot_reaches_on_price_flagged_after_the_short_sleep(
        self, monkeypatch
    ):
        shim = _Shim()

        def book(bid, ask):
            return json.dumps([{"asset_id": "1", "market": "m", "timestamp": "1",
                                "bids": [{"price": bid}], "asks": [{"price": ask}]}])

        dials = iter([
            _Socket(shim, STABLE, _abrupt(), [book("0.60", "0.62")]),
            _Socket(shim, 0, _Stop(), [book("0.70", "0.72")]),
        ])
        monkeypatch.setattr(websockets, "connect", lambda *a, **kw: next(dials))
        monkeypatch.setattr(poly_svc.random, "random", lambda: 1.0)
        monkeypatch.setattr(poly_svc, "asyncio", shim)
        seen = []
        client = poly_svc.PolymarketWebSocket(
            price_book_snapshots=True, stable_drop_retry_base=0.25
        )
        client.on_price = lambda q: seen.append((shim.t, dict(q)))
        with pytest.raises(_Stop):
            await client.run(asset_ids=["1"])
        assert shim.sleeps == [0.25]
        (_t0, first), (t1, second) = seen
        assert (first["best_bid"], second["best_bid"]) == ("0.6", "0.7")
        assert second["book_snapshot"] is True
        # The gap from the drop to the snapshot is the short sleep, inside
        # the default 250 ms repeat window.
        assert t1 - STABLE == 0.25

    async def test_a_quiet_book_that_moved_during_the_gap_is_priced(self, monkeypatch):
        r = callbacks(monkeypatch)
        await handled_once(r)  # handled at t, then t += 0.1
        r.clock.t += poly_svc.PM_WS_STABLE_RETRY_BASE_DEFAULT_S - 0.1 - 1e-6
        # Control: inside the window, a plain repeat of the old book is skipped.
        await r.ns["handle_price"](quote())
        assert r.ns["stats"]["repeats_skipped"] == 1
        # The reconnect snapshot carries the book that moved while we were down.
        await r.ns["handle_price"](quote(bid="0.70", ask="0.72", book_snapshot=True))
        assert len(r.marks) == 2
        assert r.ns["price_buffer"] == {1: 0.71, 2: 0.29}
        assert r.ns["catalog_boundary"].flush_wake.is_set()

    async def test_an_unchanged_snapshot_inside_the_window_is_still_handled(
        self, monkeypatch
    ):
        r = callbacks(monkeypatch)
        await handled_once(r)
        await r.ns["handle_price"](quote(book_snapshot=True))
        assert_handled(r)
        assert r.ns["stats"]["repeats_skipped"] == 0
