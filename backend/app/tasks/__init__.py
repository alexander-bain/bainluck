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

import logging
import os

import sentry_sdk
from celery import Celery
from celery.schedules import crontab

from app.tasks.base import run_async

import time as _time

logger = logging.getLogger(__name__)


def _tracked_run(task_name: str, async_fn):
    """Run an async task and record success/failure metrics in Redis."""
    from app.tasks.redis_state import record_task_success, record_task_failure
    start = _time.monotonic()
    try:
        result = run_async(async_fn)
        duration_ms = (_time.monotonic() - start) * 1000
        # Extract summary from task result (most tasks return dicts)
        summary = result if isinstance(result, dict) else {"result": str(result)[:200]}
        record_task_success(task_name, duration_ms, summary)
        return result
    except Exception as exc:
        duration_ms = (_time.monotonic() - start) * 1000
        record_task_failure(task_name, duration_ms, str(exc))
        raise

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
    "bainluck",
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

# =============================================================================
# Queue routing: realtime vs background workers
#
# realtime (Standard-2X, concurrency=4):
#   High-frequency tasks driving user-visible live game data.
#   Never blocked by batch jobs.
#
# background (Standard-1X, concurrency=2):
#   Hourly/daily batch tasks — enrichment, audits, maintenance.
#   Can tolerate delays without user impact.
#   Memory budget: 2 × 200MB + ~100MB overhead ≈ 500MB (fits 512MB dyno).
#
# To move a task: just change its queue in task_routes below.
# =============================================================================

from kombu import Queue

celery_app.conf.task_queues = [
    Queue("realtime", routing_key="realtime"),
    Queue("background", routing_key="background"),
]

celery_app.conf.task_default_queue = "background"

celery_app.conf.task_routes = {
    # --- Realtime: live game data (30s-120s cycle) ---
    "app.tasks.poll_all_odds": {"queue": "realtime"},
    "app.tasks.poll_sport_odds": {"queue": "realtime"},
    "app.tasks.sync_espn_live_events": {"queue": "realtime"},
    "app.tasks.poll_live_prediction_markets": {"queue": "realtime"},
    "app.tasks.sync_mlb_win_probability": {"queue": "realtime"},
    "app.tasks.sync_statpal_live_plays": {"queue": "realtime"},
    "app.tasks.sync_statpal_livescores": {"queue": "realtime"},
    "app.tasks.heartbeat": {"queue": "realtime"},
    "app.tasks.transition_event_statuses": {"queue": "realtime"},
    # --- Everything else routes to background (default queue) ---
}

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
    """Discover events for ALL active sports, then update taxonomy tags."""
    from app.tasks.sports import _discover_events
    try:
        result = _tracked_run("discover_events", _discover_events())
        # Piggyback taxonomy update — worker concurrency=2 means dedicated
        # taxonomy tasks never get a slot. Run inline after discovery.
        try:
            from app.tasks.taxonomy import _update_event_tags_impl
            tag_result = _tracked_run("update_event_tags", _update_event_tags_impl(500))
            result["taxonomy"] = tag_result
        except Exception as tag_exc:
            logger.warning("Taxonomy update failed: %s", tag_exc)
            result["taxonomy_error"] = str(tag_exc)[:200]
        # LLM enrichment — gated to run at most every 10 min
        try:
            from app.tasks.redis_state import get_redis_client
            r = get_redis_client()
            lock_key = "bainluck:llm_enrich_gate"
            if r.set(lock_key, "1", nx=True, ex=600):  # 10 min TTL
                from app.tasks.taxonomy import _enrich_taxonomy_llm_impl
                llm_result = _tracked_run(
                    "enrich_taxonomy_llm",
                    _enrich_taxonomy_llm_impl(event_limit=50, market_limit=30),
                )
                result["llm_enrichment"] = llm_result
            else:
                result["llm_enrichment"] = "skipped (gate)"
        except Exception as llm_exc:
            logger.warning("LLM enrichment failed: %s", llm_exc)
            result["llm_enrichment_error"] = str(llm_exc)[:200]
        # Piggyback DataGolf hourly poll — same starvation issue as taxonomy
        try:
            from app.tasks.redis_state import get_redis_client as _get_rc
            _r = _get_rc()
            dg_gate_key = "bainluck:datagolf_poll_gate"
            if _r.set(dg_gate_key, "1", nx=True, ex=3600):  # 1 hour TTL
                from app.tasks.datagolf import _poll_datagolf_markets
                dg_result = _tracked_run("poll_datagolf", _poll_datagolf_markets())
                result["datagolf"] = dg_result
            else:
                result["datagolf"] = "skipped (gate)"
        except Exception as dg_exc:
            logger.warning("DataGolf poll failed: %s", dg_exc)
            result["datagolf_error"] = str(dg_exc)[:200]
        return result
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
        result = _tracked_run("poll_odds", _poll_all_odds())
        # Piggyback DataGolf live poll — Redis-gated to 5 min
        try:
            from app.tasks.redis_state import get_redis_client
            r = get_redis_client()
            dg_live_key = "bainluck:datagolf_live_gate"
            if r.set(dg_live_key, "1", nx=True, ex=300):  # 5 min TTL
                from app.tasks.datagolf import _poll_datagolf_live
                dg_result = _tracked_run("datagolf_live", _poll_datagolf_live())
                result["datagolf_live"] = dg_result
            else:
                result["datagolf_live"] = "skipped (gate)"
        except Exception as dg_exc:
            logger.warning("DataGolf live poll failed: %s", dg_exc)
            result["datagolf_live_error"] = str(dg_exc)[:200]
        return {**result, "poll_reason": reason}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="app.tasks.poll_sport_odds")
