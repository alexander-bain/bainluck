"""
Redis-based adaptive polling state management.
"""

import hashlib
import json
import logging
import os
import time

import redis

logger = logging.getLogger(__name__)

from app.tasks.config import (
    POLL_STATE_KEY,
    LIVE_POLL_INTERVAL,
    FAST_POLL_INTERVAL,
    MEDIUM_POLL_INTERVAL,
    SLOW_POLL_INTERVAL,
    MEDIUM_THRESHOLD,
    SLOW_THRESHOLD,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis_client(socket_timeout=None, socket_connect_timeout=None):
    """Get sync Redis client with proper SSL handling for Heroku.

    #995 attempt-9: ``socket_timeout``/``socket_connect_timeout`` (seconds) bound
    every blocking Redis op on the returned client. A sync client with NO timeout
    (the default) will block the CALLING thread forever if Redis hangs — and when
    that caller is a phase-marker ``setex`` invoked from inside an asyncio loop
    (poll_kalshi's ``progress_cb``), the frozen thread IS the event loop, so no
    ``wait_for``/deadline timer can ever fire. That is the residual sync block
    that survived attempts 5-8. Bounded callers fail fast (raise, get swallowed)
    instead of freezing the loop.
    """
    import ssl

    kwargs = {}
    if socket_timeout is not None:
        kwargs["socket_timeout"] = socket_timeout
    if socket_connect_timeout is not None:
        kwargs["socket_connect_timeout"] = socket_connect_timeout

    if REDIS_URL.startswith("rediss://"):
        return redis.from_url(
            REDIS_URL,
            ssl_cert_reqs=ssl.CERT_NONE,
            **kwargs,
        )
    return redis.from_url(REDIS_URL, **kwargs)


def get_async_redis_client():
    """Get async Redis client for use in FastAPI route handlers."""
    import ssl
    import redis.asyncio as aioredis

    if REDIS_URL.startswith("rediss://"):
        return aioredis.from_url(
            REDIS_URL,
            ssl_cert_reqs=ssl.CERT_NONE
        )
    return aioredis.from_url(REDIS_URL)


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
        logger.warning("Redis error in should_poll_now: %s", e)
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
        logger.warning("Redis error in update_poll_state: %s", e)


# =============================================================================
# Task-Level Success Metrics
# =============================================================================

# Redis key prefix for task metrics. Each task gets a hash:
#   bainluck:task_metrics:{task_name} -> {
#       last_success_at, last_failure_at, last_duration_ms,
#       success_count_24h, failure_count_24h,
#       last_result_summary (JSON), consecutive_failures
#   }
TASK_METRICS_PREFIX = "bainluck:task_metrics"
# How long to keep metrics (48 hours — enough for dashboard + debugging)
TASK_METRICS_TTL = 172800

# Task metric labels that were RETIRED from the beat schedule but whose celery
# task + Redis metrics are intentionally kept dormant/registered (e.g. for a
# cheap re-add). Their last-run metrics never refresh, so a stale
# consecutive_failures count would latch the whole health surface to
# "degraded"/"critical" forever (a permanent false alarm). get_task_metrics
# reports these as health="retired" so every rollup that filters on
# "degraded"/"critical" (celery dashboard, build_worker_section, LLM diagnosis)
# drops them automatically. Re-adding a task to the beat = remove it from here.
# Match the label passed to _tracked_run(), not the fully-qualified beat name.
RETIRED_TASK_LABELS = frozenset({
    "resolve_winners",  # retired 2026-07-06 (#991); dormant, folded into backfill_winners
})


def record_task_success(task_name: str, duration_ms: float, result_summary: dict | None = None):
    """
    Record a successful task execution with key output metrics.

    Args:
        task_name: Short task identifier (e.g., "poll_odds", "espn_sync")
        duration_ms: How long the task took
        result_summary: Key-value pairs from the task's return dict
                       (e.g., {"events_synced": 12, "errors": 0})
    """
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        now_iso = _utc_now_iso()

        # Increment 24h success counter
        success_key = f"{TASK_METRICS_PREFIX}:{task_name}:successes"
        pipe = r.pipeline()
        pipe.hset(key, mapping={
            "last_success_at": now_iso,
            "last_duration_ms": str(round(duration_ms)),
            "last_result_summary": json.dumps(result_summary or {}),
            "consecutive_failures": "0",
        })
        pipe.expire(key, TASK_METRICS_TTL)
        pipe.incr(success_key)
        pipe.expire(success_key, 86400)  # 24h rolling window
        pipe.execute()
    except Exception as e:
        # Never let metrics recording break a task
        pass


def record_task_failure(task_name: str, duration_ms: float, error: str):
    """Record a failed task execution."""
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        now_iso = _utc_now_iso()

        # Get current consecutive failures
        current = int(r.hget(key, "consecutive_failures") or 0)

        failure_key = f"{TASK_METRICS_PREFIX}:{task_name}:failures"
        pipe = r.pipeline()
        pipe.hset(key, mapping={
            "last_failure_at": now_iso,
            "last_duration_ms": str(round(duration_ms)),
            "last_error": error[:500],  # Truncate long errors
            "consecutive_failures": str(current + 1),
        })
        pipe.expire(key, TASK_METRICS_TTL)
        pipe.incr(failure_key)
        pipe.expire(failure_key, 86400)
        pipe.execute()
    except Exception:
        pass


def get_task_metrics(task_name: str) -> dict:
    """Get metrics for a specific task."""
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        data = r.hgetall(key)
        if not data:
            return {"task": task_name, "status": "no_data"}

        success_key = f"{TASK_METRICS_PREFIX}:{task_name}:successes"
        failure_key = f"{TASK_METRICS_PREFIX}:{task_name}:failures"
        successes_24h = int(r.get(success_key) or 0)
        failures_24h = int(r.get(failure_key) or 0)

        result = {"task": task_name, "successes_24h": successes_24h, "failures_24h": failures_24h}

        for k, v in data.items():
            k_str = k.decode() if isinstance(k, bytes) else k
            v_str = v.decode() if isinstance(v, bytes) else v
            if k_str == "last_result_summary":
                try:
                    result[k_str] = json.loads(v_str)
                except (json.JSONDecodeError, TypeError):
                    result[k_str] = v_str
            else:
                result[k_str] = v_str

        # Compute health status. Retired tasks report a distinct "retired"
        # health so their stale metrics can't latch the health rollups to
        # degraded/critical (those rollups filter on health == degraded/critical).
        if task_name in RETIRED_TASK_LABELS:
            result["retired"] = True
            result["health"] = "retired"
            return result

        consecutive = int(result.get("consecutive_failures", 0))
        if consecutive >= 5:
            result["health"] = "critical"
        elif consecutive >= 2:
            result["health"] = "degraded"
        elif successes_24h == 0 and failures_24h == 0:
            result["health"] = "no_data"
        else:
            result["health"] = "healthy"

        return result
    except Exception as e:
        return {"task": task_name, "status": "error", "error": str(e)}


def get_all_task_metrics() -> list[dict]:
    """Get metrics for all tracked tasks."""
    try:
        r = get_redis_client()
        # Find all task metric keys
        pattern = f"{TASK_METRICS_PREFIX}:*"
        keys = r.keys(pattern)

        # Extract unique task names (skip :successes and :failures counter keys)
        task_names = set()
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) == 3:
                # bainluck:task_metrics:task_name
                task_names.add(parts[2])

        return [get_task_metrics(name) for name in sorted(task_names)]
    except Exception as e:
        return [{"status": "error", "error": str(e)}]


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Odds API Quota Monitoring
# =============================================================================

