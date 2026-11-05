"""#11929 Decide 27-B serve: an observed span draws flat at 15-minute steps.

PILLAR: TRUTH. SHIP: a market we were reading the whole time never shows a
hole. The writer (``stream_observed_spans``) records each stretch a live
connection carried a leg. This module turns those stretches into chart points
AT SERVE TIME, so web and iPhone draw them with no client change.

THE RULE. After a served point at ``t`` with value ``v``, if a span contains
``t``, the leg was observed and its price did not move until the next point
(the move writer writes a point on any 1-point move, and on any difference once
the last point is 5 minutes old). So ``v`` is repeated every
:data:`SPAN_STEP_S` from ``t`` up to whichever comes first: the next real
point, the span's end, or ``until`` (now, or the settlement instant). If the
span ends before the next point, one final step sits AT the span's end, and the
stretch after it is left a gap: nothing observed it. A gap no span covers is
never filled. A step is marked ``provenance: "observed_span"`` so a reader can
always tell it from a capture, and it is never counted as a data point.

SWITCH. ``SERVE_OBSERVED_SPANS`` (read per request): unset/``0`` = off (the
default) and the chart routes behave exactly as before; ``1`` = on. Turning it
on is an attended config change after the writer has filled spans.

Never raises into a chart: a failed span read serves the chart without steps.
"""

from __future__ import annotations

import logging
import os
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

SERVE_OBSERVED_SPANS_ENV = "SERVE_OBSERVED_SPANS"
#: The step between drawn points inside a span (Alex: "15-minute steps").
SPAN_STEP_S = 900
OBSERVED_SPAN_PROVENANCE = "observed_span"

Span = tuple[datetime, datetime]


def serve_spans_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(SERVE_OBSERVED_SPANS_ENV) or "").strip().lower() in ("1", "on", "true", "yes")


def merge_spans(spans: Iterable[Span]) -> list[Span]:
    """Sorted, with overlapping or touching spans joined (one observation)."""
    out: list[list[datetime]] = []
    for start, end in sorted(spans):
        if end < start:
            continue
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(s, e) for s, e in out]


def _containing(spans: Sequence[Span], starts: Sequence[datetime], at: datetime) -> Span | None:
    i = bisect_right(starts, at) - 1
    if i >= 0 and spans[i][0] <= at <= spans[i][1]:
        return spans[i]
    return None


def span_steps(
    points: Sequence[tuple[datetime, float]],
    spans: Iterable[Span],
    *,
    until: datetime | None,
    step_s: int = SPAN_STEP_S,
) -> list[tuple[datetime, float]]:
    """The steps to ADD to one leg's sorted ``points`` (see the module rule).

    ``until``: no step at or after it (now, or the settlement instant); None
    means no tail after the last point.
    """
    merged = merge_spans(spans)
    if not merged or not points:
        return []
    starts = [s for s, _e in merged]
    step = timedelta(seconds=step_s)
    out: list[tuple[datetime, float]] = []
    for i, (at, value) in enumerate(points):
        span = _containing(merged, starts, at)
        if span is None:
            continue
        nxt = points[i + 1][0] if i + 1 < len(points) else None
        limit = span[1]
        bounded_by_point = False
        if nxt is not None and nxt <= limit:
            limit, bounded_by_point = nxt, True
        if until is not None and until <= limit:
            limit, bounded_by_point = until, True
        elif nxt is None and until is None:
            continue  # no tail without a bound
        t = at + step
        while t < limit:
            out.append((t, value))
            t += step
        # The observation ended before anything else did: the flat line
        # reaches its end, and what follows stays a gap.
        if not bounded_by_point and limit > at and (not out or out[-1][0] < limit):
            out.append((limit, value))
    return out


