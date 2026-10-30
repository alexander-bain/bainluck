"""#10090 — a low-rate, always-on stack sampler for one process's event loop.

WHY. The Polymarket venue process runs at ~0.95 CPU in production while the
lab rig, at the same message rate, runs at 0.24-0.27. The gap sits in what the
lab stubs (the refresher's stamp/publish, the asyncpg wire, real Redis), so a
cut chosen from the lab profile could optimise the wrong 10%. This module says
where production's loop actually spends its time, from production.

HOW. The clock is the kernel: a one-shot ``ITIMER_PROF`` timer fires after
about ``interval_s`` of this PROCESS's CPU time (jittered ±50%, so samples
cannot alias with the 0.25 s flush cadence) and raises ``SIGPROF``. Python
runs the handler on the main thread, which is the loop thread, at its next
bytecode boundary. It hands the handler the frame that was running there, and
the handler re-arms the timer. Samples are therefore CPU-weighted: ~10 a second
at production's 0.95 CPU, none while the process sleeps.

Two thread-driven designs were measured and REJECTED. Both are biased by the
GIL to the loop's blocking calls:
- reading ``sys._current_frames()`` from a thread read 100% idle on a loop
  measured ~27-50% busy;
- a thread sending ``pthread_kill`` put 0 of 82 samples in the hot function.
The thread needs the GIL to act, and the loop gives the GIL up only at its
selector and sleep calls.

Each sample adds one count to:

- ``top_self``: the leaf Python function (C calls are charged to the Python
  function that made them, as a profile with builtins folded into callers);
- ``top_cum``: every distinct function on the stack, once per sample. Frames on
  >= 99% of non-selector samples (the loop's own scaffolding) are left off the line;
- ``top_line``: the leaf's current line;
- ``stages``: the OUTERMOST recognised stage on the stack (flush, receive,
  catalog, refresher), with ``+refresher`` when refresher code runs inside it.
  ``select`` means the loop thread was in the selector when the CPU was spent,
  so that CPU belongs to another thread or the kernel. Anything else is
  ``other``.

The walk continues across greenlet boundaries (SQLAlchemy's ``greenlet_spawn``)
into the parent greenlet's suspended frame, so a statement's compile/execute/row
Python is charged to the stage that issued it.

LIMITS. On 3.11 the handler runs at the next RESUME, backward jump or C-call
return: C-call CPU lands on its caller's line, but straight-line Python with no
calls lands on the next function entered. TLS decryption (PM sockets, Postgres,
Redis) and asyncpg's Cython row parsing run in loop transport callbacks, so they
always tag ``other`` (``asyncio/sslproto.py`` / ``selector_events.py`` leaves).

Every ``window_s`` a daemon thread (which needs no timing precision) closes the
window, builds ONE line of at most ``max_line`` bytes, and logs it:

    pm-cpu-sample n=… win=300s loop_cpu=… proc_cpu=… self_cpu=…% err=…
        stages=[…] top_self=[file:func:defline=pct,…] top_cum=[…]
        top_line=[file:func:line=pct,…]

Percentages are of all ``n`` samples. ``loop_cpu`` is the loop thread's CPU
over wall between its first and last sample. ``proc_cpu`` is the whole
process's. The gap between them is CPU spent on other threads; those samples
are charged to whatever the loop was doing. ``self_cpu`` is the sampler's own
cost (handler time on the loop, plus the thread), so every line carries it.

BOUNDS. The handler reads frame objects, bumps counters and re-arms one timer:
about 0.1 ms per sample on the rig's 40-60-frame stacks (measured: 0.28 s over
2,899 samples), so ~0.1% of a core at 10 Hz. It takes no application lock,
does no I/O, and never raises. The line is built on the thread from atomic ``dict()`` copies. The
handler is installed with SA_RESTART (``siginterrupt(False)``), and Python
retries a selector wait the signal interrupts (PEP 475). Once installed, the
handler stays installed; stopping disarms the timer and makes the handler
return at once. So a signal already in flight can never meet SIGPROF's default
action, which terminates the process. ``enabled()`` is read at start (off ⇒
nothing is installed) and again at every window boundary (off ⇒ disarmed, on
⇒ re-armed).
"""

from __future__ import annotations

