"""Uvicorn multiprocess supervisor with staggered clock-based worker recycling (#13532).

Why `--limit-max-requests 5000` was not enough on its own:
Production web traffic averages ~120-170 requests per 10 minutes (~15 req/min across
both `WEB_CONCURRENCY=2` workers). At ~7.5 req/min per worker, reaching 5,000 requests
takes ~11 hours while `web.1` memory climbs from ~516-603 MB to ~988-1,005 MB in 35-55
minutes.

This supervisor wraps ``uvicorn.supervisors.multiprocess.Multiprocess`` cleanly, keeping
every existing Uvicorn CLI flag (``--limit-max-requests``, jitter, graceful shutdown,
``$WEB_CONCURRENCY``) intact and adding a staggered wall-clock max age per worker:

- With 2 workers and default ``WEB_WORKER_MAX_AGE_SECONDS=1800`` (30 min), worker 0 is
  first recycled at ~+15 min and worker 1 at ~+30 min, then every 30 min staggered 15 min
  apart.
- At most one worker recycles at a time, only when at least one sibling responds healthy,
  and only after ``WEB_WORKER_MIN_STAGGER_SECONDS`` (default 300s) has elapsed since the
  previous recycle or unexpected respawn.
- Old workers are terminated and drained cleanly only *after* their replacement answers
  ready, so a failed replacement startup never exits the parent or leaves zero workers
  serving, and open streams never stall capacity in a single-worker window.
- Single-worker mode (``WEB_CONCURRENCY=1``) runs Uvicorn directly without self-inflicted
  clock restarts.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import multiprocessing.process
import os
import pickle
import sys
import time
from collections.abc import Callable, Sequence
from socket import socket
from typing import Any

import uvicorn
import uvicorn.server
from uvicorn.config import LOGGING_CONFIG, Config
from uvicorn.supervisors.multiprocess import Multiprocess, Process

logger = logging.getLogger("uvicorn.error")

_STARTUP_FAILURE = getattr(uvicorn, "STARTUP_FAILURE", 3)
_UVICORN_PROCESS = Process
_PROCESS_HAS_IS_READY = hasattr(Process, "is_ready")
_MULTIPROCESS_TAKES_TARGET = "target" in inspect.signature(Multiprocess.__init__).parameters
_PROCESS_TAKES_TARGET = "target" in inspect.signature(Process.__init__).parameters

DEFAULT_WORKER_MAX_AGE_SECONDS = 1800.0
DEFAULT_WORKER_MIN_STAGGER_SECONDS = 300.0
DEFAULT_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 25.0
DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0


class _CompatReadyProcess(Process):
    """Add Uvicorn 0.54+ ``is_ready`` / ``exitcode`` semantics on older Uvicorn (e.g. 0.48.0)."""

    def _close_pipes(self) -> None:
        for conn in (getattr(self, "parent_conn", None), getattr(self, "child_conn", None)):
            if conn is None:
                continue
            try:
                conn.close()
            except OSError:
                pass

    def _healthcheck(self, timeout: float) -> bool | None:
        try:
            self.parent_conn.send(b"ping")
            if self.parent_conn.poll(timeout):
                return bool(self.parent_conn.recv())
            return None
        except (OSError, EOFError, pickle.UnpicklingError):
            return None

    def ping(self, timeout: float = 5) -> bool:
        return self._healthcheck(timeout) is not None

    def is_ready(self, timeout: float = 5) -> bool:
        return self._healthcheck(timeout) is True

    def pong(self) -> None:
        self.child_conn.recv()
        bound_server = getattr(self.real_target, "__self__", None)
        started = getattr(bound_server, "started", None)
        self.child_conn.send(True if started is None else bool(started))

    def kill(self) -> None:
        super().kill()
        self._close_pipes()

    @property
    def exitcode(self) -> int | None:
        return self.process.exitcode


def _env_nonneg_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = float(raw.strip())
    except ValueError:
        logger.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default
    if val < 0:
        return 0.0
    return val


def effective_min_stagger(max_age_s: float, workers: int, configured_min_s: float) -> float:
    """Bound minimum inter-recycle stagger so slots remain strictly separable."""
    if max_age_s <= 0 or workers <= 1:
        return 0.0
    slot_step = max_age_s / float(workers)
    return max(0.0, min(configured_min_s, slot_step * 0.5))


class StaggeredClockMultiprocess(Multiprocess):
    """Uvicorn ``Multiprocess`` supervisor that recycles workers one at a time on a staggered clock."""

    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
        *,
        max_age_seconds: float | None = None,
        min_stagger_seconds: float | None = None,
        shutdown_join_timeout_seconds: float | None = None,
        startup_timeout_seconds: float | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.target = target
        if _MULTIPROCESS_TAKES_TARGET:
            super().__init__(config, target, sockets)  # type: ignore[call-arg]
        else:
            super().__init__(config, sockets)  # type: ignore[call-arg]
        self._monotonic = monotonic_fn
        self.max_age_seconds = (
            _env_nonneg_float("WEB_WORKER_MAX_AGE_SECONDS", DEFAULT_WORKER_MAX_AGE_SECONDS)
            if max_age_seconds is None
            else max(0.0, float(max_age_seconds))
        )
        raw_min_stagger = (
            _env_nonneg_float("WEB_WORKER_MIN_STAGGER_SECONDS", DEFAULT_WORKER_MIN_STAGGER_SECONDS)
            if min_stagger_seconds is None
            else max(0.0, float(min_stagger_seconds))
        )
        self.min_stagger_seconds = effective_min_stagger(
            self.max_age_seconds, max(1, int(self.processes_num)), raw_min_stagger
        )
        raw_join_timeout = (
            _env_nonneg_float(
                "WEB_WORKER_SHUTDOWN_JOIN_TIMEOUT_SECONDS",
                max(
                    DEFAULT_SHUTDOWN_JOIN_TIMEOUT_SECONDS,
                    float(getattr(config, "timeout_graceful_shutdown", None) or 15) + 10.0,
                ),
            )
            if shutdown_join_timeout_seconds is None
            else max(1.0, float(shutdown_join_timeout_seconds))
        )
        self.shutdown_join_timeout_seconds = raw_join_timeout
        raw_startup_timeout = (
            _env_nonneg_float("WEB_WORKER_STARTUP_TIMEOUT_SECONDS", DEFAULT_STARTUP_TIMEOUT_SECONDS)
            if startup_timeout_seconds is None
            else float(startup_timeout_seconds)
        )
        self.startup_timeout_seconds = max(1.0, raw_startup_timeout)
        self._started_at: list[float] = []
        self._next_recycle_at: list[float | None] = []
        self._last_event_at: float | None = None
        self._retiring_processes: list[Process] = []

    def _spawn_process(self) -> Process:
        if not _PROCESS_HAS_IS_READY and Process is _UVICORN_PROCESS:
            process: Process = _CompatReadyProcess(self.config, self.target, self.sockets)  # type: ignore[call-arg]
        elif _PROCESS_TAKES_TARGET:
            process = Process(self.config, self.target, self.sockets)  # type: ignore[call-arg]
        else:
            process = Process(self.config, self.sockets)  # type: ignore[call-arg]
        process.start()
        return process

    def _kill_and_join_worker(self, process: Process, join_timeout: float = 5.0) -> None:
        process.kill()
        inner = getattr(process, "process", None)
        if inner is not None and hasattr(inner, "join"):
            inner.join(timeout=join_timeout)
        else:
            process.join()

    def _wait_until_worker_ready(self, process: Process) -> bool:
        if hasattr(process, "is_ready"):
            deadline = time.monotonic() + self.startup_timeout_seconds
            while time.monotonic() < deadline:
                self.handle_signals()
                if self.should_exit.is_set():
                    return False
                inner = getattr(process, "process", None)
                if isinstance(inner, multiprocessing.process.BaseProcess) and not inner.is_alive():
                    return False
                if getattr(process, "exitcode", None) is not None:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if process.is_ready(timeout=min(1.0, remaining)):
                    return True
                sleep_for = min(0.1, max(0.0, deadline - time.monotonic()))
                if sleep_for > 0:
                    time.sleep(sleep_for)
            return False
        if hasattr(process, "wait_until_ready"):
            return bool(process.wait_until_ready(self.startup_timeout_seconds, self.should_exit))
        return bool(process.is_alive(timeout=self.config.timeout_worker_healthcheck))

    def _next_non_overlapping_slot(self, idx: int, now: float) -> float | None:
        if self.max_age_seconds <= 0 or len(self.processes) <= 1:
            return None
        candidate = now + self.max_age_seconds
        min_gap = self.min_stagger_seconds
        if min_gap <= 0:
            return candidate
        for _ in range(len(self.processes) + 2):
            conflict = False
            for j, other in enumerate(self._next_recycle_at):
                if j == idx or other is None:
                    continue
                if abs(other - candidate) < min_gap:
                    candidate = other + min_gap
                    conflict = True
            if not conflict:
                break
        return candidate

    def _push_siblings_past_stagger(self, active_idx: int, now: float) -> None:
        if self.max_age_seconds <= 0 or self.min_stagger_seconds <= 0:
            return
        floor = now + self.min_stagger_seconds
        for j, sched in enumerate(self._next_recycle_at):
            if j == active_idx or sched is None:
                continue
            if sched < floor:
                self._next_recycle_at[j] = floor

    def _terminate_and_join_worker(self, process: Process) -> None:
        pid = process.pid
        process.terminate()
        inner = getattr(process, "process", None)
        if inner is not None and hasattr(inner, "join"):
            if isinstance(inner, multiprocessing.process.BaseProcess):
                deadline = time.monotonic() + self.shutdown_join_timeout_seconds
                while inner.is_alive() and time.monotonic() < deadline:
                    self.handle_signals()
                    if self.should_exit.is_set():
                        if inner.is_alive():
                            self._retiring_processes.append(process)
                        return
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    inner.join(timeout=min(0.25, remaining))
                still_alive = inner.is_alive()
            else:
                inner.join(timeout=self.shutdown_join_timeout_seconds)
                still_alive = bool(inner.is_alive()) if hasattr(inner, "is_alive") else False
        else:
            process.join()
            still_alive = False
        if still_alive and not self.should_exit.is_set():
            logger.warning(
                "Staggered clock recycle force-killing worker [%s] after %.1fs graceful wait",
                pid,
                self.shutdown_join_timeout_seconds,
            )
            self._kill_and_join_worker(process, join_timeout=5.0)

    def join_all(self) -> None:
        super().join_all()
        for process in self._retiring_processes:
            process.join()
        self._retiring_processes.clear()

    def init_processes(self) -> None:
        self.processes = [self._spawn_process() for _ in range(self.processes_num)]
        now = self._monotonic()
        n = len(self.processes)
        self._started_at = [now for _ in range(n)]
        if self.max_age_seconds > 0 and n > 1:
            slot_step = self.max_age_seconds / float(n)
            self._next_recycle_at = [now + (idx + 1) * slot_step for idx in range(n)]
            logger.info(
                "Staggered clock recycle enabled: workers=%d max_age=%.0fs stagger=%.0fs min_gap=%.0fs",
                n,
                self.max_age_seconds,
                slot_step,
                self.min_stagger_seconds,
            )
        else:
            self._next_recycle_at = [None for _ in range(n)]

    def _sync_schedule_lengths(self, now: float) -> None:
        while len(self._started_at) < len(self.processes):
            self._started_at.append(now)
        while len(self._next_recycle_at) < len(self.processes):
            idx = len(self._next_recycle_at)
            self._next_recycle_at.append(self._next_non_overlapping_slot(idx, now))
        if len(self._started_at) > len(self.processes):
            del self._started_at[len(self.processes) :]
        if len(self._next_recycle_at) > len(self.processes):
            del self._next_recycle_at[len(self.processes) :]

    def keep_subprocess_alive(self) -> None:
        if self.should_exit.is_set():
            return

        now = self._monotonic()
        self._sync_schedule_lengths(now)
        hc_timeout = self.config.timeout_worker_healthcheck

        for idx, process in enumerate(self.processes):
            if process.is_alive(timeout=hc_timeout):
                continue

            process.kill()
            process.join()

            if getattr(process, "exitcode", None) == _STARTUP_FAILURE:
                logger.error("Child process [%s] failed to start, stopping the parent process.", process.pid)
                self.should_exit.set()
                return

            if self.should_exit.is_set():
                return  # pragma: full coverage

            logger.info("Child process [%s] died", process.pid)
            replacement = self._spawn_process()
            self.processes[idx] = replacement
            respawn_now = self._monotonic()
            self._started_at[idx] = respawn_now
            self._last_event_at = respawn_now
            self._next_recycle_at[idx] = self._next_non_overlapping_slot(idx, respawn_now)
            self._push_siblings_past_stagger(idx, respawn_now)

        self.recycle_aged_worker_if_due()

    def recycle_aged_worker_if_due(self) -> int | None:
        """Recycle at most one due worker if cooldown and healthy-sibling guards pass.

        Returns the recycled worker slot index, or ``None`` if no recycle ran.
        """
        if self.should_exit.is_set() or self.max_age_seconds <= 0 or len(self.processes) <= 1:
            return None

        now = self._monotonic()
        self._sync_schedule_lengths(now)
        if (
            self._last_event_at is not None
            and self.min_stagger_seconds > 0
            and (now - self._last_event_at) < self.min_stagger_seconds
        ):
            return None

        due_indices = [
            idx
            for idx, sched in enumerate(self._next_recycle_at)
            if sched is not None and now >= sched
        ]
        if not due_indices:
            return None

        # Pick the single oldest due worker.
        target_idx = min(due_indices, key=lambda idx: (self._next_recycle_at[idx] or 0.0, self._started_at[idx], idx))

        # Never leave zero live workers behind.
        hc_timeout = self.config.timeout_worker_healthcheck
        sibling_alive = any(
            j != target_idx and proc.is_alive(timeout=hc_timeout)
            for j, proc in enumerate(self.processes)
        )
        if not sibling_alive:
            return None

        old_proc = self.processes[target_idx]
        old_pid = old_proc.pid
        age_s = max(0.0, now - self._started_at[target_idx])
        logger.info(
            "Staggered clock recycle starting: slot=%d old_pid=%s age=%.0fs",
            target_idx,
            old_pid,
            age_s,
        )
        # Start the replacement first and wait until it answers ready before
        # adding it to self.processes or retiring old_proc. A failed startup
        # must never stop the parent or leave fewer workers serving.
        new_proc = self._spawn_process()
        if not self._wait_until_worker_ready(new_proc):
            exitcode = getattr(new_proc, "exitcode", None)
            new_pid = new_proc.pid
            self._kill_and_join_worker(new_proc)
            if self.should_exit.is_set():
                return None
            fail_now = self._monotonic()
            retry_delay = self.min_stagger_seconds if self.min_stagger_seconds > 0 else 1.0
            self._last_event_at = fail_now
            self._next_recycle_at[target_idx] = fail_now + retry_delay
            self._push_siblings_past_stagger(target_idx, fail_now)
            logger.error(
                "Staggered clock recycle aborted: slot=%d replacement_pid=%s failed to become ready "
                "(exitcode=%s); keeping old_pid=%s and retrying in %.0fs",
                target_idx,
                new_pid,
                exitcode,
                old_pid,
                retry_delay,
            )
            return None

        self.processes[target_idx] = new_proc
        self._terminate_and_join_worker(old_proc)

        if self.should_exit.is_set():
            return None

        done_now = self._monotonic()
        self._started_at[target_idx] = done_now
        self._last_event_at = done_now
        self._next_recycle_at[target_idx] = self._next_non_overlapping_slot(target_idx, done_now)
        self._push_siblings_past_stagger(target_idx, done_now)
        logger.info(
            "Staggered clock recycle complete: slot=%d old_pid=%s new_pid=%s next_in=%.0fs",
            target_idx,
            old_pid,
            new_proc.pid,
            max(0.0, (self._next_recycle_at[target_idx] or done_now) - done_now),
        )
        return target_idx


def build_uvicorn_config(argv: Sequence[str]) -> Config:
    """Parse standard uvicorn CLI flags into a ``Config`` instance."""
    uvicorn_main = importlib.import_module("uvicorn.main")
    ctx = uvicorn_main.main.make_context("uvicorn", list(argv))
    params = dict(ctx.params)
    app = params.pop("app")

    app_dir = params.pop("app_dir", None)
    if app_dir:
        sys.path.insert(0, str(app_dir))

    if params.get("log_config") is None:
        params["log_config"] = LOGGING_CONFIG
    if "reload_dirs" in params and not params["reload_dirs"]:
        params["reload_dirs"] = None
    if "reload_includes" in params and not params["reload_includes"]:
        params["reload_includes"] = None
    if "reload_excludes" in params and not params["reload_excludes"]:
        params["reload_excludes"] = None
    if "headers" in params and params["headers"] is not None:
        params["headers"] = [
            h.split(":", 1) if isinstance(h, str) else list(h)
            for h in params["headers"]
        ]

    valid_keys = set(inspect.signature(Config.__init__).parameters) - {"self", "app"}
    filtered: dict[str, Any] = {k: v for k, v in params.items() if k in valid_keys}
    return Config(app, **filtered)


def run_cli(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint compatible with Procfile ``python3 -m app.web_supervisor ...``."""
    args = list(sys.argv[1:] if argv is None else argv)
    config = build_uvicorn_config(args)
    if config.workers > 1:
        if not isinstance(config.app, str):
            logger.warning("You must pass the application as an import string to enable 'workers'.")
            sys.exit(1)
    else:
        # Match Uvicorn 0.54.0: multiprocess workers load config.app inside each
        # spawned child; single-worker mode loads it here before Server.run().
        config.load_app()
    server = uvicorn.server.Server(config=config)

    try:
        if config.workers > 1:
            sock = config.bind_socket()
            StaggeredClockMultiprocess(config, target=server.run, sockets=[sock]).run()
        else:
            server.run()
    except KeyboardInterrupt:
        # Clean Ctrl+C shutdown matches uvicorn.run().
        pass
    finally:
        if config.uds and os.path.exists(config.uds):
            os.remove(config.uds)

    if not server.started and not config.should_reload and config.workers == 1:
        sys.exit(_STARTUP_FAILURE)


if __name__ == "__main__":
    run_cli()
