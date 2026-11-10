"""#12042: one memory line per task on worker-background, so a spike names its task.

worker-background (Standard-1X, 512 MB, two prefork children) sat above 95% of its
quota in 78 of 208 runtime samples on Nov 10 (16:04-17:14Z) and peaked at 1,001 MB
with 518 MB in swap, while two long tasks overlapped. A window can't say which task
grew: the frequent warmers sit beside every sample. This logs, after every task,
the child's RSS at start and end and its peak DURING the task, the same shape heavy
logs as ``heavy_memory_turn``.

The peak is per task because the child's high-water mark (``VmHWM``) is reset when
the task starts (``/proc/self/clear_refs`` = 5) and a prefork child runs one task
at a time. Only on ``worker-background`` dynos (Heroku sets ``DYNO``): no config
change, and the other workers' logs are untouched. Never raises.
"""
from __future__ import annotations

import logging
import os

from app.tasks.heavy_memory_turns import peak_rss_mb, rss_mb

logger = logging.getLogger(__name__)

#: Dyno-name prefixes that log a line per task.
WATCHED_DYNO_PREFIXES = ("worker-background",)

_started: dict[str, float | None] = {}


def enabled() -> bool:
    return os.environ.get("DYNO", "").startswith(WATCHED_DYNO_PREFIXES)


def reset_peak() -> bool:
    """Reset this process's ``VmHWM`` to its current RSS. False where unsupported."""
    try:
        with open("/proc/self/clear_refs", "w") as fh:
            fh.write("5")
        return True
    except OSError:
        return False


def task_started(task_id: str | None) -> None:
    try:
        if not enabled() or not task_id:
            return
        reset_peak()
        _started[task_id] = rss_mb()
    except Exception:  # noqa: BLE001 — instrumentation never raises
        pass


def task_finished(task_id: str | None, name: str | None) -> None:
    try:
        if not enabled() or not task_id:
            return
        start = _started.pop(task_id, None)
        logger.info(
            "task_memory task=%s pid=%s rss_start_mb=%s rss_end_mb=%s peak_mb=%s",
            name, os.getpid(), start, rss_mb(), peak_rss_mb(),
        )
    except Exception:  # noqa: BLE001
        pass