QUOTA_KEY = "bainluck:odds_api_quota"
QUOTA_HISTORY_PREFIX = "bainluck:odds_api_quota:hourly"
QUOTA_TASK_HOURLY_PREFIX = "bainluck:odds_api_quota:task_hourly"
QUOTA_SPORT_HOURLY_PREFIX = "bainluck:odds_api_quota:sport_hourly"
QUOTA_ALERT_THRESHOLD = 500_000
QUOTA_WARNING_THRESHOLD = 1_000_000

# Emergency quota guard thresholds — TRUE EMERGENCIES ONLY.
# This is a last-resort circuit breaker, not a routine optimization tool.
# Prefer rate-limiting, tier adjustments, and region trimming first.
#
# The guard is purely remaining-driven: check_quota_guard() compares the live
# `remaining` reading (refreshed on every Odds API response via
# record_odds_api_quota) against these thresholds. There is NO date/expiry
# constant and there must never be one — a hardcoded expiry date silently
# disabled the guard once it rolled past (the QUOTA_GUARD_EXPIRY regression).
# Recovery is automatic: when the billing cycle resets, the API returns a
# refilled `remaining` and the guard stops tripping with no code change. Do not
# reintroduce a date-based enable/disable; gate only on `remaining`.
QUOTA_GUARD_LIVE_ONLY = 50_000   # Below this: only poll live games (no discovery/futures)
QUOTA_GUARD_FULL_STOP = 20_000   # Below this: stop ALL Odds API calls (except priority sports)
QUOTA_GUARD_ABSOLUTE_STOP = 500  # Below this: stop ALL Odds API calls, no exceptions

