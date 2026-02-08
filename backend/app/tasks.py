"""
Celery tasks for background odds polling.

This module sets up periodic tasks to:
1. Fetch odds from The Odds API
2. Store events and snapshots in the database
3. Calculate probabilities

Tiered polling (optimized for 5M calls/month):
- Only polls sports with games starting within 6 hours
- Live games: Poll every 32 seconds
- Games starting in 0-2 hours: Poll every 60 seconds
- Games starting in 2-6 hours: Poll every 2 minutes
- No games in 6 hours: Don't poll that sport at all

Adaptive slowdown: If odds aren't changing, polling slows down automatically
to conserve API calls.

Estimated capacity: ~1.9 calls/second, ~166K calls/day.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

import redis
import sentry_sdk
from contextlib import asynccontextmanager

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select, func, case, or_, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.services.database import DATABASE_URL
from app.services.odds_api import OddsAPIService
from app.models import Sport, Event, OddsSnapshot, ScoreSnapshot
from app.utils.odds_math import moneyline_to_probability, project_scores

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Handle Heroku Redis SSL (rediss:// URLs require ssl_cert_reqs=None)
broker_use_ssl = None
if REDIS_URL.startswith("rediss://"):
    import ssl
    broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE,
    }

# Create Celery app
celery_app = Celery(
    "odds_tracker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 300,  # 5 minute timeout
    "worker_prefetch_multiplier": 1,
}

if broker_use_ssl:
    celery_config["broker_use_ssl"] = broker_use_ssl
    celery_config["redis_backend_use_ssl"] = broker_use_ssl

celery_app.conf.update(**celery_config)

# Initialize Sentry for Celery workers
# Set SENTRY_DSN env var in Heroku to enable
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=0.05,  # 5% of tasks for performance monitoring
        send_default_pii=False,
    )

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "poll-odds-adaptive": {
        "task": "app.tasks.poll_all_odds",
        "schedule": 30.0,  # Check every 30 seconds, but may skip based on adaptive logic
    },
    "sync-sports-hourly": {
        "task": "app.tasks.sync_sports",
        "schedule": crontab(minute=0),  # Every hour
    },
    "discover-new-events": {
        "task": "app.tasks.discover_events",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes - discover events for all sports
    },
    "compute-gei-batch": {
        "task": "app.tasks.compute_gei_batch",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes - compute GEI for newly completed events
        "kwargs": {"limit": 50},
    },
    "compute-gei-percentiles-hourly": {
        "task": "app.tasks.compute_gei_percentiles",
        "schedule": crontab(minute=5),  # Every hour at :05 (after GEI batch at :00/:10/etc)
    },
    "poll-futures-hourly": {
        "task": "app.tasks.poll_futures_odds",
        "schedule": crontab(minute=30),  # Every hour at :30 (offset from other tasks)
    },
    "poll-kalshi-hourly": {
        "task": "app.tasks.poll_kalshi_markets",
        "schedule": crontab(minute=45),  # Every hour at :45 (offset from futures polling)
    },
    "enrich-events-hourly": {
        "task": "app.tasks.enrich_events_metadata",
        "schedule": crontab(minute=20),  # Every hour at :20 (offset from other tasks)
        "kwargs": {"limit": 50},  # Process 50 events per run
    },
    "sync-espn-live": {
        "task": "app.tasks.sync_espn_live_events",
        "schedule": 60.0,  # Every 60 seconds for live game data (scores, clock, win prob)
    },
    "backfill-team-logos": {
        "task": "app.tasks.backfill_team_logos",
        "schedule": crontab(minute=15, hour="*/6"),  # Every 6 hours at :15
    },
    "reset-ad-baseline-kickoff": {
        "task": "app.tasks.reset_ad_baseline",
        "schedule": crontab(minute=0, hour=22, day_of_month=9, month_of_year=2),  # Feb 9 @ 2PM Pacific (22:00 UTC)
    },
}

# Adaptive polling state keys in Redis
POLL_STATE_KEY = "odds_tracker:poll_state"
LAST_ODDS_HASH_KEY = "odds_tracker:last_odds_hash"

# Polling intervals (in seconds)
# Tiered approach based on game proximity (optimized for 5M calls/month)
LIVE_POLL_INTERVAL = 32       # 32 seconds for live games (the main use case!)
SOON_POLL_INTERVAL = 60       # 1 minute for games starting in 0-2 hours
LATER_POLL_INTERVAL = 120     # 2 minutes for games starting in 2-6 hours

# Adaptive polling thresholds (for when odds aren't changing)
# When odds stay the same, gradually slow down to conserve API calls
FAST_POLL_INTERVAL = 60       # 1 minute when data is changing
MEDIUM_POLL_INTERVAL = 300    # 5 minutes after unchanged polls
SLOW_POLL_INTERVAL = 600      # 10 minutes after many unchanged polls

# Thresholds for slowing down
MEDIUM_THRESHOLD = 3   # Slow to medium after this many unchanged polls
SLOW_THRESHOLD = 6     # Slow to slow after this many unchanged polls

# Sport-specific max durations (in hours) for staleness detection
# Used to infer when a match has likely ended if odds go stale
SPORT_MAX_DURATIONS = {
    # Tennis can go very long, especially Grand Slam 5-setters
    "tennis": 6.0,
    # Most team sports are 2-4 hours
    "basketball": 3.5,
    "baseball": 5.0,  # Extra innings possible
    "americanfootball": 4.5,
    "icehockey": 3.5,
    "mma": 4.0,  # Full card duration
    "boxing": 3.0,
    "golf": 8.0,  # Round can be long
    "lacrosse": 3.0,
    # Default for unknown sports
    "default": 4.0,
}

# Staleness thresholds for marking events as "closed"
ODDS_STALE_MINUTES = 30  # Minutes without odds update to consider stale
MIN_HOURS_BEFORE_STALENESS_CHECK = 1.5  # Don't check staleness until match has been live this long


def get_redis_client():
    """Get Redis client with proper SSL handling for Heroku."""
    import ssl

    if REDIS_URL.startswith("rediss://"):
        # Heroku Redis with SSL
        return redis.from_url(
            REDIS_URL,
            ssl_cert_reqs=ssl.CERT_NONE
        )
    return redis.from_url(REDIS_URL)


def compute_odds_hash(events_data: list) -> str:
    """Compute hash of odds data to detect changes."""
    # Extract just the odds-relevant data
    odds_data = []
    for event in events_data:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    odds_data.append({
                        "event": event.get("id"),
                        "bookmaker": bookmaker.get("key"),
                        "market": market.get("key"),
                        "outcome": outcome.get("name"),
                        "price": outcome.get("price"),
                        "point": outcome.get("point"),
                    })

    # Sort for consistent ordering
    odds_data.sort(key=lambda x: (x["event"], x["bookmaker"], x["market"], x["outcome"]))

    # Hash the JSON representation
    data_str = json.dumps(odds_data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()


def should_poll_now() -> tuple[bool, str]:
    """
    Check if we should poll now based on adaptive logic.
    Returns (should_poll, reason).
    """
    try:
        r = get_redis_client()
        state = r.hgetall(POLL_STATE_KEY)

        if not state:
            # First poll ever
            return True, "first_poll"

        last_poll_time = float(state.get(b"last_poll_time", 0))
        unchanged_count = int(state.get(b"unchanged_count", 0))
        has_live_games = state.get(b"has_live_games", b"false") == b"true"

        elapsed = time.time() - last_poll_time

        # Always poll frequently for live games
        if has_live_games:
            if elapsed >= LIVE_POLL_INTERVAL:
                return True, "live_games"
            return False, f"live_wait_{int(LIVE_POLL_INTERVAL - elapsed)}s"

        # Determine interval based on unchanged count
        if unchanged_count >= SLOW_THRESHOLD:
            interval = SLOW_POLL_INTERVAL
        elif unchanged_count >= MEDIUM_THRESHOLD:
            interval = MEDIUM_POLL_INTERVAL
        else:
            interval = FAST_POLL_INTERVAL

        if elapsed >= interval:
            return True, f"interval_{interval}s"

        return False, f"wait_{int(interval - elapsed)}s"

    except Exception as e:
        # If Redis fails, default to polling
        print(f"Redis error in should_poll_now: {e}")
        return True, "redis_error"


def update_poll_state(data_changed: bool, has_live_games: bool, new_hash: str):
    """Update the adaptive polling state in Redis."""
    try:
        r = get_redis_client()

        # Get current unchanged count
        current_count = int(r.hget(POLL_STATE_KEY, "unchanged_count") or 0)

        if data_changed:
            new_count = 0
        else:
            new_count = current_count + 1

        r.hset(POLL_STATE_KEY, mapping={
            "last_poll_time": time.time(),
            "unchanged_count": new_count,
            "has_live_games": "true" if has_live_games else "false",
            "last_hash": new_hash,
        })

        # Set expiry so state cleans up if worker stops
        r.expire(POLL_STATE_KEY, 3600)  # 1 hour

    except Exception as e:
        print(f"Redis error in update_poll_state: {e}")


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
    from datetime import timedelta

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
                print(f"Marked event {event.id} ({event.home_team_name} vs {event.away_team_name}) "
                      f"as closed: {close_reason}, {hours_since_start:.1f}h since start")

        except Exception as e:
            print(f"Error checking staleness for event {event.id}: {e}")
            continue

    return closed_count


def _get_task_engine():
    """Create a fresh async engine for Celery task execution.

    This creates a new engine that's bound to the current event loop,
    avoiding the 'attached to a different loop' errors when reusing
    the module-level engine across Celery task invocations.
    """
    connect_args = {}
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        connect_args["ssl"] = "require"

    return create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@asynccontextmanager
async def get_task_session():
    """Create a fresh async session for Celery task execution.

    This creates a new engine and session maker bound to the current
    event loop, avoiding conflicts between Celery's forked processes
    and asyncio event loops.
    """
    engine = _get_task_engine()
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    await engine.dispose()


def run_async(coro):
    """Helper to run async code in sync context.

    Uses asyncio.run() which properly manages the event loop lifecycle,
    ensuring clean startup and shutdown of the loop and any pending tasks.
    """
    return asyncio.run(coro)


@celery_app.task(bind=True, max_retries=3)
def sync_sports(self):
    """
    Sync available sports from The Odds API to database.

    This creates/updates Sport records for each sport
    returned by the API.
    """
    try:
        return run_async(_sync_sports())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _sync_sports():
    """Async implementation of sync_sports."""
    service = OddsAPIService()

    try:
        sports_data = await service.get_sports()

        async with get_task_session() as session:
            synced = 0
            for sport in sports_data:
                if not sport.get("active", False):
                    continue

                # Upsert sport
                stmt = insert(Sport).values(
                    key=sport["key"],
                    name=sport["title"],
                    group=sport.get("group"),
                    active=True,
                ).on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "name": sport["title"],
                        "group": sport.get("group"),
                        "active": True,
                    }
                )
                await session.execute(stmt)
                synced += 1

            await session.commit()

        return {"synced": synced}
    finally:
        await service.close()


@celery_app.task(bind=True, max_retries=3)
def discover_events(self):
    """
    Discover events for ALL active sports, including those with no events yet.

    This solves the chicken-and-egg problem where sports without events
    never get polled. Runs every 15 minutes to pick up new games.
    """
    try:
        return run_async(_discover_events())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


async def _discover_events():
    """
    Async implementation of discover_events.

    Polls ALL active sports (not just those with upcoming events) to discover
    new games. This ensures NCAA basketball, etc. get picked up even if they
    currently have no events in the database.
    """
    service = OddsAPIService()

    try:
        total_events = 0
        total_new_events = 0
        sports_polled = 0

        async with get_task_session() as session:
            # Get ALL active sports (not filtering by existing events)
            result = await session.execute(
                select(Sport).where(Sport.active == True)
            )
            sports = result.scalars().all()

            for sport in sports:
                sport_key = sport.key

                try:
                    # Fetch odds for this sport
                    events_data = await service.get_odds(sport_key)
                    sports_polled += 1

                    for event_data in events_data:
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        # Determine event status
                        now = datetime.now(timezone.utc)
                        if commence_time <= now:
                            event_status = "live"
                        else:
                            event_status = "scheduled"

                        # Upsert event
                        stmt = insert(Event).values(
                            external_id=event_data["id"],
                            sport_id=sport.id,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            status=event_status,
                        ).on_conflict_do_update(
                            index_elements=["external_id"],
                            set_={
                                "home_team_name": event_data["home_team"],
                                "away_team_name": event_data["away_team"],
                                # Don't overwrite commence_time — The Odds API occasionally
                                # returns local times as UTC. ESPN sync corrects these.
                                "status": case(
                                    (Event.status == "scheduled", event_status),
                                    else_=Event.status
                                ),
                            }
                        ).returning(Event.id)

                        result = await session.execute(stmt)
                        event_id = result.scalar_one()
                        total_events += 1

                        # Check if this was a new event (simple heuristic)
                        # If the event has no snapshots, it's likely new
                        snapshot_check = await session.execute(
                            select(func.count(OddsSnapshot.id))
                            .where(OddsSnapshot.event_id == event_id)
                        )
                        if snapshot_check.scalar() == 0:
                            total_new_events += 1

                        # Also save odds snapshots for this event
                        # This ensures events discovered have odds data immediately
                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot, is_new = await _create_or_update_snapshot(
                                session,
                                event_id,
                                bookmaker,
                                event_data
                            )
                            if is_new:
                                session.add(snapshot)

                except Exception as e:
                    # Log but continue with other sports
                    print(f"Error discovering events for {sport_key}: {e}")
                    continue

            await session.commit()

        return {
            "sports_polled": sports_polled,
            "events_found": total_events,
            "new_events": total_new_events,
        }
    finally:
        await service.close()


@celery_app.task(bind=True, max_retries=3)
def poll_all_odds(self):
    """
    Poll odds for all configured sports with adaptive polling.

    This fetches current odds from The Odds API and stores
    them as OddsSnapshot records. Polling frequency adapts based on:
    - Whether odds have changed recently
    - Whether any games are currently live
    """
    # Check if we should poll based on adaptive logic
    should_poll, reason = should_poll_now()

    if not should_poll:
        return {"skipped": True, "reason": reason}

    try:
        result = run_async(_poll_all_odds())
        return {**result, "poll_reason": reason}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


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
            from datetime import timedelta
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
                    # Live game - poll every 60 seconds
                    poll_interval = LIVE_POLL_INTERVAL
                    tier = "live"
                    has_live_games = True
                elif soonest_game and soonest_game <= now + timedelta(hours=2):
                    # Starting soon (0-2 hours) - poll every 5 minutes
                    poll_interval = SOON_POLL_INTERVAL
                    tier = "soon"
                else:
                    # Starting later (2-6 hours) - poll every 15 minutes
                    poll_interval = LATER_POLL_INTERVAL
                    tier = "later"

                # Check if enough time has elapsed since last poll for this sport
                should_poll_sport = True
                if r:
                    try:
                        last_poll_key = f"odds_tracker:last_poll:{sport_key}"
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

                try:
                    events_data = await service.get_odds(sport_key)
                    all_events_data.extend(events_data)
                    sports_polled += 1

                    # Update last poll time in Redis
                    if r:
                        try:
                            last_poll_key = f"odds_tracker:last_poll:{sport_key}"
                            r.set(last_poll_key, str(now.timestamp()), ex=3600)
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

                        # Upsert event with conditional status update
                        # - New events: set status based on commence_time
                        # - Existing "scheduled" events: update to "live" if started
                        # - Existing "live"/"completed" events: don't change status
                        event_status = "scheduled" if commence_time > now else "live"
                        stmt = insert(Event).values(
                            external_id=event_data["id"],
                            sport_id=sport.id,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=commence_time,
                            status=event_status,
                        ).on_conflict_do_update(
                            index_elements=["external_id"],
                            set_={
                                "home_team_name": event_data["home_team"],
                                "away_team_name": event_data["away_team"],
                                # Don't overwrite commence_time — The Odds API occasionally
                                # returns local times as UTC. ESPN sync corrects these.
                                # Only update status if currently "scheduled"
                                # This allows scheduled->live but preserves completed
                                "status": case(
                                    (Event.status == "scheduled", event_status),
                                    else_=Event.status
                                ),
                            }
                        ).returning(Event.id)

                        result = await session.execute(stmt)
                        event_id = result.scalar_one()
                        total_events += 1

                        # Create odds snapshots (with deduplication)
                        # Track values for setting opening odds
                        first_home_prob = None
                        first_away_prob = None
                        first_spread = None
                        first_ou = None

                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot, is_new = await _create_or_update_snapshot(
                                session,
                                event_id,
                                bookmaker,
                                event_data
                            )
                            if is_new:
                                session.add(snapshot)
                                # Capture first valid odds for opening odds
                                if first_home_prob is None and snapshot.home_win_probability:
                                    first_home_prob = float(snapshot.home_win_probability)
                                    first_away_prob = float(snapshot.away_win_probability) if snapshot.away_win_probability else None
                                    first_spread = float(snapshot.home_spread) if snapshot.home_spread else None
                                    first_ou = float(snapshot.over_under) if snapshot.over_under else None
                            total_snapshots += 1

                        # Set opening odds if this is the first time we have odds
                        if first_home_prob is not None:
                            await _maybe_set_opening_odds(
                                session, event_id,
                                first_home_prob, first_away_prob,
                                first_spread, first_ou
                            )

                except Exception as e:
                    print(f"Error polling {sport_key}: {e}")
                    continue

            # Fetch scores for sports with events that have started
            # Use a 3-day window to capture longer events like tennis matches
            # that may start one day and finish the next
            # Include "scheduled" events that have started - the scores API will
            # update their status to "live" or "completed" as appropriate
            sports_needing_scores = await session.execute(
                select(Sport.key)
                .join(Event)
                .where(
                    Sport.active == True,
                    Event.commence_time <= now,  # Event has started
                    Event.commence_time >= now - timedelta(days=3),  # Within last 3 days
                    Event.status.in_(["scheduled", "live", "completed"]),  # Include scheduled events that started
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

                            # Always update status, and update scores if available
                            event_status = "completed" if is_completed else "live"
                            update_values = {"status": event_status}

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

                            await session.execute(
                                Event.__table__.update()
                                .where(Event.external_id == external_id)
                                .values(**update_values)
                            )
                            scores_updated += 1

                            # Compute stat model for live events with score + clock data
                            # This runs independently of ESPN sync, so games that
                            # ESPN name-matching misses still get stat model WP
                            if (
                                event_obj
                                and event_status == "live"
                                and home_score is not None
                                and away_score is not None
                                and event_obj.game_clock
                                and event_obj.period
                            ):
                                try:
                                    from app.utils.win_probability import compute_statistical_win_prob
                                    from app.models.models import WinProbSnapshot

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

                                            stat_snap = WinProbSnapshot(
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
                                                },
                                            )
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
):
    """
    Set opening odds on an event if they haven't been set yet.

    Opening odds are only set once (first time we receive odds for an event).
    They're used to detect favorite switches, line movement, etc.
    """
    if home_prob is None:
        return

    # Check if opening odds already set
    result = await session.execute(
        select(Event.opening_home_probability)
        .where(Event.id == event_id)
    )
    current_opening = result.scalar_one_or_none()

    if current_opening is not None:
        # Already set, don't update
        return

    # Determine opening favorite
    if home_prob > 0.52:
        opening_favorite = "home"
    elif home_prob < 0.48:
        opening_favorite = "away"
    else:
        opening_favorite = "even"

    # Set opening odds
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


@celery_app.task(bind=True)
def poll_sport_odds(self, sport_key: str):
    """
    Poll odds for a single sport.

    Useful for manual triggering or prioritizing specific sports.
    """
    return run_async(_poll_sport_odds(sport_key))


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
                stmt = insert(Event).values(
                    external_id=event_data["id"],
                    sport_id=sport.id,
                    home_team_name=event_data["home_team"],
                    away_team_name=event_data["away_team"],
                    commence_time=commence_time,
                    status=event_status,
                ).on_conflict_do_update(
                    index_elements=["external_id"],
                    set_={
                        "home_team_name": event_data["home_team"],
                        "away_team_name": event_data["away_team"],
                        # Don't overwrite commence_time — The Odds API occasionally
                        # returns local times as UTC. ESPN sync corrects these.
                        # Only update status if currently "scheduled"
                        "status": case(
                            (Event.status == "scheduled", event_status),
                            else_=Event.status
                        ),
                    }
                ).returning(Event.id)

                result = await session.execute(stmt)
                event_id = result.scalar_one()

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


# =============================================================================
# Pulse - Live Game Excitement Metric
# =============================================================================


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


@celery_app.task(bind=True)
def compute_gei_for_event(self, event_id: int):
    """
    Compute GEI for a single completed event.

    Called after an event is marked as completed.
    """
    return run_async(_compute_gei_for_event(event_id))


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


@celery_app.task(bind=True)
def compute_gei_batch(self, limit: int = 100):
    """
    Compute Pulse for a batch of completed events.

    Useful for backfilling historical events.
    """
    return run_async(_compute_pulse_batch(limit))


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


@celery_app.task(bind=True)
def compute_gei_percentiles(self):
    """
    Recompute GEI percentile thresholds for all scopes.

    Should be run daily (or after significant new data).
    """
    return run_async(_compute_gei_percentiles())


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


# =============================================================================
# Futures Polling
# =============================================================================

# Futures poll less frequently since they change slowly
FUTURES_POLL_INTERVAL = 3600  # 1 hour default


@celery_app.task(bind=True)
def poll_futures_odds(self):
    """
    Poll futures/outrights odds from The Odds API.

    Futures markets change slowly, so we poll hourly by default.
    Updates existing markets/outcomes or creates new ones.
    """
    return run_async(_poll_futures_odds())


async def _poll_futures_odds():
    """Async implementation of futures polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.utils.odds_math import american_to_probability, probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import timedelta

    service = OddsAPIService()
    stats = {
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Discover sports with outrights
        outright_sports = await service.get_sports_with_outrights()
        sport_keys = [s["key"] for s in outright_sports]

        async with get_task_session() as session:
            # Get or create sport records for linking
            sport_result = await session.execute(
                select(Sport.id, Sport.key)
            )
            sport_map = {row.key: row.id for row in sport_result.all()}

            for sport_key in sport_keys:
                try:
                    api_response = await service.get_futures_odds(sport_key)
                    markets_data = service._parse_futures(api_response, sport_key)

                    if not markets_data:
                        continue

                    # Get market name from first result
                    market_name = markets_data[0].market_name if markets_data else sport_key

                    # Find or infer the base sport for linking
                    # e.g., "basketball_nba_championship" -> "basketball_nba"
                    base_sport_key = _infer_base_sport(sport_key)
                    sport_id = sport_map.get(base_sport_key)

                    # Upsert the market
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="odds_api",
                        external_id=sport_key,
                        sport_id=sport_id,
                        name=market_name,
                        category=_infer_category(sport_key),
                        mutually_exclusive=True,
                        status="open",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": market_name,
                            "sport_id": sport_id,  # Update sport link on every sync
                            "updated_at": func.now(),
                        }
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    market_id = result.scalar_one()
                    stats["markets_processed"] += 1

                    # Aggregate outcomes across bookmakers
                    outcome_odds = _aggregate_futures_outcomes(markets_data)

                    # Get existing outcomes for this market
                    existing_result = await session.execute(
                        select(FuturesOutcome)
                        .where(FuturesOutcome.market_id == market_id)
                    )
                    existing_outcomes = {o.external_id: o for o in existing_result.scalars().all()}

                    # Compute ranks (1 = highest probability)
                    ranked_outcomes = sorted(
                        outcome_odds.items(),
                        key=lambda x: x[1]["probability"],
                        reverse=True
                    )

                    now = datetime.now(timezone.utc)
                    yesterday = now - timedelta(hours=24)

                    for rank, (outcome_name, odds_data) in enumerate(ranked_outcomes, 1):
                        prob = odds_data["probability"]
                        american = probability_to_american(prob)

                        # Check if outcome exists
                        existing = existing_outcomes.get(outcome_name)

                        if existing:
                            # Calculate 24h change
                            old_prob = float(existing.current_probability) if existing.current_probability else None
                            prob_change = prob - old_prob if old_prob else None

                            old_rank = existing.rank
                            rank_change = old_rank - rank if old_rank else None

                            # Update existing outcome
                            existing.current_probability = prob
                            existing.current_american_odds = american
                            existing.probability_change_24h = prob_change
                            existing.rank = rank
                            existing.rank_change_24h = rank_change
                            existing.last_updated = now

                            # Set opening odds if not set
                            if existing.opening_probability is None:
                                existing.opening_probability = prob
                                existing.opening_american_odds = american
                                existing.opening_captured_at = now

                            outcome_id = existing.id
                        else:
                            # Create new outcome
                            outcome_stmt = pg_insert(FuturesOutcome).values(
                                market_id=market_id,
                                external_id=outcome_name,
                                name=outcome_name,
                                current_probability=prob,
                                current_american_odds=american,
                                opening_probability=prob,
                                opening_american_odds=american,
                                opening_captured_at=now,
                                rank=rank,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_={
                                    "current_probability": prob,
                                    "current_american_odds": american,
                                    "rank": rank,
                                    "last_updated": func.now(),
                                }
                            ).returning(FuturesOutcome.id)

                            result = await session.execute(outcome_stmt)
                            outcome_id = result.scalar_one()

                        stats["outcomes_updated"] += 1

                        # Create snapshots for each bookmaker
                        for bookmaker, bm_odds in odds_data["bookmakers"].items():
                            snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                                outcome_id=outcome_id,
                                bookmaker=bookmaker,
                                probability=bm_odds["probability"],
                                american_odds=bm_odds["american_odds"],
                                captured_at=now,
                            )
                            await session.execute(snapshot_stmt)
                            stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    return stats


