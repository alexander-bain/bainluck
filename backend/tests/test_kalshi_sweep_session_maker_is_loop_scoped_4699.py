"""#4699 — the sweep's DEFAULT session maker must be loop-scoped, not the app's global.

Both entry points in `kalshi_resolution_sweep` are driven by `_tracked_run` ->
`run_async` -> `asyncio.run(coro)`, which builds a fresh event loop per
invocation and CLOSES it on return. They defaulted to the module-level
`async_session_maker`, whose pool survives across invocations — so on the second
run its connections are bound to the first run's dead loop and `pool_pre_ping`
raises `RuntimeError` while pinging one.

Production, the night #4655 shipped: `settle_kalshi_recent_finals` succeeded at
07:10Z (the first run after v4395 cycled the dynos, when the global pool was
empty) and then failed at 07:20Z in 80 ms and 07:30Z in 8 ms — 0 successes
against 3 starts, `last_verdict_reason: RuntimeError`, the traceback naming
`run_recent_finals() running at kalshi_resolution_sweep.py:1078` under
`asyncpg._async_ping`.

WHY NO GATE CAUGHT IT, which is the part worth keeping: every existing test
injects `session_maker`, so the `session_maker or <default>` branch — the only
branch production takes — was never executed under test. A default argument that
is bound only in production is an untested branch wearing a tested function's
coverage. These tests drive the entry points with NO injection.
"""

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.kalshi_resolution_sweep as sweep


NOW = sweep.datetime(2026, 9, 10, 7, 30, tzinfo=sweep.timezone.utc)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """A session that records the event loop it was USED on.

    The loop identity is the whole point: the defect is a connection created on
    one loop being touched on the next one, so a double that does not record
    which loop it ran on cannot tell the fixed shape from the broken one.
    """

    def __init__(self, log):
        self._log = log

    async def __aenter__(self):
        self._log.append(("enter", id(asyncio.get_running_loop())))
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        # Recorded HERE, not at construction: the loop a session is *used* on is
        # the one its connection ends up bound to, and that is what the defect
        # is about.
        self._log.append(("used", id(asyncio.get_running_loop())))
        sql = str(stmt)
        if "count(*)" in sql:
            return _Result([(0, 0, 0, 0)])
        return _Result([])

    async def commit(self):
        return None


def _recording_maker(log):
    """A stand-in for `get_task_session`: a fresh session per call."""
    def maker():
        log.append(("built", id(asyncio.get_running_loop())))
        return _RecordingSession(log)
    return maker


def _session_cm(log):
    """What a patched `async_sessionmaker` hands back inside `get_task_session`.

    `get_task_session` calls `session_maker()` and enters it, then commits and
    closes the yielded session, so the double has to answer all three.
    """
    session = _RecordingSession(log)
    session.close = _AsyncNoop()
    cm = MagicMock()
    cm.__aenter__ = _AsyncReturn(session)
    cm.__aexit__ = _AsyncReturn(False)
    return cm


class TestTheDefaultIsTheTaskScopedMaker:
    """The fix itself."""

    def test_the_default_is_get_task_session(self):
        from app.tasks.base import get_task_session
        assert sweep.default_session_maker() is get_task_session

    def test_the_default_is_not_the_apps_global_session_maker(self):
        """The regression, stated as its own assertion.

        `async_session_maker` is a perfectly good factory — it is simply bound
        to an engine whose pool outlives the loop, which is the one property
        this caller cannot tolerate.
        """
        from app.services.database import async_session_maker
        assert sweep.default_session_maker() is not async_session_maker

    def test_the_module_holds_no_executable_reference_to_the_global_maker(self):
        """Only the docstring may still name it.

        Two entry points had the identical fallback and only one ran often
        enough to expose it; a third would have inherited the same line.
        """
        src = inspect.getsource(sweep)
        code = "\n".join(
            line for line in src.splitlines()
            if "async_session_maker" in line and "#" not in line
        )
        # every surviving mention must be inside the explanatory docstring
        assert "or async_session_maker" not in src, code
        assert "session_maker or async_session_maker" not in src, code