def poll_sport_odds(self, sport_key: str):
    """Poll odds for a single sport."""
    from app.tasks.odds_polling import _poll_sport_odds
    return run_async(_poll_sport_odds(sport_key))


# --- Excitement Index (EI) ---

@celery_app.task(bind=True, name="app.tasks.compute_gei_for_event")
def compute_gei_for_event(self, event_id: int):
    """Compute EI for a single completed event. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_for_event
    return run_async(_compute_ei_for_event(event_id))


@celery_app.task(bind=True, name="app.tasks.compute_gei_batch")
def compute_gei_batch(self, limit: int = 100):
    """Compute EI for a batch of completed events. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_batch
    return run_async(_compute_ei_batch(limit))


@celery_app.task(bind=True, name="app.tasks.compute_gei_percentiles")
def compute_gei_percentiles(self):
    """Recompute EI percentile thresholds for all scopes. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_percentiles
    return run_async(_compute_ei_percentiles())


# --- Futures (The Odds API) ---

@celery_app.task(bind=True, name="app.tasks.poll_futures_odds")
def poll_futures_odds(self):
    """Poll futures/outrights odds from The Odds API."""
    from app.tasks.futures import _poll_futures_odds
    return _tracked_run("poll_futures", _poll_futures_odds())


# --- Kalshi ---

@celery_app.task(bind=True, name="app.tasks.poll_kalshi_markets", soft_time_limit=600, time_limit=660)
def poll_kalshi_markets(self):
    """Poll prediction markets from Kalshi (11 min limit for market backfill)."""
    from app.tasks.kalshi import _poll_kalshi_markets
    return _tracked_run("poll_kalshi", _poll_kalshi_markets())


# --- Polymarket ---

@celery_app.task(bind=True, name="app.tasks.poll_polymarket_markets")
def poll_polymarket_markets(self):
    """Poll prediction markets from Polymarket (no API key needed)."""
    from app.tasks.polymarket import _poll_polymarket_markets
    return _tracked_run("poll_polymarket", _poll_polymarket_markets())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_polymarket_history")
def backfill_polymarket_history(self, limit: int = 50, fidelity: int = 60, interval: str = "max"):
    """Backfill historical prices from Polymarket CLOB API for outcomes with sparse data."""
    from app.tasks.polymarket import _backfill_polymarket_price_history
    return _tracked_run("polymarket_history", _backfill_polymarket_price_history(limit, fidelity, interval))


# --- Categorization ---

@celery_app.task(bind=True, name="app.tasks.categorize_futures")
def categorize_futures_task(self, limit: int = 100, force_llm: bool = False):
    """Categorize uncategorized futures markets (background task)."""
    from app.tasks.futures import _categorize_futures_impl
    return run_async(_categorize_futures_impl(limit, force_llm))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.recategorize_other")
def recategorize_other_task(self, limit: int = 500, from_category: str = None):
    """Re-run rules on 'other' (or specified category) markets to fix miscategorizations."""
    from app.tasks.futures import _recategorize_other_impl
    return run_async(_recategorize_other_impl(limit, from_category=from_category))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.regenerate_tags")
def regenerate_tags_task(self, limit: int = 5000, category: str = None):
    """Regenerate category_tags for existing markets using current patterns."""
    from app.tasks.futures import _regenerate_tags_impl
    return run_async(_regenerate_tags_impl(limit, category=category))


@celery_app.task(bind=True, name="app.tasks.mark_resolved_futures")
def mark_resolved_futures(self):
    """Mark futures markets as resolved when their resolution_date has passed."""
    from app.tasks.futures import _mark_resolved_impl
    return run_async(_mark_resolved_impl())


@celery_app.task(bind=True, name="app.tasks.fix_outcome_names")
def fix_outcome_names(self):
    """Fix Polymarket outcome names using groupItemTitle from Gamma API."""
    from app.tasks.futures import _fix_outcome_names_impl
    return run_async(_fix_outcome_names_impl())


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
    return _tracked_run("espn_sync", _sync_espn_live_events())


@celery_app.task(bind=True, name="app.tasks.backfill_team_logos")
def backfill_team_logos(self):
    """Fetch all teams from ESPN's /teams endpoint and fill in missing logos."""
    from app.tasks.espn_sync import _backfill_team_logos
    return run_async(_backfill_team_logos())