# Priority sports: allowed to poll even in FULL_STOP mode with conservation settings.
# h2h only, single region, slower interval.
QUOTA_GUARD_PRIORITY_SPORTS = frozenset({
    "basketball_nba",
    "baseball_mlb",
    "basketball_ncaab",
})
# Conservation poll interval for priority sports in low-quota mode (10 min)
QUOTA_GUARD_CONSERVATION_INTERVAL = 600

import logging
_quota_logger = logging.getLogger(__name__)


def check_quota_guard(task_type: str, sport_key: str | None = None) -> tuple[bool, str]:
    """Check if an Odds API task should proceed based on remaining quota.

    Args:
        task_type: One of "poll_odds", "discover_events", "poll_futures".
                   "poll_odds" is further split: live games always allowed
                   until FULL_STOP; non-live polling stops at LIVE_ONLY.
        sport_key: Optional sport key for per-sport priority filtering.

    Returns:
        (should_proceed, reason) — False means skip this task entirely.
        Reason strings:
          "conservation_<remaining>" — proceed but use h2h/us only + slow interval
          "live_only_<remaining>" — proceed but only live games
          "full_stop_<remaining>" — do not proceed
    """
    from datetime import datetime, timezone

    r = get_redis_client()
    if not r:
        return True, "no_redis"

    try:
        data = r.hgetall(QUOTA_KEY)
        if not data:
            return True, "no_quota_data"

        remaining = int(data.get(b"remaining", b"999999"))

        # Absolute stop: no exceptions, no priority sports, nothing.
        # Live game data still flows via ESPN, StatPal, Kalshi, Polymarket.
        if remaining <= QUOTA_GUARD_ABSOLUTE_STOP:
            _quota_logger.critical(
                "QUOTA GUARD: ABSOLUTE STOP — %s remaining. Blocking ALL Odds API calls.",
                f"{remaining:,}",
            )
            return False, f"absolute_stop_{remaining}"

        if remaining <= QUOTA_GUARD_FULL_STOP:
            # Priority sports get through in conservation mode
            if task_type == "poll_odds" and sport_key in QUOTA_GUARD_PRIORITY_SPORTS:
                _quota_logger.info(
                    "QUOTA GUARD: conservation mode — %s remaining. Allowing priority sport %s.",
                    f"{remaining:,}", sport_key,
                )
                return True, f"conservation_{remaining}"
            _quota_logger.critical(
                "QUOTA GUARD: FULL STOP — %s remaining. Blocking %s.",
                f"{remaining:,}", task_type,
            )
            return False, f"full_stop_{remaining}"

        if remaining <= QUOTA_GUARD_LIVE_ONLY:
            # Only live game polling is allowed
            if task_type in ("discover_events", "poll_futures"):
                _quota_logger.warning(
                    "QUOTA GUARD: live-only mode — %s remaining. Blocking %s.",
                    f"{remaining:,}", task_type,
                )
                return False, f"live_only_{remaining}"
            # poll_odds proceeds but will be filtered to live-only by caller
            return True, f"live_only_{remaining}"

        return True, f"ok_{remaining}"
    except Exception:
        return True, "redis_error"


