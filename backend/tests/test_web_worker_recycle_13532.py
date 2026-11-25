"""Regression guards for #13532 web dyno memory caps and staggered clock recycling.

Why `Procfile`'s `web:` command wraps Uvicorn in `app.web_supervisor` while keeping
all three Uvicorn recycle flags:
- Production web traffic averages ~12-17 req/min across both `WEB_CONCURRENCY=2`
  workers, so `--limit-max-requests 5000` takes ~10+ hours to fire while memory reaches
  ~988-1,005 MB against `1,024 MB` within 35-55 minutes.
- `StaggeredClockMultiprocess` recycles workers strictly one at a time on a staggered
  wall-clock age (`WEB_WORKER_MAX_AGE_SECONDS=1800` by default -> +15m / +30m, then every
  30m staggered 15m apart), enforcing a healthy sibling check and a minimum inter-recycle
  cool-down (`WEB_WORKER_MIN_STAGGER_SECONDS`) so both workers never restart together.
- `--timeout-graceful-shutdown` (`15`s) and supervisor join timeout (`25`s -> `.kill()`
  fallback) bound SSE stream drains (`MAX_CONNECTION_S = 900`s) while the already-ready
  replacement worker takes over traffic cleanly.
- `--limit-max-requests 5000 --limit-max-requests-jitter 1000` stays in place as a
  request-count backstop under traffic bursts.
- Three in-process L1 caps stay tightened (`10`, `10`, `48`).
"""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import uvicorn.config
import uvicorn.server

from app import web_supervisor
from app.routes import event_stream, events as events_route, market_stream
from app.utils import request_cache as rc

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROCFILE_PATH = BACKEND_DIR / "Procfile"


def _web_command_tokens() -> list[str]:
    for raw_line in PROCFILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, command = line.split(":", 1)
        if name.strip() == "web":
            tokens = shlex.split(command.strip())
            return ["8000" if tok == "$PORT" else tok for tok in tokens]
    raise AssertionError("No `web:` entry found in backend/Procfile")


def _uvicorn_args_from_procfile() -> list[str]:
    tokens = _web_command_tokens()
    assert tokens[:3] == [
        "python3",
        "-m",
        "app.web_supervisor",
    ], f"Unexpected web entrypoint: {tokens!r}"
    return tokens[3:]


def _supervisor_config(*, workers: int = 2) -> uvicorn.config.Config:
    with patch.dict(os.environ, {"WEB_CONCURRENCY": str(workers)}):
        return web_supervisor.build_uvicorn_config(_uvicorn_args_from_procfile())


