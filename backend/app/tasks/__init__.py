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
from sentry_sdk.integrations.celery import CeleryIntegration

from app.tasks.base import run_async

import time as _time

# ---------------------------------------------------------------------------
# Structured JSON logging for production (Heroku)
# ---------------------------------------------------------------------------
if os.getenv("DYNO"):
    from pythonjsonlogger import jsonlogger

    _json_handler = logging.StreamHandler()
    _json_handler.setFormatter(jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    logging.root.handlers = [_json_handler]
    logging.root.setLevel(logging.INFO)

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
        integrations=[
            CeleryIntegration(monitor_beat_tasks=True),
        ],
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


@celery_app.task(bind=True, name="app.tasks.poll_mlb_pregame")
def poll_mlb_pregame(self):
    """MLB pre-game odds polling tier — densely samples the T-48h..T-2h dark
    window the main loop misses (issue #892)."""
    from app.tasks.odds_polling import _poll_mlb_pregame
    return _tracked_run("poll_mlb_pregame", _poll_mlb_pregame())


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


@celery_app.task(name="app.tasks.check_kalshi_freshness")
def check_kalshi_freshness():
    """Daily check: alert if no Kalshi markets were updated in the last 24 hours."""
    from sqlalchemy import text as sa_text

    async def _check():
        from app.tasks.base import get_task_session
        async with get_task_session() as session:
            result = await session.execute(
                sa_text(
                    "SELECT COUNT(*) FROM futures_markets "
                    "WHERE source = 'kalshi' AND updated_at > NOW() - INTERVAL '24 hours'"
                )
            )
            count = result.scalar()
        if count == 0:
            logger.critical("No Kalshi markets updated in 24h — ingestion may be broken")
            sentry_sdk.capture_message(
                "No Kalshi markets updated in 24h — ingestion may be broken",
                level="error",
            )
        return {"kalshi_updated_24h": count, "alert": count == 0}

    return run_async(_check())


# --- Polymarket ---

@celery_app.task(bind=True, name="app.tasks.poll_polymarket_markets", soft_time_limit=540, time_limit=600)
def poll_polymarket_markets(self):
    """Poll prediction markets from Polymarket (no API key needed)."""
    from app.tasks.polymarket import _poll_polymarket_markets
    return _tracked_run("poll_polymarket", _poll_polymarket_markets())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_polymarket_history")
def backfill_polymarket_history(self, limit: int = 500, fidelity: int = 60, interval: str = "max", mode: str = "resolved_zero"):
    """Backfill historical prices from Polymarket CLOB API for outcomes with sparse data."""
    from app.tasks.polymarket import _backfill_polymarket_price_history
    return _tracked_run("polymarket_history", _backfill_polymarket_price_history(limit, fidelity, interval, mode))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.sync_polymarket_resolved")
def sync_polymarket_resolved(self):
    """Scan closed Polymarket events and update market status to 'resolved'."""
    from app.tasks.polymarket import _sync_polymarket_resolved_status
    return _tracked_run("polymarket_resolved_sync", _sync_polymarket_resolved_status())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_kalshi_history")
def backfill_kalshi_history(self, limit: int = 500, mode: str = "resolved_zero"):
    """Backfill historical prices from Kalshi candlesticks API for outcomes with sparse data."""
    from app.tasks.kalshi import _backfill_kalshi_price_history
    return _tracked_run("kalshi_history", _backfill_kalshi_price_history(limit, mode))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_kalshi_settled")
def backfill_kalshi_settled(self, limit: int = 5000):
    """Recover prices from Kalshi settled events API (much faster than candlesticks)."""
    from app.tasks.kalshi import _backfill_from_settled_events
    return _tracked_run("kalshi_settled", _backfill_from_settled_events(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_candlestick")
def backfill_kalshi_candlestick(self, limit: int = 500):
    """Backfill hourly snapshots from Kalshi candlestick API for sparse outcomes."""
    from app.tasks.kalshi import _backfill_candlestick_snapshots
    return _tracked_run("kalshi_candlestick", _backfill_candlestick_snapshots(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_volume")
def backfill_kalshi_volume(self):
    """Fast volume-only backfill — skips all phases except volume writes."""
    from app.tasks.kalshi import _backfill_volume_only
    return _tracked_run("kalshi_volume", _backfill_volume_only())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_trades")
def backfill_kalshi_trades(self, limit: int = 500):
    """Backfill snapshots from Kalshi trade history for outcomes missing cal_prob."""
    from app.tasks.kalshi import _backfill_trade_history
    return _tracked_run("kalshi_trades", _backfill_trade_history(limit))


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.backfill_polymarket_winners")
def backfill_polymarket_winners(self, limit: int = 10000):
    """Resolve Polymarket winners from Gamma API settlement data."""
    from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
    return _tracked_run("polymarket_winners", _backfill_polymarket_winners_from_api(limit))


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.clob_resolve_drain")
def clob_resolve_drain(self, limit: int = 300, dry_run: bool = False):
    """#989: authoritatively re-resolve the curve-dropped Polymarket cohort
    (pass2_loser/all_losers) via the CLOB API. Writes is_winner with
    resolution_source='clob_authoritative' for the confident resolved_direct /
    resolved_name_match tiers only; void/ambiguous stay excluded. Cursor-resumable."""
    from app.tasks.clob_resolve import clob_resolve_drain as _drain
    return _tracked_run("clob_resolve_drain", _drain(limit=limit, dry_run=dry_run))


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


@celery_app.task(bind=True, name="app.tasks.resolve_winners", soft_time_limit=540, time_limit=600)
def resolve_winners(self, limit: int = 2000):
    """RETIRED from the beat schedule 2026-07-06 (#991) — kept dormant/registered
    for a cheap re-add, NOT currently dispatched. See the retirement note at the
    'backfill-historical-links' beat entry for the bounded re-add path.

    Dedicated winner resolution — API settlement + score-based only.

    Runs independently from the full backfill_winners pipeline, which
    spends most of its 14-min budget on calibration price computation,
    DataGolf leaderboards, golf/hockey commence_time fixes, and other
    non-resolution work. This task focuses solely on resolving is_winner
    from authoritative sources.
    """
    from app.tasks.backfill_winners import _resolve_winners_only
    return _tracked_run("resolve_winners", _resolve_winners_only(limit=limit))


@celery_app.task(bind=True, name="app.tasks.backfill_winners", soft_time_limit=840, time_limit=900)
def backfill_winners(self, dry_run: bool = False, limit: int = 2000):
    """Backfill is_winner on FuturesOutcome from Kalshi settlement + Polymarket resolution."""
    from app.tasks.backfill_winners import _backfill_all_winners
    return _tracked_run("backfill_winners", _backfill_all_winners(dry_run=dry_run, limit=limit))

@celery_app.task(bind=True, name="app.tasks.check_snapshot_sparsity", soft_time_limit=600, time_limit=660)
def check_snapshot_sparsity(self):
    """Daily check for sparse snapshot events + auto-backfill from historical API."""
    from app.tasks.snapshot_sparsity import check_and_backfill_sparse_snapshots
    try:
        result = _tracked_run("check_snapshot_sparsity", check_and_backfill_sparse_snapshots())
        return result
    except Exception as exc:
        logger.exception("check_snapshot_sparsity failed")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(bind=True, name="app.tasks.backfill_historical_odds", soft_time_limit=1800, time_limit=1860)
def backfill_historical_odds_task(self, sport: str = "baseball_mlb", days_back: int = 30, max_events: int = 500):
    """Backfill sparse events from The Odds API historical endpoint. Runs in background."""
    from app.tasks.snapshot_sparsity import _backfill_historical_for_sport
    try:
        result = _tracked_run(
            "backfill_historical_odds",
            _backfill_historical_for_sport(sport=sport, days_back=days_back, max_events=max_events),
        )
        return result
    except Exception as exc:
        logger.exception("backfill_historical_odds failed for %s", sport)
        raise self.retry(exc=exc, countdown=60, max_retries=1)


@celery_app.task(bind=True, name="app.tasks.lookup_and_backfill_extids", soft_time_limit=1800, time_limit=1860)
def lookup_and_backfill_extids_task(self, sport: str = "baseball_mlb", days_back: int = 30, max_events: int = 50):
    """Find events without external_id, look them up in historical API, link and backfill."""
    from app.tasks.snapshot_sparsity import _lookup_and_backfill_missing_extids
    try:
        result = _tracked_run(
            "lookup_and_backfill_extids",
            _lookup_and_backfill_missing_extids(sport=sport, days_back=days_back, max_events=max_events),
        )
        return result
    except Exception as exc:
        logger.exception("lookup_and_backfill_extids failed for %s", sport)
        raise self.retry(exc=exc, countdown=60, max_retries=1)






@celery_app.task(bind=True, name="app.tasks.backfill_historical_links", soft_time_limit=300, time_limit=360)
def backfill_historical_links(self, batch_size: int = 100):
    """Link past-game Kalshi markets to their closed/completed events."""
    from app.tasks.prediction_market_matching import _backfill_historical_links
    return run_async(_backfill_historical_links(batch_size=batch_size))


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
def backfill_box_scores(self, limit: int = 100, priority_calibration: bool = False):
    """Fetch ESPN box scores for completed events missing box_score_data."""
    from app.tasks.espn_sync import _backfill_box_scores
    return _tracked_run("backfill_box_scores", _backfill_box_scores(limit=limit, priority_calibration=priority_calibration))


@celery_app.task(bind=True, name="app.tasks.backfill_espn_ids")
def backfill_espn_ids(self, limit: int = 1000):
    """Match completed events to ESPN IDs for box score backfilling."""
    from app.tasks.espn_sync import _backfill_espn_ids
    return run_async(_backfill_espn_ids(limit=limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_espn_win_prob")
def backfill_espn_win_prob(self, limit: int = 200):
    """Backfill ESPN win probability history for completed events with sparse snapshots."""
    from app.tasks.espn_sync import _backfill_espn_win_probability
    return _tracked_run("espn_win_prob_backfill", _backfill_espn_win_probability(limit))


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


@celery_app.task(bind=True, name="app.tasks.enrich_market_images")
def enrich_market_images(self, limit: int = 50):
    """Fetch images from Pexels API for markets missing image_url."""
    from app.tasks.enrich_markets import enrich_market_images as _enrich
    return _tracked_run("enrich_images", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_tmdb_images",
    soft_time_limit=300,
    time_limit=360,
)
def enrich_tmdb_images(self, limit: int = 50):
    """#882: real TMDB artwork for quoted-title entertainment markets."""
    from app.tasks.enrich_tmdb import enrich_tmdb_images as _enrich
    return _tracked_run("enrich_tmdb", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_market_hooks",
    soft_time_limit=600,
    time_limit=660,
)
def enrich_market_hooks(self, limit: int = 50):
    """Generate LLM hook descriptions for markets missing hook_description.

    #967 (same class as #966): this makes up to `limit` sequential OpenAI calls,
    so the batch can exceed the GLOBAL 300s ``task_time_limit`` (a HARD limit →
    SIGKILL, which is NOT a catchable exception → ``_tracked_run`` records
    neither success nor failure → silent ``no_data``). Mirror the working
    ``enrich_cu_v2_profiles``: a 600s SOFT limit raises a catchable
    SoftTimeLimitExceeded (overruns are recorded + free the slot) under a 660s
    hard limit that gives the batch room to finish.
    """
    from app.tasks.enrich_markets import enrich_market_hooks as _enrich
    return _tracked_run("enrich_hooks", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_discover_llm_metadata",
    soft_time_limit=600,
    time_limit=660,
)
def enrich_discover_llm_metadata(self, limit: int = 100):
    """Generate cached structured LLM metadata for Discover candidates.

    #966: this task makes up to `limit` sequential OpenAI calls (30s client
    timeout each), so the batch routinely exceeds the GLOBAL 300s
    ``task_time_limit`` (a HARD limit → Celery SIGKILLs the worker child).
    SIGKILL is not a catchable Python exception, so ``_tracked_run`` recorded
    neither success nor failure and the task sat at ``no_data`` for ~40h while
    the enrichment backlog froze. Mirror the working sibling
    ``enrich_cu_v2_profiles``: a 600s SOFT limit raises a catchable
    SoftTimeLimitExceeded (an overrun is recorded as a failure and frees the
    worker slot) under a 660s hard limit that gives the LLM batch room to finish.
    """
    from app.tasks.enrich_markets import enrich_discover_llm_metadata as _enrich
    return _tracked_run("enrich_discover_llm", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.enrich_cu_v2_profiles", soft_time_limit=600, time_limit=660)
def enrich_cu_v2_profiles(self, limit: int = 125):
    """Generate Content Understanding v2 profiles for feed-shaped markets."""
    from app.tasks.enrich_markets import enrich_cu_v2_profiles as _enrich
    return _tracked_run("enrich_cu_v2", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.enrich_snippet_angles", soft_time_limit=300, time_limit=360)
def enrich_snippet_angles(self, limit: int = 125):
    """Compute and cache snippet angles for feed-shaped markets."""
    from app.tasks.enrich_markets import enrich_snippet_angles as _enrich
    return _tracked_run("enrich_snippet_angles", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.generate_discover_comparison_candidates")
def generate_discover_comparison_candidates(self, limit: int = 60):
    """Generate cached cross-category comparison-game candidates."""
    from app.tasks.enrich_markets import generate_discover_comparison_candidates as _generate
    return _tracked_run("discover_comparisons", _generate(limit))


@celery_app.task(bind=True, name="app.tasks.evaluate_discover_with_llm")
def evaluate_discover_with_llm(self, limit: int = 50):
    """Grade Discover cards daily and log LLM proposals for admin review."""
    from app.tasks.enrich_markets import evaluate_discover_with_llm as _evaluate
    return _tracked_run("discover_llm_eval", _evaluate(limit))


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_ground_truth_diagnostics")
def snapshot_discover_ground_truth_diagnostics(self, limit: int = 50):
    """Persist advisory Discover ground-truth hit/miss diagnostics."""
    from app.utils.discover_ground_truth_diagnostics import (
        DEFAULT_FEED_URL,
        build_diagnostic_rows_from_debug_payload,
        fetch_debug_payload,
        persist_diagnostic_rows,
    )

    admin_secret = os.getenv("ADMIN_TOKEN")
    if not admin_secret:
        return {"status": "skipped", "reason": "ADMIN_TOKEN missing"}

    feed_url = os.getenv("DISCOVER_GROUND_TRUTH_SNAPSHOT_FEED_URL", DEFAULT_FEED_URL)
    payload = fetch_debug_payload(
        feed_url=feed_url,
        admin_secret=admin_secret,
        limit=limit,
    )
    rows = build_diagnostic_rows_from_debug_payload(payload)
    inserted = _tracked_run(
        "discover_gt_diagnostics",
        persist_diagnostic_rows(rows),
    )
    return {
        "status": "ok",
        "inserted": inserted,
        "limit": limit,
        "feed_url": feed_url,
    }


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_label_eval_run")
def snapshot_discover_label_eval_run(
    self,
    days: int = 30,
    top_k: int = 20,
    limit: int = 5000,
    surface: str | None = None,
    reviewer: str | None = None,
):
    """Persist advisory Discover human-label eval metrics."""
    from app.services.database import async_session_maker
    from app.utils.discover_label_eval_runs import (
        snapshot_discover_label_eval_run as _snapshot_label_eval_run,
    )

    async def _snapshot():
        async with async_session_maker() as db:
            run = await _snapshot_label_eval_run(
                db,
                days=days,
                top_k=top_k,
                limit=limit,
                surface=surface,
                reviewer=reviewer,
            )
            return {
                "status": run.status,
                "run_id": run.run_id,
                "row_count": run.row_count,
                "top_k": run.top_k,
            }

    return _tracked_run("discover_label_eval_snapshot", _snapshot())


@celery_app.task(bind=True, name="app.tasks.import_external_curator_ground_truth")
def import_external_curator_ground_truth(self):
    """Persist configured reviewed external-curator/social ground truth."""
    from app.tasks.base import get_task_session
    from app.utils.external_curator_ground_truth import (
        load_external_curator_ground_truth_report_from_env,
    )
    from app.utils.persisted_external_curator_ground_truth import (
        import_external_curator_ground_truth_rows,
    )

    report = load_external_curator_ground_truth_report_from_env()

    async def _persist():
        async with get_task_session() as session:
            result = await import_external_curator_ground_truth_rows(
                session,
                report["items"],
            )
        return {
            "status": "ok" if report["metadata"].get("configured") else "skipped",
            "metadata": report["metadata"],
            **result,
        }

    return _tracked_run("external_curator_gt_import", _persist())


@celery_app.task(bind=True, name="app.tasks.capture_featured_markets")
def capture_featured_markets(self):
    """Daily capture of top-volume Kalshi/Polymarket markets as featured proxy."""
    from app.tasks.base import get_task_session
    from app.utils.featured_market_capture import capture_all_featured

    async def _capture():
        async with get_task_session() as session:
            return await capture_all_featured(session)

    return _tracked_run("capture_featured_markets", _capture())


@celery_app.task(bind=True, name="app.tasks.check_ground_truth_health")
def check_ground_truth_health(self):
    """Record daily health for advisory Discover ground-truth sources."""
    from app.utils.external_curator_ground_truth import (
        load_external_curator_ground_truth_report_from_env,
    )
    from app.utils.ground_truth_health import (
        assess_ground_truth_report_health,
        summarize_ground_truth_health,
    )
    from app.utils.polymarket_email_ground_truth import (
        load_polymarket_email_ground_truth_report_from_env,
    )

    email_report = load_polymarket_email_ground_truth_report_from_env()
    curator_report = load_external_curator_ground_truth_report_from_env()
    result = summarize_ground_truth_health(
        [
            assess_ground_truth_report_health(
                email_report,
                label="polymarket_email",
            ),
            assess_ground_truth_report_health(
                curator_report,
                label="external_curator",
            ),
        ]
    )

    async def _result():
        return result

    return _tracked_run("ground_truth_health", _result())


@celery_app.task(bind=True, name="app.tasks.precompute_interestingness")
def precompute_interestingness(self):
    """Precompute market interestingness scores and cache in Redis (every 2h)."""
    from app.tasks.precompute_interestingness import _precompute_interestingness
    return _tracked_run("precompute_interestingness", _precompute_interestingness())


@celery_app.task(bind=True, name="app.tasks.check_aggregation_quality")
def check_aggregation_quality(self):
    """Daily: sample events, measure source diversity, alert on single-source spikes."""
    from app.tasks.monitoring import check_aggregation_quality as _check
    return _tracked_run("aggregation_quality", _check())


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


# --- Daily Digest ---

@celery_app.task(bind=True, name="app.tasks.send_daily_digest")
def send_daily_digest_task(self):
    """Send daily digest email to subscribers."""
    import os
    async def _send():
        from app.tasks.base import get_task_session
        from app.tasks.daily_digest import send_daily_digest
        recipients = os.environ.get("DAILY_DIGEST_RECIPIENTS", "").split(",")
        recipients = [r.strip() for r in recipients if r.strip()]
        if not recipients:
            return {"status": "no_recipients"}
        async with get_task_session() as db:
            results = {}
            for email in recipients:
                results[email] = await send_daily_digest(db, email)
            return results
    return run_async(_send())


@celery_app.task(bind=True, max_retries=3, name="app.tasks.send_bug_fixed_email")
def send_bug_fixed_email_task(self, report_id: int):
    """Send a fixed-bug notification email for one bug report."""

    async def _send():
        from app.tasks.base import get_task_session
        from app.tasks.bug_notifications import send_bug_fixed_email

        async with get_task_session() as db:
            return await send_bug_fixed_email(report_id, db)

    try:
        return run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


# --- Bug Report → GitHub Issue ---

@celery_app.task(bind=True, max_retries=2, name="app.tasks.create_github_issue_for_bug_report")
def create_github_issue_for_bug_report_task(self, report_id: int):
    """Create a GitHub Issue from a rage-shake bug report."""

    async def _create():
        from app.tasks.base import get_task_session
        from app.tasks.bug_report_github import (
            GITHUB_TOKEN, build_labels, compute_severity,
            create_github_issue, format_issue_body, format_issue_title,
            add_to_project_board, is_owner_email, should_file_individual_issue,
            compute_fingerprint, comment_on_issue, FRONTEND_URL,
        )
        from app.models.models import BugReport
        from sqlalchemy import select, update as sa_update
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        if not GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set — skipping issue creation for report #%d", report_id)
            return None

        async with get_task_session() as db:
            report = await db.get(BugReport, report_id)
            if not report:
                logger.error("Bug report #%d not found", report_id)
                return None

            if report.backlog_ref:
                logger.info("Bug report #%d already linked to %s — skipping", report_id, report.backlog_ref)
                return None

            if not report.description and not report.screenshot_base64:
                logger.info("Bug report #%d has no description and no screenshot — skipping", report_id)
                return None

            # #885: reporter provenance + routing. Owner reports always file an
            # individual issue; a non-owner feature-request / product
            # misunderstanding is taken "with a grain of salt" — NOT filed
            # individually (it remains in the admin staging archive). Bugs from
            # anyone are filed and severity-labeled.
            is_owner = is_owner_email(report.user_email)
            if not should_file_individual_issue(report.category, is_owner):
                logger.info(
                    "Bug report #%d is an external '%s' (non-bug) — skipping "
                    "individual GitHub issue per #885 routing; kept in staging.",
                    report_id,
                    report.category,
                )
                return {
                    "skipped_routing": True,
                    "report_id": report_id,
                    "category": report.category,
                    "reporter": "external",
                }

            # #975: cross-report dedup. If a DIFFERENT report with the same
            # page+category+diagnosis fingerprint already filed an issue within
            # the last 7 days, comment on it instead of filing a duplicate (a
            # recurring bug accretes evidence on one issue, not N). The existing
            # backlog_ref check only catches the SAME report re-submitted.
            fp = compute_fingerprint(report.app_state, report.category, report.description)
            cutoff = _dt.now(_tz.utc) - _td(days=7)
            recent = await db.execute(
                select(BugReport)
                .where(
                    BugReport.id != report_id,
                    BugReport.backlog_ref.isnot(None),
                    BugReport.created_at >= cutoff,
                )
                .order_by(BugReport.created_at.desc())
                .limit(200)
            )
            for prior in recent.scalars().all():
                ref = (prior.backlog_ref or "").lstrip("#")
                if not ref.isdigit():
                    continue
                if compute_fingerprint(prior.app_state, prior.category, prior.description) != fp:
                    continue
                try:
                    comment_on_issue(
                        int(ref),
                        f"Recurrence: rage-shake report #{report_id} matches this "
                        f"issue's fingerprint (same page + category + diagnosis). "
                        f"[Admin detail]({FRONTEND_URL}/admin/bug-reports)",
                    )
                except Exception:
                    logger.warning(
                        "dedup comment on %s failed — filing a new issue instead",
                        prior.backlog_ref, exc_info=True,
                    )
                    break  # comment failed → fall through to filing a fresh issue
                await db.execute(
                    sa_update(BugReport).where(BugReport.id == report_id).values(backlog_ref=prior.backlog_ref)
                )
                logger.info(
                    "Bug report #%d deduped onto %s (fingerprint %s)",
                    report_id, prior.backlog_ref, fp,
                )
                return {"deduped_onto": prior.backlog_ref, "report_id": report_id, "fingerprint": fp}

            severity = compute_severity(report.description)
            title = format_issue_title(report.description)
            body = format_issue_body(
                report_id=report.id,
                description=report.description,
                category=report.category,
                app_state=report.app_state,
                has_screenshot=bool(report.screenshot_base64),
            )
            labels = build_labels(report.category, severity, is_owner=is_owner)

            issue_number, issue_node_id = create_github_issue(title, body, labels)

            await db.execute(
                sa_update(BugReport).where(BugReport.id == report_id).values(backlog_ref=f"#{issue_number}")
            )
            logger.info("Created GitHub issue #%d for bug report #%d", issue_number, report_id)

            try:
                add_to_project_board(issue_node_id)
            except Exception:
                logger.warning("Failed to add issue #%d to project board (non-fatal)", issue_number, exc_info=True)

            return {"issue_number": issue_number, "report_id": report_id}

    try:
        return run_async(_create())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="app.tasks.digest_external_feature_requests")
def digest_external_feature_requests_task(self):
    """#975: weekly roll-up of external (non-owner) feature-request shakes.

    Per #885 these are NOT filed as individual issues (taken "with a grain of
    salt") — they sit in the admin staging archive with backlog_ref NULL. This
    rolls the past week's batch into ONE digest issue so they're reviewable in
    aggregate, and stamps their backlog_ref to the digest so they aren't
    re-digested next week (reuses the existing column — no migration).
    """

    async def _digest():
        from app.tasks.base import get_task_session
        from app.tasks.bug_report_github import (
            GITHUB_TOKEN, create_github_issue, format_digest_body, is_owner_email,
        )
        from app.models.models import BugReport
        from sqlalchemy import select, update as sa_update
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        if not GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set — skipping feature-request digest")
            return {"skipped": "no_token"}

        now = _dt.now(_tz.utc)
        cutoff = now - _td(days=7)
        async with get_task_session() as db:
            result = await db.execute(
                select(BugReport)
                .where(
                    BugReport.category == "feature_request",
                    BugReport.backlog_ref.is_(None),
                    BugReport.created_at >= cutoff,
                )
                .order_by(BugReport.created_at.desc())
                .limit(500)
            )
            rows = result.scalars().all()
            # external-only (owner feature-requests are filed individually, but
            # guard anyway in case provenance changes)
            external = [r for r in rows if not is_owner_email(r.user_email)]
            if not external:
                logger.info("Feature-request digest: nothing external this week")
                return {"digested": 0}

            reports = [
                {
                    "id": r.id,
                    "page": (r.app_state or {}).get("current_page")
                    or (r.app_state or {}).get("current_tab")
                    or "?",
                    "description": r.description,
                    "user_email": r.user_email,
                }
                for r in external
            ]
            week_label = now.strftime("%Y-%m-%d")
            body = format_digest_body(reports, week_label)
            title = f"Weekly external feature-request digest — {week_label} ({len(reports)})"
            issue_number, _ = create_github_issue(
                title, body, ["alert-intake", "type:feature", "reporter:external"]
            )

            # stamp each report's backlog_ref to the digest so it is not
            # re-digested next week (no schema migration; reuses the column)
            ids = [r.id for r in external]
            await db.execute(
                sa_update(BugReport)
                .where(BugReport.id.in_(ids))
                .values(backlog_ref=f"#{issue_number}")
            )
            logger.info(
                "Feature-request digest: rolled %d external reports into issue #%d",
                len(ids), issue_number,
            )
            return {"digested": len(ids), "issue_number": issue_number}

    return _tracked_run("feature_request_digest", _digest())


@celery_app.task(bind=True, name="app.tasks.compare_ws_shadow")
def compare_ws_shadow_task(self):
    """#836 Batch 2 (SHADOW): compute the WS-shadow-vs-current is_winner match
    rate per source and store it in Redis for review (no live watching). Gates
    the eventual flip to WS-authoritative — flip only when agreement is high."""

    async def _compare():
        import json as _json
        from app.tasks.base import get_task_session
        from app.tasks.redis_state import get_async_redis_client
        from app.services.ws_shadow import compare_shadow_verdicts, SHADOW_COMPARISON_KEY

        async with get_task_session() as session:
            report = await compare_shadow_verdicts(session)
        try:
            rc = get_async_redis_client()
            await rc.set(SHADOW_COMPARISON_KEY, _json.dumps(report), ex=14 * 86400)
            await rc.aclose()
        except Exception:
            logger.warning("ws_shadow: failed to store comparison", exc_info=True)
        logger.info("ws_shadow comparison: %s", report.get("total"))
        return report

    return _tracked_run("ws_shadow_comparison", _compare())


# --- Calibration Prices ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_calibration_prices")
def compute_calibration_prices(self):
    """Compute calibration_probability on resolved outcomes (Parts A/B/C)."""
    from app.tasks.backfill_winners import _compute_calibration_prices
    return _tracked_run("calibration_prices", _compute_calibration_prices())


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


# --- Tier 1 Event Coverage Monitoring ---

@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.check_tier1_coverage")
def check_tier1_coverage(self):
    """Alert when Tier 1 Kalshi game markets have no matching event."""
    from app.tasks.monitoring import check_tier1_event_coverage
    return run_async(check_tier1_event_coverage())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.compute_snapshot_distribution")
def compute_snapshot_distribution(self):
    """Compute snapshot count distribution and cache in Redis."""
    from app.tasks.monitoring import compute_snapshot_distribution_impl
    return run_async(compute_snapshot_distribution_impl())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.update_max_movement")
def update_max_movement(self):
    """Update max_movement_24h on futures_markets from outcome data."""
    async def _impl():
        from app.tasks.base import get_task_session
        from sqlalchemy import text
        async with get_task_session() as session:
            result = await session.execute(text("""
                UPDATE futures_markets fm
                SET max_movement_24h = sub.max_mv
                FROM (
                    SELECT fo.market_id, MAX(ABS(fo.probability_change_24h)) AS max_mv
                    FROM futures_outcomes fo
                    WHERE fo.probability_change_24h IS NOT NULL
                    GROUP BY fo.market_id
                ) sub
                WHERE fm.id = sub.market_id
                  AND fm.status IN ('open', 'active')
                  AND (fm.max_movement_24h IS DISTINCT FROM sub.max_mv)
            """))
            await session.commit()
            return {"updated": result.rowcount}
    return run_async(_impl())


# --- Data Quality Monitoring ---

@celery_app.task(bind=True, name="app.tasks.check_data_quality")
def check_data_quality(self):
    """Check classification and matching health, alert on issues."""
    from app.tasks.data_quality import _check_data_quality
    return _tracked_run("check_data_quality", _check_data_quality())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.run_data_quality_watchdog")
def run_data_quality_watchdog(self):
    """Run data quality watchdog: check freshness, coverage, sparsity; alert on failures."""
    from app.tasks.data_quality_watchdog import _run_data_quality_watchdog
    return _tracked_run("data_quality_watchdog", _run_data_quality_watchdog())


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

@celery_app.task(bind=True, name="app.tasks.export_engagement")
def export_engagement(self):
    """Nightly export of Discover engagement data for ranking review."""
    from app.tasks.export_engagement import _export_engagement_impl
    return _tracked_run("export_engagement", _export_engagement_impl())


# --- Push Notifications ---

@celery_app.task(bind=True, name="app.tasks.send_daily_challenge_push")
def send_daily_challenge_push(self):
    """Send daily challenge push notification to all opted-in device tokens."""
    from app.tasks.push_notifications import _send_daily_challenge_push
    return _tracked_run("daily_challenge_push", _send_daily_challenge_push())


@celery_app.task(bind=True, name="app.tasks.send_big_move_alerts")
def send_big_move_alerts(self):
    """Send push alerts for futures markets with >15pp movement to users who pinned them."""
    from app.tasks.push_notifications import _send_big_move_alerts
    return _tracked_run("big_move_alerts", _send_big_move_alerts())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_calibration_main")
def precompute_calibration_main(self):
    """Precompute main /api/calibration response and cache in Redis (every 1h)."""
    from app.tasks.precompute_calibration import _precompute_calibration_main
    return _tracked_run("precompute_calibration_main", _precompute_calibration_main())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_time_horizon_calibration")
def compute_time_horizon_calibration(self):
    """Precompute time-horizon calibration and cache in Redis (every 6h)."""
    from app.tasks.precompute_calibration import _compute_time_horizon_calibration
    return _tracked_run("compute_time_horizon_calibration", _compute_time_horizon_calibration())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_fair_fight_comparison")
def compute_fair_fight_comparison(self):
    """Precompute fair-fight source comparison and cache in Redis (every 6h)."""
    from app.tasks.precompute_calibration import _compute_fair_fight_comparison
    return _tracked_run("compute_fair_fight_comparison", _compute_fair_fight_comparison())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.snapshot_coverage_metrics")
def snapshot_coverage_metrics(self):
    """Daily snapshot of coverage metrics for tracking progress."""
    from app.tasks.precompute_calibration import _snapshot_coverage_metrics
    return _tracked_run("coverage_metrics", _snapshot_coverage_metrics())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.precompute_category_pages")
def precompute_category_pages(self):
    """Precompute category page responses and cache in Redis (every 1h)."""
    from app.tasks.precompute_category_pages import _precompute_all_category_pages
    return _tracked_run("precompute_category_pages", _precompute_all_category_pages())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_backfill_winners_status")
def precompute_backfill_winners_status(self):
    """Precompute backfill-winners/status response and cache in Redis (every 1h)."""
    from app.tasks.precompute_backfill_winners_status import _precompute_backfill_winners_status
    return _tracked_run("precompute_backfill_winners_status", _precompute_backfill_winners_status())


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
    "poll-mlb-pregame": {
        # MLB-only pre-game tier (issue #892): fills the T-48h..T-2h dark
        # window the 6h-lookahead main loop misses. Self-gates (quota guard,
        # main-loop-active check, no-games check) so most fires are cheap skips.
        "task": "app.tasks.poll_mlb_pregame",
        "schedule": crontab(minute="*/30"),
    },
    "sync-sports-hourly": {
        "task": "app.tasks.sync_sports",
        "schedule": crontab(minute=0),
    },
    "discover-new-events": {
        "task": "app.tasks.discover_events",
        "schedule": crontab(minute="5,35"),  # Every 30 min (was 15)
    },
    "compute-gei-batch": {
        "task": "app.tasks.compute_gei_batch",
        "schedule": crontab(minute="*/30"),  # Every 30 min (was 10)
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
        "schedule": crontab(minute=45, hour="*/2"),  # Every 2 hours — markets created days ahead, pricing appears day-of
    },
    "check-kalshi-freshness-daily": {
        "task": "app.tasks.check_kalshi_freshness",
        "schedule": crontab(minute=0, hour=9),  # Daily at 9:00 AM UTC — alert if no updates in 24h
        "options": {"queue": "background"},
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
    # DISABLED: replaced by worker-ws WebSocket consumer (#836/#837).
    "poll-live-prediction-markets": {
        "task": "app.tasks.poll_live_prediction_markets",
        "schedule": 120.0,  # Every 2 minutes — covers live + upcoming (3h) games
    },
    "sync-mlb-win-probability": {
        "task": "app.tasks.sync_mlb_win_probability",
        "schedule": 120.0,  # Every 2 minutes during MLB season
    },
    "track-statpal-usage": {
        "task": "app.tasks.track_statpal_usage",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "check-tier1-coverage": {
        "task": "app.tasks.check_tier1_coverage",
        "schedule": crontab(minute=30),  # Every hour at :30
    },
    "backfill-team-links": {
        "task": "app.tasks.backfill_team_links",
        "schedule": crontab(minute=50),  # Every hour — roster matching is cheap, large backlog to clear
        "kwargs": {"limit": 2000, "use_llm": False},
    },
    "merge-duplicate-events": {
        "task": "app.tasks.merge_duplicate_events",
        "schedule": crontab(minute="*/30"),  # Every 30 min (was 10)
        "kwargs": {"dry_run": False},
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
    # #975: weekly roll-up of external feature-request shakes into one digest issue
    "digest-external-feature-requests-weekly": {
        "task": "app.tasks.digest_external_feature_requests",
        "schedule": crontab(minute=0, hour=14, day_of_week=1),  # Weekly Monday 2:00 PM UTC
        "options": {"queue": "background"},
    },
    # #836 Batch 2 (SHADOW): refresh the WS-shadow-vs-current match rate for review
    "compare-ws-shadow": {
        "task": "app.tasks.compare_ws_shadow",
        "schedule": crontab(minute=20, hour="*/6"),
        "options": {"queue": "background"},
    },
    # March Madness bracket sync — disabled (season over). Re-enable in March.
    # "sync-mm-bracket": {
    #     "task": "app.tasks.sync_mm_bracket",
    #     "schedule": crontab(minute="*/15", hour="*", day_of_month="15-30", month_of_year="3,4"),
    # },
    "enrich-market-hooks": {
        "task": "app.tasks.enrich_market_hooks",
        # Feed-prioritized only; keep volume modest to avoid spending on the
        # entire open-market backlog.
        "schedule": crontab(minute=40, hour="*/6"),
        "kwargs": {"limit": 100},
    },
    "enrich-discover-llm-metadata": {
        "task": "app.tasks.enrich_discover_llm_metadata",
        # Async/cached only: enrich feed-shaped cards, never on feed request.
        "schedule": crontab(minute=10, hour="*/6"),
        "kwargs": {"limit": 125},
    },
    "enrich-snippet-angles": {
        "task": "app.tasks.enrich_snippet_angles",
        "schedule": crontab(minute=30, hour="*/6"),
        "kwargs": {"limit": 125},
        "options": {"queue": "background"},
    },
    "enrich-cu-v2-profiles": {
        "task": "app.tasks.enrich_cu_v2_profiles",
        "schedule": crontab(minute=50, hour="*/12"),
        "kwargs": {"limit": 125},
        "options": {"queue": "background"},
    },
    "generate-discover-comparison-candidates": {
        "task": "app.tasks.generate_discover_comparison_candidates",
        "schedule": crontab(minute=20, hour=9),
        "kwargs": {"limit": 60},
    },
    "evaluate-discover-with-llm-daily": {
        "task": "app.tasks.evaluate_discover_with_llm",
        "schedule": crontab(minute=35, hour=9),
        "kwargs": {"limit": 50},
    },
    "snapshot-discover-ground-truth-diagnostics-daily": {
        "task": "app.tasks.snapshot_discover_ground_truth_diagnostics",
        "schedule": crontab(minute=50, hour=9),
        "kwargs": {"limit": 50},
        "options": {"queue": "background"},
    },
    "import-external-curator-ground-truth-daily": {
        "task": "app.tasks.import_external_curator_ground_truth",
        "schedule": crontab(minute=45, hour=9),
        "options": {"queue": "background"},
    },
    "check-ground-truth-health-daily": {
        "task": "app.tasks.check_ground_truth_health",
        "schedule": crontab(minute=40, hour=9),
        "options": {"queue": "background"},
    },
    "capture-featured-markets-daily": {
        "task": "app.tasks.capture_featured_markets",
        "schedule": crontab(minute=0, hour=6),  # Daily at 6:00 AM UTC
        "options": {"queue": "background"},
    },
    "enrich-market-images": {
        "task": "app.tasks.enrich_market_images",
        "schedule": crontab(minute=50, hour="*/4"),  # 6x daily — fetch Pexels images
        "kwargs": {"limit": 200},
    },
    "enrich-tmdb-images": {
        "task": "app.tasks.enrich_tmdb_images",
        "schedule": crontab(minute=35, hour="*/6"),  # #882: real TMDB art for quoted-title entertainment
        "kwargs": {"limit": 50},
        "options": {"queue": "background"},
    },
    "precompute-interestingness": {
        "task": "app.tasks.precompute_interestingness",
        "schedule": crontab(minute=20, hour="*/2"),  # Every 2 hours at :20
        "options": {"queue": "background"},
    },
    "precompute-category-pages": {
        "task": "app.tasks.precompute_category_pages",
        "schedule": crontab(minute=25),  # Every hour at :25 — warm caches for politics/entertainment/economics/weather
        "options": {"queue": "background"},
    },
    "precompute-backfill-winners-status": {
        "task": "app.tasks.precompute_backfill_winners_status",
        "schedule": crontab(minute=35),  # Every hour at :35 — cache expensive backfill status queries
        "options": {"queue": "background"},
    },
    "check-aggregation-quality": {
        "task": "app.tasks.check_aggregation_quality",
        "schedule": crontab(minute=0, hour=7),  # Daily at 7:00 AM UTC
    },
    "update-max-movement": {
        "task": "app.tasks.update_max_movement",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
        "options": {"queue": "background"},
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
    "data-quality-watchdog": {
        "task": "app.tasks.run_data_quality_watchdog",
        "schedule": crontab(minute=45, hour="*/2"),  # Every 2 hours at :45
        "options": {"queue": "background"},
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
    "backfill-winners": {
        "task": "app.tasks.backfill_winners",
        "schedule": crontab(minute=45, hour="3,9,15,21"),  # Every 6 hours, offset from mark-resolved
    },
    # #991: resolve-winners beat entry RETIRED 2026-07-06. The standalone task
    # stopped being dispatched after 3 soft-limit failures (round 82) and is
    # redundant — backfill_winners runs the same shared `_resolve_winners_only`
    # path and covers the clean_resolution work at scale (~559K is_winner marks
    # /2h, OPS-343). The task def is kept (dormant, unscheduled) for a cheap
    # re-add. RE-ADD PATH if 2h freshness ever proves insufficient (watch feed
    # R6 resolved-suppression): re-add as a BOUNDED forward-only pass — small
    # limit + statement_timeout inner-op bound (NOT limit-only, which is a
    # non-fix per #969) on the realtime queue.
    "backfill-historical-links": {
        "task": "app.tasks.backfill_historical_links",
        "schedule": crontab(minute=30, hour="2,5,8,11,14,17,20,23"),  # 8x/day
        "kwargs": {"batch_size": 500},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-price-history": {
        "task": "app.tasks.backfill_polymarket_history",
        "schedule": crontab(minute=0, hour="4,10,16,22"),  # Every 6h, offset from backfill-winners
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-price-history": {
        "task": "app.tasks.backfill_kalshi_history",
        "schedule": crontab(minute=30, hour="4,10,16,22"),  # Every 6h, 30min after Polymarket
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-open-sparse": {
        "task": "app.tasks.backfill_polymarket_history",
        "schedule": crontab(minute=15, hour="3,9,15,21"),  # Every 6h, offset from resolved
        "kwargs": {"limit": 100, "mode": "open_sparse"},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-open-sparse": {
        "task": "app.tasks.backfill_kalshi_history",
        "schedule": crontab(minute=45, hour="3,9,15,21"),  # Every 6h, 30min after Polymarket
        "kwargs": {"limit": 100, "mode": "open_sparse"},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-settled-events": {
        "task": "app.tasks.backfill_kalshi_settled",
        "schedule": crontab(minute=0, hour="5,11,17,23"),  # Every 6h, offset from candlestick backfill
        "kwargs": {"limit": 5000},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-trade-history": {
        "task": "app.tasks.backfill_kalshi_trades",
        "schedule": crontab(minute=15, hour="5,11,17,23"),  # Every 6h, 15min after settled
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    "sync-polymarket-resolved-status": {
        "task": "app.tasks.sync_polymarket_resolved",
        "schedule": crontab(minute=30, hour="5,11,17,23"),  # Every 6h, 30min after Kalshi settled
        "options": {"queue": "background"},
    },
    "backfill-polymarket-winners": {
        "task": "app.tasks.backfill_polymarket_winners",
        "schedule": crontab(minute=45, hour="5,11,17,23"),  # Every 6h, 15min after PM sync
        "kwargs": {"limit": 10000},
        "options": {"queue": "background"},
    },
    "clob-resolve-drain": {
        "task": "app.tasks.clob_resolve_drain",
        "schedule": crontab(minute=20, hour="1,7,13,19"),  # Every 6h, clear of :40-:58 cal windows
        # #989: Batch-0 PASSED (16/16 resolved_direct hand-verified, zero wrong
        # maps, self-validating exact-label tier; revertible via the distinct
        # resolution_source). Auto-write enabled for resolved_direct /
        # resolved_name_match only; ambiguous/void stay excluded.
        "kwargs": {"limit": 300, "dry_run": False},
        "options": {"queue": "background"},
    },
    "backfill-box-scores": {
        "task": "app.tasks.backfill_box_scores",
        "schedule": crontab(minute=15, hour="5,11,17,23"),  # Every 6h, offset from others
        "kwargs": {"limit": 500, "priority_calibration": True},
        "options": {"queue": "background"},
    },
    "backfill-espn-ids": {
        "task": "app.tasks.backfill_espn_ids",
        "schedule": crontab(minute=45, hour="5,11,17,23"),  # Every 6h, 30min after box scores
        "kwargs": {"limit": 1000},
        "options": {"queue": "background"},
    },
    "backfill-espn-win-prob": {
        "task": "app.tasks.backfill_espn_win_prob",
        "schedule": crontab(minute=0, hour="6,12,18,0"),  # Every 6h, offset from ESPN IDs
        "kwargs": {"limit": 200},
        "options": {"queue": "background"},
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
    # Note: enrich-market-hooks and enrich-market-images schedules above
    # already handle both initial generation and regeneration.
    # Note: update_event_tags, enrich_taxonomy_llm, and DataGolf polls are
    # piggybacked on discover_events and poll_all_odds respectively.
    # With dual workers (realtime + background), these could be split out
    # into standalone tasks. Kept as piggybacked for now since the pattern
    # works and reduces scheduling complexity. DataGolf hourly poll is
    # Redis-gated to 1h on discover_events; live poll is gated to 5min on
    # poll_all_odds. Admin endpoints run tasks inline (not via .delay()).
    "daily-digest": {
        "task": "app.tasks.send_daily_digest",
        "schedule": crontab(hour=13, minute=0),  # 8am ET (UTC-5) / 6am PT
        "options": {"queue": "background"},
    },
    "export-engagement-nightly": {
        "task": "app.tasks.export_engagement",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM UTC
        "options": {"queue": "background"},
    },
    "snapshot-coverage-metrics-daily": {
        "task": "app.tasks.snapshot_coverage_metrics",
        "schedule": crontab(hour=3, minute=0),  # 3:00 AM UTC daily
        "options": {"queue": "background"},
    },
    "daily-challenge-push": {
        "task": "app.tasks.send_daily_challenge_push",
        "schedule": crontab(hour=14, minute=0),  # 2:00 PM UTC (10am ET / 7am PT)
        "options": {"queue": "background"},
    },
    "big-move-alerts": {
        "task": "app.tasks.send_big_move_alerts",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": "background"},
    },
    "precompute-calibration-main": {
        "task": "app.tasks.precompute_calibration_main",
        "schedule": crontab(minute=15),  # Every 1 hour at :15
        "options": {"queue": "background"},
    },
    "compute-time-horizon-calibration": {
        "task": "app.tasks.compute_time_horizon_calibration",
        "schedule": crontab(minute=0, hour="1,7,13,19"),  # Every 6 hours
        "options": {"queue": "background"},
    },
    "compute-fair-fight-comparison": {
        "task": "app.tasks.compute_fair_fight_comparison",
        "schedule": crontab(minute=15, hour="1,7,13,19"),  # Every 6 hours, offset 15min
        "options": {"queue": "background"},
    },
}


# =============================================================================
# Backward-compatible re-exports
#
# These allow existing code that does `from app.tasks import _infer_base_sport`
# or `from app.tasks import celery_app` to keep working.
# =============================================================================

from app.tasks.futures import _infer_base_sport  # noqa: E402, F401 (used by routes/futures.py)
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: E402, F401