def _infer_base_sport(sport_key: str) -> str:
    """Infer the base sport key from a futures sport key.

    Examples:
        basketball_nba_championship_winner -> basketball_nba
        americanfootball_nfl_super_bowl_winner -> americanfootball_nfl
        baseball_mlb_world_series_winner -> baseball_mlb
        icehockey_nhl_championship_winner -> icehockey_nhl
        soccer_epl_winner -> soccer_epl
    """
    # Common futures suffixes to strip (order matters - longer/compound first)
    suffixes = [
        # Compound suffixes (must come first)
        "_championship_winner",
        "_super_bowl_winner",
        "_world_series_winner",
        "_stanley_cup_winner",
        "_division_winner",
        "_conference_winner",
        # Simple suffixes
        "_championship",
        "_winner",
        "_mvp",
    ]

    result = sport_key

    # Keep stripping suffixes until no more match
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if result.endswith(suffix):
                result = result[:-len(suffix)]
                changed = True
                break  # Restart from beginning after each strip

    return result


def _infer_category(sport_key: str) -> str:
    """Infer the market category from the sport key."""
    key_lower = sport_key.lower()

    if "championship" in key_lower or "winner" in key_lower:
        return "championship"
    elif "mvp" in key_lower:
        return "mvp"
    elif "division" in key_lower:
        return "division"
    elif "conference" in key_lower:
        return "conference"
    else:
        return "other"


