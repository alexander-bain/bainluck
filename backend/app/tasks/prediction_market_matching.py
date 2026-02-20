"""
Prediction market → Event matching task.

Periodically scans futures_markets from Kalshi and Polymarket to:
1. Detect game-level binary markets (moneyline-style outcomes)
2. Match them to Event records by team name + commence_time
3. Write win_prob_snapshots so they appear as trend lines on OddsChart

Runs after Kalshi (:45) and Polymarket (:15) polling to pick up fresh data.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_, func

from app.tasks.base import get_task_session
from app.utils.prediction_market_matching import (
    is_game_level_market,
    extract_matchup,
    match_teams_to_event,
    find_moneyline_outcome,
    _fuzzy_team_match,
    MAX_TIME_DELTA,
    MAX_PAST_GAME_DELTA,
)

logger = logging.getLogger(__name__)


async def _match_prediction_markets(limit: int = 500):
    """
    Match game-level prediction markets to events and write win_prob_snapshots.

    Two phases:
    1. Link: Find unlinked game-level markets and match to events (set event_id)
    2. Snapshot: For all linked markets, write current probability to win_prob_snapshots
    """
    from app.models.models import (
        FuturesMarket, FuturesOutcome, Event, Sport, WinProbSnapshot,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    stats = {
        "markets_scanned": 0,
        "newly_linked": 0,
        "snapshots_written": 0,
        "snapshots_deduped": 0,
        "errors": [],
        # Funnel stats: track where markets drop off
        "funnel": {
            "total_unlinked": 0,
            "not_game_level": 0,
            "no_matchup_extracted": 0,
            "game_level_detected": 0,
            "no_event_found": 0,
            "linked": 0,
            "sample_game_level_no_event": [],  # Sample of game-level markets that couldn't match
            "sample_not_game_level": [],  # Sample of markets that weren't detected as game-level
        },
    }

    now = datetime.now(timezone.utc)

    async with get_task_session() as session:
        # ── Phase 1: Link unlinked game-level markets ────────────────────

        # Find prediction market futures without event_id that look like game-level
        unlinked_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.updated_at.desc())
            .limit(limit)
        )
        unlinked_markets = unlinked_result.scalars().all()
        stats["funnel"]["total_unlinked"] = len(unlinked_markets)

        for market in unlinked_markets:
            stats["markets_scanned"] += 1

            # Check if market name looks like a game-level matchup.
            # Note: we do NOT gate on outcome count here. Polymarket bundles
            # moneyline + spread + totals under one game event, so a game
            # like "Celtics vs. Warriors" can have 3-5+ outcomes. The name
            # pattern is the reliable signal, not outcome count.
            if not is_game_level_market(market.name, market.category):
                stats["funnel"]["not_game_level"] += 1
                if len(stats["funnel"]["sample_not_game_level"]) < 10:
                    stats["funnel"]["sample_not_game_level"].append(
                        {"source": market.source, "name": market.name}
                    )
                continue

            # Extract matchup info
            matchup = extract_matchup(market.name)
            if not matchup:
                stats["funnel"]["no_matchup_extracted"] += 1
                continue

            stats["funnel"]["game_level_detected"] += 1

            # Find candidate events by team name matching
            # Search for events where either team matches either market team
            matched_event = await _find_matching_event(
                session, matchup, market, now,
            )

            if matched_event:
                market.event_id = matched_event["event_id"]
                stats["newly_linked"] += 1
                stats["funnel"]["linked"] += 1
                logger.info(
                    "Linked %s market '%s' → event %d (%s vs %s) [yes_is_home=%s]",
                    market.source, market.name, matched_event["event_id"],
                    matched_event["home_team"], matched_event["away_team"],
                    matched_event["yes_is_home"],
                )
            else:
                stats["funnel"]["no_event_found"] += 1
                if len(stats["funnel"]["sample_game_level_no_event"]) < 10:
                    stats["funnel"]["sample_game_level_no_event"].append(
                        {
                            "source": market.source,
                            "name": market.name,
                            "team_a": matchup.team_a,
                            "team_b": matchup.team_b,
                            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                        }
                    )

        # ── Phase 2: Write win_prob_snapshots for all linked markets ─────

        # Find all linked prediction markets (including newly linked ones)
        linked_result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
            )
        )
        linked_markets = linked_result.scalars().all()

        for market in linked_markets:
            try:
                # Load the event to determine home/away mapping
                event_result = await session.execute(
                    select(Event).where(Event.id == market.event_id)
                )
                event = event_result.scalar_one_or_none()
                if not event:
                    continue

                # Re-extract matchup to determine team mapping
                matchup = extract_matchup(market.name)
                if not matchup:
                    continue

                # Get ALL outcomes for this market (game events may have
                # moneyline + spread + totals bundled together)
                outcome_result = await session.execute(
                    select(FuturesOutcome)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank)
                )
                all_outcomes = outcome_result.scalars().all()
                if not all_outcomes:
                    continue

                # Find the moneyline outcome by matching team names
                ml_result = find_moneyline_outcome(
                    all_outcomes, matchup,
                    event.home_team_name, event.away_team_name,
                )
                if not ml_result:
                    continue

                outcome, yes_is_home = ml_result
                yes_prob = float(outcome.current_probability)

                # Convert prediction market probability to home/away
                if yes_is_home:
                    home_prob = yes_prob
                else:
                    home_prob = 1.0 - yes_prob
                away_prob = 1.0 - home_prob

                # Write to win_prob_snapshots with deduplication
                source_key = market.source  # "kalshi" or "polymarket"
                snapshot, is_new = await _create_or_update_win_prob_snapshot(
                    session,
                    event_id=market.event_id,
                    source=source_key,
                    home_win_probability=round(home_prob, 4),
                    away_win_probability=round(away_prob, 4),
                    game_state={
                        "market_name": market.name,
                        "market_id": market.id,
                        "outcome_name": outcome.name,
                        "yes_probability": yes_prob,
                        "yes_bid": float(outcome.current_yes_bid) if outcome.current_yes_bid else None,
                        "yes_ask": float(outcome.current_yes_ask) if outcome.current_yes_ask else None,
                    },
                )

                if is_new:
                    session.add(snapshot)
                    stats["snapshots_written"] += 1
                else:
                    stats["snapshots_deduped"] += 1

            except Exception as e:
                stats["errors"].append(f"market {market.id}: {str(e)}")
                continue

        await session.commit()

    logger.info(
        "Prediction market matching: scanned=%d, linked=%d, "
        "snapshots_written=%d, deduped=%d, errors=%d",
        stats["markets_scanned"], stats["newly_linked"],
        stats["snapshots_written"], stats["snapshots_deduped"],
        len(stats["errors"]),
    )
    return stats


async def _find_matching_event(session, matchup, market, now):
    """
    Find an Event that matches the given matchup and market.

    Strategy:
    1. Search events by team name ILIKE matching
    2. Filter by commence_time proximity
    3. Prefer events in the same sport category
    4. Return the best match or None
    """
    from app.models.models import Event, Sport

    # Build team name search patterns
    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    # Create ILIKE conditions for team names
    ilike_conditions = []
    for team in teams_to_search:
        pattern = f"%{_escape_like(team)}%"
        ilike_conditions.append(Event.home_team_name.ilike(pattern))
        ilike_conditions.append(Event.away_team_name.ilike(pattern))

    # Time window: events starting within ±48 hours of market commence_time
    # or within ±48 hours of now if no commence_time
    reference_time = market.commence_time or now
    time_start = reference_time - MAX_TIME_DELTA
    time_end = reference_time + MAX_TIME_DELTA

    # Also restrict: don't match events that started more than 6 hours ago
    # (unless they're still live)
    past_cutoff = now - MAX_PAST_GAME_DELTA

    # Query candidate events
    event_result = await session.execute(
        select(Event)
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
            or_(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time >= past_cutoff,
            ),
        )
        .order_by(Event.commence_time)
        .limit(20)
    )
    candidates = event_result.scalars().all()

    if not candidates:
        return None

    # Score each candidate
    best_match = None
    best_score = -1

    for event in candidates:
        # Check team name matching
        team_match = match_teams_to_event(
            matchup,
            event.home_team_name,
            event.away_team_name,
        )
        if not team_match:
            continue

        # For "Will X win?" with only one team, verify the other team too
        # by checking that at least one market team matches an event team
        if matchup.format_type == "will_win" and not matchup.team_b:
            # Single-team format — must match one event team
            if not (
                _fuzzy_team_match(matchup.team_a, event.home_team_name)
                or _fuzzy_team_match(matchup.team_a, event.away_team_name)
            ):
                continue

        # Score: prefer closer commence_time + same sport + live games
        score = 0

        # Time proximity (max 10 points, closer = higher)
        if event.commence_time and market.commence_time:
            delta_hours = abs(
                (event.commence_time - market.commence_time).total_seconds()
            ) / 3600
            score += max(0, 10 - delta_hours)
        elif event.commence_time:
            delta_hours = abs(
                (event.commence_time - now).total_seconds()
            ) / 3600
            score += max(0, 5 - delta_hours / 10)

        # Live games get a bonus
        if event.status == "live":
            score += 5
        elif event.status == "scheduled":
            score += 3

        # Both teams matched (not just one) get a bonus
        if matchup.team_b:
            other = matchup.team_b if matchup.yes_team == matchup.team_a else matchup.team_a
            if (
                _fuzzy_team_match(other, event.home_team_name)
                or _fuzzy_team_match(other, event.away_team_name)
            ):
                score += 10  # Both teams matched — very strong signal

        if score > best_score:
            best_score = score
            best_match = {
                "event_id": event.id,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "yes_is_home": team_match["yes_is_home"],
                "score": score,
            }

    return best_match


def _escape_like(s: str) -> str:
    """Escape special characters for ILIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
