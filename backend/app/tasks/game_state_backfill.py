"""Backfill game state (period markers) for completed events.

Finds completed/closed events with no period data in any source
(ScoringPlay, WinProbSnapshot game_state, ESPNSnapshot) and
reconstructs period boundaries from real data.

Reconstruction strategies (in priority order):
1. Event.box_score_data scoring_plays — already stored, has period numbers
2. ESPN API fetch — call /summary for events with espn_id, get scoring_plays
3. ESPN snapshot period field — copy existing period data to game_state
4. Score snapshots + ESPN snapshots — match score changes to period transitions
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, literal
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


async def _backfill_game_state(
    limit: int = 500,
    sport_filter: str | None = None,
    batch_size: int = 50,
) -> dict:
    """Backfill missing period markers for completed events.

    Returns stats dict with counts.
    """
    stats = {
        "scanned": 0,
        "already_has_data": 0,
        "fixed_from_boxscore": 0,
        "fixed_from_espn_fetch": 0,
        "fixed_from_espn_snaps": 0,
        "fixed_start_end": 0,
        "unfixable": 0,
        "errors": 0,
        "error_samples": [],
        # Diagnostics
        "had_espn_id": 0,
        "had_box_score_data": 0,
    }

    async with get_task_session() as session:
        # Find completed events missing period data in ScoringPlay table.
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
            .where(
                Event.status.in_(["completed", "closed"]),
                ~has_scoring_play_period,
                # Skip prediction market stub events — these are auto-created
                # shells with no real game data. They don't have charts.
                or_(
                    Event.external_id.is_(None),
                    ~Event.external_id.like("pm_%"),
                ),
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
            if event.espn_id:
                stats["had_espn_id"] += 1
            if event.box_score_data:
                stats["had_box_score_data"] += 1
            try:
                fixed = await _try_fix_event(session, event)
                if fixed == "boxscore":
                    stats["fixed_from_boxscore"] += 1
                    fixed_count += 1
                elif fixed == "espn_fetch":
                    stats["fixed_from_espn_fetch"] += 1
                    fixed_count += 1
                elif fixed == "espn_snaps":
                    stats["fixed_from_espn_snaps"] += 1
                    fixed_count += 1
                elif fixed == "start_end":
                    stats["fixed_start_end"] += 1
                    fixed_count += 1
                elif fixed == "has_data":
                    stats["already_has_data"] += 1
                else:
                    stats["unfixable"] += 1

                if fixed_count > 0 and fixed_count % batch_size == 0:
                    await session.commit()
                    logger.info(f"Game state backfill: committed batch ({fixed_count} fixed)")

            except Exception as e:
                stats["errors"] += 1
                if len(stats["error_samples"]) < 5:
                    stats["error_samples"].append(f"event {event.id}: {str(e)[:200]}")
                logger.error(f"Game state backfill error for event {event.id}: {e}")
                await session.rollback()

        if fixed_count > 0:
            await session.commit()

    logger.info(f"Game state backfill complete: {stats}")
    return stats


async def _try_fix_event(session: AsyncSession, event: Event) -> str:
    """Try to reconstruct period markers for one event.

    Returns: "boxscore", "espn_fetch", "espn_snaps", "has_data", or "none".
    """
    event_id = event.id

    # 0. Check if WinProbSnapshot already has real period data.
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
                    WinProbSnapshot.game_state["period"].astext != "Final",
                ),
                WinProbSnapshot.game_state.has_key("inning"),
            ),
        )
    )
    if (wp_with_period.scalar() or 0) >= 2:
        return "has_data"

    # Get sport key
    sport_key = None
    if event.sport_id:
        sport_result = await session.execute(
            select(Sport.key).where(Sport.id == event.sport_id)
        )
        sport_key = sport_result.scalar()

    # Build a timestamp lookup from all available snapshot sources.
    # Maps (home_score, away_score) → earliest wall-clock timestamp.
    score_timestamps = await _build_score_timestamp_map(session, event_id)

    # 1. Try Event.box_score_data (already stored from previous backfills)
    box_score_plays = (event.box_score_data or {}).get("scoring_plays", [])
    if box_score_plays:
        periods_written = _write_periods_from_scoring_plays(
            session, event_id, box_score_plays, score_timestamps, event.commence_time,
        )
        if periods_written >= 2:
            return "boxscore"

    # 2. Try fetching from ESPN API (if we have espn_id)
    if event.espn_id and sport_key:
        periods_written = await _fetch_and_write_espn_periods(
            session, event, sport_key, score_timestamps,
        )
        if periods_written >= 2:
            return "espn_fetch"

    # 3. Try existing ESPN snapshot period data
    periods_written = await _copy_espn_snapshot_periods(session, event_id)
    if periods_written >= 2:
        return "espn_snaps"

    # 4. Final fallback: write "Start" and "Final" markers using real timestamps.
    #    commence_time for start, latest data point for end.
    #    Not as useful as period-level granularity, but gives the chart
    #    anchoring context rather than nothing.
    wrote_start_end = await _write_start_end_markers(session, event)
    if wrote_start_end:
        return "start_end"

    return "none"


async def _build_score_timestamp_map(
    session: AsyncSession, event_id: int
) -> dict[tuple[int, int], datetime]:
    """Build a map of (home_score, away_score) → earliest wall-clock timestamp.

    Combines ESPN snapshots, score snapshots, and win_prob game_state to get
    the best possible timestamp for each score state.
    """
    score_map: dict[tuple[int, int], datetime] = {}

    def _record(home: int, away: int, ts: datetime):
        key = (home, away)
        if key not in score_map or ts < score_map[key]:
            score_map[key] = ts

    # Source 1: ESPN snapshots (most reliable — 60s frequency with scores)
    try:
        from app.models.models import ESPNSnapshot
        espn_result = await session.execute(
            select(ESPNSnapshot.home_score, ESPNSnapshot.away_score, ESPNSnapshot.captured_at)
            .where(ESPNSnapshot.event_id == event_id)
            .order_by(ESPNSnapshot.captured_at)
        )
        for row in espn_result.all():
            if row.home_score is not None and row.away_score is not None:
                _record(int(row.home_score), int(row.away_score), row.captured_at)
    except Exception:
        pass

    # Source 2: Score snapshots
    try:
        from app.models.models import ScoreSnapshot
        score_result = await session.execute(
            select(ScoreSnapshot.home_score, ScoreSnapshot.away_score, ScoreSnapshot.captured_at)
            .where(ScoreSnapshot.event_id == event_id)
            .order_by(ScoreSnapshot.captured_at)
        )
        for row in score_result.all():
            if row.home_score is not None and row.away_score is not None:
                _record(int(row.home_score), int(row.away_score), row.captured_at)
    except Exception:
        pass

    # Source 3: WinProbSnapshot game_state with scores
    wp_result = await session.execute(
        select(WinProbSnapshot.game_state, WinProbSnapshot.captured_at)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.game_state.isnot(None),
        )
        .order_by(WinProbSnapshot.captured_at)
    )
    for row in wp_result.all():
        gs = row.game_state or {}
        hs = gs.get("home_score")
        aws = gs.get("away_score")
        if hs is not None and aws is not None:
            _record(int(hs), int(aws), row.captured_at)

    return score_map


def _write_periods_from_scoring_plays(
    session: AsyncSession,
    event_id: int,
    scoring_plays: list[dict],
    score_timestamps: dict[tuple[int, int], datetime],
    commence_time: Optional[datetime],
) -> int:
    """Extract distinct periods from ESPN scoring plays and write as WinProbSnapshot.

    Maps each period to a wall-clock timestamp by matching post-play scores
    to our score_timestamp map. Returns number of periods written.
    """
    # Group plays by period, find the first score in each period
    period_first_score: dict[int, tuple[int, int]] = {}
    for play in scoring_plays:
        period = play.get("period")
        if period is None:
            continue
        period = int(period)
        if period not in period_first_score:
            hs = play.get("home_score")
            aws = play.get("away_score")
            if hs is not None and aws is not None:
                period_first_score[period] = (int(hs), int(aws))

    if not period_first_score:
        return 0

    # Map periods to timestamps
    period_timestamps: dict[int, datetime] = {}
    for period_num, (hs, aws) in sorted(period_first_score.items()):
        ts = score_timestamps.get((hs, aws))
        if ts:
            period_timestamps[period_num] = ts

    # For period 1, use commence_time if no score match
    if 1 not in period_timestamps and commence_time:
        period_timestamps[1] = commence_time

    # Also try: for periods without a direct score match, find the closest
    # score_timestamp between the previous and next period timestamps
    sorted_periods = sorted(period_first_score.keys())
    for period_num in sorted_periods:
        if period_num in period_timestamps:
            continue
        # Find bracketing timestamps
        prev_ts = None
        next_ts = None
        for p in sorted_periods:
            if p < period_num and p in period_timestamps:
                prev_ts = period_timestamps[p]
            if p > period_num and p in period_timestamps and next_ts is None:
                next_ts = period_timestamps[p]
        # Use midpoint of bracket as estimate
        if prev_ts and next_ts:
            mid = prev_ts + (next_ts - prev_ts) / 2
            period_timestamps[period_num] = mid
        elif prev_ts:
            # Estimate based on average period duration from known data
            known = sorted(period_timestamps.items())
            if len(known) >= 2:
                avg_gap = sum(
                    (known[i+1][1] - known[i][1]).total_seconds()
                    for i in range(len(known)-1)
                ) / (len(known) - 1)
                period_timestamps[period_num] = prev_ts + timedelta(seconds=avg_gap)

    # If we have period numbers from scoring plays but couldn't map most
    # to timestamps (sparse score_timestamps), space them evenly between
    # the timestamps we do have (or between commence_time and last known).
    if len(period_timestamps) < 2 and len(period_first_score) >= 2 and commence_time:
        # Use all available timestamp sources for game end estimate
        all_known_ts = list(period_timestamps.values()) if period_timestamps else [commence_time]
        game_start = commence_time
        # Estimate end: last known timestamp or commence + 2.5 hours
        game_end = max(all_known_ts) if all_known_ts else game_start
        if (game_end - game_start).total_seconds() < 3600:
            game_end = game_start + timedelta(hours=2, minutes=30)

        duration = (game_end - game_start).total_seconds()
        n = len(sorted_periods)
        for i, pnum in enumerate(sorted_periods):
            if pnum not in period_timestamps:
                frac = i / max(n, 1)
                period_timestamps[pnum] = game_start + timedelta(seconds=duration * frac)

    if len(period_timestamps) < 2:
        return 0

    # Write period markers
    written = 0
    for period_num, ts in sorted(period_timestamps.items()):
        period_label = _period_num_to_label(period_num, len(sorted_periods))
        session.add(WinProbSnapshot(
            event_id=event_id,
            source="backfill",
            captured_at=ts,
            game_state={"period": period_label, "backfilled": True},
        ))
        written += 1

    return written


def _period_num_to_label(period_num: int, total_periods: int) -> str:
    """Convert ESPN period number to display label based on total periods."""
    ordinals = {1: "1st", 2: "2nd", 3: "3rd"}
    ordinal = ordinals.get(period_num, f"{period_num}th")

    if total_periods <= 3:
        # Hockey-style periods or soccer halves
        if total_periods == 2:
            return f"{ordinal} Half"
        return f"{ordinal} Period"
    elif total_periods <= 4:
        # Basketball/football quarters
        return f"{ordinal} Quarter"
    else:
        # Baseball innings (period > 4 total periods)
        return f"Top {ordinal}"


async def _fetch_and_write_espn_periods(
    session: AsyncSession,
    event: Event,
    sport_key: str,
    score_timestamps: dict[tuple[int, int], datetime],
) -> int:
    """Fetch scoring plays from ESPN API and write period markers.

    Only called for events with espn_id. Stores box_score_data on the event
    for future use.
    """
    try:
        from app.services.espn_api import ESPNApiClient

        async with ESPNApiClient() as espn:
            context = await espn.get_event_context(sport_key, event.espn_id)

        scoring_plays = context.get("scoring_plays", [])
        if not scoring_plays:
            logger.info(f"ESPN fetch for event {event.id}: no scoring_plays returned (espn_id={event.espn_id}, sport={sport_key})")
            return 0

        # Store for future use (if not already stored)
        if not event.box_score_data:
            event.box_score_data = {"scoring_plays": scoring_plays}
        elif "scoring_plays" not in event.box_score_data:
            event.box_score_data = {**event.box_score_data, "scoring_plays": scoring_plays}

        return _write_periods_from_scoring_plays(
            session, event.id, scoring_plays, score_timestamps, event.commence_time,
        )

    except Exception as e:
        logger.warning(f"ESPN fetch failed for event {event.id} (espn_id={event.espn_id}): {e}")
        return 0


async def _copy_espn_snapshot_periods(session: AsyncSession, event_id: int) -> int:
    """Copy period data from ESPNSnapshot records into WinProbSnapshot game_state."""
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

        # Filter date strings
        _DATE_RE = re.compile(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)",
            re.IGNORECASE,
        )
        espn_snaps = [s for s in espn_snaps if not _DATE_RE.search(s.period)]

        if not espn_snaps:
            return 0

        # Group by period, take first timestamp per unique period
        seen_periods: dict[str, datetime] = {}
        for snap in espn_snaps:
            period = snap.period.strip()
            if period and period not in seen_periods:
                seen_periods[period] = snap.captured_at

        if len(seen_periods) < 2:
            return 0

        written = 0
        for period, ts in seen_periods.items():
            # Check for existing snapshot at this timestamp
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
            written += 1

        return written

    except Exception as e:
        logger.debug(f"ESPN snapshot copy failed for event {event_id}: {e}")
        return 0


async def _write_start_end_markers(session: AsyncSession, event: Event) -> bool:
    """Write Start and Final markers using real timestamps.

    Uses commence_time for start and the latest data point from any
    source for end. Returns True if markers were written.
    """
    event_id = event.id
    start_time = event.commence_time
    if not start_time:
        return False

    # Find latest data timestamp across all sources
    end_candidates: list[datetime] = []

    try:
        r = await session.execute(
            select(func.max(OddsSnapshot.captured_at))
            .where(OddsSnapshot.event_id == event_id)
        )
        v = r.scalar()
        if v:
            end_candidates.append(v)
    except Exception:
        pass

    try:
        r = await session.execute(
            select(func.max(WinProbSnapshot.captured_at))
            .where(WinProbSnapshot.event_id == event_id)
        )
        v = r.scalar()
        if v:
            end_candidates.append(v)
    except Exception:
        pass

    try:
        from app.models.models import ESPNSnapshot
        r = await session.execute(
            select(func.max(ESPNSnapshot.captured_at))
            .where(ESPNSnapshot.event_id == event_id)
        )
        v = r.scalar()
        if v:
            end_candidates.append(v)
    except Exception:
        pass

    try:
        from app.models.models import ScoreSnapshot
        r = await session.execute(
            select(func.max(ScoreSnapshot.captured_at))
            .where(ScoreSnapshot.event_id == event_id)
        )
        v = r.scalar()
        if v:
            end_candidates.append(v)
    except Exception:
        pass

    if not end_candidates:
        return False

    end_time = max(end_candidates)

    # Sanity: game must have lasted at least 30 minutes
    if (end_time - start_time).total_seconds() < 1800:
        return False

    session.add(WinProbSnapshot(
        event_id=event_id,
        source="backfill",
        captured_at=start_time,
        game_state={"period": "Start", "backfilled": True},
    ))
    session.add(WinProbSnapshot(
        event_id=event_id,
        source="backfill",
        captured_at=end_time,
        game_state={"period": "Final", "backfilled": True},
    ))
    return True
