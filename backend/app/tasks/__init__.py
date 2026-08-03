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
    """Run an async task and record its HONEST outcome in Redis.

    Queue 300H (#1515). This used to record a success for any invocation that
    returned without raising, which is how three calibration tasks reported
    ``health: healthy`` while producing nothing: a time-horizon build that
    returned ``horizons_done: 0/4`` every 6h, a price sweep that returned
    ``terminal: partial`` on every deadline-truncated run, and a coverage
    snapshot that swallowed its own exception and returned ``terminal:
    "failed"``. The returned summary was right there in every case; nothing
    read it.

    Now the summary is classified by the pure contract in
    ``app.utils.task_verdict`` and the verdict decides which counter moves:

    * ``complete``   → success, as before
    * ``partial``    → incomplete: no success, no escalation, never GREEN
    * ``failed``     → failure (returned, not thrown) → degraded immediately
    * ``unknown``    → authoritative: incomplete. Legacy (no terminal truth in
      the summary at all): recorded as a success exactly as before, but stamped
      ``unverified`` — the invocation returned, which is not proof of work.

    Enforcement is scoped to ``task_verdict.ENFORCED_TASKS`` — the four
    calibration adapters. Every other task classifies to a non-authoritative
    ``unknown`` and records exactly as it did before, because a ``status`` key
    means "no live games" or "nothing to backfill" in most of this codebase and
    reading it as a terminal would swap one false GREEN for thirty false REDs.

    Thrown exceptions keep their existing behaviour. ``BaseException`` is now
    caught rather than ``Exception`` so a cancellation or a warm-shutdown kill
    records a terminal before propagating — an in-flight beat killed by a
    deploy used to vanish from both the ledger and the counters (r346).
    """
    from app.tasks.redis_state import (
        record_task_incomplete,
        record_task_success,
        record_task_failure,
        touch_worker_liveness,
    )
    from app.utils.task_verdict import COMPLETE, FAILED, UNKNOWN, verdict_for

    # #1280 Item 3: every task run refreshes this worker generation's liveness so
    # the phase-heartbeat watchdog can tell a frozen marker owned by a live
    # generation (real wedge → RED) from one left by a dead/restarted generation
    # (stale → reconcile, no page). Best-effort; never blocks the task.
    touch_worker_liveness()
    start = _time.monotonic()
    try:
        result = run_async(async_fn)
        duration_ms = (_time.monotonic() - start) * 1000
        # Extract summary from task result (most tasks return dicts)
        summary = result if isinstance(result, dict) else {"result": str(result)[:200]}
        verdict = verdict_for(task_name, result)

        if verdict.verdict == COMPLETE:
            record_task_success(
                task_name, duration_ms, summary,
                verdict=COMPLETE, verdict_reason=verdict.reason,
            )
        elif verdict.verdict == FAILED:
            record_task_failure(
                task_name, duration_ms,
                f"task returned a failed terminal ({verdict.reason})",
                verdict=FAILED, verdict_reason=verdict.reason,
            )
        elif verdict.verdict == UNKNOWN and not verdict.authoritative:
            # Legacy shape: preserve the pre-300H recording so ~100 tasks that
            # predate the contract keep a usable health surface, but say plainly
            # that nothing was verified.
            record_task_success(
                task_name, duration_ms, summary,
                verdict="unverified", verdict_reason=verdict.reason,
            )
        else:
            record_task_incomplete(
                task_name, duration_ms,
                verdict=verdict.verdict, verdict_reason=verdict.reason,
                result_summary=summary,
            )
        return result
    except BaseException as exc:  # noqa: BLE001 — cancellation must leave a terminal
        duration_ms = (_time.monotonic() - start) * 1000
        record_task_failure(
            task_name, duration_ms,
            str(exc) or type(exc).__name__,
            verdict="thrown", verdict_reason=type(exc).__name__,
        )
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

# #1197: explicit TCP keepalive timers shared by the broker + result backend and
# the get_redis_client helpers (single source in config.py). Empty {} on platforms
# without TCP_KEEPIDLE (macOS CI) — redis-py then falls back to plain keepalive.
from app.tasks.config import socket_keepalive_options as _socket_keepalive_options
from app.tasks.result_retention import RESULT_EXPIRES_S as _RESULT_EXPIRES_S
from app.tasks.result_retention import apply_result_suppression as _apply_result_suppression

_KEEPALIVE_OPTS = _socket_keepalive_options()

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
    # Queue 300R Item 1: bound result residency explicitly. Celery's default is
    # 24h, and on a 50MB allkeys-lru instance a 24h result key is not "stored",
    # it is queued for eviction alongside everything else. Admin status polls
    # read a task_id while the operator is on the page, so an hour is generous.
    # The per-task half of this (suppressing results nothing can poll) is
    # applied after the beat schedule — see result_retention.py.
    "result_expires": _RESULT_EXPIRES_S,
    # ------------------------------------------------------------------------
    # Redis connection stability (#1197). The sustained TLS
    # `[SSL: UNEXPECTED_EOF_WHILE_READING]` ConnectionError volume (~135-180/24h,
    # firstSeen Feb) is Heroku-Redis idle-connection churn: the stacktrace lands
    # in celery/backends/redis.py `get()` → `connect_check_health` → TLS
    # `do_handshake`, i.e. a connection Heroku had idle-closed is being
    # re-established and the handshake EOFs. TCP keepalive keeps pooled
    # connections alive so they aren't idle-reaped (fewer reconnects = fewer
    # handshake EOFs), and a health-check interval makes redis-py proactively
    # PING+recycle a stale connection instead of failing on first reuse. Applied
    # to BOTH the broker and the result backend (the trace is the backend; the
    # sibling Sentry groups on the broker share the same root cause).
    "redis_socket_keepalive": True,          # result-backend TCP keepalive
    "redis_backend_health_check_interval": 25,
    "redis_socket_connect_timeout": 5,       # bound the handshake (was unbounded)
    # #1197 (r246 option a) — the pool/recycle tuning the #233 keepalive-alone
    # didn't deliver (churn rose 135→294/24h after it). Two levers:
    #   1) socket_keepalive_options: explicit TCP KEEPIDLE/INTVL/CNT so pooled
    #      connections are probed BEFORE Heroku's idle-reap window instead of dying
    #      on next reuse with a TLS EOF (bare socket_keepalive=True uses the ~2h OS
    #      default idle — longer than the reap, so it never helped). See config.py.
    #   2) retry_on_timeout + broker_connection_retry_on_startup: a transient
    #      handshake EOF/timeout retries transparently instead of surfacing as a
    #      ConnectionError. Applied to BOTH broker and result backend.
    "redis_retry_on_timeout": True,          # result-backend transient-error retry
    "broker_connection_retry_on_startup": True,
    "broker_connection_retry": True,
    "broker_transport_options": {
        "socket_keepalive": True,
        "socket_keepalive_options": _KEEPALIVE_OPTS,
        "health_check_interval": 25,
        "retry_on_timeout": True,
    },
    "result_backend_transport_options": {
        "socket_keepalive": True,
        "socket_keepalive_options": _KEEPALIVE_OPTS,
        "health_check_interval": 25,
        "retry_on_timeout": True,
    },
}

if broker_use_ssl:
    celery_config["broker_use_ssl"] = broker_use_ssl
    celery_config["redis_backend_use_ssl"] = broker_use_ssl

celery_app.conf.update(**celery_config)