def _aggregate_futures_outcomes(markets_data) -> dict:
    """Aggregate outcome odds across multiple bookmakers.

    Normalizes each bookmaker's implied probabilities to remove the vig
    (overround) before averaging across bookmakers. Without normalization,
    implied probabilities from American odds sum to >100% (often 130-150%
    for markets with many outcomes), inflating every outcome's probability.

    Returns a dict mapping outcome names to aggregated data:
    {
        "Lakers": {
            "probability": 0.11,  # Average of vig-removed probs across books
            "bookmakers": {
                "draftkings": {"probability": 0.14, "american_odds": 600},
                "fanduel": {"probability": 0.16, "american_odds": 525},
            }
        }
    }
    """
    from statistics import mean
    from collections import defaultdict

    # First pass: group outcomes by bookmaker to calculate per-bookmaker totals
    bookmaker_outcomes = defaultdict(list)  # bookmaker -> [(name, probability, american_odds)]

    for market in markets_data:
        bookmaker = market.bookmaker
        for outcome in market.outcomes:
            bookmaker_outcomes[bookmaker].append(
                (outcome.name, outcome.probability, outcome.american_odds)
            )

    # Second pass: normalize each bookmaker's probabilities to sum to 1.0
    # This removes the vig/overround
    outcomes = {}

    for bookmaker, bm_outcomes in bookmaker_outcomes.items():
        total_prob = sum(prob for _, prob, _ in bm_outcomes)

        for name, raw_prob, american_odds in bm_outcomes:
            # Normalize: divide by total so all outcomes sum to 1.0
            normalized_prob = raw_prob / total_prob if total_prob > 0 else raw_prob

            if name not in outcomes:
                outcomes[name] = {
                    "normalized_probabilities": [],
                    "bookmakers": {},
                }

            outcomes[name]["normalized_probabilities"].append(normalized_prob)
            outcomes[name]["bookmakers"][bookmaker] = {
                "probability": raw_prob,  # Keep raw implied prob for bookmaker display
                "american_odds": american_odds,
            }

    # Calculate average normalized probability for each outcome
    result = {}
    for name, data in outcomes.items():
        result[name] = {
            "probability": mean(data["normalized_probabilities"]),
            "bookmakers": data["bookmakers"],
        }

    return result