class _FakeClock:
    def __init__(self, initial: float = 1_000.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class _FakeInnerProcess:
    def __init__(self, *, alive_after_join: bool = False) -> None:
        self.alive_after_join = alive_after_join
        self.join_timeouts: list[float | None] = []

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive_after_join


class _FakeWorkerProcess:
    _next_pid = 2000

    def __init__(
        self,
        *,
        alive: bool = True,
        ready: bool = True,
        exitcode: int | None = None,
        hung_on_terminate: bool = False,
        timeline: list[str] | None = None,
    ) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.alive = alive
        self.ready = ready
        self.exitcode = exitcode
        self.timeline = timeline if timeline is not None else []
        self.started = False
        self.terminated = False
        self.killed = False
        self.process = _FakeInnerProcess(alive_after_join=hung_on_terminate)

    def start(self) -> None:
        self.started = True
        if not self.ready and self.exitcode is not None:
            self.alive = False
        self.timeline.append(f"start:{self.pid}")

    def is_alive(self, timeout: float = 5) -> bool:
        return self.alive

    def is_ready(self, timeout: float = 5) -> bool:
        return self.alive and self.ready

    def terminate(self) -> None:
        self.terminated = True
        self.timeline.append(f"terminate:{self.pid}")
        if not self.process.alive_after_join:
            self.alive = False

    def kill(self) -> None:
        self.killed = True
        self.alive = False
        self.process.alive_after_join = False
        self.timeline.append(f"kill:{self.pid}")

    def join(self) -> None:
        self.timeline.append(f"join:{self.pid}")


class TestWebWorkerRecycleProcfile:
    def test_web_command_binds_supervisor_and_all_three_recycle_flags(self) -> None:
        cfg = _supervisor_config(workers=2)

        assert cfg.app == "app.main:app"
        assert cfg.workers == 2
        assert isinstance(cfg.limit_max_requests, int) and 2000 <= cfg.limit_max_requests <= 10000
        assert (
            isinstance(cfg.limit_max_requests_jitter, int)
            and 0 < cfg.limit_max_requests_jitter < cfg.limit_max_requests
        )
        assert (
            isinstance(cfg.timeout_graceful_shutdown, int)
            and 5 <= cfg.timeout_graceful_shutdown <= 30
        )

        # SSE streams can run up to 900s; shutdown timeout must stay far tighter.
        assert cfg.timeout_graceful_shutdown < event_stream.MAX_CONNECTION_S
        assert cfg.timeout_graceful_shutdown < market_stream.MAX_CONNECTION_S

    def test_web_command_does_not_hardcode_workers(self) -> None:
        """Heroku's `WEB_CONCURRENCY` controls worker count without editing Procfile."""
        tokens = _web_command_tokens()
        assert not any(
            tok == "--workers" or tok.startswith("--workers=") or tok == "-w"
            for tok in tokens
        )

    def test_uvicorn_config_honors_flags_with_web_concurrency(self) -> None:
        cfg = _supervisor_config(workers=2)
        assert cfg.workers == 2
        assert cfg.limit_max_requests == 5000
        assert cfg.limit_max_requests_jitter == 1000
        assert cfg.timeout_graceful_shutdown == 15

    async def test_uvicorn_server_on_tick_triggers_exit_with_jitter_band(self) -> None:
        cfg = _supervisor_config(workers=1)
        server = uvicorn.server.Server(cfg)
        threshold = server.limit_max_requests
        assert threshold is not None and 5000 <= threshold <= 6000

        server.server_state.total_requests = threshold - 1
        assert await server.on_tick(1) is False

        server.server_state.total_requests = threshold
        assert await server.on_tick(2) is True

    def test_run_cli_selects_staggered_supervisor_only_for_multiprocess(self) -> None:
        fake_sock = object()
        calls: list[str] = []

        class _StubServer:
            def __init__(self, config):
                self.started = True
                self.config = config

            def run(self, sockets=None) -> None:
                calls.append(f"single:{self.config.workers}")

        class _StubSupervisor:
            def __init__(self, config, target, sockets):
                calls.append(f"multi:{config.workers}:{len(sockets)}")

            def run(self) -> None:
                calls.append("supervisor_run")

        def _load_app(_self) -> None:
            calls.append("load_app")

        with (
            patch.object(uvicorn.config.Config, "load_app", _load_app),
            patch.object(uvicorn.config.Config, "bind_socket", return_value=fake_sock),
            patch.object(uvicorn.server, "Server", _StubServer),
            patch.object(web_supervisor, "StaggeredClockMultiprocess", _StubSupervisor),
        ):
            with patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}):
                web_supervisor.run_cli(_uvicorn_args_from_procfile())
            with patch.dict(os.environ, {"WEB_CONCURRENCY": "1"}):
                web_supervisor.run_cli(_uvicorn_args_from_procfile())

        assert calls == ["multi:2:1", "supervisor_run", "load_app", "single:1"]


