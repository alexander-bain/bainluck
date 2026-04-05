"""Backfill game state (period markers) for completed events.

Finds completed/closed events with no period data in any source
(ScoringPlay, WinProbSnapshot game_state, ESPNSnapshot) and
reconstructs period boundaries from available data.

Reconstruction strategies (in priority order):
1. ESPN snapshot period field — copy to WinProbSnapshot game_state
2. Score progression — detect score changes to infer period boundaries
3. MLB Stats API linescore — fetch historical inning data (baseball only)
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_, or_, exists, text, literal, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.base import get_task_session
from app.models.models import (
    Event,
    Sport,
    WinProbSnapshot,
    ScoringPlay,
)

logger = logging.getLogger(__name__)

# Sports where we know the period structure
SPORT_PERIOD_NAMES = {
    "basketball_nba": ["Q1", "Q2", "Q3", "Q4"],
    "basketball_ncaab": ["1st Half", "2nd Half"],
    "basketball_wncaab": ["Q1", "Q2", "Q3", "Q4"],
    "basketball_wnba": ["Q1", "Q2", "Q3", "Q4"],
    "americanfootball_nfl": ["Q1", "Q2", "Q3", "Q4"],
    "americanfootball_ncaaf": ["Q1", "Q2", "Q3", "Q4"],
    "icehockey_nhl": ["1st Period", "2nd Period", "3rd Period"],
}


async def _backfill_game_state(
    limit: int = 500,
    sport_filter: str | None = None,
    batch_size: int = 100,
) -> dict:
    """Backfill missing period markers for completed events.

    Processes events in batches. For each event missing period data,
    tries to reconstruct from existing DB data.

    Args:
        limit: Max events to process per run.
        sport_filter: Optional sport key prefix (e.g., "baseball" or "basketball_nba").
        batch_size: DB commit batch size.

    Returns:
        Stats dict with counts.
    """
    stats = {
        "scanned": 0,
        "already_has_data": 0,
        "fixed_from_espn": 0,
        "fixed_from_scores": 0,
        "unfixable": 0,
        "errors": 0,
    }

    async with get_task_session() as session:
        # Find completed events that have NO period data in ScoringPlay.
        # We check ScoringPlay as the "ground truth" source because it's
        # what the history endpoint checks first.
        has_scoring_play_period = (
            select(literal(1))
            .where(
                ScoringPlay.event_id == Event.id,
                ScoringPlay.period.isnot(None),
                ScoringPlay.period != "",
            )
            .correlate(Event)
            .exists()
        )

        query = (
            select(Event)
            .join(Sport, Event.sport_id == Sport.id)
            .options()
            .where(
                Event.status.in_(["completed", "closed"]),
                ~has_scoring_play_period,
            )
            .order_by(Event.commence_time.desc())
            .limit(limit)
        )

        if sport_filter:
            query = query.where(Sport.key.like(f"{sport_filter}%"))

        result = await session.execute(query)
        events = result.scalars().all()
        stats["scanned"] = len(events)
        logger.info(f"Game state backfill: found {len(events)} events to check")

        fixed_count = 0

        for event in events:
            try:
                fixed = await _try_fix_event(session, event)
                if fixed == "espn":
                    stats["fixed_from_espn"] += 1
                    fixed_count += 1
                elif fixed == "scores":
                    stats["fixed_from_scores"] += 1
                    fixed_count += 1
                elif fixed == "has_data":
                    stats["already_has_data"] += 1
                else:
                    stats["unfixable"] += 1

                # Batch commits
                if fixed_count > 0 and fixed_count % batch_size == 0:
                    await session.commit()
                    logger.info(f"Game state backfill: committed batch ({fixed_count} fixed so far)")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Game state backfill error for event {event.id}: {e}")
                # CRITICAL: rollback so the poisoned transaction doesn't
                # cascade failures to all subsequent events.
                await session.rollback()

        if fixed_count > 0:
            await session.commit()

    logger.info(
        f"Game state backfill complete: scanned={stats['scanned']}, "
        f"fixed_espn={stats['fixed_from_espn']}, "
        f"fixed_scores={stats['fixed_from_scores']}, "
        f"already_had={stats['already_has_data']}, "
        f"unfixable={stats['unfixable']}, errors={stats['errors']}"
    )
    return stats


async def _try_fix_event(session: AsyncSession, event: Event) -> str:
    """Try to reconstruct period markers for one event.

    Returns: "espn", "scores", "has_data", or "none".
    """
    event_id = event.id

    # 1. Check if WinProbSnapshot already has game_state with period data.
    #    If so, the history endpoint's third fallback will pick it up.
    #    Use safe JSONB checks: period key exists and is non-empty, OR
    #    inning key exists (any truthy value — avoids unsafe integer cast).
    wp_with_period = await session.execute(
        select(func.count())
        .select_from(WinProbSnapshot)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.game_state.isnot(None),
            or_(
                and_(
                    WinProbSnapshot.game_state.has_key("period"),
                    WinProbSnapshot.game_state["period"].astext != "",
                    WinProbSnapshot.game_state["period"].astext != "null",
                ),
                WinProbSnapshot.game_state.has_key("inning"),
            ),
        )
    )
    wp_period_count = wp_with_period.scalar() or 0
    if wp_period_count >= 2:
        return "has_data"

    # 2. Check ESPNSnapshot for period data — copy to WinProbSnapshot game_state
    try:
        from app.models.models import ESPNSnapshot
        espn_result = await session.execute(
            select(ESPNSnapshot)
            .where(
                ESPNSnapshot.event_id == event_id,
                ESPNSnapshot.period.isnot(None),
                ESPNSnapshot.period != "",
                ESPNSnapshot.period != "Final",
            )
            .order_by(ESPNSnapshot.captured_at)
        )
        espn_snaps = espn_result.scalars().all()

        # Filter out pre-game date strings in Python (safer than SQL regex)
        _DATE_RE = re.compile(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)",
            re.IGNORECASE,
        )
        espn_snaps = [s for s in espn_snaps if not _DATE_RE.search(s.period)]

        if espn_snaps:
            # Group by period, take first timestamp per period
            seen_periods: dict[str, datetime] = {}
            for snap in espn_snaps:
                period = snap.period.strip()
                if period and period not in seen_periods:
                    seen_periods[period] = snap.captured_at

            if len(seen_periods) >= 2:
                # Write synthetic WinProbSnapshot entries with game_state
                for period, ts in seen_periods.items():
                    # Check if one already exists at this timestamp
                    existing = await session.execute(
                        select(func.count())
                        .select_from(WinProbSnapshot)
                        .where(
                            WinProbSnapshot.event_id == event_id,
                            WinProbSnapshot.source == "espn",
                            WinProbSnapshot.captured_at == ts,
                        )
                    )
                    if (existing.scalar() or 0) > 0:
                        # Update existing snapshot's game_state
                        await session.execute(
                            WinProbSnapshot.__table__.update()
                            .where(
                                WinProbSnapshot.event_id == event_id,
                                WinProbSnapshot.source == "espn",
                                WinProbSnapshot.captured_at == ts,
                            )
                            .values(game_state={"period": period, "backfilled": True})
                        )
                    else:
                        # Create new snapshot with just game_state
                        session.add(WinProbSnapshot(
                            event_id=event_id,
                            source="espn",
                            captured_at=ts,
                            game_state={"period": period, "backfilled": True},
                        ))

                return "espn"
    except Exception as e:
        logger.debug(f"ESPN backfill failed for event {event_id}: {e}")

    # 3. Reconstruct from score progression in WinProbSnapshot game_state
    #    (score changes across snapshots imply period progression)
    try:
        wp_result = await session.execute(
            select(WinProbSnapshot)
            .where(
                WinProbSnapshot.event_id == event_id,
                WinProbSnapshot.game_state.isnot(None),
            )
            .order_by(WinProbSnapshot.captured_at)
        )
        wp_snaps = wp_result.scalars().all()

        if len(wp_snaps) >= 4:
            # Track score changes — each unique (home_score, away_score) step
            # with a timestamp gives us approximate period boundaries
            score_transitions: list[dict] = []
            prev_home = None
            prev_away = None

            for snap in wp_snaps:
                gs = snap.game_state or {}
                home = gs.get("home_score")
                away = gs.get("away_score")
                if home is None or away is None:
                    continue

                if home != prev_home or away != prev_away:
                    score_transitions.append({
                        "timestamp": snap.captured_at,
                        "home_score": home,
                        "away_score": away,
                    })
                    prev_home = home
                    prev_away = away

            # Get sport key for period structure
            sport_key = None
            if event.sport_id:
                sport_result = await session.execute(
                    select(Sport.key).where(Sport.id == event.sport_id)
                )
                sport_key = sport_result.scalar()

            period_names = SPORT_PERIOD_NAMES.get(sport_key or "")

            if period_names and score_transitions:
                # Divide game timeline into equal segments for each period
                if len(score_transitions) >= 2:
                    first_ts = score_transitions[0]["timestamp"]
                    last_ts = score_transitions[-1]["timestamp"]
                    total_duration = (last_ts - first_ts).total_seconds()

                    if total_duration > 0:
                        n_periods = len(period_names)
                        period_duration = total_duration / n_periods

                        for i, pname in enumerate(period_names):
                            period_ts = first_ts + timedelta(
                                seconds=period_duration * i
                            )
                            # Find the nearest score transition to this time
                            best_snap = min(
                                score_transitions,
                                key=lambda s: abs((s["timestamp"] - period_ts).total_seconds()),
                            )
                            session.add(WinProbSnapshot(
                                event_id=event_id,
                                source="backfill",
                                captured_at=best_snap["timestamp"],
                                game_state={"period": pname, "backfilled": True},
                            ))

                        return "scores"
    except Exception as e:
        logger.debug(f"Score-based backfill failed for event {event_id}: {e}")

    return "none"
