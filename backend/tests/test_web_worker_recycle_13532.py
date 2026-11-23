"""Regression guards for #13532 uvicorn worker recycling on web dynos.

Why all three flags belong together on `backend/Procfile`'s `web:` line:
- `--limit-max-requests`: recycles each worker process periodically so accumulated
  per-worker L1 caches do not push `web.1` over its 1,024 MB memory quota into swap.
- `--limit-max-requests-jitter`: staggers recycles across the two `WEB_CONCURRENCY=2`
  workers so both do not restart together.
- `--timeout-graceful-shutdown`: bounded shutdown (`15`s). Without it, uvicorn's
  default is `None` (unbounded wait) while `/api/events/stream` and
  `/api/markets/stream` hold SSE connections for up to `MAX_CONNECTION_S = 900` s
  and `Multiprocess.Process.always_pong` keeps healthchecks green — leaving a
  recycling worker closed to new requests yet holding all its RAM for up to 15 min.
"""

from __future__ import annotations

import importlib
import os
import shlex
from pathlib import Path
from unittest.mock import patch

import uvicorn.config
import uvicorn.server

from app.routes import event_stream, market_stream

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


def _click_params() -> dict[str, object]:
    tokens = _web_command_tokens()
    assert tokens[0] == "uvicorn", f"Unexpected web entrypoint: {tokens!r}"
    # Import the module explicitly so `uvicorn.__init__.main` (re-exported Command)
    # cannot shadow module lookup and resolve `Command.main` method by mistake.
    uvicorn_main = importlib.import_module("uvicorn.main")
    ctx = uvicorn_main.main.make_context("uvicorn", tokens[1:])
    return ctx.params


class TestWebWorkerRecycleProcfile:
    def test_web_command_binds_all_three_recycle_flags(self) -> None:
        params = _click_params()

        max_requests = params["limit_max_requests"]
        jitter = params["limit_max_requests_jitter"]
        graceful_shutdown = params["timeout_graceful_shutdown"]

        assert isinstance(max_requests, int) and 200 <= max_requests <= 2000
        assert isinstance(jitter, int) and 0 < jitter < max_requests
        assert isinstance(graceful_shutdown, int) and 5 <= graceful_shutdown <= 30

        # SSE streams can run up to 900s; shutdown timeout must stay far tighter.
        assert graceful_shutdown < event_stream.MAX_CONNECTION_S
        assert graceful_shutdown < market_stream.MAX_CONNECTION_S

    def test_web_command_does_not_hardcode_workers(self) -> None:
        """Heroku's `WEB_CONCURRENCY` controls worker count without editing Procfile."""
        tokens = _web_command_tokens()
        assert not any(
            tok == "--workers" or tok.startswith("--workers=") or tok == "-w"
            for tok in tokens
        )

    def test_uvicorn_config_honors_flags_with_web_concurrency(self) -> None:
        params = _click_params()
        with patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}):
            cfg = uvicorn.config.Config(
                params["app"],
                host=params["host"],
                port=int(params["port"]),
                limit_max_requests=params["limit_max_requests"],
                limit_max_requests_jitter=params["limit_max_requests_jitter"],
                timeout_graceful_shutdown=params["timeout_graceful_shutdown"],
            )
        assert cfg.workers == 2
        assert cfg.limit_max_requests == 600
        assert cfg.limit_max_requests_jitter == 150
        assert cfg.timeout_graceful_shutdown == 15

    async def test_uvicorn_server_on_tick_triggers_exit_with_jitter_band(self) -> None:
        params = _click_params()
        cfg = uvicorn.config.Config(
            params["app"],
            host=params["host"],
            port=int(params["port"]),
            limit_max_requests=params["limit_max_requests"],
            limit_max_requests_jitter=params["limit_max_requests_jitter"],
            timeout_graceful_shutdown=params["timeout_graceful_shutdown"],
        )
        server = uvicorn.server.Server(cfg)
        threshold = server.limit_max_requests
        assert threshold is not None and 600 <= threshold <= 750

        server.server_state.total_requests = threshold - 1
        assert await server.on_tick(1) is False

        server.server_state.total_requests = threshold
        assert await server.on_tick(2) is True