# =============================================================================
# Kalshi Polling
# =============================================================================


@celery_app.task(bind=True)
def poll_kalshi_markets(self):
    """
    Poll prediction markets from Kalshi.

    Kalshi provides structured event data including timing information
    and bid/ask spreads for prediction markets.
    """
    return run_async(_poll_kalshi_markets())


async def _poll_kalshi_markets():
    """Async implementation of Kalshi polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.kalshi_api import KalshiAPIService
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import os

    # Check if Kalshi API key is configured
    if not os.getenv("KALSHI_API_KEY"):
        return {"status": "skipped", "reason": "KALSHI_API_KEY not configured"}

    service = KalshiAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Only fetch sports-related categories to stay within rate limits
        # Kalshi has thousands of politics/economics markets we don't need
        sports_categories = ["Sports", "Golf", "Football", "Basketball", "Baseball", "Hockey", "Tennis"]
        events = await service.get_all_events(categories=sports_categories)

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            for event in events:
                try:
                    # Each Kalshi event can have multiple markets
                    # For multivariate events, we create one FuturesMarket per event
                    # with outcomes for each market within

                    if not event.markets:
                        continue

                    # Determine category based on Kalshi's category
                    category = _kalshi_category_to_internal(event.category)

                    # For events with multiple markets (multivariate), create one FuturesMarket
                    # For single-market events, use the market directly
                    if len(event.markets) == 1:
                        market = event.markets[0]
                        market_name = event.title
                        commence_time = market.close_time  # When trading ends
                        expiration_time = market.expiration_time
                    else:
                        market_name = event.title
                        # Use earliest close time from all markets
                        close_times = [m.close_time for m in event.markets if m.close_time]
                        commence_time = min(close_times) if close_times else None
                        expiration_times = [m.expiration_time for m in event.markets if m.expiration_time]
                        expiration_time = max(expiration_times) if expiration_times else None

                    # Upsert the FuturesMarket
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="kalshi",
                        external_id=event.event_ticker,
                        name=market_name,
                        category=category,
                        mutually_exclusive=event.mutually_exclusive,
                        commence_time=commence_time,
                        resolution_date=expiration_time,
                        status="open",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": market_name,
                            "commence_time": commence_time,
                            "resolution_date": expiration_time,
                            "updated_at": func.now(),
                        }
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    futures_market_id = result.scalar_one()
                    stats["events_processed"] += 1

                    # First pass: compute probabilities and names for all outcomes
                    outcome_data = []
                    for market in event.markets:
                        # Calculate probability from bid/ask midpoint or last price
                        if market.yes_bid is not None and market.yes_ask is not None:
                            prob = (market.yes_bid + market.yes_ask) / 2
                        elif market.last_price is not None:
                            prob = market.last_price
                        else:
                            continue  # Skip markets without pricing

                        american = probability_to_american(prob) if prob and prob > 0 else None

                        # For single-market events, use "Yes" as outcome name
                        # For multi-market events, prefer yes_sub_title (player/team name),
                        # then subtitle, then title if it differs from event title,
                        # then parsed ticker as last resort
                        if len(event.markets) == 1:
                            outcome_name = "Yes"
                        else:
                            if market.yes_sub_title:
                                outcome_name = market.yes_sub_title
                            elif market.subtitle:
                                outcome_name = market.subtitle
                            elif market.title and market.title != event.title:
                                outcome_name = market.title
                            else:
                                # Extract name from ticker (e.g. "COTY-24-BELICHICK" -> "Belichick")
                                outcome_name = _parse_kalshi_ticker_name(market.ticker)

                        outcome_data.append({
                            "market": market,
                            "prob": prob,
                            "american": american,
                            "outcome_name": outcome_name,
                        })

                    # Sort by probability descending to compute ranks (1 = highest)
                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Second pass: upsert outcomes with correct probability-based ranks
                    for rank, od in enumerate(outcome_data, 1):
                        market = od["market"]
                        prob = od["prob"]
                        american = od["american"]
                        outcome_name = od["outcome_name"]
                        stats["markets_processed"] += 1

                        # Upsert outcome
                        outcome_stmt = pg_insert(FuturesOutcome).values(
                            market_id=futures_market_id,
                            external_id=market.ticker,
                            name=outcome_name,
                            current_probability=prob,
                            current_american_odds=american,
                            current_yes_bid=market.yes_bid,
                            current_yes_ask=market.yes_ask,
                            opening_probability=prob,
                            opening_american_odds=american,
                            opening_captured_at=now,
                            rank=rank,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_={
                                "name": outcome_name,
                                "current_probability": prob,
                                "current_american_odds": american,
                                "current_yes_bid": market.yes_bid,
                                "current_yes_ask": market.yes_ask,
                                "rank": rank,
                                "last_updated": func.now(),
                            }
                        ).returning(FuturesOutcome.id)

                        result = await session.execute(outcome_stmt)
                        outcome_id = result.scalar_one()
                        stats["outcomes_updated"] += 1

                        # Create snapshot with Kalshi-specific data
                        snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                            outcome_id=outcome_id,
                            bookmaker="kalshi",
                            probability=prob,
                            american_odds=american,
                            yes_bid=market.yes_bid,
                            yes_ask=market.yes_ask,
                            last_price=market.last_price,
                            captured_at=now,
                        )
                        await session.execute(snapshot_stmt)
                        stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{event.event_ticker}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    return stats


def _parse_kalshi_ticker_name(ticker: str) -> str:
    """Extract a human-readable name from a Kalshi market ticker.

    Kalshi tickers look like 'KXCOTY-24-BELICHICK' or 'NBACHAMP-BOS'.
    We take the last segment that isn't purely numeric and title-case it.
    """
    if not ticker:
        return "Unknown"
    parts = ticker.split("-")
    # Walk backwards to find the last non-numeric segment
    for part in reversed(parts):
        if part and not part.isdigit():
            # Title-case and return (e.g. "BELICHICK" -> "Belichick")
            return part.title()
    return ticker


def _kalshi_category_to_internal(kalshi_category: Optional[str]) -> str:
    """Map Kalshi category to internal category."""
    if not kalshi_category:
        return "other"

    category_lower = kalshi_category.lower()

    # Sports categories
    if any(s in category_lower for s in ["sports", "golf", "football", "basketball", "baseball", "hockey", "soccer"]):
        return "championship"

    # Other categories
    if "politic" in category_lower or "election" in category_lower:
        return "politics"
    if "econom" in category_lower or "fed" in category_lower or "inflation" in category_lower:
        return "economics"
    if "entertainment" in category_lower or "movie" in category_lower or "award" in category_lower:
        return "entertainment"
    if "tech" in category_lower or "crypto" in category_lower:
        return "tech"

    return "other"


# ============================================================================
# LLM Metadata Enrichment Task
# ============================================================================


@celery_app.task(bind=True)
def enrich_events_metadata(self, limit: int = 50):
    """
    Enrich events with LLM-generated metadata (gender, level, league, importance).

    This task runs periodically to classify new events that don't have metadata yet.
    Uses heuristics first, falling back to LLM for ambiguous cases.

    Args:
        limit: Maximum number of events to process per run

    Returns:
        Dict with enrichment statistics
    """
    return run_async(_enrich_events_metadata(limit))


async def _enrich_events_metadata(limit: int = 50):
    """Async implementation of enrich_events_metadata."""
    from app.services import llm
    from app.models.models import Event
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stats = {
        "processed": 0,
        "enriched": 0,
        "errors": 0,
        "remaining": 0,
        "llm_available": llm.is_available(),
    }

    try:
        async with get_task_session() as session:
            # Find events without metadata (prioritize recent events)
            result = await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    Event.llm_gender.is_(None),
                    Event.llm_level.is_(None),
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            events = result.scalars().all()

            if not events:
                remaining_result = await session.execute(
                    select(Event.id).where(
                        Event.llm_gender.is_(None),
                        Event.llm_level.is_(None),
                    )
                )
                stats["remaining"] = len(remaining_result.all())
                return stats

            for event in events:
                try:
                    sport_key = event.sport.key if event.sport else None
                    text = f"{event.away_team_name} at {event.home_team_name}"

                    # Classify using heuristics + LLM fallback
                    event.llm_gender = llm.classify_gender_cached(text, sport_key)
                    event.llm_level = llm.classify_level_cached(text, sport_key)
                    event.llm_league = llm.classify_league_cached(text, sport_key)
                    event.llm_importance = llm.classify_importance_cached(text, sport_key)

                    stats["enriched"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    if stats["errors"] <= 5:
                        print(f"Error enriching event {event.id}: {e}")

                stats["processed"] += 1

            # Count remaining
            remaining_result = await session.execute(
                select(Event.id).where(
                    Event.llm_gender.is_(None),
                    Event.llm_level.is_(None),
                )
            )
            stats["remaining"] = len(remaining_result.all())

    except Exception as e:
        print(f"Enrichment task error: {e}")
        stats["errors"] += 1

    return stats


# ============================================================================
# ESPN Live Sync Task
# ============================================================================


# ESPN sport key mapping (our sport_key -> ESPN sport identifier)
ESPN_SPORT_MAPPING = {
    "basketball_nba": "basketball/nba",
    "basketball_ncaab": "basketball/mens-college-basketball",
    "basketball_wncaab": "basketball/womens-college-basketball",
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "icehockey_nhl": "hockey/nhl",
    "baseball_mlb": "baseball/mlb",
    "soccer_usa_mls": "soccer/usa.1",
    "soccer_epl": "soccer/eng.1",
}


@celery_app.task(bind=True)
def sync_espn_live_events(self):
    """
    Sync live event data from ESPN for all sports with active games.

    This task runs every 60 seconds to keep scores, clock, period,
    and win probability updated for live games.

    Returns:
        Dict with sync statistics
    """
    return run_async(_sync_espn_live_events())


async def _sync_espn_live_events():
    """Async implementation of sync_espn_live_events."""
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport, Team, ESPNSnapshot
    from sqlalchemy import select, distinct
    from sqlalchemy.orm import selectinload

    stats = {
        "sports_checked": 0,
        "sports_with_live": 0,
        "events_synced": 0,
        "events_updated": 0,
        "errors": [],
    }

    def _normalize_name(name: str) -> str:
        """Normalize team name for matching — strip accents, unify quotes/apostrophes."""
        import unicodedata
        # Normalize unicode (NFD decomposition) then strip combining marks (accents)
        normalized = unicodedata.normalize("NFD", name)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Unify all apostrophe/quote variants to standard ASCII apostrophe
        for ch in ("\u2018", "\u2019", "\u02BB", "\u02BC", "\u0060", "\u00B4", "\u2032"):
            normalized = normalized.replace(ch, "'")
        return normalized.lower().strip()

    def names_match(our_names: list, espn_name: str) -> bool:
        """Name matching with unicode normalization — check if any name is a substring of the other."""
        espn_lower = _normalize_name(espn_name or "")
        for name in our_names:
            name_lower = _normalize_name(name)
            if name_lower in espn_lower or espn_lower in name_lower:
                return True
        return False

    async def upsert_team(session, team_name, espn_team, sport_id):
        """Create or update a Team record with ESPN enrichment data."""
        if not espn_team:
            return
        team_result = await session.execute(
            select(Team).where(
                Team.name == team_name,
                Team.sport_id == sport_id,
            )
        )
        team = team_result.scalar_one_or_none()

        if not team:
            team = Team(
                name=team_name,
                sport_id=sport_id,
            )
            session.add(team)

        # Update ESPN fields
        team.espn_id = espn_team.espn_id
        if espn_team.abbreviation:
            team.abbreviation = espn_team.abbreviation
        if espn_team.primary_color:
            color = espn_team.primary_color
            if not color.startswith("#"):
                color = f"#{color}"
            team.primary_color = color
        if espn_team.secondary_color:
            color = espn_team.secondary_color
            if not color.startswith("#"):
                color = f"#{color}"
            team.secondary_color = color
        if espn_team.logo_url:
            team.logo_url_small = espn_team.logo_url
            team.logo_url_large = espn_team.logo_url
        if espn_team.record:
            team.current_record = espn_team.record

        # Store alternate names for lookup
        alt_names = set()
        for n in [espn_team.display_name, espn_team.short_name, espn_team.nickname, espn_team.name]:
            if n and n != team_name:
                alt_names.add(n)
        if alt_names:
            existing = set(team.alternate_names or [])
            team.alternate_names = list(existing | alt_names)

        stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1

    def get_event_name_variations(event):
        """Get all name variations for an event's teams."""
        home_names = [event.home_team_name]
        away_names = [event.away_team_name]
        if event.home_team_normalized:
            home_names.append(event.home_team_normalized)
        if event.away_team_normalized:
            away_names.append(event.away_team_normalized)
        if event.home_team_alt_names:
            home_names.extend(event.home_team_alt_names)
        if event.away_team_alt_names:
            away_names.extend(event.away_team_alt_names)
        return home_names, away_names

    try:
        async with get_task_session() as session:
            # Find sports with live games
            live_sports_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(Event.status == "live")
            )
            live_sport_keys = [row[0] for row in live_sports_result.all()]

            if not live_sport_keys:
                return {"status": "no_live_games", **stats}

            stats["sports_with_live"] = len(live_sport_keys)

            # Also find sports with scheduled games for team data pre-population
            scheduled_sports_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(Event.status == "scheduled")
            )
            scheduled_sport_keys = [row[0] for row in scheduled_sports_result.all()]

            # Collect all ESPN-mapped sport keys to fetch
            all_fetch_keys = set()
            for k in live_sport_keys:
                if k in ESPN_SPORT_MAPPING:
                    all_fetch_keys.add(k)
            for k in scheduled_sport_keys:
                if k in ESPN_SPORT_MAPPING:
                    all_fetch_keys.add(k)

            if not all_fetch_keys:
                return {"status": "no_espn_mapped_sports", **stats}

            # Fetch all ESPN scoreboards
            espn = ESPNAPIService()
            espn_data = {}
            try:
                for key in all_fetch_keys:
                    try:
                        events = await espn.get_scoreboard(key)
                        espn_data[key] = events or []
                    except Exception as e:
                        stats["errors"].append(f"espn_fetch_{key}: {str(e)}")
                        espn_data[key] = []
            finally:
                await espn.close()

            # Process live events
            for sport_key in live_sport_keys:
                stats["sports_checked"] += 1

                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue

                try:
                    events_result = await session.execute(
                        select(Event)
                        .options(selectinload(Event.sport))
                        .where(
                            Event.sport.has(key=sport_key),
                            Event.status == "live",
                        )
                    )
                    our_events = events_result.scalars().all()

                    for event in our_events:
                        home_names, away_names = get_event_name_variations(event)

                        for ee in espn_events:
                            if not ee.home_team or not ee.away_team:
                                continue

                            espn_home = ee.home_team.display_name or ee.home_team.name or ""
                            espn_away = ee.away_team.display_name or ee.away_team.name or ""

                            if names_match(home_names, espn_home) and names_match(away_names, espn_away):
                                stats["events_synced"] += 1
                                changed = False

                                # Upsert team records with ESPN data (colors, logos)
                                await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                                await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)

                                # Update ESPN ID
                                if ee.espn_id and event.espn_id != ee.espn_id:
                                    event.espn_id = ee.espn_id
                                    changed = True

                                # Correct commence_time from ESPN if significantly different
                                # The Odds API occasionally returns local times as UTC
                                if ee.date and event.commence_time:
                                    time_diff = abs((ee.date - event.commence_time).total_seconds())
                                    if time_diff > 300:  # > 5 minutes difference
                                        print(
                                            f"ESPN: Correcting commence_time for event {event.id} "
                                            f"({event.home_team_name} vs {event.away_team_name}): "
                                            f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                            f"(diff: {time_diff/3600:.1f}h)"
                                        )
                                        event.commence_time = ee.date
                                        changed = True

                                # Update game clock
                                if ee.clock and event.game_clock != ee.clock:
                                    event.game_clock = ee.clock
                                    changed = True

                                # Update period
                                if ee.status_detail and event.period != ee.status_detail:
                                    event.period = ee.status_detail
                                    changed = True

                                # Update scores
                                if ee.home_score is not None and event.home_score != ee.home_score:
                                    event.home_score = ee.home_score
                                    changed = True
                                if ee.away_score is not None and event.away_score != ee.away_score:
                                    event.away_score = ee.away_score
                                    changed = True

                                # Update broadcast info
                                if ee.broadcasts:
                                    broadcast_str = ", ".join(ee.broadcasts[:3])
                                    if event.broadcast_info != broadcast_str:
                                        event.broadcast_info = broadcast_str
                                        changed = True

                                # Update ESPN win probability and save snapshot
                                if ee.home_win_probability is not None:
                                    event.espn_win_prob_home = ee.home_win_probability
                                    sources = event.win_probability_sources or {}
                                    sources["espn"] = ee.home_win_probability
                                    event.win_probability_sources = sources
                                    changed = True

                                    snapshot = ESPNSnapshot(
                                        event_id=event.id,
                                        home_win_probability=ee.home_win_probability,
                                        away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                                        home_score=ee.home_score,
                                        away_score=ee.away_score,
                                        game_clock=ee.clock,
                                        period=ee.status_detail,
                                    )
                                    session.add(snapshot)
                                    stats["snapshots_created"] = stats.get("snapshots_created", 0) + 1

                                    # Also write ESPN to generic win_prob_snapshots table
                                    try:
                                        from app.models.models import WinProbSnapshot
                                        espn_wp_snap = WinProbSnapshot(
                                            event_id=event.id,
                                            source="espn",
                                            home_win_probability=ee.home_win_probability,
                                            away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                                            game_state={
                                                "clock": ee.clock,
                                                "period": ee.status_detail,
                                                "home_score": ee.home_score,
                                                "away_score": ee.away_score,
                                            },
                                        )
                                        session.add(espn_wp_snap)
                                    except Exception:
                                        pass  # Table may not exist yet

                                # Compute statistical model win probability (live games only)
                                if ee.status == "in" and ee.home_score is not None and ee.away_score is not None and ee.clock:
                                    try:
                                        from app.utils.win_probability import compute_statistical_win_prob
                                        from app.models.models import WinProbSnapshot

                                        # Use opening spread if available
                                        pregame_spread = None
                                        if event.opening_home_spread is not None:
                                            pregame_spread = float(event.opening_home_spread)

                                        # Prefer numeric period for reliability
                                        period_str = ee.status_detail
                                        if ee.period and not period_str:
                                            period_str = str(ee.period)

                                        stat_wp = compute_statistical_win_prob(
                                            home_score=ee.home_score,
                                            away_score=ee.away_score,
                                            clock=ee.clock,
                                            period=period_str,
                                            sport_key=sport_key,
                                            pregame_spread=pregame_spread,
                                        )
                                        if stat_wp is not None:
                                            sources = event.win_probability_sources or {}
                                            sources["stat_model"] = round(stat_wp, 4)
                                            event.win_probability_sources = sources
                                            changed = True

                                            stat_snap = WinProbSnapshot(
                                                event_id=event.id,
                                                source="stat_model",
                                                home_win_probability=round(stat_wp, 4),
                                                away_win_probability=round(1.0 - stat_wp, 4),
                                                game_state={
                                                    "clock": ee.clock,
                                                    "period": ee.status_detail,
                                                    "home_score": ee.home_score,
                                                    "away_score": ee.away_score,
                                                    "pregame_spread": pregame_spread,
                                                },
                                            )
                                            session.add(stat_snap)
                                            stats["stat_model_computed"] = stats.get("stat_model_computed", 0) + 1
                                        else:
                                            logger.warning(
                                                f"stat_model returned None for event {event.id} "
                                                f"(sport={sport_key}, clock={ee.clock!r}, period={ee.status_detail!r}, "
                                                f"score={ee.home_score}-{ee.away_score})"
                                            )
                                    except Exception as e:
                                        logger.error(f"stat_model error for event {event.id}: {e}")
                                elif ee.status == "in":
                                    # Only track missing data for live games
                                    if ee.home_score is None or ee.away_score is None:
                                        stats["stat_model_no_score"] = stats.get("stat_model_no_score", 0) + 1
                                    elif not ee.clock:
                                        stats["stat_model_no_clock"] = stats.get("stat_model_no_clock", 0) + 1

                                if changed:
                                    stats["events_updated"] += 1

                                break  # Found match, move to next event

                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")

            # Second pass: sync team data for scheduled events
            # (so colors/logos appear before games go live)
            for sport_key in scheduled_sport_keys:
                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue

                try:
                    events_result = await session.execute(
                        select(Event)
                        .options(selectinload(Event.sport))
                        .where(
                            Event.sport.has(key=sport_key),
                            Event.status == "scheduled",
                        )
                    )
                    scheduled_events = events_result.scalars().all()

                    for event in scheduled_events:
                        home_names, away_names = get_event_name_variations(event)

                        for ee in espn_events:
                            if not ee.home_team or not ee.away_team:
                                continue
                            espn_home = ee.home_team.display_name or ee.home_team.name or ""
                            espn_away = ee.away_team.display_name or ee.away_team.name or ""

                            if names_match(home_names, espn_home) and names_match(away_names, espn_away):
                                await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                                await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)
                                # Correct commence_time from ESPN if significantly different
                                if ee.date and event.commence_time:
                                    time_diff = abs((ee.date - event.commence_time).total_seconds())
                                    if time_diff > 300:  # > 5 minutes
                                        print(
                                            f"ESPN: Correcting commence_time for scheduled event {event.id} "
                                            f"({event.home_team_name} vs {event.away_team_name}): "
                                            f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                            f"(diff: {time_diff/3600:.1f}h)"
                                        )
                                        event.commence_time = ee.date
                                if ee.broadcasts and not event.broadcast_info:
                                    event.broadcast_info = ", ".join(ee.broadcasts)
                                if ee.espn_id and not event.espn_id:
                                    event.espn_id = ee.espn_id
                                break
                except Exception as e:
                    stats["errors"].append(f"scheduled_{sport_key}: {str(e)}")

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        print(f"ESPN sync task error: {e}\n{traceback.format_exc()}")

    return stats