def record_odds_api_quota(
    remaining: int,
    used: int,
    source_task: str,
    pre_call_used: int | None = None,
    sport_key: str | None = None,
):
    """Store latest quota reading from passive header capture.

    Args:
        remaining: Remaining quota from API header
        used: Used quota from API header (after the call)
        source_task: Which task made the call (poll_odds, discover_events, poll_futures)
        pre_call_used: Used quota BEFORE the API call (from a previous header read).
                       If provided, enables accurate per-task attribution.
        sport_key: Optional sport identifier the call was made for. When provided
                   alongside a positive delta, billed units are also attributed to
                   a per-sport hourly bucket, enabling per-sport cost visibility.
    """
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return
    try:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")

        pipe = r.pipeline()
        # Current snapshot (always up to date)
        pipe.hset(QUOTA_KEY, mapping={
            "remaining": str(remaining),
            "used": str(used),
            "updated_at": now.isoformat(),
            "source_task": source_task,
        })
        pipe.expire(QUOTA_KEY, 86400 * 7)  # 7 day TTL

        # Hourly history (for graphing)
        history_key = f"{QUOTA_HISTORY_PREFIX}:{hour_key}"
        pipe.hset(history_key, mapping={
            "remaining": str(remaining),
            "used": str(used),
        })
        pipe.expire(history_key, 86400 * 35)  # 35 day TTL (covers full billing cycle)

        # Per-task quota delta tracking
        # Use pre_call_used if provided (accurate per-task attribution),
        # otherwise fall back to global prev_used (may misattribute across tasks)
        if pre_call_used is not None:
            delta = used - pre_call_used
        else:
            prev_data = r.hgetall(QUOTA_KEY)
            prev_used = int(prev_data.get(b"used", b"0")) if prev_data else 0
            delta = used - prev_used
        if delta > 0:  # Skip negative deltas (month rollover)
            task_hourly_key = f"{QUOTA_TASK_HOURLY_PREFIX}:{source_task}:{hour_key}"
            pipe.incrby(task_hourly_key, delta)
            pipe.expire(task_hourly_key, 86400 * 35)  # 35 day TTL

            # Per-sport attribution (only when caller supplies a sport_key).
            # Sharing the same delta as task attribution keeps totals consistent.
            if sport_key:
                sport_hourly_key = f"{QUOTA_SPORT_HOURLY_PREFIX}:{sport_key}:{hour_key}"
                pipe.incrby(sport_hourly_key, delta)
                pipe.expire(sport_hourly_key, 86400 * 35)

        pipe.execute()

        # Log warnings at threshold crossings
        if remaining <= QUOTA_ALERT_THRESHOLD:
            _quota_logger.warning(
                "ODDS API QUOTA LOW: %s remaining (%s used)", f"{remaining:,}", f"{used:,}"
            )
        elif remaining <= QUOTA_WARNING_THRESHOLD:
            _quota_logger.warning(
                "Odds API quota low: %s remaining (%s used)", f"{remaining:,}", f"{used:,}"
            )
    except Exception:
        pass  # Never break a task for metrics


