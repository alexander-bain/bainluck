"""#11929 — `/history` serves each line at the chart's resolution, not every row.

THE PAYLOAD THIS BOUNDS. `GET /api/futures/{id}/history` serves every row in
its window, and a window's rows grow with how often we write them, not with
what the chart can draw. Measured on production 2026-11-04 ~05:1xZ (public GETs):

    market    request                 bytes       longest line
    86832     hours=168&range=full    1,994,661   1,555 points
    40533     hours=168&range=full    1,623,936   1,511 points
    1         hours=168&range=full    1,413,675   1,270 points
    108629    hours=168                 237,422     249 points

and #11929's cause 2 makes the live stream write up to a point a minute per
leg — 10,080 a week, on the 1W read every futures page opens with.

THE RESOLUTION. `FuturesChart` draws on an 800-unit viewBox whose plot is 730
units wide (50 left + 20 right padding). A line holding more points than that
cannot draw them, so a line longer than `CHART_RESOLUTION_POINTS` is served as
the LAST REAL OBSERVATION in each of that many equal slices of its window.
Never an average, never an interpolated value, never a smoothed one: every
served point is a point the route had already decided to serve, at its own
instant and its own value. A line that already fits is returned untouched, so
every line within the budget is byte-for-byte what it was.

ALWAYS KEPT, whatever bucket they fall in: a line's first point (its opening —
the value a reader compares the last one with) and every settlement point
(`bookmaker == "settlement"`, the freeze's terminal mark — settled means
settled). The last point needs no rule: it is the last in its own bucket.

Pure: no DB, no clock. The route hands in the window and the lines.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

#: One point per unit of `FuturesChart`'s 730-unit plot (see the header).
CHART_RESOLUTION_POINTS = 730


def bucket_seconds_for(window_seconds: float, points: int = CHART_RESOLUTION_POINTS) -> int:
    """The slice width for a window: whole minutes, never below one.

    Whole minutes on an epoch-aligned grid, so two reads of one window cut on
    the same edges and a reload does not reshuffle which instants are served.
    """
    if not window_seconds or window_seconds <= 0 or points <= 0:
        return 60
    return max(60, math.ceil(window_seconds / points / 60) * 60)


def _stamp(point: dict) -> Optional[datetime]:
    raw = point.get("timestamp")
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def thin_line(history: list, bucket_seconds: int) -> list:
    """The last real observation in each bucket, plus the always-kept points.

    A point whose stamp will not parse is kept: a point this cannot place is
    never dropped on the strength of a bucket it cannot be put in. Order is the
    input's own.
    """
    keep: set[int] = {0} if history else set()
    last_in_bucket: dict[int, tuple[datetime, int]] = {}
    for i, point in enumerate(history):
        ts = _stamp(point)
        if ts is None or point.get("bookmaker") == "settlement":
            keep.add(i)
            continue
        key = int(ts.timestamp()) // bucket_seconds
        held = last_in_bucket.get(key)
        if held is None or ts >= held[0]:
            last_in_bucket[key] = (ts, i)
    keep.update(i for _ts, i in last_in_bucket.values())
    return [p for i, p in enumerate(history) if i in keep]


def thin_history_to_resolution(
    outcome_history: dict,
    *,
    window_hours: float,
    now: datetime,
    points: int = CHART_RESOLUTION_POINTS,
) -> Optional[dict]:
    """Thin, in place, every line longer than `points`; None when none was.

    The window is the longer of the one searched (`window_hours`) and the one
    the served points actually reach back to (an archive interval under
    `range=full` can predate the live window). Returns the additive
    `resolution` block the route serves beside the lines it thinned.
    """
    long_lines = [
        entry for entry in outcome_history.values()
        if len(entry.get("history") or ()) > points
    ]
    if not long_lines:
        return None
    stamps = [
        ts for entry in outcome_history.values()
        for ts in (_stamp(p) for p in entry.get("history") or ())
        if ts is not None
    ]
    reach_s = (now - min(stamps)).total_seconds() if stamps else 0.0
    window_s = max(float(window_hours or 0) * 3600.0, reach_s)
    bucket_s = bucket_seconds_for(window_s, points)
    before = after = 0
    for entry in long_lines:
        history = entry["history"]
        thinned = thin_line(history, bucket_s)
        before += len(history)
        after += len(thinned)
        entry["history"] = thinned
    return {
        "bucket_seconds": bucket_s,
        "max_points_per_line": points,
        "lines_thinned": len(long_lines),
        "points_before": before,
        "points_served": after,
    }