# #1280 Item 3: refresh this worker generation's liveness on every Celery
# heartbeat, independent of task execution. This keeps the liveness key fresh
# even for a briefly-idle worker (so the phase-heartbeat watchdog never mis-reads
# a healthy generation as dead), and — because the heartbeat is emitted by the
# worker's main process, not the wedged task's event loop — it stays fresh during
# a genuine event-loop wedge, so a real stall still reads RED. Wrapped
# defensively: a signal-API change must never block worker startup.
try:  # pragma: no cover - signal wiring exercised by the worker, not unit tests
    from celery.signals import worker_heartbeat as _worker_heartbeat

    @_worker_heartbeat.connect
    def _refresh_worker_liveness(**_kwargs):
        try:
            from app.tasks.redis_state import touch_worker_liveness

            touch_worker_liveness()
        except Exception:
            pass
except Exception:  # pragma: no cover - defensive
    pass

# =============================================================================
# Queue routing: realtime vs background vs heavy workers
#
# realtime (Standard-2X, concurrency=4):
#   High-frequency tasks driving user-visible live game data.
#   Never blocked by batch jobs.
#
# background (Standard-1X, concurrency=2):
#   Short (<300s) hourly/daily batch tasks and matching-pipeline drivers
#   (match_prediction_markets, poll_kalshi_markets, merges). Latency-tolerant
#   but must still fire promptly — so it must NOT share slots with 600s
#   grinders. Memory budget: 2 × 200MB + ~100MB overhead ≈ 500MB (fits 512MB
#   dyno). NOTE (#233): the sentinels moved OFF background onto `heavy` — the
#   ~40-beat, 2-slot queue was starving their morning fires (no_run_cached).
#
# heavy (Standard-1X, concurrency=2):
#   ISOLATION LANE for the calibration precompute family — the user-facing
#   cache-warmers (precompute_calibration_main hourly, calibration_prices,
#   time_horizon, fair_fight, source_intelligence, coverage,
#   backfill_winners_status). These are 600s-class but latency-relevant: they
#   warm /calibration and the source dashboards. On a dedicated 2-slot worker
#   they can NEVER starve — at most 2-3 of them ever fire in the same minute
#   (only precompute_calibration_main is hourly; the rest are 6h and staggered
#   :00/:10/:15/:30), so 2 slots always suffice. This is the structural fix for
#   the recurring background-queue starvation (cal_price #183, then
#   time_horizon, then precompute_calibration_main #223) that per-task
#   minute-offset juggling could not durably solve.
#
#   Also here (#233): the 5 sentinels (flow/grid/horizon/settled daily
#   07:10-07:45 UTC + calibration weekly). They are daily and cheap (~5s
#   detect-only) — the antithesis of a slot-filler — but were dying as
#   no_run_cached on the congested background queue every morning (#232's
#   diagnosis). Their staggered daily fires never collide with the hourly
#   :15 precompute, so the 2 heavy slots absorb them without starving the
#   cache-warmers. Sentinels must fire PROMPTLY (they are alarms); heavy is
#   the only lane that guarantees a free slot at 07:10-07:45.
#
#   Deliberately NOT here: the big backfills (backfill_winners 840s, the
#   kalshi/polymarket backfills 600-960s). They stay on `background` where
#   they have always lived — moving them here would just relocate the
#   starvation (they'd fill both heavy slots and delay the hourly calibration
#   warmer, observed live during the #224 rollout). Backfill-vs-fast-task
#   contention on background was never the reported problem; calibration
#   starvation was. So heavy stays a small, guaranteed-free calibration lane.
#
# HEAVY membership rule: the calibration/precompute cache-warmer family + the
# 5 sentinels (#233). Applied programmatically to both task_routes and the beat
# schedule's per-entry `options["queue"]` (beat options override task_routes, so
# both must agree — see the loop after the beat_schedule definition).
# =============================================================================

from kombu import Queue

celery_app.conf.task_queues = [
    Queue("realtime", routing_key="realtime"),
    Queue("background", routing_key="background"),
    Queue("heavy", routing_key="heavy"),
]

celery_app.conf.task_default_queue = "background"

celery_app.conf.task_routes = {
    # --- Realtime: live game data (30s-120s cycle) ---
    "app.tasks.poll_all_odds": {"queue": "realtime"},
    "app.tasks.poll_datagolf_inplay": {"queue": "realtime"},
    "app.tasks.poll_sport_odds": {"queue": "realtime"},
    "app.tasks.sync_espn_live_events": {"queue": "realtime"},
    "app.tasks.poll_live_prediction_markets": {"queue": "realtime"},
    "app.tasks.sync_mlb_win_probability": {"queue": "realtime"},
    "app.tasks.sync_statpal_live_plays": {"queue": "realtime"},
    "app.tasks.sync_statpal_livescores": {"queue": "realtime"},
    "app.tasks.heartbeat": {"queue": "realtime"},
    "app.tasks.transition_event_statuses": {"queue": "realtime"},
    # --- Everything else routes to background (default queue) ---
    # --- 600s-class grinders route to `heavy` (applied below) ---
}

# The big backfills + fast tasks stay on `background` (their historical home).
# Listed here for documentation / the guard test: these must NOT leak onto the
# heavy calibration lane, or they'd fill its 2 slots and re-starve the hourly
# /calibration warmer (observed live during the #224 rollout). Backfill-vs-fast
# contention on background was never the reported problem.
_HEAVY_KEEP_ON_BACKGROUND = {
    "app.tasks.match_prediction_markets",   # linkage pipeline, every 15 min
    "app.tasks.poll_kalshi_markets",        # ingest cadence
    "app.tasks.merge_duplicate_events",     # matching pipeline
    "app.tasks.merge_degenerate_combat_events",
    # NOTE: the 5 sentinels moved to HEAVY_TASKS (Queue #233) — see below.
    # the big backfills — deliberately NOT on heavy (see comment above)
    "app.tasks.backfill_winners",
    "app.tasks.backfill_kalshi_candlestick",
    "app.tasks.backfill_kalshi_history",
    "app.tasks.backfill_kalshi_settled",
    "app.tasks.backfill_kalshi_trades",
    "app.tasks.backfill_kalshi_volume",
    "app.tasks.backfill_polymarket_history",
    "app.tasks.backfill_polymarket_winners",
    "app.tasks.backfill_espn_win_prob",
    "app.tasks.backfill_team_identities",
}

# The heavy lane = the calibration/precompute cache-warmer family PLUS the
# daily/weekly sentinels (Queue #233). Kept explicit (not derived from
# decorators) so routing is greppable and stable.
HEAVY_TASKS = {
    "app.tasks.precompute_calibration_main",       # hourly :15 — the frozen one (#223)
    "app.tasks.compute_calibration_prices",        # cal_price (#183)
    "app.tasks.compute_time_horizon_calibration",  # time_horizon (r228: prior fix didn't take)
    "app.tasks.compute_fair_fight_comparison",
    "app.tasks.precompute_source_intelligence",
    "app.tasks.snapshot_coverage_metrics",
    "app.tasks.precompute_backfill_winners_status",
    # Sentinels (Queue #233): moved off `background` because the morning beats
    # (flow 07:10 / grid 07:25 / horizon 07:40 / settled 07:45 UTC) were dying
    # as no_run_cached on the congested ~40-beat, 2-slot background queue
    # (#232's diagnosis). They are daily (calibration weekly) and cheap (~5s
    # detect-only), so 2 heavy slots absorb them with room to spare — the hourly
    # precompute (:15) never collides with the staggered :10/:25/:40/:45 fires.
    # All 5 sentinels move together (the code has always treated them as one
    # group); horizon at 07:40 is inside the protected window, so leaving it on
    # background would keep a beat contending exactly where #233 needs quiet.
    "app.tasks.flow_sentinel",
    "app.tasks.grid_sentinel",
    "app.tasks.grid_register_sentinel",
    "app.tasks.horizon_sentinel",
    "app.tasks.settled_concept_sentinel",
    "app.tasks.calibration_sentinel",
    # Queue #258: the Board Sentinel keeps the board itself honest (duplicate
    # fingerprints, stale Inbox, template-P1 share, blocked-in-Inbox, missing
    # area labels). Cheap + daily like its siblings; heavy queue for a free slot.
    "app.tasks.board_sentinel",
    # #1201/#1193/#1202: daily MLB schedule self-heal + coverage. Cheap and daily
    # like the sentinels, and it must fire promptly at 07:05 so the standing
    # inverted rows are healed before the 07:10 flow sentinel reads resolved_state.
    "app.tasks.mlb_schedule_coverage",
}

