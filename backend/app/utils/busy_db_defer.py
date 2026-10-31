"""#10090: heavy background scans stand down while production Postgres is busy.

On Saturday 2026-10-31 the database was disk-read saturated (read-iops ~2,700
on standard-3, active queries parked on ``DataFileRead``) and signed-in Sports,
My Stuff and Discover requests ran past the router's 25 s limit. A
``pg_stat_statements`` diff over 16:41-17:24Z put about a quarter of all blocks read
on background scans no reader waits on: the winner-coverage census, theme
assembly's candidate union, the calibration bucket build, Phase 1.5's resolved
cross-sport sweep, the opening-repair walk and the matching-reconciliation
counts. This module is the one switch those call sites read.

``BUSY_DB_DEFER_HEAVY_SCANS=1`` turns it on; anything else (including unset)
is off and every scan runs exactly as before. While on, a scan whose call site
asks :func:`should_defer` during the busy window skips that run and logs one
WARNING line naming itself — never silently. The window is a fixed UTC hour
range, ``BUSY_DB_DEFER_HOURS_UTC`` (``"15-05"`` by default: 8 AM to 10 PM PT,
11 AM to 1 AM ET), because it is the predicate a reader of a log line can check
without a query, and a cheap Postgres busy signal would itself be a read on the
saturated database. Outside the window the scans run as normal, so each still
gets ~10 hours a night.

Settlement, grading and price writes never call this. A deferred run returns
:func:`deferred_result`, whose ``terminal: skipped`` the task-verdict contract
already reads as "banked no work" — not GREEN and not a failure.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

SWITCH_ENV = "BUSY_DB_DEFER_HEAVY_SCANS"
HOURS_ENV = "BUSY_DB_DEFER_HOURS_UTC"
DEFAULT_BUSY_HOURS_UTC = (15, 5)
DEFERRED_REASON = "busy_db_deferred"


def switch_on() -> bool:
    """Read per call, so a config change takes effect on the next run."""
    return os.getenv(SWITCH_ENV, "").strip() == "1"


def busy_hours_utc() -> tuple[int, int]:
    """``(start, end)`` hours, end exclusive; a window may wrap midnight.

    A malformed value falls back to the default with a warning rather than
    raising: a typo in a config var must not stop the scans' own tasks.
    """
    raw = os.getenv(HOURS_ENV, "").strip()
    if not raw:
        return DEFAULT_BUSY_HOURS_UTC
    try:
        start_s, end_s = raw.split("-")
        start, end = int(start_s), int(end_s)
    except ValueError:
        start = end = -1
    if not (0 <= start <= 23 and 0 <= end <= 23):
        logger.warning(
            "busy-db defer: %s=%r is not 'H-H' with hours 0-23; using %02d-%02d",
            HOURS_ENV, raw, *DEFAULT_BUSY_HOURS_UTC,
        )
        return DEFAULT_BUSY_HOURS_UTC
    return start, end


def in_busy_window(now: Optional[datetime] = None) -> bool:
    """Equal start and end is an empty window: nothing is busy.

    A naive ``now`` is UTC, as the task code's naive datetimes are.
    """
    start, end = busy_hours_utc()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)
    hour = now.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def should_defer(scan: str, now: Optional[datetime] = None) -> bool:
    """True when ``scan`` must skip this run; logs the skip when it does."""
    if not switch_on() or not in_busy_window(now):
        return False
    start, end = busy_hours_utc()
    logger.warning(
        "busy-db defer: %s skipped this run (%s=1, busy window %02d:00-%02d:00 UTC)",
        scan, SWITCH_ENV, start, end,
    )
    return True


def deferred_result(scan: str, **extra: Any) -> dict:
    start, end = busy_hours_utc()
    return {
        "terminal": "skipped",
        "reason": DEFERRED_REASON,
        "scan": scan,
        "busy_hours_utc": f"{start:02d}-{end:02d}",
        **extra,
    }
