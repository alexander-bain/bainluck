"""
Excitement Index (EI) computation tasks.

Replaces the old Pulse tasks with the standard GEI formula:
  EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import Event, OddsSnapshot, Sport
from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


async def update_live_ei(session) -> int:
    """
    Compute and update EI for all currently live events.

    Returns the number of events updated.
    """
    from app.utils.excitement_index import calculate_ei, EIDataPoint

    # Get all live events
    result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(Event.status == "live")
    )
    live_events = result.scalars().all()

    if not live_events:
        return 0

    updated = 0
    now = datetime.now(timezone.utc)

    for event in live_events:
        try:
            # Get all snapshots for this event
            result = await session.execute(
                select(OddsSnapshot)
                .where(OddsSnapshot.event_id == event.id)
                .order_by(OddsSnapshot.captured_at)
            )
            snapshots = result.scalars().all()

            if len(snapshots) < 3:
                continue

            # Convert to EIDataPoint objects
            data_points = [
                EIDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    source=s.bookmaker,
                )
                for s in snapshots
            ]

            # Calculate EI
            sport_key = event.sport.key if event.sport else "unknown"
            ei_result = calculate_ei(
                snapshots=data_points,
                game_start=event.commence_time,
                current_time=now,
                sport_key=sport_key,
            )

            if ei_result:
                # Store EI score (1-100) in raw_ei field
                # We divide by 100 to fit the existing decimal field format
                event.raw_ei = ei_result.score / 100.0
                event.ei_metadata = ei_result.metadata.to_json()
                event.ei_computed_at = now
                updated += 1

        except Exception as e:
            logger.error(f"Error computing EI for event {event.id}: {e}")
            continue

    return updated


# Legacy aliases
async def update_live_pulse(session) -> int:
    """Legacy alias — now uses EI."""
    return await update_live_ei(session)

async def update_live_gei(session) -> int:
    """Legacy alias — now uses EI."""
    return await update_live_ei(session)


async def _compute_ei_for_event(event_id: int):
    """Compute EI for a single completed event."""
    from app.utils.excitement_index import calculate_ei, EIDataPoint

    async with get_task_session() as session:
        # Get the event with its sport
        result = await session.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(Event.id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event:
            return {"error": f"Event {event_id} not found"}

        if event.status != "completed":
            return {"error": f"Event {event_id} is not completed (status: {event.status})"}

        if event.raw_ei is not None:
            return {"skipped": True, "reason": "EI already computed"}

        # Get all snapshots for this event
        result = await session.execute(
            select(OddsSnapshot)
            .where(OddsSnapshot.event_id == event_id)
            .order_by(OddsSnapshot.captured_at)
        )
        snapshots = result.scalars().all()

        if len(snapshots) < 3:
            return {"error": f"Insufficient snapshots ({len(snapshots)}) for EI calculation"}

        # Convert to EIDataPoint objects
        data_points = [
            EIDataPoint(
                captured_at=s.captured_at,
                home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                source=s.bookmaker,
            )
            for s in snapshots
        ]

        # Determine game end time (last snapshot)
        game_end = max(s.captured_at for s in snapshots)

        # Calculate EI
        sport_key = event.sport.key if event.sport else "unknown"
        ei_result = calculate_ei(
            snapshots=data_points,
            game_start=event.commence_time,
            current_time=game_end,
            sport_key=sport_key,
        )

        if ei_result is None:
            return {"error": "EI calculation returned None (insufficient data)"}

        # Don't store unreliable scores for completed events
        if ei_result.data_quality == "minimal":
            return {
                "event_id": event_id,
                "skipped": True,
                "reason": f"Insufficient aggregated data ({ei_result.metadata.snapshot_count} time buckets, need 10+)",
                "data_quality": ei_result.data_quality,
            }

        # Update event with EI (store score/100 to fit existing field)
        event.raw_ei = ei_result.score / 100.0
        event.ei_metadata = ei_result.metadata.to_json()
        event.ei_computed_at = datetime.now(timezone.utc)

        await session.commit()

        return {
            "event_id": event_id,
            "ei_score": ei_result.score,
            "raw_ei": round(ei_result.raw_ei, 4),
            "status": get_ei_status_label(ei_result.score),
            "data_quality": ei_result.data_quality,
            "snapshot_count": ei_result.metadata.snapshot_count,
        }


def get_ei_status_label(score: int) -> str:
    """Quick status label for task result output."""
    from app.utils.excitement_index import get_ei_status
    return get_ei_status(score)


# Legacy aliases
_compute_pulse_for_event = _compute_ei_for_event
_compute_gei_for_event = _compute_ei_for_event


async def _compute_ei_batch(limit: int):
    """Compute EI for a batch of completed events."""
    from app.utils.excitement_index import calculate_ei, EIDataPoint

    async with get_task_session() as session:
        # Find completed events without EI
        result = await session.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status == "completed",
                Event.raw_ei.is_(None),
            )
            .order_by(Event.commence_time.desc())
            .limit(limit)
        )
        events = result.scalars().all()

        if not events:
            return {"processed": 0, "message": "No events to process"}

        processed = 0
        errors = 0

        for event in events:
            # Get snapshots for this event
            result = await session.execute(
                select(OddsSnapshot)
                .where(OddsSnapshot.event_id == event.id)
                .order_by(OddsSnapshot.captured_at)
            )
            snapshots = result.scalars().all()

            if len(snapshots) < 3:
                continue

            # Convert to EIDataPoint objects
            data_points = [
                EIDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    source=s.bookmaker,
                )
                for s in snapshots
            ]

            game_end = max(s.captured_at for s in snapshots)
            sport_key = event.sport.key if event.sport else "unknown"

            try:
                ei_result = calculate_ei(
                    snapshots=data_points,
                    game_start=event.commence_time,
                    current_time=game_end,
                    sport_key=sport_key,
                )

                if ei_result and ei_result.data_quality != "minimal":
                    event.raw_ei = ei_result.score / 100.0
                    event.ei_metadata = ei_result.metadata.to_json()
                    event.ei_computed_at = datetime.now(timezone.utc)
                    processed += 1
            except Exception as e:
                logger.error(f"Error computing EI for event {event.id}: {e}")
                errors += 1

        await session.commit()

        return {
            "processed": processed,
            "errors": errors,
            "remaining": len(events) - processed - errors,
        }


# Legacy alias
_compute_pulse_batch = _compute_ei_batch


async def _compute_ei_percentiles():
    """Compute EI percentile thresholds for percentile-based scoring."""
    from collections import defaultdict
    from app.models import EIPercentile

    async with get_task_session() as session:
        # Get all finished events with raw EI (completed + closed)
        # Exclude events with raw_ei=0 (insufficient data / flatline placeholders)
        result = await session.execute(
            select(Event.raw_ei, Sport.key)
            .join(Sport)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.raw_ei.isnot(None),
                Event.raw_ei > 0,
            )
        )
        events = result.all()

        if not events:
            return {"error": "No events with EI found"}

        # Group by sport
        by_sport = defaultdict(list)
        all_eis = []

        for raw_ei, sport_key in events:
            ei_value = float(raw_ei)
            by_sport[sport_key].append(ei_value)
            all_eis.append(ei_value)

        # Compute global percentiles
        await _store_percentiles(session, 'global', all_eis)
        scopes_computed = ['global']

        # Compute per-sport percentiles (minimum 30 samples)
        for sport_key, eis in by_sport.items():
            if len(eis) >= 30:
                await _store_percentiles(session, sport_key, eis)
                scopes_computed.append(sport_key)

        await session.commit()

        return {
            "total_events": len(all_eis),
            "scopes_computed": scopes_computed,
            "sports_with_data": list(by_sport.keys()),
        }


# Legacy alias
_compute_gei_percentiles = _compute_ei_percentiles


async def _store_percentiles(session, scope: str, values: list[float]):
    """Store percentile thresholds for a scope."""
    from app.models import EIPercentile
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if not values:
        return

    values = sorted(values)
    sample_size = len(values)

    for p in range(1, 101):
        # Calculate percentile value
        idx = (p / 100) * (len(values) - 1)
        lower_idx = int(idx)
        upper_idx = min(lower_idx + 1, len(values) - 1)
        fraction = idx - lower_idx

        if lower_idx == upper_idx:
            threshold = values[lower_idx]
        else:
            threshold = values[lower_idx] * (1 - fraction) + values[upper_idx] * fraction

        stmt = pg_insert(EIPercentile).values(
            scope=scope,
            percentile=p,
            raw_ei_threshold=threshold,
            sample_size=sample_size,
        ).on_conflict_do_update(
            index_elements=['scope', 'percentile'],
            set_={
                'raw_ei_threshold': threshold,
                'sample_size': sample_size,
                'computed_at': func.now(),
            }
        )
        await session.execute(stmt)
