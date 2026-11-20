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

RSS alone can't say what the dyno pays for. A prefork child starts at ~160 MB of
RSS that is mostly the parent's pages, shared until written (copy-on-write), and
Heroku's quota counts a shared page once. So the end of each line also carries,
from ``/proc/<pid>/smaps_rollup``, the child's ``private_mb`` (pages only it
holds: its own allocations plus parent pages it has written), ``shared_mb`` and
``pss_mb``, and the parent's ``parent_pss_mb``. The parent's PSS plus each
child's is the dyno's real footprint. A ``private_mb`` near the RSS on a quiet
task means copy-on-write broke the sharing, not that the task allocated.
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


#: ``smaps_rollup`` fields (kB) summed into each reported figure.
_PRIVATE_FIELDS = ("Private_Clean", "Private_Dirty")
_SHARED_FIELDS = ("Shared_Clean", "Shared_Dirty")


def smaps_mb(pid: int | str = "self") -> dict[str, float] | None:
    """``{"pss", "private", "shared"}`` in MB for ``pid``; None where unreadable."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as fh:
            kb: dict[str, int] = {}
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    kb[key.strip()] = int(parts[0])
    except OSError:
        return None
    if "Pss" not in kb:
        return None
    return {
        "pss": round(kb["Pss"] / 1024, 1),
        "private": round(sum(kb.get(f, 0) for f in _PRIVATE_FIELDS) / 1024, 1),
        "shared": round(sum(kb.get(f, 0) for f in _SHARED_FIELDS) / 1024, 1),
    }


def _split_fields() -> str:
    """`` private_mb=… shared_mb=… pss_mb=… parent_pss_mb=…``; ``None`` where unreadable."""
    own = smaps_mb() or {}
    parent = smaps_mb(os.getppid()) or {}
    return " private_mb=%s shared_mb=%s pss_mb=%s parent_pss_mb=%s" % (
        own.get("private"), own.get("shared"), own.get("pss"), parent.get("pss"),
    )


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
            "task_memory task=%s pid=%s rss_start_mb=%s rss_end_mb=%s peak_mb=%s%s",
            name, os.getpid(), start, rss_mb(), peak_rss_mb(), _split_fields(),
        )
    except Exception:  # noqa: BLE001
        pass
