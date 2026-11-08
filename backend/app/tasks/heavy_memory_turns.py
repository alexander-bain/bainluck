"""#12019: the Kalshi poll and the market matcher take turns on worker-heavy.

THE SHIP. Newly listed games get a Kalshi price again. Kalshi's market creation
stopped at Sun Nov 8 12:58 AM PT because the poll that creates markets kept
dying before it finished: in the 24 h to 12:45 PM, 12 starts, 4 successes and 4
hard kills. The 12:45 PM run's log shows why — it started beside
``match_prediction_markets`` (both run on worker-heavy, concurrency 2, one
1 GB Standard-2X dyno), R14 "memory quota exceeded" every 22 s from 12:55:12,
then R15 at 12:57:24 and SIGKILL. That is the dyno's memory, not a time limit.

THE RULE. One shared lease, so the two never run at the same time:

* The full poll (``poll_kalshi_markets`` with no ``event_ticker``) takes the
  lease. If the matcher holds it, the poll marks itself PENDING and retries a
  minute later. While the mark is set the matcher declines its next tick, so
  the poll gets the dyno as soon as the current matching pass ends. If it still
  cannot take the lease after ``POLL_MAX_RETRIES`` it runs anyway, which is
  today's behaviour — a held lease must never cost a whole two-hour poll.
* The matcher takes the same lease and declines a tick when the poll holds it
  or is pending. It runs every 15 minutes, so a declined tick costs one pass.

Both log their resident memory at the end (``heavy_memory_turn``), so the next
R14 names which task was large. Every Redis problem fails OPEN: the task runs,
as it did before this module.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: The single lease both tasks take (``single_flight`` prefixes it).
LEASE_TASK = "heavy:kalshi_poll_or_match"

#: Set by a poll that found the matcher running; the matcher's next tick
#: declines while it exists. Outlives the poll's whole retry window.
PENDING_KEY = "bainluck:heavy:kalshi_poll_pending"
PENDING_TTL_S = 1200

#: Lease TTLs a little past each task's Celery hard limit (660 s and 870 s), so
#: a hard-killed holder frees the dyno soon after it could still be alive.
POLL_LEASE_TTL_S = 720
MATCH_LEASE_TTL_S = 930

#: A matching pass measured ~779 s; 15 one-minute retries cover a full pass.
POLL_RETRY_COUNTDOWN_S = 60
POLL_MAX_RETRIES = 15


def _client():
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:  # noqa: BLE001 — a turn must never be why a task cannot start
        return None


def poll_is_pending(rc=None) -> bool:
    """True while a poll is waiting for the matcher to finish. False on any error."""
    client = rc if rc is not None else _client()
    if client is None:
        return False
    try:
        return bool(client.exists(PENDING_KEY))
    except Exception:  # noqa: BLE001
        return False


def mark_poll_pending(rc=None) -> None:
    client = rc if rc is not None else _client()
    if client is None:
        return
    try:
        client.set(PENDING_KEY, "1", ex=PENDING_TTL_S)
    except Exception:  # noqa: BLE001
        pass


def clear_poll_pending(rc=None) -> None:
    client = rc if rc is not None else _client()
    if client is None:
        return
    try:
        client.delete(PENDING_KEY)
    except Exception:  # noqa: BLE001
        pass


def rss_mb() -> float | None:
    """This process's resident memory in MB (``/proc/self/statm``), or None."""
    try:
        with open("/proc/self/statm", "rb") as fh:
            resident_pages = int(fh.read().split()[1])
        return round(resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 1)
    except (OSError, IndexError, ValueError):
        return None


def peak_rss_mb() -> float | None:
    """This process's peak resident memory in MB (``VmHWM``), or None."""
    try:
        with open("/proc/self/status", "rb") as fh:
            for line in fh:
                if line.startswith(b"VmHWM:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, IndexError, ValueError):
        # No /proc (macOS) or an unexpected line: unmeasured, never a small number.
        return None
    return None


def log_memory(task: str, start_mb: float | None) -> None:
    """One line per run: start, end and peak RSS. Never raises."""
    try:
        logger.info(
            "heavy_memory_turn task=%s pid=%s rss_start_mb=%s rss_end_mb=%s peak_mb=%s",
            task,
            os.getpid(),
            start_mb,
            rss_mb(),
            peak_rss_mb(),
        )
    except Exception:  # noqa: BLE001 — instrumentation never raises
        pass