class TestStaggeredClockSupervisor13532:
    def _build_supervisor(
        self,
        clock: _FakeClock,
        *,
        workers: int = 2,
        max_age_seconds: float = 1800.0,
        min_stagger_seconds: float = 300.0,
        hung_first: bool = False,
    ) -> tuple[web_supervisor.StaggeredClockMultiprocess, list[_FakeWorkerProcess], list[str]]:
        cfg = _supervisor_config(workers=workers)
        timeline: list[str] = []
        spawned: list[_FakeWorkerProcess] = []

        def _fake_process(*_args, **_kwargs):
            idx = len(spawned)
            proc = _FakeWorkerProcess(
                hung_on_terminate=(hung_first and idx == 0),
                timeline=timeline,
            )
            spawned.append(proc)
            return proc

        sup = web_supervisor.StaggeredClockMultiprocess(
            cfg,
            target=lambda sockets=None: None,
            sockets=[],
            max_age_seconds=max_age_seconds,
            min_stagger_seconds=min_stagger_seconds,
            shutdown_join_timeout_seconds=25.0,
            monotonic_fn=clock,
        )
        with patch.object(web_supervisor, "Process", side_effect=_fake_process):
            sup.init_processes()
        return sup, spawned, timeline

    def test_staggers_two_workers_and_never_restarts_both_together(self) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        timeline: list[str] = []
        spawned: list[_FakeWorkerProcess] = []

        def _make_proc(*args, **kwargs):
            proc = _FakeWorkerProcess(timeline=timeline)
            spawned.append(proc)
            return proc

        with patch.object(web_supervisor, "Process", side_effect=_make_proc):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                monotonic_fn=clock,
            )
            sup.init_processes()

            assert sup._next_recycle_at == [1900.0, 2800.0]

            # Before first slot (15 min): nothing recycles.
            clock.advance(899.0)
            assert sup.recycle_aged_worker_if_due() is None

            # At +15 min: replacement starts & becomes ready BEFORE old worker retires.
            clock.advance(1.0)  # now = 1900.0
            first_old_pid = sup.processes[0].pid
            recycled = sup.recycle_aged_worker_if_due()
            assert recycled == 0
            new0_pid = sup.processes[0].pid
            assert new0_pid != first_old_pid
            assert sup._next_recycle_at == [3700.0, 2800.0]

            # Replacement spawned BEFORE old worker was terminated & joined.
            s_idx = timeline.index(f"start:{new0_pid}")
            t_idx = timeline.index(f"terminate:{first_old_pid}")
            assert s_idx < t_idx

            # Immediately afterwards, worker 1 is still untouched even inside cooldown.
            clock.advance(299.0)  # now = 2199.0
            assert sup.recycle_aged_worker_if_due() is None

            # At +30 min (now = 2800.0): worker 1 recycles; worker 0 stays up.
            clock.now = 2800.0
            second_old_pid = sup.processes[1].pid
            assert sup.recycle_aged_worker_if_due() == 1
            assert sup.processes[1].pid != second_old_pid
            assert sup.processes[0].pid == new0_pid
            assert sup._next_recycle_at[0] == 3700.0
            assert sup._next_recycle_at[1] == 4600.0

    def test_clock_jump_past_both_deadlines_recycles_only_one_and_restaggers(self) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        with patch.object(web_supervisor, "Process", side_effect=lambda *a, **k: _FakeWorkerProcess()):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                monotonic_fn=clock,
            )
            sup.init_processes()
            p0_orig = sup.processes[0].pid
            p1_orig = sup.processes[1].pid

            # Jump past BOTH deadlines (1900 and 2800).
            clock.advance(5_000.0)  # now = 6000.0
            recycled = sup.recycle_aged_worker_if_due()
            assert recycled == 0
            assert sup.processes[0].pid != p0_orig
            assert sup.processes[1].pid == p1_orig
            # Worker 1 was pushed forward past min_stagger and blocked during cooldown.
            assert sup._next_recycle_at[1] is not None and sup._next_recycle_at[1] >= 6300.0
            clock.advance(299.0)
            assert sup.recycle_aged_worker_if_due() is None
            clock.advance(1.0)
            assert sup.recycle_aged_worker_if_due() == 1

    def test_refuses_recycle_if_sibling_is_unhealthy(self) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        with patch.object(web_supervisor, "Process", side_effect=lambda *a, **k: _FakeWorkerProcess()):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                monotonic_fn=clock,
            )
            sup.init_processes()
            p0_orig = sup.processes[0].pid
            sup.processes[1].alive = False
            clock.now = 1900.0
            assert sup.recycle_aged_worker_if_due() is None
            assert sup.processes[0].pid == p0_orig

    def test_unexpected_worker_crash_restaggers_sibling_past_min_gap(self) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        with patch.object(web_supervisor, "Process", side_effect=lambda *a, **k: _FakeWorkerProcess()):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                monotonic_fn=clock,
            )
            sup.init_processes()
            # Worker 0 crashes at t=2650 (only 150s before Worker 1's 2800 slot).
            clock.now = 2650.0
            sup.processes[0].alive = False
            p1_pid = sup.processes[1].pid
            sup.keep_subprocess_alive()

            assert sup.processes[0].alive is True
            # Worker 1 did NOT restart at t=2650 and is pushed >= 2650 + 300 = 2950.
            assert sup.processes[1].pid == p1_pid
            assert sup._next_recycle_at[1] is not None and sup._next_recycle_at[1] >= 2950.0

    def test_hung_worker_gets_force_killed_after_join_timeout(self) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        timeline: list[str] = []
        created = 0

        def _make_proc(*args, **kwargs):
            nonlocal created
            created += 1
            return _FakeWorkerProcess(hung_on_terminate=(created == 1), timeline=timeline)

        with patch.object(web_supervisor, "Process", side_effect=_make_proc):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                shutdown_join_timeout_seconds=25.0,
                monotonic_fn=clock,
            )
            sup.init_processes()
            hung = sup.processes[0]
            hung_pid = hung.pid
            clock.now = 1900.0
            assert sup.recycle_aged_worker_if_due() == 0
            assert hung.terminated is True
            assert hung.killed is True
            assert hung.process.join_timeouts == [25.0, 5.0]
            assert f"kill:{hung_pid}" in timeline
            assert timeline.index(f"start:{sup.processes[0].pid}") < timeline.index(f"terminate:{hung_pid}")
            assert timeline.index(f"terminate:{hung_pid}") < timeline.index(f"kill:{hung_pid}")

    def test_failed_replacement_keeps_old_worker_and_parent_alive_and_retries_after_min_gap(
        self,
    ) -> None:
        clock = _FakeClock(1_000.0)
        cfg = _supervisor_config(workers=2)
        timeline: list[str] = []
        spawned: list[_FakeWorkerProcess] = []

        def _make_proc(*_args, **_kwargs):
            idx = len(spawned)
            # Attempts 0 & 1 are initial workers; attempt 2 fails startup; attempt 3 succeeds.
            fails = idx == 2
            proc = _FakeWorkerProcess(
                ready=not fails,
                exitcode=(web_supervisor._STARTUP_FAILURE if fails else None),
                timeline=timeline,
            )
            spawned.append(proc)
            return proc

        with patch.object(web_supervisor, "Process", side_effect=_make_proc):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                max_age_seconds=1800.0,
                min_stagger_seconds=300.0,
                startup_timeout_seconds=5.0,
                monotonic_fn=clock,
            )
            sup.init_processes()
            old0, old1 = sup.processes[0], sup.processes[1]

            clock.now = 1900.0
            assert sup.recycle_aged_worker_if_due() is None

            failed_proc = spawned[2]
            assert failed_proc.killed is True
            assert old0.terminated is False
            assert sup.processes == [old0, old1]
            assert not sup.should_exit.is_set()

            # Parent keep-alive stays up because the failed replacement never entered self.processes.
            sup.keep_subprocess_alive()
            assert not sup.should_exit.is_set()
            assert sup.processes == [old0, old1]
            assert sup._next_recycle_at[0] == 2200.0

            # Still in retry cooldown.
            clock.now = 2199.0
            assert sup.recycle_aged_worker_if_due() is None

            # At +min_stagger, replacement retries and succeeds cleanly.
            clock.now = 2200.0
            assert sup.recycle_aged_worker_if_due() == 0
            assert old0.terminated is True
            assert sup.processes[0] is spawned[3]
            assert sup.processes[1] is old1
            assert sup._next_recycle_at == [4000.0, 2800.0]

    def test_supports_uvicorn_054_two_arg_multiprocess_and_process(self) -> None:
        import threading

        cfg = _supervisor_config(workers=2)
        seen_init: list[tuple[object, object]] = []
        seen_proc: list[tuple[object, object]] = []

        def _fake_mp_init(self, config, sockets) -> None:
            seen_init.append((config, sockets))
            self.config = config
            self.sockets = sockets
            self.processes_num = config.workers
            self.processes = []
            self.should_exit = threading.Event()
            self.signal_queue = []

        def _two_arg_proc(config, sockets):
            seen_proc.append((config, sockets))
            return _FakeWorkerProcess()

        with (
            patch.object(web_supervisor.Multiprocess, "__init__", _fake_mp_init),
            patch.object(web_supervisor, "_MULTIPROCESS_TAKES_TARGET", False),
            patch.object(web_supervisor, "_PROCESS_TAKES_TARGET", False),
            patch.object(web_supervisor, "Process", side_effect=_two_arg_proc),
        ):
            sup = web_supervisor.StaggeredClockMultiprocess(
                cfg,
                target=lambda sockets=None: None,
                sockets=[],
                monotonic_fn=_FakeClock(500.0),
            )
            sup.init_processes()

        assert len(seen_init) == 1
        assert len(seen_proc) == 2