@celery_app.task(bind=True, name="app.tasks.cleanup_bad_espn_matches")
def cleanup_bad_espn_matches(self):
    """Validate existing ESPN ID assignments and clear bad matches."""
    from app.tasks.espn_sync import _cleanup_bad_espn_matches
    return run_async(_cleanup_bad_espn_matches())


@celery_app.task(bind=True, name="app.tasks.backfill_box_scores")
def backfill_box_scores(self, limit: int = 100):
    """Fetch ESPN box scores for completed events missing box_score_data."""
    from app.tasks.espn_sync import _backfill_box_scores
    return run_async(_backfill_box_scores(limit=limit))


# --- Team Linking (Futures → Teams) ---

@celery_app.task(bind=True, name="app.tasks.backfill_team_links")
def backfill_team_links(self, limit: int = 200, use_llm: bool = True):
    """Backfill team_id on futures outcomes and market_tier on futures markets."""
    from app.tasks.team_linking import _backfill_team_links
    return run_async(_backfill_team_links(limit, use_llm))


@celery_app.task(bind=True, name="app.tasks.backfill_canonical_keys")
def backfill_canonical_keys(self, limit: int = 500):
    """Backfill canonical_market_key and llm_league on futures markets."""
    from app.tasks.team_linking import _backfill_canonical_keys
    return run_async(_backfill_canonical_keys(limit))


# --- Prediction Market → Event Matching ---

@celery_app.task(bind=True, name="app.tasks.match_prediction_markets", time_limit=870, soft_time_limit=840)
def match_prediction_markets(self, limit: int = 500):
    """Match game-level prediction markets to events and write win_prob_snapshots."""
    from app.tasks.prediction_market_matching import _match_prediction_markets
    return _tracked_run("prediction_market_match", _match_prediction_markets(limit))


