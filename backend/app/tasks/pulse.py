"""
Pulse (Game Excitement Index) computation tasks.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import Event, OddsSnapshot, Sport
from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


async def update_live_pulse(session) -> int:
    """
    Compute and update Pulse for all currently live events.

    Pulse measures how "alive" a game is based on probability movement.
    Called during each poll cycle to provide real-time excitement scores.
    Returns the number of events updated.
    """
    from app.utils.pulse import calculate_pulse, PulseDataPoint

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

            # Convert to PulseDataPoint objects
            data_points = [
                PulseDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    bookmaker=s.bookmaker,
                )
                for s in snapshots
            ]

            # Calculate Pulse
            sport_key = event.sport.key if event.sport else "unknown"
            pulse_result = calculate_pulse(
                snapshots=data_points,
                game_start=event.commence_time,
                current_time=now,
                sport_key=sport_key,
            )

            if pulse_result:
                # Store Pulse score (1-100) in raw_gei field
                # We divide by 100 to fit the existing decimal field format
                event.raw_gei = pulse_result.score / 100.0
                event.gei_components = pulse_result.components.to_json()
                event.gei_computed_at = now
                updated += 1

        except Exception as e:
            print(f"Error computing Pulse for event {event.id}: {e}")
            continue

    return updated


# Legacy alias for backwards compatibility
async def update_live_gei(session) -> int:
    """Legacy alias - now uses Pulse."""
    return await update_live_pulse(session)


async def _compute_pulse_for_event(event_id: int):
    """Compute Pulse for a single completed event."""
    from app.utils.pulse import calculate_pulse, PulseDataPoint

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

        if event.raw_gei is not None:
            return {"skipped": True, "reason": "Pulse already computed"}

        # Get all snapshots for this event
        result = await session.execute(
            select(OddsSnapshot)
            .where(OddsSnapshot.event_id == event_id)
            .order_by(OddsSnapshot.captured_at)
        )
        snapshots = result.scalars().all()

        if len(snapshots) < 3:
            return {"error": f"Insufficient snapshots ({len(snapshots)}) for Pulse calculation"}

        # Convert to PulseDataPoint objects
        data_points = [
            PulseDataPoint(
                captured_at=s.captured_at,
                home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                bookmaker=s.bookmaker,
            )
            for s in snapshots
        ]

        # Determine game end time (last snapshot)
        game_end = max(s.captured_at for s in snapshots)

        # Calculate Pulse
        sport_key = event.sport.key if event.sport else "unknown"
        pulse_result = calculate_pulse(
            snapshots=data_points,
            game_start=event.commence_time,
            current_time=game_end,
            sport_key=sport_key,
        )

        if pulse_result is None:
            return {"error": "Pulse calculation returned None (insufficient data)"}

        # Don't store unreliable scores for completed events
        if pulse_result.data_quality == "minimal":
            return {
                "event_id": event_id,
                "skipped": True,
                "reason": f"Insufficient aggregated data ({pulse_result.snapshot_count} time buckets, need 10+)",
                "data_quality": pulse_result.data_quality,
            }

        # Update event with Pulse (store score/100 to fit existing field)
        event.raw_gei = pulse_result.score / 100.0
        event.gei_components = pulse_result.components.to_json()
        event.gei_computed_at = datetime.now(timezone.utc)

        await session.commit()

        return {
            "event_id": event_id,
            "pulse_score": pulse_result.score,
            "status": pulse_result.status,
            "data_quality": pulse_result.data_quality,
            "snapshot_count": pulse_result.snapshot_count,
        }


# Legacy alias
async def _compute_gei_for_event(event_id: int):
    """Legacy alias - now uses Pulse."""
    return await _compute_pulse_for_event(event_id)


async def _compute_pulse_batch(limit: int):
    """Compute Pulse for a batch of completed events."""
    from app.utils.pulse import calculate_pulse, PulseDataPoint

    async with get_task_session() as session:
        # Find completed events without Pulse
        result = await session.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status == "completed",
                Event.raw_gei.is_(None),
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

            # Convert to PulseDataPoint objects
            data_points = [
                PulseDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    bookmaker=s.bookmaker,
                )
                for s in snapshots
            ]

            game_end = max(s.captured_at for s in snapshots)
            sport_key = event.sport.key if event.sport else "unknown"

            try:
                pulse_result = calculate_pulse(
                    snapshots=data_points,
                    game_start=event.commence_time,
                    current_time=game_end,
                    sport_key=sport_key,
                )

                if pulse_result and pulse_result.data_quality != "minimal":
                    event.raw_gei = pulse_result.score / 100.0
                    event.gei_components = pulse_result.components.to_json()
                    event.gei_computed_at = datetime.now(timezone.utc)
                    processed += 1
            except Exception as e:
                print(f"Error computing GEI for event {event.id}: {e}")
                errors += 1

        await session.commit()

        return {
            "processed": processed,
            "errors": errors,
            "remaining": len(events) - processed - errors,
        }


async def _compute_gei_percentiles():
    """Async implementation of compute_gei_percentiles."""
    from collections import defaultdict
    from app.models import GEIPercentile

    async with get_task_session() as session:
        # Get all finished events with raw GEI (completed + closed)
        # Exclude events with raw_gei=0 (insufficient data / flatline placeholders)
        result = await session.execute(
            select(Event.raw_gei, Sport.key)
            .join(Sport)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.raw_gei.isnot(None),
                Event.raw_gei > 0,
            )
        )
        events = result.all()

        if not events:
            return {"error": "No events with GEI found"}

        # Group by sport
        by_sport = defaultdict(list)
        all_geis = []

        for raw_gei, sport_key in events:
            gei_value = float(raw_gei)
            by_sport[sport_key].append(gei_value)
            all_geis.append(gei_value)

        # Compute global percentiles
        await _store_percentiles(session, 'global', all_geis)
        scopes_computed = ['global']

        # Compute per-sport percentiles (minimum 30 samples)
        for sport_key, geis in by_sport.items():
            if len(geis) >= 30:
                await _store_percentiles(session, sport_key, geis)
                scopes_computed.append(sport_key)

        await session.commit()

        return {
            "total_events": len(all_geis),
            "scopes_computed": scopes_computed,
            "sports_with_data": list(by_sport.keys()),
        }


async def _store_percentiles(session, scope: str, values: list[float]):
    """Store percentile thresholds for a scope."""
    from app.models import GEIPercentile
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

        stmt = pg_insert(GEIPercentile).values(
            scope=scope,
            percentile=p,
            raw_gei_threshold=threshold,
            sample_size=sample_size,
        ).on_conflict_do_update(
            index_elements=['scope', 'percentile'],
            set_={
                'raw_gei_threshold': threshold,
                'sample_size': sample_size,
                'computed_at': func.now(),
            }
        )
        await session.execute(stmt)