class TestL1CacheCaps13532:
    def test_l1_caps_are_tightened(self) -> None:
        assert events_route._GAME_MARKETS_MAX_SIZE == 10
        assert events_route._RELATED_FUTURES_MAX_SIZE == 10
        assert rc._LAST_GOOD_MAX == 48

    def test_last_good_evicts_past_cap(self) -> None:
        rc._reset_last_good_for_tests()
        try:
            for i in range(rc._LAST_GOOD_MAX + 5):
                rc.remember_last_good(f"k:{i}", {"i": i}, built_at=float(i + 1))
            assert len(rc._last_good) <= rc._LAST_GOOD_MAX
            assert len(rc._last_good) == rc._LAST_GOOD_MAX
            assert "k:0" not in rc._last_good
            assert f"k:{rc._LAST_GOOD_MAX + 4}" in rc._last_good
        finally:
            rc._reset_last_good_for_tests()


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_dummy_asgi_app(tmp_path: Path) -> Path:
    app_file = tmp_path / "dummy_sup_app.py"
    app_file.write_text(
        """
import asyncio, fcntl, os

COUNTER = os.environ["START_COUNTER_FILE"]
FAIL_ON = {int(x) for x in os.environ.get("FAIL_ON_START_N", "").split(",") if x.strip()}


def _bump() -> int:
    with open(COUNTER, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        n = int(raw) if raw else 0
        n += 1
        fh.seek(0)
        fh.truncate()
        fh.write(str(n))
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return n


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                n = _bump()
                await asyncio.sleep(float(os.environ.get("BOOT_SECONDS", "0.1")))
                if n in FAIL_ON:
                    await send({"type": "lifespan.startup.failed", "message": f"fail start {n}"})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    pid = str(os.getpid()).encode("ascii")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain"), (b"connection", b"close")],
        }
    )
    await send({"type": "http.response.body", "body": pid})
""".lstrip(),
        encoding="utf-8",
    )
    return app_file