for _heavy_task in HEAVY_TASKS:
    celery_app.conf.task_routes[_heavy_task] = {"queue": "heavy"}

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


@celery_app.task(name="app.tasks.run_freshness_watchdog")
def run_freshness_watchdog():
    """#995 NEVER-AGAIN: alert the moment market CREATION stalls per source, or a
    poll's phase marker stops advancing (suspected event-loop block). This is the
    creates-specific + heartbeat signal the 28-day freeze needed — the coarse
    "updated in 24h" check below stayed green throughout it."""
    from app.tasks.watchdog import _run_freshness_watchdog
    return _tracked_run("freshness_watchdog", _run_freshness_watchdog())


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
def backfill_kalshi_settled(self, limit: int = 5000, only_series=None):
    """Recover prices from Kalshi settled events API (much faster than candlesticks).

    ``only_series`` (#227 Item 2) pins the scan to specific series prefixes (e.g.
    ``["KXPGA"]`` for the Open) to settle an already-concluded event NOW."""
    from app.tasks.kalshi import _backfill_from_settled_events
    return _tracked_run("kalshi_settled", _backfill_from_settled_events(limit, only_series=only_series))


@celery_app.task(bind=True, soft_time_limit=420, time_limit=480, name="app.tasks.backfill_settled_gap_creation")
def backfill_settled_gap_creation(self, limit: int = 1500):
    """#138/#995: create Kalshi markets that opened+settled during the 2026-06-09→
    07-08 creation freeze (gotcha #38) — invisible to the open-poll and only
    UPDATEd (never created) by backfill_kalshi_settled. Bounded + resumable."""
    from app.tasks.kalshi import _backfill_settled_gap_creation
    return _tracked_run("kalshi_gap_creation", _backfill_settled_gap_creation(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.recover_datagolf_participation")
def recover_datagolf_participation(self, limit: int = 150):
    """#994 recover-first: reclassify wrongly-VOIDed DataGolf losers back into the
    calibration curve. Dedicated task (NOT a backfill_winners phase) because that
    pipeline is budget-starved before Phase 0g; this drains the ~17K DNP cohort
    reliably (bounded + resumable, quota-polite)."""
    from app.tasks.backfill_winners import _recover_datagolf_participation
    return _tracked_run("datagolf_recovery", _recover_datagolf_participation(limit=limit))


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.regrade_polymarket_under_signflip")
def regrade_polymarket_under_signflip(self):
    """#145 Item 1: run the #137 Polymarket Under/No sign-flip re-grade as a
    DEDICATED task. It was a backfill_winners phase positioned AFTER
    calibration_prices, but that pipeline hits its 840s budget guard and returns
    partial (stopped_before=calibration_prices) BEFORE the #137 integrity block
    ever runs — so the regrade applied 0 despite ~36K rows matching in prod. This
    single cheap set-based UPDATE (flips cp AND opening, so it's durable against a
    later cal-price fallback) drains the class reliably each cycle. Idempotent."""
    from app.tasks.backfill_winners import _regrade_polymarket_under_signflip
    return _tracked_run("poly_under_signflip", _regrade_polymarket_under_signflip())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.unresolve_datagolf_premature")
def unresolve_datagolf_premature(self):
    """#146 Item 2: starvation sibling of the #145 poly flip. The #137
    calibration-integrity block runs AFTER calibration_prices, which the
    backfill_winners budget guard stops before — so this un-resolve of
    prematurely-resolved DataGolf markets never runs in prod. Dedicated task;
    cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _unresolve_datagolf_premature
    return _tracked_run("datagolf_premature_unresolve", _unresolve_datagolf_premature())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.null_impossible_both_sides_openings")
def null_impossible_both_sides_openings(self):
    """#146 Item 2: starvation sibling of the #145 poly flip (same budget guard).
    Nulls impossible both-sides=1.0 binary openings/cp that poison the calibration
    curve. Dedicated task; cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _null_impossible_both_sides_openings
    return _tracked_run("impossible_both_sides_null", _null_impossible_both_sides_openings())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.correct_both_winner_guess_side")
def correct_both_winner_guess_side(self):
    """#997: starvation sibling of the #146 integrity beats. Demotes the tier-0
    guess side of a both-winner mutually-exclusive binary to loser when a
    strictly-higher authority sibling already won. The in-drain call is
    budget-guarded out on heavy cycles, so this dedicated beat guarantees it
    runs. Cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _correct_both_winner_guess_side
    return _tracked_run("both_winner_guess_flip", _correct_both_winner_guess_side())


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
    from app.tasks.clob_resolve import (
        clob_resolve_drain as _drain,
        _DEFAULT_WRITE_TIERS,
    )
    # Amendment 1 — ordinal tier CAPPED ENABLE (#989 Item 2, Queue #124). Batch-0
    # PASSED (25/25 label-agree, 0 disagreements, vintage-stratified). Enable the
    # ordinal tier in the beat, capped at _ORDINAL_FIRST_BATCH_CAP=2,000 cumulative
    # writes (Redis-tracked; the drain stops writing ordinal once the cap is hit).
    # The cap holds until winrate + curve stability are verified on the first
    # ≤2,000; uncapping for the full ~15K drain is a deliberate later step.
    tiers = _DEFAULT_WRITE_TIERS + ("resolved_ordinal",)
    return _tracked_run("clob_resolve_drain", _drain(
        limit=limit, dry_run=dry_run, write_tiers=tiers, enable_ordinal=True,
    ))


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


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.ensure_perf_indexes")
def ensure_perf_indexes(self):
    """#1197: build the missing team-route event indexes CONCURRENTLY at runtime
    (gotcha #31 — never in a migration). High time limit: CONCURRENTLY on the
    events table can take a while; idempotent (IF NOT EXISTS)."""
    from app.utils.ensure_indexes import ensure_perf_indexes as _run
    return run_async(_run())


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
def backfill_espn_win_prob(self, limit: int = 200, oldest_first: bool = False):
    """Backfill ESPN win probability history for completed events with sparse snapshots.

    oldest_first=True reaches the OLD tail the newest-first pass starves (gotcha #41).
    """
    from app.tasks.espn_sync import _backfill_espn_win_probability
    return _tracked_run("espn_win_prob_backfill", _backfill_espn_win_probability(limit, oldest_first))


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.compute_game_moments")
def compute_game_moments(self, limit: int = 60):
    """THE MOMENTS ENGINE (#1168): join scoring plays to win-prob swings for
    recently-completed MLB games, persist confident moments, and report the MLB
    ground-truth agreement rate. Soft limit set because it makes per-event MLB API
    calls (gotcha #51)."""
    from app.tasks.game_moments import _compute_game_moments
    return _tracked_run("game_moments", _compute_game_moments(limit=limit))


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


@celery_app.task(
    bind=True,
    name="app.tasks.backfill_market_shapes",
    time_limit=660,
    soft_time_limit=600,
)
def backfill_market_shapes(self, limit: int = 40000, dry_run: bool = False):
    """Classify + persist market shape into market_type (Queue #194 Item 1).

    Bounded/resumable/deadline-guarded. Only touches market_type IS NULL rows,
    so it also shapes freshly-ingested markets each run."""
    from app.tasks.backfill_market_shapes import _backfill_market_shapes
    return _tracked_run(
        "market_shape_backfill",
        _backfill_market_shapes(limit=limit, dry_run=dry_run),
    )


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


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300, name="app.tasks.mlb_schedule_coverage")
def mlb_schedule_coverage(self):
    """#1201/#1193/#1202: daily MLB schedule self-heal + coverage. Repairs the
    standing inverted / future-settled rows (gotcha #32/#46) via MLB ground truth,
    then runs the read-only coverage check so the 07:10 Flow Sentinel resolved_state
    reads a clean slate. Heavy queue (#233) — cheap, daily, must fire promptly."""
    from app.tasks.schedule_coverage import run_mlb_schedule_coverage_and_repair
    return _tracked_run("mlb_schedule_coverage", run_mlb_schedule_coverage_and_repair())


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


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_candidate_pool")
def snapshot_discover_candidate_pool(
    self,
    limit: int = 300,
    retention_days: int = 30,
):
    """Persist the pre-ranking Discover candidate pool for offline replay (#142)."""
    from app.services.database import async_session_maker
    from app.utils.discover_candidate_snapshot import (
        snapshot_discover_candidate_pool as _snapshot_candidate_pool,
    )

    async def _snapshot():
        async with async_session_maker() as db:
            return await _snapshot_candidate_pool(
                db,
                limit=limit,
                retention_days=retention_days,
            )

    return _tracked_run("discover_candidate_snapshot", _snapshot())


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


# --- Entity Registry Seeds (#171 execution rails; seed is on-demand only. The
# poly matchup backfill now ALSO has a 6h catch-up beat — #173/#1024 — since the
# ingest write-hook needs a net for the historical backlog + any missed rows) ---

@celery_app.task(
    bind=True,
    soft_time_limit=1500,
    time_limit=1560,
    name="app.tasks.seed_entity_registry",
)
def seed_entity_registry(self, persons_only: bool = True):
    """#171/#1020 — Run the A1 entity-registry fold-in seed in-worker.

    Removes the ``heroku run`` requirement (EPERM from the sandboxed crank). The
    person fold-in scans all individual-sport events + golf/motorsport futures
    outcomes, so it can exceed the GLOBAL 300s ``task_time_limit`` (a HARD limit →
    SIGKILL); a 1500s SOFT limit under a 1560s hard limit gives it room while
    keeping the overrun catchable. Idempotent + commits per batch, so a re-trigger
    resumes and a soft-limit overrun leaves committed progress intact.
    """
    from app.tasks.entity_seed import seed_entity_registry_impl
    return run_async(seed_entity_registry_impl(persons_only))


@celery_app.task(
    bind=True,
    soft_time_limit=900,
    time_limit=960,
    name="app.tasks.canonicalize_entities",
)
def canonicalize_entities_task(self, dry_run: bool = False):
    """#175 Item 1 — collapse same-family duplicate entities in-worker.

    On-demand merge of edition-multiplied person/team dups (e.g. "Alexandra Eala"
    ×15 across tennis tournament sport_keys) into one canonical entity, aliases
    repointed. Census-gated (cross-family homonyms left apart), additive-first,
    idempotent. 900s soft limit keeps the overrun catchable above the 300s cap.
    """
    from app.tasks.entity_seed import canonicalize_entities_impl
    return run_async(canonicalize_entities_impl(dry_run))


@celery_app.task(
    bind=True,
    soft_time_limit=900,
    time_limit=960,
    name="app.tasks.backfill_polymarket_matchups",
)
def backfill_polymarket_matchups(self, all_groups: bool = False):
    """#171/#1021 — Backfill ``matchup_title`` on poly game sub-markets in-worker.

    Recovers the "A vs. B" matchup from a sibling row in the same Polymarket group
    so the resolution engine reads both participants. Idempotent (only writes where
    missing); commits every 2000 rows. 900s soft limit keeps the overrun catchable
    above the global 300s hard cap.
    """
    from app.tasks.entity_seed import backfill_polymarket_matchups_impl
    return run_async(backfill_polymarket_matchups_impl(all_groups))


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


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.calibration_sentinel")
def calibration_sentinel(self, file_issues=True, suppress_known=True):
    """Calibration Sentinel (#1054): mine resolved-outcome cohorts across
    category × source × series × structure × table-provenance, n-weighted MCE per
    cohort, evidence-pack each break, and file ONE deduped GitHub issue per cohort
    fingerprint. Read-only detection — never writes market data (gotcha #21).
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the task's own 600s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.calibration_sentinel import _run_calibration_sentinel
    return _tracked_run(
        "calibration_sentinel",
        _run_calibration_sentinel(file_issues=file_issues, suppress_known=suppress_known),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.flow_sentinel")
def flow_sentinel(self, file_issues=True, canary=False):
    """Flow Sentinel (#1078): drive the six scripted user flows against
    production (search gold-set, duplicate events, event completeness, resolved
    state, chart density, category/Discover), assert a concrete correctness
    condition per flow, and file ONE deduped GitHub issue per failing flow. This
    is the reliability/design program's measurement — it removes Alex from the
    detection loop. Read-only against production; the sentinel files work, never
    writes data. The 840s soft limit (under the 900s hard limit, clear of the
    global 300s) plus the run's 540s inner deadline keep it from SIGKILLing
    untracked (#966)."""
    from app.tasks.flow_sentinel import _run_flow_sentinel
    return _tracked_run(
        "flow_sentinel",
        _run_flow_sentinel(file_issues=file_issues, canary=canary),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.grid_sentinel")
def grid_sentinel(self, file_issues=True):
    """Grid Sentinel (Queue #196): audit each championship grid (MLB/NBA/NHL),
    classify every finding as REAL vs an EXPLAINED calendar/blend artifact so RED
    always means REAL, and file ONE deduped GitHub issue per league with real
    defects. Includes the ground-truth envelope self-check (merged prob must live
    inside its source envelope) + a DB freshness self-check — retiring the Manus
    ground-truth file from accuracy duty. Read-only; never writes market data
    (gotcha #21). The 840s soft limit (under the 900s hard limit, clear of the
    global 300s) plus the run's 480s inner deadline keep it from SIGKILLing
    untracked (#966)."""
    from app.tasks.grid_sentinel import _run_grid_sentinel
    return _tracked_run(
        "grid_sentinel",
        _run_grid_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660,
                 name="app.tasks.grid_register_sentinel")
def grid_register_sentinel(self, apply=False, file_issues=True):
    """Grid Register Sentinel (Queue #295): diff each committed grid register
    against current source inventory. Unambiguous drift (exact-identity ticker
    rename, authoritative settlement) proposes a validated next version;
    ambiguous drift is never applied and files ONE deduped P2 needs-triage issue
    per league with an MC-ready question. Defaults to ``apply=False`` (dry-run /
    diff only) so publication is an explicit choice. Identity only — reads no
    probabilities and writes no market data (gotcha #21). The 600s soft limit
    sits under the 660s hard limit and above the run's 240s inner deadline, so
    it can never SIGKILL untracked (#966)."""
    from app.tasks.grid_register_sentinel import _run_grid_register_sentinel
    return _tracked_run(
        "grid_register_sentinel",
        _run_grid_register_sentinel(apply=apply, file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.horizon_sentinel")
def horizon_sentinel(self, file_issues=True):
    """Horizon Sentinel (Queue #223): read THE HORIZON CALENDAR
    (app/config/majors_calendar.yaml — every knowable major through 2030) and
    escalate as each event nears — T-30 candidate, T-14 needs-page, T-7 marquee
    escalation, IN-PROGRESS-WITHOUT-PAGE = P0 — filing ONE deduped GitHub issue
    per uncovered event. A marquee event should never arrive without a page (The
    Open / World Cup top-slot failure class). Read-only; files work, never data.
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the run's 180s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.horizon_sentinel import _run_horizon_sentinel
    return _tracked_run(
        "horizon_sentinel",
        _run_horizon_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.settled_concept_sentinel")
def settled_concept_sentinel(self, file_issues=True):
    """Settled-Concept Sentinel (Queue #226): within ~24h of any marquee concept
    settling (THE HORIZON CALENDAR knows the dates), read the LIVE event-concept
    surface and assert the settled contract — champion hero (winner market,
    won:true, top prob), field membership (round/leader markets show only real
    competitors), evolution chart resolves to one ~100% winner line (no 0.99-wall,
    no fizzle), and no double-graded round markets. Classifies REAL vs EXPLAINED so
    RED means REAL, and files ONE deduped GitHub issue per concept with REAL
    defects. The guard #225 earned. Read-only; files work, never data (gotcha #21).
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the run's 240s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.settled_concept_sentinel import _run_settled_concept_sentinel
    return _tracked_run(
        "settled_concept_sentinel",
        _run_settled_concept_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.board_sentinel")
def board_sentinel(self, file_issues=True):
    """Board Sentinel (Queue #258): keep GitHub `Ready` a trustworthy execution
    source by keeping the BOARD itself honest. Daily checks — duplicate sentinel
    fingerprints among open alert-intake (the r252 dupe class), untriaged Inbox
    cards >48h, template-P1 share above the documented cap, blocked/parked cards in
    Inbox, and alert-intake issues missing every area:* label. Classifies REAL vs
    UNKNOWN (API/auth inability is never GREEN, never a cleanup accusation); files
    ONE deduped board-cleanup issue on RED and closes it on GREEN via the shared
    filing rail. Read-only against GitHub — never bulk-mutates the board (Ops owns
    the one-time cleanup). The 840s soft limit (under the 900s hard limit) plus the
    run's 120s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.board_sentinel import _run_board_sentinel
    return _tracked_run(
        "board_sentinel",
        _run_board_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90, name="app.tasks.sentry_snapshot")
def sentry_snapshot(self):
    """#237 Item 1: cache the top Sentry issues by 24h volume to Redis
    (bainluck:sentry:top_24h) so the ops-snapshot endpoint reads a warm key instead
    of calling Sentry live on the request path. No-ops (writes a no_token status)
    when SENTRY_AUTH_TOKEN is absent. Light HTTP task — runs on the background
    queue; the 60s soft limit keeps it clear of the global 300s hard limit."""
    from app.tasks.sentry_snapshot import _run_sentry_snapshot
    return _tracked_run("sentry_snapshot", _run_sentry_snapshot())


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


@celery_app.task(bind=True, name="app.tasks.poll_datagolf_inplay")
def poll_datagolf_inplay(self):
    """#144: dedicated ~90s in-play golf poll (schedule-window gated).

    Decoupled from poll_all_odds so live golf keeps a sub-minute-feeling cadence
    even when no ball sports are live. The window guard inside makes this a single
    Redis check off-tournament (near-zero cost)."""
    from app.tasks.datagolf import _poll_datagolf_inplay
    return _tracked_run("datagolf_inplay", _poll_datagolf_inplay())


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


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.merge_degenerate_combat_events")
def merge_degenerate_combat_events_task(self, dry_run: bool = True, limit: int = 500):
    """#175 Item 3 — merge degenerate home==away fight events into their real
    odds-registry event so orphaned Kalshi fight markets assemble multi-source."""
    from app.tasks.sports import _merge_degenerate_combat_events_impl
    return run_async(_merge_degenerate_combat_events_impl(dry_run=dry_run, limit=limit))


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


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300, name="app.tasks.send_morning_digest")
def send_morning_digest(self):
    """Morning Digest v1 (Queue #200): once daily (~7 AM PT) push the 3-5 most
    interesting probabilities to opted-in device tokens. Reuses the cached
    Discover interestingness scores (one content brain, cheap reads only)."""
    from app.tasks.morning_digest import _run_morning_digest
    return _tracked_run("morning_digest", _run_morning_digest())


# Queue 272 (#1459): the canonical compute is a single frozen-semantics CTE whose
# wall time on the production population VARIES widely with concurrent DB load —
# measured 605.8s at a quiet moment (18:24 UTC) but 910s under a 399-deep
# background backfill queue (22:33 UTC). At the old 600s (then 900s) soft limit it
# kept dying with SoftTimeLimitExceeded BEFORE it could publish, so once the 2h
# TTL expired the cache blanked and /api/calibration 503'd. The gates forbid
# chunking/changing the query, so the fix is real headroom over the observed
# contended range: soft 1500 / hard 1560 (25/26 min). One successful run warms the
# fresh key AND the durable 7-day last-good key (see _precompute_calibration_main),
# after which any later overrun is invisible to the route (it serves last-good as
# stale). Memory is unchanged (same payload); the heavy lane (concurrency 2,
# hourly cadence, siblings 6h-staggered) absorbs the longer hold. The underlying
# query cost / backfill DB-contention is a separate perf follow-up (#1197 stays
# open) — this queue restores availability, not compute speed.
@celery_app.task(bind=True, soft_time_limit=1500, time_limit=1560, name="app.tasks.precompute_calibration_main")
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


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_source_intelligence")
def precompute_source_intelligence(self):
    """Precompute the Source-Intelligence ("Measure") snapshot into Redis (every 6h).

    L2-129 / #206: keeps the 4 heavy corpus queries off the request path and never
    caches a degraded/empty build (the blank-page poisoning bug)."""
    from app.tasks.precompute_source_intelligence import _compute_source_intelligence
    return _tracked_run("precompute_source_intelligence", _compute_source_intelligence())


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


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_discover_candidate_base")
def precompute_discover_candidate_base(self):
    """Precompute + publish the anonymous Discover candidate-ID base (Queue 285)."""
    from app.tasks.precompute_category_pages import _precompute_discover_candidate_base
    return _tracked_run(
        "precompute_discover_candidate_base", _precompute_discover_candidate_base()
    )


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90, name="app.tasks.refresh_open_commentary")
def refresh_open_commentary(self):
    """Refresh the live AI commentary box for The Open Championship (Open-only,
    live-only). Cheap Redis-gated skip off-tournament; one OpenAI call per run
    while live. See app/tasks/golf_commentary.py."""
    from app.tasks.golf_commentary import _refresh_open_commentary
    return _tracked_run("refresh_open_commentary", _refresh_open_commentary())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.precompute_admin_audit_all")
def precompute_admin_audit_all(self):
    """Precompute /api/admin/audit/all (4 grid subprocesses) into Redis (L2-90)."""
    from app.tasks.precompute_admin_health import _precompute_admin_audit_all
    return _tracked_run("precompute_admin_audit_all", _precompute_admin_audit_all())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_admin_link_rate")
def precompute_admin_link_rate(self):
    """Precompute /api/admin/prediction-markets/link-rate into Redis (L2-90)."""
    from app.tasks.precompute_admin_health import _precompute_admin_link_rate
    return _tracked_run("precompute_admin_link_rate", _precompute_admin_link_rate())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_admin_matured_linkage")
def precompute_admin_matured_linkage(self):
    """Precompute the matured-linkage metric into Redis (Queue #220/221 Item 2)."""
    from app.tasks.precompute_admin_health import _precompute_admin_matured_linkage
    return _tracked_run("precompute_admin_matured_linkage", _precompute_admin_matured_linkage())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_backfill_winners_status")
def precompute_backfill_winners_status(self):
    """Precompute backfill-winners/status response and cache in Redis (every 1h)."""
    from app.tasks.precompute_backfill_winners_status import _precompute_backfill_winners_status
    return _tracked_run("precompute_backfill_winners_status", _precompute_backfill_winners_status())


@celery_app.task(bind=True, soft_time_limit=280, time_limit=300, name="app.tasks.precompute_backfill_progress")
def precompute_backfill_progress(self):
    """Precompute backfill-progress heavy census (density + June ledger) — #179/#1052."""
    from app.tasks.precompute_backfill_progress import _precompute_backfill_progress
    return _tracked_run("precompute_backfill_progress", _precompute_backfill_progress())


@celery_app.task(bind=True, soft_time_limit=280, time_limit=300, name="app.tasks.backfill_combat_wps")
def backfill_combat_wps(self, limit: int = 500, dry_run: bool = False):
    """Combat-targeted oldest-first WPS backfill — reaches the settled-fight tail (#178)."""
    from app.tasks.backfill_combat_wps import _backfill_combat_wps
    return _tracked_run("backfill_combat_wps", _backfill_combat_wps(limit=limit, dry_run=dry_run))


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
    "poll-datagolf-inplay": {
        # #144: dedicated ~90s in-play golf poll. Decoupled from poll_all_odds
        # (whose tick rate — bounded by live ball-sports — throttled the L2-66
        # piggyback to ~5min in the golf-only summer window). Self-gates on a
        # Redis schedule-window flag so it's a single Redis check off-tournament
        # (near-zero cost). Realtime queue for the fast cadence.
        "task": "app.tasks.poll_datagolf_inplay",
        "schedule": 90.0,
    },
    "refresh-open-commentary": {
        # Same-day live feature (2026-07-19): AI commentary box for The Open
        # Championship. Self-gates on the golf in-play window (cheap Redis skip
        # off-tournament) and generates only while The Open is LIVE — one OpenAI
        # call per run, at most. Background queue (runs the full golf aggregation).
        "task": "app.tasks.refresh_open_commentary",
        "schedule": 180.0,
        "options": {"queue": "background"},
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
    "run-freshness-watchdog": {
        # #995 NEVER-AGAIN: creates-specific freshness + poll phase-heartbeat.
        # Every 10 min so a 10-min event-loop-block heartbeat has resolution;
        # both checks are cheap (2 indexed MAX queries + a few Redis reads).
        "task": "app.tasks.run_freshness_watchdog",
        "schedule": crontab(minute="*/10"),
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
    "compute-game-moments": {
        "task": "app.tasks.compute_game_moments",
        "schedule": crontab(minute=20, hour="*/2"),  # Every 2h — offline join over recently-completed MLB games
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
    "merge-degenerate-combat-events": {
        # #175 Item 3 — self-heal the "15132461 class": degenerate home==away
        # fight events (a combat market whose matchup parsed to one competitor)
        # get folded into their real odds-registry event so the page unifies and
        # the Kalshi market repoints. Every 6h catches weekend fight-night events
        # same-day. Idempotent (skips 0/>1 real matches; never guesses).
        "task": "app.tasks.merge_degenerate_combat_events",
        "schedule": crontab(minute=25, hour="*/6"),
        "kwargs": {"dry_run": False, "limit": 500},
        "options": {"queue": "background"},
    },
    "canonicalize-entities-daily": {
        # #175 Item 1 — self-heal same-family duplicate person/team entities
        # (edition-multiplied across sport_keys). Idempotent: a clean registry
        # yields 0 merges. Census-gated so cross-family homonyms are left apart.
        # Also runs post-seed inside seed_entity_registry_impl; the two paths are
        # safe to overlap because each merge is a no-op once collapsed.
        "task": "app.tasks.canonicalize_entities",
        "schedule": crontab(minute=15, hour=8),  # Daily 08:15 UTC
        "kwargs": {"dry_run": False},
        "options": {"queue": "background"},
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
    # #142/RANK-2: human-label gold-set eval, snapshotted daily so tapworthy@20 /
    # boring@20 / love-recall trend over time and thin strata surface.
    "snapshot-discover-label-eval-run-daily": {
        "task": "app.tasks.snapshot_discover_label_eval_run",
        "schedule": crontab(minute=55, hour=9),
        "options": {"queue": "background"},
    },
    # #142/RANK-2: pre-ranking candidate-pool snapshot for the offline replay
    # harness (per-candidate features + served rank + score anatomy).
    "snapshot-discover-candidate-pool-daily": {
        "task": "app.tasks.snapshot_discover_candidate_pool",
        "schedule": crontab(minute=5, hour=10),
        "kwargs": {"limit": 300, "retention_days": 30},
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
    "precompute-discover-candidate-base": {
        "task": "app.tasks.precompute_discover_candidate_base",
        # Every 2 min — keep the anonymous Discover candidate-ID base warm so cold
        # feed pages skip the ~3–6s nine-query discovery (Queue 285). The 60s
        # freshness window (CANDIDATE_BASE_FRESH_SECONDS) enforces the "no looser
        # than the anon feed freshness contract" bound; the bounded last-good key
        # + request-path publish keep cold pages covered between beats.
        "schedule": crontab(minute="*/2"),
        "options": {"queue": "background"},
    },
    "precompute-backfill-winners-status": {
        "task": "app.tasks.precompute_backfill_winners_status",
        "schedule": crontab(minute=35),  # Every hour at :35 — cache expensive backfill status queries
        "options": {"queue": "background"},
    },
    "precompute-backfill-progress": {
        "task": "app.tasks.precompute_backfill_progress",
        "schedule": crontab(minute="*/15"),  # Every 15 min — #179/#1052 progress census (density + June ledger)
        "options": {"queue": "background"},
    },
    "backfill-combat-wps": {
        "task": "app.tasks.backfill_combat_wps",
        "schedule": crontab(minute=50, hour=9),  # Daily 09:50 UTC — self-heal the settled-fight blend tail (#178)
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
    "calibration-sentinel-weekly": {
        # #1054: self-serve calibration break detection → evidence pack → issue
        # filing. Weekly (Monday 06:20 UTC) — resolved-outcome cohorts move slowly,
        # and the new-format early-warning tier catches a broken format long before
        # a 50K-outcome pileup, so a weekly cadence is enough. heavy queue (#233).
        "task": "app.tasks.calibration_sentinel",
        "schedule": crontab(minute=20, hour=6, day_of_week=1),  # Weekly Monday 06:20 UTC
        "options": {"queue": "heavy"},
    },
    "mlb-schedule-coverage-daily": {
        # #1201/#1193/#1202: daily MLB schedule self-heal + coverage. Runs at 07:05
        # UTC — 5 min BEFORE the flow sentinel (07:10) — so the standing inverted /
        # future-settled MLB rows (gotcha #32/#46) are re-dated/voided and the
        # official-slate reconciliation is fresh when resolved_state reads. heavy
        # queue (#233 — must fire promptly; no bg starvation).
        "task": "app.tasks.mlb_schedule_coverage",
        "schedule": crontab(minute=5, hour=7),  # Daily 07:05 UTC
        "options": {"queue": "heavy"},
    },
    "flow-sentinel-daily": {
        # #1078: scripted user-flow acceptance sentinel against production. Daily
        # (07:10 UTC) — user-facing regressions (search break, unmerged dup,
        # empty live game, resolved-shown-as-live, dark charts, empty category)
        # need faster detection than the weekly calibration cadence. Files one
        # deduped issue per failing flow. heavy queue (#233 — no bg starvation).
        "task": "app.tasks.flow_sentinel",
        "schedule": crontab(minute=10, hour=7),  # Daily 07:10 UTC
        "options": {"queue": "heavy"},
    },
    "grid-sentinel-daily": {
        # Queue #196: championship grid reliability sentinel. Daily (07:25 UTC,
        # after the flow sentinel) — grid defects (missing teams/columns,
        # monotonicity, envelope corruption, stale-when-active futures) need
        # daily detection. Classifies findings against the season-window artifact
        # registry so RED means REAL; files one deduped issue per RED league.
        # heavy queue (#233).
        "task": "app.tasks.grid_sentinel",
        "schedule": crontab(minute=25, hour=7),  # Daily 07:25 UTC
        "options": {"queue": "heavy"},
    },
    "grid-register-sentinel-daily": {
        # Queue #295: diff every committed grid register against live source
        # inventory. Runs at 07:32 UTC — after the grid sentinel (07:25) so the
        # two never contend for the heavy dyno, and before the horizon sentinel
        # (07:40). Dry-run by default: it proposes and reports versions but does
        # not publish until apply=True is passed explicitly.
        "task": "app.tasks.grid_register_sentinel",
        "schedule": crontab(minute=32, hour=7),  # Daily 07:32 UTC
        "options": {"queue": "heavy"},
    },
    "horizon-sentinel-daily": {
        # Queue #223: marquee-event early-warning sentinel. Daily (07:40 UTC,
        # after the grid sentinel) — reads THE HORIZON CALENDAR
        # (app/config/majors_calendar.yaml) and escalates each major as it nears
        # (T-30 candidate, T-14 needs-page, T-7 marquee escalation,
        # IN-PROGRESS-WITHOUT-PAGE = P0), filing one deduped issue per uncovered
        # event so a marquee never arrives without a page. heavy queue (#233).
        "task": "app.tasks.horizon_sentinel",
        "schedule": crontab(minute=40, hour=7),  # Daily 07:40 UTC
        "options": {"queue": "heavy"},
    },
    "settled-concept-sentinel-daily": {
        # Queue #226: within ~24h of any marquee concept settling (THE HORIZON
        # CALENDAR knows the dates), assert the settled contract on the LIVE
        # event-concept surface — champion hero, field membership, evolution chart
        # resolves, no double-graded round markets — classifying REAL vs EXPLAINED
        # so RED means REAL, filing one deduped issue per concept with REAL
        # defects. The guard #225 earned. Daily (07:45 UTC, after the horizon
        # sentinel). heavy queue (#233).
        "task": "app.tasks.settled_concept_sentinel",
        "schedule": crontab(minute=45, hour=7),  # Daily 07:45 UTC
        "options": {"queue": "heavy"},
    },
    "board-sentinel-daily": {
        # Queue #258: keep the BOARD honest so GitHub `Ready` stays a trustworthy
        # execution source — duplicate sentinel fingerprints, stale Inbox cards,
        # template-P1 share, blocked-in-Inbox, missing area labels. Classifies REAL
        # vs UNKNOWN so RED means real; files one deduped cleanup issue and closes
        # it on green via the shared filing rail. Daily (07:50 UTC, after the other
        # sentinels so it observes a settled board). heavy queue (#233).
        "task": "app.tasks.board_sentinel",
        "schedule": crontab(minute=50, hour=7),  # Daily 07:50 UTC
        "options": {"queue": "heavy"},
    },
    "recategorize-other-daily": {
        "task": "app.tasks.recategorize_other",
        "schedule": crontab(minute=0, hour=8),  # Daily at 8:00 AM UTC
        "kwargs": {"limit": 2000},
    },
    "sentry-snapshot-15min": {
        # #237 Item 1: cache the top Sentry issues by 24h volume so the ops-snapshot
        # endpoint reads a warm Redis key instead of calling Sentry live. Light HTTP
        # task on the background queue; no-ops without SENTRY_AUTH_TOKEN.
        "task": "app.tasks.sentry_snapshot",
        "schedule": crontab(minute="*/15"),
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
    "backfill-settled-gap-creation": {
        # #138/#995: create the freeze-gap markets (2026-06-09→07-08). Runs 30min
        # after the settled-events pass so it creates missing markets that the
        # settled/candlestick/calibration passes then enrich next cycle.
        "task": "app.tasks.backfill_settled_gap_creation",
        "schedule": crontab(minute=30, hour="5,11,17,23"),
        "kwargs": {"limit": 1500},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-matchups": {
        # #173/#1024: catch-up net for matchup_title. The ingest write-hook now
        # stamps fresh poly game sub-markets at birth, but the historical backlog
        # (rows ingested before the hook) still needs the one-shot logic, and any
        # row that slips through (e.g. a sibling that named the matchup was absent
        # in the ingested batch) converges here. Idempotent (writes only where
        # missing); runs 45min after the gap-creation pass so newly-created rows
        # get a title the same cycle. Previously on-demand only (no beat).
        "task": "app.tasks.backfill_polymarket_matchups",
        "schedule": crontab(minute=45, hour="5,11,17,23"),
        "kwargs": {"all_groups": True},
        "options": {"queue": "background"},
    },
    "recover-datagolf-participation": {
        # #994: re-enabled after diagnosis (#136). The "400s" that blocked the
        # first attempt were mostly 429 rate-limits — DataGolf caps at 45 req/min
        # and the old 0.5s pacing = 120/min. The recovery now paces BEFORE every
        # request (1.5s = 40/min) and stops-and-resumes on any residual 429, so it
        # drains autonomously (the ~189-market cohort in 1-2 beats) with no manual
        # trigger. Genuinely-invalid tours (e.g. 'alt') → residual/symmetric-
        # exclude. Offset from the other datagolf tasks to avoid sharing the cap.
        "task": "app.tasks.recover_datagolf_participation",
        "schedule": crontab(minute=30, hour="4,10,16,22"),
        "kwargs": {"limit": 200},
        "options": {"queue": "background"},
    },
    "regrade-polymarket-under-signflip": {
        # #145 Item 1: dedicated task — the #137 poly Under/No sign-flip regrade
        # was a backfill_winners phase that never ran (pipeline budget-guards out
        # before calibration_prices). One cheap idempotent UPDATE; drains the
        # ~36K-row class and forward-fixes any rows the poller re-introduces.
        "task": "app.tasks.regrade_polymarket_under_signflip",
        "schedule": crontab(minute=45, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "unresolve-datagolf-premature": {
        # #146 Item 2: starvation sibling of the poly flip — the #137 integrity
        # block never runs (budget guard stops before calibration_prices).
        "task": "app.tasks.unresolve_datagolf_premature",
        "schedule": crontab(minute=50, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "null-impossible-both-sides-openings": {
        # #146 Item 2: starvation sibling of the poly flip (same reason).
        "task": "app.tasks.null_impossible_both_sides_openings",
        "schedule": crontab(minute=55, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "correct-both-winner-guess-side": {
        # #997: starvation sibling of the #146 integrity beats — demote the
        # guess side of both-winner mutually-exclusive binaries. Offset a few
        # minutes after the both-sides null so they never contend for the worker.
        "task": "app.tasks.correct_both_winner_guess_side",
        "schedule": crontab(minute=58, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "compute-calibration-prices": {
        # #180 Item 1 — THE autopilot fix. `_compute_calibration_prices` was ONLY
        # a backfill_winners phase, but that pipeline budget-guards out at
        # `stopped_before: calibration_prices` on EVERY run (the 840s guard is spent
        # on resolution before it reaches the pricing step), so the pricing step
        # NEVER ran in production. Result: recent-cohort cal_prob coverage collapsed
        # (kalshi 24.2%→4.2%, poly 80.2%→9.2%, June→July 2026). Extracted to its own
        # dedicated task (same pattern as the #145/#146 integrity siblings above) so
        # it drains autonomously. Monotonic + resumable by construction: every part
        # selects `calibration_probability IS NULL` and commits per 100K batch, so a
        # soft-limit kill just resumes from the remaining NULL rows next run — it
        # NEVER restarts from scratch (gotcha #34). Runs in the empty 2/8/14/20 hour
        # windows (clear of backfill_winners :45@3,9,15,21 and the :40-:58@5,11,17,23
        # integrity beats) so it prices the freshly-resolved/nulled rows those beats
        # leave behind. 10-min soft-limit (600s) matches the task def.
        #
        # #183 Item 3 de-contention (r178: zero SCHEDULED fires observed): the
        # background worker is Standard-1X concurrency=2 (only two slots). The
        # original :15 minute collided EVERY slot with a pile-up of ~9 background
        # beats — critically `precompute-calibration-main` (minute=15 HOURLY, also a
        # 600s calibration grinder) AND `mark-resolved-futures` (:15 @ 2,8,14,20) —
        # so calibration_prices routinely arrived as the 3rd+ task at :15 and lost
        # the 2-slot race, never getting to run (gotcha #12/#39 discipline: a long
        # co-scheduled task can starve a beat on a shared worker). Moved to :10,
        # which fires only three fast */10 Redis cache-warmers (freshness-watchdog,
        # max-movement, admin-link-rate) in these hours — no 600s contender — so the
        # task now gets a free slot at dispatch. Still clear of backfill_winners and
        # the integrity beats; ordering vs the resolution beats is preserved.
        "task": "app.tasks.compute_calibration_prices",
        "schedule": crontab(minute=10, hour="2,8,14,20"),
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
    "backfill-espn-win-prob-oldest": {
        # #207 Item 2: oldest-first pass drains the OLD tail the newest-first run
        # can never reach (gotcha #41). Daily so both ends make progress.
        "task": "app.tasks.backfill_espn_win_prob",
        "schedule": crontab(minute=20, hour=3),  # Daily 03:20 UTC, off-peak
        "kwargs": {"limit": 200, "oldest_first": True},
        "options": {"queue": "background"},
    },
    "backfill-canonical-keys-daily": {
        "task": "app.tasks.backfill_canonical_keys",
        "schedule": crontab(minute=30, hour=8),  # Daily at 8:30 AM UTC
        "kwargs": {"limit": 2000},
    },
    "backfill-market-shapes": {
        # Queue #194 Item 1 / Queue #260 — recompute + persist the semantics v2
        # contract (display shape in market_type; relation/exhaustive/
        # expected_winners/fingerprint in market_metadata.shape).
        # Every 20 min: rolls over all rows in bounded/resumable cursor passes,
        # recomputing on NULL / version-old / fingerprint-change and writing
        # only on change (so a converged table costs reads only).
        "task": "app.tasks.backfill_market_shapes",
        "schedule": crontab(minute="*/20"),
        "kwargs": {"limit": 40000},
        "options": {"queue": "background"},
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
    "morning-digest-daily": {
        # Queue #200: notifications v1 — one daily push of the 3-5 most
        # interesting probabilities to opted-in device tokens. Reuses cached
        # Discover interestingness (one content brain). 14:05 UTC = 7:05 AM PT
        # (staggered 5 min after the daily-challenge push).
        "task": "app.tasks.send_morning_digest",
        "schedule": crontab(hour=14, minute=5),
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
    "precompute-source-intelligence": {
        "task": "app.tasks.precompute_source_intelligence",
        "schedule": crontab(minute=30, hour="1,7,13,19"),  # Every 6 hours, offset 30min
        "options": {"queue": "background"},
    },
    "precompute-admin-audit-all": {
        "task": "app.tasks.precompute_admin_audit_all",
        "schedule": crontab(minute="*/15"),  # Every 15 min — keeps /audit/all cache warm
        "options": {"queue": "background"},
    },
    "precompute-admin-link-rate": {
        "task": "app.tasks.precompute_admin_link_rate",
        "schedule": crontab(minute="*/10"),  # Every 10 min — keeps /link-rate cache warm
        "options": {"queue": "background"},
    },
    "precompute-admin-matured-linkage": {
        "task": "app.tasks.precompute_admin_matured_linkage",
        "schedule": crontab(minute="*/10"),  # Every 10 min — matured-linkage headline (Item 2)
        "options": {"queue": "background"},
    },
}

# Route the heavy grinder class onto the dedicated `heavy` worker. Beat entries
# pin `options["queue"]` explicitly, which OVERRIDES task_routes at dispatch
# time — so both must agree. This loop is the single source of truth: it flips
# every HEAVY_TASKS beat entry to the heavy queue regardless of what it was
# authored with. (See the queue-routing comment block above for the rationale.)
for _beat_entry in celery_app.conf.beat_schedule.values():
    if _beat_entry.get("task") in HEAVY_TASKS:
        _beat_entry.setdefault("options", {})["queue"] = "heavy"


# Queue 300R Item 1 — targeted result suppression. Must run AFTER the beat
# schedule exists (it is derived from it) and after every task decorator has
# run. Beat-only tasks with no HTTP dispatcher stop writing a celery-task-meta
# key; anything an admin route can hand a task_id for keeps its result. Health
# and observability are unaffected — those read the `bainluck:task_metrics:*`
# hash written by `_tracked_run`, not the result backend. See
# app/tasks/result_retention.py for the full argument and the drift guard.
_SUPPRESSED_RESULT_TASKS = _apply_result_suppression(celery_app)


# =============================================================================
# Backward-compatible re-exports
#
# These allow existing code that does `from app.tasks import _infer_base_sport`
# or `from app.tasks import celery_app` to keep working.
# =============================================================================

from app.tasks.futures import _infer_base_sport  # noqa: E402, F401 (used by routes/futures.py)
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: E402, F401
