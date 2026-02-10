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

import os

import sentry_sdk
from celery import Celery
from celery.schedules import crontab

from app.tasks.base import run_async

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


# =============================================================================
# Task definitions
#
# Each task is a thin wrapper that calls run_async() on the async implementation
# from the appropriate submodule. The name= parameter is pinned to "app.tasks.*"
# to match the beat schedule and preserve backward compatibility.
# =============================================================================


# --- Sports & Event Discovery ---

@celery_app.task(bind=True, max_retries=3, name="app.tasks.sync_sports")
def sync_sports(self):
    """Sync available sports from The Odds API to database."""
    from app.tasks.sports import _sync_sports
    try:
        return run_async(_sync_sports())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.discover_events")
def discover_events(self):
    """Discover events for ALL active sports."""
    from app.tasks.sports import _discover_events
    try:
        return run_async(_discover_events())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


# --- Odds Polling ---

@celery_app.task(bind=True, max_retries=3, name="app.tasks.poll_all_odds")
def poll_all_odds(self):
    """Poll odds for all configured sports with adaptive polling."""
    from app.tasks.odds_polling import _poll_all_odds
    from app.tasks.redis_state import should_poll_now

    should_poll, reason = should_poll_now()
    if not should_poll:
        return {"skipped": True, "reason": reason}

    try:
        result = run_async(_poll_all_odds())
        return {**result, "poll_reason": reason}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="app.tasks.poll_sport_odds")
def poll_sport_odds(self, sport_key: str):
    """Poll odds for a single sport."""
    from app.tasks.odds_polling import _poll_sport_odds
    return run_async(_poll_sport_odds(sport_key))


# --- Pulse (Game Excitement Index) ---

@celery_app.task(bind=True, name="app.tasks.compute_gei_for_event")
def compute_gei_for_event(self, event_id: int):
    """Compute GEI for a single completed event."""
    from app.tasks.pulse import _compute_gei_for_event
    return run_async(_compute_gei_for_event(event_id))


@celery_app.task(bind=True, name="app.tasks.compute_gei_batch")
def compute_gei_batch(self, limit: int = 100):
    """Compute Pulse for a batch of completed events."""
    from app.tasks.pulse import _compute_pulse_batch
    return run_async(_compute_pulse_batch(limit))


@celery_app.task(bind=True, name="app.tasks.compute_gei_percentiles")
def compute_gei_percentiles(self):
    """Recompute GEI percentile thresholds for all scopes."""
    from app.tasks.pulse import _compute_gei_percentiles
    return run_async(_compute_gei_percentiles())


# --- Futures (The Odds API) ---

@celery_app.task(bind=True, name="app.tasks.poll_futures_odds")
def poll_futures_odds(self):
    """Poll futures/outrights odds from The Odds API."""
    from app.tasks.futures import _poll_futures_odds
    return run_async(_poll_futures_odds())


# --- Kalshi ---

@celery_app.task(bind=True, name="app.tasks.poll_kalshi_markets")
def poll_kalshi_markets(self):
    """Poll prediction markets from Kalshi."""
    from app.tasks.kalshi import _poll_kalshi_markets
    return run_async(_poll_kalshi_markets())


# --- ESPN ---

@celery_app.task(bind=True, name="app.tasks.enrich_events_metadata")
def enrich_events_metadata(self, limit: int = 50):
    """Enrich events with LLM-generated metadata."""
    from app.tasks.espn_sync import _enrich_events_metadata
    return run_async(_enrich_events_metadata(limit))


@celery_app.task(bind=True, name="app.tasks.sync_espn_live_events")
def sync_espn_live_events(self):
    """Sync live event data from ESPN for all sports with active games."""
    from app.tasks.espn_sync import _sync_espn_live_events
    return run_async(_sync_espn_live_events())


@celery_app.task(bind=True, name="app.tasks.backfill_team_logos")
def backfill_team_logos(self):
    """Fetch all teams from ESPN's /teams endpoint and fill in missing logos."""
    from app.tasks.espn_sync import _backfill_team_logos
    return run_async(_backfill_team_logos())


# --- Heartbeat ---

@celery_app.task(name="app.tasks.heartbeat")
def heartbeat():
    """Write a heartbeat timestamp to Redis for health monitoring."""
    from datetime import datetime, timezone
    from app.tasks.redis_state import get_redis_client
    try:
        r = get_redis_client()
        r.set("odds_tracker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=300)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =============================================================================
# Beat schedule
# =============================================================================

celery_app.conf.beat_schedule = {
    "poll-odds-adaptive": {
        "task": "app.tasks.poll_all_odds",
        "schedule": 30.0,
    },
    "sync-sports-hourly": {
        "task": "app.tasks.sync_sports",
        "schedule": crontab(minute=0),
    },
    "discover-new-events": {
        "task": "app.tasks.discover_events",
        "schedule": crontab(minute="*/15"),
    },
    "compute-gei-batch": {
        "task": "app.tasks.compute_gei_batch",
        "schedule": crontab(minute="*/10"),
        "kwargs": {"limit": 50},
    },
    "compute-gei-percentiles-hourly": {
        "task": "app.tasks.compute_gei_percentiles",
        "schedule": crontab(minute=5),
    },
    "poll-futures-hourly": {
        "task": "app.tasks.poll_futures_odds",
        "schedule": crontab(minute=30),
    },
    "poll-kalshi-hourly": {
        "task": "app.tasks.poll_kalshi_markets",
        "schedule": crontab(minute=45),
    },
    "enrich-events-hourly": {
        "task": "app.tasks.enrich_events_metadata",
        "schedule": crontab(minute=20),
        "kwargs": {"limit": 50},
    },
    "sync-espn-live": {
        "task": "app.tasks.sync_espn_live_events",
        "schedule": 60.0,
    },
    "backfill-team-logos": {
        "task": "app.tasks.backfill_team_logos",
        "schedule": crontab(minute=15, hour="*/6"),
    },
    "heartbeat": {
        "task": "app.tasks.heartbeat",
        "schedule": 60.0,
    },
}


# =============================================================================
# Backward-compatible re-exports
#
# These allow existing code that does `from app.tasks import _infer_base_sport`
# or `from app.tasks import celery_app` to keep working.
# =============================================================================

from app.tasks.futures import _infer_base_sport  # noqa: E402, F401 (used by routes/futures.py)
