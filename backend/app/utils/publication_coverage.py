"""#12108 PR 1: is the blend we serve being recorded, and how fast is it growing?

The gauge plan §5 (on #11850) asks for, as one task summary in task metrics:

* ``events_with_line`` — events that started in the last 24 h with a sportsbook
  line (a ``betting`` value in ``win_probability_sources``);
* ``with_row_by_t_minus_1h`` / ``with_row_by_start`` — how many of those have a
  ``probability_publications`` row recorded at or before T-1h / the start;
* ``table_bytes`` — the table's total size (``pg_total_relation_size``, no
  scan), and ``projected_month_bytes`` — the growth since the previous run's
  sample (kept in Redis), scaled to 30 days. No table scan anywhere: the rows
  are never counted. Over :data:`MONTHLY_ALARM_BYTES` the status is ``alarm``
  (logged at ERROR). Acceptance (plan §5): ≥ 90 % coverage at T-1h and at the start, and
  growth ≤ 60 MB a day.

Dark: with ``PROBABILITY_PUBLICATION_RECORDING`` off it runs nothing and returns
``{"status": "disabled"}`` — there is nothing being recorded to measure.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.probability_publication import recording_enabled

logger = logging.getLogger(__name__)

#: Plan §5: alarm when the table would grow by 2 GB in a month.
MONTHLY_ALARM_BYTES = 2 * 1024**3
#: Plan §5 acceptance: at least this share of events with a line covered.
COVERAGE_TARGET = 0.90

COVERAGE_SQL = """
SELECT
  COUNT(*) AS events_with_line,
  COUNT(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM probability_publications p
    WHERE p.event_id = e.id AND p.recorded_at <= e.commence_time - INTERVAL '1 hour'
  )) AS with_row_by_t_minus_1h,
  COUNT(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM probability_publications p
    WHERE p.event_id = e.id AND p.recorded_at <= e.commence_time
  )) AS with_row_by_start
FROM events e
WHERE e.commence_time > CAST(:now AS timestamptz) - INTERVAL '24 hours'
  AND e.commence_time <= CAST(:now AS timestamptz)
  AND e.win_probability_sources ? 'betting'
"""

SIZE_SQL = "SELECT pg_total_relation_size('probability_publications') AS table_bytes"
#: The previous run's size sample, for the growth rate.
SIZE_SAMPLE_KEY = "publication_coverage:last_size"
SIZE_SAMPLE_TTL_S = 7 * 24 * 3600
#: Under this much time between samples the rate is too noisy to project.
MIN_SAMPLE_GAP_S = 3600


def _share(part: int, whole: int) -> Optional[float]:
    return round(part / whole, 4) if whole else None


def projected_month_bytes(
    table_bytes: int, now: datetime, previous: Optional[dict]
) -> Optional[float]:
    """Growth since ``previous`` ({"bytes", "at" epoch}) scaled to 30 days;
    ``None`` (UNKNOWN) with no usable previous sample."""
    if not isinstance(previous, dict):
        return None
    try:
        gap = now.timestamp() - float(previous["at"])
        grown = table_bytes - int(previous["bytes"])
    except (KeyError, TypeError, ValueError):
        return None
    if gap < MIN_SAMPLE_GAP_S:
        return None
    return max(grown, 0) * (30 * 86400 / gap)


def coverage_summary(
    coverage: dict, table_bytes: int, projected: Optional[float]
) -> dict[str, Any]:
    """Pure: the reads → the gauge. Shares are ``None`` (UNKNOWN) with no
    events, never 0 or 100 %; growth is ``None`` without a previous sample."""
    events = int(coverage.get("events_with_line") or 0)
    by_t1h = int(coverage.get("with_row_by_t_minus_1h") or 0)
    by_start = int(coverage.get("with_row_by_start") or 0)
    alarm = projected is not None and projected > MONTHLY_ALARM_BYTES
    return {
        "status": "alarm" if alarm else "ok",
        "events_with_line": events,
        "with_row_by_t_minus_1h": by_t1h,
        "with_row_by_start": by_start,
        "share_by_t_minus_1h": _share(by_t1h, events),
        "share_by_start": _share(by_start, events),
        "coverage_target": COVERAGE_TARGET,
        "table_bytes": int(table_bytes),
        "projected_month_bytes": int(projected) if projected is not None else None,
        "monthly_alarm_bytes": MONTHLY_ALARM_BYTES,
    }


def _swap_size_sample(table_bytes: int, now: datetime, client: Any = None) -> Optional[dict]:
    """Store this run's size sample; return the previous one (or ``None``).
    A Redis failure costs only the growth figure, never the gauge."""
    try:
        if client is None:
            from app.tasks.redis_state import get_redis_client

            client = get_redis_client()
        raw = client.get(SIZE_SAMPLE_KEY)
        client.set(
            SIZE_SAMPLE_KEY,
            json.dumps({"bytes": int(table_bytes), "at": now.timestamp()}),
            ex=SIZE_SAMPLE_TTL_S,
        )
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — growth is optional, coverage is not
        logger.warning("publication coverage: size sample unavailable: %s", str(exc)[:200])
        return None


async def publication_coverage(
    db: Any, *, now: Optional[datetime] = None, redis: Any = None
) -> dict[str, Any]:
    """Two reads and one Redis sample; nothing written to the database. Off
    unless recording is on."""
    if not recording_enabled():
        return {"status": "disabled"}
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    coverage = (await db.execute(text(COVERAGE_SQL), {"now": now})).mappings().one()
    table_bytes = int((await db.execute(text(SIZE_SQL))).scalar() or 0)
    previous = _swap_size_sample(table_bytes, now, redis)
    summary = coverage_summary(dict(coverage), table_bytes, projected_month_bytes(table_bytes, now, previous))
    if summary["status"] == "alarm":
        logger.error(
            "probability_publications growth alarm: projected %s bytes/month (alarm %s)",
            summary["projected_month_bytes"], MONTHLY_ALARM_BYTES,
        )
    return summary