import logging
import os
import random
import re
import signal
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL_S = 0.1
WINDOW_S = 300.0
MAX_LINE_BYTES = 8192
TOP_SELF = 25
TOP_CUM = 25
TOP_LINE = 15
#: Frames on at least this share of a window's non-selector samples are the loop's own
#: scaffolding (``run_forever``, ``_run_once``…) and carry no information.
SCAFFOLD_SHARE = 0.99
MAX_DEPTH = 256
#: The production timer counts this process's CPU and raises SIGPROF. A rig on
#: macOS passes ``signal.ITIMER_REAL`` (wall clock, SIGALRM): macOS notices an
#: expired CPU timer only at the thread's next kernel entry, which pulls every
#: sample onto the frame making the next syscall (measured: 33% on asyncio's
#: ``recv_into`` caller in the rig). Linux checks CPU timers on every scheduler
#: tick and delivers at that point; the Linux-only test proves it on CI.
SIGNAL_OF_TIMER = {
    signal.ITIMER_PROF: signal.SIGPROF,
    signal.ITIMER_REAL: signal.SIGALRM,
}

IDLE = "select"
OTHER = "other"
REFRESHER = "refresher"

#: Stage rules for the Polymarket venue process, matched on each frame's code:
#: ``(stage, path fragment, function names or None for any function there)``.
#: The outermost match on the stack names the sample's stage; a ``refresher``
#: frame below another stage adds ``+refresher``.
PM_STAGES = (
    ("flush", "tasks/polymarket_ws.py", frozenset({
        "flush_prices", "_flush_prices", "flush_withdrawals", "flush_observations",
        "flush_standalone", "_flush_standalone", "flush_props", "_flush_props",
        "join_flushes_then_drain",
    })),
    ("receive", "tasks/polymarket_ws.py", frozenset({
        "handle_price", "handle_trade", "handle_resolved",
    })),
    ("receive", "services/polymarket_ws.py", None),
    ("receive", "services/polymarket_ws_process.py", None),
    ("receive", "websockets/", None),
    ("catalog", "tasks/polymarket_ws.py", frozenset({"refresh_catalog"})),
    (REFRESHER, "tasks/live_blend_refresh.py", None),
    (REFRESHER, "utils/blend_preview.py", None),
)

_STDLIB = re.compile(r"/lib/python\d+\.\d+/")


def short_path(path: str) -> str:
    """A path short enough for a log line and still unambiguous."""
    for marker in ("/site-packages/", "/dist-packages/"):
        at = path.rfind(marker)
        if at >= 0:
            return path[at + len(marker):]
    at = path.rfind("/backend/")
    if at >= 0:
        return path[at + len("/backend/"):]
    if path.startswith("/app/app/"):  # Heroku: the slug root is backend/
        return path[len("/app/"):]
    match = None
    for match in _STDLIB.finditer(path):
        pass
    if match is not None:
        return path[match.end():]
    return path


def env_enabled(name: str = "PM_CPU_SAMPLER") -> bool:
    """Default ON: only an explicit ``0`` (or false/off/no) turns it off."""
    return os.getenv(name, "1").strip().lower() not in ("0", "false", "off", "no")


