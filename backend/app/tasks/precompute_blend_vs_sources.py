"""Bounded read-only precompute for /calibration Blend vs Contributing Sources (#356a).

Scans completed events since ``RECORDING_START_ISO`` in small batches using
indexed ``LATERAL`` lookups on ``probability_publications (event_id, rev)``,
enforcing ``SET LOCAL transaction_read_only = on`` and ``statement_timeout``
10s, then publishes the precomputed JSON payload to Redis.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.utils.blend_vs_sources_calibration import (
    HOLDOUT_END_ISO,
    HOLDOUT_START_ISO,
    LAST_GOOD_KEY,
    LAST_GOOD_TTL_S,
    RECORDING_START_ISO,
    REDIS_KEY,
    TTL_S,
    build_blend_vs_sources_payload,
)
from app.utils.publication_reader import HORIZONS

logger = logging.getLogger(__name__)

_ENV_HOLDOUT_RELEASED = "BLEND_VS_SOURCES_HOLDOUT_RELEASED"
_ENV_MIN_COMMENCE_TIME = "BLEND_VS_SOURCES_MIN_COMMENCE_TIME"
_ENV_MAX_COMMENCE_TIME = "BLEND_VS_SOURCES_MAX_COMMENCE_TIME"
_ENV_EXCLUDE_START = "BLEND_VS_SOURCES_EXCLUDE_START"
_ENV_EXCLUDE_END = "BLEND_VS_SOURCES_EXCLUDE_END"

_COMPLETED_EVENTS_SQL = text(
    """
    SELECT e.id AS event_id,
           e.commence_time AS commence_time,
           e.home_score AS home_score,
           e.away_score AS away_score,
           s.key AS sport_key
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE e.status = 'completed'
      AND e.commence_time >= :min_commence_time
      AND e.commence_time < :max_commence_time
      AND (
          CAST(:exclude_start AS timestamptz) IS NULL
          OR CAST(:exclude_end AS timestamptz) IS NULL
          OR e.commence_time < CAST(:exclude_start AS timestamptz)
          OR e.commence_time >= CAST(:exclude_end AS timestamptz)
      )
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
    ORDER BY e.id
    """
)

# Uses uq_probability_publications_event_rev (event_id, rev) in reverse index
# order per (event_id, horizon cutoff). Selects only lean forecast columns;
# never reads observations or queued_frame JSONB.
_HORIZON_LATERAL_SQL = text(
    """
    SELECT b.event_id AS event_id,
           b.horizon AS horizon,
           p.rev AS rev,
           p.recorded_at AS recorded_at,
           p.sources AS sources,
           p.blend_probability AS blend_probability
    FROM unnest(
        CAST(:event_ids AS bigint[]),
        CAST(:cutoffs AS timestamptz[]),
        CAST(:horizons AS text[])
    ) AS b(event_id, cutoff, horizon)
    CROSS JOIN LATERAL (
        SELECT pp.rev, pp.recorded_at, pp.sources, pp.blend_probability
        FROM probability_publications pp
        WHERE pp.event_id = b.event_id
          AND pp.recorded_at <= b.cutoff
        ORDER BY pp.rev DESC
        LIMIT 1
    ) AS p
    WHERE p.blend_probability IS NOT NULL
    """
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_optional_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return _as_utc(datetime.fromisoformat(stripped))


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def window_overlaps_holdout(
    min_dt: datetime,
    max_dt: datetime,
    *,
    exclude_start: datetime | None = None,
    exclude_end: datetime | None = None,
    holdout_start: datetime | None = None,
    holdout_end: datetime | None = None,
) -> bool:
    """Return True if ``[min_dt, max_dt) \\ [exclude_start, exclude_end)`` overlaps the holdout."""
    lower = _as_utc(min_dt)
    upper = _as_utc(max_dt)
    if upper <= lower:
        return False

    h_start = _as_utc(holdout_start or datetime.fromisoformat(HOLDOUT_START_ISO))
    h_end = _as_utc(holdout_end or datetime.fromisoformat(HOLDOUT_END_ISO))
    if h_end <= h_start:
        return False

    intervals: list[tuple[datetime, datetime]] = [(lower, upper)]
    if exclude_start is not None and exclude_end is not None:
        ex_s = _as_utc(exclude_start)
        ex_e = _as_utc(exclude_end)
        if ex_e > ex_s:
            next_intervals: list[tuple[datetime, datetime]] = []
            for a, b in intervals:
                if ex_e <= a or ex_s >= b:
                    next_intervals.append((a, b))
                else:
                    if a < ex_s:
                        next_intervals.append((a, ex_s))
                    if ex_e < b:
                        next_intervals.append((ex_e, b))
            intervals = next_intervals

    return any(max(a, h_start) < min(b, h_end) for a, b in intervals)


def _build_batch_bind_params(events: list[Any]) -> tuple[dict[str, Any], dict[int, int]]:
    event_ids: list[int] = []
    cutoffs: list[datetime] = []
    horizons: list[str] = []
    outcomes_by_event: dict[int, int] = {}

    for row in events:
        eid = int(row.event_id)
        commence_time = _as_utc(row.commence_time)
        outcomes_by_event[eid] = 1 if int(row.home_score) > int(row.away_score) else 0
        for h_name, offset in HORIZONS:
            event_ids.append(eid)
            cutoffs.append(commence_time - offset)
            horizons.append(h_name)

    return (
        {
            "event_ids": event_ids,
            "cutoffs": cutoffs,
            "horizons": horizons,
        },
        outcomes_by_event,
    )


async def _run_read_only_query(session_factory, sql, params, *, statement_timeout_ms: int):
    async with session_factory() as db:
        if not db.in_transaction():
            await db.begin()
        await db.execute(text("SET LOCAL transaction_read_only = on"))
        await db.execute(
            text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        )
        rows = (await db.execute(sql, params)).all()
        await db.rollback()
        return rows


async def collect_blend_vs_sources_observations(
    session_factory,
    *,
    recording_start: datetime | None = None,
    min_commence_time: datetime | None = None,
    max_commence_time: datetime | None = None,
    exclude_start: datetime | None = None,
    exclude_end: datetime | None = None,
    now_utc: datetime | None = None,
    batch_size: int = 50,
    deadline_s: float = 240.0,
    statement_timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Read completed events + horizon publications read-only in bounded batches."""
    started = time.monotonic()
    lower_bound = _as_utc(
        min_commence_time or recording_start or datetime.fromisoformat(RECORDING_START_ISO)
    )
    now_dt = _as_utc(now_utc or datetime.now(timezone.utc))
    upper_bound = (
        min(now_dt, _as_utc(max_commence_time))
        if max_commence_time is not None
        else now_dt
    )
    if upper_bound <= lower_bound:
        return {
            "complete": True,
            "events_scanned": 0,
            "events_total": 0,
            "observations": [],
        }

    ex_start_dt = _as_utc(exclude_start) if exclude_start is not None else None
    ex_end_dt = _as_utc(exclude_end) if exclude_end is not None else None
    if (
        ex_start_dt is not None
        and ex_end_dt is not None
        and ex_start_dt <= lower_bound
        and ex_end_dt >= upper_bound
    ):
        return {
            "complete": True,
            "events_scanned": 0,
            "events_total": 0,
            "observations": [],
        }

    event_rows = await _run_read_only_query(
        session_factory,
        _COMPLETED_EVENTS_SQL,
        {
            "min_commence_time": lower_bound,
            "max_commence_time": upper_bound,
            "exclude_start": ex_start_dt,
            "exclude_end": ex_end_dt,
        },
        statement_timeout_ms=statement_timeout_ms,
    )

    events_total = len(event_rows)
    observations: list[dict[str, Any]] = []
    events_scanned = 0

    for idx in range(0, events_total, batch_size):
        if time.monotonic() - started >= deadline_s:
            return {
                "complete": False,
                "events_scanned": events_scanned,
                "events_total": events_total,
                "observations": observations,
            }

        batch = event_rows[idx : idx + batch_size]
        params, outcomes_by_event = _build_batch_bind_params(batch)
        pub_rows = await _run_read_only_query(
            session_factory,
            _HORIZON_LATERAL_SQL,
            params,
            statement_timeout_ms=statement_timeout_ms,
        )

        for pub in pub_rows:
            eid = int(pub.event_id)
            observations.append(
                {
                    "event_id": eid,
                    "horizon": str(pub.horizon),
                    "blend_probability": pub.blend_probability,
                    "sources": pub.sources,
                    "outcome": outcomes_by_event[eid],
                }
            )
        events_scanned += len(batch)

    return {
        "complete": True,
        "events_scanned": events_scanned,
        "events_total": events_total,
        "observations": observations,
    }