# ============================================================================
# ESPN Team Logo Backfill
# ============================================================================


@celery_app.task(bind=True)
def backfill_team_logos(self):
    """
    Fetch all teams from ESPN's /teams endpoint and fill in missing logos.

    This runs periodically to ensure all teams in supported leagues have
    logo data, even if they haven't appeared in a live/scheduled game
    during an ESPN sync cycle.
    """
    return run_async(_backfill_team_logos())


async def _backfill_team_logos():
    """Async implementation of backfill_team_logos."""
    from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP
    from app.models.models import Team, Sport
    from sqlalchemy import select

    stats = {
        "sports_checked": 0,
        "teams_fetched": 0,
        "teams_updated": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find teams missing logos, grouped by sport
            result = await session.execute(
                select(Team, Sport.key)
                .join(Sport)
                .where(Team.logo_url_small.is_(None))
            )
            teams_missing_logos = result.all()

            if not teams_missing_logos:
                return {"status": "no_teams_missing_logos", **stats}

            # Group by sport key
            sport_keys_needed = set()
            teams_by_sport = {}
            for team, sport_key in teams_missing_logos:
                if sport_key in SPORT_LEAGUE_MAP:
                    sport_keys_needed.add(sport_key)
                    teams_by_sport.setdefault(sport_key, []).append(team)

            if not sport_keys_needed:
                return {"status": "no_espn_mapped_sports_need_logos", **stats}

            # Fetch teams from ESPN for each sport
            espn = ESPNAPIService()
            try:
                for sport_key in sport_keys_needed:
                    stats["sports_checked"] += 1
                    try:
                        espn_teams = await espn.get_teams(sport_key)
                        stats["teams_fetched"] += len(espn_teams)
                    except Exception as e:
                        stats["errors"].append(f"fetch_{sport_key}: {str(e)}")
                        continue

                    if not espn_teams:
                        continue

                    # Build lookup of ESPN teams by various name forms
                    espn_by_id = {}
                    espn_by_name = {}
                    for et in espn_teams:
                        espn_by_id[et.espn_id] = et
                        for name in [et.display_name, et.name, et.short_name, et.nickname]:
                            if name:
                                espn_by_name[name.lower()] = et

                    # Try to match our teams to ESPN teams
                    for team in teams_by_sport.get(sport_key, []):
                        matched_espn = None

                        # Match by ESPN ID first (most reliable)
                        if team.espn_id and team.espn_id in espn_by_id:
                            matched_espn = espn_by_id[team.espn_id]
                        else:
                            # Match by name
                            names_to_check = [team.name]
                            if team.alternate_names:
                                names_to_check.extend(team.alternate_names)

                            for name in names_to_check:
                                name_lower = name.lower()
                                # Exact match
                                if name_lower in espn_by_name:
                                    matched_espn = espn_by_name[name_lower]
                                    break
                                # Substring match
                                for espn_name, et in espn_by_name.items():
                                    if name_lower in espn_name or espn_name in name_lower:
                                        matched_espn = et
                                        break
                                if matched_espn:
                                    break

                        if matched_espn and matched_espn.logo_url:
                            team.logo_url_small = matched_espn.logo_url
                            team.logo_url_large = matched_espn.logo_url
                            if not team.espn_id:
                                team.espn_id = matched_espn.espn_id
                            if matched_espn.primary_color and not team.primary_color:
                                color = matched_espn.primary_color
                                if not color.startswith("#"):
                                    color = f"#{color}"
                                team.primary_color = color
                            if matched_espn.secondary_color and not team.secondary_color:
                                color = matched_espn.secondary_color
                                if not color.startswith("#"):
                                    color = f"#{color}"
                                team.secondary_color = color
                            # Store alternate names for future matching
                            alt_names = set(team.alternate_names or [])
                            for n in [matched_espn.display_name, matched_espn.short_name, matched_espn.nickname, matched_espn.name]:
                                if n and n != team.name:
                                    alt_names.add(n)
                            if alt_names:
                                team.alternate_names = list(alt_names)
                            stats["teams_updated"] += 1
            finally:
                await espn.close()

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        print(f"Team logo backfill error: {e}\n{traceback.format_exc()}")

    return stats


# ---------------------------------------------------------------------------
# Ad Baseline Reset — scheduled at kickoff so view deltas track game-day growth
# ---------------------------------------------------------------------------
@celery_app.task(bind=True)
def reset_ad_baseline(self):
    """Clear the Super Bowl ad view baseline in Redis.

    Scheduled to run at 2 PM Pacific (22:00 UTC) on Feb 9, 2026 — kickoff.
    The next /api/contest/ads fetch will snapshot fresh view counts,
    so all +/- deltas reflect views gained during the game.
    """
    import ssl as _ssl
    try:
        if REDIS_URL.startswith("rediss://"):
            r = redis.from_url(REDIS_URL, ssl_cert_reqs=_ssl.CERT_NONE)
        else:
            r = redis.from_url(REDIS_URL)
        r.delete("sb_contest:ad_baseline")
        r.delete("sb_contest:youtube_ads")
        print("Ad baseline reset — next fetch will snapshot fresh view counts")
        return {"status": "reset", "message": "Ad baseline cleared at kickoff"}
    except Exception as e:
        print(f"Ad baseline reset error: {e}")
        return {"status": "error", "error": str(e)}