class _Window:
    """One window's counters. The handler writes them; the thread swaps in a
    fresh window and reads the old one through atomic ``dict()`` copies."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self.n = 0
        self.errors = 0
        self.self_counts: dict = {}
        self.cum_counts: dict = {}
        self.line_counts: dict = {}
        self.stage_counts: dict = {}
        self.handler_cpu = 0.0
        self.first: Optional[tuple] = None  # (wall, loop thread cpu)
        self.last: Optional[tuple] = None
        self.wall0 = clock()
        self.proc0 = time.process_time()


def _bump(counts: dict, key) -> None:
    counts[key] = counts.get(key, 0) + 1


class LoopCpuSampler:
    """See the module docstring. ``fold`` and ``line`` are public so a test (or
    a rig) can drive the counting and the line without the timer or thread."""

    def __init__(
        self,
        *,
        prefix: str = "pm-cpu-sample",
        stages=PM_STAGES,
        interval_s: float = SAMPLE_INTERVAL_S,
        window_s: float = WINDOW_S,
        max_line: int = MAX_LINE_BYTES,
        enabled: Callable[[], bool] = env_enabled,
        log: logging.Logger = logger,
        clock: Callable[[], float] = time.monotonic,
        timer: int = signal.ITIMER_PROF,
    ) -> None:
        self.prefix = prefix
        self.timer = timer
        self.signum = SIGNAL_OF_TIMER[timer]
        self.interval_s = interval_s
        self.window_s = window_s
        self.max_line = max_line
        self._enabled = enabled
        self._log = log
        self._clock = clock
        self._rules = tuple(stages)
        self._stage_of: dict = {}
        self._random = random.Random()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active = False
        self.thread_errors = 0
        self._window = _Window(clock)

    # ── the handler side (runs on the loop thread) ──────────────────────────
    def _classify(self, code) -> tuple:
        """``(stage or None, is_selector_leaf)`` for one code object, cached."""
        cached = self._stage_of.get(code)
        if cached is not None:
            return cached
        filename, name = code.co_filename, code.co_name
        stage = None
        for rule_stage, fragment, names in self._rules:
            if fragment in filename and (names is None or name in names):
                stage = rule_stage
                break
        idle = name == "select" and filename.endswith("selectors.py")
        cached = self._stage_of[code] = (stage, idle)
        return cached

    def fold(self, frame, window: Optional[_Window] = None) -> None:
        """Count one sample of ``frame``'s stack. Never raises."""
        w = self._window if window is None else window
        try:
            if frame is None:
                return
            leaf = frame.f_code
            w.n += 1
            if self._classify(leaf)[1]:
                _bump(w.stage_counts, IDLE)
                return
            _bump(w.self_counts, leaf)
            _bump(w.line_counts, (leaf, frame.f_lineno))
            seen = set()
            outer = None
            refresher = False
            depth = 0
            # SQLAlchemy's async layer runs each statement inside greenlet_spawn,
            # and a greenlet keeps its own frame chain: the outermost frame in it
            # has f_back None. Continue from the parent greenlet's suspended frame,
            # or every statement's Python reads `other`. sys.modules, so no import
            # runs inside the handler.
            greenlet_mod = sys.modules.get("greenlet")
            g = greenlet_mod.getcurrent() if greenlet_mod is not None else None
            while depth < MAX_DEPTH:
                if frame is None:
                    g = g.parent if g is not None else None
                    if g is None:
                        break
                    frame = g.gr_frame
                    continue
                code = frame.f_code
                if code not in seen:
                    seen.add(code)
                    stage = self._classify(code)[0]
                    if stage is not None:
                        outer = stage  # walking outward: the last match is outermost
                        refresher = refresher or stage == REFRESHER
                frame = frame.f_back
                depth += 1
            for code in seen:
                _bump(w.cum_counts, code)
            if outer is None:
                outer = OTHER
            elif refresher and outer != REFRESHER:
                outer = f"{outer}+{REFRESHER}"
            _bump(w.stage_counts, outer)
        except Exception:
            w.errors += 1

    def _arm(self) -> None:
        signal.setitimer(self.timer, self.interval_s * (0.5 + self._random.random()))

    def _on_signal(self, signum, frame) -> None:
        if not self._active:
            return
        try:
            cpu0 = time.thread_time()
            now = self._clock()
            w = self._window
            self.fold(frame, w)
            if w.first is None:
                w.first = (now, cpu0)
            w.last = (now, cpu0)
            w.handler_cpu += time.thread_time() - cpu0
        except Exception:
            pass
        try:
            if self._active:
                self._arm()
        except Exception:
            return

    # ── the line (runs on the thread) ───────────────────────────────────────
    @staticmethod
    def _name(code, lineno=None) -> str:
        line = code.co_firstlineno if lineno is None else lineno
        return f"{short_path(code.co_filename)}:{code.co_name}:{line}"

    def line(self, thread_cpu: Optional[float] = None) -> str:
        """Close the current window and return its line (<= ``max_line`` bytes)."""
        w, self._window = self._window, _Window(self._clock)
        # dict() of a plain dict copies in C under the GIL: a handler that
        # still holds the old window can at worst add a count nobody reads.
        self_counts, cum_counts = dict(w.self_counts), dict(w.cum_counts)
        line_counts, stage_counts = dict(w.line_counts), dict(w.stage_counts)
        n = w.n
        wall = max(1e-9, self._clock() - w.wall0)
        proc_cpu = (time.process_time() - w.proc0) / wall
        if w.first is not None and w.last is not None and w.last[0] > w.first[0]:
            loop_cpu = f"{(w.last[1] - w.first[1]) / (w.last[0] - w.first[0]):.2f}"
        else:
            loop_cpu = "-"
        self_cpu = w.handler_cpu + (thread_cpu or 0.0)

        def pct(count) -> str:
            return f"{100.0 * count / n:.1f}" if n else "0.0"

        def top(counts, k):
            return sorted(counts.items(), key=lambda kv: -kv[1])[:k]

        scaffold = SCAFFOLD_SHARE * (n - stage_counts.get(IDLE, 0))  # selector samples carry no stack
        lists = {
            "stages": [f"{stage}={pct(c)}" for stage, c in top(stage_counts, 16)],
            "top_self": [f"{self._name(code)}={pct(c)}" for code, c in top(self_counts, TOP_SELF)],
            "top_cum": [
                f"{self._name(code)}={pct(c)}"
                for code, c in top(cum_counts, TOP_CUM + 16) if c < scaffold
            ][:TOP_CUM],
            "top_line": [
                f"{self._name(code, lineno)}={pct(c)}"
                for (code, lineno), c in top(line_counts, TOP_LINE)
            ],
        }
        head = (
            f"{self.prefix} n={n} win={wall:.0f}s loop_cpu={loop_cpu} "
            f"proc_cpu={proc_cpu:.2f} self_cpu={100.0 * self_cpu / wall:.3f}% "
            f"err={w.errors + self.thread_errors}"
        )
        self.thread_errors = 0

        def render() -> str:
            return head + "".join(f" {key}=[{','.join(items)}]" for key, items in lists.items())

        text = render()
        while len(text.encode("utf-8", "replace")) > self.max_line:
            longest = max(("top_line", "top_cum", "top_self"), key=lambda k: len(lists[k]))
            if not lists[longest]:
                return head[: self.max_line]
            lists[longest].pop()
            text = render()
        return text

    # ── start / stop ────────────────────────────────────────────────────────
    def start(self, *, thread: bool = True) -> Optional["LoopCpuSampler"]:
        """Install the handler, arm the timer, start the line thread. Call it
        ON the loop thread, which must be the main thread (Python runs signal
        handlers only there). Returns None, having changed nothing, when
        disabled, off the main thread, or when SIGPROF or ITIMER_PROF is
        already in use (a stopped sampler's inert handler is not "in use"). ``thread=False`` (tests, rigs) leaves line-building to
        the caller."""
        if not self._safe_enabled():
            return None
        if threading.current_thread() is not threading.main_thread():
            self._log.warning("%s: not on the main thread; not started", self.prefix)
            return None
        previous = signal.getsignal(self.signum)
        owner = getattr(previous, "__self__", None)
        inert = isinstance(owner, LoopCpuSampler) and not owner._active
        if (
            not (inert or previous in (signal.SIG_DFL, signal.SIG_IGN, None))
            or signal.getitimer(self.timer) != (0.0, 0.0)
        ):
            self._log.warning("%s: its signal or timer is already in use; not started", self.prefix)
            return None
        self._window = _Window(self._clock)
        self._active = True
        signal.signal(self.signum, self._on_signal)
        signal.siginterrupt(self.signum, False)
        self._arm()
        if thread:
            worker = threading.Thread(target=self._run, name=f"{self.prefix}-line", daemon=True)
            self._thread = worker
            worker.start()
        return self

    def stop(self, join_timeout: Optional[float] = None) -> None:
        """Disarm and end the line thread; the handler stays installed and
        returns at once. Never joins unless asked (the loop must not wait)."""
        self._stop.set()
        self._active = False
        try:
            signal.setitimer(self.timer, 0)
        except Exception:
            pass
        worker = self._thread
        if join_timeout is not None and worker is not None:
            worker.join(join_timeout)

    def _safe_enabled(self) -> bool:
        try:
            return bool(self._enabled())
        except Exception:
            return False

    def _run(self) -> None:
        try:
            thread_cpu0 = time.thread_time()
            while not self._stop.wait(self.window_s):
                try:
                    if self._active:
                        text = self.line(time.thread_time() - thread_cpu0)
                        self._log.info("%s", text)
                    else:
                        self._window = _Window(self._clock)
                except Exception:
                    self.thread_errors += 1
                try:
                    enabled = self._safe_enabled()
                    if enabled and not self._active and not self._stop.is_set():
                        self._active = True
                        self._arm()
                    elif not enabled and self._active:
                        self._active = False
                        signal.setitimer(self.timer, 0)
                except Exception:
                    self.thread_errors += 1
                thread_cpu0 = time.thread_time()
        except Exception:
            # Never take the process down; the lines simply stop.
            return
