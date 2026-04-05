"""
MLB Stats API live win probability sync task.

Polls the MLB Stats API for live games and writes win probability snapshots
using the official MLB win probability endpoint (no model required — MLB
computes it from play-by-play data).

Architecture:
- Fetches today's schedule via /api/v1/schedule?sportId=1
- Filters to in-progress games
- For each live game, fetches current win probability via /api/v1/game/{gamePk}/contextMetrics
- Matches to our Event records by team name + commence_time proximity
- Writes win_prob_snapshots with source="mlb"

Source key: "mlb" (registered in win_prob_sources.py).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models import Event, Sport
from app.tasks.base import get_task_session
from app.tasks.snapshots import _create_or_update_win_prob_snapshot

logger = logging.getLogger(__name__)

# Source key for win_prob_snapshots — matches the registry entry
WIN_PROB_SOURCE_KEY = "mlb"

# Time window for matching MLB games to our events (±4 hours)
MATCH_WINDOW_HOURS = 4


async def _sync_mlb_win_probability():
    """
    Fetch live MLB win probabilities and write to win_prob_snapshots.

    Returns dict with stats about the sync operation.
    """
    from app.services.mlb_api import MLBAPIService

    stats = {
        "live_games_found": 0,
        "events_matched": 0,
        "snapshots_created": 0,
        "snapshots_updated": 0,
        "match_failures": 0,
        "errors": [],
    }

    service = MLBAPIService()
    try:
        # Get live MLB games with current win probability
        live_games = await service.get_live_games()
        stats["live_games_found"] = len(live_games)

        if not live_games:
            logger.info("MLB sync: no live games found")
            return stats

        async with get_task_session() as session:
            # Fetch all live + recently started MLB events from our DB
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=8)  # MLB games can be long

            result = await session.execute(
                select(Event)
                .join(Sport, Event.sport_id == Sport.id)
                .options(selectinload(Event.sport))
                .where(
                    and_(
                        Sport.key.in_(["baseball_mlb", "baseball_mlb_preseason"]),
                        Event.status.in_(["live", "scheduled"]),
                        Event.commence_time >= window_start,
                        Event.commence_time <= now + timedelta(hours=1),
                    )
                )
            )
            our_events = result.scalars().all()

            if not our_events:
                logger.info("MLB sync: no matching MLB events in our DB")
                return stats

            # Build lookup by team name fragments for matching
            # Our events have home_team_name/away_team_name like "Boston Red Sox"
            event_lookup = {}
            for ev in our_events:
                # Key by lowercase team name fragments
                home_key = _normalize_team(ev.home_team_name)
                away_key = _normalize_team(ev.away_team_name)
                event_lookup[(home_key, away_key)] = ev
                event_lookup[(away_key, home_key)] = ev  # Either ordering

            for mlb_game in live_games:
                try:
                    # Try to match to our event
                    event = _match_mlb_game_to_event(
                        mlb_game, our_events, event_lookup
                    )
                    if event is None:
                        stats["match_failures"] += 1
                        logger.debug(
                            f"MLB sync: no match for {mlb_game.away_team} @ {mlb_game.home_team}"
                        )
                        continue

                    stats["events_matched"] += 1

                    # Build game state for the snapshot
                    game_state = {}
                    if mlb_game.inning is not None:
                        game_state["inning"] = mlb_game.inning
                    if mlb_game.inning_half:
                        game_state["inning_half"] = mlb_game.inning_half
                    # Also store as "period" for consistency with ESPN/stat_model
                    # format, so chart period markers can extract it uniformly.
                    if mlb_game.inning is not None and mlb_game.inning_half:
                        ordinals = {1: "1st", 2: "2nd", 3: "3rd"}
                        ord_str = ordinals.get(mlb_game.inning, f"{mlb_game.inning}th")
                        game_state["period"] = f"{mlb_game.inning_half.capitalize()} {ord_str}"
                    if mlb_game.home_score is not None:
                        game_state["home_score"] = mlb_game.home_score
                    if mlb_game.away_score is not None:
                        game_state["away_score"] = mlb_game.away_score
                    game_state["mlb_game_pk"] = mlb_game.game_pk

                    # Write win probability snapshot
                    snapshot, is_new = await _create_or_update_win_prob_snapshot(
                        session,
                        event_id=event.id,
                        source=WIN_PROB_SOURCE_KEY,
                        home_win_probability=round(mlb_game.home_win_probability, 4),
                        away_win_probability=round(mlb_game.away_win_probability, 4),
                        game_state=game_state if game_state else None,
                    )

                    if is_new:
                        session.add(snapshot)
                        stats["snapshots_created"] += 1
                    else:
                        stats["snapshots_updated"] += 1

                    # Also update win_probability_sources on the event
                    sources = event.win_probability_sources or {}
                    sources[WIN_PROB_SOURCE_KEY] = round(mlb_game.home_win_probability, 4)
                    event.win_probability_sources = sources

                    # Update Event.period for feed scoring (late-game bonus)
                    # and chart game state display. ESPN sync also sets this,
                    # but MLB API has more reliable inning data for baseball.
                    if game_state.get("period"):
                        event.period = game_state["period"]
                    if mlb_game.inning is not None:
                        # Baseball doesn't have a running clock — store inning
                        # info as game_clock for the live badge display
                        half = (mlb_game.inning_half or "").capitalize()
                        event.game_clock = f"{half} {mlb_game.inning}" if half else str(mlb_game.inning)

                except Exception as e:
                    stats["errors"].append(str(e))
                    logger.error(f"MLB sync error for game {mlb_game.game_pk}: {e}")

            await session.commit()

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error(f"MLB sync failed: {e}")
    finally:
        await service.close()

    logger.info(
        f"MLB sync: {stats['live_games_found']} live, "
        f"{stats['events_matched']} matched, "
        f"{stats['snapshots_created']} new snapshots, "
        f"{stats['snapshots_updated']} updated"
    )
    return stats


def _normalize_team(name: str) -> str:
    """Normalize team name for matching."""
    return name.lower().strip()


def _match_mlb_game_to_event(mlb_game, our_events, event_lookup):
    """
    Match an MLB API game to one of our Event records.

    Strategy:
    1. Direct team name match (substring matching)
    2. Commence time proximity (within ±4 hours)
    """
    from app.services.mlb_api import _name_matches

    mlb_home = mlb_game.home_team.lower()
    mlb_away = mlb_game.away_team.lower()

    best_match = None
    best_score = 0

    for ev in our_events:
        our_home = ev.home_team_name.lower()
        our_away = ev.away_team_name.lower()

        # Check name match (either orientation)
        home_home = _name_matches(our_home, mlb_home)
        away_away = _name_matches(our_away, mlb_away)
        home_away = _name_matches(our_home, mlb_away)
        away_home = _name_matches(our_away, mlb_home)

        name_match = (home_home and away_away) or (home_away and away_home)
        if not name_match:
            continue

        # Check time proximity
        if mlb_game.game_datetime:
            try:
                mlb_time = datetime.fromisoformat(
                    mlb_game.game_datetime.replace("Z", "+00:00")
                )
                time_diff = abs((ev.commence_time - mlb_time).total_seconds())
                if time_diff > MATCH_WINDOW_HOURS * 3600:
                    continue
                # Better time match = higher score
                score = 1.0 / (1.0 + time_diff / 3600)
            except Exception:
                score = 0.5  # Can't parse time, use partial score
        else:
            score = 0.5

        if score > best_score:
            best_score = score
            best_match = ev

    return best_match