async def load_observed_spans(
    db: Any, outcome_ids: Iterable[int], start: datetime, end: datetime,
) -> dict[int, list[Span]]:
    """Per outcome, its spans overlapping ``[start, end]``; an open span ends at
    its venue heartbeat. ``{}`` when off, on no ids, or on any failure."""
    ids = sorted({int(o) for o in outcome_ids})
    if not ids or not serve_spans_enabled():
        return {}
    from sqlalchemy import text

    try:
        result = await db.execute(
            text(
                "SELECT s.outcome_id, s.started_at, "
                "COALESCE(s.ended_at, h.beat_at, s.started_at) AS ended_at "
                "FROM stream_observed_spans AS s "
                "LEFT JOIN stream_span_heartbeats AS h ON h.venue = s.venue "
                "WHERE s.outcome_id = ANY(CAST(:ids AS integer[])) "
                "AND s.started_at <= CAST(:end AS timestamptz) "
                "AND COALESCE(s.ended_at, h.beat_at, s.started_at) >= CAST(:start AS timestamptz) "
                "ORDER BY s.outcome_id, s.started_at"
            ),
            {"ids": ids, "start": start, "end": end},
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001 — a span read never fails a chart
        logger.warning("observed spans: read for %d legs failed: %s", len(ids), str(exc)[:200])
        return {}
    out: dict[int, list[Span]] = {}
    for oid, started, ended in rows:
        out.setdefault(int(oid), []).append((started, ended))
    return out


def _stamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


async def add_history_steps(
    db: Any,
    outcome_history: Mapping[int, dict],
    *,
    now: datetime,
    until_for: Any,
) -> int:
    """``/history``: add each drawn leg's steps to its ``history`` list, in place.

    ``until_for(oid)`` → the leg's ``until`` (now, the settlement instant, or
    None for no tail). Returns the number of steps added; 0 when off.
    """
    if not serve_spans_enabled():
        return 0
    series: dict[int, list[tuple[datetime, float, str]]] = {}
    for oid, entry in outcome_history.items():
        points = []
        for pt in entry.get("history") or ():
            at, prob = _stamp(pt.get("timestamp")), pt.get("probability")
            if at is not None and prob is not None:
                points.append((at, float(prob), pt.get("bookmaker") or "consensus"))
        if points:
            series[oid] = sorted(points, key=lambda p: p[0])
    if not series:
        return 0
    start = min(points[0][0] for points in series.values())
    spans = await load_observed_spans(db, series.keys(), start, now)
    added = 0
    for oid, points in series.items():
        steps = span_steps(
            [(at, value) for at, value, _book in points], spans.get(oid, ()),
            until=until_for(oid),
        )
        if not steps:
            continue
        times = [at for at, _value, _book in points]
        history = outcome_history[oid]["history"]
        for at, value in steps:
            # The step repeats the point before it, so it carries that point's book.
            book = points[bisect_right(times, at) - 1][2]
            history.append({
                "timestamp": at.isoformat(),
                "probability": value,
                "american_odds": None,
                "bookmaker": book,
                "provenance": OBSERVED_SPAN_PROVENANCE,
            })
        history.sort(key=lambda pt: _stamp(pt["timestamp"]))
        added += len(steps)
    return added


async def add_timeline_steps(
    db: Any,
    entries_by_instant: dict[datetime, dict],
    legs: Mapping[int, str],
    *,
    now: datetime,
    until: datetime | None,
) -> int:
    """``/probability-timeline``: seat each charted leg's steps as entries, in place.

    ``legs``: outcome id → the name its values are keyed by. A step joins an
    existing entry at its instant only where that leg has no value there
    (``setdefault``: a capture, venue or archive value keeps its seat) and
    never adds ``Field`` (no Field member was read at a step, #7351).
    """
    if not serve_spans_enabled() or not legs:
        return 0
    series: dict[int, list[tuple[datetime, float]]] = {}
    for at in sorted(entries_by_instant):
        values = entries_by_instant[at].get("outcomes") or {}
        for oid, name in legs.items():
            if values.get(name) is not None:
                series.setdefault(oid, []).append((at, float(values[name])))
    if not series:
        return 0
    start = min(points[0][0] for points in series.values())
    spans = await load_observed_spans(db, series.keys(), start, now)
    added = 0
    for oid, points in series.items():
        name = legs[oid]
        for at, value in span_steps(points, spans.get(oid, ()), until=until):
            entry = entries_by_instant.setdefault(
                at, {"timestamp": at.isoformat(), "outcomes": {}}
            )
            if name not in entry["outcomes"]:
                entry["outcomes"][name] = round(value, 6)
                entry.setdefault("observed_span", []).append(name)
                added += 1
    return added