@pytest.mark.asyncio
class TestNeitherEntryPointReachesForTheGlobal:
    """Driven with NO `session_maker` — the branch production takes."""

    async def test_run_recent_finals_uses_the_task_scoped_default(self):
        log = []
        boom = MagicMock(side_effect=AssertionError(
            "run_recent_finals reached for the app's global session maker"
        ))
        with patch.object(sweep, "default_session_maker",
                          return_value=_recording_maker(log)), \
                patch("app.services.database.async_session_maker", boom):
            report = await sweep.run_recent_finals(
                limit=5, apply=False, client_factory=lambda: MagicMock(), now=NOW,
            )
        assert report["selection"] == "recent_finals"
        assert ("built", id(asyncio.get_running_loop())) in log
        boom.assert_not_called()

    async def test_run_sweep_uses_the_task_scoped_default(self):
        log = []
        boom = MagicMock(side_effect=AssertionError(
            "run_sweep reached for the app's global session maker"
        ))
        with patch.object(sweep, "default_session_maker",
                          return_value=_recording_maker(log)), \
                patch.object(sweep, "_read_cursor", return_value=(0, 0)), \
                patch.object(sweep, "_write_cursor", return_value=True), \
                patch("app.services.database.async_session_maker", boom):
            await sweep.run_sweep(
                limit=5, apply=False, client_factory=lambda: MagicMock(),
            )
        assert log, "run_sweep never built a session at all"
        boom.assert_not_called()


class TestTwoSuccessiveLoopsIsTheFailureShape:
    """The reproduction: `asyncio.run` TWICE, exactly as the beat does.

    A single-invocation test passes against the broken code — the 07:10Z
    production run passed too, and wrote all 61 legs. Only the second
    invocation, on a second loop, discriminates.
    """

    def test_two_successive_loops_build_their_own_engine_and_never_touch_the_global(self):
        """`default_session_maker` is NOT patched here — that is the point.

        Patching the default away is how a test of this shape goes vacuous: it
        would then prove only that the entry point uses whatever it is handed.
        Here the real default chooses, and the app's global maker is a landmine
        that fails the test if the choice goes back to what it was.
        """
        import app.services.database as db
        import app.tasks.base as base

        log = []
        engines = []

        def _fake_engine(**kwargs):
            eng = MagicMock()
            eng.dispose = _AsyncNoop()
            engines.append(eng)
            return eng

        def _global_maker(*a, **k):
            raise AssertionError(
                "the default reached the app's GLOBAL session maker — this is "
                "the #4699 defect: its pool outlives the asyncio.run loop"
            )

        def run_once():
            with patch.object(base, "_get_task_engine", _fake_engine), \
                    patch.object(base, "async_sessionmaker",
                                 return_value=lambda: _session_cm(log)), \
                    patch.object(db, "async_session_maker", _global_maker):
                return asyncio.run(sweep.run_recent_finals(
                    limit=5, apply=False,
                    client_factory=lambda: MagicMock(), now=NOW,
                ))

        run_once()
        loops_after_first = {loop for _, loop in log}
        run_once()
        loops_after_second = {loop for _, loop in log}

        # Two `asyncio.run` calls => two distinct loops. The second must have
        # built its own session rather than reaching for anything the first
        # left behind.
        assert len(loops_after_second) > len(loops_after_first), (
            f"the second invocation reused the first loop: {loops_after_second}"
        )
        # An engine per use, disposed each time, so nothing can cross a loop.
        assert len(engines) >= 2, engines
        for eng in engines:
            assert eng.dispose.calls == 1, "every engine must be disposed"

    def test_get_task_session_builds_and_disposes_an_engine_per_use(self):
        """Why `get_task_session` is a safe default and the global is not.

        Nothing survives the `async with`, so nothing can be carried into the
        next loop. Asserted on the real helper, not on a copy of its shape.
        """
        import app.tasks.base as base

        engines = []

        def _fake_engine(**kwargs):
            eng = MagicMock()
            eng.dispose = _AsyncNoop()
            engines.append(eng)
            return eng

        session_cm = MagicMock()
        session_cm.__aenter__ = _AsyncReturn(MagicMock(
            commit=_AsyncNoop(), rollback=_AsyncNoop(), close=_AsyncNoop(),
        ))
        session_cm.__aexit__ = _AsyncReturn(False)

        async def _use():
            with patch.object(base, "_get_task_engine", _fake_engine), \
                    patch.object(base, "async_sessionmaker",
                                 return_value=lambda: session_cm):
                async with base.get_task_session():
                    pass

        asyncio.run(_use())
        asyncio.run(_use())

        assert len(engines) == 2, "an engine must be built per use, not shared"
        assert engines[0] is not engines[1]
        for eng in engines:
            assert eng.dispose.calls == 1, "every engine must be disposed"


class _AsyncNoop:
    def __init__(self):
        self.calls = 0

    async def __call__(self, *a, **k):
        self.calls += 1
        return None


class _AsyncReturn:
    def __init__(self, value):
        self.value = value

    async def __call__(self, *a, **k):
        return self.value