def _fetch_pid(port: int, *, timeout: float = 2.0) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/pid", timeout=timeout) as resp:
            if resp.status == 200:
                return int(resp.read().decode("ascii").strip())
    except Exception:
        return None
    return None


def _run_real_supervisor(
    tmp_path: Path,
    *,
    port: int,
    max_age_s: float,
    min_stagger_s: float,
    fail_on_start_n: str = "",
) -> tuple[subprocess.Popen[str], Path, Path]:
    _write_dummy_asgi_app(tmp_path)
    counter_file = tmp_path / "starts.txt"
    log_file = tmp_path / "supervisor.log"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": f"{tmp_path}:{BACKEND_DIR}",
            "START_COUNTER_FILE": str(counter_file),
            "FAIL_ON_START_N": fail_on_start_n,
            "BOOT_SECONDS": "0.1",
            "WEB_CONCURRENCY": "2",
            "WEB_WORKER_MAX_AGE_SECONDS": str(max_age_s),
            "WEB_WORKER_MIN_STAGGER_SECONDS": str(min_stagger_s),
            "WEB_WORKER_STARTUP_TIMEOUT_SECONDS": "15",
            "WEB_WORKER_SHUTDOWN_JOIN_TIMEOUT_SECONDS": "5",
        }
    )
    log_fh = open(log_file, "w+", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.web_supervisor",
            "dummy_sup_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--limit-max-requests",
            "5000",
            "--limit-max-requests-jitter",
            "1000",
            "--timeout-graceful-shutdown",
            "3",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._test_log_fh = log_fh  # type: ignore[attr-defined]
    return proc, log_file, counter_file


def _stop_real_supervisor(proc: subprocess.Popen[str]) -> int:
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)
    finally:
        fh = getattr(proc, "_test_log_fh", None)
        if fh is not None:
            fh.close()
    assert proc.returncode is not None
    return int(proc.returncode)


