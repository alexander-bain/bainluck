"""
Redis-based adaptive polling state management.
"""

import hashlib
import json
import os
import time

import redis

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

        # Compute health status
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
QUOTA_ALERT_THRESHOLD = 500_000
QUOTA_WARNING_THRESHOLD = 1_000_000

import logging
_quota_logger = logging.getLogger(__name__)


def record_odds_api_quota(remaining: int, used: int, source_task: str, pre_call_used: int | None = None):
    """Store latest quota reading from passive header capture.

    Args:
        remaining: Remaining quota from API header
        used: Used quota from API header (after the call)
        source_task: Which task made the call (poll_odds, discover_events, poll_futures)
        pre_call_used: Used quota BEFORE the API call (from a previous header read).
                       If provided, enables accurate per-task attribution.
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

        pipe.execute()

        # Log warnings at threshold crossings
        if remaining <= QUOTA_ALERT_THRESHOLD:
            _quota_logger.critical(
                "ODDS API QUOTA CRITICAL: %s remaining (%s used)", f"{remaining:,}", f"{used:,}"
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