def get_odds_api_quota() -> dict:
    """Get current quota snapshot from Redis."""
    r = get_redis_client()
    if not r:
        return {"status": "unknown"}
    try:
        data = r.hgetall(QUOTA_KEY)
        if not data:
            return {"status": "no_data"}

        remaining = int(data.get(b"remaining", b"0"))
        used = int(data.get(b"used", b"0"))
        total = remaining + used
        pct_used = (used / total * 100) if total > 0 else 0

        if remaining <= QUOTA_ALERT_THRESHOLD:
            health = "critical"
        elif remaining <= QUOTA_WARNING_THRESHOLD:
            health = "warning"
        else:
            health = "healthy"

        return {
            "remaining": remaining,
            "used": used,
            "total": total,
            "pct_used": round(pct_used, 1),
            "health": health,
            "updated_at": data.get(b"updated_at", b"").decode(),
            "source_task": data.get(b"source_task", b"").decode(),
        }
    except Exception:
        return {"status": "error"}


def get_odds_api_quota_history(hours: int = 168) -> list:
    """Get hourly quota history for graphing (default: 7 days)."""
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return []
    try:
        now = datetime.now(timezone.utc)
        results = []
        for h in range(hours):
            dt = now - timedelta(hours=h)
            key = f"{QUOTA_HISTORY_PREFIX}:{dt.strftime('%Y-%m-%dT%H')}"
            data = r.hgetall(key)
            if data:
                results.append({
                    "hour": dt.strftime("%Y-%m-%dT%H:00Z"),
                    "remaining": int(data.get(b"remaining", b"0")),
                    "used": int(data.get(b"used", b"0")),
                })
        return list(reversed(results))
    except Exception:
        return []


def get_odds_api_task_breakdown(hours: int = 168) -> list:
    """Get daily quota usage breakdown by task type.

    Args:
        hours: Number of hours to look back (default: 168 = 7 days)

    Returns:
        List of daily totals per task, e.g.:
        [{"date": "2026-03-26", "poll_odds": 50000, "discover_events": 10000, "poll_futures": 5000}]
    """
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    r = get_redis_client()
    if not r:
        return []
    try:
        # Scan for all task_hourly keys
        pattern = f"{QUOTA_TASK_HOURLY_PREFIX}:*"
        keys = r.keys(pattern)

        # Group by date and task
        daily_data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Format: bainluck:odds_api_quota:task_hourly:{task_name}:{YYYY-MM-DDTHH}
            parts = key_str.split(":")
            if len(parts) >= 5:
                task_name = parts[3]
                hour_str = parts[4]
                date_str = hour_str[:10]  # Extract YYYY-MM-DD

                delta = int(r.get(key) or 0)
                daily_data[date_str][task_name] += delta

        # Convert to list format, sorted by date
        results = []
        for date in sorted(daily_data.keys()):
            entry = {"date": date}
            entry.update(daily_data[date])
            results.append(entry)

        return results
    except Exception:
        return []