async def _precompute_blend_vs_sources_calibration(
    *,
    deadline_s: float = 240.0,
    batch_size: int = 50,
    recording_start_iso: str = RECORDING_START_ISO,
    min_commence_time_iso: str | None = None,
    max_commence_time_iso: str | None = None,
    exclude_start_iso: str | None = None,
    exclude_end_iso: str | None = None,
    holdout_released: bool | None = None,
    statement_timeout_ms: int = 10_000,
) -> dict[str, Any]:
    """Precompute and publish Blend vs Contributing Sources calibration to Redis.

    Decision 360 fail-closed holdout guard: while ``holdout_released`` is False
    (default unless ``BLEND_VS_SOURCES_HOLDOUT_RELEASED`` is explicitly enabled)
    and the requested scoring window overlaps ``[HOLDOUT_START_ISO, HOLDOUT_END_ISO)``,
    refuse with zero database queries and zero Redis writes.
    """
    from app.tasks.base import _get_task_engine, get_task_session
    from app.tasks.redis_state import get_redis_client

    now_dt = _as_utc(datetime.now(timezone.utc))
    min_dt = (
        _parse_optional_iso(min_commence_time_iso)
        or _parse_optional_iso(os.environ.get(_ENV_MIN_COMMENCE_TIME))
        or _parse_optional_iso(recording_start_iso)
        or _as_utc(datetime.fromisoformat(RECORDING_START_ISO))
    )
    max_cfg = _parse_optional_iso(max_commence_time_iso) or _parse_optional_iso(
        os.environ.get(_ENV_MAX_COMMENCE_TIME)
    )
    effective_max = min(now_dt, max_cfg) if max_cfg is not None else now_dt
    exclude_start_dt = _parse_optional_iso(exclude_start_iso) or _parse_optional_iso(
        os.environ.get(_ENV_EXCLUDE_START)
    )
    exclude_end_dt = _parse_optional_iso(exclude_end_iso) or _parse_optional_iso(
        os.environ.get(_ENV_EXCLUDE_END)
    )
    released = (
        _env_flag(_ENV_HOLDOUT_RELEASED, default=False)
        if holdout_released is None
        else bool(holdout_released)
    )

    if not released and window_overlaps_holdout(
        min_dt,
        effective_max,
        exclude_start=exclude_start_dt,
        exclude_end=exclude_end_dt,
    ):
        logger.info(
            "blend-vs-sources calibration held before DB read (window [%s, %s) overlaps Decide 44 holdout [%s, %s))",
            min_dt.isoformat(),
            effective_max.isoformat(),
            HOLDOUT_START_ISO,
            HOLDOUT_END_ISO,
        )
        return {
            "status": "held",
            "terminal": "held",
            "published": False,
            "reason": "holdout_window_active",
            "holdout_start": HOLDOUT_START_ISO,
            "holdout_end": HOLDOUT_END_ISO,
            "min_commence_time": min_dt.isoformat(),
            "max_commence_time": effective_max.isoformat(),
        }

    engine = _get_task_engine(statement_timeout_ms=statement_timeout_ms)
    try:
        collection = await collect_blend_vs_sources_observations(
            lambda: get_task_session(engine=engine),
            min_commence_time=min_dt,
            max_commence_time=effective_max,
            exclude_start=exclude_start_dt,
            exclude_end=exclude_end_dt,
            now_utc=now_dt,
            batch_size=batch_size,
            deadline_s=deadline_s,
            statement_timeout_ms=statement_timeout_ms,
        )
    finally:
        await engine.dispose()

    if not collection["complete"]:
        logger.warning(
            "blend-vs-sources calibration hit wall deadline (%d/%d events) — leaving last_good intact",
            collection["events_scanned"],
            collection["events_total"],
        )
        return {
            "status": "partial",
            "terminal": "partial",
            "published": False,
            "events_scanned": collection["events_scanned"],
            "events_total": collection["events_total"],
        }

    scoring_window = {
        "min_commence_time": min_dt.isoformat(),
        "max_commence_time": effective_max.isoformat(),
        "exclude_start": exclude_start_dt.isoformat() if exclude_start_dt is not None else None,
        "exclude_end": exclude_end_dt.isoformat() if exclude_end_dt is not None else None,
        "holdout_released": released,
    }
    payload = build_blend_vs_sources_payload(
        collection["observations"],
        generated_at=now_dt.isoformat(),
        recording_start=min_dt.isoformat(),
        events_scanned=collection["events_scanned"],
        scoring_window=scoring_window,
    )
    raw = json.dumps(payload, default=str)
    rc = get_redis_client()
    rc.set(REDIS_KEY, raw, ex=TTL_S)
    rc.set(LAST_GOOD_KEY, raw, ex=LAST_GOOD_TTL_S)

    horizon_counts = {
        h: h_data.get("n_events", 0)
        for h, h_data in (payload.get("horizons") or {}).items()
    }
    logger.info(
        "Published blend-vs-sources calibration (%d events scanned, horizons=%s)",
        collection["events_scanned"],
        horizon_counts,
    )
    return {
        "status": "complete",
        "terminal": "complete",
        "published": True,
        "events_scanned": collection["events_scanned"],
        "events_total": collection["events_total"],
        "horizons": horizon_counts,
    }
