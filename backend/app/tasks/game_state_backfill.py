"""Backfill game state (period markers) for completed events.

Finds completed/closed events with no period data in any source
(ScoringPlay, WinProbSnapshot game_state, ESPNSnapshot) and
reconstructs period boundaries from available data.

Reconstruction strategies (in priority order):
1. ESPN snapshot period field — copy to WinProbSnapshot game_state
2. Score progression — detect score changes to infer period boundaries
3. Timeline division — divide game timeline (from any data source) into
   sport-appropriate periods using known period structure
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
    OddsSnapshot,
)

logger = logging.getLogger(__name__)

# Sports where we know the period structure and typical real-time duration.
# duration_minutes is wall-clock time (includes timeouts, halftime, etc.)
SPORT_PERIODS = {
    "basketball_nba": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 150,
        # Proportional timing: Q1 ends ~25%, halftime ~50%, Q3 ends ~72%, game ends ~100%
        "splits": [0.0, 0.25, 0.50, 0.72],
    },
    "basketball_ncaab": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 120,
        "splits": [0.0, 0.50],
    },
    "basketball_wncaab": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 130,
        "splits": [0.0, 0.25, 0.50, 0.72],
    },
    "basketball_wnba": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 130,
        "splits": [0.0, 0.25, 0.50, 0.72],
    },
    "americanfootball_nfl": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 190,
        "splits": [0.0, 0.25, 0.52, 0.72],  # Halftime is longer in NFL
    },
    "americanfootball_ncaaf": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 200,
        "splits": [0.0, 0.25, 0.52, 0.72],
    },
    "icehockey_nhl": {
        "names": ["1st Period", "2nd Period", "3rd Period"],
        "duration_minutes": 150,
        "splits": [0.0, 0.36, 0.68],  # Intermissions between periods
    },
    "baseball_mlb": {
        "names": ["Top 1st", "Top 2nd", "Top 3rd", "Top 4th", "Top 5th",
                   "Top 6th", "Top 7th", "Top 8th", "Top 9th"],
        "duration_minutes": 180,
        "splits": [0.0, 0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88],
    },
    "baseball_mlb_preseason": {
        "names": ["Top 1st", "Top 2nd", "Top 3rd", "Top 4th", "Top 5th",
                   "Top 6th", "Top 7th", "Top 8th", "Top 9th"],
        "duration_minutes": 180,
        "splits": [0.0, 0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88],
    },
    "soccer_epl": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_spain_la_liga": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_uefa_champs_league": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_germany_bundesliga": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_italy_serie_a": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_france_ligue_one": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "soccer_usa_mls": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
}

# Fallback: for sports not in the map, try to infer from prefix
SPORT_PREFIX_PERIODS = {
    "basketball": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 140,
        "splits": [0.0, 0.25, 0.50, 0.72],
    },
    "americanfootball": {
        "names": ["Q1", "Q2", "Q3", "Q4"],
        "duration_minutes": 190,
        "splits": [0.0, 0.25, 0.52, 0.72],
    },
    "icehockey": {
        "names": ["1st Period", "2nd Period", "3rd Period"],
        "duration_minutes": 150,
        "splits": [0.0, 0.36, 0.68],
    },
    "soccer": {
        "names": ["1st Half", "2nd Half"],
        "duration_minutes": 115,
        "splits": [0.0, 0.50],
    },
    "baseball": {
        "names": ["Top 1st", "Top 2nd", "Top 3rd", "Top 4th", "Top 5th",
                   "Top 6th", "Top 7th", "Top 8th", "Top 9th"],
        "duration_minutes": 180,
        "splits": [0.0, 0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88],
    },
}


def _get_period_config(sport_key: str) -> dict | None:
    """Get period configuration for a sport key, with prefix fallback."""
    if sport_key in SPORT_PERIODS:
        return SPORT_PERIODS[sport_key]
    # Try prefix match
    prefix = sport_key.split("_")[0] if "_" in sport_key else sport_key
    return SPORT_PREFIX_PERIODS.get(prefix)


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
        "fixed_from_timeline": 0,
        "unfixable": 0,
        "errors": 0,
    }

    async with get_task_session() as session:
        # Find completed events that have NO period data in ScoringPlay.
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
                elif fixed == "timeline":
                    stats["fixed_from_timeline"] += 1
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
                await session.rollback()

        if fixed_count > 0:
            await session.commit()

    logger.info(
        f"Game state backfill complete: scanned={stats['scanned']}, "
        f"fixed_espn={stats['fixed_from_espn']}, "
        f"fixed_scores={stats['fixed_from_scores']}, "
        f"fixed_timeline={stats['fixed_from_timeline']}, "
        f"already_had={stats['already_has_data']}, "
        f"unfixable={stats['unfixable']}, errors={stats['errors']}"
    )
    return stats


async def _try_fix_event(session: AsyncSession, event: Event) -> str:
    """Try to reconstruct period markers for one event.

    Returns: "espn", "scores", "timeline", "has_data", or "none".
    """
    event_id = event.id

    # 1. Check if WinProbSnapshot already has game_state with period data.
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

    # Get sport key (needed by all strategies below)
    sport_key = None
    if event.sport_id:
        sport_result = await session.execute(
            select(Sport.key).where(Sport.id == event.sport_id)
        )
        sport_key = sport_result.scalar()

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

        # Filter out pre-game date strings in Python
        _DATE_RE = re.compile(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)",
            re.IGNORECASE,
        )
        espn_snaps = [s for s in espn_snaps if not _DATE_RE.search(s.period)]

        if espn_snaps:
            seen_periods: dict[str, datetime] = {}
            for snap in espn_snaps:
                period = snap.period.strip()
                if period and period not in seen_periods:
                    seen_periods[period] = snap.captured_at

            if len(seen_periods) >= 2:
                for period, ts in seen_periods.items():
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
                        session.add(WinProbSnapshot(
                            event_id=event_id,
                            source="espn",
                            captured_at=ts,
                            game_state={"period": period, "backfilled": True},
                        ))
                return "espn"
    except Exception as e:
        logger.debug(f"ESPN backfill failed for event {event_id}: {e}")

    # 3. Timeline division — use ANY available timestamp source to determine
    #    game start/end, then place period markers at sport-appropriate proportions.
    #    This is the broadest strategy: works for any event with odds data.
    period_config = _get_period_config(sport_key or "")
    if not period_config:
        return "none"

    try:
        # Determine game timeline from multiple sources (most to least reliable)
        game_start = event.commence_time
        game_end = None

        # Source A: Last odds snapshot timestamp (most common data source)
        last_odds = await session.execute(
            select(func.max(OddsSnapshot.captured_at))
            .where(OddsSnapshot.event_id == event_id)
        )
        odds_end = last_odds.scalar()

        # Source B: Last win prob snapshot timestamp
        last_wp = await session.execute(
            select(func.max(WinProbSnapshot.captured_at))
            .where(WinProbSnapshot.event_id == event_id)
        )
        wp_end = last_wp.scalar()

        # Source C: Last ESPN snapshot timestamp
        try:
            from app.models.models import ESPNSnapshot
            last_espn = await session.execute(
                select(func.max(ESPNSnapshot.captured_at))
                .where(ESPNSnapshot.event_id == event_id)
            )
            espn_end = last_espn.scalar()
        except Exception:
            espn_end = None

        # Source D: Last score snapshot timestamp
        try:
            from app.models.models import ScoreSnapshot
            last_score = await session.execute(
                select(func.max(ScoreSnapshot.captured_at))
                .where(ScoreSnapshot.event_id == event_id)
            )
            score_end = last_score.scalar()
        except Exception:
            score_end = None

        # Pick the latest end time from all sources
        candidates = [t for t in [odds_end, wp_end, espn_end, score_end] if t is not None]
        if not candidates:
            return "none"  # No data at all

        game_end = max(candidates)

        # Sanity: game must have lasted at least 30 minutes
        if game_start is None:
            return "none"
        duration = (game_end - game_start).total_seconds()
        if duration < 1800:  # 30 min minimum
            return "none"

        # Cap duration at expected max (e.g., don't let stale bookmaker data
        # from 20 min after the game stretch the timeline)
        expected_duration = period_config["duration_minutes"] * 60
        max_duration = expected_duration * 1.4  # 40% buffer for OT, delays
        if duration > max_duration:
            # Clip game_end to expected duration
            game_end = game_start + timedelta(seconds=expected_duration)
            duration = expected_duration

        # Place period markers at proportional splits
        period_names = period_config["names"]
        splits = period_config["splits"]

        for i, (pname, split_frac) in enumerate(zip(period_names, splits)):
            marker_ts = game_start + timedelta(seconds=duration * split_frac)
            session.add(WinProbSnapshot(
                event_id=event_id,
                source="backfill",
                captured_at=marker_ts,
                game_state={"period": pname, "backfilled": True},
            ))

        return "timeline"

    except Exception as e:
        logger.debug(f"Timeline backfill failed for event {event_id}: {e}")

    return "none"