def get_odds_api_sport_breakdown(hours: int = 24) -> list:
    """Get billed-unit usage broken down by sport_key over a rolling window.

    Per-sport attribution is only populated when callers pass ``sport_key`` to
    ``record_odds_api_quota`` — discovery, live polling, and futures all do so.

    Args:
        hours: Number of hours to look back (default: 24)

    Returns:
        List of per-sport totals sorted by usage descending, e.g.:
        [{"sport": "basketball_nba", "billed_units": 42000, "hours": 24}, ...]
    """
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    r = get_redis_client()
    if not r:
        return []
    try:
        now = datetime.now(timezone.utc)
        # Build the set of hour keys within the window so we only aggregate
        # buckets we actually care about (avoids scan-every-key blowups).
        window_hours = {
            (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H")
            for h in range(hours)
        }

        pattern = f"{QUOTA_SPORT_HOURLY_PREFIX}:*"
        keys = r.keys(pattern)

        per_sport: dict[str, int] = defaultdict(int)
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Format: bainluck:odds_api_quota:sport_hourly:{sport_key}:{YYYY-MM-DDTHH}
            # sport_key may itself contain colons in theory; split from the right.
            parts = key_str.rsplit(":", 1)
            if len(parts) != 2:
                continue
            hour_str = parts[1]
            if hour_str not in window_hours:
                continue
            # Strip the shared prefix (plus trailing colon) to recover sport_key
            prefix_len = len(QUOTA_SPORT_HOURLY_PREFIX) + 1
            sport_key = parts[0][prefix_len:]
            if not sport_key:
                continue
            try:
                delta = int(r.get(key) or 0)
            except (TypeError, ValueError):
                continue
            per_sport[sport_key] += delta

        results = [
            {"sport": sport, "billed_units": units, "hours": hours}
            for sport, units in per_sport.items()
        ]
        results.sort(key=lambda row: row["billed_units"], reverse=True)
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Database size history (for trended storage view)
# ---------------------------------------------------------------------------

DB_SIZE_HISTORY_PREFIX = "bainluck:db_size_history"

# ---------------------------------------------------------------------------
# StatPal API usage tracking
# ---------------------------------------------------------------------------

STATPAL_USAGE_KEY = "bainluck:statpal_usage"
STATPAL_USAGE_HISTORY_PREFIX = "bainluck:statpal_usage:daily"


def record_statpal_usage(request_count: int, api_date: str):
    """Store a StatPal daily request count reading.

    Args:
        request_count: Number of requests made today (from StatPal API).
        api_date: Date string from the API response (YYYY-MM-DD).
    """
    from datetime import datetime, timezone

    r = get_redis_client()
    if not r:
        return
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        r.hset(STATPAL_USAGE_KEY, mapping={
            "request_count": request_count,
            "date": api_date,
            "updated_at": now_str,
        })
        # Also store in daily history (keyed by the API date)
        history_key = f"{STATPAL_USAGE_HISTORY_PREFIX}:{api_date}"
        r.set(history_key, str(request_count), ex=86400 * 90)  # 90 day TTL
    except Exception:
        pass


def get_statpal_usage() -> dict:
    """Get current StatPal usage snapshot from Redis."""
    r = get_redis_client()
    if not r:
        return {"status": "unknown"}
    try:
        data = r.hgetall(STATPAL_USAGE_KEY)
        if not data:
            return {"status": "no_data"}
        return {
            "request_count": int(data.get(b"request_count", b"0")),
            "date": data.get(b"date", b"").decode(),
            "updated_at": data.get(b"updated_at", b"").decode(),
        }
    except Exception:
        return {"status": "error"}


def get_statpal_usage_history(days: int = 90) -> list:
    """Get daily StatPal request counts for trending."""
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return []
    try:
        results = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            key = f"{STATPAL_USAGE_HISTORY_PREFIX}:{day}"
            val = r.get(key)
            if val:
                results.append({"date": day, "request_count": int(val)})
        return results
    except Exception:
        return []


def record_db_size(size_mb: float):
    """Store a DB size reading keyed by date (one per day)."""
    from datetime import datetime, timezone
    r = get_redis_client()
    if not r:
        return
    try:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history_key = f"{DB_SIZE_HISTORY_PREFIX}:{day_key}"
        r.set(history_key, str(round(size_mb, 1)), ex=86400 * 90)  # 90 day TTL
    except Exception:
        pass


def get_db_size_history(days: int = 90) -> list:
    """Get daily DB size readings for trending."""
    from datetime import datetime, timezone, timedelta
    r = get_redis_client()
    if not r:
        return []
    try:
        results = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            key = f"{DB_SIZE_HISTORY_PREFIX}:{day}"
            val = r.get(key)
            if val:
                results.append({"date": day, "size_mb": float(val)})
        return results
    except Exception:
        return []


# =============================================================================
# Link Rate Change Detection
# =============================================================================

LINK_RATE_SNAPSHOT_PREFIX = "bainluck:link_rate_snapshot"
SOURCE_COVERAGE_SNAPSHOT_PREFIX = "bainluck:source_coverage_snapshot"


def record_link_rate_snapshot(rates: dict[str, float]) -> None:
    """Store today's per-sport/league link rates in Redis.

    Args:
        rates: {"kalshi:basketball_nba": 100.0, "polymarket:tennis": 35.1, ...}
    """
    from datetime import datetime, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{LINK_RATE_SNAPSHOT_PREFIX}:{today}"
        r.hset(key, mapping={k: str(v) for k, v in rates.items()})
        r.expire(key, 86400 * 7)
    except Exception:
        pass


def get_link_rate_changes(threshold_pp: float = 5.0) -> list[dict]:
    """Compare today's link rates vs yesterday's. Return significant changes.

    Returns list of {"key": "kalshi:basketball_nba", "today": 95.0, "yesterday": 100.0, "delta": -5.0}
    """
    from datetime import datetime, timedelta, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        today_data = r.hgetall(f"{LINK_RATE_SNAPSHOT_PREFIX}:{today}")
        yesterday_data = r.hgetall(f"{LINK_RATE_SNAPSHOT_PREFIX}:{yesterday}")

        if not today_data or not yesterday_data:
            return []

        def _decode(d):
            return {
                (k.decode() if isinstance(k, bytes) else k): float(v.decode() if isinstance(v, bytes) else v)
                for k, v in d.items()
            }

        today_rates = _decode(today_data)
        yesterday_rates = _decode(yesterday_data)

        changes = []
        for key in set(today_rates) | set(yesterday_rates):
            t = today_rates.get(key)
            y = yesterday_rates.get(key)
            if t is not None and y is not None:
                delta = t - y
                if abs(delta) >= threshold_pp:
                    changes.append({"key": key, "today": t, "yesterday": y, "delta": round(delta, 1)})
            elif t is not None and y is None:
                changes.append({"key": key, "today": t, "yesterday": None, "delta": None, "note": "new"})
            elif t is None and y is not None:
                changes.append({"key": key, "today": None, "yesterday": y, "delta": None, "note": "disappeared"})

        return sorted(changes, key=lambda c: abs(c.get("delta") or 0), reverse=True)
    except Exception:
        return []


def record_source_coverage_snapshot(rates: dict[str, float]) -> None:
    """Store today's per-sport/source event coverage rates in Redis."""
    from datetime import datetime, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{today}"
        r.hset(key, mapping={k: str(v) for k, v in rates.items()})
        r.expire(key, 86400 * 7)
    except Exception:
        pass


def get_source_coverage_changes(threshold_pp: float = 5.0) -> list[dict]:
    """Compare today's source coverage vs yesterday's. Return significant changes."""
    from datetime import datetime, timedelta, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        today_data = r.hgetall(f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{today}")
        yesterday_data = r.hgetall(f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{yesterday}")

        if not today_data or not yesterday_data:
            return []

        def _decode(d):
            return {
                (k.decode() if isinstance(k, bytes) else k): float(v.decode() if isinstance(v, bytes) else v)
                for k, v in d.items()
            }

        today_rates = _decode(today_data)
        yesterday_rates = _decode(yesterday_data)

        changes = []
        for key in set(today_rates) | set(yesterday_rates):
            t = today_rates.get(key)
            y = yesterday_rates.get(key)
            if t is not None and y is not None:
                delta = t - y
                if abs(delta) >= threshold_pp:
                    changes.append({"key": key, "today": t, "yesterday": y, "delta": round(delta, 1)})

        return sorted(changes, key=lambda c: abs(c.get("delta") or 0), reverse=True)
    except Exception:
        return []
