"""#683 archive rail: the operational bounds of an ATTENDED run, and nothing else.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable older probability journey on web and native, with explicit
archive provenance.

The planner (:mod:`app.services.kalshi_archive_recovery`) and the importer
(:mod:`app.services.kalshi_archive_apply`) are run by a person, against
production, under a reviewed budget. This module is where that budget is
enforced. It changes no global default: the house engine, the shared Kalshi
client and every other caller keep exactly the behaviour they had.

WHAT IS BOUNDED, AND HOW

* **Every database connection** these two modules open carries
  ``statement_timeout`` = :data:`ARCHIVE_STATEMENT_TIMEOUT_MS` and
  ``lock_timeout`` = :data:`ARCHIVE_LOCK_TIMEOUT_MS` as asyncpg STARTUP
  parameters (``get_task_session``'s per-engine channel, #4482). A startup
  parameter belongs to the connection, so it survives ``COMMIT``, ``ROLLBACK``,
  ``RESET`` and a pool reconnect, which a ``SET`` does not. Each session also
  reads both values back from ``pg_settings`` before its first statement and
  refuses to run unarmed (:class:`ArchiveSessionUnarmed`).
* **Every HTTP response** on this rail is streamed and counted BEFORE it is
  buffered (:class:`BoundedArchiveService`). A ``Content-Length`` over the cap
  is refused before the body is read; a body that grows past the per-response
  cap, or pushes the run past its total, is abandoned mid-stream. At most one
  transport chunk beyond a cap is ever held. A non-identity
  ``Content-Encoding`` is refused rather than decoded (identity is requested),
  so the counted bytes are the bytes parsed.
* **The whole operation** runs inside an :class:`OperationWall`: connection,
  plan loading and decoding, validation, database work, serialisation, and the
  cancel/close that ends it. Async work is cancelled at the wall; synchronous
  work is interrupted by ``SIGALRM`` where Python allows it (main thread).
* **Console and artifact output** is capped (:class:`ConsoleCap`,
  :func:`write_bounded_artifact`). Over the cap nothing more is written, the
  overflow is reported, and the exit is non-zero. An artifact is written whole
  or not at all, and never over an existing file.
* **Console delivery** is inside the same wall: once bound, every write to the
  real stdout/stderr is written AND flushed under the wall's alarm (work
  deadline while working, hard deadline for the receipt), so no byte is left
  in a Python buffer for the interpreter's exit flush. A sink that misses the
  wall makes the console unavailable for the rest of the run (nothing more is
  sent to it, the exit is held at 3) and :func:`exit_process` ends the process
  without the exit flush that would block on that sink again.

WHAT IS NOT BOUNDED HERE (stated, never implied): libpq/asyncpg's internal
result buffers before a row reaches Python; bytes a native library writes to
file descriptor 1 or 2 directly; the server side of a statement after the
client gave up (``statement_timeout`` is what bounds that); delivery of console
bytes the kernel accepted before the wall (the reader of a pipe or terminal
owns those); and a console write off the main thread (no alarm: checked before
and after only).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text

#: Per-statement and per-lock-wait bounds for EVERY connection on this rail.
ARCHIVE_STATEMENT_TIMEOUT_MS = 10_000
ARCHIVE_LOCK_TIMEOUT_MS = 500

#: The first attended sample's reviewed profile. Defaults for the CLIs, NOT a
#: ceiling on later reviewed runs (the 150K-outcome/10K-per-run scale is
#: unpaid and needs its own reviewed budget).
FIRST_SAMPLE_PROFILE = {
    "outcomes": 1,
    "hourly_slots_max": 26,
    "provider_requests_max": 3,
    "pace_seconds": 2.0,
    "planner_wall_seconds": 120.0,
    "response_bytes_max": 1 << 20,
    "total_response_bytes_max": 3 << 20,
    "plan_bytes_max": 256 << 10,
    "console_bytes_max": 256 << 10,
    "import_wall_seconds": 30.0,
    "statement_timeout_ms": ARCHIVE_STATEMENT_TIMEOUT_MS,
    "lock_timeout_ms": ARCHIVE_LOCK_TIMEOUT_MS,
}

#: Settings each archive session must read back before its first statement.
SESSION_BUDGET_SQL = (
    "SELECT name, setting FROM pg_settings"
    " WHERE name IN ('statement_timeout', 'lock_timeout')"
)


class ArchiveSessionUnarmed(RuntimeError):
    """A session came up without the archive statement/lock bounds. Nothing ran."""


async def verify_session_budget(session: Any) -> dict:
    """Read both bounds back from the server; raise unless they are the archive's."""
    rows = (await session.execute(text(SESSION_BUDGET_SQL))).fetchall()
    found = {str(r[0]): str(r[1]) for r in rows}
    want = {
        "statement_timeout": str(ARCHIVE_STATEMENT_TIMEOUT_MS),
        "lock_timeout": str(ARCHIVE_LOCK_TIMEOUT_MS),
    }
    if found != want:
        raise ArchiveSessionUnarmed(f"session_budget_unarmed:{found}")
    return found


