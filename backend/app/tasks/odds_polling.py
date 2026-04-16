"""
Main odds polling tasks: poll_all_odds, poll_sport_odds, and snapshot helpers.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, case, or_, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models import Sport, Event, OddsSnapshot, ScoreSnapshot
from app.services.odds_api import OddsAPIService
from app.utils.odds_math import moneyline_to_probability, project_scores
from app.tasks.base import get_task_session, run_async
from app.tasks.config import (
    LIVE_POLL_INTERVAL,
    SOON_POLL_INTERVAL,
    LATER_POLL_INTERVAL,
    MEDIUM_POLL_INTERVAL,
    SLOW_POLL_INTERVAL,
    MEDIUM_THRESHOLD,
    SLOW_THRESHOLD,
    ODDS_STALE_MINUTES,
    MIN_HOURS_BEFORE_STALENESS_CHECK,
    SPORT_MAX_DURATIONS,
)
from app.tasks.redis_state import (
    get_redis_client,
    compute_odds_hash,
    should_poll_now,
    update_poll_state,
    check_quota_guard,
    POLL_STATE_KEY,
    QUOTA_GUARD_LIVE_ONLY,
    QUOTA_GUARD_PRIORITY_SPORTS,
    QUOTA_GUARD_CONSERVATION_INTERVAL,
)

logger = logging.getLogger(__name__)


def get_statpal_end_time(event) -> Optional[datetime]:
    """
    Extract StatPal end time from event — checks dedicated column first,
    falls back to JSONB win_probability_sources storage.

    Returns a timezone-aware datetime if found, else None.
    """
    statpal_end = getattr(event, "statpal_end_time", None)
    if statpal_end:
        return statpal_end
    sources = getattr(event, "win_probability_sources", None) or {}
    end_str = sources.get("statpal_end_time")
    if end_str:
        try:
            return datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            pass
    return None


def get_max_duration_for_sport(sport_key: str) -> float:
    """
    Get the maximum expected duration (in hours) for a sport.

    Used for staleness detection - we only mark events as "closed"
    if they've been live longer than this duration AND odds are stale.
    """
    # Check for exact match first
    for sport_prefix, duration in SPORT_MAX_DURATIONS.items():
        if sport_prefix == "default":
            continue
        if sport_key.startswith(sport_prefix):
            return duration

    return SPORT_MAX_DURATIONS["default"]


async def detect_and_close_stale_events(session) -> int:
    """
    Detect live events with stale odds and mark them as "closed".

    This provides a fallback when the Scores API doesn't report completion,
    which can happen with tennis and other sports.

    An event is marked as "closed" when:
    1. It's currently "live" status
    2. It started at least MIN_HOURS_BEFORE_STALENESS_CHECK hours ago
    3. Either:
       a. It has no odds snapshots at all (bookmakers stopped offering odds), OR
       b. The latest odds snapshot is older than ODDS_STALE_MINUTES

    Returns the number of events marked as closed.
    """
    now = datetime.now(timezone.utc)
    closed_count = 0

    # Find all live events that started more than MIN_HOURS ago
    min_start_time = now - timedelta(hours=MIN_HOURS_BEFORE_STALENESS_CHECK)

    result = await session.execute(
        select(Event)
        .join(Sport)
        .where(
            Event.status == "live",
            Event.commence_time <= min_start_time,
        )
        .options(selectinload(Event.sport))
    )
    live_events = result.scalars().all()

    for event in live_events:
        try:
            hours_since_start = (now - event.commence_time).total_seconds() / 3600

            # Check StatPal end time first — definitive close signal
            statpal_end = get_statpal_end_time(event)
            if statpal_end and statpal_end <= now:
                await session.execute(
                    Event.__table__.update()
                    .where(Event.id == event.id)
                    .values(status="closed")
                )
                closed_count += 1
                logger.info(
                    f"Marked event {event.id} ({event.home_team_name} vs {event.away_team_name}) "
                    f"as closed: statpal_end_time, {hours_since_start:.1f}h since start"
                )
                continue

            # Check if ANY bookmaker has provided odds recently
            # We need to find the most recently updated snapshot across all bookmakers
            # valid_until is updated when we see the same odds again; captured_at is when odds changed
            stale_threshold = now - timedelta(minutes=ODDS_STALE_MINUTES)

            # Count snapshots that have been updated recently
            recent_snapshot_count = await session.execute(
                select(func.count())
                .select_from(OddsSnapshot)
                .where(
                    OddsSnapshot.event_id == event.id,
                    or_(
                        OddsSnapshot.valid_until >= stale_threshold,
                        and_(
                            OddsSnapshot.valid_until == None,
                            OddsSnapshot.captured_at >= stale_threshold
                        )
                    )
                )
            )
            recent_count = recent_snapshot_count.scalar()

            should_close = False
            close_reason = ""

            if recent_count == 0:
                # No bookmaker has updated odds recently - check if we ever had odds
                any_snapshot = await session.execute(
                    select(func.count())
                    .select_from(OddsSnapshot)
                    .where(OddsSnapshot.event_id == event.id)
                )
                total_snapshots = any_snapshot.scalar()

                if total_snapshots == 0:
                    should_close = True
                    close_reason = "no_odds_data"
                else:
                    # Had odds but all bookmakers stopped updating
                    should_close = True
                    close_reason = "all_bookmakers_stale"

            if should_close:
                await session.execute(
                    Event.__table__.update()
                    .where(Event.id == event.id)
                    .values(status="closed")
                )
                closed_count += 1
                logger.info(f"Marked event {event.id} ({event.home_team_name} vs {event.away_team_name}) "
                      f"as closed: {close_reason}, {hours_since_start:.1f}h since start")

        except Exception as e:
            logger.warning(f"Error checking staleness for event {event.id}: {e}")
            continue

    return closed_count


def _snapshots_are_equal(existing: OddsSnapshot, new_values: dict) -> bool:
    """Check if the key odds values are the same."""
    # Compare the fields that matter for deduplication
    # Using rough equality for decimals
    def eq(a, b):
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # For numeric types, compare values
        return float(a) == float(b) if isinstance(a, (int, float)) or hasattr(a, '__float__') else a == b

    return (
        eq(existing.home_moneyline, new_values.get("home_moneyline")) and
        eq(existing.away_moneyline, new_values.get("away_moneyline")) and
        eq(existing.home_spread, new_values.get("home_spread")) and
        eq(existing.over_under, new_values.get("over_under")) and
        eq(existing.home_win_probability, new_values.get("home_win_probability"))
    )


def _parse_snapshot_values(bookmaker: dict, event_data: dict) -> dict:
    """Parse bookmaker data into snapshot field values."""
    values = {
        "home_moneyline": None,
        "away_moneyline": None,
        "home_spread": None,
        "home_spread_odds": None,
        "away_spread_odds": None,
        "over_under": None,
        "over_odds": None,
        "under_odds": None,
        "home_win_probability": None,
        "away_win_probability": None,
        "projected_home_score": None,
        "projected_away_score": None,
    }

    home_team = event_data["home_team"]
    away_team = event_data["away_team"]

    for market in bookmaker.get("markets", []):
        market_key = market["key"]
        outcomes = {o["name"]: o for o in market["outcomes"]}

        if market_key == "h2h":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            values["home_moneyline"] = home_outcome.get("price")
            values["away_moneyline"] = away_outcome.get("price")

            if values["home_moneyline"] and values["away_moneyline"]:
                home_prob, away_prob = moneyline_to_probability(
                    values["home_moneyline"],
                    values["away_moneyline"],
                )
                values["home_win_probability"] = round(home_prob, 4)
                values["away_win_probability"] = round(away_prob, 4)

        elif market_key == "spreads":
            home_outcome = outcomes.get(home_team, {})
            away_outcome = outcomes.get(away_team, {})
            values["home_spread"] = home_outcome.get("point")
            values["home_spread_odds"] = home_outcome.get("price")
            values["away_spread_odds"] = away_outcome.get("price")

        elif market_key == "totals":
            over_outcome = outcomes.get("Over", {})
            under_outcome = outcomes.get("Under", {})
            values["over_under"] = over_outcome.get("point")
            values["over_odds"] = over_outcome.get("price")
            values["under_odds"] = under_outcome.get("price")

    # Calculate projected scores
    if values["home_spread"] is not None and values["over_under"]:
        home_score, away_score = project_scores(
            float(values["home_spread"]),
            float(values["over_under"]),
        )
        values["projected_home_score"] = home_score
        values["projected_away_score"] = away_score

    return values


async def _maybe_set_opening_odds(
    session,
    event_id: int,
    home_prob: float | None,
    away_prob: float | None,
    home_spread: float | None,
    over_under: float | None,
    commence_time: datetime | None = None,
):
    """
    Update opening odds for a scheduled event.

    Opening odds represent the last pregame consensus — they keep updating
    on every poll while the game is still scheduled. Once the game starts,
    they freeze, capturing what the market thought right before kickoff.

    If commence_time is not provided, falls back to checking the event status.
    """
    if home_prob is None:
        return

    now = datetime.now(timezone.utc)

    # Only update if the game hasn't started yet
    if commence_time is not None and commence_time <= now:
        return

    # Also check event status as a fallback
    result = await session.execute(
        select(Event.status)
        .where(Event.id == event_id)
    )
    status = result.scalar_one_or_none()
    if status and status != "scheduled":
        return

    # Determine opening favorite
    if home_prob > 0.52:
        opening_favorite = "home"
    elif home_prob < 0.48:
        opening_favorite = "away"
    else:
        opening_favorite = "even"

    # Update opening odds (keeps updating until game starts)
    await session.execute(
        Event.__table__.update()
        .where(Event.id == event_id)
        .values(
            opening_home_probability=home_prob,
            opening_away_probability=away_prob,
            opening_home_spread=home_spread,
            opening_over_under=over_under,
            opening_favorite=opening_favorite,
        )
    )


async def _create_or_update_snapshot(
    session,
    event_id: int,
    bookmaker: dict,
    event_data: dict
) -> tuple[OddsSnapshot, bool]:
    """
    Create a new snapshot or update existing if values unchanged.

    Returns (snapshot, is_new) tuple.
    - If values changed: creates new snapshot, returns (new_snapshot, True)
    - If values same: updates existing snapshot's reading_count/valid_until, returns (existing, False)
    """
    now = datetime.now(timezone.utc)
    bookmaker_key = bookmaker["key"]

    # Parse the new values
    new_values = _parse_snapshot_values(bookmaker, event_data)

    # Find the most recent snapshot for this event+bookmaker
    result = await session.execute(
        select(OddsSnapshot)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.bookmaker == bookmaker_key
        )
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    # If no existing snapshot or values changed, create new one
    if existing is None or not _snapshots_are_equal(existing, new_values):
        # If there was an existing one, set its valid_until
        if existing is not None:
            existing.valid_until = now

        # Create new snapshot
        snapshot = OddsSnapshot(
            event_id=event_id,
            bookmaker=bookmaker_key,
            captured_at=now,
            reading_count=1,
            **new_values
        )
        return snapshot, True
    else:
        # Values are the same - just update the existing snapshot
        existing.reading_count += 1
        existing.valid_until = now
        return existing, False


# _create_or_update_win_prob_snapshot moved to tasks/snapshots.py
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: F401


async def _create_snapshot(
    event_id: int,
    bookmaker: dict,
    event_data: dict
) -> OddsSnapshot:
    """Create an OddsSnapshot from API data. (Legacy - used by poll_sport_odds)"""
    values = _parse_snapshot_values(bookmaker, event_data)
    snapshot = OddsSnapshot(
        event_id=event_id,
        bookmaker=bookmaker["key"],
        captured_at=datetime.now(timezone.utc),
        reading_count=1,
        **values
    )
    return snapshot


async def _poll_all_odds():
    """
    Async implementation of poll_all_odds with tiered per-sport polling.

    Tiered polling based on game proximity:
    - Live games (in progress): Poll every 60 seconds
    - Starting soon (0-2 hours): Poll every 5 minutes
    - Starting later (2-6 hours): Poll every 15 minutes
    - No games in 6 hours: Don't poll that sport

    Uses per-sport last poll times stored in Redis.
    Also fetches scores for live/completed games.
    """
    from app.tasks.excitement_index import update_live_ei as update_live_gei

    # Emergency quota guard: check overall quota level
    guard_ok, guard_reason = check_quota_guard("poll_odds")
    if not guard_ok:
        # Full stop — but priority sports may still be allowed (checked per-sport below)
        if "full_stop" in guard_reason:
            logger.info("poll_all_odds in FULL STOP — only priority sports allowed")
        else:
            logger.warning("poll_all_odds SKIPPED by quota guard: %s", guard_reason)
            return {"skipped": True, "reason": f"quota_guard:{guard_reason}"}

    # Check if we're in live-only mode (quota < QUOTA_GUARD_LIVE_ONLY)
    quota_live_only = "live_only" in guard_reason
    quota_full_stop = "full_stop" in guard_reason
    quota_conservation = quota_full_stop or "conservation" in guard_reason

    service = OddsAPIService()

    try:
        total_events = 0
        total_snapshots = 0
        all_events_data = []
        has_live_games = False
        sports_polled = 0
        sports_skipped = 0
        scores_updated = 0
        stat_model_from_poll = 0

        # Get Redis client for per-sport poll tracking
        try:
            r = get_redis_client()
        except Exception:
            r = None

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            # Get all sports with upcoming/live games in the next 6 hours
            lookahead_6h = now + timedelta(hours=6)

            # Query to get sports with their soonest game time
            result = await session.execute(
                select(
                    Sport.key,
                    func.min(Event.commence_time).label("soonest_game"),
                    func.bool_or(Event.status == "live").label("has_live")
                )
                .join(Event)
                .where(
                    Sport.active == True,
                    Event.status.in_(["scheduled", "live"]),
                    Event.commence_time <= lookahead_6h,
                    Event.commence_time >= now - timedelta(hours=6)
                )
                .group_by(Sport.key)
            )
            sport_data = result.all()

            # Even if no sports need odds polling, we should still check for stale events
            # and update scores for recently started games
            if not sport_data:
                # Still run staleness detection for any live events that may have ended
                events_closed = await detect_and_close_stale_events(session)
                await session.commit()
                return {
                    "events": 0,
                    "snapshots": 0,
                    "sports": 0,
                    "sports_skipped": 0,
                    "events_closed": events_closed,
                    "message": "No sports with games in the next 6 hours.",
                    "skipped": True,
                }

            for row in sport_data:
                sport_key = row[0]
                soonest_game = row[1]
                is_live = row[2]

                # Determine poll interval for this sport
                if is_live or (soonest_game and soonest_game <= now):
                    # Live game - poll every 32 seconds
                    poll_interval = LIVE_POLL_INTERVAL
                    tier = "live"
                    has_live_games = True
                elif soonest_game and soonest_game <= now + timedelta(hours=2):
                    # Starting soon (0-2 hours) - poll every 5 minutes
                    poll_interval = SOON_POLL_INTERVAL
                    tier = "soon"
                else:
                    # Starting later (2-6 hours) - poll every 1 hour
                    poll_interval = LATER_POLL_INTERVAL
                    tier = "later"

                # Quota guard: in full-stop mode, only priority sports allowed
                if quota_full_stop:
                    if sport_key not in QUOTA_GUARD_PRIORITY_SPORTS:
                        sports_skipped += 1
                        continue
                    # Re-check per-sport to get conservation reason
                    _, guard_reason = check_quota_guard("poll_odds", sport_key=sport_key)
                    quota_conservation = "conservation" in guard_reason
                    # In full-stop conservation, only poll live games
                    if tier != "live":
                        sports_skipped += 1
                        continue

                # Quota guard: in live-only mode, skip non-live sports entirely
                if quota_live_only and not quota_full_stop and tier != "live":
                    sports_skipped += 1
                    continue

                # Adaptive slowdown: when odds haven't changed for a sport,
                # gradually increase the interval to conserve API quota.
                # Only applies to non-live tiers (live games always poll fast).
                if tier != "live" and r:
                    try:
                        unchanged_key = f"bainluck:unchanged_count:{sport_key}"
                        unchanged_raw = r.get(unchanged_key)
                        unchanged_count = int(unchanged_raw.decode()) if unchanged_raw else 0
                        if unchanged_count >= SLOW_THRESHOLD:
                            poll_interval = max(poll_interval, SLOW_POLL_INTERVAL)
                        elif unchanged_count >= MEDIUM_THRESHOLD:
                            poll_interval = max(poll_interval, MEDIUM_POLL_INTERVAL)
                    except Exception:
                        pass

                # Check if enough time has elapsed since last poll for this sport
                should_poll_sport = True
                if r:
                    try:
                        last_poll_key = f"bainluck:last_poll:{sport_key}"
                        last_poll = r.get(last_poll_key)
                        if last_poll:
                            last_poll_time = float(last_poll.decode())
                            elapsed = now.timestamp() - last_poll_time
                            if elapsed < poll_interval:
                                # Not enough time elapsed, skip this sport
                                should_poll_sport = False
                                sports_skipped += 1
                    except Exception:
                        pass  # If Redis fails, just poll

                if not should_poll_sport:
                    continue

                # Quota optimization: use lighter API params for non-live tiers.
                # - "later" tier: h2h only (saves 2/3 of billed requests per event)
                # - "soon"/"later" tiers: primary US bookmakers only (saves 1/2)
                # - "live" tier: full params for maximum coverage
                # - Conservation mode: always h2h + us only (even live)
                if quota_conservation:
                    api_markets = "h2h"
                    api_regions = "us"
                    poll_interval = max(poll_interval, QUOTA_GUARD_CONSERVATION_INTERVAL)
                elif tier == "live":
                    api_markets = "h2h,spreads,totals"
                    api_regions = "us,us2"
                elif tier == "soon":
                    # Full markets, single region (saves ~50% vs live)
                    api_markets = "h2h,spreads,totals"
                    api_regions = "us"
                else:  # "later" — h2h only, primary US only (saves ~83% vs live)
                    api_markets = "h2h"
                    api_regions = "us"

                try:
                    pre_used = service.last_requests_used
                    events_data = await service.get_odds(
                        sport_key,
                        regions=api_regions,
                        markets=api_markets,
                    )
                    all_events_data.extend(events_data)
                    sports_polled += 1

                    # Record quota from response headers
                    if service.last_requests_remaining is not None:
                        from app.tasks.redis_state import record_odds_api_quota
                        record_odds_api_quota(
                            service.last_requests_remaining,
                            service.last_requests_used or 0,
                            "poll_odds",
                            pre_call_used=pre_used,
                            sport_key=sport_key,
                        )

                    # Update last poll time and per-sport adaptive state in Redis
                    if r:
                        try:
                            last_poll_key = f"bainluck:last_poll:{sport_key}"
                            r.set(last_poll_key, str(now.timestamp()), ex=3600)

                            # Per-sport adaptive slowdown: track unchanged polls.
                            # Hash only the odds for this sport to detect per-sport changes.
                            sport_hash = compute_odds_hash(events_data)
                            prev_sport_hash_key = f"bainluck:odds_hash:{sport_key}"
                            unchanged_key = f"bainluck:unchanged_count:{sport_key}"
                            prev_sport_hash = r.get(prev_sport_hash_key)
                            prev_sport_hash = prev_sport_hash.decode() if prev_sport_hash else None

                            if prev_sport_hash and prev_sport_hash == sport_hash:
                                # Odds unchanged — increment counter
                                r.incr(unchanged_key)
                            else:
                                # Odds changed — reset counter
                                r.set(unchanged_key, "0", ex=7200)

                            r.set(prev_sport_hash_key, sport_hash, ex=7200)
                            r.expire(unchanged_key, 7200)
                        except Exception:
                            pass

                    for event_data in events_data:
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        # Get or create sport
                        sport_result = await session.execute(
                            select(Sport).where(Sport.key == sport_key)
                        )
                        sport = sport_result.scalar_one_or_none()

                        if not sport:
                            sport = Sport(
                                key=sport_key,
                                name=sport_key.replace("_", " ").title(),
                                active=True,
                            )
                            session.add(sport)
                            await session.flush()

                        # ── Unified event matching via Event Registry ──
                        event_status = "scheduled" if commence_time > now else "live"
                        from app.services.event_registry import (
                            find_or_create_event, EventIdentity, EventClaim,
                        )
                        identity = EventIdentity(
                            sport_key=sport_key,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            claim=EventClaim("odds_api", event_data["id"]),
                            commence_time_source="odds_api",
                            status=event_status,
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        event_id = event.id
                        if was_created:
                            total_events += 1

                        # Create odds snapshots (with deduplication)
                        # Collect all bookmaker values for opening odds consensus
                        all_home_probs = []
                        all_away_probs = []
                        all_spreads = []
                        all_ous = []

                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot, is_new = await _create_or_update_snapshot(
                                session,
                                event_id,
                                bookmaker,
                                event_data
                            )
                            if is_new:
                                session.add(snapshot)
                            # Collect values from ALL bookmakers (new or existing)
                            # for computing opening odds consensus
                            if snapshot.home_win_probability:
                                all_home_probs.append(float(snapshot.home_win_probability))
                                if snapshot.away_win_probability:
                                    all_away_probs.append(float(snapshot.away_win_probability))
                                if snapshot.home_spread is not None:
                                    all_spreads.append(float(snapshot.home_spread))
                                if snapshot.over_under is not None:
                                    all_ous.append(float(snapshot.over_under))
                            total_snapshots += 1

                        # Update opening odds with consensus across all bookmakers
                        # (keeps updating on every poll while game is scheduled)
                        if all_home_probs:
                            avg_home = sum(all_home_probs) / len(all_home_probs)
                            avg_away = sum(all_away_probs) / len(all_away_probs) if all_away_probs else (1 - avg_home)
                            avg_spread = sum(all_spreads) / len(all_spreads) if all_spreads else None
                            avg_ou = sum(all_ous) / len(all_ous) if all_ous else None
                            await _maybe_set_opening_odds(
                                session, event_id,
                                avg_home, avg_away,
                                avg_spread, avg_ou,
                                commence_time=commence_time,
                            )

                            # Write betting consensus to win_probability_sources
                            # so the multi-source aggregation system sees it.
                            # Write betting consensus to win_probability_sources
                            # using SQLAlchemy ORM update to avoid JSONB cast issues.
                            from sqlalchemy import update as _update
                            betting_val = round(avg_home, 4)
                            # Read current value, merge, write back
                            _evt_r = await session.execute(
                                select(Event.win_probability_sources).where(Event.id == event_id)
                            )
                            _current = _evt_r.scalar_one_or_none() or {}
                            _current["betting"] = betting_val
                            await session.execute(
                                _update(Event)
                                .where(Event.id == event_id)
                                .values(win_probability_sources=_current)
                            )

                except Exception as e:
                    print(f"Error polling {sport_key}: {e}")
                    continue

            # Fetch scores for sports with events that have started
            # Use a 3-day window to capture longer events like tennis matches
            # that may start one day and finish the next
            # Include "scheduled" events that have started - the scores API will
            # update their status to "live" or "completed" as appropriate
            # Include "closed" events too — the staleness checker may close events
            # before the Scores API reports final scores, especially for minor
            # leagues. Including them here lets us backfill scores on the next poll.
            sports_needing_scores = await session.execute(
                select(Sport.key)
                .join(Event)
                .where(
                    Sport.active == True,
                    Event.commence_time <= now,  # Event has started
                    Event.commence_time >= now - timedelta(days=3),  # Within last 3 days
                    Event.status.in_(["scheduled", "live", "completed", "closed"]),
                )
                .distinct()
            )
            sports_for_scores = [row[0] for row in sports_needing_scores.all()]

            for sport_key in sports_for_scores:
                try:
                    # Request scores from last 3 days to match the query window
                    scores_data = await service.get_scores(sport_key, days_from=3)

                    for score_event in scores_data:
                        try:
                            external_id = score_event.get("id")
                            is_completed = score_event.get("completed", False)

                            # Parse scores from the API response
                            event_scores = score_event.get("scores")
                            home_team = score_event.get("home_team")
                            away_team = score_event.get("away_team")

                            # Find scores for home and away teams
                            home_score = None
                            away_score = None

                            if event_scores is not None and len(event_scores) > 0:
                                for team_score in event_scores:
                                    score_str = team_score.get("score")
                                    # Safely parse score - handles empty strings, None, non-numeric
                                    # Note: score of 0 is valid and should be stored
                                    try:
                                        if score_str is not None and score_str != "":
                                            score_val = int(score_str)
                                        else:
                                            score_val = None
                                    except (ValueError, TypeError):
                                        score_val = None

                                    team_name = team_score.get("name")
                                    if team_name == home_team:
                                        home_score = score_val
                                    elif team_name == away_team:
                                        away_score = score_val

                            # Determine status from scores API response.
                            # CRITICAL: Only set "live" if the event has actually started.
                            # The Scores API returns upcoming events with completed=False,
                            # which would incorrectly set scheduled games to "live".
                            score_commence_str = score_event.get("commence_time")
                            if score_commence_str:
                                try:
                                    score_commence = datetime.fromisoformat(
                                        score_commence_str.replace("Z", "+00:00")
                                    )
                                except (ValueError, TypeError):
                                    score_commence = None
                            else:
                                score_commence = None

                            if is_completed:
                                event_status = "completed"
                            elif score_commence and score_commence <= now:
                                event_status = "live"
                            elif home_score is not None and away_score is not None:
                                # Has scores but no commence_time — trust that it's live
                                event_status = "live"
                            else:
                                # Event hasn't started — skip status update entirely
                                # Still update scores if present (shouldn't be, but safe)
                                event_status = None

                            update_values = {}
                            if event_status is not None:
                                update_values["status"] = event_status

                            if home_score is not None:
                                update_values["home_score"] = home_score
                            if away_score is not None:
                                update_values["away_score"] = away_score

                            # Get current event to check if score changed
                            event_result = await session.execute(
                                select(Event).where(Event.external_id == external_id)
                            )
                            event_obj = event_result.scalar_one_or_none()

                            # Record score snapshot if scores changed
                            if event_obj and home_score is not None and away_score is not None:
                                old_home = event_obj.home_score
                                old_away = event_obj.away_score
                                if old_home != home_score or old_away != away_score:
                                    # Score changed - record a snapshot
                                    score_snap = ScoreSnapshot(
                                        event_id=event_obj.id,
                                        home_score=home_score,
                                        away_score=away_score,
                                    )
                                    session.add(score_snap)

                            if update_values:
                                await session.execute(
                                    Event.__table__.update()
                                    .where(Event.external_id == external_id)
                                    .values(**update_values)
                                )
                            scores_updated += 1

                            # Compute stat model for live events with score data.
                            # Prefers ESPN clock/period but falls back to wall-clock
                            # estimation from commence_time when ESPN sync misses
                            # (common for college teams with name mismatches).
                            if (
                                event_obj
                                and event_status == "live"
                                and home_score is not None
                                and away_score is not None
                                and (event_obj.game_clock or event_obj.period or event_obj.commence_time)
                            ):
                                try:
                                    from app.utils.win_probability import compute_statistical_win_prob

                                    pregame_spread = None
                                    if event_obj.opening_home_spread is not None:
                                        pregame_spread = float(event_obj.opening_home_spread)

                                    stat_wp = compute_statistical_win_prob(
                                        home_score=home_score,
                                        away_score=away_score,
                                        clock=event_obj.game_clock,
                                        period=event_obj.period,
                                        sport_key=sport_key,
                                        pregame_spread=pregame_spread,
                                        commence_time=event_obj.commence_time,
                                    )
                                    if stat_wp is not None:
                                        # Update event's win_probability_sources
                                        # Need to re-fetch to get current JSONB
                                        fresh = await session.execute(
                                            select(Event).where(Event.id == event_obj.id)
                                        )
                                        fresh_event = fresh.scalar_one_or_none()
                                        if fresh_event:
                                            sources = fresh_event.win_probability_sources or {}
                                            sources["stat_model"] = round(stat_wp, 4)
                                            fresh_event.win_probability_sources = sources

                                            stat_snap, is_new = await _create_or_update_win_prob_snapshot(
                                                session,
                                                event_id=event_obj.id,
                                                source="stat_model",
                                                home_win_probability=round(stat_wp, 4),
                                                away_win_probability=round(1.0 - stat_wp, 4),
                                                game_state={
                                                    "clock": event_obj.game_clock,
                                                    "period": event_obj.period,
                                                    "home_score": home_score,
                                                    "away_score": away_score,
                                                    "pregame_spread": pregame_spread,
                                                    "source": "odds_poll",
                                                    "time_source": "espn" if event_obj.game_clock else "wall_clock",
                                                },
                                            )
                                            if is_new:
                                                session.add(stat_snap)
                                            stat_model_from_poll += 1
                                except Exception as e:
                                    logger.warning(f"stat_model in odds poll failed for event {event_obj.id}: {e}")

                        except Exception as e:
                            print(f"Error updating score for event {score_event.get('id')}: {e}")
                            continue

                except Exception as e:
                    print(f"Error fetching scores for {sport_key}: {e}")
                    continue

            # Detect and mark stale events as "closed"
            # This catches matches that the Scores API didn't report as completed
            events_closed = await detect_and_close_stale_events(session)

            # Update GEI for all live events (real-time excitement scores)
            live_gei_updated = 0
            if has_live_games:
                live_gei_updated = await update_live_gei(session)

            await session.commit()

        # Compute hash and check for changes
        new_hash = compute_odds_hash(all_events_data)

        # Get previous hash to detect changes
        try:
            r = get_redis_client()
            prev_hash = r.hget(POLL_STATE_KEY, "last_hash")
            prev_hash = prev_hash.decode() if prev_hash else None
        except Exception:
            prev_hash = None

        data_changed = prev_hash is None or prev_hash != new_hash

        # Update adaptive polling state
        update_poll_state(data_changed, has_live_games, new_hash)

        return {
            "events": total_events,
            "snapshots": total_snapshots,
            "sports_polled": sports_polled,
            "sports_skipped": sports_skipped,
            "scores_updated": scores_updated,
            "stat_model_from_poll": stat_model_from_poll,
            "events_closed": events_closed,
            "live_gei_updated": live_gei_updated,
            "data_changed": data_changed,
            "has_live_games": has_live_games,
        }
    finally:
        await service.close()


async def _poll_sport_odds(sport_key: str):
    """Async implementation of poll_sport_odds."""
    service = OddsAPIService()

    try:
        events_data = await service.get_odds(sport_key)

        async with get_task_session() as session:
            # Get or create sport
            result = await session.execute(
                select(Sport).where(Sport.key == sport_key)
            )
            sport = result.scalar_one_or_none()

            if not sport:
                sport = Sport(
                    key=sport_key,
                    name=sport_key.replace("_", " ").title(),
                    active=True,
                )
                session.add(sport)
                await session.flush()

            total_snapshots = 0

            for event_data in events_data:
                commence_time = datetime.fromisoformat(
                    event_data["commence_time"].replace("Z", "+00:00")
                )

                event_status = "scheduled" if commence_time > datetime.now(timezone.utc) else "live"

                # ── Unified event matching via Event Registry ──
                from app.services.event_registry import (
                    find_or_create_event, EventIdentity, EventClaim,
                )
                identity = EventIdentity(
                    sport_key=sport_key,
                    home_team_name=event_data["home_team"],
                    away_team_name=event_data["away_team"],
                    commence_time=commence_time,
                    claim=EventClaim("odds_api", event_data["id"]),
                    commence_time_source="odds_api",
                    status=event_status,
                )
                event, was_created = await find_or_create_event(
                    session, identity,
                )
                event_id = event.id

                for bookmaker in event_data.get("bookmakers", []):
                    snapshot = await _create_snapshot(event_id, bookmaker, event_data)
                    session.add(snapshot)
                    total_snapshots += 1

            await session.commit()

        return {
            "sport": sport_key,
            "events": len(events_data),
            "snapshots": total_snapshots,
        }
    finally:
        await service.close()