class TestRealProcessStaggeredSupervisor13532:
    def test_real_supervisor_two_workers_recycles_cleanly(self, tmp_path: Path) -> None:
        port = _free_local_port()
        proc, log_file, _counter = _run_real_supervisor(
            tmp_path,
            port=port,
            max_age_s=4.0,
            min_stagger_s=1.0,
        )
        try:
            initial_pids: set[int] = set()
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline and len(initial_pids) < 2:
                pid = _fetch_pid(port)
                if pid is not None:
                    initial_pids.add(pid)
                else:
                    time.sleep(0.05)
            assert len(initial_pids) == 2, f"Expected 2 initial workers, got {initial_pids}"

            new_pid_seen: int | None = None
            recycle_deadline = time.monotonic() + 15.0
            while time.monotonic() < recycle_deadline:
                assert proc.poll() is None, log_file.read_text(encoding="utf-8", errors="replace")
                pid = _fetch_pid(port)
                if pid is not None and pid not in initial_pids:
                    new_pid_seen = pid
                logs_now = log_file.read_text(encoding="utf-8", errors="replace")
                if new_pid_seen is not None and "Staggered clock recycle complete:" in logs_now:
                    break
                time.sleep(0.1)
            assert new_pid_seen is not None, log_file.read_text(encoding="utf-8", errors="replace")

            rc_code = _stop_real_supervisor(proc)
            assert rc_code == 0, log_file.read_text(encoding="utf-8", errors="replace")
            logs = log_file.read_text(encoding="utf-8", errors="replace")
            assert "Staggered clock recycle starting:" in logs
            assert "Staggered clock recycle complete:" in logs
            assert "stopping the parent process" not in logs
        finally:
            if proc.poll() is None:
                _stop_real_supervisor(proc)

    def test_real_supervisor_failed_replacement_keeps_serving_and_retries(self, tmp_path: Path) -> None:
        port = _free_local_port()
        proc, log_file, _counter = _run_real_supervisor(
            tmp_path,
            port=port,
            max_age_s=4.0,
            min_stagger_s=1.5,
            fail_on_start_n="3",
        )
        try:
            initial_pids: set[int] = set()
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline and len(initial_pids) < 2:
                pid = _fetch_pid(port)
                if pid is not None:
                    initial_pids.add(pid)
                else:
                    time.sleep(0.05)
            assert len(initial_pids) == 2

            # Wait for start #3 failure AND start #4 recovery + old worker retirement while serving continuously.
            recovered_pid: int | None = None
            saw_abort = False
            saw_complete = False
            poll_failures = 0
            wait_deadline = time.monotonic() + 25.0
            while time.monotonic() < wait_deadline:
                assert proc.poll() is None, log_file.read_text(encoding="utf-8", errors="replace")
                pid = _fetch_pid(port)
                if pid is None:
                    poll_failures += 1
                elif pid not in initial_pids:
                    recovered_pid = pid
                logs_now = log_file.read_text(encoding="utf-8", errors="replace")
                if "Staggered clock recycle aborted:" in logs_now:
                    saw_abort = True
                if "Staggered clock recycle complete:" in logs_now:
                    saw_complete = True
                if recovered_pid is not None and saw_abort and saw_complete:
                    break
                time.sleep(0.15)

            assert saw_abort, log_file.read_text(encoding="utf-8", errors="replace")
            assert saw_complete, log_file.read_text(encoding="utf-8", errors="replace")
            assert recovered_pid is not None, log_file.read_text(encoding="utf-8", errors="replace")
            assert poll_failures == 0

            rc_code = _stop_real_supervisor(proc)
            assert rc_code == 0, log_file.read_text(encoding="utf-8", errors="replace")
            logs = log_file.read_text(encoding="utf-8", errors="replace")
            assert "Staggered clock recycle aborted:" in logs
            assert "Staggered clock recycle complete:" in logs
            assert "stopping the parent process" not in logs
        finally:
            if proc.poll() is None:
                _stop_real_supervisor(proc)