@asynccontextmanager
async def archive_session():
    """A task session whose every connection carries the archive bounds.

    The bounds travel as asyncpg startup parameters on a fresh engine, so a
    connection opened after a commit or a pool reconnect carries them too. A
    URL without that channel (anything not asyncpg) comes up unarmed and is
    refused here before the caller's first statement.
    """
    from app.tasks.base import get_task_session

    async with get_task_session(
        statement_timeout_ms=ARCHIVE_STATEMENT_TIMEOUT_MS,
        lock_timeout_ms=ARCHIVE_LOCK_TIMEOUT_MS,
    ) as session:
        await verify_session_budget(session)
        yield session


# ── the operation wall ─────────────────────────────────────────────────────


class WallExpired(Exception):
    """The operation's reviewed wall ran out during ``phase``."""

    def __init__(self, phase: str):
        super().__init__(f"wall_expired:{phase}")
        self.phase = phase


class OperationWall:
    """One inclusive wall-clock budget for a whole attended operation.

    ``reserve`` is the tail kept for cancelling, closing and writing the
    receipt; work stops at :attr:`work_deadline`, everything stops at
    :attr:`deadline`. The receipt artifact is sealed by
    :attr:`artifact_deadline`, so the reserve's last quarter is always left
    for delivering the summary to the console: a slow disk cannot take the
    console's turn, and neither gets time past :attr:`deadline`.
    """

    def __init__(
        self,
        seconds: float,
        *,
        reserve: Optional[float] = None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        seconds = float(seconds)
        if not seconds > 0:
            raise ValueError("an operation wall must be positive")
        self.seconds = seconds
        self.monotonic = monotonic
        self.started = monotonic()
        self.deadline = self.started + seconds
        self.reserve = min(2.0, seconds * 0.1) if reserve is None else float(reserve)
        self.work_deadline = self.deadline - self.reserve
        self.artifact_deadline = self.deadline - self.reserve / 4

    def remaining(self, *, work: bool = True, end: Optional[float] = None) -> float:
        if end is None:
            end = self.work_deadline if work else self.deadline
        return end - self.monotonic()

    def elapsed(self) -> float:
        return self.monotonic() - self.started

    def check(self, phase: str, *, work: bool = True, end: Optional[float] = None) -> None:
        if self.remaining(work=work, end=end) <= 0:
            raise WallExpired(phase)

    @contextmanager
    def sync_phase(self, phase: str, *, work: bool = True, end: Optional[float] = None):
        """Run synchronous work inside the wall; interrupt it when the wall ends.

        ``SIGALRM`` raises :class:`WallExpired` between bytecodes, so a Python
        loop is interrupted; one long C call (a single huge ``json.loads``) is
        not, which is why every input it can see is size-capped first. Off the
        main thread (no signals) the wall is checked before and after.
        Never armed around an ``await``. ``end`` (a monotonic instant) ends
        the phase sooner than the work or hard deadline.
        """
        self.check(phase, work=work, end=end)
        armed = threading.current_thread() is threading.main_thread() and hasattr(
            signal, "setitimer"
        )
        previous = None
        if armed:

            def _expire(signum, frame):
                raise WallExpired(phase)

            previous = signal.signal(signal.SIGALRM, _expire)
            signal.setitimer(
                signal.ITIMER_REAL, max(self.remaining(work=work, end=end), 0.001)
            )
        try:
            yield
        finally:
            if armed:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
        self.check(phase, work=work, end=end)


async def run_within_wall(
    make: Callable[[], Awaitable[Any]],
    *,
    wall: OperationWall,
    progress: dict,
    cancel_until: Optional[float] = None,
) -> Any:
    """Await ``make()`` until the wall's work deadline; then cancel, bounded.

    On expiry the task is cancelled and given until ``cancel_until`` (a
    monotonic instant, default the wall's hard deadline) to unwind; whether it
    did is written to ``progress["cancel"]`` and :class:`WallExpired` is
    raised. ``progress`` is the operation's own running receipt, so whatever it
    had committed and recorded before the wall is still there to report.
    """
    task = asyncio.ensure_future(make())
    done, _ = await asyncio.wait({task}, timeout=max(wall.remaining(), 0.0))
    if task in done:
        return task.result()
    phase = str(progress.get("phase") or "unknown")
    progress["wall"] = {"expired_in_phase": phase, "seconds": wall.seconds}
    task.cancel()
    until = wall.deadline if cancel_until is None else cancel_until
    done, _ = await asyncio.wait({task}, timeout=max(until - wall.monotonic(), 0.0))
    if task in done:
        progress["cancel"] = "acknowledged"
        if not task.cancelled():
            task.exception()  # retrieved, so it is never logged as unobserved
    else:
        progress["cancel"] = "unacknowledged"
    raise WallExpired(phase)


def run_bounded_loop(
    coro: Awaitable[Any],
    *,
    straggler_grace: float = 0.5,
    close_by: Optional[float] = None,
    monotonic: Callable[[], float] = time.monotonic,
    shutdown: Optional[dict] = None,
) -> Any:
    """``asyncio.run`` without its unbounded waits on work that ignores cancel.

    ``asyncio.run`` gathers every leftover task, then awaits every open async
    generator's cleanup, with no timeout: one task, or one generator
    ``finally``, that never acknowledges its cancellation holds the process
    past its wall. Here both share ONE shutdown budget of ``straggler_grace``
    seconds that also ends at ``close_by`` (a ``monotonic`` instant: the wall's
    cancel-and-close end), so shutdown never spends the receipt's time.
    Whatever is still running then is abandoned to die with the process and
    is COUNTED in ``shutdown`` (the caller's receipt) rather than logged at
    garbage collection::

        {"clean": bool, "tasks_cancelled": n, "tasks_unacknowledged": n,
         "asyncgens": "closed" | "unacknowledged" | "not_reached",
         "abandoned": n, "seconds": s}

    Never ``asyncio.wait_for`` here: on timeout it cancels AND waits for that
    cancellation to be acknowledged, which is the unbounded wait again.
    """
    report = {} if shutdown is None else shutdown
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            _bounded_shutdown(loop, straggler_grace, close_by, monotonic, report)
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _bounded_shutdown(
    loop: asyncio.AbstractEventLoop,
    grace: float,
    close_by: Optional[float],
    monotonic: Callable[[], float],
    report: dict,
) -> None:
    started = monotonic()
    end = started + max(float(grace), 0.0)
    if close_by is not None:
        end = min(end, close_by)

    def left() -> float:
        return max(end - monotonic(), 0.0)

    report.update(
        clean=False, tasks_cancelled=0, tasks_unacknowledged=0, asyncgens="not_reached"
    )
    pending: list = []
    try:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pending:
            t.cancel()
        report["tasks_cancelled"] = len(pending)
        if pending:
            loop.run_until_complete(asyncio.wait(pending, timeout=left()))
        closing = loop.create_task(loop.shutdown_asyncgens())
        loop.run_until_complete(asyncio.wait({closing}, timeout=left()))
        report["asyncgens"] = "closed" if closing.done() else "unacknowledged"
    except Exception as e:  # noqa: BLE001 — shutdown is best effort, bounded, reported
        report["error"] = type(e).__name__
    finally:
        left_behind = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in left_behind:
            # Counted in the receipt instead; never a stray line at collection.
            t._log_destroy_pending = False
        report["tasks_unacknowledged"] = sum(1 for t in pending if not t.done())
        report["abandoned"] = len(left_behind)
        report["clean"] = (
            not left_behind and report["asyncgens"] == "closed" and "error" not in report
        )
        report["seconds"] = round(monotonic() - started, 3)


# ── HTTP: count before buffering ───────────────────────────────────────────


class ArchiveBudgetExceeded(Exception):
    """A byte budget stopped a response. The outcome stays held, never absent."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}{':' + detail if detail else ''}")
        self.reason = reason


class ArchiveResponseRefused(Exception):
    """A response this rail will not parse (e.g. an encoding it did not ask for)."""

    def __init__(self, reason: str):
        super().__init__(f"response_refused:{reason}")
        self.reason = reason


@dataclass
class ArchiveByteBudget:
    """Per-response and per-run caps on response bytes, and what was received."""

    response_cap: int
    total_cap: int
    received: int = 0
    responses: int = 0
    largest: int = 0

    def __post_init__(self):
        if self.response_cap <= 0 or self.total_cap <= 0:
            raise ValueError("byte caps must be positive")

    def as_report(self) -> dict:
        return {
            "response_cap": self.response_cap,
            "total_cap": self.total_cap,
            "received": self.received,
            "responses": self.responses,
            "largest_response": self.largest,
        }


async def _once(blob: bytes):
    yield blob


class BoundedArchiveService:
    """The planner's three archive reads, streamed under an :class:`ArchiveByteBudget`.

    Same routes, parameters and parsers as :class:`~app.services.kalshi_api.
    KalshiAPIService` (the parsers are shared functions, not copies), on the
    service's own client. Only this rail's requests change: each asks for
    ``Accept-Encoding: identity`` and is read as a stream. A non-2xx raises
    ``httpx.HTTPStatusError`` before any body is read, so a 429 keeps its
    ``Retry-After`` and is classified exactly as before.
    """

    def __init__(self, service: Any, budget: ArchiveByteBudget):
        self._service = service
        self._client = service.client
        self._base = service.BASE_URL
        self.budget = budget

    async def _get_text(self, path: str, params: Optional[dict] = None) -> str:
        budget = self.budget
        chunks: list[bytes] = []
        size = 0
        async with self._client.stream(
            "GET",
            f"{self._base}{path}",
            params=params,
            headers={"Accept-Encoding": "identity"},
        ) as response:
            response.raise_for_status()
            encoding = (response.headers.get("content-encoding") or "identity").strip()
            if encoding.lower() not in ("", "identity"):
                raise ArchiveResponseRefused(f"content_encoding:{encoding[:24]}")
            declared = (response.headers.get("content-length") or "").strip()
            if declared.isdigit() and int(declared) > budget.response_cap:
                raise ArchiveBudgetExceeded(
                    "response_bytes", f"declared={int(declared)}"
                )
            if declared.isdigit() and budget.received + int(declared) > budget.total_cap:
                raise ArchiveBudgetExceeded("total_bytes", f"declared={int(declared)}")
            budget.responses += 1
            if response.is_stream_consumed:
                # A transport that handed back an already-buffered body (an
                # in-process one; never httpx's network transport). The caps
                # still decide, but the bytes were buffered before we saw them.
                stream = _once(response.content)
            else:
                stream = response.aiter_raw()
            async for chunk in stream:
                size += len(chunk)
                budget.received += len(chunk)
                budget.largest = max(budget.largest, size)
                if size > budget.response_cap:
                    raise ArchiveBudgetExceeded("response_bytes", f"read>{budget.response_cap}")
                if budget.received > budget.total_cap:
                    raise ArchiveBudgetExceeded("total_bytes", f"read>{budget.total_cap}")
                chunks.append(chunk)
            charset = response.charset_encoding or "utf-8"
        return b"".join(chunks).decode(charset, errors="replace")

    async def get_historical_cutoff(self) -> dict:
        from app.services.kalshi_api import parse_historical_cutoff

        return parse_historical_cutoff(json.loads(await self._get_text("/historical/cutoff")))

    async def get_historical_markets(
        self,
        *,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ):
        from app.services.kalshi_api import (
            historical_markets_params,
            parse_historical_markets,
        )

        params = historical_markets_params(
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            limit=limit,
            cursor=cursor,
        )
        return parse_historical_markets(
            json.loads(await self._get_text("/historical/markets", params))
        )

    async def get_historical_market_candlesticks_payload(
        self, ticker: str, *, period_interval: int, start_ts: int, end_ts: int
    ):
        from app.services.kalshi_api import (
            KalshiArchiveCandlePayload,
            historical_candles_path,
        )

        raw_body = await self._get_text(
            historical_candles_path(ticker),
            {
                "period_interval": int(period_interval),
                "start_ts": int(start_ts),
                "end_ts": int(end_ts),
            },
        )
        return KalshiArchiveCandlePayload.from_text(
            requested_ticker=ticker,
            raw_body=raw_body,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    async def close(self):
        await self._service.close()


# ── output: console and artifact ───────────────────────────────────────────

#: Bytes kept back from the console cap for the one overflow notice.
OVERFLOW_NOTICE_RESERVE = 160


class _CappedStream:
    def __init__(self, cap: "ConsoleCap", real):
        self._cap, self._real = cap, real

    def write(self, s):
        return self._cap._write(self._real, s)

    def flush(self):
        self._cap._deliver(self._real.flush)

    def isatty(self):
        return False

    @property
    def encoding(self):
        return getattr(self._real, "encoding", "utf-8")


#: Set once any console on this process missed its wall (see :func:`exit_process`).
_console_lost = False
#: The installed :class:`ConsoleCap` (``sys.stdout`` is process-wide, so is this).
_installed: Optional["ConsoleCap"] = None


def _alarm_armed() -> bool:
    return hasattr(signal, "getitimer") and signal.getitimer(signal.ITIMER_REAL)[0] > 0


class ConsoleCap:
    """One shared byte cap over ``sys.stdout`` + ``sys.stderr``, delivered inside the wall.

    Installed BEFORE the app is imported, so logging handlers built during
    import hold the capped streams. Past the cap nothing more is written (no
    partial line passes as output); :attr:`overflowed` is set and the CLI exits
    non-zero after :meth:`restore` prints one fixed notice inside the reserve.

    After :meth:`bind`, every write reaches the real stream and is flushed
    inside the operation's wall: by its work deadline while the operation
    runs, by its hard deadline once :meth:`receipt` is called. Past the wall
    no write starts (no fresh allowance). A write or flush the wall interrupts,
    or one the sink refuses, makes the console :attr:`unavailable` (the
    reason): bytes the sink had not taken are dropped, nothing more is sent to
    it, and the CLI holds its exit at 3. The receipt artifact, written before
    the console, is the record; a lost console never means nothing was written.
    """

    def __init__(self, cap: int):
        if cap <= OVERFLOW_NOTICE_RESERVE:
            raise ValueError("console cap below the overflow notice reserve")
        self.cap = int(cap)
        self.used = 0
        self.dropped = 0
        self.overflowed = False
        self.unavailable: Optional[str] = None
        self.undelivered = 0
        self._wall: Optional[OperationWall] = None
        self._work = True
        self._real_out, self._real_err = sys.stdout, sys.stderr

    def install(self) -> "ConsoleCap":
        global _installed
        sys.stdout = _CappedStream(self, self._real_out)
        sys.stderr = _CappedStream(self, self._real_err)
        _installed = self
        return self

    def bind(self, wall: OperationWall) -> "ConsoleCap":
        """Deliver every later write inside ``wall`` (its work deadline, for now)."""
        self._wall, self._work = wall, True
        return self

    def receipt(self) -> None:
        """The receipt's turn: writes may use the wall's reserve, up to its hard deadline."""
        self._work = False

    def deliver_receipt(self, render: Callable[[], str]) -> bool:
        """Serialize the receipt and print it, both inside the wall's hard deadline.

        One phase covers ``render`` and the write, so a slow serialisation is
        cut by the same alarm as a slow sink. False = the console is unavailable.
        """
        self.receipt()

        def send():
            print(render())

        return self._deliver(send) and self.unavailable is None

    def _write(self, real, s) -> int:
        data = str(s)
        n = len(data.encode("utf-8", errors="replace"))
        if self.unavailable is not None:
            self.undelivered += n
            return len(data)
        if self.overflowed or self.used + n > self.cap - OVERFLOW_NOTICE_RESERVE:
            self.overflowed = True
            self.dropped += n
            return len(data)
        self.used += n

        def write_through():
            real.write(data)
            real.flush()

        if not self._deliver(write_through):
            self.undelivered += n
        return len(data)

    def _deliver(self, send: Callable[[], Any]) -> bool:
        """Run one write/flush to the real sink inside the bound wall. False = unavailable."""
        global _console_lost
        if self.unavailable is not None:
            return False
        wall = self._wall
        try:
            if wall is None or _alarm_armed():
                # Unbound (before the wall exists), or inside an enclosing
                # phase of the same wall whose alarm already ends sooner.
                send()
            else:
                with wall.sync_phase("console", work=self._work):
                    send()
            return True
        except WallExpired as e:
            self.unavailable = f"wall_expired:{e.phase}"
        except Exception as e:  # noqa: BLE001 — a refused sink is an unavailable console
            self.unavailable = f"sink_error:{type(e).__name__}"
        _console_lost = True
        return False

    def restore(self) -> None:
        global _installed
        sys.stdout, sys.stderr = self._real_out, self._real_err
        if _installed is self:
            _installed = None
        if self.overflowed:
            notice = f"OUTPUT_CAP_EXCEEDED: cap={self.cap} dropped_bytes={self.dropped}\n"
            real_err = self._real_err

            def send():
                real_err.write(notice[: OVERFLOW_NOTICE_RESERVE - 1])
                real_err.flush()

            self._deliver(send)


def bind_console(wall: OperationWall) -> None:
    """Deliver the installed console's later writes inside ``wall`` (see :meth:`ConsoleCap.bind`)."""
    if _installed is not None:
        _installed.bind(wall)


def deliver_receipt(wall: OperationWall, render: Callable[[], str]) -> bool:
    """Serialize and print the receipt inside ``wall``'s hard deadline. False = not delivered.

    Through the installed console when there is one (:meth:`ConsoleCap.deliver_receipt`).
    Without one (a direct call) the same phase bounds a plain flushed print.
    """
    if _installed is not None:
        if _installed._wall is None:
            _installed.bind(wall)
        return _installed.deliver_receipt(render)
    try:
        with wall.sync_phase("console", work=False):
            print(render(), flush=True)
        return True
    except WallExpired:
        return False


def exit_process(code: int) -> None:
    """End an attended CLI process with ``code``, never waiting on a lost console.

    A console that missed its wall can still hold undelivered bytes in the
    real stream's buffer, and the interpreter's exit flush would block on the
    same sink with no bound. Then, and only then, the process ends with
    ``os._exit``: the artifact was fsynced before the console was tried, the
    event loop is closed, and an exit flush of a lost console is owed nothing.
    Otherwise every byte was already flushed inside the wall and the exit is
    the ordinary ``sys.exit``.
    """
    if _console_lost:
        os._exit(code)
    sys.exit(code)


class ArtifactOverflow(Exception):
    def __init__(self, size: int, cap: int):
        super().__init__(f"artifact_overflow:{size}>{cap}")
        self.size, self.cap = size, cap


def write_bounded_artifact(path: str, payload: Any, cap: int) -> int:
    """Write ``payload`` as JSON to ``path`` whole, or not at all. Returns bytes.

    Refuses (nothing written) when the serialisation exceeds ``cap`` or
    ``path`` already exists: a sealed plan or receipt is never truncated and
    never overwritten. Interrupted (the wall's alarm), the temporary file is
    removed and ``path`` either holds the whole artifact or does not exist.
    """
    blob = json.dumps(payload, indent=2, default=str).encode("utf-8")
    if len(blob) > cap:
        raise ArtifactOverflow(len(blob), cap)
    if os.path.lexists(path):
        raise FileExistsError(path)
    directory = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(directory, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.link(tmp, path)  # atomic, and fails if ``path`` appeared meanwhile
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return len(blob)


class InputTooLarge(Exception):
    def __init__(self, size: int, cap: int):
        super().__init__(f"input_too_large:{size}>{cap}")
        self.size, self.cap = size, cap


def read_bounded_json(path: str, cap: int) -> Any:
    """Read at most ``cap`` bytes of JSON; refuse a larger file before decoding it."""
    with open(path, "rb") as fh:
        blob = fh.read(cap + 1)
    if len(blob) > cap:
        raise InputTooLarge(len(blob), cap)
    return json.loads(blob.decode("utf-8"))