@celery_app.task(bind=True, name="app.tasks.poll_live_prediction_markets")
def poll_live_prediction_markets(self):
    """Fast-poll prices for prediction markets linked to live events (every 2 min)."""
    from app.tasks.prediction_market_matching import _poll_live_prediction_market_prices
    return _tracked_run("prediction_market_live", _poll_live_prediction_market_prices())


@celery_app.task(bind=True, name="app.tasks.backfill_polymarket_win_prob")
def backfill_polymarket_win_prob(self, market_id: int, event_id: int):
    """Backfill win_prob_snapshots from Polymarket CLOB price history."""
    from app.tasks.prediction_market_matching import _backfill_polymarket_win_prob_history
    return run_async(_backfill_polymarket_win_prob_history(market_id, event_id))


# --- MLB Live Win Probability ---

@celery_app.task(bind=True, name="app.tasks.sync_mlb_win_probability")
def sync_mlb_win_probability(self):
    """Sync live MLB win probabilities from the MLB Stats API (every 2 min during games)."""
    from app.tasks.mlb_sync import _sync_mlb_win_probability
    return _tracked_run("mlb_sync", _sync_mlb_win_probability())


# --- Roster Sync (ESPN + MLB Stats API) ---

@celery_app.task(bind=True, name="app.tasks.sync_rosters", time_limit=300, soft_time_limit=270)
def sync_rosters(self, sport_key: str = None):
    """Sync player rosters from ESPN + MLB Stats API to Team.roster_players."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"sync_rosters starting (sport_key={sport_key})")
    from app.tasks.roster_sync import _sync_rosters
    result = run_async(_sync_rosters(sport_key))
    logger.info(f"sync_rosters completed: {result}")
    return result


# --- StatPal (Schedules, Injuries, Play-by-Play) ---

@celery_app.task(bind=True, name="app.tasks.sync_statpal_schedules")
def sync_statpal_schedules(self, sport_key: str = None):
    """Sync fixture schedules from StatPal — corrects commence_time, populates end_time."""
    from app.tasks.statpal_sync import _sync_statpal_schedules
    return _tracked_run("statpal_schedules", _sync_statpal_schedules(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_injuries")
def sync_statpal_injuries(self, sport_key: str = None):
    """Sync injury reports from StatPal for line movement context."""
    from app.tasks.statpal_sync import _sync_statpal_injuries
    return _tracked_run("statpal_injuries", _sync_statpal_injuries(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_live_plays")
def sync_statpal_live_plays(self, sport_key: str = None):
    """Fetch play-by-play data from StatPal for live games."""
    from app.tasks.statpal_sync import _sync_statpal_live_plays
    return _tracked_run("statpal_plays", _sync_statpal_live_plays(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_livescores")
def sync_statpal_livescores(self):
    """Poll StatPal livescores for real-time game state (every 30s)."""
    from app.tasks.statpal_sync import _sync_statpal_livescores
    return _tracked_run("statpal_livescores", _sync_statpal_livescores())


@celery_app.task(bind=True, name="app.tasks.sync_statpal_rosters")
def sync_statpal_rosters(self, sport_key: str = None):
    """Sync team rosters from StatPal (supplements ESPN roster data)."""
    from app.tasks.statpal_sync import _sync_statpal_rosters
    return run_async(_sync_statpal_rosters(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_standings")
def sync_statpal_standings(self, sport_key: str = None):
    """Sync league standings from StatPal."""
    from app.tasks.statpal_sync import _sync_statpal_standings
    return _tracked_run("statpal_standings", _sync_statpal_standings(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_team_stats")
def sync_statpal_team_stats(self, sport_key: str = None):
    """Sync season-level team statistics from StatPal."""
    from app.tasks.statpal_sync import _sync_statpal_team_stats
    return _tracked_run("statpal_team_stats", _sync_statpal_team_stats(sport_key))


# --- Snapshot Retention ---

@celery_app.task(bind=True, soft_time_limit=1700, time_limit=1800, name="app.tasks.collapse_snapshots")
def collapse_snapshots(self, min_age_hours: int = 48, table: str = "odds", limit: int = 200):
    """Collapse consecutive identical snapshot rows for one table at a time."""
    from app.tasks.retention import _collapse_snapshots_impl
    return run_async(_collapse_snapshots_impl(min_age_hours, table, limit))


# --- Matching Audits ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_canonical_keys")
def audit_canonical_keys(self, limit: int = 50):
    """Audit canonical key dedup quality with LLM verification."""
    from app.tasks.matching_audit import _audit_canonical_keys_impl
    return run_async(_audit_canonical_keys_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_prediction_market_links")
def audit_prediction_market_links(self, limit: int = 50):
    """Audit prediction market → event link quality with LLM verification."""
    from app.tasks.matching_audit import _audit_prediction_market_links_impl
    return run_async(_audit_prediction_market_links_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_related_futures")
def audit_related_futures(self, limit: int = 30):
    """Audit related futures coverage with LLM verification."""
    from app.tasks.matching_audit import _audit_related_futures_impl
    return run_async(_audit_related_futures_impl(limit))


# --- Matching Eval Metrics ---

@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.compute_matching_metrics")
def compute_matching_metrics(self):
    """Compute prediction market matching coverage and accuracy metrics."""
    from app.tasks.matching_audit import _compute_matching_metrics_impl
    return run_async(_compute_matching_metrics_impl())


# --- Data Quality Monitoring ---

@celery_app.task(bind=True, name="app.tasks.check_data_quality")
def check_data_quality(self):
    """Check classification and matching health, alert on issues."""
    from app.tasks.data_quality import _check_data_quality
    return _tracked_run("check_data_quality", _check_data_quality())


# --- Team Identity Backfill ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_team_identities")
def backfill_team_identities(self):
    from app.tasks.team_identity_backfill import _backfill_team_identities
    return run_async(_backfill_team_identities())


# --- Game State Backfill ---

@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860, name="app.tasks.backfill_game_state")
def backfill_game_state(self, limit=500, sport_filter=None):
    from app.tasks.game_state_backfill import _backfill_game_state
    return run_async(_backfill_game_state(limit=limit, sport_filter=sport_filter))


# --- DataGolf ---

@celery_app.task(bind=True, name="app.tasks.poll_datagolf_markets")
def poll_datagolf_markets(self):
    """Poll DataGolf schedule + pre-tournament predictions (hourly)."""
    from app.tasks.datagolf import _poll_datagolf_markets
    return _tracked_run("poll_datagolf", _poll_datagolf_markets())


@celery_app.task(bind=True, name="app.tasks.poll_datagolf_live")
def poll_datagolf_live(self):
    """Poll DataGolf live in-play probabilities (every 5 min, Redis-gated)."""
    from app.tasks.datagolf import _poll_datagolf_live, LIVE_KEY_PREFIX, POLL_TOURS
    from app.tasks.redis_state import get_redis_client

    # Only run if there's a live tournament (set by the live task itself or hourly poll)
    r = get_redis_client()
    any_live = any(r.get(f"{LIVE_KEY_PREFIX}:{tour}") for tour in POLL_TOURS)
    if not any_live:
        # Still run to detect if a tournament just went live
        pass

    return _tracked_run("datagolf_live", _poll_datagolf_live())


# --- Golf Leaderboard Snapshot ---

@celery_app.task(bind=True, name="app.tasks.snapshot_golf_leaderboard")
def snapshot_golf_leaderboard(self):
    """Snapshot golf leaderboard positions/probs at start of day for delta computation."""
    from app.tasks.datagolf import _snapshot_leaderboard
    return _tracked_run("golf_leaderboard_snapshot", _snapshot_leaderboard())


# --- March Madness Bracket Sync ---

@celery_app.task(bind=True, name="app.tasks.sync_mm_bracket")
def sync_mm_bracket(self):
    """Sync NCAA tournament bracket data from ESPN (seeds, regions, rounds)."""
    from app.tasks.march_madness import _sync_march_madness_bracket
    return _tracked_run("mm_bracket_sync", _sync_march_madness_bracket())


# --- Event Taxonomy ---

@celery_app.task(bind=True, name="app.tasks.update_event_tags")
def update_event_tags(self, limit: int = 500):
    """Compute and persist event_tags + market_tags for events and futures."""
    from app.tasks.taxonomy import _update_event_tags_impl
    return _tracked_run("update_event_tags", _update_event_tags_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660,
                 name="app.tasks.enrich_taxonomy_llm")
def enrich_taxonomy_llm(self, event_limit: int = 50, market_limit: int = 30):
    """Enrich events and futures with LLM-generated taxonomy tags (stakes, narrative, audience, structure)."""
    from app.tasks.taxonomy import _enrich_taxonomy_llm_impl
    return _tracked_run("enrich_taxonomy_llm", _enrich_taxonomy_llm_impl(event_limit, market_limit))


# --- Duplicate Event Cleanup ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.merge_duplicate_events")
def merge_duplicate_events_task(self, dry_run: bool = True):
    """Find and merge duplicate events (StatPal + Odds API race condition)."""
    from app.tasks.sports import _merge_duplicate_events_impl
    return run_async(_merge_duplicate_events_impl(dry_run=dry_run))


# --- Cleanup ---

@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860, name="app.tasks.cleanup_crypto")
def cleanup_crypto(self, batch_size: int = 5000):
    """Delete all crypto futures data (markets, outcomes, snapshots)."""
    from app.tasks.retention import _cleanup_crypto_impl
    return run_async(_cleanup_crypto_impl(batch_size))


@celery_app.task(bind=True, soft_time_limit=3600, time_limit=3660, name="app.tasks.turbo_collapse_futures")
def turbo_collapse_futures(self, limit: int = 5000):
    """Aggressive collapse pass for futures snapshots — high partition limit."""
    from app.tasks.retention import _collapse_snapshots_impl
    return run_async(_collapse_snapshots_impl(min_age_hours=24, table="futures", limit=limit))


@celery_app.task(bind=True, soft_time_limit=3600, time_limit=3660, name="app.tasks.turbo_collapse_odds")
def turbo_collapse_odds(self, limit: int = 5000):
    """Aggressive collapse pass for odds snapshots — high partition limit."""
    from app.tasks.retention import _collapse_snapshots_impl
    return run_async(_collapse_snapshots_impl(min_age_hours=24, table="odds", limit=limit))


# --- StatPal Usage Tracking ---

@celery_app.task(name="app.tasks.track_statpal_usage")
def track_statpal_usage():
    """Fetch and record StatPal API daily request count (every 15 min)."""
    from app.services.statpal_api import get_statpal_request_count
    from app.tasks.redis_state import record_statpal_usage

    async def _impl():
        data = await get_statpal_request_count()
        if data and data.get("request_count") is not None:
            record_statpal_usage(data["request_count"], data.get("current_date", ""))
            return {"recorded": True, **data}
        return {"recorded": False, "reason": "no_data"}

    return run_async(_impl())


# --- Heartbeat ---

@celery_app.task(name="app.tasks.heartbeat")
def heartbeat():
    """Write a heartbeat timestamp to Redis for health monitoring."""
    from datetime import datetime, timezone
    from app.tasks.redis_state import get_redis_client
    try:
        r = get_redis_client()
        r.set("bainluck:heartbeat", datetime.now(timezone.utc).isoformat(), ex=300)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@celery_app.task(name="app.tasks.transition_event_statuses")
def transition_event_statuses():
    """Transition event statuses based on commence_time (no API calls needed).

    Fixes the circular dependency where status='live' is required by ESPN/StatPal/
    prediction market tasks, but was only set by Odds API polling which may be
    throttled by quota conservation or adaptive slowdown.

    Runs every 60s on the realtime queue:
    - scheduled → live: when commence_time <= now
    - live → closed: when commence_time + max_sport_duration has passed and no
      recent data updates (staleness fallback)
    """
    from app.tasks.espn_sync import _transition_event_statuses_impl
    return _tracked_run("transition_statuses", _transition_event_statuses_impl())


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
        "schedule": crontab(minute="5,20,35,50"),  # Offset to run AFTER StatPal schedule sync
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
    "poll-futures-every-4h": {
        "task": "app.tasks.poll_futures_odds",
        "schedule": crontab(minute=30, hour="*/4"),  # Every 4 hours — futures change very slowly, quota conservation
    },
    "poll-kalshi": {
        "task": "app.tasks.poll_kalshi_markets",
        "schedule": crontab(minute="15,45"),  # Every 30 min — game markets need timely ingestion
    },
    "poll-polymarket-hourly": {
        "task": "app.tasks.poll_polymarket_markets",
        "schedule": crontab(minute=15),
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
    "transition-event-statuses": {
        "task": "app.tasks.transition_event_statuses",
        "schedule": 60.0,
    },
    "match-prediction-markets": {
        "task": "app.tasks.match_prediction_markets",
        "schedule": crontab(minute="5,20,35,50"),  # Every 15 min — link new markets ASAP
        "kwargs": {"limit": 500},
    },
    "poll-live-prediction-markets": {
        "task": "app.tasks.poll_live_prediction_markets",
        "schedule": 120.0,  # Every 2 minutes — only targets linked live game markets
    },
    "sync-mlb-win-probability": {
        "task": "app.tasks.sync_mlb_win_probability",
        "schedule": 120.0,  # Every 2 minutes during MLB season
    },
    "track-statpal-usage": {
        "task": "app.tasks.track_statpal_usage",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "backfill-team-links": {
        "task": "app.tasks.backfill_team_links",
        "schedule": crontab(minute=50),  # Every hour — roster matching is cheap, large backlog to clear
        "kwargs": {"limit": 2000, "use_llm": False},
    },
    "sync-rosters-daily": {
        "task": "app.tasks.sync_rosters",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC — moved from 7 AM to avoid contention with snapshot collapse tasks
    },
    # StatPal schedule sync — one per major sport to avoid timeout
    # (soccer returns thousands of global fixtures and overwhelms a single run)
    "sync-statpal-schedules-nba": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=0),
        "kwargs": {"sport_key": "basketball_nba"},
    },
    "sync-statpal-schedules-nhl": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=1),
        "kwargs": {"sport_key": "icehockey_nhl"},
    },
    "sync-statpal-schedules-mlb": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=2),
        "kwargs": {"sport_key": "baseball_mlb"},
    },
    "sync-statpal-schedules-nfl": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=3),
        "kwargs": {"sport_key": "americanfootball_nfl"},
    },
    "sync-statpal-injuries": {
        "task": "app.tasks.sync_statpal_injuries",
        "schedule": crontab(minute=20),  # Hourly at :20 — injuries cached with 2h TTL anyway (was every 15 min)
    },
    "sync-statpal-live-plays": {
        "task": "app.tasks.sync_statpal_live_plays",
        "schedule": 60.0,  # Every 60 seconds — play-by-play for live NFL games only
    },
    "sync-statpal-livescores": {
        "task": "app.tasks.sync_statpal_livescores",
        "schedule": 30.0,  # Every 30 seconds — real-time scores for all live games
    },
    "sync-statpal-rosters-daily": {
        "task": "app.tasks.sync_statpal_rosters",
        "schedule": crontab(minute=30, hour=7),  # Daily at 7:30 AM UTC — after ESPN roster sync (7:00)
    },
    "sync-statpal-standings-daily": {
        "task": "app.tasks.sync_statpal_standings",
        "schedule": crontab(minute=0, hour=8),  # Daily at 8:00 AM UTC
    },
    "sync-statpal-team-stats-weekly": {
        "task": "app.tasks.sync_statpal_team_stats",
        "schedule": crontab(minute=0, hour=9, day_of_week=1),  # Weekly Monday 9:00 AM UTC
    },
    "sync-mm-bracket": {
        "task": "app.tasks.sync_mm_bracket",
        "schedule": crontab(minute="*/15", hour="*", day_of_month="15-30", month_of_year="3,4"),
    },
    "collapse-odds-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=30, hour=6),  # Daily at 6:30 AM UTC
        "kwargs": {"table": "odds", "limit": 500},
    },
    "collapse-winprob-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=35, hour=6),  # Daily at 6:35 AM UTC
        "kwargs": {"table": "winprob", "limit": 500},
    },
    "collapse-futures-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=40, hour=6),  # Daily at 6:40 AM UTC
        "kwargs": {"table": "futures", "limit": 500},
    },
    "turbo-collapse-futures": {
        "task": "app.tasks.turbo_collapse_futures",
        "schedule": crontab(minute=30, hour="*/6"),  # Every 6 hours — catch up on backlog
        "kwargs": {"limit": 5000},
    },
    "turbo-collapse-odds": {
        "task": "app.tasks.turbo_collapse_odds",
        "schedule": crontab(minute=45, hour="*/6"),  # Every 6 hours
        "kwargs": {"limit": 5000},
    },
    "matching-metrics-daily": {
        "task": "app.tasks.compute_matching_metrics",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC
    },
    "check-data-quality-daily": {
        "task": "app.tasks.check_data_quality",
        "schedule": crontab(minute=0, hour=11),  # Daily at 11:00 AM UTC (4 AM PT)
    },
    "recategorize-other-daily": {
        "task": "app.tasks.recategorize_other",
        "schedule": crontab(minute=0, hour=8),  # Daily at 8:00 AM UTC
        "kwargs": {"limit": 2000},
    },
    "mark-resolved-futures": {
        "task": "app.tasks.mark_resolved_futures",
        "schedule": crontab(minute=15, hour="2,8,14,20"),  # Every 6 hours — keeps resolved futures from cluttering feed (was daily)
    },
    "backfill-canonical-keys-daily": {
        "task": "app.tasks.backfill_canonical_keys",
        "schedule": crontab(minute=30, hour=8),  # Daily at 8:30 AM UTC
        "kwargs": {"limit": 2000},
    },
    "audit-canonical-keys-daily": {
        "task": "app.tasks.audit_canonical_keys",
        "schedule": crontab(minute=0, hour=9),  # Daily at 9:00 AM UTC
        "kwargs": {"limit": 50},
    },
    "snapshot-golf-leaderboard-daily": {
        "task": "app.tasks.snapshot_golf_leaderboard",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC (~6am ET) — before tournament rounds start
    },
    "audit-prediction-market-links-daily": {
        "task": "app.tasks.audit_prediction_market_links",
        "schedule": crontab(minute=15, hour=9),  # Daily at 9:15 AM UTC
        "kwargs": {"limit": 50},
    },
    "audit-related-futures-daily": {
        "task": "app.tasks.audit_related_futures",
        "schedule": crontab(minute=30, hour=9),  # Daily at 9:30 AM UTC
        "kwargs": {"limit": 30},
    },
    # Note: update_event_tags, enrich_taxonomy_llm, and DataGolf polls are
    # piggybacked on discover_events and poll_all_odds respectively.
    # With dual workers (realtime + background), these could be split out
    # into standalone tasks. Kept as piggybacked for now since the pattern
    # works and reduces scheduling complexity. DataGolf hourly poll is
    # Redis-gated to 1h on discover_events; live poll is gated to 5min on
    # poll_all_odds. Admin endpoints run tasks inline (not via .delay()).
}


# =============================================================================
# Backward-compatible re-exports
#
# These allow existing code that does `from app.tasks import _infer_base_sport`
# or `from app.tasks import celery_app` to keep working.
# =============================================================================

from app.tasks.futures import _infer_base_sport  # noqa: E402, F401 (used by routes/futures.py)
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: E402, F401
