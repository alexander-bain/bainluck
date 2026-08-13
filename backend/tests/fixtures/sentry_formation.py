"""The deployed formation, PARSED from backend/Procfile — never hand-copied (#1501).

Codex C-CERT-SENTRY (c) rejected the previous volume claim partly because its
budget arithmetic "prices four realtime children" while the Procfile also
declares background and heavy pools, web, a scheduler and a websocket process.
A constant transcribed into a comment cannot notice a new dyno type; this module
reads the file, so adding one to the Procfile changes the derived number and
trips :mod:`tests.test_sentry_filter`.

Why the process count is what matters: ``app/utils/sentry_filter.py`` keeps its
throttle state **in process memory** (deliberately — gotcha #39: the biggest
error class is Redis being unreachable, and a filter that needs Redis to decide
whether to report a Redis failure fails exactly when it matters). So every
process that calls ``sentry_sdk.init`` holds its own independent allowance, and
the fleet ceiling for one signature is

    cap x (SDK processes) x (process incarnations per process per day)

Celery's prefork pool forks children from the parent AFTER ``sentry_sdk.init``
has run at import time, so each child inherits a *copy* of an empty throttle
table — a fresh allowance per child, and another one every time
``--max-memory-per-child`` recycles it.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Free Developer plan (``am3_f``): 5,000 error events per billing month,
#: on-demand disabled, period the 21st -> the 20th.
QUOTA_EVENTS_PER_MONTH = 5_000
#: Mean days per month, so the daily budget does not swing with month length.
DAYS_PER_MONTH = 30.4
DAILY_BUDGET = QUOTA_EVENTS_PER_MONTH / DAYS_PER_MONTH  # ~164.5/day

PROCFILE = Path(__file__).resolve().parents[2] / "Procfile"


def parse_procfile(path: Path = PROCFILE) -> dict[str, dict]:
    """``{proc_type: {"command", "concurrency", "max_memory_kb", "kind"}}``."""
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, command = line.split(":", 1)
        name, command = name.strip(), command.strip()
        conc = re.search(r"--concurrency[= ](\d+)", command)
        mem = re.search(r"--max-memory-per-child[= ](\d+)", command)
        if "celery" in command and " worker" in f" {command}":
            kind = "celery_worker"
        elif "celery" in command and "beat" in command:
            kind = "celery_beat"
        elif name == "release":
            kind = "release"
        else:
            kind = "single"
        out[name] = {
            "command": command,
            "concurrency": int(conc.group(1)) if conc else None,
            "max_memory_kb": int(mem.group(1)) if mem else None,
            "kind": kind,
        }
    return out


def sdk_processes(spec: dict) -> int:
    """OS processes that hold their own ``before_send`` state, for one dyno.

    A celery prefork worker is the parent plus ``--concurrency`` children; the
    parent counts because billiard's worker-death records are emitted there.
    """
    if spec["kind"] == "celery_worker":
        return 1 + (spec["concurrency"] or 1)
    return 1


FORMATION = parse_procfile()

#: Steady-state process types (``release`` is transient, one per deploy).
STEADY_TYPES = tuple(sorted(n for n in FORMATION if n != "release"))

#: Every steady-state process type initialises the SDK: ``web`` imports
#: ``app.main``; the celery types boot ``app.tasks.celery_app``; ``worker-ws``
#: runs ``run_kalshi_ws.py``, whose ``from app.tasks.kalshi_ws import ...``
#: executes ``app/tasks/__init__.py`` and therefore its ``sentry_sdk.init``.
STEADY_SDK_PROCESSES = sum(sdk_processes(FORMATION[n]) for n in STEADY_TYPES)

#: One dyno of each type is running in production (``heroku ps -a bainluck``,
#: verified 2026-08-13). Scaling any type up multiplies the ceiling below.
DYNOS_PER_TYPE = 1
